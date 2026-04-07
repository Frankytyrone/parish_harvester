# Parish Bulletin Harvester

A fully automated tool that collects the current weekly newsletter/bulletin
from 50+ Derry Diocese parishes every weekend.

## Features

- **Headless browser fetching** (Playwright/Chromium) — handles JS-rendered pages
- **Intelligent PDF detection** — finds bulletin PDFs by keyword + date heuristics
- **Screenshot fallback** — captures full-page PNG when no PDF is found
- **AI verification** (GitHub Models GPT-4o Vision, free) — reads each file and checks it's for the current week
- **Self-cleaning** — moves fresh files to `Bulletins/current/`, discards stale ones
- **GitHub Actions** — runs automatically every Saturday at 06:00 UTC

---

## Quick Start

### 1. Clone and install

```bash
git clone https://github.com/Frankytyrone/parish_harvester.git
cd parish_harvester
pip install -r requirements.txt
python -m playwright install --with-deps chromium
# Ubuntu/Debian only — required by pdf2image:
sudo apt-get install -y poppler-utils
```

### 2. Configure for local development

For **GitHub Actions**, no configuration is needed — `GITHUB_TOKEN` is provided automatically.

For **local development**, create a [GitHub Personal Access Token](https://github.com/settings/tokens) and set it:

```bash
cp .env.example .env
# Edit .env and set your GitHub PAT:
# GITHUB_TOKEN=your-github-pat-here
```

### 3. Run

```bash
# Full run (fetch → verify → clean)
python main.py

# Specify a diocese / date
python main.py --diocese derry_diocese --target-date 2026-04-05

# Skip AI verification
python main.py --skip-verify

# Fetch only (no cleanup)
python main.py --dry-run
```

---

## Output

```
Bulletins/
├── current/                      # ✅ Verified fresh bulletins for the current week
├── raw/                          # Intermediate files (cleared after each run)
├── history/                      # 📚 Dated report archive (report_YYYY-MM-DD.json)
├── all_bulletins_YYYY-MM-DD.pdf  # 📖 A–Z mega PDF (real bulletins + placeholder pages)
├── copilot_review.md             # 🤖 Auto-generated review file for Copilot
├── report.json                   # Machine-readable summary
└── report.txt                    # Human-readable summary
```

### Exit codes

| Code | Meaning |
|------|---------|
| 0    | Success (run completed; individual parish errors are logged in the report) |
| 1    | Catastrophic failure (unhandled exception; the run did not complete) |

---

## Project Structure

```
parish_harvester/
├── README.md
├── requirements.txt
├── .env.example
├── .gitignore
├── parishes/
│   └── derry_diocese.txt     # One URL per line (50 deduplicated parishes)
├── harvester/
│   ├── __init__.py
│   ├── config.py             # Settings: target date, timeouts, paths
│   ├── fetcher.py            # Stage 1 — Playwright fetch logic
│   ├── verifier.py           # Stage 2 — GitHub Models Vision date verification
│   ├── cleaner.py            # Stage 3 — File sorting + report generation
│   └── utils.py              # Helpers: URL parsing, date formats
├── main.py                   # CLI entry point
└── .github/
    └── workflows/
        └── harvest.yml       # Scheduled GitHub Actions workflow
```

---

## GitHub Actions Setup

**No configuration needed!** The workflow uses `GITHUB_TOKEN` which is automatically provided by GitHub Actions — no secrets to add.

The workflow runs automatically every **Saturday at 06:00 UTC**, or you can trigger it manually from the **Actions** tab.

Bulletins are uploaded as a workflow artifact (retained for 30 days).

### AI Verification

The harvester uses the **GitHub Models API** (free) with GPT-4o vision to read each bulletin and confirm it's for the current week. This uses your existing GitHub account — no OpenAI API key, no billing, no setup.

---

## Design Principles

- **No per-site config** — generic heuristics only; no JSON mapping per parish
- **Graceful degradation** — a site being down logs an error and moves on; the run never crashes entirely
- **Idempotent** — running twice overwrites previous output with the same result
- **Facebook excluded** — requires authentication; not scrape-friendly
