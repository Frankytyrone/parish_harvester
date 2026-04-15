"""
report.py — Simple report generator for the Parish Bulletin Harvester.

Moves downloaded PDFs to current/, writes report.json with
downloaded/html_links/failed counts.
"""
from __future__ import annotations

import json
import shutil
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .fetcher import FetchResult


def generate_report(
    results: list["FetchResult"],
    raw_dir: Path,
    current_dir: Path,
    report_json: Path,
    report_txt: Path,
    target: date,
) -> dict:
    """
    Move downloaded PDFs from raw_dir to current_dir, write report files.

    Returns a summary dict with keys: downloaded, html_links, failed, fallback.
    """
    current_dir.mkdir(parents=True, exist_ok=True)

    downloaded: list[dict] = []
    fallback: list[dict] = []
    html_links: list[dict] = []
    failed: list[dict] = []

    for r in results:
        if r.status == "ok" and r.file_path and r.file_path.exists():
            dest = current_dir / r.file_path.name
            shutil.copy2(r.file_path, dest)
            entry = {
                "parish": r.key,
                "display_name": r.display_name,
                "url": r.url,
                "file": dest.name,
                "file_type": r.file_type,
            }
            if r.is_fallback:
                fallback.append(entry)
            else:
                downloaded.append(entry)
        elif r.status == "html_link":
            html_links.append({
                "parish": r.key,
                "display_name": r.display_name,
                "url": r.url,
            })
        else:
            failed.append({
                "parish": r.key,
                "display_name": r.display_name,
                "url": r.url,
                "error": r.error,
            })

    report = {
        "target_date": str(target),
        "summary": {
            "downloaded": len(downloaded),
            "fallback": len(fallback),
            "html_links": len(html_links),
            "failed": len(failed),
        },
        "downloaded": downloaded,
        "fallback": fallback,
        "html_links": html_links,
        "failed": failed,
    }

    report_json.parent.mkdir(parents=True, exist_ok=True)
    report_json.write_text(json.dumps(report, indent=2), encoding="utf-8")

    lines = [
        f"Parish Bulletin Harvest Report — {target}",
        "=" * 50,
        f"Downloaded : {len(downloaded)}",
        f"Fallback   : {len(fallback)}",
        f"HTML links : {len(html_links)}",
        f"Failed     : {len(failed)}",
        "",
    ]
    if downloaded:
        lines += ["Downloaded bulletins:", ""]
        for d in downloaded:
            lines.append(f"  ✅ {d['display_name']} — {d['file']}")
        lines.append("")
    if fallback:
        lines += ["Fallback bulletins (possibly stale — target URL unavailable):", ""]
        for d in fallback:
            lines.append(f"  ⏪ {d['display_name']} — {d['file']}")
        lines.append("")
    if html_links:
        lines += ["HTML-only parishes (clickable links in mega PDF):", ""]
        for h in html_links:
            lines.append(f"  🔗 {h['display_name']} — {h['url']}")
        lines.append("")
    if failed:
        lines += ["Failed parishes:", ""]
        for f_item in failed:
            lines.append(f"  ❌ {f_item['display_name']} — {f_item['error']}")
        lines.append("")

    report_txt.write_text("\n".join(lines), encoding="utf-8")

    return report
