"""Twitter/X scraper using Tweepy v2 (API v2 search endpoint).

Requirements:
  pip install tweepy
  Twitter API access notes:
    - Free tier: 500k tweets/month READ, limited search.
    - Basic tier (~$100/mo): 10M tweets/month, full recent-search (7 days).
    - Pro tier (~$5000/mo): full-archive search (all history).
  For 2-year lookback you need the Academic Research track or Pro tier.
  Set TWITTER_BEARER_TOKEN in .env.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

import tweepy
from tweepy.errors import TweepyException

import config
from scraper.base import BaseScraper

logger = logging.getLogger(__name__)

# Fields requested from the API
TWEET_FIELDS = [
    "created_at", "text", "author_id", "public_metrics",
    "lang", "entities",
]
EXPANSIONS = ["author_id"]
USER_FIELDS = ["username"]


class TwitterScraper(BaseScraper):
    robots_url = "https://twitter.com/robots.txt"

    def __init__(self):
        super().__init__(min_delay=config.REQUEST_DELAY, max_retries=config.MAX_RETRIES)
        self._client: Optional[tweepy.Client] = None

    def _get_client(self) -> tweepy.Client:
        if self._client is None:
            self._client = tweepy.Client(
                bearer_token=config.TWITTER_BEARER_TOKEN,
                consumer_key=config.TWITTER_API_KEY,
                consumer_secret=config.TWITTER_API_SECRET,
                access_token=config.TWITTER_ACCESS_TOKEN,
                access_token_secret=config.TWITTER_ACCESS_SECRET,
                wait_on_rate_limit=True,
            )
        return self._client

    def scrape(self, lookback_days: int = config.LOOKBACK_DAYS, **_) -> list[dict]:
        if not config.TWITTER_BEARER_TOKEN:
            logger.warning("No TWITTER_BEARER_TOKEN — skipping Twitter scraping.")
            return []

        client = self._get_client()
        # API v2 recent_search only covers the last 7 days on Basic tier.
        # For full 2-year history, use full_archive_search (Pro/Academic).
        start_time = datetime.now(timezone.utc) - timedelta(days=lookback_days)

        results: list[dict] = []
        seen: set[str] = set()

        for query in config.TWITTER_QUERIES:
            logger.info("Twitter search: %s", query)
            try:
                paginator = tweepy.Paginator(
                    client.search_all_tweets,  # requires Academic/Pro; swap to
                    # client.search_recent_tweets for Basic tier (7 days only)
                    query=f"{query} -is:retweet lang:*",
                    tweet_fields=TWEET_FIELDS,
                    expansions=EXPANSIONS,
                    user_fields=USER_FIELDS,
                    start_time=start_time,
                    max_results=100,
                )
                for page in paginator:
                    if not page.data:
                        continue
                    users = {u.id: u.username for u in (page.includes or {}).get("users", [])}
                    for tweet in page.data:
                        rec = self._tweet_to_record(tweet, users)
                        if rec and rec["id"] not in seen:
                            seen.add(rec["id"])
                            results.append(rec)
                    self._rate_limit()
            except tweepy.errors.Forbidden as exc:
                logger.error(
                    "Twitter 403 on query '%s' — check API tier permissions: %s",
                    query, exc,
                )
                break
            except tweepy.errors.TooManyRequests:
                logger.warning("Twitter rate limit hit — Tweepy will auto-wait.")
            except TweepyException as exc:
                logger.error("Tweepy error for query '%s': %s", query, exc)

        logger.info("Twitter: collected %d records", len(results))
        return results

    def _tweet_to_record(self, tweet: tweepy.Tweet, users: dict) -> dict | None:
        url = f"https://twitter.com/i/web/status/{tweet.id}"
        if not self._allowed(url):
            return None
        ts = tweet.created_at.isoformat() if tweet.created_at else ""
        metrics = tweet.public_metrics or {}
        return {
            "id": self.make_id("twitter", url, ts),
            "platform": "twitter",
            "url": url,
            "author": users.get(tweet.author_id, str(tweet.author_id)),
            "published_at": ts,
            "raw_text": tweet.text,
            "translated_text": None,
            "detected_language": tweet.lang,
            "companies": [],
            "themes": [],
            "sentiment": {},
            "engagement": {
                "upvotes_likes": metrics.get("like_count", 0),
                "comments": metrics.get("reply_count", 0),
                "shares_retweets": metrics.get("retweet_count", 0),
            },
            "flags": {"legal": False, "hate_speech": False},
        }
