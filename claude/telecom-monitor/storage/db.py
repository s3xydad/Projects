"""SQLite storage layer for collected and classified posts."""

import json
import logging
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

import config

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS posts (
    id                TEXT PRIMARY KEY,
    platform          TEXT NOT NULL,
    url               TEXT NOT NULL,
    author            TEXT,
    published_at      TEXT,
    raw_text          TEXT,
    translated_text   TEXT,
    detected_language TEXT,
    companies         TEXT,       -- JSON array
    themes            TEXT,       -- JSON array
    sentiment_label   TEXT,
    sentiment_score   REAL,
    engagement_likes  INTEGER DEFAULT 0,
    engagement_comments INTEGER DEFAULT 0,
    engagement_shares   INTEGER DEFAULT 0,
    flag_legal        INTEGER DEFAULT 0,
    flag_hate_speech  INTEGER DEFAULT 0,
    classify_error    TEXT
);

CREATE TABLE IF NOT EXISTS run_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at  TEXT,
    finished_at TEXT,
    total       INTEGER,
    skipped     INTEGER,
    errored     INTEGER,
    flag_legal  INTEGER,
    flag_hate   INTEGER
);

CREATE INDEX IF NOT EXISTS idx_platform        ON posts(platform);
CREATE INDEX IF NOT EXISTS idx_published_at    ON posts(published_at);
CREATE INDEX IF NOT EXISTS idx_sentiment_label ON posts(sentiment_label);
CREATE INDEX IF NOT EXISTS idx_lang            ON posts(detected_language);
"""


class Database:
    def __init__(self, path: str = config.DB_PATH):
        self.path = path
        self._init_db()

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ── Insertion ─────────────────────────────────────────────────────────────

    def insert_many(self, records: list[dict]) -> tuple[int, int, int]:
        """Returns (inserted, skipped_duplicates, errored)."""
        inserted = skipped = errored = 0
        with self._conn() as conn:
            for rec in records:
                try:
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO posts (
                            id, platform, url, author, published_at,
                            raw_text, translated_text, detected_language,
                            companies, themes,
                            sentiment_label, sentiment_score,
                            engagement_likes, engagement_comments, engagement_shares,
                            flag_legal, flag_hate_speech, classify_error
                        ) VALUES (
                            :id, :platform, :url, :author, :published_at,
                            :raw_text, :translated_text, :detected_language,
                            :companies, :themes,
                            :sentiment_label, :sentiment_score,
                            :engagement_likes, :engagement_comments, :engagement_shares,
                            :flag_legal, :flag_hate_speech, :classify_error
                        )
                        """,
                        self._flatten(rec),
                    )
                    if conn.execute("SELECT changes()").fetchone()[0]:
                        inserted += 1
                    else:
                        skipped += 1
                        logger.debug("Duplicate skipped: %s", rec.get("id"))
                except sqlite3.Error as exc:
                    logger.warning("DB insert error for %s: %s", rec.get("id"), exc)
                    errored += 1
        return inserted, skipped, errored

    def log_run(self, started_at: str, finished_at: str, total: int,
                skipped: int, errored: int, legal: int, hate: int) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO run_log
                    (started_at, finished_at, total, skipped, errored, flag_legal, flag_hate)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (started_at, finished_at, total, skipped, errored, legal, hate),
            )

    # ── Query helpers used by the dashboard ──────────────────────────────────

    def all_posts_df(self):
        """Return all posts as a pandas DataFrame."""
        import pandas as pd
        with self._conn() as conn:
            df = pd.read_sql_query("SELECT * FROM posts", conn)
        # Deserialize JSON columns
        df["companies"] = df["companies"].apply(
            lambda x: json.loads(x) if x else []
        )
        df["themes"] = df["themes"].apply(
            lambda x: json.loads(x) if x else []
        )
        return df

    def count_by_platform(self) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT platform, COUNT(*) as cnt FROM posts GROUP BY platform"
            ).fetchall()
        return [dict(r) for r in rows]

    def total_count(self) -> int:
        with self._conn() as conn:
            return conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0]

    def flagged_posts(self, flag: str = "legal") -> list[dict]:
        col = "flag_legal" if flag == "legal" else "flag_hate_speech"
        with self._conn() as conn:
            rows = conn.execute(
                f"SELECT * FROM posts WHERE {col} = 1 ORDER BY published_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    # ── Serialization ─────────────────────────────────────────────────────────

    @staticmethod
    def _flatten(rec: dict) -> dict:
        sentiment = rec.get("sentiment") or {}
        engagement = rec.get("engagement") or {}
        flags = rec.get("flags") or {}
        return {
            "id": rec.get("id", ""),
            "platform": rec.get("platform", ""),
            "url": rec.get("url", ""),
            "author": rec.get("author", ""),
            "published_at": rec.get("published_at", ""),
            "raw_text": rec.get("raw_text", ""),
            "translated_text": rec.get("translated_text"),
            "detected_language": rec.get("detected_language"),
            "companies": json.dumps(rec.get("companies", [])),
            "themes": json.dumps(rec.get("themes", [])),
            "sentiment_label": sentiment.get("label"),
            "sentiment_score": sentiment.get("score"),
            "engagement_likes": engagement.get("upvotes_likes", 0),
            "engagement_comments": engagement.get("comments", 0),
            "engagement_shares": engagement.get("shares_retweets", 0),
            "flag_legal": int(flags.get("legal", False)),
            "flag_hate_speech": int(flags.get("hate_speech", False)),
            "classify_error": rec.get("_classify_error"),
        }
