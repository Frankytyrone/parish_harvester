from __future__ import annotations

import json
import html
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from harvester.fetcher import parse_evidence_file
from harvester.page_renderer import render_diocese_page

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = REPO_ROOT / "docs"
RECIPES_DIR = REPO_ROOT / "parishes" / "recipes"
BULLETINS_DIR = DOCS_DIR / "bulletins"

LIVE_DIOCESES = {"raphoe", "derry", "down-and-connor"}
RELIABILITY_PATH = DOCS_DIR / "reliability.json"
REPORT_PATH = REPO_ROOT / "Bulletins" / "report.json"
EVIDENCE_DIOCESE_KEYS = {
    "derry": "derry_diocese",
    "down-and-connor": "down_and_connor",
    "raphoe": "raphoe_diocese",
}

_CANONICAL_DIOCESES = [
    "Armagh",
    "Dublin",
    "Cashel and Emly",
    "Tuam",
    "Clogher",
    "Cloyne",
    "Cork and Ross",
    "Derry",
    "Down and Connor",
    "Dromore",
    "Elphin",
    "Ferns",
    "Galway Kilmacduagh and Kilfenora",
    "Kerry",
    "Kildare and Leighlin",
    "Killala",
    "Killaloe",
    "Limerick",
    "Meath",
    "Ossory",
    "Raphoe",
    "Waterford and Lismore",
    "Achonry",
    "Ardagh and Clonmacnoise",
    "Kilmore",
    "Kilfenora-and-Kilmacduagh",
]


@dataclass(frozen=True)
class DioceseCard:
    key: str
    name: str


def _slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = "".join(ch for ch in normalized if ord(ch) < 128)
    lowered = ascii_value.lower()
    collapsed = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")
    return collapsed


def _all_dioceses() -> list[DioceseCard]:
    return [DioceseCard(key=_slugify(name), name=name) for name in _CANONICAL_DIOCESES]


def _recipe_dirs(diocese_key: str) -> list[Path]:
    candidates = {
        RECIPES_DIR / diocese_key,
        RECIPES_DIR / diocese_key.replace("-", "_"),
    }
    return [path for path in candidates if path.is_dir()]


def _recipe_files(diocese_key: str) -> list[Path]:
    files: list[Path] = []
    for recipe_dir in _recipe_dirs(diocese_key):
        files.extend(sorted(recipe_dir.glob("*.json")))
    return files


def _parish_links(diocese_key: str) -> list[dict[str, str]]:
    evidence_key = EVIDENCE_DIOCESE_KEYS.get(diocese_key)
    if evidence_key:
        try:
            entries = parse_evidence_file(evidence_key, REPO_ROOT / "parishes")
        except Exception:
            entries = []
        if entries:
            return [
                {
                    "name": entry.display_name,
                    "url": entry.bulletin_page or entry.example_url,
                }
                for entry in entries
                if (entry.bulletin_page or entry.example_url)
            ]

    links: list[dict[str, str]] = []
    for path in _recipe_files(diocese_key):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            payload = {}
        if not isinstance(payload, dict):
            continue
        name = (
            str(payload.get("parish_name") or "").strip()
            or str(payload.get("display_name") or "").strip()
            or path.stem.replace("-", " ").replace("_", " ").title()
        )
        url = str(payload.get("start_url") or "").strip()
        if not url:
            continue
        links.append({"name": name, "url": url})
    return links


def _recipe_keys(diocese_key: str) -> set[str]:
    keys: set[str] = set()
    for path in _recipe_files(diocese_key):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            payload = {}
        if isinstance(payload, dict):
            key = str(payload.get("parish_key") or "").strip()
            if key:
                keys.add(key)
                continue
        keys.add(path.stem)
    return keys


def _load_downloaded(report_path: Path) -> set[str]:
    if not report_path.exists():
        return set()
    try:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
    except Exception:
        return set()
    downloaded = payload.get("downloaded")
    if not isinstance(downloaded, list):
        return set()
    keys: set[str] = set()
    for row in downloaded:
        if not isinstance(row, dict):
            continue
        parish = str(row.get("parish") or "").strip()
        if parish:
            keys.add(parish)
    return keys


def _viewer_pattern(diocese_key: str) -> re.Pattern[str]:
    stem = diocese_key.replace("-", "[-_]")
    return re.compile(rf"^{stem}-(\d{{4}}-\d{{2}}-\d{{2}})\.html$")


def _latest_viewer(diocese_key: str) -> tuple[Path | None, str | None]:
    if not BULLETINS_DIR.exists():
        return None, None
    regex = _viewer_pattern(diocese_key)
    latest: tuple[Path, str] | None = None
    for path in sorted(BULLETINS_DIR.glob("*.html")):
        if path.name == "index.html":
            continue
        match = regex.match(path.name)
        if not match:
            continue
        date_text = match.group(1)
        if latest is None or date_text > latest[1]:
            latest = (path, date_text)
    return latest if latest else (None, None)


def _ocr_text_from_viewer(path: Path | None) -> str:
    if path is None or not path.exists():
        return ""
    raw_html = path.read_text(encoding="utf-8")
    match = re.search(
        r'<div id="ocr-panel">\s*(.*?)\s*</div>\s*<div class="note-box">',
        raw_html,
        re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return ""
    fragment = match.group(1)
    without_tags = re.sub(r"<[^>]+>", "\n", fragment)
    compacted = re.sub(r"[ \t\r\f\v]+", " ", without_tags)
    lines = [line.strip() for line in compacted.splitlines() if line.strip()]
    return "\n".join(lines)


def _placeholder_page(diocese: DioceseCard, out_path: Path) -> None:
    parish_links = _parish_links(diocese.key)
    parish_styles = ""
    parish_markup = ""
    if parish_links:
        parish_styles = """
    .parish-section { margin-top: 16px; background: #fff; border: 1px solid #d6ecea; border-radius: 12px; padding: 18px; }
    .parish-section h2 { margin: 0 0 10px; color: #1a6b6b; font-size: 1rem; text-transform: uppercase; }
    .parish-list { margin: 0; padding-left: 20px; columns: 2; }
    .parish-list li { margin: 6px 0; }
    .parish-list a { color: #1a6b6b; text-decoration: none; }
    .parish-list a:hover { text-decoration: underline; }
"""
        parish_markup = f"""
    <section class=\"parish-section\">
      <h2>{diocese.name.upper()} PARISH LINKS</h2>
      {_render_placeholder_parish_links(parish_links)}
    </section>"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        f"""<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>{diocese.name} — Parish Press</title>
  <link rel=\"stylesheet\" href=\"../../assets/site.css\" />
  <style>
    body {{ font-family: Arial, Helvetica, sans-serif; margin: 0; background: #f7fbfb; color: #16202a; }}
    .wrap {{ max-width: 920px; margin: 0 auto; padding: 22px 16px; }}
    .headline {{ margin: 0 0 16px; background: #1a6b6b; color: #fff; padding: 14px 16px; text-transform: uppercase; }}
    .card {{ background: #fff; border: 1px solid #d6ecea; border-radius: 12px; padding: 18px; }}
{parish_styles}
  </style>
</head>
<body>
  <main class=\"wrap\">
    <h1 class=\"headline\">{diocese.name.upper()} DIOCESE BIG BULLETIN</h1>
    <section class=\"card\">
      <p>We're still collecting bulletins for this diocese. Check back next Sunday.</p>
    </section>
{parish_markup}
  </main>
</body>
</html>
""",
        encoding="utf-8",
    )


def _load_reliability() -> dict[str, dict]:
    if not RELIABILITY_PATH.exists():
        return {}
    try:
        payload = json.loads(RELIABILITY_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    parishes = payload.get("parishes")
    return parishes if isinstance(parishes, dict) else {}


def _status_dot(avg_success_rate: float | None) -> str:
    if avg_success_rate is None:
        return "⚪"
    if avg_success_rate >= 0.8:
        return "🟢"
    if avg_success_rate >= 0.5:
        return "��"
    return "🔴"


def _landing_page(rows: list[dict[str, str]]) -> str:
    live_sections = "".join(
        (
            "<section class=\"live-diocese\">"
            f"<div class=\"live-diocese-head\"><h2>{html_name} Diocese</h2>"
            f"<a href=\"dioceses/{row['key']}/\">Open big bulletin →</a></div>"
            "<p class=\"live-diocese-note\">Parish links below come from the bulletin evidence file.</p>"
            f"{_render_placeholder_parish_links(_parish_links(row['key']))}"
            "</section>"
        )
        for row in rows
        if row["key"] in LIVE_DIOCESES and _parish_links(row["key"])
        for html_name in [row["name"]]
    )
    cards_html = "".join(
        (
            "<article class=\"diocese-card\">"
            f"<h2>{row['name']}</h2>"
            f"<p><strong>{row['dot']}</strong> {row['status_label']}</p>"
            f"<p>Last updated: {row['updated']}</p>"
            f"<a href=\"dioceses/{row['key']}/\">Open →</a>"
            "</article>"
        )
        for row in rows
    )
    return f"""<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Parish Press — Irish Catholic Bulletins</title>
  <link rel=\"stylesheet\" href=\"assets/site.css\" />
  <style>
    body {{ margin: 0; font-family: Arial, Helvetica, sans-serif; background: #f7fbfb; color: #16202a; }}
    .hero {{ background: #1a6b6b; color: #fff; padding: 26px 18px; }}
    .hero-inner, .content, .footer {{ max-width: 1180px; margin: 0 auto; }}
    .banner {{ background: #fff4df; border: 1px solid #f5d08d; color: #704d0f; border-radius: 10px; padding: 10px 12px; margin-top: 12px; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: 14px; margin-top: 18px; }}
    .diocese-card {{ background: #fff; border: 1px solid #d6ecea; border-radius: 12px; padding: 14px; }}
    .diocese-card h2 {{ margin: 0 0 8px; font-size: 1.08rem; }}
    .diocese-card p {{ margin: 0 0 8px; color: #4b5563; }}
    .diocese-card a {{ color: #1a6b6b; font-weight: 700; text-decoration: none; }}
    .diocese-card a:hover {{ text-decoration: underline; }}
    .content {{ padding: 20px 16px 10px; }}
    .live-diocese {{ margin-top: 20px; background: #fff; border: 1px solid #d6ecea; border-radius: 12px; padding: 16px; }}
    .live-diocese-head {{ display: flex; justify-content: space-between; align-items: baseline; gap: 10px; flex-wrap: wrap; }}
    .live-diocese-head h2 {{ margin: 0; color: #1a6b6b; }}
    .live-diocese-head a {{ color: #1a6b6b; font-weight: 700; text-decoration: none; }}
    .live-diocese-head a:hover {{ text-decoration: underline; }}
    .live-diocese-note {{ margin: 8px 0 12px; color: #4b5563; }}
    .parish-list {{ margin: 0; padding-left: 18px; columns: 3; }}
    .parish-list li {{ margin: 6px 0; }}
    .parish-list a {{ color: #1a6b6b; text-decoration: none; }}
    .parish-list a:hover {{ text-decoration: underline; }}
    .footer {{ border-top: 1px solid #d6ecea; margin-top: 18px; padding: 14px 16px 24px; color: #4b5563; font-size: 0.95rem; }}
    .footer a {{ color: #1a6b6b; text-decoration: none; }}
    .footer a:hover {{ text-decoration: underline; }}
  </style>
</head>
<body>
  <header class=\"hero\">
    <div class=\"hero-inner\">
      <h1>Parish Press — Irish Catholic Bulletins</h1>
      <p>Auto-collected every Sunday. Free forever.</p>
      <p class=\"banner\">🤖 Bulletins are auto-collected from parish websites. OCR may contain errors. Always check the original PDF.</p>
    </div>
  </header>
  <main class=\"content\">
    <section class=\"grid\">{cards_html}</section>
    {live_sections}
  </main>
  <footer class=\"footer\">
    <p><a href=\"bulletins/index.html\">Browse the full OCR bulletin archive</a></p>
    <p><a href=\"mega_pdf/index.html\">Open the mega PDF tab viewer</a></p>
    <p><a href=\"EMBEDDING.md\">Read the embedding guide</a> · <a href=\"embed-examples.html\">Open copy/paste embed examples</a></p>
    <p><a href=\"badges/\">Parish reliability scores</a></p>
    <p>Subscribe (RSS): <a href=\"feeds/derry_diocese.xml\">Derry Diocese</a> · <a href=\"feeds/down_and_connor.xml\">Down &amp; Connor</a></p>
    <p><a href=\"search/\">Search all bulletins</a></p>
    <p>📅 Subscribe in Google/Apple Calendar: <a href=\"calendars/derry.ics\">Derry Diocese</a> · <a href=\"calendars/down_and_connor.ics\">Down &amp; Connor</a> · <a href=\"calendars/all.ics\">All parishes</a></p>
    <p><a href=\"sitemap.html\">🗺️ Site map — every public URL</a> · <a href=\"COST_DASHBOARD.md\">💷 Cost dashboard</a></p>
    <p><a href=\"subscribe/\">📬 Subscribe for reminders</a></p>
    <p>© 2026 Parish Press</p>
  </footer>
</body>
</html>
"""


def _subscribe_page(dioceses: list[DioceseCard]) -> str:
    items = "".join(
        f'<li><a href="../dioceses/{d.key}/">{d.name}</a></li>' for d in dioceses
    )
    return f"""<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Subscribe — Parish Press</title>
  <link rel=\"stylesheet\" href=\"../assets/site.css\" />
</head>
<body>
  <main style=\"max-width:900px;margin:0 auto;padding:20px 16px;font-family:Arial,Helvetica,sans-serif;\">
    <h1>📬 Subscribe for reminders</h1>
    <p>Pick your diocese page below and use the RSS/calendar links from the footer.</p>
    <ul style=\"columns:2;\">{items}</ul>
  </main>
</body>
</html>
"""


def _render_placeholder_parish_links(parish_links: list[dict[str, str]]) -> str:
    if not parish_links:
        return "<p>No parish links available yet.</p>"
    items = "".join(
        f'<li><a href="{html.escape(link["url"], quote=True)}">{html.escape(link["name"])}</a></li>'
        for link in sorted(parish_links, key=lambda item: item["name"].lower())
    )
    return f'<ul class="parish-list">{items}</ul>'


def run(report_path: Path = REPORT_PATH, docs_dir: Path = DOCS_DIR) -> None:
    dioceses = _all_dioceses()
    downloaded = _load_downloaded(report_path)
    reliability = _load_reliability()

    rows: list[dict[str, str]] = []
    for diocese in dioceses:
        out_path = docs_dir / "dioceses" / diocese.key / "index.html"
        keys = _recipe_keys(diocese.key)
        trained = bool(keys)
        success_this_run = bool(downloaded.intersection(keys))

        viewer_path, updated = _latest_viewer(diocese.key)
        if diocese.key in LIVE_DIOCESES and trained and success_this_run and viewer_path:
            render_diocese_page(
                diocese_key=diocese.key,
                diocese_display_name=diocese.name,
                mega_pdf_url=f"../../mega_pdf/{diocese.key.replace('-', '_')}_mega_bulletin.pdf",
                ocr_text=_ocr_text_from_viewer(viewer_path),
                parish_links=_parish_links(diocese.key),
                out_path=out_path,
            )
            updated_label = updated or "Coming soon"
        else:
            _placeholder_page(diocese, out_path)
            updated_label = "Coming soon"

        rates = []
        for key in keys:
            value = reliability.get(key)
            if isinstance(value, dict):
                rate = value.get("success_rate")
                if isinstance(rate, (int, float)):
                    rates.append(float(rate))
        avg = (sum(rates) / len(rates)) if rates else None
        dot = _status_dot(avg)
        status_label = "Reliability available" if avg is not None else "No reliability data yet"
        rows.append(
            {
                "key": diocese.key,
                "name": diocese.name,
                "dot": dot,
                "status_label": status_label,
                "updated": updated_label,
            }
        )

    docs_dir.mkdir(parents=True, exist_ok=True)
    (docs_dir / "index.html").write_text(_landing_page(rows), encoding="utf-8")
    subscribe_dir = docs_dir / "subscribe"
    subscribe_dir.mkdir(parents=True, exist_ok=True)
    (subscribe_dir / "index.html").write_text(_subscribe_page(dioceses), encoding="utf-8")
