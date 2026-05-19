from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from html import escape
from pathlib import Path
from shutil import copyfile

REPO_ROOT = Path(__file__).resolve().parent.parent
OCR_CONTENT_PATTERN = re.compile(r'<div class="scrollable-viewer">(.*?)</div>', re.DOTALL)
PAGE_HEADING_PATTERN = re.compile(r'<h2>\s*Page\s+(\d+)\s*</h2>', re.IGNORECASE)
PARISH_HEADER_PATTERN = re.compile(r'^#\s*---\s*(.*?)\s*---\s*$')
OUTPUT_PAGE_PATTERN = re.compile(r'^(derry|down_and_connor)-(\d{4}-\d{2}-\d{2})\.html$')


@dataclass(frozen=True)
class DioceseConfig:
    slug: str
    display_name: str
    source_urls: Path


DIOCESES = {
    'derry': DioceseConfig(
        slug='derry',
        display_name='Derry',
        source_urls=REPO_ROOT / 'parishes' / 'derry_diocese_bulletin_urls.txt',
    ),
    'down_and_connor': DioceseConfig(
        slug='down_and_connor',
        display_name='Down & Connor',
        source_urls=REPO_ROOT / 'parishes' / 'down_and_connor_bulletin_urls.txt',
    ),
}


PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{title} - {date}</title>
  <style>
    :root {{
      --teal: #1b6b6b;
      --teal-link: #1b7a7a;
      --navy: #10233f;
      --navy-soft: #1b2e4b;
      --bg: #f5f8f8;
      --card: #ffffff;
      --border: #d5e2e2;
      --amber-bg: #fff3cd;
      --amber-border: #ffc107;
      --orange: #f59e0b;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Arial, Helvetica, sans-serif;
      background: var(--bg);
      color: #1f2937;
    }}
    a {{ color: var(--teal-link); }}
    nav {{
      background: #ffffff;
      border-bottom: 1px solid var(--border);
      padding: 14px 24px;
    }}
    nav a {{
      color: var(--teal);
      font-weight: 700;
      text-decoration: none;
    }}
    .hero {{
      padding: 28px 24px 14px;
    }}
    .hero h1 {{
      margin: 0;
      color: var(--teal);
      font-size: clamp(2rem, 4vw, 3.1rem);
      line-height: 1.1;
      letter-spacing: 0.02em;
    }}
    main {{
      padding: 0 24px 40px;
    }}
    .download-link {{
      display: inline-block;
      margin: 10px 0 22px;
      color: var(--teal-link);
      font-weight: 700;
      text-decoration: none;
    }}
    .viewer-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 24px;
      align-items: start;
    }}
    .col {{
      min-width: 0;
    }}
    .panel-card {{
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 18px;
      padding: 22px;
      box-shadow: 0 10px 30px rgba(15, 23, 42, 0.08);
    }}
    .panel-card h2, .parish-list h2 {{
      margin: 0 0 18px;
      color: var(--navy);
      font-size: 1rem;
      font-weight: 800;
      letter-spacing: 0.06em;
      text-transform: uppercase;
    }}
    .pdf-frame {{
      width: 100%;
      min-height: 72vh;
      border: 1px solid var(--border);
      border-radius: 14px;
      background: #fff;
    }}
    .pro-tip {{
      margin-top: 16px;
      background: var(--navy);
      color: #fff;
      border-radius: 14px;
      overflow: hidden;
    }}
    .pro-tip-header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      padding: 14px 16px;
      font-weight: 800;
      letter-spacing: 0.03em;
    }}
    .pro-tip button {{
      appearance: none;
      border: none;
      background: var(--orange);
      color: #fff;
      width: 34px;
      height: 34px;
      border-radius: 10px;
      font-size: 1.3rem;
      font-weight: 800;
      cursor: pointer;
    }}
    .pro-tip-body {{
      padding: 0 16px 16px;
      font-size: 0.97rem;
      line-height: 1.6;
    }}
    .ocr-scroll {{
      min-height: 72vh;
      max-height: 72vh;
      overflow-y: auto;
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 22px;
      background: #fff;
      font-family: Georgia, 'Times New Roman', serif;
      line-height: 1.7;
    }}
    .ocr-scroll p {{ margin: 0 0 0.45rem; }}
    .ocr-scroll hr {{ border: 0; border-top: 1px solid #d7dddd; margin: 1.5rem 0; }}
    .ocr-page-heading {{
      margin: 0 0 1rem;
      color: var(--navy);
      font-size: 1rem;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }}
    .amber-note {{
      margin-top: 16px;
      background: var(--amber-bg);
      border: 1px solid var(--amber-border);
      border-radius: 14px;
      padding: 14px 16px;
      color: #5c4400;
      font-weight: 700;
    }}
    .ocr-explainer {{
      margin: 12px 2px 0;
      color: #475569;
      font-size: 0.95rem;
      line-height: 1.6;
    }}
    .parish-list {{
      margin-top: 28px;
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 18px;
      padding: 22px;
      box-shadow: 0 10px 30px rgba(15, 23, 42, 0.08);
    }}
    .parish-grid {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 12px 20px;
    }}
    .parish-grid a {{
      color: var(--teal);
      font-weight: 700;
      text-decoration: none;
    }}
    .parish-grid a:hover, .download-link:hover, nav a:hover {{ text-decoration: underline; }}
    @media (max-width: 960px) {{
      .viewer-grid, .parish-grid {{ grid-template-columns: 1fr; }}
      .pdf-frame, .ocr-scroll {{ min-height: 55vh; max-height: none; }}
    }}
  </style>
</head>
<body>
  <nav><a href="../index.html">Home</a> · <a href="./index.html">OCR bulletin archive</a></nav>
  <div class="hero">
    <h1>{title}</h1>
  </div>
  <main>
    <a class="download-link" href="../mega_pdf/{diocese}_mega_bulletin.pdf" download>Download PDF</a>
    <div class="viewer-grid">
      <div class="col">
        <div class="panel-card">
          <h2>Bulletins Original PDF Version</h2>
          <iframe class="pdf-frame" src="../mega_pdf/{diocese}_mega_bulletin.pdf#view=FitH" title="{title} PDF"></iframe>
          <div class="pro-tip">
            <div class="pro-tip-header">
              <span>🔍 PRO TIP: FIND TEXT INSTANTLY</span>
              <button type="button" aria-expanded="false" onclick="toggleTip(this)">+</button>
            </div>
            <div class="pro-tip-body" hidden>
              Use the browser PDF viewer controls to jump pages fast, then press Ctrl+F (or Cmd+F on Mac) to search the original bulletin instantly.
            </div>
          </div>
        </div>
      </div>
      <div class="col">
        <div class="panel-card">
          <h2>Bulletins OCR Extracted Plain Text</h2>
          <div class="ocr-scroll">
            {ocr_content}
          </div>
          <div class="amber-note">Note: The plain-text OCR version is auto-generated, so always check the original PDF if anything looks unclear.</div>
          <p class="ocr-explainer">*OCR (Optical Character Recognition) is technology that reads text from the bulletin pages and turns it into searchable, copyable plain text.</p>
        </div>
      </div>
    </div>
    <section class="parish-list">
      <h2>Parishes With Working Bulletin Links</h2>
      <div class="parish-grid">
        {parish_links}
      </div>
    </section>
  </main>
  <script>
    function toggleTip(button) {{
      const body = button.parentElement.nextElementSibling;
      const expanded = button.getAttribute('aria-expanded') === 'true';
      button.setAttribute('aria-expanded', expanded ? 'false' : 'true');
      button.textContent = expanded ? '+' : '−';
      body.hidden = expanded;
    }}
  </script>
</body>
</html>
"""

INDEX_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>OCR Bulletin Archive</title>
  <style>
    body {{
      margin: 0;
      font-family: Arial, Helvetica, sans-serif;
      background: #f5f8f8;
      color: #1f2937;
    }}
    main {{ max-width: 1100px; margin: 0 auto; padding: 32px 24px 48px; }}
    a {{ color: #1b6b6b; }}
    h1 {{ margin: 0 0 10px; color: #1b6b6b; font-size: clamp(2rem, 4vw, 3rem); }}
    p {{ color: #475569; }}
    .archive-list {{ display: grid; gap: 16px; margin-top: 28px; }}
    .archive-card {{
      background: #fff;
      border: 1px solid #d5e2e2;
      border-radius: 16px;
      padding: 18px 20px;
      box-shadow: 0 10px 24px rgba(15, 23, 42, 0.06);
    }}
    .archive-card strong {{ color: #10233f; display: block; margin-bottom: 6px; text-transform: uppercase; letter-spacing: 0.04em; }}
    .archive-actions {{ display: flex; flex-wrap: wrap; gap: 12px; margin-top: 12px; }}
    .archive-actions a {{ font-weight: 700; text-decoration: none; }}
    .empty {{
      background: #fff;
      border: 1px dashed #b6c8c8;
      border-radius: 16px;
      padding: 20px;
      margin-top: 28px;
    }}
  </style>
</head>
<body>
  <main>
    <a href="../index.html">← Back to home</a>
    <h1>OCR Bulletin Archive</h1>
    <p>Newest bulletin pages appear first after each successful harvest and Pages deploy.</p>
    {content}
  </main>
</body>
</html>
"""


def extract_ocr_content(ocr_html_path: Path) -> str:
    text = ocr_html_path.read_text(encoding='utf-8')
    match = OCR_CONTENT_PATTERN.search(text)
    if not match:
        raise ValueError(f'Could not locate OCR content in {ocr_html_path}')
    inner = match.group(1).strip()
    return PAGE_HEADING_PATTERN.sub(lambda m: f'<h3 class="ocr-page-heading">PAGE {m.group(1)}</h3>', inner)


def parse_parish_links(diocese: str) -> list[tuple[str, str]]:
    source_path = DIOCESES[diocese].source_urls
    links: list[tuple[str, str]] = []
    current_name: str | None = None
    captured_for_header = False
    for raw_line in source_path.read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()
        header_match = PARISH_HEADER_PATTERN.match(line)
        if header_match:
            current_name = header_match.group(1)
            captured_for_header = False
            continue
        if not line or line.startswith('#'):
            continue
        if current_name and not captured_for_header:
            links.append((current_name, line))
            captured_for_header = True
    return links


def build_parish_grid(links: list[tuple[str, str]]) -> str:
    return '\n        '.join(
        f'<a href="{escape(url, quote=True)}" target="_blank" rel="noopener noreferrer">{escape(name)}</a>'
        for name, url in links
    )


def render_bulletin_page(diocese: str, date: str, ocr_content: str, parish_links: list[tuple[str, str]]) -> str:
    config = DIOCESES[diocese]
    title = f'{config.display_name.upper()} DIOCESE BIG BULLETIN'
    return PAGE_TEMPLATE.format(
        title=title,
        date=date,
        diocese=diocese,
        ocr_content=ocr_content,
        parish_links=build_parish_grid(parish_links),
    )


def render_archive_index(bulletins_dir: Path) -> str:
    entries: list[tuple[str, str, str, str]] = []
    for path in bulletins_dir.glob('*.html'):
        match = OUTPUT_PAGE_PATTERN.match(path.name)
        if not match:
            continue
        diocese, date = match.groups()
        entries.append((date, DIOCESES[diocese].display_name, path.name, diocese))
    entries.sort(key=lambda item: (item[0], item[1]), reverse=True)
    if not entries:
        content = '<div class="empty">No OCR bulletin pages have been generated yet.</div>'
    else:
        cards = []
        for date, display_name, filename, diocese in entries:
            cards.append(
                '<div class="archive-card">'
                f'<strong>{escape(display_name)} Diocese</strong>'
                f'<div>{escape(date)}</div>'
                '<div class="archive-actions">'
                f'<a href="{escape(filename, quote=True)}">Open side-by-side viewer</a>'
                f'<a href="{escape(diocese + "-latest.html", quote=True)}">Latest link</a>'
                '</div>'
                '</div>'
            )
        content = '<div class="archive-list">' + ''.join(cards) + '</div>'
    return INDEX_TEMPLATE.format(content=content)


def generate_viewer_page(diocese: str, date: str, ocr_html_path: Path, output_path: Path, latest_output_path: Path, bulletins_dir: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    ocr_content = extract_ocr_content(ocr_html_path)
    parish_links = parse_parish_links(diocese)
    output_path.write_text(render_bulletin_page(diocese, date, ocr_content, parish_links), encoding='utf-8')
    copyfile(output_path, latest_output_path)
    bulletins_dir.mkdir(parents=True, exist_ok=True)
    (bulletins_dir / 'index.html').write_text(render_archive_index(bulletins_dir), encoding='utf-8')


def main() -> None:
    parser = argparse.ArgumentParser(description='Build side-by-side OCR bulletin viewer pages.')
    parser.add_argument('--diocese', choices=sorted(DIOCESES), required=True)
    parser.add_argument('--date', required=True)
    parser.add_argument('--ocr-html', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--latest-output', required=True, type=Path)
    parser.add_argument('--bulletins-dir', default=REPO_ROOT / 'docs' / 'bulletins', type=Path)
    args = parser.parse_args()

    generate_viewer_page(
        diocese=args.diocese,
        date=args.date,
        ocr_html_path=args.ocr_html,
        output_path=args.output,
        latest_output_path=args.latest_output,
        bulletins_dir=args.bulletins_dir,
    )


if __name__ == '__main__':
    main()
