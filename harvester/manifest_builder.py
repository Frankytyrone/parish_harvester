from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from xml.etree import ElementTree as ET

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


def _write_atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix=f"{path.stem}-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
            handle.write("\n")
        os.replace(temp_path, path)
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


def _load_failures(repo_root: Path) -> dict[str, int]:
    failures_path = repo_root / "parishes" / "consecutive_failures.json"
    if not failures_path.exists():
        return {}
    try:
        payload = json.loads(failures_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(payload, dict):
        return {}

    failures: dict[str, int] = {}
    for key, value in payload.items():
        parish_key = str(key).strip()
        if not parish_key:
            continue
        try:
            failures[parish_key] = int(value)
        except (TypeError, ValueError):
            continue
    return failures


def _all_parish_keys(repo_root: Path) -> list[str]:
    parishes_dir = repo_root / "parishes"
    keys: set[str] = set()
    for contacts_path in parishes_dir.glob("*_contacts.json"):
        try:
            payload = json.loads(contacts_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        keys.update(str(key).strip() for key in payload.keys() if str(key).strip())
    return sorted(keys)


def _to_tier(success_rate: float | None, failures: int | None = None) -> str:
    if success_rate is not None:
        if success_rate >= 0.8:
            return "green"
        if success_rate >= 0.5:
            return "amber"
        return "red"
    if failures is None:
        return "grey"
    if failures <= 0:
        return "green"
    if failures <= 2:
        return "amber"
    return "red"


def _normalise_last_success(raw: object) -> str | None:
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    if not text:
        return None
    if len(text) >= 10:
        return text[:10]
    return text


def _build_reliability(repo_root: Path, generated_at: str) -> dict[str, object]:
    failures = _load_failures(repo_root)
    learned_dir = repo_root / "recipes" / "learned"

    parishes: dict[str, dict[str, object]] = {}
    for parish_key in _all_parish_keys(repo_root):
        learned_path = learned_dir / f"{parish_key}.json"
        learned_payload: dict[str, object] = {}
        if learned_path.exists():
            try:
                candidate = json.loads(learned_path.read_text(encoding="utf-8"))
                if isinstance(candidate, dict):
                    learned_payload = candidate
            except Exception:
                learned_payload = {}

        success_rate: float | None = None
        raw_rate = learned_payload.get("success_rate")
        if isinstance(raw_rate, (int, float)):
            success_rate = max(0.0, min(float(raw_rate), 1.0))

        failure_count = failures.get(parish_key)
        if success_rate is None and failure_count is not None:
            if failure_count <= 0:
                success_rate = 1.0
            elif failure_count <= 2:
                success_rate = 0.5
            else:
                success_rate = 0.0

        parishes[parish_key] = {
            "success_rate": success_rate,
            "tier": _to_tier(success_rate, failure_count),
            "last_success": _normalise_last_success(learned_payload.get("last_success")),
        }

    return {
        "generated_at": generated_at,
        "parishes": parishes,
    }


def _write_rss_feeds(
    docs_dir: Path,
    dioceses: dict[str, dict[str, object]],
    target_date: str,
    generated_at_dt: datetime,
) -> None:
    feeds_dir = docs_dir / "feeds"
    feeds_dir.mkdir(parents=True, exist_ok=True)

    item_date = target_date.strip() if target_date else generated_at_dt.date().isoformat()
    pub_date = format_datetime(generated_at_dt)

    for diocese, data in dioceses.items():
        display_name = str(data.get("display_name") or diocese)
        mega_pdf = str(data.get("mega_pdf") or "")
        success_rate = str(data.get("success_rate") or "")

        rss = ET.Element("rss", version="2.0")
        channel = ET.SubElement(rss, "channel")
        ET.SubElement(channel, "title").text = f"{display_name} Bulletins"
        ET.SubElement(channel, "link").text = mega_pdf
        ET.SubElement(channel, "description").text = f"Latest bulletin feed for {display_name}"
        ET.SubElement(channel, "lastBuildDate").text = pub_date

        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = f"{display_name} bulletin for {item_date}"
        ET.SubElement(item, "link").text = mega_pdf
        ET.SubElement(item, "guid").text = f"{mega_pdf}#{item_date}"
        ET.SubElement(item, "pubDate").text = pub_date
        ET.SubElement(item, "description").text = f"Latest mega PDF ({success_rate} success rate)"

        feed_path = feeds_dir / f"{diocese}.xml"
        ET.ElementTree(rss).write(feed_path, encoding="utf-8", xml_declaration=True)


def build_manifest(report_path: Path, dioceses_in_run: list[str], output_path: Path) -> None:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    target_date = str(report.get("target_date") or "").strip()
    report_downloaded = _coerce_rows(report.get("downloaded"))
    report_html_links = _coerce_rows(report.get("html_links"))
    report_failed = _coerce_rows(report.get("failed"))

    repo_root = report_path.resolve().parent.parent
    mega_dir = repo_root / "mega_pdf"
    docs_dir = repo_root / "docs"
    docs_bulletins_dir = docs_dir / "bulletins"

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

    generated_at_dt = datetime.now(timezone.utc).replace(microsecond=0)
    generated_at = generated_at_dt.isoformat().replace("+00:00", "Z")
    payload = {
        "generated_at": generated_at,
        "target_date": target_date,
        "dioceses": dioceses,
    }

    _write_atomic_json(output_path, payload)
    _write_atomic_json(docs_dir / "reliability.json", _build_reliability(repo_root, generated_at))
    _write_rss_feeds(docs_dir, dioceses, target_date, generated_at_dt)
