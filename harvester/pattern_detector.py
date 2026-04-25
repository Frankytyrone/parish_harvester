"""
pattern_detector.py — Intelligent URL pattern detection for the Parish Harvester.

When a parish's predicted bulletin URL returns HTTP 404 this module tries
alternative date-format patterns (A–E) to detect whether the parish has
silently changed their URL structure.

Usage (inside fetcher.py)::

    from .pattern_detector import detect_pattern, save_pattern_change

    new_url = await detect_pattern(parish_key, failed_url, target_date, browser)
    if new_url:
        ...
        save_pattern_change(parish_key, failed_url, new_url, target_date)
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.async_api import Browser

from .config import PAGE_LOAD_TIMEOUT_MS, PARISHES_DIR
from .utils import generate_url_variants

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Path to the JSON file that persists detected pattern changes across runs.
PATTERN_CHANGES_FILE: Path = PARISHES_DIR / "pattern_changes.json"

# Number of consecutive weekly successes required before printing an upgrade hint.
_CONFIRM_THRESHOLD: int = 2


# ---------------------------------------------------------------------------
# Pattern change persistence helpers
# ---------------------------------------------------------------------------

def load_pattern_changes() -> dict:
    """Load the pattern-changes tracking file.  Returns ``{}`` on any error."""
    if PATTERN_CHANGES_FILE.exists():
        try:
            return json.loads(PATTERN_CHANGES_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_pattern_change(
    parish_key: str,
    original_url: str,
    new_url: str,
    target_date: date,
) -> None:
    """
    Record (or update) a detected URL-pattern change for *parish_key*.

    - First detection:  creates an entry with ``confidence = 1``.
    - Same new URL on a subsequent run: increments ``confidence``.
    - Different new URL:  resets the entry (pattern changed again).

    When ``confidence`` reaches :data:`_CONFIRM_THRESHOLD` a human-friendly
    suggestion to update the evidence file is printed.
    """
    changes = load_pattern_changes()
    today = target_date.isoformat()

    existing = changes.get(parish_key)
    if existing and existing.get("new_url") == new_url:
        existing["confidence"] = existing.get("confidence", 1) + 1
        existing["last_success"] = today
    else:
        changes[parish_key] = {
            "detected": today,
            "original_url": original_url,
            "new_url": new_url,
            "confidence": 1,
            "last_success": today,
        }

    try:
        PATTERN_CHANGES_FILE.write_text(
            json.dumps(changes, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception as exc:
        print(f"  ⚠️  Could not save pattern change for {parish_key}: {exc}")
        return

    confidence = changes[parish_key]["confidence"]
    if confidence >= _CONFIRM_THRESHOLD:
        print(
            f"  💡 Pattern change confirmed ({confidence} weeks). "
            f"Consider updating the evidence file:\n"
            f"     old: {original_url}\n"
            f"     new: {new_url}"
        )


# ---------------------------------------------------------------------------
# Core detection logic
# ---------------------------------------------------------------------------

async def detect_pattern(
    parish_key: str,
    original_url: str,
    target_date: date,
    browser: "Browser",
) -> str | None:
    """
    Try alternative URL date-format patterns when *original_url* returns 404.

    Generates up to 10 candidate URLs (via :func:`~harvester.utils.generate_url_variants`),
    sends a HEAD request to each, and returns the first URL that responds with
    HTTP 200.  Returns ``None`` if no variant succeeds.

    Only HEAD requests are made — no full file downloads during detection.
    """
    variants = generate_url_variants(original_url, target_date)
    if not variants:
        return None

    print(f"  🔍 Trying {len(variants)} pattern variants for {parish_key}...")

    context = await browser.new_context()
    try:
        page = await context.new_page()
        for variant_url in variants:
            encoded = variant_url.replace(" ", "%20")
            try:
                response = await page.request.fetch(
                    encoded,
                    method="HEAD",
                    timeout=PAGE_LOAD_TIMEOUT_MS,
                )
                status = response.status
                if response.ok:
                    print(f"     {variant_url}: {status} ✓")
                    return variant_url
                else:
                    print(f"     {variant_url}: {status}")
            except Exception as exc:
                print(f"     {variant_url}: error ({exc})")
    finally:
        try:
            await context.close()
        except Exception:
            pass

    return None
