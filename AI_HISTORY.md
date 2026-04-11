# AI Development Diary – Parish Bulletin Harvester

This file is the AI's permanent memory. Before making any changes to this
repository, the AI must read this file first to understand what has already
been built and why.

---

## Session 1 – Foundation (Prior to April 2026)

### Problem
The original `ParishRobot.py` script was downloading 2 KB "bulletins" that
were actually 404 error pages, wasting time on junk pages (privacy policies,
safeguarding documents) and had no memory between runs.

### Changes Made
1. **Junk Filter** (`harvester/config.py` → `JUNK_KEYWORDS`)
   Links containing words like "safeguarding", "gdpr", "privacy", "policy",
   "baptism", "marriage", "roster", "facebook", etc. are silently ignored.

2. **30 KB / Valid PDF Blocker** (`harvester/utils.py` → `is_valid_pdf`)
   Any downloaded file that does not start with the `%PDF` magic bytes is
   immediately discarded.  This eliminates the 2 KB HTML error pages that
   were being mis-saved as bulletins.

3. **Memory / Success Map** (`harvester/profiles.py`)
   After each successful run the harvester writes `parishes/parish_profiles.json`
   recording: `last_success_url`, `last_success_method`, `site_type`.
   On the next run it checks there first before crawling the whole site.

4. **Google Docs Viewer Bypass** (`harvester/fetcher.py`)
   When an `<iframe src>` points at `docs.google.com/viewer?url=…`, the
   harvester extracts the inner URL and downloads the actual file directly,
   bypassing the slow viewer.

5. **HTML-Bulletin Scraper** (`harvester/fetcher.py` → `_scrape_html_to_pdf`)
   For sites like Ballinascreen (Wix) that publish the bulletin as an HTML
   page rather than a PDF, the harvester scrapes the text and converts it to
   a PDF using `reportlab`.

---

## Session 2 – Predictive URL Engine / "Safe Cracker" (April 2026)

### Problem
The user discovered that most parishes in Derry Diocese update their bulletin
URL by simply changing the date portion each Sunday.  Instead of crawling the
whole website every week, the app should **predict** next week's URL
mathematically from last week's known URL.

### The Six "Safe Cracker" Patterns

The user mapped every parish in the diocese to one of these six patterns:

| Code | Format | Example | Parishes |
|------|--------|---------|----------|
| **A** | `DDMMYY` (no separator) | `050426.pdf` | Aghyaran, Ardmore, Buncrana, Carndonagh, Castlederg |
| **B** | `D-M-YY` (dashes, no leading zeros) | `5-4-26.pdf` | Limavady, Claudy (.docx) |
| **C** | `YYYY-MM-DD` + `/YYYY/MM/` folder | `2026-04-12.pdf` | Clonmany |
| **D** | `DD-Month-YYYY` + `/YYYY/MM/` folder | `12-April-2026.pdf` | Bellaghy (WordPress) |
| **E** | `[YYYY-M-D]` bracketed | `[2026-4-12].pdf` | Greenlough |
| **F** | Static filename | `laveyparishbulletin.pdf` | Lavey |

And two HTML (non-PDF) patterns:

| Code | Format | Example | Parishes |
|------|--------|---------|----------|
| **HTML-SLUG** | `D_month_YYYY` in URL slug | `/ballinascreen-5_april_2026` | Ballinascreen |
| **HTML-ID** | Sequential DB integer | `/Newsletters/384/Bulletin-…` | Banagher |

### How the Safe Cracker Works

1. **Look at last week's URL** from `parish_profiles.json` (`source_url`).
2. **Identify the pattern** by trying each regex in order (A → B → C → D → E → F).
3. **Substitute the new date** mathematically.
4. **Attempt a direct download** of the predicted URL.
5. **If the download fails** (404, file < 30 KB, not a valid PDF), fall back to
   the standard full-crawl / HTML-scrape pipeline.

### Changes Made in This Session

#### `harvester/utils.py`
- Added `_D_M_YY_RE` regex for Pattern B (`D-M-YY` dashes, no leading zeros).
- Added `_BRACKETED_ISO_RE` regex for Pattern E (`[YYYY-M-D]`).
- Rewrote `rewrite_date_url()` to handle all six patterns:
  - **A** (DDMMYYYY / DDMMYY) – was already supported; kept as-is.
  - **C** (ISO `YYYY-MM-DD`) – now rewrites both the filename date and any
    `/YYYY/MM/` directory segment in the path.
  - **B** (`D-M-YY`) – new; preserves the no-leading-zero format.
  - **D** (`DD-Month-YYYY`) – new; uses month names, updates `/YYYY/MM/` dir.
  - **E** (`[YYYY-M-D]`) – new; preserves brackets and no-leading-zero format.
  - **F** (no date found) – returns URL unchanged so the caller downloads the
    same static file.

#### `harvester/fetcher.py`
- Imported `rewrite_slug_url` from `utils`.
- **Improved memory path**: when a remembered `source_url` is available, the
  app now tries the *date-rewritten* version first (to catch the common case
  where the URL just has a new date) before trying the original remembered URL.
  Both are tried before falling back to a full root scan.
- **Predictive slug path**: for non-PDF URLs that contain a `D_month_YYYY`
  slug, `rewrite_slug_url()` rewrites the slug to this week's date and the app
  attempts to scrape that page directly (HTML → PDF) before doing a full crawl.
  This makes Ballinascreen-style sites instant.

#### New Files
- `All_the_pdfs_Derry_Diocese.txt` – Master reference listing every known
  parish URL, its pattern code, worked examples, and notes.  Used by the AI
  to understand the diocese and as a human-readable audit trail.
- `AI_HISTORY.md` (this file) – Permanent AI diary.

---

## Rules the AI Must Never Forget

1. **Never trust a file smaller than ~30 KB** – it is almost certainly a
   404/error HTML page masquerading as a PDF.  Delete it and try again.

2. **Predict before you crawl** – if you have a previous URL in the success
   map, apply `rewrite_date_url()` first.  Only crawl if the prediction fails.

3. **The six patterns are exhaustive for Derry Diocese** – every parish uses
   one of A, B, C, D, E, F, HTML-SLUG, or HTML-ID.  When adding a new parish
   check `All_the_pdfs_Derry_Diocese.txt` first.

4. **Update `/YYYY/MM/` folder paths** when rewriting Pattern C or D URLs –
   forgetting this will silently produce a 404 when the month rolls over.

5. **Banagher (HTML-ID) cannot be predicted safely** – always fall back to
   scraping the homepage for the correct link.

6. **Claudy is a `.docx` file** served via Google Docs Viewer – extract the
   inner URL, apply Pattern B rewrite, and download directly.

7. **Static files (Pattern F)** are simply re-downloaded each week unchanged –
   the priest overwrites the same filename.  Freshness is checked by the
   bulletin date extracted from the file content, not the URL.
