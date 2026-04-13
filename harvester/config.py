"""
config.py — Central configuration for the Parish Bulletin Harvester.
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
PARISHES_DIR = BASE_DIR / "parishes"
BULLETINS_DIR = BASE_DIR / "Bulletins"
RAW_DIR = BULLETINS_DIR / "raw"
CURRENT_DIR = BULLETINS_DIR / "current"
REPORT_JSON = BULLETINS_DIR / "report.json"
REPORT_TXT = BULLETINS_DIR / "report.txt"

# ---------------------------------------------------------------------------
# Timeouts & concurrency
# ---------------------------------------------------------------------------
PAGE_LOAD_TIMEOUT_MS: int = 45_000   # 45 s
TOTAL_TIMEOUT_S: int = 120           # 120 s per parish
CONCURRENCY: int = 8                 # parallel asyncio tasks

# ---------------------------------------------------------------------------
# Bulletin keyword heuristics
# ---------------------------------------------------------------------------
BULLETIN_KEYWORDS: tuple[str, ...] = (
    "bulletin",
    "newsletter",
    "news",
    "parish",
    "weekly",
    "leaflet",
)

JUNK_KEYWORDS: tuple[str, ...] = (
    "safeguarding",
    "gdpr",
    "privacy",
    "policy",
    "form",
    "baptism",
    "marriage",
    "roster",
    "schedule",
    "facebook",
    "twitter",
    "youtube",
    "mailto",
)

SUB_PAGE_KEYWORDS: tuple[str, ...] = (
    "read more",
    "click here",
    "download",
    "view",
    "open",
    "current newsletter",
    "latest newsletter",
    "this week",
    "view bulletin",
    "download bulletin",
    "more info",
    "full newsletter",
    "read newsletter",
    "view newsletter",
    "parish bulletin",
)

# Keywords used to find the bulletin image/link on Wix and similar sites.
# These are matched against both anchor text and <img> alt attributes.
BULLETIN_IMAGE_KEYWORDS: tuple[str, ...] = (
    "bulletin",
    "mass times",
    "parish bulletin",
    "newsletter",
    "weekly bulletin",
    "parish news",
)

# CSS selectors tried (in order) when scraping text from an HTML bulletin page.
# Wix-specific selectors are listed first, then generic fallbacks.
WIX_SELECTORS: tuple[str, ...] = (
    "[data-hook='post-description']",
    "[data-hook='post-content']",
    "div[data-testid='site-root']",
    "div#site-content",
    "div.wix-rich-text",
    "article",
    "main",
    "div.content",
    "div#content",
)


# ---------------------------------------------------------------------------
# Target date helpers
# ---------------------------------------------------------------------------

def next_sunday(from_date: date | None = None) -> date:
    """Return the date of the next Sunday on or after *from_date*."""
    d = from_date or date.today()
    days_ahead = 6 - d.weekday()  # weekday(): Monday=0, Sunday=6
    if days_ahead < 0:
        days_ahead += 7
    return d + timedelta(days=days_ahead)


def week_range(target: date) -> tuple[date, date]:
    """Return the Monday–Sunday range that contains *target*."""
    monday = target - timedelta(days=target.weekday())
    sunday = monday + timedelta(days=6)
    return monday, sunday


def is_fresh(bulletin_date: date, target: date) -> bool:
    """Return True if *bulletin_date* is within 10 days before *target*.

    Parish bulletins are weekly.  Running mid-week means the most recent
    bulletin is from last Sunday, which falls outside the current Mon–Sun
    week.  Accepting anything within 10 days ensures we never mark a
    genuinely current bulletin as stale just because we ran before the new
    one was uploaded.
    """
    return 0 <= (target - bulletin_date).days <= 10
