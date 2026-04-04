"""
config.py — Central configuration for the Parish Bulletin Harvester.
"""
from __future__ import annotations

import os
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
# GitHub Models API
# ---------------------------------------------------------------------------
GITHUB_TOKEN: str = os.getenv("GITHUB_TOKEN", "")
OPENAI_MODEL: str = "gpt-4o"

# ---------------------------------------------------------------------------
# Timeouts & concurrency
# ---------------------------------------------------------------------------
PAGE_LOAD_TIMEOUT_MS: int = 30_000   # 30 s
TOTAL_TIMEOUT_S: int = 60            # 60 s per parish
CONCURRENCY: int = 5                 # parallel asyncio tasks

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
    """Return True if *bulletin_date* falls within the same Mon–Sun week as *target*."""
    monday, sunday = week_range(target)
    return monday <= bulletin_date <= sunday
