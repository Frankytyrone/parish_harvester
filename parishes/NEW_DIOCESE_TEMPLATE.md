# How to Add a New Diocese

This guide explains how to add a new diocese to the Parish Bulletin Harvester.

## Overview

The harvester is **evidence-driven**: you provide real, manually verified bulletin
URLs, and the code does the date maths to predict where this week's bulletin will be.

No crawling, no guessing.  You already know where every bulletin is — the code
just needs 2–3 example URLs per parish to detect the pattern.

---

## Step 1 — Create the evidence file

Create `parishes/{diocese_name}_bulletin_urls.txt`.

Use the same format as `parishes/derry_diocese_bulletin_urls.txt`:

```
# --- Parish Name ---
# Pattern X: <description>
https://example.com/pdf/120426.pdf
https://example.com/pdf/050426.pdf
```

### Supported URL patterns

| Pattern | Format | Example |
|---------|--------|---------|
| **A** | `DDMMYY` | `carndonaghparish.com/pdf/120426.pdf` |
| **B** | `D-M-YY` | `limavadyparish.org/onewebmedia/5-4-26.pdf` |
| **C** | `YYYY-MM-DD` | `clonmanyparish.ie/wp-content/uploads/2026/04/2026-04-12.pdf` |
| **D** | `DD-Month-YYYY` slug | `bellaghyparish.com/.../Newsletter-12-April-2026-1.pdf` |
| **E** | `[YYYY-M-D]` | `greenlough.com/.../2nd_Sunday[2026-4-12].pdf` |
| **F** (static) | Fixed URL | `laveyparish.com/laveyparishbulletin.pdf` (same URL every week) |
| **H** | Sequential number | `banagherparish.com/files/9/Newsletters/384/Bulletin-...` |
| **clonleigh** | WP post (Saturday before Sunday) | `clonleighparish.com/2026/04/11/strabane-...-12th-april-2026/` |
| **greenlough** | Liturgical name + `[YYYY-M-D]` | `greenlough.com/publications/newsletter/Palm_Sunday[2026-3-29].pdf` |
| **html_link** | No PDF — link only | `melmountparish.com/parishnews.html` |
| **image** | JPEG/PNG converted to PDF | `iskaheenparish.com/wp-content/uploads/2026/04/1.jpg` |
| **docx** | Word document converted to PDF | `parishofclaudy.com/NEWSLETTER 12-4-26.docx` |

### Rules

1. **Most recent bulletin first** in each parish group.
2. Provide **2–3 example URLs** so the code can verify the pattern.
3. Comments after `#` are ignored, except for:
   - `# --- Parish Name ---` headers (required to start a parish group)
   - `# Pattern X:` to tell the code which pattern to use
   - `# key: xxx` to override the auto-derived parish key (needed for CDN/Google Drive URLs)
   - `# html_link:` to mark parishes with no downloadable bulletin
   - `# image:` for JPEG/PNG bulletins
   - `# docx:` for Word document bulletins

---

## Step 2 — Create the contacts file (optional)

Create `parishes/{diocese_name}_contacts.json` to provide display names,
website URLs, and Facebook links.  These appear in placeholder pages in the
mega PDF for parishes where the bulletin could not be downloaded.

```json
{
  "ardmoreparish": {
    "display_name": "Ardmore Parish",
    "website": "http://www.ardmoreparish.com",
    "facebook": null
  }
}
```

The key must match the auto-derived key from the evidence file URL
(first path component of the domain, without `www.` and TLD).

---

## Step 3 — Run

```bash
python main.py --diocese your_diocese_name
```

The harvester will:
1. Parse `parishes/your_diocese_name_bulletin_urls.txt`
2. Calculate this week's URL for each parish using date maths
3. Download all bulletins (10 concurrent)
4. Stitch into one A–Z mega PDF
5. Write `Bulletins/report.json`

---

## Example: Adding a new Pattern A parish

Your parish publishes at:
- `https://newparish.com/pdf/120426.pdf` (12 April 2026)
- `https://newparish.com/pdf/050426.pdf` (5 April 2026)

Add to the evidence file:
```
# --- New Parish ---
# Pattern A: DDMMYY
https://newparish.com/pdf/120426.pdf
https://newparish.com/pdf/050426.pdf
```

The harvester will automatically calculate `190426.pdf` for 19 April 2026.

---

## Example: Adding an HTML-only parish

```
# --- Sion Mills ---
# html_link: no PDF available — link shown in mega PDF
http://www.parishofsionmills.com/news.html
```

---

## Example: Adding a Pattern H (sequential number) parish

```
# --- New Patrons ---
# Pattern H: sequential number — increments by 1 each week
https://newpatronsparish.org/files/10/Bulletins/42/Sunday-12th-April-2026
https://newpatronsparish.org/files/10/Bulletins/41/Sunday-5th-April-2026
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Parish shows as "failed" every week | Check the URL is still live; update the example URL |
| Wrong date being predicted | Make sure the most recent URL is listed **first** |
| CDN URL doesn't produce a stable key | Add `# key: myparishname` comment |
| Parish has a Google Drive link | Use `# html_link:` and link to the Drive URL |
