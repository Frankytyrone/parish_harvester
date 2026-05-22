from __future__ import annotations

import json
import os
import re
import tempfile
import unicodedata
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from xml.etree import ElementTree as ET

from ocr.generate_bulletin_pages import DIOCESES

PAGES_BASE_URL = "https://frankytyrone.github.io/parish_harvester"
CDN_BASE_URL = "https://cdn.jsdelivr.net/gh/Frankytyrone/parish_harvester@main"
VIEWER_FILE_PATTERN = re.compile(r"^(derry|down_and_connor)-(\d{4}-\d{2}-\d{2})\.html$")
OCR_PANEL_PATTERN = re.compile(
    r'<div id="ocr-panel">\s*(.*?)\s*</div>\s*<div class="note-box">',
    re.DOTALL | re.IGNORECASE,
)
PARISH_NAME_PATTERN = re.compile(
    r"<li class=\"parish-item\"[^>]*>\s*<a class=\"parish-link\"[^>]*>\s*<span[^>]*>.*?</span>\s*<span>(.*?)</span>\s*</a>\s*</li>",
    re.DOTALL | re.IGNORECASE,
)
HTML_TAG_PATTERN = re.compile(r"<[^>]+>")
WHITESPACE_PATTERN = re.compile(r"\s+")
MAX_SEARCH_DOC_TEXT = 4_000
MAX_SEARCH_INDEX_BYTES = 5 * 1024 * 1024


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


def _normalise_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (value or "").lower())


def _load_display_to_key_map(repo_root: Path) -> dict[str, str]:
    mapping: dict[str, str] = {}
    parishes_dir = repo_root / "parishes"
    for path in parishes_dir.glob("*_contacts.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        for key, value in payload.items():
            parish_key = str(key).strip()
            if not parish_key:
                continue
            mapping[_normalise_key(parish_key)] = parish_key
            if isinstance(value, dict):
                display_name = str(value.get("display_name") or "").strip()
                if display_name:
                    mapping[_normalise_key(display_name)] = parish_key
                    if display_name.lower().endswith(" parish"):
                        mapping[_normalise_key(display_name[:-7])] = parish_key
    return mapping


def _extract_ocr_text(viewer_html: str) -> str:
    match = OCR_PANEL_PATTERN.search(viewer_html)
    if not match:
        return ""
    text = HTML_TAG_PATTERN.sub("\n", match.group(1))
    lines = [WHITESPACE_PATTERN.sub(" ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def _extract_parish_names(viewer_html: str) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for match in PARISH_NAME_PATTERN.finditer(viewer_html):
        name = str(match.group(1) or "").strip()
        if not name:
            continue
        key = _normalise_key(name)
        if key in seen:
            continue
        seen.add(key)
        names.append(name)
    return names


def _write_search_index(repo_root: Path, docs_dir: Path, generated_at: str) -> None:
    bulletins_dir = docs_dir / "bulletins"
    display_to_key = _load_display_to_key_map(repo_root)
    documents: list[dict[str, str]] = []
    for viewer_path in sorted(bulletins_dir.glob("*.html")):
        if viewer_path.name == "index.html":
            continue
        match = VIEWER_FILE_PATTERN.match(viewer_path.name)
        if not match:
            continue
        ocr_slug, bulletin_date = match.groups()
        diocese = "derry_diocese" if ocr_slug == "derry" else "down_and_connor"
        viewer_html = viewer_path.read_text(encoding="utf-8")
        ocr_text = _extract_ocr_text(viewer_html)
        if not ocr_text:
            continue
        snippet = ocr_text[:MAX_SEARCH_DOC_TEXT]
        parish_names = _extract_parish_names(viewer_html)
        if not parish_names:
            parish_names = [DIOCESES[ocr_slug].display_name]
        for parish_name in parish_names:
            parish_key = display_to_key.get(_normalise_key(parish_name), _normalise_key(parish_name))
            documents.append(
                {
                    "id": f"{diocese}-{bulletin_date}-{parish_key}",
                    "parish": parish_name,
                    "diocese": diocese,
                    "date": bulletin_date,
                    "viewer_url": f"{PAGES_BASE_URL}/bulletins/{viewer_path.name}#{parish_key}",
                    "text": snippet,
                }
            )

    documents.sort(key=lambda item: str(item.get("date") or ""), reverse=True)
    original_count = len(documents)
    payload = {"generated_at": generated_at, "documents": documents}
    encoded = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    while len(encoded) > MAX_SEARCH_INDEX_BYTES and documents:
        documents.pop()
        payload["documents"] = documents
        encoded = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    if len(encoded) > MAX_SEARCH_INDEX_BYTES:
        print("Warning: docs/search-index.json exceeded 5MB and no documents could be retained.")
    elif len(documents) < original_count:
        print("Warning: docs/search-index.json exceeded 5MB; dropped oldest documents.")
    _write_atomic_json(docs_dir / "search-index.json", payload)


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


# ---------------------------------------------------------------------------
# ICS calendar generation (RFC 5545)
# ---------------------------------------------------------------------------

def _ics_escape(value: str) -> str:
    """Escape text values per RFC 5545 §3.3.11."""
    return (
        (value or "")
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
        .replace("\r", "")
    )


def _slugify(value: str) -> str:
    """Return a URL/UID-safe lowercase slug."""
    nfkd = unicodedata.normalize("NFKD", value.lower())
    ascii_str = nfkd.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", ascii_str).strip("-")[:40]


def _event_to_vevent(event: dict, parish_key: str, dtstamp: str) -> list[str]:
    """Convert an event dict to VEVENT lines."""
    date_iso = event.get("date_iso", "")
    try:
        datetime.strptime(date_iso, "%Y-%m-%d")
    except ValueError:
        return []

    title = str(event.get("title") or "")
    uid = f"{parish_key}-{date_iso}-{_slugify(title)}@parish_harvester"
    dtstart = date_iso.replace("-", "")  # YYYYMMDD

    time_val = event.get("time_24h_or_null")
    if time_val:
        # Parse HH:MM, zero-pad each component, produce HHMMSS for iCalendar DTSTART
        parts = str(time_val).split(":")
        hh = parts[0].zfill(2) if parts else "00"
        mm = parts[1].zfill(2) if len(parts) > 1 else "00"
        dtstart_str = f"DTSTART:{dtstart}T{hh}{mm}00"
    else:
        dtstart_str = f"DTSTART;VALUE=DATE:{dtstart}"

    lines = [
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{dtstamp}",
        dtstart_str,
        f"SUMMARY:{_ics_escape(title)}",
    ]
    loc = event.get("location_or_null")
    if loc:
        lines.append(f"LOCATION:{_ics_escape(str(loc))}")
    desc = event.get("description")
    if desc:
        lines.append(f"DESCRIPTION:{_ics_escape(str(desc))}")
    cat = event.get("category")
    if cat:
        lines.append(f"CATEGORIES:{_ics_escape(str(cat).upper())}")
    lines.append("END:VEVENT")
    return lines


def _write_ics_calendars(docs_dir: Path, events_dir: Path, generated_at: datetime) -> None:
    """Write per-diocese and combined .ics calendar files.

    Parameters
    ----------
    docs_dir:
        Destination: writes to ``docs_dir/calendars/<diocese>.ics`` and
        ``docs_dir/calendars/all.ics``.
    events_dir:
        Source: ``events_dir/<diocese>/<parish_key>.json``.
    generated_at:
        UTC datetime used for DTSTAMP.
    """
    calendars_dir = docs_dir / "calendars"
    calendars_dir.mkdir(parents=True, exist_ok=True)

    dtstamp = generated_at.strftime("%Y%m%dT%H%M%SZ")
    all_vevents: list[str] = []

    if events_dir.is_dir():
        diocese_dirs = sorted(d for d in events_dir.iterdir() if d.is_dir())
    else:
        diocese_dirs = []

    for diocese_dir in diocese_dirs:
        diocese_key = diocese_dir.name
        vevents: list[str] = []
        for json_file in sorted(diocese_dir.glob("*.json")):
            try:
                payload = json.loads(json_file.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                continue
            parish_key = str(payload.get("parish_key") or json_file.stem)
            for event in payload.get("events") or []:
                lines = _event_to_vevent(event, parish_key, dtstamp)
                if lines:
                    vevents.extend(lines)

        cal_lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            f"PRODID:-//parish_harvester//{diocese_key}//EN",
            f"X-WR-CALNAME:{diocese_key.replace('_', ' ').title()} Parish Events",
            "CALSCALE:GREGORIAN",
            "METHOD:PUBLISH",
        ] + vevents + ["END:VCALENDAR"]

        ics_path = calendars_dir / f"{diocese_key}.ics"
        ics_path.write_text("\r\n".join(cal_lines) + "\r\n", encoding="utf-8")
        all_vevents.extend(vevents)

    all_cal_lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//parish_harvester//all//EN",
        "X-WR-CALNAME:All Parishes Events",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
    ] + all_vevents + ["END:VCALENDAR"]

    (calendars_dir / "all.ics").write_text(
        "\r\n".join(all_cal_lines) + "\r\n", encoding="utf-8"
    )


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
    _write_search_index(repo_root, docs_dir, generated_at)
    _write_ics_calendars(docs_dir, repo_root / "Bulletins" / "events", generated_at_dt)
