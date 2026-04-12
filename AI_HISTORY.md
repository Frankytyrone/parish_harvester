# AI_HISTORY.md — Parish Bulletin Harvester Rules & Conversation Log

This file records the rules established through conversations with the user and
the AI assistant.  Any AI agent working on this codebase should read this file
before making changes, so that hard-won lessons are never forgotten.

---

## The Three Core Rules

### Rule 1: Never Accept a PDF Smaller Than 50 KB

When a parish website cannot find a bulletin it often returns an HTML error page
e.g. a "404 Not Found" page but delivers it with a `.pdf` Content-Disposition
header.  The resulting file is valid PDF magic-bytes but only 2–14 KB in size —
completely useless.

**The Fix:** After every PDF download, check the file size.  If it is less than
50,000 bytes (50 KB), delete the file immediately, log a clear warning, and
continue searching other links.  This is implemented in `harvester/fetcher.py`
via `_is_real_pdf()` and the `_MIN_PDF_BYTES = 50_000` constant.

**Rule 1b: Try Multiple PDF Candidates Before Giving Up.**  The scorer now
returns up to 5 ranked candidates (`_pick_top_pdfs`).  If the highest-scoring
link is a junk/tiny file the next candidate is tried automatically before
falling back to HTML-to-PDF conversion.  This prevents false errors when a
site publishes multiple PDFs (e.g. a small "Call to Pray" PDF alongside the
real bulletin).

**Rule 1c: Scan HTML Pages for Embedded PDF Links.**  When the fetch path lands
on an HTML bulletin-listing page (e.g. stmarysparishcreggan.com/bulletins),
`_scrape_html_to_pdf` first scans all `<a href>`, `<embed src>`, and
`<object data>` elements for real PDF links and tries to download the best
match before falling back to text extraction via reportlab.

---

### Rule 2: Use Predictive Date Shifting

Many parish websites use highly predictable URL patterns.  Instead of crawling
the entire site from scratch every week, the app should **predict** this week's
URL from last week's successful download URL by substituting the new date.

Known patterns (with real examples):

| Pattern | Example URL | Notes |
|---------|-------------|-------|
| `DDMMYY` | `http://www.carndonaghparish.com/pdf/050426.pdf` → `120426.pdf` | 6-digit date in filename |
| `DDMMYY` | `https://www.parishofaghyaran.com/pdf/120426.pdf` | Same pattern |
| `YYYY/MM` + `DD-Month-YYYY` | `https://bellaghyparish.com/wp-content/uploads/2026/04/Newsletter-12-April-2026-1.pdf` | WordPress-style |
| `DD-Month-YYYY` slug | `https://bellaghyparish.com/wp-content/uploads/2026/04/29-March-2026.pdf` | WP slug |

**The Fix:** In `harvester/fetcher.py` (`_fetch_inner`), the Predictive URL
Generator reads `last_success_url` from the parish profile (stored memory bank)
and applies `rewrite_date_url()` (for DDMMYY/DDMMYYYY) and `rewrite_wp_url()`
(for WordPress YYYY/MM + slug patterns) to generate this week's predicted URL.
The predicted URL is tried **before** any site crawl.  If it succeeds, we save
time.  If it fails, the app falls back to a full crawl and updates the memory
with the newly found URL.

---

### Rule 3: Maintain a Self-Learning Memory Bank

The app records the **actual source URL** of every successfully downloaded
bulletin in `parishes/parish_profiles.json`.  This is the `last_success_url`
field.  It is critical that this stores the **direct PDF URL** (e.g.
`carndonaghparish.com/pdf/050426.pdf`) rather than the homepage URL, because
the Predictive URL Generator (Rule 2) needs a date-containing URL to date-shift.

**The Fix:** Every `FetchResult` returned on success now includes `source_url`
set to the actual PDF URL.  `harvester/profiles.py:update_profile()` prefers
`source_url` over `url` when writing `last_success_url` to the profile.

If a predicted URL fails, the app performs a full crawl, finds the correct URL,
and writes it to the memory bank so the prediction improves next week.

---

## Conversation History

### Session 1 — Initial Problems Identified

**User observation:** The app is not grabbing many PDFs.  Files as small as 2 KB
are being saved — these are obviously not real parish bulletins.

**Root cause identified:** The downloader was blindly saving HTML error pages
with a `.pdf` extension.  No size validation was in place.

**Fixes agreed:**
1. Add a 30 KB minimum size filter (Rule 1 above).
2. Add a "Memory" system so the app remembers where it found the bulletin last
   week (Rule 3 above).
3. Add a "Google Docs Viewer bypass" — when a bulletin is embedded in a Google
   Docs Viewer iframe, extract the real PDF URL from the query string.
4. Add a "Junk Filter" — immediately ignore links containing words like
   "safeguarding", "gdpr", "policy", or "baptism".

### Session 2 — Predictive URL Generator

**User observation:** Parish URLs follow strict, predictable date patterns.
Examples given by the user:

```
https://www.parishofaghyaran.com/pdf/120426.pdf
https://www.parishofaghyaran.com/pdf/220326.pdf
https://www.parishofaghyaran.com/pdf/080226.pdf

https://bellaghyparish.com/wp-content/uploads/2026/04/Newsletter-12-April-2026-1.pdf
https://bellaghyparish.com/wp-content/uploads/2026/04/29-March-2026.pdf

http://www.carndonaghparish.com/pdf/050426.pdf
http://www.carndonaghparish.com/pdf/150326.pdf
```

**User quote:** *"look its dead easy, it nearly updates itself!!!"*

**Fix agreed:** Implement a Predictive URL Generator (Rule 2 above) that
mathematically shifts the date in the stored URL to predict this week's URL,
and tries it before crawling the site.

### Session 3 — Memory Bank Bug Fix

**Bug found:** The code was reading `hint.get("source_url")` but the profile
stores the key as `"last_success_url"`.  This meant the Memory Bank was
completely broken — the app never tried the remembered URL.  Fixed by using
`hint.get("last_success_url")` throughout `_fetch_inner`.

**Second bug found:** When a PDF was found via a site crawl, the `FetchResult`
did not include `source_url=best_pdf`.  This caused the memory bank to store
the homepage URL instead of the actual PDF URL, making date prediction
impossible next week.  Fixed by adding `source_url=best_pdf` to the relevant
`FetchResult` return statements.

### Session 4 — Safe Cracker Patterns B, C, D, E + Amalgamated Parishes

**User mapping:** The user provided a complete manual survey of all 51 parishes in
Derry Diocese, discovering that sites use six distinct URL date patterns.

**New patterns added to `rewrite_date_url()` in `harvester/utils.py`:**

| Code | Pattern | Regex | Example parish |
|------|---------|-------|----------------|
| B | `D-M-YY` | `_D_M_YY_RE` | Limavady: `5-4-26.pdf` → `12-4-26.pdf` |
| C | ISO `YYYY-MM-DD` + `/YYYY/MM/` dir | `_ISO_RE` + dir update | Clonmany: `2026-04-12.pdf` → `2026-04-19.pdf` |
| D | `DD-Month-YYYY` slug + `/YYYY/MM/` dir | `_SLUG_DATE_RE` + dir | Bellaghy: `12-April-2026.pdf` |
| E | `[YYYY-M-D]` bracketed | `_BRACKETED_ISO_RE` | Greenlough: `[2026-4-12].pdf` |

Pattern D was previously split across `rewrite_date_url()` (DDMMYY only) and
`rewrite_wp_url()` (WordPress slug + dir).  These are now **unified** into a single
`rewrite_date_url()` function that tries all patterns in order (A → C → B → D → E).
The separate `rewrite_wp_url()` is kept in `utils.py` for backwards compatibility
but the fetcher now calls only `rewrite_date_url()`.

**Amalgamated parish deduplication:** Several Derry parishes share one bulletin.
`parishes/derry_diocese.txt` now marks the duplicate URLs as comments so the app
never downloads the same bulletin twice:
- Ballinascreen ↔ Desertmartin
- Melmount ↔ Camus (Strabane)
- Waterside ↔ Strathfoyle
- St Eugene's Cathedral ↔ Longtower (Templemore)
- Three Patrons ↔ Pennyburn / Carnhill / Galliagh
- Cappagh ↔ Killyclogher

**Future scaling:** A `scout.py` tool is planned to auto-discover parish websites
from a diocesan directory page (e.g. `downandconnor.org/parishes-ministries/`) and
automatically identify which of the A–F patterns each parish uses.  See
`CONVERSATION_LOG_STRATEGY.md` for full design details.

**OCR strategy for 26 dioceses:** At ~24,000 pages/month, third-party OCR (DocStrange/
Nanonets) is too expensive.  Recommended approach: `pymupdf4llm` (free, runs on
GitHub Actions) or `gpt-4o-mini` vision (~$2–3/month for all 26 dioceses).

### Session 5 — URL Evidence Log + Stale Placeholder Fixes (2026-04-12)

**User action:** Provided a manually verified list of real bulletin URLs found on
each Derry Diocese parish website.  This is the most complete evidence set gathered
so far, covering ~20 parishes with multiple dated examples per parish.

**Key discoveries from the URL evidence log:**

1. **Stale placeholder URLs fixed** — `derry_diocese.txt` previously listed
   `dmaparish.com/pdf/310825.pdf`, `culdaffparish.com/pdf/310825.pdf`,
   `fahanparish.com/pdf/310825.pdf`, and `cappaghparish.com/pdf/310825.pdf`.
   The `310825` filename (= 31 August 2025) was an old placeholder that was never
   updated.  These have been replaced with their real current URLs.

2. **New Pattern H discovered — Banagher numeric ID:**
   `banagherparish.com/files/9/Newsletters/384/Bulletin---Divine-Mercy-Sunday---12th-April-2026`
   The path contains a sequentially incrementing integer ID (382, 383, 384...).
   Each week the ID goes up by 1.  The predictor should try `last_known_ID + 1`
   as its first prediction for this parish.  This is a new pattern not previously
   in `rewrite_date_url()` — it needs to be added to `harvester/utils.py`.

3. **Desertmartin confirmed STALE** — `desertmartinparish.com` last updated
   March 2025.  Already commented out in `derry_diocese.txt` (amalgamated with
   Ballinascreen), but the staleness is now confirmed.

4. **Cappagh 2025 content warning** — `cappaghparish.com/pdf/120426.pdf` has a
   2026 filename but the bulletin content inside is from 2025.  The AI verifier
   (Stage 2) should catch this, but it is noted here as a known anomaly.

5. **Iskaheen uses JPEG images** — `iskaheenparish.com/bulletin` publishes the
   bulletin as a `.jpg` image, not a PDF.  The harvester cannot meaningfully
   convert a scanned JPEG to a searchable PDF.  The reader should be given a
   direct link to the bulletin page instead.

6. **Star of the Sea (Magilligan) SSL error** — main site has an SSL certificate
   error.  Bulletin is on Google Drive.  Google Drive links do not follow a
   predictable date pattern; this parish requires a manual check each week.

7. **Clonleigh (Strabane Pastoral Area) HTML bulletins** — bulletins are WordPress
   post pages, not PDFs.  The harvester should scrape the text and convert to PDF,
   or failing that, provide the reader with a clickable link to the dated post.

**New file created:** `parishes/derry_diocese_bulletin_urls.txt` — a manually
verified evidence log of all known bulletin URLs grouped by parish, with pattern
codes annotated.  The predictor reads this file to seed its memory bank for
parishes that have never been run before.

**Files changed this session:**
- `parishes/derry_diocese_bulletin_urls.txt` — CREATED (new evidence log)
- `parishes/derry_diocese.txt` — UPDATED (stale 310825 placeholders replaced)
- `AI_HISTORY.md` — UPDATED (this session recorded)

**TODO from this session (not yet implemented in code):**
- Add Pattern H (Banagher numeric ID) to `harvester/utils.py`
- Seed `parish_profiles.json` with `last_success_url` values from the evidence log
  so the predictor fires immediately on first run without needing a prior success
- Switch `MODEL_NAME` from `gpt-4o` to `gpt-4o-mini` in `harvester/config.py`
- Remove stale duplicate keys (`_310825` variants) from `parish_profiles.json`