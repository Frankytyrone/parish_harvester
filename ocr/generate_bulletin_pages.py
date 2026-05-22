from __future__ import annotations

import argparse
import json
import html
import os
import re
import time
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from PyPDF2 import PdfReader

from harvester.ai_summaries import summarise_bulletin
from harvester.weekly_diff import diff_bulletins

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = REPO_ROOT / "docs"
BULLETINS_DIR = DOCS_DIR / "bulletins"
BULLETINS_DATA_DIR = REPO_ROOT / "Bulletins"
SUMMARIES_DIR = BULLETINS_DATA_DIR / "summaries"
DIFFS_DIR = BULLETINS_DATA_DIR / "diffs"
CONTACTS_PATH_BY_DIOCESE = {
    "derry": REPO_ROOT / "parishes" / "derry_diocese_contacts.json",
    "down_and_connor": REPO_ROOT / "parishes" / "down_and_connor_contacts.json",
}

HEADER_PATTERN = re.compile(r"^#\s*---\s*(.*?)\s*---\s*$")
OCR_BODY_PATTERN = re.compile(r'<div class="scrollable-viewer">\s*(.*?)\s*</div>\s*</body>', re.DOTALL | re.IGNORECASE)
OCR_PAGE_HEADING_PATTERN = re.compile(r"<h2>\s*Page\s+(\d+)\s*</h2>", re.IGNORECASE)
VIEWER_FILE_PATTERN = re.compile(r"^(derry|down_and_connor)-(\d{4}-\d{2}-\d{2})\.html$")
OCR_PANEL_PATTERN = re.compile(
    r'<div id="ocr-panel">\s*(.*?)\s*</div>\s*<div class="note-box">',
    re.DOTALL | re.IGNORECASE,
)
HTML_TAG_PATTERN = re.compile(r"<[^>]+>")
WHITESPACE_PATTERN = re.compile(r"\s+")
TEAL = "#1a6b6b"
TEXT = "#1a1a2e"
ACCENT = "#c0392b"
FOOTER = "#114b4b"


@dataclass(frozen=True)
class DioceseConfig:
    key: str
    display_name: str
    headline: str
    evidence_path: Path
    pdf_filename: str


@dataclass(frozen=True)
class ViewerEntry:
    diocese: str
    date: str
    path: Path


DIOCESES = {
    "derry": DioceseConfig(
        key="derry",
        display_name="Derry Diocese",
        headline="DERRY DIOCESE BIG BULLETIN",
        evidence_path=REPO_ROOT / "parishes" / "derry_diocese_bulletin_urls.txt",
        pdf_filename="derry_mega_bulletin.pdf",
    ),
    "down_and_connor": DioceseConfig(
        key="down_and_connor",
        display_name="Down & Connor Diocese",
        headline="DOWN & CONNOR DIOCESE BIG BULLETIN",
        evidence_path=REPO_ROOT / "parishes" / "down_and_connor_bulletin_urls.txt",
        pdf_filename="down_and_connor_mega_bulletin.pdf",
    ),
}


def parse_parish_links(path: Path) -> list[tuple[str, str]]:
    parish_links: list[tuple[str, str]] = []
    current_name: str | None = None
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        header = HEADER_PATTERN.match(line)
        if header:
            current_name = header.group(1).strip()
            continue
        if not line or line.startswith("#"):
            continue
        if current_name:
            parish_links.append((current_name, line))
            current_name = None
    return parish_links


def extract_ocr_fragment(path: Path) -> str:
    raw_html = path.read_text(encoding="utf-8")
    match = OCR_BODY_PATTERN.search(raw_html)
    if not match:
        raise ValueError(f"Could not find OCR content wrapper in {path}")
    fragment = OCR_PAGE_HEADING_PATTERN.sub(r"<h3>PAGE \1</h3>", match.group(1).strip())
    return fragment


def count_pdf_pages(path: Path) -> int:
    return len(PdfReader(str(path)).pages)


def _normalise_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (value or "").lower())


def _load_parish_entries(diocese: str, parish_links: list[tuple[str, str]]) -> list[tuple[str, str]]:
    contacts_path = CONTACTS_PATH_BY_DIOCESE.get(diocese)
    display_to_key: dict[str, str] = {}
    if contacts_path and contacts_path.exists():
        try:
            payload = json.loads(contacts_path.read_text(encoding="utf-8"))
        except Exception:
            payload = {}
        if isinstance(payload, dict):
            for key, value in payload.items():
                parish_key = str(key).strip()
                if not parish_key:
                    continue
                display_to_key[_normalise_name(parish_key)] = parish_key
                if isinstance(value, dict):
                    display_name = str(value.get("display_name") or "").strip()
                    if display_name:
                        display_to_key[_normalise_name(display_name)] = parish_key
                        if display_name.lower().endswith(" parish"):
                            display_to_key[_normalise_name(display_name[:-7])] = parish_key
    entries: list[tuple[str, str]] = []
    seen: set[str] = set()
    for name, _ in parish_links:
        normalized = _normalise_name(name)
        parish_key = display_to_key.get(normalized) or normalized
        if not parish_key or parish_key in seen:
            continue
        seen.add(parish_key)
        entries.append((parish_key, name))
    return entries


def _fragment_to_plain_text(ocr_fragment: str) -> str:
    text = html.unescape(HTML_TAG_PATTERN.sub("\n", ocr_fragment))
    lines = [WHITESPACE_PATTERN.sub(" ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def _read_viewer_plain_text(path: Path) -> str:
    raw_html = path.read_text(encoding="utf-8")
    match = OCR_PANEL_PATTERN.search(raw_html)
    if not match:
        return ""
    return _fragment_to_plain_text(match.group(1))


def _find_previous_viewer_path(diocese: str, bulletin_date: str) -> Path | None:
    try:
        current_date = date.fromisoformat(bulletin_date)
    except ValueError:
        return None
    target = current_date - timedelta(days=7)
    for day_offset in [0, -1, 1, -2, 2, -3, 3]:
        candidate_date = target + timedelta(days=day_offset)
        if candidate_date == current_date:
            continue
        candidate_path = BULLETINS_DIR / f"{diocese}-{candidate_date.isoformat()}.html"
        if candidate_path.exists():
            return candidate_path
    return None


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _write_parish_reader_outputs(
    diocese: str,
    bulletin_date: str,
    ocr_text: str,
    parish_links: list[tuple[str, str]],
) -> None:
    parish_entries = _load_parish_entries(diocese, parish_links)
    if not parish_entries:
        return

    previous_viewer_path = _find_previous_viewer_path(diocese, bulletin_date)
    if previous_viewer_path:
        previous_text = _read_viewer_plain_text(previous_viewer_path)
        prior_missing = False
    else:
        previous_text = ""
        prior_missing = True

    summaries_disabled = os.getenv("PARISH_AI_SUMMARIES_DISABLE", "").strip() == "1"
    if summaries_disabled:
        print("AI bulletin summaries disabled via PARISH_AI_SUMMARIES_DISABLE=1")

    mistral_api_key = os.getenv("MISTRAL_API_KEY")
    for idx, (parish_key, parish_name) in enumerate(parish_entries):
        if summaries_disabled:
            summary_payload = {"bullets": None, "error": "ai_summaries_disabled"}
        else:
            if idx > 0:
                time.sleep(0.5)
            summary_result = summarise_bulletin(ocr_text, parish_name, mistral_api_key)
            if summary_result is None:
                error_reason = "missing_mistral_api_key" if not (mistral_api_key or "").strip() else "summary_generation_failed"
                summary_payload = {"bullets": None, "error": error_reason}
            else:
                summary_payload = summary_result

        _write_json(SUMMARIES_DIR / f"{parish_key}.json", summary_payload)

        if prior_missing:
            diff_payload = {
                "added_lines": [],
                "removed_lines": [],
                "kept_count": 0,
                "note": "no_prior_bulletin_found",
            }
        else:
            diff_payload = diff_bulletins(ocr_text, previous_text)
        _write_json(DIFFS_DIR / f"{parish_key}.json", diff_payload)


def _render_parish_links(parish_links: list[tuple[str, str]]) -> str:
    if not parish_links:
        return '<p class="empty-state">No parish bulletin links were found for this diocese yet.</p>'
    sorted_links = sorted(parish_links, key=lambda pair: pair[0].lower())
    items = []
    for name, url in sorted_links:
        items.append(
            (
                "<li class=\"parish-item\" data-name=\"{name_key}\">"
                "<a class=\"parish-link\" href=\"{url}\" target=\"_blank\" rel=\"noopener noreferrer\">"
                "<span aria-hidden=\"true\">⛪</span> <span>{name}</span></a></li>"
            ).format(
                name_key=html.escape(name.lower(), quote=True),
                url=html.escape(url, quote=True),
                name=html.escape(name),
            )
        )
    return (
        '<div id="parish-empty" class="empty-state" hidden>No matching parishes found.</div>'
        '<ul id="parish-grid" class="parish-grid">{items}</ul>'
    ).format(items="".join(items))


def _diocese_label(display_name: str) -> str:
    return display_name.replace(" Diocese", "").upper()


def format_uk_date(iso_date: str) -> str:
    match = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", str(iso_date or "").strip())
    if not match:
        return str(iso_date or "").strip()
    return f"{match.group(3)}/{match.group(2)}/{match.group(1)}"


def render_viewer_page(config: DioceseConfig, bulletin_date: str, page_count: int, ocr_fragment: str, parish_links: list[tuple[str, str]]) -> str:
    pdf_href = f"../mega_pdf/{config.pdf_filename}"
    archive_href = "index.html"
    diocese_label = _diocese_label(config.display_name)
    uk_bulletin_date = format_uk_date(bulletin_date)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{html.escape(config.display_name)} Bulletin Viewer — {html.escape(uk_bulletin_date)}</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Segoe UI", Arial, Helvetica, sans-serif;
      background: #f8f9fa;
      color: {TEXT};
      line-height: 1.8;
      font-size: 17px;
    }}
    a {{ color: {TEAL}; }}
    a:focus-visible, button:focus-visible, input:focus-visible {{
      outline: 3px solid #0f5e5e;
      outline-offset: 2px;
    }}
    .page {{ max-width: 1500px; margin: 0 auto; padding: 24px 20px 40px; }}
    .back-link {{ display: inline-block; margin-bottom: 12px; font-weight: 700; text-decoration: none; }}
    .header {{ text-align: center; margin-bottom: 20px; }}
    .diocese-label {{ margin: 0; color: {ACCENT}; font-size: 1rem; letter-spacing: 0.18em; text-transform: uppercase; font-weight: 800; }}
    h1 {{ margin: 8px 0 8px; color: {TEAL}; font-size: clamp(2rem, 3.4vw, 2.9rem); letter-spacing: 0.03em; }}
    .meta {{ color: #616876; margin: 0 0 18px; }}
    .search-wrap {{ position: relative; margin: 0 auto 16px; max-width: 1100px; }}
    .search-input {{
      width: 100%;
      border: 1px solid #bdd7d5;
      border-radius: 999px;
      min-height: 52px;
      padding: 12px 48px 12px 18px;
      font-size: 1rem;
      line-height: 1.4;
      background: #ffffff;
      color: {TEXT};
    }}
    .search-clear {{
      position: absolute;
      right: 12px;
      top: 50%;
      transform: translateY(-50%);
      width: 36px;
      height: 36px;
      border: 0;
      border-radius: 999px;
      background: transparent;
      color: #5f6573;
      font-size: 1.2rem;
      cursor: pointer;
    }}
    .search-clear[hidden] {{ display: none; }}
    .pill-button {{
      min-height: 44px;
      border-radius: 999px;
      padding: 10px 18px;
      font-weight: 700;
      text-decoration: none;
      display: inline-flex;
      align-items: center;
      justify-content: center;
    }}
    .pill-button.primary {{ background: {TEAL}; color: #fff; border: 1px solid {TEAL}; }}
    .pill-button.secondary {{ background: #fff; color: {TEAL}; border: 2px solid {TEAL}; }}
    .panel-tools {{
      display: flex;
      justify-content: flex-end;
      margin-bottom: 8px;
    }}
    .panel-tools .pill-button {{ min-height: 36px; padding: 7px 14px; font-size: 0.9rem; }}
    .ocr-search-tools {{
      display: flex;
      align-items: center;
      justify-content: flex-end;
      gap: 8px;
      margin-bottom: 10px;
      flex-wrap: wrap;
    }}
    .ocr-search-tools button {{
      border: 0;
      border-radius: 999px;
      background: {TEAL};
      color: #fff;
      font-weight: 700;
      min-height: 34px;
      padding: 6px 12px;
      cursor: pointer;
    }}
    .ocr-search-tools button:disabled {{ background: #9bbfbd; cursor: not-allowed; }}
    .match-count {{
      color: #4b5563;
      font-size: 0.92rem;
      min-width: 86px;
      text-align: right;
    }}
    .viewer-grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 22px; align-items: start; }}
    .column-title {{ margin: 0 0 12px; color: {TEAL}; font-size: 1rem; font-weight: 800; letter-spacing: 0.08em; text-transform: uppercase; text-align: center; }}
    .panel {{ background: #fff; border: 1px solid #d6ecea; border-radius: 18px; padding: 18px; box-shadow: 0 12px 30px rgba(26, 107, 107, 0.08); }}
    .pdf-controls {{
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 12px;
      margin: 8px 0;
      font-weight: 700;
      color: #2b3a4a;
      text-align: center;
      flex-wrap: wrap;
    }}
    .pdf-controls button {{
      border: 0;
      border-radius: 999px;
      background: {TEAL};
      color: #fff;
      font-weight: 700;
      min-height: 44px;
      padding: 10px 18px;
      cursor: pointer;
    }}
    .pdf-controls button:disabled {{ background: #9bbfbd; cursor: not-allowed; }}
    .pdf-canvas-wrap {{
      height: 75vh;
      min-height: 420px;
      overflow: auto;
      border: 1px solid #c7dcda;
      border-radius: 12px;
      background: #f2f5f5;
      display: flex;
      justify-content: center;
      align-items: flex-start;
      padding: 8px;
    }}
    #pdf-canvas {{ display: block; background: #fff; box-shadow: 0 6px 16px rgba(0,0,0,0.15); }}
    #ocr-panel {{
      height: 75vh;
      min-height: 420px;
      overflow-y: auto;
      border: 1px solid #d9e4e3;
      border-radius: 12px;
      padding: 22px;
      background: #fff;
      font-size: 18px;
      line-height: 1.9;
      color: {TEXT};
      scroll-behavior: smooth;
    }}
    #ocr-panel h3, #ocr-panel .ocr-page-heading {{
      color: {TEAL};
      margin-top: 0;
      margin-bottom: 12px;
      font-size: 1.05rem;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }}
    #ocr-panel hr {{ border: 0; border-top: 1px solid #d4dfde; margin: 22px 0; }}
    #ocr-panel p {{ margin: 0 0 10px; white-space: pre-wrap; }}
    #ocr-panel mark {{ background: #fff59d; padding: 0 2px; }}
    .note-box {{ margin-top: 16px; padding: 14px 16px; border-radius: 14px; background: #fff4df; border: 1px solid #f5d08d; color: #704d0f; font-weight: 600; }}
    .parish-section {{ margin-top: 28px; background: #fff; border: 1px solid #d6ecea; border-radius: 18px; padding: 22px; box-shadow: 0 12px 30px rgba(26, 107, 107, 0.06); }}
    .parish-section h2 {{ margin: 0 0 16px; color: {TEAL}; font-size: 1.3rem; font-weight: 800; letter-spacing: 0.05em; text-transform: uppercase; text-align: center; }}
    .parish-filter {{ width: 100%; border: 1px solid #bdd7d5; border-radius: 10px; min-height: 48px; font-size: 1rem; padding: 10px 12px; margin-bottom: 14px; }}
    ul.parish-grid {{ list-style: none; display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px 14px; padding: 0; margin: 0; }}
    .parish-item {{ margin: 0; }}
    .parish-link {{
      min-height: 44px;
      display: flex;
      align-items: center;
      gap: 8px;
      text-decoration: none;
      color: {TEAL};
      font-size: 18px;
      font-weight: 700;
      background: #f9fcfc;
      border: 1px solid #d9ecea;
      border-radius: 10px;
      padding: 8px 12px;
    }}
    .parish-link:hover {{ text-decoration: underline; }}
    .empty-state {{ margin: 0 0 12px; color: #6b7280; }}
    footer {{
      margin-top: 26px;
      background: {FOOTER};
      color: #fff;
      padding: 14px 20px;
    }}
    .footer-inner {{
      max-width: 1500px;
      margin: 0 auto;
      display: flex;
      justify-content: space-between;
      gap: 12px;
      flex-wrap: wrap;
      font-size: 0.95rem;
    }}
    .footer-inner a {{ color: #d8f0ee; text-decoration: none; font-weight: 700; }}
    .footer-inner a:hover {{ text-decoration: underline; }}
    @media (max-width: 1100px) {{
      .viewer-grid {{ grid-template-columns: 1fr; }}
      ul.parish-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
    }}
    @media (max-width: 720px) {{
      .page {{ padding: 20px 14px 36px; }}
      ul.parish-grid {{ grid-template-columns: 1fr; }}
      .pdf-controls {{ flex-wrap: wrap; }}
    }}
  </style>
</head>
<body>
  <div class="page">
    <a class="back-link" href="{archive_href}">← Back to bulletin archive</a>
    <header class="header">
      <p class="diocese-label">{html.escape(diocese_label)}</p>
      <h1>{html.escape(config.headline)}</h1>
      <p class="meta">Generated for {html.escape(uk_bulletin_date)}.</p>
    </header>
    <div class="search-wrap">
      <input id="ocr-search" class="search-input" type="search" placeholder="🔍 Search OCR text..." aria-label="Search OCR text" />
      <button id="clear-search" class="search-clear" type="button" aria-label="Clear OCR search" hidden>×</button>
    </div>

    <div class="viewer-grid">
      <section>
        <h2 class="column-title">Bulletins Original PDF Version</h2>
        <div class="panel">
          <div class="panel-tools">
            <a class="pill-button secondary" href="{pdf_href}" target="_blank" rel="noopener noreferrer">⬇ Download PDF</a>
          </div>
          <div class="pdf-controls" data-controls="top">
            <button data-action="prev" type="button">← Previous</button>
            <span data-role="page-indicator">Page 1 of {page_count}</span>
            <button data-action="next" type="button">Next →</button>
          </div>
          <div id="pdf-canvas-wrap" class="pdf-canvas-wrap">
            <canvas id="pdf-canvas" title="{html.escape(config.display_name)} mega bulletin PDF"></canvas>
          </div>
          <div class="pdf-controls" data-controls="bottom">
            <button data-action="prev" type="button">← Previous</button>
            <span data-role="page-indicator">Page 1 of {page_count}</span>
            <button data-action="next" type="button">Next →</button>
          </div>
        </div>
      </section>

      <section>
        <h2 class="column-title">Bulletins OCR Extracted Plain Text</h2>
        <div class="panel">
          <div class="ocr-search-tools">
            <span id="ocr-match-count" class="match-count">0 matches</span>
            <button id="ocr-prev" type="button" disabled>← Prev</button>
            <button id="ocr-next" type="button" disabled>Next →</button>
          </div>
          <div id="ocr-panel">{ocr_fragment}</div>
          <div class="note-box">Note: The plain-text OCR version is auto-generated and may contain errors so it is always best to double check with the original PDF.</div>
        </div>
      </section>
    </div>

    <section class="parish-section">
      <h2>{html.escape(diocese_label)} Parishes with Working Bulletin Links</h2>
      <input id="parish-filter" class="parish-filter" type="search" placeholder="Filter parishes..." aria-label="Filter parishes" />
      {_render_parish_links(parish_links)}
    </section>
  </div>
  <footer>
    <div class="footer-inner">
      <span>© 2026 Parish Bulletin Harvester</span>
      <a href="https://github.com/Frankytyrone/parish_harvester" target="_blank" rel="noopener noreferrer">GitHub Repository</a>
    </div>
  </footer>

  <script src="https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js"></script>
  <script>
    (function () {{
      const pdfHref = {pdf_href!r};
      const initialPages = {page_count};
      const canvas = document.getElementById('pdf-canvas');
      const canvasWrap = document.getElementById('pdf-canvas-wrap');
      const context = canvas.getContext('2d');
      const ocrPanel = document.getElementById('ocr-panel');
      const indicators = Array.from(document.querySelectorAll('[data-role="page-indicator"]'));
      const prevButtons = Array.from(document.querySelectorAll('button[data-action="prev"]'));
      const nextButtons = Array.from(document.querySelectorAll('button[data-action="next"]'));
      const ocrSearch = document.getElementById('ocr-search');
      const clearSearch = document.getElementById('clear-search');
      const matchCount = document.getElementById('ocr-match-count');
      const prevMatchBtn = document.getElementById('ocr-prev');
      const nextMatchBtn = document.getElementById('ocr-next');
      const parishFilter = document.getElementById('parish-filter');
      const parishItems = Array.from(document.querySelectorAll('.parish-item'));
      const parishEmpty = document.getElementById('parish-empty');
      const originalOcrHtml = ocrPanel.innerHTML;
      const pdfjs = window['pdfjs-dist/build/pdf'] || window.pdfjsLib;
      let currentPage = 1;
      let totalPages = initialPages;
      let pdfDoc = null;
      let isRendering = false;
      let pendingPage = null;
      let ocrMatches = [];
      let currentMatchIndex = -1;

      if (!pdfjs) {{
        return;
      }}

      pdfjs.GlobalWorkerOptions.workerSrc = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';

      function escapeRegExp(text) {{
        const specials = new Set(['\\\\', '^', '$', '.', '|', '?', '*', '+', '(', ')', '[', ']', '{{', '}}']);
        return Array.from(text).map((ch) => specials.has(ch) ? `\\\\${{ch}}` : ch).join('');
      }}

      function updateControls() {{
        indicators.forEach((indicator) => {{
          indicator.textContent = `Page ${{currentPage}} of ${{totalPages}}`;
        }});
        prevButtons.forEach((button) => {{
          button.disabled = currentPage <= 1 || !pdfDoc;
        }});
        nextButtons.forEach((button) => {{
          button.disabled = currentPage >= totalPages || !pdfDoc;
        }});
      }}

      function syncOcrToPage(pageNumber) {{
        const pageAnchor = document.getElementById(`ocr-page-${{pageNumber}}`);
        const headingAnchor = document.querySelector(`#ocr-panel h3#ocr-page-${{pageNumber}}`);
        const textHeading = Array.from(document.querySelectorAll('#ocr-panel h3')).find((heading) => {{
          return heading.textContent.trim().toUpperCase() === `PAGE ${{pageNumber}}`;
        }});
        const target = pageAnchor || headingAnchor || textHeading;
        if (target) {{
          target.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
        }}
      }}

      function queueRender(pageNumber) {{
        if (isRendering) {{
          pendingPage = pageNumber;
          return;
        }}
        renderPage(pageNumber);
      }}

      async function renderPage(pageNumber) {{
        if (!pdfDoc) {{
          return;
        }}
        isRendering = true;
        currentPage = pageNumber;
        updateControls();
        const page = await pdfDoc.getPage(pageNumber);
        const viewport = page.getViewport({{ scale: 1 }});
        const availableWidth = Math.max(canvasWrap.clientWidth - 16, 100);
        const scale = availableWidth / viewport.width;
        const scaledViewport = page.getViewport({{ scale }});
        canvas.width = Math.floor(scaledViewport.width);
        canvas.height = Math.floor(scaledViewport.height);
        canvas.style.width = '100%';
        canvas.style.height = 'auto';
        await page.render({{
          canvasContext: context,
          viewport: scaledViewport,
        }}).promise;
        syncOcrToPage(pageNumber);
        isRendering = false;
        if (pendingPage !== null) {{
          const queued = pendingPage;
          pendingPage = null;
          queueRender(queued);
        }}
      }}

      function goToPage(nextPage) {{
        if (!pdfDoc) {{
          return;
        }}
        const clamped = Math.min(Math.max(nextPage, 1), totalPages);
        if (clamped === currentPage && !isRendering) {{
          return;
        }}
        queueRender(clamped);
      }}

      prevButtons.forEach((button) => {{
        button.addEventListener('click', function () {{
          goToPage(currentPage - 1);
        }});
      }});
      nextButtons.forEach((button) => {{
        button.addEventListener('click', function () {{
          goToPage(currentPage + 1);
        }});
      }});

      new ResizeObserver(function () {{
        if (pdfDoc) {{
          queueRender(currentPage);
        }}
      }}).observe(canvasWrap);

      pdfjs.getDocument(pdfHref).promise.then(function (doc) {{
        pdfDoc = doc;
        totalPages = doc.numPages || initialPages;
        updateControls();
        queueRender(currentPage);
      }}).catch(function () {{
        updateControls();
      }});

      function scrollToMatch(idx) {{
        if (!ocrMatches.length || idx < 0 || idx >= ocrMatches.length) return;
        ocrMatches.forEach((mark) => mark.style.outline = '');
        const target = ocrMatches[idx];
        target.style.outline = '2px solid #0f5e5e';
        target.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
      }}

      function updateMatchUi() {{
        if (!matchCount || !prevMatchBtn || !nextMatchBtn) return;
        const total = ocrMatches.length;
        if (!total) {{
          matchCount.textContent = '0 matches';
          prevMatchBtn.disabled = true;
          nextMatchBtn.disabled = true;
          return;
        }}
        matchCount.textContent = `${{currentMatchIndex + 1}} / ${{total}} matches`;
        prevMatchBtn.disabled = false;
        nextMatchBtn.disabled = false;
      }}

      function applyOcrSearch(query) {{
        ocrPanel.innerHTML = originalOcrHtml;
        ocrMatches = [];
        currentMatchIndex = -1;
        if (!query) {{
          clearSearch.hidden = true;
          updateMatchUi();
          return;
        }}
        clearSearch.hidden = false;
        const regex = new RegExp(escapeRegExp(query), 'gi');
        const walker = document.createTreeWalker(ocrPanel, NodeFilter.SHOW_TEXT, null);
        const nodes = [];
        while (walker.nextNode()) {{
          const node = walker.currentNode;
          if (node.parentElement && node.parentElement.tagName !== 'MARK' && node.nodeValue.trim()) {{
            nodes.push(node);
          }}
        }}
        nodes.forEach((node) => {{
          const text = node.nodeValue;
          regex.lastIndex = 0;
          if (!regex.test(text)) {{
            return;
          }}
          regex.lastIndex = 0;
          const fragment = document.createDocumentFragment();
          let lastIndex = 0;
          let match = null;
          while ((match = regex.exec(text)) !== null) {{
            if (match.index > lastIndex) {{
              fragment.appendChild(document.createTextNode(text.slice(lastIndex, match.index)));
            }}
            const mark = document.createElement('mark');
            mark.textContent = match[0];
            fragment.appendChild(mark);
            ocrMatches.push(mark);
            lastIndex = match.index + match[0].length;
          }}
          if (lastIndex < text.length) {{
            fragment.appendChild(document.createTextNode(text.slice(lastIndex)));
          }}
          node.parentNode.replaceChild(fragment, node);
        }});
        if (ocrMatches.length) {{
          currentMatchIndex = 0;
          scrollToMatch(currentMatchIndex);
        }}
        updateMatchUi();
      }}

      ocrSearch.addEventListener('input', function (event) {{
        applyOcrSearch(event.target.value.trim());
      }});
      clearSearch.addEventListener('click', function () {{
        ocrSearch.value = '';
        applyOcrSearch('');
        ocrSearch.focus();
      }});
      prevMatchBtn.addEventListener('click', function () {{
        if (!ocrMatches.length) return;
        currentMatchIndex = (currentMatchIndex - 1 + ocrMatches.length) % ocrMatches.length;
        updateMatchUi();
        scrollToMatch(currentMatchIndex);
      }});
      nextMatchBtn.addEventListener('click', function () {{
        if (!ocrMatches.length) return;
        currentMatchIndex = (currentMatchIndex + 1) % ocrMatches.length;
        updateMatchUi();
        scrollToMatch(currentMatchIndex);
      }});

      parishFilter.addEventListener('input', function (event) {{
        const term = event.target.value.trim().toLowerCase();
        let visibleCount = 0;
        parishItems.forEach((item) => {{
          const matches = item.dataset.name.includes(term);
          item.hidden = !matches;
          if (matches) {{
            visibleCount += 1;
          }}
        }});
        if (parishEmpty) {{
          parishEmpty.hidden = visibleCount !== 0;
        }}
      }});

      updateControls();
      updateMatchUi();
    }})();
  </script>
</body>
</html>
"""


def write_viewer_page(diocese: str, bulletin_date: str, pdf_path: Path, ocr_html_path: Path) -> Path:
    config = DIOCESES[diocese]
    page_count = count_pdf_pages(pdf_path)
    ocr_fragment = extract_ocr_fragment(ocr_html_path)
    ocr_plain_text = _fragment_to_plain_text(ocr_fragment)
    parish_links = parse_parish_links(config.evidence_path)
    output_path = BULLETINS_DIR / f"{diocese}-{bulletin_date}.html"
    output_path.write_text(
        render_viewer_page(config, bulletin_date, page_count, ocr_fragment, parish_links),
        encoding="utf-8",
    )
    _write_parish_reader_outputs(diocese, bulletin_date, ocr_plain_text, parish_links)
    return output_path


def scan_viewer_entries() -> list[ViewerEntry]:
    entries: list[ViewerEntry] = []
    if not BULLETINS_DIR.exists():
        return entries
    for path in BULLETINS_DIR.glob("*.html"):
        if path.name == "index.html":
            continue
        match = VIEWER_FILE_PATTERN.match(path.name)
        if not match:
            continue
        entries.append(ViewerEntry(diocese=match.group(1), date=match.group(2), path=path))
    return sorted(entries, key=lambda entry: (entry.date, entry.diocese), reverse=True)


def write_bulletins_index(entries: list[ViewerEntry]) -> None:
    items = []
    for entry in entries:
        config = DIOCESES[entry.diocese]
        items.append(
            f"<li><a href=\"{entry.path.name}\">{html.escape(config.display_name)} — {html.escape(format_uk_date(entry.date))}</a></li>"
        )
    if not items:
        items.append("<li>No OCR bulletin viewer pages have been generated yet.</li>")
    BULLETINS_DIR.mkdir(parents=True, exist_ok=True)
    (BULLETINS_DIR / "index.html").write_text(
        f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>OCR Bulletin Archive</title>
  <style>
    body {{ margin: 0; font-family: Arial, Helvetica, sans-serif; background: #f7faf9; color: {TEXT}; }}
    .page {{ max-width: 960px; margin: 0 auto; padding: 28px 20px 40px; }}
    h1 {{ margin: 0 0 10px; color: {TEAL}; }}
    p {{ color: #4b5563; }}
    .archive {{ margin-top: 24px; background: #fff; border: 1px solid #d6ecea; border-radius: 16px; padding: 20px; box-shadow: 0 12px 30px rgba(26, 122, 122, 0.06); }}
    ul {{ margin: 0; padding-left: 24px; }}
    li {{ margin: 10px 0; }}
    a {{ color: {TEAL}; font-weight: 700; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
  </style>
</head>
<body>
  <div class="page">
    <a href="../index.html">← Back to dashboard</a>
    <h1>OCR Bulletin Archive</h1>
    <p>Newest generated bulletin viewer pages appear first.</p>
    <div class="archive">
      <ul>{''.join(items)}</ul>
    </div>
  </div>
</body>
</html>
""",
        encoding="utf-8",
    )


def write_root_index(entries: list[ViewerEntry]) -> None:
    latest_by_diocese: dict[str, ViewerEntry] = {}
    cards = []
    for entry in entries:
        if entry.diocese not in latest_by_diocese:
            latest_by_diocese[entry.diocese] = entry
    for diocese in DIOCESES.values():
        latest = latest_by_diocese.get(diocese.key)
        ocr_href = f"bulletins/{latest.path.name}" if latest else "bulletins/index.html"
        ocr_label = format_uk_date(latest.date) if latest else "Archive"
        cards.append(
            f"""
        <article class="card">
          <p class="eyebrow">Mega PDF card</p>
          <h2>{html.escape(diocese.display_name)}</h2>
          <p>Latest OCR viewer: <strong>{html.escape(ocr_label)}</strong></p>
          <div class="actions">
            <a class="button secondary" href="mega_pdf/index.html#{diocese.key}">👁 View Online</a>
            <a class="button primary" href="{ocr_href}">📖 Read OCR Text</a>
            <a class="button secondary" href="mega_pdf/{diocese.pdf_filename}" download>⬇ Download PDF</a>
          </div>
        </article>
            """
        )
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    (DOCS_DIR / "index.html").write_text(
        f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Parish Bulletin Dashboard</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: Arial, Helvetica, sans-serif; background: linear-gradient(180deg, #eff9f8 0%, #f8fbfb 100%); color: {TEXT}; }}
    .hero {{ padding: 44px 20px 24px; background: linear-gradient(135deg, {TEAL} 0%, #114b4b 100%); color: white; }}
    .hero-inner, .content {{ max-width: 1160px; margin: 0 auto; }}
    .hero h1 {{ margin: 0 0 10px; font-size: clamp(2.1rem, 4vw, 3.2rem); }}
    .hero p {{ margin: 0; max-width: 760px; color: rgba(255,255,255,0.88); font-size: 1.05rem; }}
    .content {{ padding: 28px 20px 40px; }}
    .section-title {{ margin: 0 0 16px; color: {TEAL}; font-size: 1.45rem; }}
    .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 20px; }}
    .card {{ background: #fff; border: 1px solid #d6ecea; border-radius: 18px; padding: 22px; box-shadow: 0 14px 34px rgba(26, 122, 122, 0.08); }}
    .eyebrow {{ margin: 0 0 8px; color: #6b7280; text-transform: uppercase; letter-spacing: 0.08em; font-size: 0.8rem; font-weight: 700; }}
    .card h2 {{ margin: 0 0 10px; font-size: 1.45rem; }}
    .card p {{ margin: 0 0 18px; color: #4b5563; }}
    .actions {{ display: flex; flex-wrap: wrap; gap: 10px; }}
    .button {{ display: inline-flex; align-items: center; justify-content: center; padding: 11px 16px; border-radius: 999px; font-weight: 700; text-decoration: none; }}
    .button.primary {{ background: {TEAL}; color: white; }}
    .button.secondary {{ background: #edf7f6; color: {TEAL}; border: 1px solid #cfe8e6; }}
    .archive-card {{ margin-top: 24px; background: #fff; border: 1px solid #d6ecea; border-radius: 18px; padding: 20px; box-shadow: 0 12px 30px rgba(26, 122, 122, 0.06); }}
    .archive-card a {{ color: {TEAL}; font-weight: 700; text-decoration: none; }}
    .archive-card a:hover {{ text-decoration: underline; }}
  </style>
</head>
<body>
  <section class="hero">
    <div class="hero-inner">
      <h1>Parish Bulletin Dashboard</h1>
      <p>Read the latest diocesan mega PDFs, switch to OCR side-by-side viewer pages, and browse the growing bulletin archive published to GitHub Pages.</p>
    </div>
  </section>
  <main class="content">
    <h2 class="section-title">Mega PDF cards</h2>
    <div class="cards">{''.join(cards)}</div>
    <div class="archive-card">
      <p><a href="bulletins/index.html">Browse the full OCR bulletin archive</a></p>
      <p><a href="mega_pdf/index.html">Open the mega PDF tab viewer</a></p>
      <p><a href="search/">Search all bulletins</a></p>
    </div>
  </main>
</body>
</html>
""",
        encoding="utf-8",
    )


def rebuild_indexes() -> None:
    entries = scan_viewer_entries()
    write_bulletins_index(entries)
    write_root_index(entries)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate side-by-side OCR bulletin viewer pages.")
    parser.add_argument("--diocese", choices=sorted(DIOCESES))
    parser.add_argument("--date")
    parser.add_argument("--pdf", type=Path)
    parser.add_argument("--ocr-html", type=Path)
    parser.add_argument("--rebuild-indexes", action="store_true")
    args = parser.parse_args()

    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    BULLETINS_DIR.mkdir(parents=True, exist_ok=True)

    if args.rebuild_indexes:
        rebuild_indexes()
        return

    if not all([args.diocese, args.date, args.pdf, args.ocr_html]):
        parser.error("--diocese, --date, --pdf, and --ocr-html are required unless --rebuild-indexes is used.")

    write_viewer_page(args.diocese, args.date, args.pdf, args.ocr_html)
    rebuild_indexes()


if __name__ == "__main__":
    main()
