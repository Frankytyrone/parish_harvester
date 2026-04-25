"""
config.py — Central configuration for the Parish Bulletin Harvester.
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

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
PAGE_LOAD_TIMEOUT_MS: int = 30_000   # 30 s per page request
TOTAL_TIMEOUT_S: int = 60            # 60 s total per parish
CONCURRENCY: int = 10                # parallel asyncio tasks

# ---------------------------------------------------------------------------
# PDF validation
# ---------------------------------------------------------------------------
MIN_PDF_BYTES: int = 20_000          # 20 KB minimum PDF size

# ---------------------------------------------------------------------------
# Bulletin size / page limits
# ---------------------------------------------------------------------------
MAX_BULLETIN_PAGES: int = 4          # reject PDFs with more than 4 pages
MAX_BULLETIN_SIZE_MB: int = 5        # reject files larger than 5 MB (pre-download)


# ---------------------------------------------------------------------------
# Target date helpers
# ---------------------------------------------------------------------------

def target_sunday(from_date: date | None = None) -> date:
    """Return the bulletin target Sunday based on which day of the week it is.

    Always returns the most recent past Sunday (or today if today is Sunday).
    Parishes do not upload next week's bulletin until Wednesday/Thursday at
    the earliest, so jumping ahead to next Sunday on Friday/Saturday would
    produce URLs that do not yet exist.

    * Sunday (weekday 6)       → today (current bulletin is already live)
    * Monday–Saturday (0–5)    → last Sunday (bulletins for next Sunday are
                                  not uploaded until at least Wednesday/Thursday
                                  of the following week, so never jump forward)
    """
    d = from_date or date.today()
    wd = d.weekday()  # Monday=0 … Sunday=6
    if wd == 6:
        # Today is Sunday — use today
        return d
    # Monday through Saturday — use last Sunday
    return d - timedelta(days=wd + 1)


# Backwards compatibility alias
next_sunday = target_sunday


def week_range(target: date) -> tuple[date, date]:
    """Return the Monday–Sunday range that contains *target*."""
    monday = target - timedelta(days=target.weekday())
    sunday = monday + timedelta(days=6)
    return monday, sunday
