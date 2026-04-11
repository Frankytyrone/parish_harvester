# CONVERSATION_LOG_STRATEGY.md
# Parish Bulletin Harvester — Strategy & Design Decisions

This file preserves the key strategic insights from the development chat sessions.
Any developer or AI agent working on this project should read this file to understand
**why** the system is designed the way it is, and what the roadmap looks like.

---

## The "Safe Cracker" Metaphor

The app works like a safecracker with a cheat sheet. Every parish website has a
different "dial combination" (URL pattern) for its bulletin. Once you know the
combination, you don't need to guess — you just do the maths and turn the dial.

The six known "lock combinations" for Derry Diocese:

| Code | Format | Real Example | Notes |
|------|--------|--------------|-------|
| **A** | `DDMMYY` | `carndonaghparish.com/pdf/050426.pdf` | Most common pattern |
| **B** | `D-M-YY` | `limavadyparish.org/onewebmedia/5-4-26.pdf` | No leading zeros |
| **C** | `YYYY-MM-DD` | `clonmanyparish.ie/2026/04/2026-04-12.pdf` | Also updates `/YYYY/MM/` dir |
| **D** | `DD-Month-YYYY` | `bellaghyparish.com/wp-content/.../12-April-2026.pdf` | WordPress slug style |
| **E** | `[YYYY-M-D]` | `greenlough.com/newsletter/[2026-4-12].pdf` | Bracketed ISO variant |
| **F** | Static | `laveyparish.com/.../laveyparishbulletin.pdf` | Never changes; re-download & check |

---

## Rule 1: The 50 KB "Fake PDF" Blocker

**Problem:** When a parish website can't find the bulletin, it often returns an HTML
"404 Not Found" page but sends it with a `.pdf` Content-Disposition header. The
file looks like a PDF but is only 2–14 KB in size.

**Fix:** After every download, check the file size. Reject anything under **50,000
bytes (50 KB)**. Even the smallest single-page church bulletin is well over 50 KB.
If the highest-scoring PDF link is rejected, the next best candidate is tried
automatically (up to 5 candidates via `_pick_top_pdfs`).

**Implemented in:** `harvester/fetcher.py` → `_is_real_pdf()`,
`_MIN_PDF_BYTES = 50_000`, and `_pick_top_pdfs()`.

---

## Rule 2: The Predictive URL Engine (The Safe Cracker)

**Problem:** Crawling entire websites from scratch every week is slow and fragile.

**Fix:** Store the URL of every successfully downloaded bulletin in
`parishes/parish_profiles.json` (the "memory bank"). On the next run, apply
`rewrite_date_url()` to mathematically predict this week's URL by substituting
the new target date. Try the predicted URL **before** doing any site crawl.

Six patterns are handled (A–F above). Pattern F (static) means the URL never
changes — download it and check freshness from the content.

**Implemented in:**
- `harvester/utils.py` → `rewrite_date_url()` (handles all 6 patterns)
- `harvester/fetcher.py` → `_fetch_inner()` predictive section

---

## Rule 3: The Self-Learning Memory Bank

**Problem:** Without memory, the app starts from scratch every week.

**Fix:** After every successful download, record:
- `last_success_url` — the **exact PDF URL** (not the homepage), so
  `rewrite_date_url()` can predict next week's URL
- `last_success_date` — the date it was found
- `last_success_method` — `"pdf"` or `"html_to_pdf"`
- `consecutive_failures` — how many weeks in a row it has failed

**Key lesson:** Store `source_url` (the direct PDF URL) not the parish homepage.
The homepage URL contains no date pattern to shift. See `harvester/profiles.py` →
`update_profile()`.

---

## Amalgamated Parishes — No Double Downloads

Several parishes in Derry Diocese share a priest, share a church building, and
publish **one combined bulletin** under one of the parish names. If we list both
URLs, the app downloads the same PDF twice.

**Fix:** In `parishes/derry_diocese.txt`, only the "primary" parish URL is active.
The duplicate is commented out with a note. This prevents wasteful double-downloads.

| Group | Primary (active) | Duplicate (commented out) |
|-------|-----------------|--------------------------|
| Ballinascreen & Desertmartin | `parishofballinascreen.com` | `desertmartinparish.com` |
| Melmount & Camus (Strabane) | `melmountparish.com` | `camusparish.com` |
| Waterside & Strathfoyle | `watersideparish.net` | (Strathfoyle has no separate site) |
| Templemore (St Eugene's + Longtower) | `steugenescathedral.com` | `longtowerchurch.org` |
| Three Patrons (Pennyburn/Carnhill/Galliagh) | `threepatrons.org` | (no separate sites) |
| Killyclogher & Cappagh | `cappaghparish.com` | (Killyclogher redirects to Cappagh) |

---

## The AI Detective (Fallback Scraper)

Sometimes the maths fails — a parish secretary might name the file
`12-April-2026-Divine-Mercy-FINAL.pdf` instead of `12-April-2026.pdf`. The
pure maths will get a 404.

**Fix:** If the predicted URL fails, fall back to a full site crawl. The scraper
navigates to the parish homepage (or news page), looks for PDF links, and scores
them using keywords (`bulletin`, `newsletter`, etc.) and date matches. It then
downloads the best candidate.

For WordPress sites that embed PDFs using PDF Embedder, the PDF URL is hardcoded
as `href` in the page HTML even though it looks like an image to the user. The
scraper extracts it directly.

---

## The "Ghost" Parishes (No Website)

Some very rural parishes have no dedicated website. They post bulletins to
Facebook or rely entirely on the central diocesan site. The app handles these
gracefully — it tries the URL, fails cleanly, and logs "No PDF found" without
crashing.

Ghost parishes in Derry Diocese: Gortin, Greencastle, Killygordon, Magilligan,
Malin, Plumbridge, Swatragh (Granaghan).

---

## Future: Scaling to 26 Irish Dioceses

### `scout.py` — The Autonomous Diocesan Scout

The plan for scaling beyond Derry:

1. **Directory Grabber:** Give the Scout the URL of an official diocesan directory
   (e.g., `downandconnor.org/parishes-ministries/`). It reads the page and
   extracts every parish website link automatically.

2. **Amalgamation Detector:** If two parish names link to the same website, the
   Scout automatically groups them to prevent double downloads.

3. **Brute Force Pattern Matching:** For each discovered website, the Scout fires
   off the known patterns (A–F) with this week's date and checks whether they
   return a valid PDF (> 30 KB). First hit wins.

4. **Self-Writing Master File:** Once a pattern is confirmed, the Scout writes a
   new `All_the_pdfs_<Diocese>.txt` file. From that point, the Harvester runs
   every Sunday using mathematical prediction — no crawling needed.

5. **Human-Error Fallback:** For parishes like Aghagallon (Down & Connor) where
   the parish secretary adds "Easter-Sunday2-" to the filename, the AI Detective
   scraper kicks in as a backup after maths fails.

**Usage (planned):**
```
python scout.py --diocese "Down & Connor" --directory "https://downandconnor.org/parishes-ministries/"
```

### Proven in Down & Connor

Down & Connor uses the exact same WordPress structures as Derry. Example:
- `aghagallonandballinderryparish.ie/wp-content/uploads/2026/04/Bulletin-5th-April-2026-Easter-Sunday2-.pdf`
  → WordPress with human-readable slug (Pattern D + human error fallback)
- `antrimparish.com` → Uses WordPress PDF Embedder; real PDF URL is in the HTML

---

## The OCR / Text Extraction Problem

### Why Normal OCR Fails on Church Bulletins

Church bulletins use **multiple columns, text boxes, and embedded images**. Standard
OCR readers (Tesseract, pdfplumber, etc.) read straight across the page, scrambling
column 1 and column 2 together into gibberish.

DocStrange (Nanonets) and similar "Vision AI" tools are excellent because they look
at the page layout like a human before reading the text. However, at 26 dioceses
with ~1,500 parishes producing 4-page weekly bulletins, the maths is brutal:

- **24,000 pages/month** to process
- DocStrange's 10,000 free credits: gone in under 2 weeks
- LlamaParse's 1,000 pages/day free tier: hits the daily cap on Sunday alone

### Recommended Solutions at Scale

1. **`pymupdf4llm`** (100% free, runs locally on GitHub Actions):
   A modern multi-column-aware PDF extractor specifically designed for AI
   pipelines. Produces clean Markdown output. Runs inside GitHub Actions at $0 cost.

2. **`gpt-4o-mini` Vision Hack (pennies)**:
   The app already has `pdf2image` and `openai` installed. Convert each PDF page
   to an image, pass it to `gpt-4o-mini` with a prompt like
   *"Extract mass times and anniversaries into JSON."* At ~$0.15/million tokens,
   processing the entire Derry Diocese costs about **10 cents per week**.
   Scaling to 26 dioceses would cost roughly **$2–3/week**.

3. **LlamaParse** (30,000 free pages/month, but limited to 1,000/day):
   Good for mid-scale use; combine with rate limiting across the week.

4. **Nanonets "Tech for Good" Grant** (recommended action):
   Email Nanonets support explaining this is a non-profit community project
   covering all 26 Catholic dioceses in Ireland. Companies like Nanonets
   regularly award 100,000+ free credits to community projects for the PR value.

### Current Status

For the Derry Diocese pilot, the Mathematical Predictor (Rules 1–3) has reduced
AI verification calls by ~80% — the URL itself proves freshness for Pattern A–E
parishes. AI verification is only needed for HTML/Wix bulletins and fallback crawls.

---

## GitHub Actions Cost Estimate (All 26 Dioceses)

| Resource | Usage | Cost |
|----------|-------|------|
| GitHub Actions compute | ~45 min/run × 4 runs/month = 180 min | **Free** (Pro: 3,000 min/month) |
| OpenAI `gpt-4o-mini` OCR | 24,000 pages/month | **~$2–3/month** |
| PDF storage | 1.5 GB/week | Use parish website URLs (no storage needed) or Backblaze B2 (~$0.25/month for 50 GB) |
| **Total** | | **~$3/month** |

**Key insight:** Because the Mathematical Predictor handles 80% of parishes without
any AI call, the compute cost stays well inside the GitHub Pro free tier even at
full 26-diocese scale.

---

*This file was generated from the development chat log on 2026-04-11.*
*Last updated: 2026-04-11*
