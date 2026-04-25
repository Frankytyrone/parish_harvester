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

Training mode now uses a Chrome extension side panel so you can mark:
- static HTML bulletin pages (**Mark Page as HTML**),
- the current URL as a bulletin file (**Mark Current URL as File**),
- image bulletins (right-click an image → **Mark as Bulletin Image**),
- image regions to convert to PDF (**Crop Bulletin Image**).

The fetcher also auto-detects WordPress PDF Embedder links (`a.pdfemb-viewer`) and prefers those URLs first.

---

## New Features

### 1. Error Notifications in the Floating Toolbar

The floating Parish Trainer toolbar now shows a small coloured status bar below the buttons:
- ✅ **Green bar** — action succeeded (e.g. "✅ Marked as HTML")
- ❌ **Red bar** — action failed (e.g. "❌ Could not communicate with page. Try refreshing.")

The message auto-hides after 4 seconds.

### 2. Retry Logic

When a PDF download fails (network error, timeout, bad response), the harvester
automatically retries up to **2 more times** (3 total attempts) with a 3-second
wait between attempts. Each retry is logged to the terminal:

```
↩️ Retrying ardmoreparish (attempt 2/3): HTTP 503 for https://...
↩️ Retrying ardmoreparish (attempt 3/3): HTTP 503 for https://...
```

### 3. Harvest Log / History

Every harvest run appends results to `harvest_log.json` in the project root. At
the end of each run, a summary table of the last 20 harvests is printed:

```
── Harvest Log (last 20) ─────────────────────────────────────────────
 Parish                 │ Status │ Type    │ Timestamp           │ Error / URL
────────────────────────┼────────┼─────────┼─────────────────────┼──────────────
 Ardmore Parish         │ ✅ ok   │ pdf     │ 2026-04-20T08:00:00 │ https://...
 Clonleigh Parish       │ 💥 fail │         │ 2026-04-20T08:01:12 │ HTTP 404
```

The log file is cumulative — it grows over time and lets you see trends in which
parishes fail regularly.

### 4. iFrame PDF Detection

The bulletin scraper now specifically checks `iframe[src]` elements before
falling back to generic link scanning:
- If the iframe `src` ends in `.pdf` or contains `.pdf`, it is treated as a
  direct PDF URL and downloaded immediately.
- If the `src` is a Google Docs viewer URL (`docs.google.com/viewer?url=…`), the
  real PDF URL is extracted from the `url=` query parameter automatically.

This covers parishes that embed their bulletin PDF inside an `<iframe>` on their
website (a common WordPress pattern).

### 5. Automatic Scheduled Harvesting

Run the harvester automatically every week without manual intervention:

```bash
python scheduler.py
```

By default this runs the full harvest every **Sunday at 08:00**. The schedule is
configurable via environment variables — no code changes required:

```bash
# Run every Sunday at 10:30 instead
HARVEST_SCHEDULE="sunday 10:30" python scheduler.py

# Run on a different day
HARVEST_SCHEDULE="monday 06:00" python scheduler.py

# Use a different diocese
HARVEST_DIOCESE="armagh_diocese" python scheduler.py
```

**Cost: zero.** Uses only the lightweight [`schedule`](https://pypi.org/project/schedule/)
pip package (already in `requirements.txt`) and Python built-ins. No cloud
services, no subscriptions, no cron daemon required — just leave the terminal
running.

To run it in the background on Linux/macOS:

```bash
nohup python scheduler.py &> scheduler.log &
```

---

## Project Structure

```
parish_harvester/
├── README.md
├── requirements.txt
├── scheduler.py        # Automatic weekly scheduler
├── harvest_log.json    # Auto-created: per-run harvest history (appended)
├── .gitignore
├── parishes/
│   ├── derry_diocese_bulletin_urls.txt   # Evidence file — master list of bulletin URLs
│   ├── derry_diocese_contacts.json       # Parish display names, websites, Facebook
│   ├── recipes/                          # Recorded Playwright recipes per parish
│   └── NEW_DIOCESE_TEMPLATE.md           # Guide: how to add a new diocese
├── harvester/
│   ├── __init__.py
│   ├── config.py         # Paths, timeouts, target_sunday()
│   ├── fetcher.py        # Parse evidence file, calculate URLs, download
│   ├── replay.py         # Replays trained recipe steps
│   ├── harvest_log.py    # Harvest log writer and summary printer
│   ├── liturgical.py     # Catholic liturgical calendar 2026 (for Greenlough)
│   ├── report.py         # Generate report.json and report.txt
│   ├── stitcher.py       # Stitch A–Z mega PDF
│   └── utils.py          # Date maths: rewrite_date_url, rewrite_greenlough_url, etc.
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
- `harvest_log.json` — cumulative harvest history (all runs)

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
