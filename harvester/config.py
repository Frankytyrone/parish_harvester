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
# Target date helpers
# ---------------------------------------------------------------------------

def target_sunday(from_date: date | None = None) -> date:
    """Return the bulletin target Sunday based on which day of the week it is.

    The logic reflects when parish websites actually publish their bulletins:

    * Sunday (weekday 6)      → today (current bulletin is already live)
    * Monday–Thursday (0–3)   → last Sunday (bulletin has been live all week)
    * Friday–Saturday (4–5)   → next Sunday (parishes upload a day or two early)
    """
    d = from_date or date.today()
    wd = d.weekday()  # Monday=0 … Sunday=6
    if wd == 6:
        # Today is Sunday — use today
        return d
    if wd <= 3:
        # Monday through Thursday — use last Sunday
        return d - timedelta(days=wd + 1)
    # Friday or Saturday — use next Sunday
    return d + timedelta(days=6 - wd)


# Backwards compatibility alias
next_sunday = target_sunday


def week_range(target: date) -> tuple[date, date]:
    """Return the Monday–Sunday range that contains *target*."""
    monday = target - timedelta(days=target.weekday())
    sunday = monday + timedelta(days=6)
    return monday, sunday
