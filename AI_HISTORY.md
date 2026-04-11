# AI_HISTORY.md — Parish Bulletin Harvester Rules & Conversation Log

This file records the rules established through conversations with the user and
the AI assistant.  Any AI agent working on this codebase should read this file
before making changes, so that hard-won lessons are never forgotten.

---

## The Three Core Rules

### Rule 1: Never Accept a PDF Smaller Than 30 KB

When a parish website cannot find a bulletin it often returns an HTML error page
(e.g. a "404 Not Found" page) but delivers it with a `.pdf` Content-Disposition
header.  The resulting file is valid PDF magic-bytes but only 2–14 KB in size —
completely useless.

**The Fix:** After every PDF download, check the file size.  If it is less than
30,000 bytes (30 KB), delete the file immediately, log a clear warning, and
continue searching other links.  This is implemented in `harvester/fetcher.py`
via `_is_real_pdf()` and the `_MIN_PDF_BYTES = 30_000` constant.

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
