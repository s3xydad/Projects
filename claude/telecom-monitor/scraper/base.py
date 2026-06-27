"""Shared base class for all scrapers."""

import time
import random
import logging
import hashlib
from abc import ABC, abstractmethod
from urllib.robotparser import RobotFileParser

logger = logging.getLogger(__name__)


class BaseScraper(ABC):
    robots_url: str = ""

    def __init__(self, min_delay: float = 2.0, max_retries: int = 3):
        self.min_delay = min_delay
        self.max_retries = max_retries
        self._last_request: float = 0.0
        self._robots: RobotFileParser | None = None

    # ── robots.txt ────────────────────────────────────────────────────────────

    def _load_robots(self) -> None:
        if self._robots is not None:
            return
        self._robots = RobotFileParser()
        self._robots.set_url(self.robots_url)
        try:
            self._robots.read()
        except Exception as exc:
            logger.warning("Could not fetch robots.txt at %s: %s", self.robots_url, exc)

    def _allowed(self, url: str) -> bool:
        if not self.robots_url:
            return True
        self._load_robots()
        return self._robots.can_fetch("*", url)

    # ── rate limiting ─────────────────────────────────────────────────────────

    def _rate_limit(self) -> None:
        """Enforce self.min_delay between calls.

        Use this at page/batch boundaries, not per-item inside SDK generators
        that already read X-Ratelimit-* headers (e.g. PRAW ListingGenerators).
        Adding sleep inside those generators causes double-throttling.
        """
        elapsed = time.monotonic() - self._last_request
        wait = self.min_delay - elapsed
        if wait > 0:
            time.sleep(wait + random.uniform(0, 0.15))
        self._last_request = time.monotonic()

    def _backoff(self, attempt: int) -> None:
        """Exponential backoff: 2^attempt seconds, up to 60s."""
        delay = min(2 ** attempt, 60) + random.uniform(0, 1)
        logger.info("Backoff: waiting %.1f s (attempt %d)", delay, attempt)
        time.sleep(delay)

    # ── record ID ────────────────────────────────────────────────────────────

    @staticmethod
    def make_id(platform: str, url: str, published_at: str) -> str:
        raw = f"{platform}:{url}:{published_at}"
        return hashlib.sha256(raw.encode()).hexdigest()[:24]

    # ── interface ─────────────────────────────────────────────────────────────

    @abstractmethod
    def scrape(self, **kwargs) -> list[dict]:
        """Return a list of raw post dicts conforming to the data schema."""
