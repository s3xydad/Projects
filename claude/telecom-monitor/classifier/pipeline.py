"""Full NLP classification pipeline.

Layers applied to every post record:
  1. Language detection (langdetect)
  2. Translation to English for non-English posts (deep-translator / Google)
  3. Company tagging (keyword match)
  4. Theme classification (keyword match, multi-label)
  5. Sentiment analysis (VADER — fast, works well for social text)
  6. Content flags (regex / keyword)

Install:
  pip install langdetect deep-translator vaderSentiment
"""

import logging
import re
from typing import Optional

from langdetect import detect, LangDetectException
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from deep_translator import GoogleTranslator, exceptions as dt_exc

from config import COMPANIES, THEME_KEYWORDS, LEGAL_KEYWORDS, HATE_SPEECH_WORDS

logger = logging.getLogger(__name__)

_vader = SentimentIntensityAnalyzer()

# Pre-compiled patterns for speed
_company_patterns: dict[str, re.Pattern] = {
    key: re.compile(
        "|".join(re.escape(alias) for alias in aliases),
        flags=re.IGNORECASE,
    )
    for key, aliases in COMPANIES.items()
}

_theme_patterns: dict[str, re.Pattern] = {
    theme: re.compile(
        "|".join(re.escape(kw) for kw in kws),
        flags=re.IGNORECASE,
    )
    for theme, kws in THEME_KEYWORDS.items()
}

_legal_pattern = re.compile(
    "|".join(re.escape(kw) for kw in LEGAL_KEYWORDS),
    flags=re.IGNORECASE,
)

_hate_pattern = re.compile(
    "|".join(re.escape(w) for w in HATE_SPEECH_WORDS),
    flags=re.IGNORECASE,
) if HATE_SPEECH_WORDS else None


# ── Public interface ──────────────────────────────────────────────────────────

def classify_post(record: dict) -> dict:
    """Mutate-and-return: fills in all classification fields on a raw record."""
    text = record.get("raw_text", "")

    # 1. Language detection
    lang = _detect_language(text)
    record["detected_language"] = lang

    # 2. Translation
    translated: Optional[str] = None
    if lang and lang != "en":
        translated = _translate(text, lang)
    record["translated_text"] = translated

    analysis_text = translated or text

    # 3. Company tagging
    companies = _tag_companies(analysis_text)
    if not companies:
        companies = _tag_companies(text)  # fallback to original
    record["companies"] = companies

    # 4. Theme classification
    themes = _classify_themes(analysis_text)
    record["themes"] = themes if themes else ["OTHER"]

    # 5. Sentiment
    record["sentiment"] = _analyze_sentiment(analysis_text)

    # 6. Content flags
    record["flags"] = _detect_flags(analysis_text)

    # Strip internal helper keys
    record.pop("_fb_post_id", None)

    return record


def classify_batch(records: list[dict]) -> list[dict]:
    out = []
    for i, rec in enumerate(records):
        try:
            out.append(classify_post(rec))
        except Exception as exc:
            logger.warning("classify_post failed on record %d: %s", i, exc)
            rec["_classify_error"] = str(exc)
            out.append(rec)
    return out


# ── Internal helpers ──────────────────────────────────────────────────────────

def _detect_language(text: str) -> Optional[str]:
    try:
        return detect(text[:1000])  # langdetect is fast but limit input length
    except LangDetectException:
        return None


def _translate(text: str, src_lang: str) -> Optional[str]:
    try:
        translator = GoogleTranslator(source=src_lang, target="en")
        # Google Translate has a 5000-char limit per call
        chunks = [text[i : i + 4500] for i in range(0, len(text), 4500)]
        return " ".join(translator.translate(chunk) for chunk in chunks)
    except (dt_exc.TranslationNotFound, dt_exc.LanguageNotSupportedException) as exc:
        logger.debug("Translation skipped (%s): %s", src_lang, exc)
        return None
    except Exception as exc:
        logger.warning("Translation error for lang '%s': %s", src_lang, exc)
        return None


def _tag_companies(text: str) -> list[str]:
    return [key for key, pat in _company_patterns.items() if pat.search(text)]


def _classify_themes(text: str) -> list[str]:
    return [theme for theme, pat in _theme_patterns.items() if pat.search(text)]


def _analyze_sentiment(text: str) -> dict:
    scores = _vader.polarity_scores(text)
    compound = scores["compound"]
    if compound >= 0.05:
        label, confidence = "POSITIVE", _scale_confidence(compound)
    elif compound <= -0.05:
        label, confidence = "NEGATIVE", _scale_confidence(abs(compound))
    else:
        label, confidence = "NEUTRAL", 1.0 - abs(compound) * 2
    return {"label": label, "score": round(confidence, 3)}


def _scale_confidence(compound_abs: float) -> float:
    """Map VADER compound magnitude [0.05, 1.0] → confidence [0.5, 1.0]."""
    return round(0.5 + 0.5 * min(compound_abs / 1.0, 1.0), 3)


def _detect_flags(text: str) -> dict:
    legal = bool(_legal_pattern.search(text))
    hate = bool(_hate_pattern and _hate_pattern.search(text))
    return {"legal": legal, "hate_speech": hate}
