"""
cleaner.py — Stage 3: Sort fresh/stale files and generate reports.
"""
from __future__ import annotations

import json
import shutil
from datetime import date, datetime
from pathlib import Path
from typing import Any

from .config import BULLETINS_DIR, CURRENT_DIR, RAW_DIR, REPORT_JSON, REPORT_TXT

HISTORY_DIR = BULLETINS_DIR / "history"


def _categorise_fetch_error(error: str) -> str:
    """Return a short category label for a fetch error message."""
    e = error.lower()
    if "timeout" in e:
        return "Timeout"
    if "no pdf found" in e:
        return "No PDF Found"
    if "not a valid pdf" in e or "invalid pdf" in e:
        return "Invalid PDF"
    if "http " in e or "http error" in e or "status" in e:
        return "HTTP Error"
    return "Other"


class CleanResult:
    """Summary of what the cleaner did."""

    def __init__(self) -> None:
        self.fresh: list[dict[str, Any]] = []
        self.stale: list[dict[str, Any]] = []
        self.unknown: list[dict[str, Any]] = []
        self.errors: list[dict[str, Any]] = []
        # Parishes that could not be fetched at all (no file downloaded)
        self.failed_fetches: list[dict[str, Any]] = []

    def add(self, parish: str, file_path: Path, verdict: str) -> None:
        entry: dict[str, Any] = {
            "parish": parish,
            "file": file_path.name,
            "verdict": verdict,
        }
        if verdict == "FRESH":
            self.fresh.append(entry)
        elif verdict == "STALE":
            self.stale.append(entry)
        elif verdict.startswith("ERROR"):
            self.errors.append(entry)
        else:
            self.unknown.append(entry)

    @property
    def total(self) -> int:
        return len(self.fresh) + len(self.stale) + len(self.unknown) + len(self.errors)


def clean(
    verdicts: dict[str, str],   # file_path.name → verdict
    raw_dir: Path | None = None,
    current_dir: Path | None = None,
    report_json: Path | None = None,
    report_txt: Path | None = None,
    target: date | None = None,
    failed_fetches: list[dict[str, Any]] | None = None,
) -> CleanResult:
    """
    Move FRESH and UNKNOWN files to *current_dir*, delete STALE/ERROR files
    from *raw_dir*, and write JSON + text reports.

    *verdicts* maps file basename → "FRESH" | "STALE" | "UNKNOWN" | "ERROR:..."
    *failed_fetches* is an optional list of dicts with keys: parish, url, error.
    """
    raw_dir = raw_dir or RAW_DIR
    current_dir = current_dir or CURRENT_DIR
    report_json = report_json or REPORT_JSON
    report_txt = report_txt or REPORT_TXT
    failed_fetches = failed_fetches or []

    current_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)
    report_json.parent.mkdir(parents=True, exist_ok=True)

    result = CleanResult()
    result.failed_fetches = list(failed_fetches)

    for filename, verdict in verdicts.items():
        src = raw_dir / filename
        if not src.exists():
            continue

        # Derive parish name from filename (strip extension)
        parish = src.stem

        result.add(parish, src, verdict)

        if verdict == "FRESH" or verdict == "UNKNOWN":
            dest = current_dir / filename
            shutil.move(str(src), str(dest))
        else:
            # STALE or ERROR → delete
            src.unlink(missing_ok=True)

    # -----------------------------------------------------------------------
    # Generate reports
    # -----------------------------------------------------------------------
    report_data: dict[str, Any] = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "target_date": str(target) if target else None,
        "summary": {
            "total": result.total,
            "fresh": len(result.fresh),
            "stale": len(result.stale),
            "unknown": len(result.unknown),
            "errors": len(result.errors),
            "failed_fetches": len(result.failed_fetches),
        },
        "fresh": result.fresh,
        "stale": result.stale,
        "unknown": result.unknown,
        "errors": result.errors,
        "failed_fetches": result.failed_fetches,
    }

    report_json.write_text(json.dumps(report_data, indent=2), encoding="utf-8")

    # Save a dated copy in history/
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    date_suffix = str(target) if target else datetime.utcnow().strftime("%Y-%m-%d")
    history_path = HISTORY_DIR / f"report_{date_suffix}.json"
    history_path.write_text(json.dumps(report_data, indent=2), encoding="utf-8")
    print(f"  📚 History : {history_path}")

    lines = [
        "Parish Bulletin Harvest Report",
        "=" * 40,
        f"Generated : {report_data['generated_at']}",
        f"Target    : {report_data['target_date']}",
        "",
        f"Total processed : {result.total}",
        f"✅ FRESH         : {len(result.fresh)}",
        f"❌ STALE         : {len(result.stale)}",
        f"⚠️  UNKNOWN       : {len(result.unknown)}",
        f"💥 ERRORS         : {len(result.errors)}",
        f"🚫 FAILED FETCH   : {len(result.failed_fetches)}",
        "",
    ]
    if result.fresh:
        lines.append("--- FRESH ---")
        for e in result.fresh:
            lines.append(f"  {e['parish']:40s}  {e['file']}")
        lines.append("")
    if result.stale:
        lines.append("--- STALE ---")
        for e in result.stale:
            lines.append(f"  {e['parish']:40s}  {e['file']}")
        lines.append("")
    if result.unknown:
        lines.append("--- UNKNOWN ---")
        for e in result.unknown:
            lines.append(f"  {e['parish']:40s}  {e['file']}")
        lines.append("")
    if result.errors:
        lines.append("--- ERRORS ---")
        for e in result.errors:
            lines.append(f"  {e['parish']:40s}  {e['file']}  ({e['verdict']})")
        lines.append("")

    if result.failed_fetches:
        lines.append("--- FAILED TO RETRIEVE ---")
        # Group by error category
        by_category: dict[str, list[dict[str, Any]]] = {}
        for ff in result.failed_fetches:
            cat = _categorise_fetch_error(ff.get("error", ""))
            by_category.setdefault(cat, []).append(ff)

        for cat in sorted(by_category):
            lines.append(f"  [{cat}]")
            for ff in by_category[cat]:
                lines.append(
                    f"    {ff['parish']:38s}  {ff.get('url', '')}  —  {ff.get('error', '')}"
                )
        lines.append("")

    report_txt.write_text("\n".join(lines), encoding="utf-8")

    return result
