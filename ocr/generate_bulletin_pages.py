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
TEAL = "#1a7a7a"
TEXT = "#163030"


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


def _render_parish_links(parish_links: list[tuple[str, str]]) -> str:
    if not parish_links:
        return '<p class="empty-state">No parish bulletin links were found for this diocese yet.</p>'
    items = []
    for name, url in parish_links:
        items.append(
            "<li><a href=\"{url}\" target=\"_blank\" rel=\"noopener noreferrer\">{name}</a></li>".format(
                url=html.escape(url, quote=True),
                name=html.escape(name),
            )
        )
    return "<ul class=\"parish-grid\">{items}</ul>".format(items="".join(items))


def render_viewer_page(config: DioceseConfig, bulletin_date: str, page_count: int, ocr_fragment: str, parish_links: list[tuple[str, str]]) -> str:
    pdf_href = f"../mega_pdf/{config.pdf_filename}"
    archive_href = "index.html"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{html.escape(config.display_name)} Bulletin Viewer — {html.escape(bulletin_date)}</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Arial, Helvetica, sans-serif;
      background: #f7faf9;
      color: {TEXT};
      line-height: 1.5;
    }}
    a {{ color: {TEAL}; }}
    .page {{ max-width: 1500px; margin: 0 auto; padding: 28px 20px 48px; }}
    .back-link {{ display: inline-block; margin-bottom: 18px; font-weight: 700; text-decoration: none; }}
    h1 {{ margin: 0 0 6px; color: {TEAL}; font-size: clamp(2rem, 3vw, 2.8rem); letter-spacing: 0.02em; }}
    .meta {{ color: #4b5563; margin-bottom: 22px; }}
    .download-link {{ display: inline-flex; align-items: center; gap: 8px; margin-bottom: 18px; font-weight: 700; text-decoration: none; }}
    .viewer-grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 22px; align-items: start; }}
    .column-title {{ margin: 0 0 12px; color: {TEXT}; font-size: 0.98rem; font-weight: 800; letter-spacing: 0.08em; text-transform: uppercase; }}
    .panel {{ background: #fff; border: 1px solid #d6ecea; border-radius: 18px; padding: 18px; box-shadow: 0 12px 30px rgba(26, 122, 122, 0.08); }}
    .pdf-frame {{ width: 100%; height: 70vh; min-height: 680px; border: 1px solid #c7dcda; border-radius: 12px; background: #f2f5f5; }}
    .pdf-controls {{ display: flex; align-items: center; justify-content: center; gap: 12px; margin-top: 12px; font-weight: 700; color: #345; }}
    .pdf-controls button {{ border: 0; border-radius: 999px; background: {TEAL}; color: #fff; font-weight: 700; padding: 10px 18px; cursor: pointer; }}
    .pdf-controls button:disabled {{ background: #9bbfbd; cursor: not-allowed; }}
    details.pro-tip {{ margin-top: 16px; border: 1px solid #d6ecea; border-radius: 14px; background: #eef7f6; overflow: hidden; }}
    details.pro-tip summary {{ list-style: none; cursor: pointer; display: flex; align-items: center; justify-content: space-between; padding: 14px 16px; font-weight: 800; color: {TEXT}; }}
    details.pro-tip summary::-webkit-details-marker {{ display: none; }}
    .pro-tip-body {{ padding: 0 16px 16px; color: #36505a; }}
    .ocr-panel {{ max-height: 70vh; overflow-y: auto; border: 1px solid #d9e4e3; border-radius: 12px; padding: 22px; background: #fff; }}
    .ocr-panel h3 {{ color: {TEAL}; margin-top: 0; margin-bottom: 10px; font-size: 1rem; letter-spacing: 0.06em; }}
    .ocr-panel hr {{ border: 0; border-top: 1px solid #d4dfde; margin: 22px 0; }}
    .ocr-panel p {{ margin: 0 0 8px; white-space: pre-wrap; }}
    .note-box {{ margin-top: 16px; padding: 14px 16px; border-radius: 14px; background: #fff4df; border: 1px solid #f5d08d; color: #704d0f; font-weight: 600; }}
    .note-small {{ margin-top: 10px; color: #6b7280; font-size: 0.92rem; }}
    .parish-section {{ margin-top: 28px; background: #fff; border: 1px solid #d6ecea; border-radius: 18px; padding: 22px; box-shadow: 0 12px 30px rgba(26, 122, 122, 0.06); }}
    .parish-section h2 {{ margin: 0 0 16px; color: {TEXT}; font-size: 1rem; font-weight: 800; letter-spacing: 0.08em; text-transform: uppercase; }}
    ul.parish-grid {{ list-style: disc; display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px 28px; padding-left: 24px; margin: 0; }}
    ul.parish-grid li {{ break-inside: avoid; }}
    ul.parish-grid a {{ text-decoration: none; font-weight: 600; }}
    ul.parish-grid a:hover {{ text-decoration: underline; }}
    .empty-state {{ margin: 0; color: #6b7280; }}
    @media (max-width: 1100px) {{
      .viewer-grid {{ grid-template-columns: 1fr; }}
      .pdf-frame {{ min-height: 520px; }}
    }}
    @media (max-width: 720px) {{
      .page {{ padding: 20px 14px 36px; }}
      ul.parish-grid {{ grid-template-columns: 1fr; }}
      .pdf-controls {{ flex-wrap: wrap; }}
    }}
  </style>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js"></script>
</head>
<body>
  <div class="page">
    <a class="back-link" href="{archive_href}">← Back to bulletin archive</a>
    <h1>{html.escape(config.headline)}</h1>
    <p class="meta">Generated for {html.escape(bulletin_date)}.</p>
    <a class="download-link" href="{pdf_href}" download>⬇ Download PDF</a>

    <div class="viewer-grid">
      <section>
        <h2 class="column-title">Bulletins original PDF version</h2>
        <div class="panel">
          <div id="pdf-container" style="width:100%;height:70vh;min-height:680px;border:1px solid #c7dcda;border-radius:12px;overflow:hidden;background:#525659;">
            <canvas id="pdf-canvas" style="display:block;width:100%;height:100%;"></canvas>
          </div>
          <div class="pdf-controls">
            <button id="prev-page" type="button">← Previous</button>
            <span id="page-indicator">Page 1 of {page_count}</span>
            <button id="next-page" type="button">Next →</button>
          </div>
          <details class="pro-tip">
            <summary><span>🔍 PRO TIP: FIND TEXT INSTANTLY</span><span>+</span></summary>
            <div class="pro-tip-body">Press Ctrl+F (or Cmd+F on Mac) to search the OCR text on the right.</div>
          </details>
        </div>
      </section>

      <section>
        <h2 class="column-title">Bulletins OCR extracted plain text</h2>
        <div class="panel">
          <div class="ocr-panel">{ocr_fragment}</div>
          <div class="note-box">Note: The plain-text OCR version is auto-generated and may contain errors so it is always best to double check with the original PDF.</div>
          <p class="note-small">*OCR (Optical Character Recognition) is technology that turns images of text into editable, searchable digital text.</p>
        </div>
      </section>
    </div>

    <section class="parish-section">
      <h2>Parishes with working bulletin links</h2>
      {_render_parish_links(parish_links)}
    </section>
  </div>

  <script>
    (function () {{
      const pdfjsLib = window['pdfjs-dist/build/pdf'];
      pdfjsLib.GlobalWorkerOptions.workerSrc = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';

      let pdfDoc = null;
      let currentPage = 1;
      const totalPages = {page_count};
      const canvas = document.getElementById('pdf-canvas');
      const ctx = canvas.getContext('2d');
      const indicator = document.getElementById('page-indicator');
      const prev = document.getElementById('prev-page');
      const next = document.getElementById('next-page');

      async function renderPage(num) {{
        const page = await pdfDoc.getPage(num);
        const container = canvas.parentElement;
        const viewport = page.getViewport({{ scale: container.clientWidth / page.getViewport({{ scale: 1 }}).width }});
        canvas.height = viewport.height;
        canvas.width = viewport.width;
        await page.render({{ canvasContext: ctx, viewport }}).promise;
        indicator.textContent = `Page ${{num}} of ${{totalPages}}`;
        prev.disabled = num <= 1;
        next.disabled = num >= totalPages;
      }}

      pdfjsLib.getDocument('{pdf_href}').promise.then(pdf => {{
        pdfDoc = pdf;
        renderPage(currentPage);
      }});

      prev.addEventListener('click', () => {{ if (currentPage > 1) renderPage(--currentPage); }});
      next.addEventListener('click', () => {{ if (currentPage < totalPages) renderPage(++currentPage); }});
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
