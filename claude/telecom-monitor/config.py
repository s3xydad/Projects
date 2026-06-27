"""Central configuration for the Telecom Social Monitor pipeline."""

import os
from pathlib import Path
from dotenv import load_dotenv

_HERE = Path(__file__).parent
load_dotenv(_HERE / ".env")

# Runtime data lives outside the sandboxed source tree so Python can write it.
_DATA_DIR = Path(os.environ.get("APPDATA", Path.home())) / "TelecomMonitor"
_DATA_DIR.mkdir(parents=True, exist_ok=True)

# ── API credentials ───────────────────────────────────────────────────────────
REDDIT_CLIENT_ID     = os.getenv("REDDIT_CLIENT_ID", "")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET", "")
REDDIT_USER_AGENT    = os.getenv("REDDIT_USER_AGENT", "TelecomMonitor/1.0")

TWITTER_BEARER_TOKEN  = os.getenv("TWITTER_BEARER_TOKEN", "")
TWITTER_API_KEY       = os.getenv("TWITTER_API_KEY", "")
TWITTER_API_SECRET    = os.getenv("TWITTER_API_SECRET", "")
TWITTER_ACCESS_TOKEN  = os.getenv("TWITTER_ACCESS_TOKEN", "")
TWITTER_ACCESS_SECRET = os.getenv("TWITTER_ACCESS_SECRET", "")

FACEBOOK_ACCESS_TOKEN = os.getenv("FACEBOOK_ACCESS_TOKEN", "")

DB_PATH         = os.getenv("DB_PATH", str(_DATA_DIR / "telecom_monitor.db"))
LOOKBACK_DAYS   = int(os.getenv("LOOKBACK_DAYS", "730"))
REQUEST_DELAY   = float(os.getenv("REQUEST_DELAY_SECONDS", "2.0"))
MAX_RETRIES     = int(os.getenv("MAX_RETRIES", "3"))

# ── Company definitions ───────────────────────────────────────────────────────
COMPANIES = {
    "ATT": [
        "AT&T", "AT&T Wireless", "AT&T Mobile", "att wireless",
        "@ATT", "#ATT", "attcustomerservice",
    ],
    "TMOBILE": [
        "T-Mobile", "TMobile", "T Mobile", "Sprint",
        "@TMobile", "#TMobile", "tmobile",
    ],
    "VERIZON": [
        "Verizon", "Verizon Wireless", "VZW", "Big Red",
        "@Verizon", "#Verizon", "verizonwireless",
    ],
}

# ── Theme keyword dictionaries ────────────────────────────────────────────────
THEME_KEYWORDS = {
    "CUSTOMER_SERVICE": [
        "customer service", "support", "agent", "wait time", "hold",
        "call center", "chat support", "phone support", "resolution",
        "rep", "representative", "escalate", "supervisor",
        "helpdesk", "help desk", "ticket",
    ],
    "PRICING_BILLING": [
        "price", "pricing", "cost", "bill", "billing", "charge", "fee",
        "autopay", "discount", "promo", "promotion", "plan cost",
        "monthly cost", "expensive", "cheap", "hidden fee",
        "unexpected charge", "rate increase", "price hike",
    ],
    "NETWORK_COVERAGE": [
        "coverage", "signal", "dead zone", "5G", "LTE", "4G", "bars",
        "rural", "urban", "data speed", "download speed", "upload speed",
        "dropped call", "no signal", "weak signal", "outage",
        "network down", "tower", "hotspot",
    ],
    "CONTRACT_CANCELLATION": [
        "cancel", "cancellation", "ETF", "early termination",
        "termination fee", "contract", "locked in", "lock-in",
        "port number", "porting", "switch carrier", "switching",
        "unlock", "unlocked", "leave", "leaving",
    ],
}

LEGAL_KEYWORDS = [
    "lawsuit", "litigation", "class action", "attorney", "lawyer",
    "court", "CFPB", "FCC complaint", "legal threat", "sue", "sued",
    "settlement", "damages", "arbitration", "subpoena",
]

# Minimal profanity list — extend with a full list in production.
HATE_SPEECH_WORDS = [
    "f***", "s***", "b****", "a**hole",
    # Add slurs and hate-speech terms appropriate for your moderation policy.
]

# ── Reddit subreddits to monitor ──────────────────────────────────────────────
REDDIT_SUBREDDITS = [
    "tmobile", "ATT", "verizon", "NoContract",
    "mobilecarriers", "cordcutters", "wireless",
]

REDDIT_SEARCH_TERMS = [
    "AT&T", "T-Mobile", "Verizon",
    "att wireless", "tmobile", "verizon wireless",
]

# ── Twitter search queries ────────────────────────────────────────────────────
TWITTER_QUERIES = [
    "@ATT OR #ATT OR #attcustomerservice",
    "@TMobile OR #TMobile OR #tmobile",
    "@Verizon OR #Verizon OR #verizonwireless",
]

# ── Facebook page IDs for official carrier pages ──────────────────────────────
FACEBOOK_PAGE_IDS = {
    "ATT":     "att",
    "TMOBILE": "tmobile",
    "VERIZON": "verizon",
}

PLATFORMS = ["reddit", "twitter", "facebook"]
