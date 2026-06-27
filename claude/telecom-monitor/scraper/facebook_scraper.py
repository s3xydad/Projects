"""Facebook scraper using the Graph API v18+.

Requirements:
  pip install requests
  Access notes:
    - You need a Facebook App with "pages_read_engagement" and
      "pages_read_user_content" permissions approved.
    - You also need a Page Access Token for each official carrier page.
    - The Graph API does NOT return arbitrary public posts — only posts from
      Pages that have authorized your app, or using a System User token with
      granted permissions.
    - For public group posts, the "Groups API" requires additional approval.
    - See: https://developers.facebook.com/docs/graph-api/
  Set FACEBOOK_ACCESS_TOKEN in .env.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
import requests

import config
from scraper.base import BaseScraper

logger = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.facebook.com/v18.0"


class FacebookScraper(BaseScraper):
    robots_url = "https://www.facebook.com/robots.txt"

    def __init__(self):
        super().__init__(min_delay=config.REQUEST_DELAY, max_retries=config.MAX_RETRIES)

    def scrape(self, lookback_days: int = config.LOOKBACK_DAYS, **_) -> list[dict]:
        if not config.FACEBOOK_ACCESS_TOKEN:
            logger.warning("No FACEBOOK_ACCESS_TOKEN — skipping Facebook scraping.")
            return []

        cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
        cutoff_unix = int(cutoff.timestamp())
        results: list[dict] = []
        seen: set[str] = set()

        for company_key, page_id in config.FACEBOOK_PAGE_IDS.items():
            logger.info("Facebook: scraping page '%s' (%s)", page_id, company_key)
            for post_rec in self._iter_page_posts(page_id, cutoff_unix):
                if post_rec["id"] not in seen:
                    seen.add(post_rec["id"])
                    results.append(post_rec)
                # Fetch post comments
                for comment_rec in self._iter_post_comments(
                    post_rec["_fb_post_id"], cutoff_unix, seen
                ):
                    results.append(comment_rec)
                    seen.add(comment_rec["id"])

        logger.info("Facebook: collected %d records", len(results))
        return results

    # ── Graph API helpers ─────────────────────────────────────────────────────

    def _get(self, endpoint: str, params: dict) -> Optional[dict]:
        params["access_token"] = config.FACEBOOK_ACCESS_TOKEN
        url = f"{GRAPH_BASE}/{endpoint}"
        if not self._allowed(url):
            logger.warning("robots.txt disallows %s", url)
            return None

        for attempt in range(self.max_retries):
            self._rate_limit()
            try:
                resp = requests.get(url, params=params, timeout=30)
            except requests.RequestException as exc:
                logger.error("Request error (%s): %s", url, exc)
                self._backoff(attempt)
                continue

            if resp.status_code == 403:
                logger.error("HTTP 403 on %s — stopping Facebook scrape.", url)
                return None
            if resp.status_code == 429:
                logger.warning("HTTP 429 — rate limited.")
                self._backoff(attempt)
                continue
            if not resp.ok:
                logger.warning("HTTP %d on %s", resp.status_code, url)
                self._backoff(attempt)
                continue

            data = resp.json()
            if "error" in data:
                logger.error("Graph API error: %s", data["error"])
                return None
            return data

        return None

    def _iter_page_posts(self, page_id: str, cutoff_unix: int):
        params = {
            "fields": "id,message,created_time,likes.summary(true),comments.summary(true),shares",
            "since": cutoff_unix,
            "limit": 100,
        }
        endpoint = f"{page_id}/posts"
        while endpoint:
            data = self._get(endpoint, params)
            if not data:
                break
            for post in data.get("data", []):
                rec = self._fb_post_to_record(post)
                if rec:
                    yield rec
            # Follow pagination cursors
            next_url = data.get("paging", {}).get("next")
            if next_url:
                # Graph API returns full URLs for next page — extract endpoint
                endpoint = next_url.replace(f"{GRAPH_BASE}/", "")
                params = {}  # params are embedded in the next URL
            else:
                break

    def _iter_post_comments(self, post_id: str, cutoff_unix: int, seen: set):
        params = {
            "fields": "id,message,created_time,like_count,from",
            "since": cutoff_unix,
            "limit": 100,
        }
        endpoint = f"{post_id}/comments"
        while endpoint:
            data = self._get(endpoint, params)
            if not data:
                break
            for comment in data.get("data", []):
                rec = self._fb_comment_to_record(comment)
                if rec and rec["id"] not in seen:
                    yield rec
            next_url = data.get("paging", {}).get("next")
            if next_url:
                endpoint = next_url.replace(f"{GRAPH_BASE}/", "")
                params = {}
            else:
                break

    def _fb_post_to_record(self, post: dict) -> Optional[dict]:
        text = (post.get("message") or "").strip()
        if not text:
            return None
        post_id = post["id"]
        url = f"https://www.facebook.com/{post_id.replace('_', '/posts/')}"
        ts = post.get("created_time", "")
        likes = post.get("likes", {}).get("summary", {}).get("total_count", 0)
        comments = post.get("comments", {}).get("summary", {}).get("total_count", 0)
        shares = post.get("shares", {}).get("count", 0)
        rec = {
            "id": self.make_id("facebook", url, ts),
            "_fb_post_id": post_id,
            "platform": "facebook",
            "url": url,
            "author": "[page_post]",
            "published_at": ts,
            "raw_text": text,
            "translated_text": None,
            "detected_language": None,
            "companies": [],
            "themes": [],
            "sentiment": {},
            "engagement": {
                "upvotes_likes": likes,
                "comments": comments,
                "shares_retweets": shares,
            },
            "flags": {"legal": False, "hate_speech": False},
        }
        return rec

    def _fb_comment_to_record(self, comment: dict) -> Optional[dict]:
        text = (comment.get("message") or "").strip()
        if not text:
            return None
        comment_id = comment["id"]
        url = f"https://www.facebook.com/{comment_id}"
        ts = comment.get("created_time", "")
        author = comment.get("from", {}).get("name", "[unknown]")
        return {
            "id": self.make_id("facebook", url, ts),
            "_fb_post_id": comment_id,
            "platform": "facebook",
            "url": url,
            "author": author,
            "published_at": ts,
            "raw_text": text,
            "translated_text": None,
            "detected_language": None,
            "companies": [],
            "themes": [],
            "sentiment": {},
            "engagement": {
                "upvotes_likes": comment.get("like_count", 0),
                "comments": 0,
                "shares_retweets": 0,
            },
            "flags": {"legal": False, "hate_speech": False},
        }
