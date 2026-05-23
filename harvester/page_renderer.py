from __future__ import annotations

import html
from datetime import UTC, datetime
from pathlib import Path
from string import Template

TEMPLATE_PATH = Path(__file__).resolve().parent / "templates" / "diocese_page.html"
ISSUES_URL = "https://github.com/Frankytyrone/parish_harvester/issues/new"
EMPTY_OCR_TEXT = "We're still collecting OCR text for this diocese. Check back next Sunday."


def _render_parish_links(parish_links: list[dict]) -> str:
    if not parish_links:
        return '<p class="empty-state">No parish links available yet.</p>'

    items: list[str] = []
    for link in sorted(parish_links, key=lambda item: str(item.get("name") or "").lower()):
        name = html.escape(str(link.get("name") or "Unnamed Parish"))
        url = html.escape(str(link.get("url") or "#"), quote=True)
        items.append(f'<li><a href="{url}" target="_blank" rel="noopener noreferrer">{name}</a></li>')
    return f'<ul class="parish-list">{"".join(items)}</ul>'


def render_diocese_page(
    diocese_key: str,
    diocese_display_name: str,
    mega_pdf_url: str,
    ocr_text: str,
    parish_links: list[dict],
    out_path: Path,
) -> None:
    template = Template(TEMPLATE_PATH.read_text(encoding="utf-8"))
    display = str(diocese_display_name or diocese_key).strip() or diocese_key
    normalized_ocr = (ocr_text or "").strip() or EMPTY_OCR_TEXT

    payload = {
        "page_title": html.escape(f"{display} Diocese Big Bulletin"),
        "diocese_display_name": html.escape(display),
        "headline": html.escape(f"{display.upper()} DIOCESE BIG BULLETIN"),
        "mega_pdf_url": html.escape(mega_pdf_url, quote=True),
        "ocr_text": html.escape(normalized_ocr),
        "parish_heading": html.escape(f"{display.upper()} PARISHES WITH WORKING BULLETIN LINKS"),
        "parish_links_html": _render_parish_links(parish_links),
        "year": str(datetime.now(UTC).year),
        "issues_url": html.escape(ISSUES_URL, quote=True),
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(template.safe_substitute(payload), encoding="utf-8")
