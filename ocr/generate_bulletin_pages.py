from __future__ import annotations

import argparse
import html
import re
from dataclasses import dataclass
from pathlib import Path

from PyPDF2 import PdfReader

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = REPO_ROOT / "docs"
BULLETINS_DIR = DOCS_DIR / "bulletins"

HEADER_PATTERN = re.compile(r"^#\s*---\s*(.*?)\s*---\s*$")
OCR_BODY_PATTERN = re.compile(r'<div class="scrollable-viewer">\s*(.*?)\s*</div>\s*</body>', re.DOTALL | re.IGNORECASE)
OCR_PAGE_HEADING_PATTERN = re.compile(r"<h2>\s*Page\s+(\d+)\s*</h2>", re.IGNORECASE)
VIEWER_FILE_PATTERN = re.compile(r"^(derry|down_and_connor)-(\d{4}-\d{2}-\d{2})\.html$")
TEAL = "#1a6b6b"
TEXT = "#1a1a2e"
ORANGE = "#c0392b"


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
    fragment = OCR_PAGE_HEADING_PATTERN.sub(
        r'<hr class="ocr-page-divider"><h3>PAGE \1</h3>',
        match.group(1).strip(),
    )
    return fragment


def count_pdf_pages(path: Path) -> int:
    return len(PdfReader(str(path)).pages)


def _render_parish_links(parish_links: list[tuple[str, str]]) -> str:
    if not parish_links:
        return '<p class="empty-state">No parish bulletin links were found for this diocese yet.</p>'
    items = []
    for name, url in sorted(parish_links, key=lambda parish: parish[0].lower()):
        items.append(
            "<li class=\"parish-item\" data-parish-name=\"{search_name}\"><a href=\"{url}\" target=\"_blank\" rel=\"noopener noreferrer\">⛪ {name}</a></li>".format(
                url=html.escape(url, quote=True),
                name=html.escape(name),
                search_name=html.escape(name.lower(), quote=True),
            )
        )
    return "<ul class=\"parish-grid\">{items}</ul>".format(items="".join(items))


def render_viewer_page(config: DioceseConfig, bulletin_date: str, page_count: int, ocr_fragment: str, parish_links: list[tuple[str, str]]) -> str:
    pdf_href = f"../mega_pdf/{config.pdf_filename}"
    archive_href = "index.html"
    diocese_label = config.display_name.replace(" Diocese", "").upper()
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{html.escape(config.display_name)} Bulletin Viewer — {html.escape(bulletin_date)}</title>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js"></script>
  <style>
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Segoe UI", Arial, Helvetica, sans-serif;
      background: #f8f9fa;
      color: {TEXT};
      font-size: 17px;
      line-height: 1.8;
    }}
    a {{ color: {TEAL}; }}
    a, button, input {{
      outline-offset: 2px;
    }}
    a:focus-visible, button:focus-visible, input:focus-visible {{
      outline: 3px solid #0f4e4e;
    }}
    .page {{ max-width: 1540px; margin: 0 auto; padding: 24px 20px 40px; }}
    .back-link {{ display: inline-block; margin-bottom: 10px; font-weight: 700; text-decoration: none; color: {TEAL}; }}
    .header {{ text-align: center; margin-bottom: 22px; }}
    .diocese-label {{
      margin: 0;
      color: {ORANGE};
      letter-spacing: 0.12em;
      text-transform: uppercase;
      font-variant: small-caps;
      font-weight: 700;
      font-size: 0.92rem;
    }}
    h1 {{ margin: 6px 0 4px; color: {TEAL}; font-size: clamp(2rem, 3.5vw, 3.1rem); line-height: 1.25; }}
    .meta {{ margin: 0 0 14px; color: #5f6772; font-size: 0.96rem; }}
    .search-row {{
      position: relative;
      max-width: 980px;
      margin: 0 auto 12px;
    }}
    #ocr-search {{
      width: 100%;
      height: 52px;
      padding: 0 52px 0 16px;
      border-radius: 999px;
      border: 1px solid #bad5d5;
      font-size: 1.03rem;
      background: #fff;
      color: {TEXT};
    }}
    #clear-search {{
      position: absolute;
      right: 14px;
      top: 50%;
      transform: translateY(-50%);
      border: 0;
      background: transparent;
      color: #3c4c5d;
      font-size: 1.3rem;
      width: 36px;
      height: 36px;
      border-radius: 999px;
      cursor: pointer;
      display: none;
    }}
    .action-row {{
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      margin-bottom: 16px;
    }}
    .pill-button {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-height: 44px;
      padding: 10px 18px;
      border-radius: 999px;
      border: 1px solid {TEAL};
      text-decoration: none;
      font-weight: 700;
      color: {TEAL};
      background: #fff;
    }}
    .pill-button.primary {{
      background: {TEAL};
      color: #fff;
    }}
    .viewer-grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 20px; align-items: start; }}
    .panel {{
      background: #fff;
      border: 1px solid #d3e7e7;
      border-radius: 16px;
      box-shadow: 0 12px 30px rgba(17, 75, 75, 0.08);
      padding: 16px;
    }}
    .column-title {{
      margin: 0 0 10px;
      color: {TEAL};
      text-align: center;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      font-size: 1rem;
      font-weight: 800;
    }}
    .pdf-shell {{
      height: 75vh;
      display: flex;
      flex-direction: column;
      gap: 10px;
    }}
    .pdf-controls {{
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 10px;
      flex-wrap: wrap;
      color: #28414d;
      font-weight: 700;
      font-size: 0.98rem;
      min-height: 44px;
    }}
    .pdf-controls button {{
      min-height: 44px;
      min-width: 118px;
      border: 0;
      border-radius: 999px;
      background: {TEAL};
      color: #fff;
      font-weight: 700;
      padding: 10px 16px;
      cursor: pointer;
    }}
    .pdf-controls button:disabled {{ background: #97b9b9; cursor: not-allowed; }}
    .pdf-canvas-wrap {{
      flex: 1;
      overflow: auto;
      border: 1px solid #c9dddd;
      border-radius: 12px;
      background: #f3f6f7;
      padding: 8px;
    }}
    #pdf-canvas {{
      display: block;
      margin: 0 auto;
      background: #fff;
      max-width: 100%;
      box-shadow: 0 8px 20px rgba(0, 0, 0, 0.12);
    }}
    .ocr-panel {{
      height: 75vh;
      overflow-y: auto;
      border: 1px solid #dbe5e7;
      border-radius: 12px;
      padding: 20px;
      background: #fff;
      font-size: 18px;
      line-height: 1.9;
      color: {TEXT};
    }}
    .ocr-panel h2 {{
      color: {TEAL};
      margin: 0 0 10px;
      font-size: 1.55rem;
      line-height: 1.35;
    }}
    .ocr-panel h3 {{
      color: #0f5a5a;
      margin: 12px 0 10px;
      font-size: 1.28rem;
      line-height: 1.4;
    }}
    .ocr-panel h4 {{ margin: 10px 0 8px; font-size: 1.16rem; line-height: 1.45; }}
    .ocr-panel p {{ margin: 0 0 12px; white-space: pre-wrap; }}
    .ocr-panel a {{ color: {TEAL}; font-weight: 600; }}
    .ocr-page-divider {{ border: 0; border-top: 1px solid rgba(26, 107, 107, 0.45); margin: 24px 0 12px; }}
    .ocr-page-label {{
      margin: 0 0 12px;
      color: {TEAL};
      font-size: 1rem;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      font-weight: 800;
    }}
    .ocr-panel table {{
      width: 100%;
      border-collapse: collapse;
      margin: 0 0 14px;
      font-size: 1rem;
    }}
    .ocr-panel th, .ocr-panel td {{
      border: 1px solid #cddddd;
      padding: 8px 10px;
      text-align: left;
      vertical-align: top;
    }}
    .ocr-panel mark {{ background: #ffef88; color: #1f1f1f; padding: 0 2px; border-radius: 2px; }}
    .note-box {{
      margin-top: 14px;
      padding: 14px 16px;
      border-radius: 12px;
      background: #fff4df;
      border: 1px solid #f0d196;
      color: #704d0f;
      font-weight: 700;
      line-height: 1.6;
    }}
    .parish-section {{
      margin-top: 26px;
      background: #fff;
      border: 1px solid #d3e7e7;
      border-radius: 16px;
      box-shadow: 0 12px 30px rgba(17, 75, 75, 0.08);
      padding: 20px;
    }}
    .parish-section h2 {{
      margin: 0 0 12px;
      color: {TEAL};
      text-align: center;
      font-size: clamp(1.25rem, 2.2vw, 1.8rem);
      line-height: 1.4;
      text-transform: uppercase;
      font-weight: 800;
      letter-spacing: 0.05em;
    }}
    #parish-filter {{
      width: 100%;
      max-width: 440px;
      height: 46px;
      border-radius: 10px;
      border: 1px solid #bfd4d6;
      padding: 0 12px;
      font-size: 1rem;
      margin-bottom: 12px;
    }}
    ul.parish-grid {{
      list-style: none;
      margin: 0;
      padding: 0;
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 10px 18px;
    }}
    .parish-item a {{
      display: flex;
      align-items: center;
      min-height: 44px;
      color: {TEAL};
      font-size: 18px;
      font-weight: 700;
      text-decoration: none;
      line-height: 1.4;
    }}
    .parish-item a:hover {{ text-decoration: underline; }}
    .empty-state {{ margin: 0; color: #6b7280; }}
    .footer {{
      margin-top: 28px;
      background: #114b4b;
      color: #fff;
      padding: 14px 20px;
    }}
    .footer-inner {{
      max-width: 1540px;
      margin: 0 auto;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      font-size: 0.95rem;
    }}
    .footer a {{ color: #fff; display: inline-flex; align-items: center; }}
    @media (max-width: 1100px) {{
      ul.parish-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
    }}
    @media (max-width: 768px) {{
      .viewer-grid {{ grid-template-columns: 1fr; }}
      .pdf-shell, .ocr-panel {{ height: auto; min-height: 60vh; }}
      .page {{ padding: 18px 12px 28px; }}
      ul.parish-grid {{ grid-template-columns: 1fr; }}
      .footer-inner {{ flex-direction: column; align-items: flex-start; }}
    }}
  </style>
</head>
<body>
  <div class="page">
    <a class="back-link" href="{archive_href}">← Back to bulletin archive</a>
    <header class="header">
      <p class="diocese-label">{html.escape(diocese_label)}</p>
      <h1>{html.escape(config.headline)}</h1>
      <p class="meta">Generated for {html.escape(bulletin_date)}</p>
    </header>
    <div class="search-row">
      <input id="ocr-search" type="search" placeholder="🔍 Search OCR text..." aria-label="Search OCR text" />
      <button id="clear-search" type="button" aria-label="Clear OCR search">×</button>
    </div>
    <div class="action-row">
      <a class="pill-button primary" href="{pdf_href}" target="_blank" rel="noopener noreferrer">⬇ Download PDF</a>
      <a class="pill-button" href="#ocr-section">Jump to OCR text</a>
    </div>

    <div class="viewer-grid">
      <section>
        <h2 class="column-title">Bulletins original PDF version</h2>
        <div class="panel">
          <div class="pdf-shell">
            <div class="pdf-controls">
              <button class="prev-page" type="button">← Previous</button>
              <span class="page-indicator">Page 1 of {page_count}</span>
              <button class="next-page" type="button">Next →</button>
            </div>
            <div id="pdf-canvas-wrap" class="pdf-canvas-wrap">
              <canvas id="pdf-canvas" aria-label="{html.escape(config.display_name)} mega bulletin PDF"></canvas>
            </div>
            <div class="pdf-controls">
              <button class="prev-page" type="button">← Previous</button>
              <span class="page-indicator">Page 1 of {page_count}</span>
              <button class="next-page" type="button">Next →</button>
            </div>
          </div>
        </div>
      </section>

      <section id="ocr-section">
        <h2 class="column-title">Bulletins OCR extracted plain text</h2>
        <div class="panel">
          <div id="ocr-panel" class="ocr-panel">{ocr_fragment}</div>
          <div class="note-box">Note: OCR text is auto-generated and may contain errors. Always verify against the original PDF.</div>
        </div>
      </section>
    </div>

    <section class="parish-section">
      <h2>{html.escape(diocese_label)} Parishes with working bulletin links</h2>
      <input id="parish-filter" type="search" placeholder="Filter parishes..." aria-label="Filter parishes" />
      {_render_parish_links(parish_links)}
    </section>
  </div>
  <footer class="footer">
    <div class="footer-inner">
      <span>© 2026 Parish Bulletin Harvester</span>
      <a href="https://github.com/Frankytyrone/parish_harvester" target="_blank" rel="noopener noreferrer" aria-label="Parish Bulletin Harvester GitHub repository">
        <svg aria-hidden="true" width="20" height="20" viewBox="0 0 16 16" fill="currentColor">
          <path d="M8 0C3.58 0 0 3.67 0 8.2c0 3.62 2.29 6.68 5.47 7.77.4.08.55-.18.55-.39 0-.19-.01-.83-.01-1.5-2.01.45-2.53-.51-2.69-.97-.09-.24-.48-.97-.82-1.17-.28-.16-.68-.56-.01-.57.63-.01 1.08.59 1.23.84.72 1.24 1.87.89 2.33.68.07-.54.28-.89.5-1.09-1.78-.21-3.64-.92-3.64-4.11 0-.91.32-1.65.84-2.24-.08-.21-.37-1.06.08-2.21 0 0 .69-.23 2.26.86a7.62 7.62 0 0 1 4.12 0c1.57-1.09 2.26-.86 2.26-.86.45 1.15.16 2 .08 2.21.52.59.84 1.33.84 2.24 0 3.2-1.87 3.89-3.65 4.1.29.26.54.75.54 1.52 0 1.1-.01 1.98-.01 2.25 0 .21.14.47.55.39A8.23 8.23 0 0 0 16 8.2C16 3.67 12.42 0 8 0Z"></path>
        </svg>
      </a>
    </div>
  </footer>

  <script>
    (function () {{
      const workerSrc = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';
      const totalPages = {page_count};
      const pdfHref = {pdf_href!r};
      const prevButtons = Array.from(document.querySelectorAll('.prev-page'));
      const nextButtons = Array.from(document.querySelectorAll('.next-page'));
      const indicators = Array.from(document.querySelectorAll('.page-indicator'));
      const canvasWrap = document.getElementById('pdf-canvas-wrap');
      const canvas = document.getElementById('pdf-canvas');
      const context = canvas.getContext('2d');
      const ocrPanel = document.getElementById('ocr-panel');
      const originalOcrHtml = ocrPanel.innerHTML;
      const searchInput = document.getElementById('ocr-search');
      const clearSearchButton = document.getElementById('clear-search');
      const parishFilterInput = document.getElementById('parish-filter');
      const parishItems = Array.from(document.querySelectorAll('.parish-item'));

      let pdfDoc = null;
      let currentPage = 1;
      let rendering = false;
      let pendingPageRender = false;
      let pageAnchors = new Map();

      function refreshPageAnchors() {{
        pageAnchors = new Map();
        Array.from(ocrPanel.querySelectorAll('h3')).forEach(function (element) {{
          const match = element.textContent ? element.textContent.match(/PAGE\\s+(\\d+)/i) : null;
          if (match) {{
            pageAnchors.set(Number(match[1]), element);
          }}
        }});
      }}

      function updateControls() {{
        indicators.forEach((indicator) => {{
          indicator.textContent = `Page ${{currentPage}} of ${{totalPages}}`;
        }});
        prevButtons.forEach((button) => {{
          button.disabled = currentPage <= 1;
        }});
        nextButtons.forEach((button) => {{
          button.disabled = currentPage >= totalPages;
        }});
      }}

      function syncOcrScroll() {{
        const target = pageAnchors.get(currentPage);
        if (target) {{
          target.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
        }}
      }}

      async function renderPdfPage() {{
        if (!pdfDoc) {{
          return;
        }}
        rendering = true;
        const page = await pdfDoc.getPage(currentPage);
        const unscaledViewport = page.getViewport({{ scale: 1 }});
        const availableWidth = Math.max(canvasWrap.clientWidth - 20, 320);
        const scale = availableWidth / unscaledViewport.width;
        const viewport = page.getViewport({{ scale }});
        canvas.width = Math.floor(viewport.width);
        canvas.height = Math.floor(viewport.height);
        canvas.style.width = `${{Math.floor(viewport.width)}}px`;
        canvas.style.height = `${{Math.floor(viewport.height)}}px`;
        await page.render({{ canvasContext: context, viewport }}).promise;
        rendering = false;
        updateControls();
        syncOcrScroll();
        if (pendingPageRender) {{
          pendingPageRender = false;
          requestRender();
        }}
      }}

      function requestRender() {{
        if (rendering) {{
          pendingPageRender = true;
          return;
        }}
        renderPdfPage().catch(function (error) {{
          console.error('Failed to render PDF page', error);
        }});
      }}

      function escapeRegex(text) {{
        return text.replace(/[.*+?^${{}}()|[\\]\\\\]/g, '\\\\$&');
      }}

      function applyTextHighlights(term) {{
        ocrPanel.innerHTML = originalOcrHtml;
        if (!term) {{
          refreshPageAnchors();
          return;
        }}
        const regex = new RegExp(escapeRegex(term), 'gi');
        const walker = document.createTreeWalker(ocrPanel, NodeFilter.SHOW_TEXT);
        const textNodes = [];
        let node = walker.nextNode();
        while (node) {{
          if (node.nodeValue && node.nodeValue.trim()) {{
            textNodes.push(node);
          }}
          node = walker.nextNode();
        }}
        textNodes.forEach(function (textNode) {{
          const text = textNode.nodeValue;
          if (!regex.test(text)) {{
            regex.lastIndex = 0;
            return;
          }}
          regex.lastIndex = 0;
          const fragment = document.createDocumentFragment();
          let lastIndex = 0;
          let match = regex.exec(text);
          while (match) {{
            fragment.appendChild(document.createTextNode(text.slice(lastIndex, match.index)));
            const mark = document.createElement('mark');
            mark.textContent = match[0];
            fragment.appendChild(mark);
            lastIndex = match.index + match[0].length;
            match = regex.exec(text);
          }}
          fragment.appendChild(document.createTextNode(text.slice(lastIndex)));
          textNode.parentNode.replaceChild(fragment, textNode);
        }});
        refreshPageAnchors();
      }}

      function ensureExternalLinkSafety() {{
        document.querySelectorAll('a[href]').forEach(function (anchor) {{
          const href = anchor.getAttribute('href') || '';
          if (/^(https?:|mailto:|tel:)/i.test(href)) {{
            anchor.setAttribute('target', '_blank');
            anchor.setAttribute('rel', 'noopener noreferrer');
          }}
        }});
      }}

      function handleSearchInput() {{
        const term = searchInput.value.trim();
        clearSearchButton.style.display = term ? 'block' : 'none';
        applyTextHighlights(term);
      }}

      function goToPage(nextPage) {{
        if (nextPage < 1 || nextPage > totalPages || nextPage === currentPage) {{
          return;
        }}
        currentPage = nextPage;
        requestRender();
      }}

      prevButtons.forEach(function (button) {{
        button.addEventListener('click', function () {{
          goToPage(currentPage - 1);
        }});
      }});

      nextButtons.forEach(function (button) {{
        button.addEventListener('click', function () {{
          goToPage(currentPage + 1);
        }});
      }});

      searchInput.addEventListener('input', handleSearchInput);
      clearSearchButton.addEventListener('click', function () {{
        searchInput.value = '';
        handleSearchInput();
        searchInput.focus();
      }});

      parishFilterInput.addEventListener('input', function () {{
        const term = parishFilterInput.value.trim().toLowerCase();
        parishItems.forEach(function (item) {{
          const name = item.getAttribute('data-parish-name') || '';
          item.style.display = !term || name.includes(term) ? '' : 'none';
        }});
      }});

      pdfjsLib.GlobalWorkerOptions.workerSrc = workerSrc;
      pdfjsLib.getDocument(pdfHref).promise.then(function (documentRef) {{
        pdfDoc = documentRef;
        currentPage = Math.min(Math.max(1, currentPage), pdfDoc.numPages || totalPages);
        requestRender();
        new ResizeObserver(function () {{
          requestRender();
        }}).observe(canvasWrap);
      }}).catch(function (error) {{
        console.error('Failed to load PDF', error);
      }});

      refreshPageAnchors();
      ensureExternalLinkSafety();
      updateControls();
    }})();
  </script>
</body>
</html>
"""


def write_viewer_page(diocese: str, bulletin_date: str, pdf_path: Path, ocr_html_path: Path) -> Path:
    config = DIOCESES[diocese]
    page_count = count_pdf_pages(pdf_path)
    ocr_fragment = extract_ocr_fragment(ocr_html_path)
    parish_links = parse_parish_links(config.evidence_path)
    output_path = BULLETINS_DIR / f"{diocese}-{bulletin_date}.html"
    output_path.write_text(
        render_viewer_page(config, bulletin_date, page_count, ocr_fragment, parish_links),
        encoding="utf-8",
    )
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
            f"<li><a href=\"{entry.path.name}\">{html.escape(config.display_name)} — {html.escape(entry.date)}</a></li>"
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
        ocr_label = latest.date if latest else "Archive"
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
