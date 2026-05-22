from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from ocr.generate_bulletin_pages import DIOCESES

PAGES_BASE_URL = "https://frankytyrone.github.io/parish_harvester"
CDN_BASE_URL = "https://cdn.jsdelivr.net/gh/Frankytyrone/parish_harvester@main"


def _coerce_rows(value: object) -> list[dict]:
    if not isinstance(value, list):
        return []
    return [row for row in value if isinstance(row, dict)]


def _load_parish_keys(repo_root: Path, diocese: str) -> set[str]:
    contacts_path = repo_root / "parishes" / f"{diocese}_contacts.json"
    if not contacts_path.exists():
        return set()
    try:
        payload = json.loads(contacts_path.read_text(encoding="utf-8"))
    except Exception:
        return set()
    if not isinstance(payload, dict):
        return set()
    return {str(key).strip() for key in payload.keys() if str(key).strip()}


def _count_parishes(rows: list[dict], parish_keys: set[str]) -> int:
    if not parish_keys:
        return 0
    return sum(1 for row in rows if str(row.get("parish") or "").strip() in parish_keys)


def _display_name(diocese: str, ocr_slug: str) -> str:
    if diocese == "derry_diocese":
        return "Derry Diocese"
    if ocr_slug == "down_and_connor":
        return "Down and Connor"
    return ocr_slug.replace("_", " ").title()


def build_manifest(report_path: Path, dioceses_in_run: list[str], output_path: Path) -> None:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    target_date = str(report.get("target_date") or "").strip()
    report_downloaded = _coerce_rows(report.get("downloaded"))
    report_html_links = _coerce_rows(report.get("html_links"))
    report_failed = _coerce_rows(report.get("failed"))

    repo_root = report_path.resolve().parent.parent
    mega_dir = repo_root / "mega_pdf"
    docs_bulletins_dir = repo_root / "docs" / "bulletins"

    dioceses: dict[str, dict] = {}
    for diocese in dioceses_in_run:
        if not isinstance(diocese, str) or not diocese.strip():
            continue
        normalized_diocese = diocese.strip()
        ocr_slug = normalized_diocese.removesuffix("_diocese")
        if ocr_slug not in DIOCESES:
            continue

        mega_filename = f"{ocr_slug}_mega_bulletin.pdf"
        mega_pdf_path = mega_dir / mega_filename
        if not mega_pdf_path.exists():
            continue

        parish_keys = _load_parish_keys(repo_root, normalized_diocese)
        downloaded = _count_parishes(report_downloaded, parish_keys)
        html_links = _count_parishes(report_html_links, parish_keys)
        failed = _count_parishes(report_failed, parish_keys)
        total = downloaded + failed
        success_rate = f"{(downloaded / total * 100) if total else 0.0:.1f}%"

        entry: dict[str, object] = {
            "display_name": _display_name(normalized_diocese, ocr_slug),
            "mega_pdf": f"{PAGES_BASE_URL}/mega_pdf/{mega_filename}",
            "mega_pdf_cdn": f"{CDN_BASE_URL}/mega_pdf/{mega_filename}",
            "downloaded": downloaded,
            "html_links": html_links,
            "failed": failed,
            "success_rate": success_rate,
        }

        if target_date:
            ocr_viewer_file = docs_bulletins_dir / f"{ocr_slug}-{target_date}.html"
            if ocr_viewer_file.exists():
                entry["ocr_viewer"] = f"{PAGES_BASE_URL}/bulletins/{ocr_slug}-{target_date}.html"

        dioceses[normalized_diocese] = entry

    payload = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "target_date": target_date,
        "dioceses": dioceses,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix="manifest-", suffix=".tmp", dir=output_path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
            handle.write("\n")
        os.replace(temp_path, output_path)
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)
