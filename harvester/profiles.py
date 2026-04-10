"""
profiles.py — Self-learning parish profile system for the Parish Bulletin Harvester.

After each run, a JSON file is written to ``parishes/parish_profiles.json`` that
records what worked and what did not for every parish.  On the next run the file
is loaded and the stored information is used to make smarter decisions (e.g. skip
straight to the HTML scraping strategy for a known Wix site, or try a rewritten
version of the last successful URL before doing a full page scan).
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Load / save
# ---------------------------------------------------------------------------

def load_profiles(path: Path) -> dict[str, Any]:
    """
    Load parish profiles from *path*.
    Returns an empty dict if the file does not exist or cannot be parsed.
    """
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_profiles(profiles: dict[str, Any], path: Path) -> None:
    """Write *profiles* to *path* as pretty-printed JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(profiles, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Update / query
# ---------------------------------------------------------------------------

def update_profile(
    profiles: dict[str, Any],
    parish: str,
    fetch_result: Any,
    target: date,
) -> None:
    """
    Update *profiles[parish]* in-place based on the outcome stored in
    *fetch_result*.

    *fetch_result* is expected to have the attributes:
        .url, .status, .error, .file_type, .site_type, .source_url
    (All optional; missing attributes are handled gracefully.)
    """
    profile: dict[str, Any] = profiles.setdefault(
        parish,
        {
            "url": getattr(fetch_result, "url", ""),
            "last_success_method": None,
            "last_success_date": None,
            "last_success_url": None,
            "failure_count": 0,
            "consecutive_failures": 0,
            "last_failure_reason": None,
            "url_pattern": None,
            "site_type": None,
            "notes": [],
        },
    )

    # Always refresh the base URL
    profile["url"] = getattr(fetch_result, "url", profile.get("url", ""))

    # Persist detected site type (e.g. "wix") even on failure
    site_type = getattr(fetch_result, "site_type", None)
    if site_type:
        profile["site_type"] = site_type

    if getattr(fetch_result, "status", "") == "ok":
        profile["last_success_method"] = getattr(fetch_result, "file_type", None) or "pdf"
        profile["last_success_date"] = str(target)
        # Prefer source_url (the page where content was actually found)
        source_url = getattr(fetch_result, "source_url", "") or getattr(fetch_result, "url", "")
        profile["last_success_url"] = source_url
        profile["consecutive_failures"] = 0
        profile["last_failure_reason"] = None
    else:
        profile["failure_count"] = profile.get("failure_count", 0) + 1
        profile["consecutive_failures"] = profile.get("consecutive_failures", 0) + 1
        profile["last_failure_reason"] = getattr(fetch_result, "error", "unknown error")

        # Flag for manual review after 3+ consecutive failures
        if profile["consecutive_failures"] >= 3:
            note = (
                f"Consecutive failures >= 3 as of {target} — "
                "may need manual review"
            )
            notes: list[str] = profile.get("notes", [])
            if note not in notes:
                notes.append(note)
            # Keep the notes list bounded
            profile["notes"] = notes[-10:]


def get_hint(
    profiles: dict[str, Any],
    parish: str,
    target: date,
) -> dict[str, Any] | None:
    """
    Return a hint dict for *parish* based on its recorded history, or ``None``
    if no useful history exists.

    The hint dict may contain any subset of:
        last_success_url, last_success_method, site_type, url_pattern
    """
    profile = profiles.get(parish)
    if not profile:
        return None

    hint: dict[str, Any] = {}

    if profile.get("last_success_url"):
        hint["last_success_url"] = profile["last_success_url"]

    if profile.get("last_success_method"):
        hint["last_success_method"] = profile["last_success_method"]

    if profile.get("site_type"):
        hint["site_type"] = profile["site_type"]

    if profile.get("url_pattern"):
        hint["url_pattern"] = profile["url_pattern"]

    return hint if hint else None
