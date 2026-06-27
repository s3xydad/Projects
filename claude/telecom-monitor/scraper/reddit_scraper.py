"""Reddit scraper using PRAW.

Requirements:
  pip install praw
  Create a Reddit app at https://www.reddit.com/prefs/apps (script type).
  Set REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USER_AGENT in .env.

Rate limits (free tier, per OAuth client ID):
  - 100 QPM averaged over a 10-minute window (burst up to 1,000 per window).
  - Response headers report current usage:
      X-Ratelimit-Used      — requests used this period
      X-Ratelimit-Remaining — requests left this period
      X-Ratelimit-Reset     — seconds until the period resets
  - PRAW reads these headers automatically via `reddit.auth.limits` and
    sleeps when `remaining` hits 0, so we don't need to parse them manually.
  - We set a 0.65 s floor delay (≈ 92 QPM) to stay ~8 % under the cap and
    leave headroom for PRAW's own internal requests (e.g. token refresh).
  - Do NOT add extra sleeps inside PRAW's own listing generators — PRAW's
    built-in throttle already handles inter-request pacing for those calls.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Generator

import praw
from praw.exceptions import PRAWException

import config
from scraper.base import BaseScraper

logger = logging.getLogger(__name__)

# 0.65 s ≈ 92 QPM — safely under the 100 QPM free-tier cap.
# PRAW's own throttle is the hard backstop; this just prevents unnecessary
# bursting and gives a small buffer for token-refresh requests.
_REDDIT_MIN_DELAY = 0.65


class RedditScraper(BaseScraper):
    robots_url = "https://www.reddit.com/robots.txt"

    def __init__(self):
        super().__init__(min_delay=_REDDIT_MIN_DELAY, max_retries=config.MAX_RETRIES)
        self._reddit: praw.Reddit | None = None

    def _get_reddit(self) -> praw.Reddit:
        if self._reddit is None:
            self._reddit = praw.Reddit(
                client_id=config.REDDIT_CLIENT_ID,
                client_secret=config.REDDIT_CLIENT_SECRET,
                user_agent=config.REDDIT_USER_AGENT,
                read_only=True,
                # ratelimit_seconds: max seconds PRAW will auto-sleep on 429.
                # Default is 5; bump to 65 so it waits out a full reset window
                # rather than erroring immediately.
                ratelimit_seconds=65,
            )
        return self._reddit

    def _log_quota(self) -> None:
        """Log remaining quota from PRAW's cached header values."""
        limits = getattr(self._reddit, "auth", None)
        if limits is None:
            return
        info = getattr(limits, "limits", {})
        if info:
            logger.debug(
                "Reddit quota — used: %s  remaining: %s  reset_in: %ss",
                info.get("used", "?"),
                info.get("remaining", "?"),
                info.get("reset_timestamp", "?"),
            )

    def scrape(self, lookback_days: int = config.LOOKBACK_DAYS, **_) -> list[dict]:
        reddit = self._get_reddit()
        cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
        results: list[dict] = []
        seen: set[str] = set()

        # 1. Subreddit new-post listings
        # PRAW's ListingGenerator auto-throttles these via X-Ratelimit-* headers,
        # so we don't add a manual delay inside _iter_subreddit.
        for sub_name in config.REDDIT_SUBREDDITS:
            logger.info("Scanning r/%s", sub_name)
            try:
                sub = reddit.subreddit(sub_name)
                for post in self._iter_subreddit(sub, cutoff):
                    rec = self._post_to_record(post)
                    if rec and rec["id"] not in seen:
                        seen.add(rec["id"])
                        results.append(rec)
                        for comment_rec in self._iter_comments(post, cutoff, seen):
                            results.append(comment_rec)
                            seen.add(comment_rec["id"])
                self._log_quota()
            except PRAWException as exc:
                logger.error("r/%s — PRAW error: %s", sub_name, exc)

        # 2. Keyword search across all of Reddit
        # search() paginates with separate API calls between pages, so we add
        # our floor delay between *pages* (not individual posts within a page).
        for term in config.REDDIT_SEARCH_TERMS:
            logger.info("Reddit-wide search: '%s'", term)
            try:
                page_count = 0
                for post in reddit.subreddit("all").search(
                    term, sort="new", time_filter="all", limit=None
                ):
                    if datetime.fromtimestamp(post.created_utc, tz=timezone.utc) < cutoff:
                        break
                    rec = self._post_to_record(post)
                    if rec and rec["id"] not in seen:
                        seen.add(rec["id"])
                        results.append(rec)
                    page_count += 1
                    # PRAW fetches 100 posts per page; apply our floor delay
                    # at page boundaries rather than per-post.
                    if page_count % 100 == 0:
                        self._rate_limit()
                        self._log_quota()
            except PRAWException as exc:
                logger.error("Search '%s' — PRAW error: %s", term, exc)

        logger.info("Reddit: collected %d records", len(results))
        return results

    # ── helpers ───────────────────────────────────────────────────────────────

    def _iter_subreddit(
        self, sub: praw.models.Subreddit, cutoff: datetime
    ) -> Generator:
        # No manual delay here — PRAW's ListingGenerator paces itself using
        # X-Ratelimit-* response headers. Adding sleep here would double-count.
        for post in sub.new(limit=None):
            ts = datetime.fromtimestamp(post.created_utc, tz=timezone.utc)
            if ts < cutoff:
                break
            yield post

    def _iter_comments(
        self,
        post: praw.models.Submission,
        cutoff: datetime,
        seen: set[str],
    ) -> Generator:
        try:
            post.comments.replace_more(limit=0)
            for comment in post.comments.list():
                ts = datetime.fromtimestamp(comment.created_utc, tz=timezone.utc)
                if ts < cutoff:
                    continue
                rec = self._comment_to_record(comment, post.subreddit.display_name)
                if rec and rec["id"] not in seen:
                    yield rec
        except PRAWException as exc:
            logger.warning("Comments for %s — error: %s", post.id, exc)

    def _post_to_record(self, post: praw.models.Submission) -> dict | None:
        url = f"https://www.reddit.com{post.permalink}"
        if not self._allowed(url):
            return None
        ts = datetime.fromtimestamp(post.created_utc, tz=timezone.utc).isoformat()
        text = (post.selftext or post.title).strip()
        if not text:
            return None
        return {
            "id": self.make_id("reddit", url, ts),
            "platform": "reddit",
            "url": url,
            "author": str(post.author) if post.author else "[deleted]",
            "published_at": ts,
            "raw_text": f"{post.title}\n\n{post.selftext}".strip(),
            "translated_text": None,
            "detected_language": None,
            "companies": [],
            "themes": [],
            "sentiment": {},
            "engagement": {
                "upvotes_likes": post.score,
                "comments": post.num_comments,
                "shares_retweets": 0,
            },
            "flags": {"legal": False, "hate_speech": False},
        }

    def _comment_to_record(
        self, comment: praw.models.Comment, subreddit: str
    ) -> dict | None:
        url = f"https://www.reddit.com{comment.permalink}"
        if not self._allowed(url):
            return None
        ts = datetime.fromtimestamp(comment.created_utc, tz=timezone.utc).isoformat()
        text = (comment.body or "").strip()
        if not text or text == "[deleted]" or text == "[removed]":
            return None
        return {
            "id": self.make_id("reddit", url, ts),
            "platform": "reddit",
            "url": url,
            "author": str(comment.author) if comment.author else "[deleted]",
            "published_at": ts,
            "raw_text": text,
            "translated_text": None,
            "detected_language": None,
            "companies": [],
            "themes": [],
            "sentiment": {},
            "engagement": {
                "upvotes_likes": comment.score,
                "comments": 0,
                "shares_retweets": 0,
            },
            "flags": {"legal": False, "hate_speech": False},
        }
