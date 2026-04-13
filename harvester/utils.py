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
        # Also skip dated filenames (e.g. Bulletin-5th-April-2026) — those change
        # every week and would make the key unstable.
        _has_year = bool(re.search(r"\b20[0-9]{2}\b", last))
        if last and last.lower() not in _SKIP and not last.isdigit() and not _has_year:
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

# Pattern G: WordPress date-based post slug /YYYY/MM/DD/slug/
# e.g. clonleighparish.com/2026/04/03/strabane-pastoral-area-newsletter.../
_WP_DATE_POST_RE = re.compile(r"/(\d{4})/(\d{2})/(\d{2})/[^/]+/")

# Lighter variant: matches just the /YYYY/MM/DD/ path segment (no slug required).
# Used by _find_dated_bulletin_link() to extract publish dates from WP post URLs.
_WP_DATE_PATH_RE = re.compile(r"/(\d{4})/(\d{2})/(\d{2})/")

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

# Matches date slugs like "5_april_2026", "15-february-2026", "5th-April-2026"
# The optional ordinal suffix (?:st|nd|rd|th)? handles formats like "5th" or "12th".
_SLUG_DATE_RE = re.compile(
    r"(\d{1,2})(?:st|nd|rd|th)?[_\-]([a-z]+)[_\-](\d{4})",
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

    # Determine the separator used in the original slug.
    # Use the character just before the month group (group 2) to correctly
    # handle ordinal suffixes like "5th-April-2026" where group 1 is "5".
    sep_pos = m.start(2) - 1
    sep = url[sep_pos] if 0 <= sep_pos < len(url) else "_"

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
    # Day and month intentionally omit leading zeros (matching the input pattern).
    # Year uses :02d so that e.g. year 2005 produces "05" not "5".
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
                    # Use the character just before group 2 as separator to
                    # correctly handle ordinals like "5th-April" where group 1="5"
                    sep_pos = m.start(2) - 1
                    sep = path[sep_pos] if 0 <= sep_pos < len(path) else "-"
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
    # Pattern G: WordPress date-based post slug /YYYY/MM/DD/slug/
    # (e.g. clonleighparish.com/2026/04/03/strabane-newsletter-.../
    #   -> clonleighparish.com/2026/04/10/)
    # Strip the unpredictable slug and return the day-archive URL with
    # the date shifted by 7 days so the fetcher can find the new post.
    # ------------------------------------------------------------------
    g_m = _WP_DATE_POST_RE.search(path)
    if g_m:
        try:
            g_orig = date(int(g_m.group(1)), int(g_m.group(2)), int(g_m.group(3)))
            if abs((g_orig - target).days) < 365:
                predicted_date = g_orig + timedelta(days=7)
                new_seg = (
                    f"/{predicted_date.year}"
                    f"/{predicted_date.month:02d}"
                    f"/{predicted_date.day:02d}/"
                )
                return parsed._replace(path=path[: g_m.start()] + new_seg).geturl()
        except ValueError:
            pass

    # ------------------------------------------------------------------
    # Pattern F: No date found - return URL unchanged (static files).
    # However, if the URL has a /YYYY/MM/ directory segment, update that
    # even when the filename itself has no recognisable date.  This handles
    # WordPress image bulletins (e.g. Iskaheen parish) where the filename
    # is always "1.jpg" but the year/month directory changes monthly.
    # ------------------------------------------------------------------
    new_path = _WP_YEAR_MONTH_RE.sub(
        lambda m: (
            f"/{target.year}/{target.month:02d}/"
            if abs(int(m.group(1)) - target.year) <= 1
            else m.group(0)
        ),
        path,
    )
    if new_path != path:
        return parsed._replace(path=new_path).geturl()

    return url


# ---------------------------------------------------------------------------
# Pattern G — WordPress date-based post slugs (Clonleigh / Strabane)
# ---------------------------------------------------------------------------


def rewrite_wp_date_post_url(url: str, target: date) -> str:
    """
    Rewrite a WordPress post URL in the format ``/YYYY/MM/DD/slug/`` by
    date-shifting the date component 7 days forward and stripping the
    unpredictable slug.

    The resulting URL is the WordPress day-archive page (``/YYYY/MM/DD/``).
    The fetcher uses ``_find_dated_bulletin_link()`` to locate the actual
    newsletter post on that archive page.

    Example::

        https://clonleighparish.com/2026/04/03/strabane-pastoral-area-newsletter.../
        → https://clonleighparish.com/2026/04/10/   (target 7 days later, slug stripped)

    Returns the original URL unchanged if no ``/YYYY/MM/DD/slug/`` segment is found.
    """
    m = _WP_DATE_POST_RE.search(url)
    if not m:
        return url
    try:
        orig = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return url

    if abs((orig - target).days) >= 365:
        return url

    # Shift date by 7 days to predict next post publish date
    predicted_date = orig + timedelta(days=7)
    new_seg = f"/{predicted_date.year}/{predicted_date.month:02d}/{predicted_date.day:02d}/"
    # Strip everything from the slug onwards; keep only up to /YYYY/MM/DD/
    return url[: m.start()] + new_seg


# ---------------------------------------------------------------------------
# Pattern H — Sequential newsletter number (Banagher & Three Patrons)
# ---------------------------------------------------------------------------

# Matches both /Newsletters/NNN/ (Banagher) and /Weekly-Bulletins/NNN/ (Three Patrons)
_NEWSLETTER_NUM_RE = re.compile(r"(/(?:Newsletters|Weekly-Bulletins)/)(\d+)/")


def extract_newsletter_number(url: str) -> "int | None":
    """
    Extract the sequential newsletter number from a Banagher- or Three-Patrons-style URL.

    Examples::

        https://www.banagherparish.com/files/9/Newsletters/384/Bulletin---...
        → 384

        https://www.threepatrons.org/files/10/Weekly-Bulletins/95/Sunday-12th-April-2026
        → 95

    Returns ``None`` if neither ``/Newsletters/NNN/`` nor ``/Weekly-Bulletins/NNN/``
    is found.
    """
    m = _NEWSLETTER_NUM_RE.search(url)
    if m:
        return int(m.group(2))
    return None


def rewrite_newsletter_number_url(url: str, increment: int = 1) -> str:
    """
    Increment the sequential newsletter number in a Banagher- or Three-Patrons-style
    URL and strip the unpredictable free-form slug that follows it.

    Examples::

        https://www.banagherparish.com/files/9/Newsletters/384/Bulletin---Divine-Mercy-Sunday---12th-April-2026
        → https://www.banagherparish.com/files/9/Newsletters/385/

        https://www.threepatrons.org/files/10/Weekly-Bulletins/95/Sunday-12th-April-2026
        → https://www.threepatrons.org/files/10/Weekly-Bulletins/96/

    The slug after the number is removed because it cannot be predicted.

    Returns the original URL unchanged if no ``/Newsletters/NNN/`` or
    ``/Weekly-Bulletins/NNN/`` segment is found.
    """
    m = _NEWSLETTER_NUM_RE.search(url)
    if not m:
        return url
    new_number = int(m.group(2)) + increment
    # m.group(1) preserves the category name (/Newsletters/ or /Weekly-Bulletins/)
    return url[: m.start()] + m.group(1) + f"{new_number}/"


def safe_filename(prefix: str, suffix: str) -> str:
    """Combine a sanitized parish prefix with a file suffix."""
    prefix = re.sub(r"[^a-z0-9_-]", "_", prefix.lower())
    return f"{prefix}{suffix}"


# ---------------------------------------------------------------------------
# Greenlough parish — liturgical name + date rewrite
# ---------------------------------------------------------------------------

def rewrite_greenlough_url(url: str, target: date) -> str | None:
    """
    Rewrite a Greenlough parish URL by replacing both the liturgical
    Sunday name and the [YYYY-M-D] date bracket.

    Returns the new URL, or None if this isn't a Greenlough URL or
    no liturgical name is available for the target date.
    """
    if "greenlough.com/publications/newsletter/" not in url:
        return None
    from .liturgical import get_liturgical_name
    name = get_liturgical_name(target)
    if not name:
        return None
    # The URL pattern is: .../newsletter/LITURGICAL_NAME_[YYYY-M-D].pdf
    # Extract the base and rebuild
    base = url.split("/newsletter/")[0] + "/newsletter/"
    return f"{base}{name}_[{target.year}-{target.month}-{target.day}].pdf"


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
