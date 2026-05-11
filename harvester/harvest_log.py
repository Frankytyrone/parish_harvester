"""
harvest_log.py — Append-only JSON harvest log and summary printer.

Every time a parish is fetched, a result entry is appended to
``harvest_log.json`` in the project root.  Call ``print_summary()`` at
the end of a run to see the last 20 entries as a neat table.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone
from pathlib import Path

from .fetcher import FetchResult

# Path to the JSON log file (project root)
_LOG_PATH = Path(__file__).resolve().parent.parent / "harvest_log.json"
_CONSECUTIVE_FAILURES_PATH = (
    Path(__file__).resolve().parent.parent / "parishes" / "consecutive_failures.json"
)
_STALE_BULLETINS_PATH = (
    Path(__file__).resolve().parent.parent / "parishes" / "stale_bulletins.json"
)


def log_result(
    result: FetchResult | None,
    key: str,
    display_name: str,
    error: str = "",
) -> None:
    """Append one harvest result to ``harvest_log.json``.

    Parameters
    ----------
    result:
        The ``FetchResult`` returned by the fetcher, or ``None`` if the
        fetch raised an unexpected exception.
    key:
        Parish key (e.g. ``"ardmoreparish"``).
    display_name:
        Human-readable parish name.
    error:
        Error message to record when *result* is ``None`` or
        ``result.status == "error"``.
    """
    if result is not None:
        status = result.status if result.status in ("ok", "html_link") else "failed"
        url = result.url
        file_type = result.file_type
        err_msg = result.error if status == "failed" else ""
    else:
        status = "failed"
        url = ""
        file_type = ""
        err_msg = error or "Unknown error"

    entry = {
        "parish_key": key,
        "display_name": display_name,
        "status": "ok" if status in ("ok", "html_link") else "failed",
        "url": url,
        "file_type": file_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "error": err_msg,
    }

    # Load existing log (or start fresh)
    try:
        existing: list[dict] = json.loads(_LOG_PATH.read_text(encoding="utf-8"))
        if not isinstance(existing, list):
            existing = []
    except (FileNotFoundError, json.JSONDecodeError):
        existing = []

    existing.append(entry)
    _LOG_PATH.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")


def print_summary(n: int = 20) -> None:
    """Print a neat table of the last *n* harvest entries to the terminal."""
    try:
        entries: list[dict] = json.loads(_LOG_PATH.read_text(encoding="utf-8"))
        if not isinstance(entries, list):
            entries = []
    except (FileNotFoundError, json.JSONDecodeError):
        print("  📋 No harvest log found yet.")
        return

    recent = entries[-n:]
    if not recent:
        print("  📋 Harvest log is empty.")
        return

    # Column widths
    col_name = max(len(e.get("display_name", "")) for e in recent)
    col_name = max(col_name, len("Parish"))
    col_status = 6
    col_type = max(len(e.get("file_type", "")) for e in recent)
    col_type = max(col_type, len("Type"))
    col_ts = 19  # "YYYY-MM-DDTHH:MM:SS"

    sep = (
        f"{'─' * (col_name + 2)}"
        f"┼{'─' * (col_status + 2)}"
        f"┼{'─' * (col_type + 2)}"
        f"┼{'─' * (col_ts + 2)}"
        f"┼{'─' * 40}"
    )

    header = (
        f" {'Parish':<{col_name}} "
        f"│ {'Status':<{col_status}} "
        f"│ {'Type':<{col_type}} "
        f"│ {'Timestamp':<{col_ts}} "
        f"│ Error / URL"
    )

    print(f"\n── Harvest Log (last {len(recent)}) {'─' * 40}")
    print(header)
    print(sep)

    for e in recent:
        name = (e.get("display_name") or "")[:col_name]
        status = e.get("status", "")
        status_icon = "✅ ok  " if status == "ok" else "💥 fail"
        ftype = (e.get("file_type") or "")[:col_type]
        ts_raw = e.get("timestamp", "")
        ts = ts_raw[:col_ts] if ts_raw else ""
        detail = e.get("error") or e.get("url") or ""
        detail = detail[:60]
        print(
            f" {name:<{col_name}} "
            f"│ {status_icon:<{col_status}} "
            f"│ {ftype:<{col_type}} "
            f"│ {ts:<{col_ts}} "
            f"│ {detail}"
        )

    ok_count = sum(1 for e in recent if e.get("status") == "ok")
    fail_count = sum(1 for e in recent if e.get("status") == "failed")
    print(f"\n  ✅ {ok_count} ok   💥 {fail_count} failed   (of last {len(recent)})\n")


def update_consecutive_failures(
    results: list[FetchResult], failures_path: Path | None = None
) -> dict[str, int]:
    """Update per-parish consecutive failure counts and persist to JSON."""
    path = failures_path or _CONSECUTIVE_FAILURES_PATH
    path.parent.mkdir(parents=True, exist_ok=True)

    try:
        existing = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(existing, dict):
            existing = {}
    except (FileNotFoundError, json.JSONDecodeError):
        existing = {}

    counts: dict[str, int] = {}
    for key, value in existing.items():
        try:
            counts[key] = max(0, int(value))
        except (TypeError, ValueError):
            counts[key] = 0

    for result in results:
        key = (result.key or "").strip()
        if not key:
            continue
        if result.status in ("ok", "html_link"):
            counts[key] = 0
        else:
            counts[key] = counts.get(key, 0) + 1

    path.write_text(json.dumps(counts, indent=2, ensure_ascii=False), encoding="utf-8")
    return counts


def _extract_date_from_url(url: str) -> date | None:
    """Extract a date from *url* using common bulletin filename patterns.

    Tried in order from most explicit to most compact:
    YYYY-MM-DD, DD-MM-YYYY/DD_MM_YYYY/DD/MM/YYYY, DDMMYY, and DDMMYYYY.
    Returns the first valid ``date`` parsed; invalid calendar dates are skipped.
    """
    text = url or ""
    patterns = (
        (
            re.compile(
                r"(?<!\d)(20\d{2})[-_/](0?[1-9]|1[0-2])[-_/](0?[1-9]|[12]\d|3[01])(?!\d)"
            ),
            lambda m: datetime(
                year=int(m.group(1)),
                month=int(m.group(2)),
                day=int(m.group(3)),
            ).date(),
        ),
        (
            re.compile(
                r"(?<!\d)(0?[1-9]|[12]\d|3[01])[-_/](0?[1-9]|1[0-2])[-_/]((?:19|20)\d{2})(?!\d)"
            ),
            lambda m: datetime(
                year=int(m.group(3)),
                month=int(m.group(2)),
                day=int(m.group(1)),
            ).date(),
        ),
        (
            re.compile(r"(?<!\d)(\d{2})(\d{2})(\d{2})(?!\d)"),
            lambda m: datetime.strptime("".join(m.groups()), "%d%m%y").date(),
        ),
        (
            re.compile(r"(?<!\d)(\d{2})(\d{2})((?:19|20)\d{2})(?!\d)"),
            lambda m: datetime.strptime("".join(m.groups()), "%d%m%Y").date(),
        ),
    )

    for pattern, parser in patterns:
        for match in pattern.finditer(text):
            try:
                return parser(match)
            except ValueError:
                continue
    return None


def update_stale_bulletins(
    results: list[FetchResult], bulletins_path: Path | None = None
) -> dict[str, object]:
    """Persist stale/unknown bulletin-date checks based on result URLs."""
    path = bulletins_path or _STALE_BULLETINS_PATH
    path.parent.mkdir(parents=True, exist_ok=True)

    today = date.today()
    stale: list[dict[str, object]] = []
    unknown_date: list[dict[str, object]] = []

    for result in results:
        if result.status != "ok" or not result.url:
            continue
        key = (result.key or "").strip()
        if not key:
            continue
        display_name = (result.display_name or key).strip() or key
        extracted = _extract_date_from_url(result.url)
        if extracted is None:
            unknown_date.append(
                {
                    "key": key,
                    "display_name": display_name,
                    "url": result.url,
                    "reason": "no_date_in_url",
                }
            )
            continue

        days_old = (today - extracted).days
        if days_old > 8:
            stale.append(
                {
                    "key": key,
                    "display_name": display_name,
                    "url": result.url,
                    "extracted_date": extracted.isoformat(),
                    "days_old": days_old,
                    "reason": "date_in_url",
                }
            )

    payload: dict[str, object] = {
        "generated_at": datetime.now(timezone.utc)
        .replace(tzinfo=None)
        .isoformat(timespec="seconds"),
        "stale": stale,
        "unknown_date": unknown_date,
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return payload
