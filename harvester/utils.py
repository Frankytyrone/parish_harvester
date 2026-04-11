"""
utils.py — Shared helper utilities for the Parish Bulletin Harvester.
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlparse


# ---------------------------------------------------------------------------
# Parish name extraction
# ---------------------------------------------------------------------------

def parish_name_from_url(url: str) -> str:
    """
    Derive a sanitized, human-readable parish name from a URL.

    Examples:
        https://www.parishofaghyaran.com/news.html  →  parishofaghyaran
        https://www.derrydiocese.org/parishes/gortin →  derrydiocese_gortin
    """
    parsed = urlparse(url)
    hostname = parsed.netloc.lower()
    # strip leading www. / www2. etc.
    hostname = re.sub(r"^www\d*\.", "", hostname)
    # take the base domain without TLD
    parts = hostname.split(".")
    base = parts[0] if parts else hostname

    # Include the last path segment if it adds meaningful info
    path_parts = [p for p in parsed.path.strip("/").split("/") if p]
    if path_parts:
        last = path_parts[-1]
        # Strip file extension
        if "." in last:
            last = last.rsplit(".", 1)[0]
        # e.g. /parishes/gortin  →  append "gortin"
        # Skip generic page names that add no information
        _SKIP = {"news", "parishnews", "html", "htm", "php", "pdf", "aspx", "index"}
        if last and last.lower() not in _SKIP and not last.isdigit():
            base = f"{base}_{last}"

    # Remove any URL-encoded characters and reduce to safe chars
    base = re.sub(r"[^a-z0-9_-]", "_", base)
    base = re.sub(r"_+", "_", base).strip("_")
    return base


# ---------------------------------------------------------------------------
# Date-pattern helpers
# ---------------------------------------------------------------------------

_DDMMYY_RE = re.compile(r"(?<!\d)(\d{2})(\d{2})(\d{2})(?!\d)")      # 310825
_DDMMYYYY_RE = re.compile(r"(?<!\d)(\d{2})(\d{2})(\d{4})(?!\d)")    # 31082025
_ISO_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")                     # 2025-08-31
_ISO_NODASH_RE = re.compile(r"(?<!\d)(\d{4})(\d{2})(\d{2})(?!\d)")  # 20250831
_WP_YEAR_MONTH_RE = re.compile(r"/(\d{4})/(\d{2})/")                 # /2026/04/

# Pattern B: D-M-YY (1–2 digit day/month, 2-digit year, dash-separated)
# e.g. 5-4-26, 12-4-26, 15-3-26  (Limavady parish pattern)
_D_M_YY_RE = re.compile(r"(?<!\d)(\d{1,2})-(\d{1,2})-(\d{2})(?!\d)")

# Pattern E: [YYYY-M-D] bracketed ISO variant
# e.g. [2026-4-12], [2026-12-25]  (Greenlough parish pattern)
_BRACKETED_ISO_RE = re.compile(r"\[(\d{4})-(\d{1,2})-(\d{1,2})\]")

# Month name → month number mapping (English, full and abbreviated)
_MONTH_MAP: dict[str, int] = {
    "january": 1,  "jan": 1,
    "february": 2, "feb": 2,
    "march": 3,    "mar": 3,
    "april": 4,    "apr": 4,
    "may": 5,
    "june": 6,     "jun": 6,
    "july": 7,     "jul": 7,
    "august": 8,   "aug": 8,
    "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10,
    "november": 11, "nov": 11,
    "december": 12, "dec": 12,
}

# Matches date slugs like "5_april_2026", "15-february-2026", "2-february-2025"
_SLUG_DATE_RE = re.compile(
    r"(\d{1,2})[_\-]([a-z]+)[_\-](\d{4})",
    re.IGNORECASE,
)

_MONTH_NAMES: list[str] = [
    "", "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
]


def extract_date_from_string(text: str) -> date | None:
    """Try to parse a date from a filename/URL fragment. Returns None on failure."""
    # ISO with dashes
    m = _ISO_RE.search(text)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass

    # ISO without dashes (8 digits)
    m = _ISO_NODASH_RE.search(text)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass

    # DDMMYYYY (8 digits)
    m = _DDMMYYYY_RE.search(text)
    if m:
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            pass

    # DDMMYY (6 digits) — interpret YY as 2000+YY
    m = _DDMMYY_RE.search(text)
    if m:
        try:
            year = 2000 + int(m.group(3))
            return date(year, int(m.group(2)), int(m.group(1)))
        except ValueError:
            pass

    return None


def extract_date_from_slug(slug: str) -> date | None:
    """
    Extract a date from a URL slug like '5_april_2026' or '15-february-2026'.

    Returns None if no recognisable date pattern is found.
    """
    m = _SLUG_DATE_RE.search(slug)
    if not m:
        return None
    try:
        day = int(m.group(1))
        month = _MONTH_MAP.get(m.group(2).lower())
        year = int(m.group(3))
        if month:
            return date(year, month, day)
    except ValueError:
        pass
    return None


def rewrite_slug_url(url: str, target: date) -> str:
    """
    If a URL contains a date slug like '5_april_2026', rewrite it to use
    the *target* date.  Preserves the separator character (_ or -).

    Returns the original URL unchanged if no slug date is found.
    """
    m = _SLUG_DATE_RE.search(url)
    if not m:
        return url
    try:
        # Validate original date
        old_month = _MONTH_MAP.get(m.group(2).lower())
        if not old_month:
            return url
        date(int(m.group(3)), old_month, int(m.group(1)))  # raises ValueError if invalid
    except ValueError:
        return url

    # Determine the separator used in the original slug
    sep_pos = m.start() + len(m.group(1))
    sep = url[sep_pos] if sep_pos < len(url) else "_"

    new_slug = f"{target.day}{sep}{_MONTH_NAMES[target.month]}{sep}{target.year}"
    return url[: m.start()] + new_slug + url[m.end() :]


def rewrite_wp_url(url: str, target: date) -> str:
    """
    Rewrite a WordPress-style URL by updating both the ``YYYY/MM`` path
    component *and* any date slug in the filename (e.g. ``DD-Month-YYYY``).

    Examples::

        /wp-content/uploads/2026/03/29-March-2026.pdf
        → /wp-content/uploads/2026/04/5-April-2026.pdf   (target = 2026-04-05)

        /wp-content/uploads/2026/04/Newsletter-12-April-2026-1.pdf
        → /wp-content/uploads/2026/04/Newsletter-19-April-2026-1.pdf  (target = 2026-04-19)

    Returns the original URL unchanged if neither pattern is found.
    """
    # First update the date slug in the filename part
    new_url = rewrite_slug_url(url, target)

    # Then update the YYYY/MM path segment
    def _replace_ym(m: re.Match) -> str:
        try:
            orig_year = int(m.group(1))
            # Allow ±1 year to handle year-boundary transitions
            # (e.g. a December bulletin URL used to predict a January one)
            if abs(orig_year - target.year) <= 1:
                return f"/{target.year}/{target.month:02d}/"
        except (ValueError, AttributeError):
            pass
        return m.group(0)

    return _WP_YEAR_MONTH_RE.sub(_replace_ym, new_url)


def date_variants(target: date) -> list[str]:
    """
    Return all date-string patterns for the target date and the preceding six
    days that we should look for in PDF filenames / link text.
    """
    variants: list[str] = []
    for delta in range(7):
        d = target - timedelta(days=delta)
        dd = f"{d.day:02d}"
        mm = f"{d.month:02d}"
        yy = f"{d.year % 100:02d}"
        yyyy = str(d.year)
        variants += [
            f"{dd}{mm}{yy}",          # DDMMYY
            f"{dd}{mm}{yyyy}",        # DDMMYYYY
            f"{yyyy}-{mm}-{dd}",      # YYYY-MM-DD
            f"{yyyy}{mm}{dd}",        # YYYYMMDD
        ]
    return variants


def rewrite_date_url(url: str, target: date) -> str:
    """
    Rewrite a URL's date component(s) to use the *target* date.

    Recognised patterns (tried in order; first match wins):

    - Pattern A (DDMMYYYY / DDMMYY): /pdf/050426.pdf  ->  /pdf/120426.pdf
    - Pattern C (ISO YYYY-MM-DD):    /2026/04/2026-04-05.pdf  ->  /2026/04/2026-04-12.pdf
                                     (also updates any /YYYY/MM/ directory segment)
    - Pattern B (D-M-YY):            /onewebmedia/5-4-26.pdf  ->  /onewebmedia/12-4-26.pdf
    - Pattern D (DD-Month-YYYY):     Newsletter-12-April-2026.pdf  ->  Newsletter-19-April-2026.pdf
                                     (also updates any /YYYY/MM/ directory segment)
    - Pattern E ([YYYY-M-D]):        [2026-4-5].pdf  ->  [2026-4-12].pdf

    Returns the original URL unchanged if no date pattern is detected (Pattern F -
    static files like laveyparishbulletin.pdf are downloaded as-is).
    """
    parsed = urlparse(url)
    path = parsed.path

    def _update_yyyymm_dir(old_d: date, p: str) -> str:
        """Replace /YYYY/MM/ directory segments matching *old_d* with the target."""
        old_seg = f"/{old_d.year}/{old_d.month:02d}/"
        new_seg = f"/{target.year}/{target.month:02d}/"
        return p.replace(old_seg, new_seg)

    # ------------------------------------------------------------------
    # Pattern A: DDMMYYYY (8 consecutive digits)
    # ------------------------------------------------------------------
    def _replace_ddmmyyyy(m: re.Match) -> str:
        try:
            orig = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
            if abs((orig - target).days) < 365:
                return f"{target.day:02d}{target.month:02d}{target.year}"
        except ValueError:
            pass
        return m.group(0)

    new_path = _DDMMYYYY_RE.sub(_replace_ddmmyyyy, path)
    if new_path != path:
        return parsed._replace(path=new_path).geturl()

    # Pattern A: DDMMYY (6 consecutive digits)
    def _replace_ddmmyy(m: re.Match) -> str:
        try:
            year = 2000 + int(m.group(3))
            orig = date(year, int(m.group(2)), int(m.group(1)))
            if abs((orig - target).days) < 365:
                return f"{target.day:02d}{target.month:02d}{target.year % 100:02d}"
        except ValueError:
            pass
        return m.group(0)

    new_path = _DDMMYY_RE.sub(_replace_ddmmyy, path)
    if new_path != path:
        return parsed._replace(path=new_path).geturl()

    # ------------------------------------------------------------------
    # Pattern C: ISO YYYY-MM-DD (with optional /YYYY/MM/ directory update)
    # ------------------------------------------------------------------
    orig_iso: "date | None" = None
    iso_m = _ISO_RE.search(path)
    if iso_m:
        try:
            orig_iso = date(int(iso_m.group(1)), int(iso_m.group(2)), int(iso_m.group(3)))
        except ValueError:
            pass

    if orig_iso and abs((orig_iso - target).days) < 365:
        def _replace_iso(m: re.Match) -> str:
            try:
                d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                if abs((d - target).days) < 365:
                    return f"{target.year}-{target.month:02d}-{target.day:02d}"
            except ValueError:
                pass
            return m.group(0)

        new_path = _ISO_RE.sub(_replace_iso, path)
        new_path = _update_yyyymm_dir(orig_iso, new_path)
        return parsed._replace(path=new_path).geturl()

    # ------------------------------------------------------------------
    # Pattern B: D-M-YY (dashed, 1-2 digit day/month, 2-digit year)
    # e.g. 5-4-26  ->  12-4-26  (Limavady parish)
    # ------------------------------------------------------------------
    def _replace_d_m_yy(m: re.Match) -> str:
        try:
            year = 2000 + int(m.group(3))
            orig = date(year, int(m.group(2)), int(m.group(1)))
            if abs((orig - target).days) < 365:
                return f"{target.day}-{target.month}-{target.year % 100:02d}"
        except ValueError:
            pass
        return m.group(0)

    new_path = _D_M_YY_RE.sub(_replace_d_m_yy, path)
    if new_path != path:
        return parsed._replace(path=new_path).geturl()

    # ------------------------------------------------------------------
    # Pattern D: DD-Month-YYYY slug (also updates /YYYY/MM/ dir)
    # e.g. Newsletter-12-April-2026.pdf  ->  Newsletter-19-April-2026.pdf
    # ------------------------------------------------------------------
    slug_m = _SLUG_DATE_RE.search(path)
    orig_slug: "date | None" = None
    if slug_m:
        try:
            old_month = _MONTH_MAP.get(slug_m.group(2).lower())
            if old_month:
                orig_slug = date(int(slug_m.group(3)), old_month, int(slug_m.group(1)))
        except ValueError:
            pass

    if orig_slug and abs((orig_slug - target).days) < 365:
        def _replace_slug_d(m: re.Match) -> str:
            try:
                old_month_num = _MONTH_MAP.get(m.group(2).lower())
                if not old_month_num:
                    return m.group(0)
                d = date(int(m.group(3)), old_month_num, int(m.group(1)))
                if abs((d - target).days) < 365:
                    sep_pos = m.start() + len(m.group(1))
                    sep = path[sep_pos] if sep_pos < len(path) else "-"
                    month_str = _MONTH_NAMES[target.month].capitalize()
                    return f"{target.day:02d}{sep}{month_str}{sep}{target.year}"
            except ValueError:
                pass
            return m.group(0)

        new_path = _SLUG_DATE_RE.sub(_replace_slug_d, path)
        new_path = _update_yyyymm_dir(orig_slug, new_path)
        return parsed._replace(path=new_path).geturl()

    # ------------------------------------------------------------------
    # Pattern E: [YYYY-M-D] bracketed ISO variant (Greenlough parish)
    # e.g. [2026-4-5]  ->  [2026-4-12]
    # ------------------------------------------------------------------
    def _replace_bracketed(m: re.Match) -> str:
        try:
            orig = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            if abs((orig - target).days) < 365:
                return f"[{target.year}-{target.month}-{target.day}]"
        except ValueError:
            pass
        return m.group(0)

    new_path = _BRACKETED_ISO_RE.sub(_replace_bracketed, path)
    if new_path != path:
        return parsed._replace(path=new_path).geturl()

    # ------------------------------------------------------------------
    # Pattern F: No date found - return URL unchanged (static files).
    # ------------------------------------------------------------------
    return url


def safe_filename(prefix: str, suffix: str) -> str:
    """Combine a sanitized parish prefix with a file suffix."""
    prefix = re.sub(r"[^a-z0-9_-]", "_", prefix.lower())
    return f"{prefix}{suffix}"


# ---------------------------------------------------------------------------
# PDF validation
# ---------------------------------------------------------------------------

def is_valid_pdf(path: Path) -> bool:
    """Return True if the file at *path* starts with the PDF magic bytes ``%PDF``."""
    try:
        with path.open("rb") as fh:
            return fh.read(4) == b"%PDF"
    except OSError:
        return False
