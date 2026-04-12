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
### Session 5 — Evidence File, Profile Fixes & Pattern H (Banagher)

**Date:** 2026-04-12

**User action:** Provided a complete manual survey file (`parishes/derry_diocese_bulletin_urls.txt`)
containing the real current bulletin URLs for every active Derry Diocese parish as of 12 April 2026.
This gives the predictive engine a verified starting point.

**Problems identified and fixed:**

1. **Stale `310825` placeholder URLs** — Four entries in `derry_diocese.txt` still had
   `310825` (= 31 Aug 2025) in their URLs.  Fixed by replacing with real `120426` URLs
   for dmaparish, culdaffparish, fahanparish, and cappaghparish.

2. **Wrong JSON keys in `parish_profiles.json`** — Three profile keys contained
   stale date fragments or URL path fragments that meant the predictive engine could
   never match them:
   - `dmaparish_310825` → renamed to `dmaparish`
   - `culdaffparish_310825` → renamed to `culdaffparish`
   - `banagherparish_information` → renamed to `banagherparish`

3. **Banagher `last_success_url` was a Christmas 2025 bulletin** — The stored URL
   pointed to newsletter #268 (4th Sunday of Advent).  Corrected to #384
   (Divine Mercy Sunday, 12 April 2026).

4. **Bellaghy profile showed 8 consecutive failures** — The real current URL
   `bellaghyparish.com/wp-content/uploads/2026/04/Newsletter-12-April-2026-1.pdf`
   was confirmed working.  Profile reset to reflect success.

**New pattern discovered — Pattern H (Sequential Newsletter Number):**

Banagher parish does not use a date in its URL.  It uses a sequential issue number
(`/Newsletters/384/`) followed by a free-form title slug that cannot be predicted.
Two new helper functions were added to `harvester/utils.py`:
- `extract_newsletter_number(url)` — extracts the issue number
- `rewrite_newsletter_number_url(url, increment=1)` — increments the number and
  strips the unpredictable slug, returning a base URL to crawl from

**Cappagh warning noted:** User confirmed that even though `cappaghparish.com/pdf/120426.pdf`
returns a file, the content is stale (from 2025).  The fetcher's 50 KB minimum check
should catch fake PDFs, but the date-in-content check (via OCR/text extraction) is the
only reliable guard against stale-content PDFs.

**Iskaheen note:** `iskaheenparish.com/bulletin` serves the bulletin as a JPEG image,
not a PDF.  The fetcher currently cannot handle this.  A future task is to detect
`<img>` tags on bulletin pages and download+convert JPEG bulletins to PDF.

**Star of the Sea note:** `staroftheseacathedral.com` uses a Google Drive link for the
bulletin.  The Google Docs Viewer bypass (Rule 1, Session 1) should handle this —
the real PDF URL is embedded in the Drive viewer query string.  Entry remains commented
out in `derry_diocese.txt` due to the SSL certificate error on the main site.

**Clonleigh HTML bulletin note:** `clonleighparish.com` publishes an HTML bulletin page
(not a PDF).  If the fetcher cannot convert it to PDF, the user requests that the
reader be shown a direct link opening in a new browser tab.  This is a future UI task.

---

### Session 6 — AI Verifier Removed, 9 Failing Parishes Fixed

**Date:** 2026-04-12

**User decision:** Remove the GPT-4o AI verifier. It hits the GitHub Models free
tier rate limit (50 calls/day) before half the parishes are processed. Since the
bulletin date is already encoded in the URL for most parishes, vision verification
adds no value and wastes the entire daily API quota.

**Fix:** `--skip-verify` flag added. Rate-limit detection added to stop verification
mid-run rather than crashing with 429 errors. `MODEL_NAME` changed from `gpt-4o` to
`gpt-4o-mini` in `harvester/config.py` for if/when it is re-enabled.

**9 parishes fixed this session:**

1. **Bellaghy** — ERR_ABORTED on /current-newsletter/ bypassed. Predictive URL
   engine now goes directly to the WP uploads PDF (Pattern D). Profile already had
   the correct `last_success_url`; Pattern D handles the `-1` issue-number suffix.

2. **Claudy** — Listing page timeout bypassed. Bulletins are DOCX files at
   `parishofclaudy.com/onewebmedia/NEWSLETTER D-M-YY.docx`. Added
   `_download_docx_as_pdf()` to `harvester/fetcher.py` — converts via LibreOffice
   headless with python-docx fallback.

3. **Iskaheen** — Bulletin is a JPEG image (`1.jpg`). Added image detection scan
   inside `_scrape_html_to_pdf()` and `_download_image_as_pdf()` using Pillow.
   Pattern F (YYYY/MM directory update) now also applies to JPEG/image URLs.

4. **Clonleigh (Strabane)** — HTML WordPress post slug. Pattern G added to
   `rewrite_date_url()`: detects `/YYYY/MM/DD/slug/`, date-shifts +7 days, strips
   slug to return `/YYYY/MM/DD/` archive URL. `_find_dated_bulletin_link()` updated
   to also recognize `/YYYY/MM/DD/` path dates (not just slug dates). The fetcher
   predictive section now handles directory-style URLs by calling
   `_find_dated_bulletin_link()` + `_scrape_html_to_pdf()` instead of `_download_pdf()`.

5. **Limavady** — Listing page timeout bypassed. Pattern B prediction now goes
   directly to the PDF in `/onewebmedia/`. Profile updated with `url_pattern: "B"`.

6. **Waterside** — Pattern A regex already handled the `oo` suffix correctly (the
   `(?!\d)` lookahead allows non-digit suffixes). Profile updated with the correct
   `last_success_url` pointing to the real PDF.

7. **Three Patrons** — Pattern H (sequential number) confirmed. Same system as
   Banagher. `_NEWSLETTER_NUM_RE` regex updated to match both `/Newsletters/NNN/`
   (Banagher) and `/Weekly-Bulletins/NNN/` (Three Patrons). `rewrite_newsletter_number_url()`
   now preserves the category name. Pattern H integrated into `_fetch_inner()`.

8. **Sion Mills** — Marked as "no consistent online bulletin". Profile notes updated.

9. **Ballinascreen** — `_find_dated_bulletin_link()` now also checks for `/YYYY/MM/DD/`
   path dates in URLs, improving detection of WP date-based post links.
