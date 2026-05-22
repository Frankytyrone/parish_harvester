# 🗺️ Site Map — Parish Harvester Public Website

All URLs are at: `https://frankytyrone.github.io/parish_harvester/`

**Update this when adding new public URLs.**

| URL | What it's for | Auto-updated? | Added in bundle |
|-----|---------------|---------------|-----------------|
| `/` (index.html) | Dashboard — links to everything | ✅ Yes (each OCR run) | Bundle D |
| `mega_pdf/derry_mega_bulletin.pdf` | Derry Diocese — all parish PDFs in one file | ✅ Yes (weekly) | Bundle A |
| `mega_pdf/down_and_connor_mega_bulletin.pdf` | Down & Connor — all parish PDFs in one file | ✅ Yes (weekly) | Bundle A |
| `mega_pdf/index.html` | Tabbed PDF viewer — switch between dioceses | ✅ Yes (each OCR run) | Bundle D |
| `bulletins/index.html` | Archive index — browse all past OCR viewer pages | ✅ Yes (each OCR run) | Bundle D |
| `bulletins/<diocese>-YYYY-MM-DD.html` | Per-bulletin OCR viewer — text beside PDF | ✅ Yes (each OCR run) | Bundle D |
| `feeds/derry_diocese.xml` | RSS feed — Derry Diocese bulletins | ✅ Yes (weekly) | Bundle F |
| `feeds/down_and_connor.xml` | RSS feed — Down & Connor bulletins | ✅ Yes (weekly) | Bundle F |
| `calendars/derry.ics` | iCalendar — Derry parish events (subscribe in any app) | ✅ Yes (weekly) | Bundle I |
| `calendars/down_and_connor.ics` | iCalendar — Down & Connor parish events | ✅ Yes (weekly) | Bundle I |
| `calendars/all.ics` | iCalendar — all dioceses combined | ✅ Yes (weekly) | Bundle I |
| `search/` | Full-text search across all bulletin text | ✅ Yes (each OCR run) | Bundle E |
| `badges/` | Parish reliability scores (% successful harvests) | ✅ Yes (each harvest) | Bundle E |
| `EMBEDDING.md` | How to embed bulletins or feeds on your own site | ❌ Static | Bundle E |
| `embed-examples.html` | Copy/paste embed code examples | ❌ Static | Bundle E |
| `sitemap.html` | Visual card grid of every public page | ❌ Static (update manually) | Bundle I |
| `COST_DASHBOARD.md` | Traffic-light tracker: storage, AI, Actions minutes | ✅ Yes (each harvest) | Bundle I |
| `manifest.json` | Raw JSON: all parishes, dates, URLs (for developers) | ✅ Yes (weekly) | Bundle D |
| `reliability.json` | Raw JSON: per-parish success/failure stats | ✅ Yes (each harvest) | Bundle E |
| `search-index.json` | Search index (built by OCR pipeline) | ✅ Yes (each OCR run) | Bundle E |

---

*This file is hand-maintained. It's small, so that's fine.*
*When you add a new public URL (e.g. a new page in `docs/`), add a row here.*
