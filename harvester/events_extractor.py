from __future__ import annotations

"""Extract dated community events from parish bulletin OCR text.

Uses the ai_router multi-provider fallback (Gemini → Groq → Mistral).
On AI failure returns ``[]`` and logs honestly — never invents events.

Output schema per event::

    {
        "title": str,
        "date_iso": "YYYY-MM-DD",
        "time_24h_or_null": "HH:MM" | null,
        "location_or_null": str | null,
        "description": str,
        "category": "mass"|"confession"|"meeting"|"fundraiser"|"sacrament"|"social"|"youth"|"other"
    }
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

MAX_INPUT_CHARS = 12_000

_EVENTS_PROMPT = (
    "From this Catholic parish bulletin text, extract every dated event. "
    "Return a JSON array. Each item: "
    '{"title", "date_iso", "time_24h_or_null", "location_or_null", "description", "category"}. '
    "Categories: mass, confession, meeting, fundraiser, sacrament, social, youth, other. "
    "Only include events with a real date. "
    "Return [] if no events found. JSON only, no prose."
)

VALID_CATEGORIES = frozenset(
    {"mass", "confession", "meeting", "fundraiser", "sacrament", "social", "youth", "other"}
)


def _validate_date_iso(value: Any) -> bool:
    """Return True if *value* is a string parseable as YYYY-MM-DD."""
    if not isinstance(value, str):
        return False
    try:
        datetime.strptime(value.strip(), "%Y-%m-%d")
        return True
    except ValueError:
        return False


def _validate_event(item: Any) -> dict | None:
    """Return a cleaned event dict or None if the item is structurally invalid."""
    if not isinstance(item, dict):
        return None
    if not _validate_date_iso(item.get("date_iso")):
        return None
    title = str(item.get("title") or "").strip()
    if not title:
        return None
    category = str(item.get("category") or "other").strip().lower()
    if category not in VALID_CATEGORIES:
        category = "other"
    return {
        "title": title,
        "date_iso": item["date_iso"].strip(),
        "time_24h_or_null": item.get("time_24h_or_null") or None,
        "location_or_null": item.get("location_or_null") or None,
        "description": str(item.get("description") or "").strip(),
        "category": category,
    }


def _parse_events_json(raw: str) -> list[dict]:
    """Try to extract a JSON array from the AI response text."""
    text = raw.strip()
    # Strip markdown code fences if present
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    # Find first '[' … last ']'
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1 or end <= start:
        return []
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return []


def extract_events(
    text: str,
    parish_name: str,
    parish_key: str,
    diocese: str,
    ai_router: Any = None,
) -> list[dict]:
    """Extract dated events from bulletin OCR text using the AI router.

    Parameters
    ----------
    text:
        Raw OCR text from the bulletin.
    parish_name:
        Human-readable parish name for logging.
    parish_key:
        Machine-readable key (used in file paths / UIDs).
    diocese:
        Diocese key (e.g. ``"derry"``).
    ai_router:
        Module or object with a ``call_ai(prompt) -> (text, provider)``
        callable.  If ``None``, the default ``harvester.ai_router`` is used.

    Returns
    -------
    list[dict]
        Validated events; empty list on AI failure or if none found.
    """
    if os.getenv("PARISH_EVENTS_DISABLE", "").strip() == "1":
        print(f"[events_extractor] Skipped for {parish_key} — PARISH_EVENTS_DISABLE=1")
        return []

    if ai_router is None:
        from harvester import ai_router as _default_router  # lazy import

        ai_router = _default_router

    truncated = (text or "")[:MAX_INPUT_CHARS]
    prompt = f"{_EVENTS_PROMPT}\n\nParish: {parish_name}\n\n{truncated}"

    try:
        raw_text, provider = ai_router.call_ai(prompt)
    except Exception as exc:  # noqa: BLE001
        print(f"[events_extractor] AI call raised unexpected error for {parish_key}: {exc}")
        return []

    if raw_text is None:
        print(f"[events_extractor] AI unavailable for {parish_key} — returning []")
        return []

    raw_items = _parse_events_json(raw_text)
    if not isinstance(raw_items, list):
        print(f"[events_extractor] AI returned non-list for {parish_key} — returning []")
        return []

    valid: list[dict] = []
    dropped = 0
    for item in raw_items:
        cleaned = _validate_event(item)
        if cleaned is None:
            dropped += 1
        else:
            valid.append(cleaned)

    if dropped:
        print(f"[events_extractor] {parish_key}: dropped {dropped} invalid items (no parseable date_iso).")

    print(
        f"[events_extractor] {parish_key}: {len(valid)} event(s) extracted via {provider or 'unknown'}."
    )
    return valid


def write_events_json(
    events: list[dict],
    parish_key: str,
    parish_name: str,
    diocese: str,
    bulletin_date: str,
    ai_provider: str | None,
    error: str | None,
    repo_root: Path,
) -> None:
    """Write the events output file for a single parish."""
    from datetime import timezone

    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    payload = {
        "generated_at": generated_at,
        "parish_key": parish_key,
        "parish_name": parish_name,
        "diocese": diocese,
        "source_bulletin_date": bulletin_date,
        "events": events,
        "ai_provider": ai_provider,
        "error": error,
    }
    out_path = repo_root / "Bulletins" / "events" / diocese / f"{parish_key}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    import os
    import tempfile

    fd, tmp = tempfile.mkstemp(prefix=f"{parish_key}-", suffix=".tmp", dir=out_path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
            fh.write("\n")
        os.replace(tmp, out_path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
