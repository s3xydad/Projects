"""Main pipeline runner.

Usage:
  python pipeline.py                          # run all scrapers
  python pipeline.py --platform reddit        # Reddit only
  python pipeline.py --platform twitter       # Twitter only
  python pipeline.py --platform facebook      # Facebook only
  python pipeline.py --demo                   # seed with synthetic data, skip scraping
  python pipeline.py --demo --count 5000      # custom demo record count
"""

import argparse
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

# Must import config first so _DATA_DIR is created before we open the log.
import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(config._DATA_DIR / "pipeline.log"),
    ],
)
logger = logging.getLogger("pipeline")


def run(platforms: list[str], lookback_days: int) -> dict:
    from scraper import RedditScraper, TwitterScraper, FacebookScraper
    from classifier.pipeline import classify_batch
    from storage.db import Database

    db = Database()
    started_at = datetime.now(timezone.utc).isoformat()
    all_records: list[dict] = []

    scrapers = {
        "reddit":   RedditScraper,
        "twitter":  TwitterScraper,
        "facebook": FacebookScraper,
    }

    for platform in platforms:
        cls = scrapers.get(platform)
        if cls is None:
            logger.warning("Unknown platform: %s", platform)
            continue
        logger.info("=== Scraping %s ===", platform.upper())
        try:
            scraper = cls()
            records = scraper.scrape(lookback_days=lookback_days)
            logger.info("%s: %d raw records", platform, len(records))
            all_records.extend(records)
        except Exception as exc:
            logger.error("%s scraper failed: %s", platform, exc, exc_info=True)

    logger.info("=== Classifying %d records ===", len(all_records))
    classified = classify_batch(all_records)

    logger.info("=== Storing to DB ===")
    inserted, skipped, errored = db.insert_many(classified)

    finished_at = datetime.now(timezone.utc).isoformat()
    legal_count = sum(1 for r in classified if r.get("flags", {}).get("legal"))
    hate_count  = sum(1 for r in classified if r.get("flags", {}).get("hate_speech"))

    db.log_run(
        started_at=started_at,
        finished_at=finished_at,
        total=len(classified),
        skipped=skipped,
        errored=errored,
        legal=legal_count,
        hate=hate_count,
    )

    summary = {
        "started_at":  started_at,
        "finished_at": finished_at,
        "total":       len(classified),
        "inserted":    inserted,
        "skipped":     skipped,
        "errored":     errored,
        "flag_legal":  legal_count,
        "flag_hate":   hate_count,
    }

    logger.info(
        "Run complete — total=%d inserted=%d skipped=%d errored=%d "
        "legal_flags=%d hate_flags=%d",
        summary["total"], summary["inserted"], summary["skipped"],
        summary["errored"], summary["flag_legal"], summary["flag_hate"],
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Telecom Social Monitor pipeline")
    parser.add_argument(
        "--platform", choices=["reddit", "twitter", "facebook"],
        action="append", dest="platforms",
        help="Platform(s) to scrape. Repeat to include multiple. Default: all.",
    )
    parser.add_argument(
        "--lookback-days", type=int, default=730,
        help="How many days back to collect posts (default: 730 / 2 years).",
    )
    parser.add_argument(
        "--demo", action="store_true",
        help="Skip live scraping and seed the DB with synthetic demo data.",
    )
    parser.add_argument(
        "--count", type=int, default=3000,
        help="Number of synthetic records to generate in demo mode.",
    )
    args = parser.parse_args()

    if args.demo:
        from demo_data import seed_db
        seed_db(args.count)
        return

    platforms = args.platforms or ["reddit", "twitter", "facebook"]
    run(platforms, args.lookback_days)


if __name__ == "__main__":
    main()
