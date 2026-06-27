"""Generate realistic synthetic data for dashboard demo mode.

Usage:
  python demo_data.py                # writes ~3000 records to telecom_monitor.db
  python demo_data.py --count 5000   # custom record count
"""

import json
import random
import hashlib
import argparse
from datetime import datetime, timezone, timedelta

from storage.db import Database

COMPANIES   = ["ATT", "TMOBILE", "VERIZON"]
PLATFORMS   = ["reddit", "twitter", "facebook"]
THEMES      = ["CUSTOMER_SERVICE", "PRICING_BILLING", "NETWORK_COVERAGE",
               "CONTRACT_CANCELLATION", "OTHER"]
SENTIMENTS  = ["POSITIVE", "NEUTRAL", "NEGATIVE"]
LANGUAGES   = ["en"] * 80 + ["es"] * 8 + ["fr"] * 4 + ["de"] * 3 + ["pt"] * 3 + ["zh-cn"] * 2

# Weighted sentiment distributions per company (POSITIVE%, NEUTRAL%, NEGATIVE%)
SENTIMENT_WEIGHTS = {
    "ATT":     [0.22, 0.28, 0.50],
    "TMOBILE": [0.38, 0.30, 0.32],
    "VERIZON": [0.30, 0.32, 0.38],
}

SAMPLE_TEXTS = {
    "CUSTOMER_SERVICE": [
        "Spent 2 hours on hold with {} support and never got a resolution. Terrible.",
        "The {} rep was so helpful and solved my issue in minutes. Really impressed.",
        "{} chat support took forever but finally fixed my account issue.",
        "Escalated to a supervisor at {} and they credited my account. Happy now.",
        "{} customer service is the worst I've ever dealt with. Will be switching.",
    ],
    "PRICING_BILLING": [
        "My {} bill jumped $20 this month with zero explanation. Hidden fees again.",
        "{} gave me a great promotional rate but it expired after 3 months.",
        "Autopay discount with {} saved me $10/month — actually worth it.",
        "{} charged me an activation fee they promised to waive. Disputing now.",
        "Switched to {} and my monthly bill went from $80 to $55. Same coverage.",
    ],
    "NETWORK_COVERAGE": [
        "{} 5G in my area is blazing fast — getting 800 Mbps consistently.",
        "Dead zones everywhere in rural areas on {}. Dropped calls daily.",
        "{} coverage map is a lie. Zero signal at my house according to them.",
        "Just switched to {} and the signal improvement is night and day.",
        "{} network was down for 3 hours yesterday. Major outage in my city.",
    ],
    "CONTRACT_CANCELLATION": [
        "{} charged me an ETF even though I was out of contract. Had to dispute.",
        "Porting my number away from {} took 5 days. Nightmare experience.",
        "Finally cancelled {}. The unlocking process was painless thankfully.",
        "{} locked my phone even though I'd paid it off. Had to threaten legal.",
        "Switching from {} — they made cancellation so easy I was shocked.",
    ],
    "OTHER": [
        "{} new device lineup looks really impressive for this year.",
        "Does anyone know if {} supports WiFi calling internationally?",
        "{} just announced a partnership with a satellite provider. Interesting.",
        "Getting a new phone through {} upgrade program — easy process.",
        "{} store employees were very knowledgeable about the new plans.",
    ],
}

LEGAL_TEXTS = [
    "{} just got hit with a class action lawsuit over hidden fees.",
    "Filing an FCC complaint against {} today. This is unacceptable.",
    "My attorney sent a letter to {} regarding the fraudulent charge.",
    "Class action against {} — join at [link]. They owe us money.",
]

HATE_TEXTS = [
    "{} is complete b****. I hate this company so much.",
    "F*** {} and their terrible service. Never again.",
]


def _make_id(platform, url, ts):
    raw = f"{platform}:{url}:{ts}"
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def generate_records(count: int) -> list[dict]:
    now = datetime.now(timezone.utc)
    records = []

    for i in range(count):
        company    = random.choice(COMPANIES)
        platform   = random.choices(PLATFORMS, weights=[0.5, 0.35, 0.15])[0]
        theme      = random.choices(THEMES, weights=[0.3, 0.25, 0.25, 0.1, 0.1])[0]
        lang       = random.choice(LANGUAGES)
        days_ago   = random.randint(0, 730)
        ts         = (now - timedelta(days=days_ago, hours=random.randint(0, 23))).isoformat()
        url        = f"https://{platform}.com/post/{i:07d}"
        post_id    = _make_id(platform, url, ts)

        # Sentiment
        weights    = SENTIMENT_WEIGHTS[company]
        sent_label = random.choices(SENTIMENTS, weights=weights)[0]
        sent_score = round(random.uniform(0.55, 0.98), 3)

        # Text
        templates  = SAMPLE_TEXTS[theme]
        raw_text   = random.choice(templates).format(company.replace("ATT", "AT&T").replace("TMOBILE", "T-Mobile"))

        # Legal/hate flags (~2% / ~1%)
        legal = False
        hate  = False
        roll  = random.random()
        if roll < 0.01:
            raw_text = random.choice(HATE_TEXTS).format(company)
            hate = True
        elif roll < 0.03:
            raw_text = random.choice(LEGAL_TEXTS).format(company)
            legal = True

        # Multi-company posts (~5%)
        companies = [company]
        if random.random() < 0.05:
            other = random.choice([c for c in COMPANIES if c != company])
            companies.append(other)

        # Multi-theme posts (~15%)
        themes = [theme]
        if random.random() < 0.15:
            extra = random.choice([t for t in THEMES if t != theme])
            themes.append(extra)

        records.append({
            "id":                post_id,
            "platform":          platform,
            "url":               url,
            "author":            f"user_{random.randint(1000, 99999)}",
            "published_at":      ts,
            "raw_text":          raw_text,
            "translated_text":   None if lang == "en" else f"[EN] {raw_text}",
            "detected_language": lang,
            "companies":         json.dumps(companies),
            "themes":            json.dumps(themes),
            "sentiment_label":   sent_label,
            "sentiment_score":   sent_score,
            "engagement_likes":  random.randint(0, 500),
            "engagement_comments": random.randint(0, 100),
            "engagement_shares": random.randint(0, 50),
            "flag_legal":        int(legal),
            "flag_hate_speech":  int(hate),
            "classify_error":    None,
        })

    return records


def seed_db(count: int = 3000) -> None:
    db = Database()
    records = generate_records(count)
    import sqlite3
    with sqlite3.connect(db.path) as conn:
        conn.executemany(
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
            records,
        )
        conn.commit()
    print(f"Demo data: inserted up to {count} records into {db.path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=3000)
    args = parser.parse_args()
    seed_db(args.count)
