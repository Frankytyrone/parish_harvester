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
        if last and last.lower() not in _SKIP:
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
    If a URL contains a DDMMYY/DDMMYYYY date pattern in its path, rewrite it
    to use the *target* date.  Used for sites like dmaparish.com/pdf/310825.pdf.
    """
    parsed = urlparse(url)
    path = parsed.path

    def _replace(m: re.Match) -> str:
        try:
            if len(m.group(0)) == 8:
                # DDMMYYYY
                orig = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
            else:
                # DDMMYY
                year = 2000 + int(m.group(3))
                orig = date(year, int(m.group(2)), int(m.group(1)))
            # Only rewrite if it looks like a plausible bulletin date
            if abs((orig - target).days) < 365:
                if len(m.group(0)) == 8:
                    return f"{target.day:02d}{target.month:02d}{target.year}"
                else:
                    return f"{target.day:02d}{target.month:02d}{target.year % 100:02d}"
        except ValueError:
            pass
        return m.group(0)

    new_path = _DDMMYYYY_RE.sub(_replace, path)
    if new_path == path:
        new_path = _DDMMYY_RE.sub(_replace, path)

    return parsed._replace(path=new_path).geturl()


def safe_filename(prefix: str, suffix: str) -> str:
    """Combine a sanitized parish prefix with a file suffix."""
    prefix = re.sub(r"[^a-z0-9_-]", "_", prefix.lower())
    return f"{prefix}{suffix}"
