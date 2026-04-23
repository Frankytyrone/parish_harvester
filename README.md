# Parish Bulletin Harvester v2

Downloads weekly Catholic parish bulletins by calculating URLs from known patterns,
then stitches them into one A–Z mega PDF.

## How it works

1. **Evidence file** (`parishes/{diocese}_bulletin_urls.txt`) records real, manually
   verified bulletin URLs for every parish.
2. The harvester **reads the evidence file** and first uses date maths to predict
   this week's URL for each parish.
3. If `parishes/recipes/{parish_key}.json` exists, Playwright replays those
   recorded steps first (training recipe mode).
4. If recipe replay fails (or no recipe exists), Playwright opens the parish page,
   scans links/embeds/iframes, and downloads the best PDF/DOCX match.
5. All PDFs are **stitched into one mega PDF** (A–Z). HTML-only parishes get a
   clickable link page instead.

**Prediction first, page scraping fallback. No AI verifier.**

---

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
python -m playwright install chromium
```

### 2. Run

```bash
# Full run for Derry Diocese (auto-calculates this week's Sunday)
python main.py

# Specify a diocese or date
python main.py --diocese derry_diocese --target-date 2026-04-19

# Fetch only (no report or mega PDF)
python main.py --dry-run

# Train a parish recipe (interactive browser)
python main.py --train "Hannahstown"
# or
python train.py "Hannahstown"
```

Training mode now includes a floating trainer panel so you can mark:
- image bulletins (right-click an image → **Mark as Bulletin Image**),
- static HTML bulletin pages,
- or the current URL as a bulletin file.

If `extension/` exists beside `train.py`, training automatically loads the
Manifest V3 Chromium extension panel instead of injecting inline page JS. If
the folder is missing, it falls back to inline panel injection.

---

## Project Structure

```
parish_harvester/
├── README.md
├── requirements.txt
├── .gitignore
├── parishes/
│   ├── derry_diocese_bulletin_urls.txt   # Evidence file — master list of bulletin URLs
│   ├── derry_diocese_contacts.json       # Parish display names, websites, Facebook
│   ├── recipes/                          # Recorded Playwright recipes per parish
│   └── NEW_DIOCESE_TEMPLATE.md           # Guide: how to add a new diocese
├── harvester/
│   ├── __init__.py
│   ├── config.py       # Paths, timeouts, target_sunday()
│   ├── fetcher.py      # Parse evidence file, calculate URLs, download
│   ├── replay.py       # Replays trained recipe steps
│   ├── liturgical.py   # Catholic liturgical calendar 2026 (for Greenlough)
│   ├── report.py       # Generate report.json and report.txt
│   ├── stitcher.py     # Stitch A–Z mega PDF
│   └── utils.py        # Date maths: rewrite_date_url, rewrite_greenlough_url, etc.
├── main.py             # CLI entry point
├── train.py            # Interactive recipe recorder
└── .github/
    └── workflows/
        └── harvest.yml   # Scheduled GitHub Actions workflow (every Sunday 12:00 UTC)
```

---

## URL Patterns

| Pattern | Format | Example |
|---------|--------|---------|
| A | `DDMMYY` | `.../pdf/120426.pdf` |
| B | `D-M-YY` | `.../onewebmedia/5-4-26.pdf` |
| C | `YYYY-MM-DD` | `.../uploads/2026/04/2026-04-12.pdf` |
| D | `DD-Month-YYYY` | `.../Newsletter-12-April-2026-1.pdf` |
| E | `[YYYY-M-D]` | `...[2026-4-12].pdf` |
| F | Static URL | same URL overwritten every week |
| H | Sequential number | `.../Newsletters/384/Bulletin-...` |
| clonleigh | WP post (Saturday before Sunday) | `.../2026/04/11/strabane-...-12th-april-2026/` |
| greenlough | Liturgical name + `[YYYY-M-D]` | `...Palm_Sunday[2026-3-29].pdf` |
| html\_link | No PDF — link only in mega PDF | `melmountparish.com/parishnews.html` |
| image | JPEG/PNG → PDF (via Pillow) | `iskaheenparish.com/.../1.jpg` |
| docx | Word doc → PDF (via LibreOffice) | `parishofclaudy.com/NEWSLETTER 12-4-26.docx` |

---

## Target Date Logic

The harvester calculates the target Sunday automatically:

| Day run | Target |
|---------|--------|
| Sunday | Today |
| Monday–Saturday | Last Sunday |

Override with `--target-date YYYY-MM-DD`.

---

## Adding a New Diocese

See `parishes/NEW_DIOCESE_TEMPLATE.md` for a complete guide.

Short version:
1. Create `parishes/{name}_bulletin_urls.txt` with real bulletin URLs
2. Create `parishes/{name}_contacts.json` with display names (optional)
3. Run `python main.py --diocese {name}`

---

## Output

After each run:

- `Bulletins/current/` — downloaded bulletin PDFs
- `Bulletins/all_bulletins_{date}.pdf` — merged A–Z mega PDF
- `Bulletins/report.json` — machine-readable report
- `Bulletins/report.txt` — human-readable report

### report.json structure

```json
{
  "target_date": "2026-04-19",
  "summary": {
    "downloaded": 25,
    "html_links": 4,
    "failed": 2
  },
  "downloaded": [...],
  "html_links": [...],
  "failed": [...]
}
```

---

## GitHub Actions

The workflow runs every Sunday at 12:00 UTC and:
1. Downloads all bulletins
2. Creates the mega PDF
3. Posts a summary issue to the repository
4. Uploads the Bulletins folder as an artifact
