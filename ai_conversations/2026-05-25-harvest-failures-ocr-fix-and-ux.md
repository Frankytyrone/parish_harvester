# 2026-05-25 — Harvest failures, OCR provider fix, homepage slimming, and diocese UX updates

## Summary of changes

- Fixed the two blocking test failures in `extension/manifest.json`:
  - Updated `update_url` to `https://frankytyrone.github.io/parish_harvester/updates.xml`
  - Added `"world": "MAIN"` to the `content_scripts` block

- Reworked OCR provider fallback in `ocr/convert_bulletin.py`:
  - Primary: **Mistral** (`MISTRAL_API_KEY`) on the PDF directly
  - Fallback: **Gemini** (`GEMINI_API_KEY`) via `google-generativeai` using `gemini-1.5-flash` on PDF-to-image pages
  - Final fallback: **OpenAI** (`OPENAI_API_KEY`) via `gpt-4o-mini`
  - Removed GitHub Models OCR path from the chain

- Updated dependency and workflow wiring:
  - Added `google-generativeai` to `requirements.txt`
  - Added `GEMINI_API_KEY` to harvest workflow env in `.github/workflows/harvest.yml`
  - Added `GEMINI_API_KEY` to OCR workflow env in `.github/workflows/ocr-bulletin.yml`

- Slimmed homepage (`docs/index.html`):
  - Removed the large top card grid section
  - Kept the compact diocese parish-list sections and footer links

- Added UX improvements across **all 26** diocese pages under `docs/dioceses/*/index.html`:
  - PDF panel now includes **⤢ Open in new tab** button
  - OCR panel now includes **⤢ Open in new tab** button
  - Added OCR search bar with real-time highlight (`highlightOCR`) and matching teal styling
  - Ensured pages without live OCR/PDF content still expose the same viewer controls and fallback links

- Updated template support for future generated diocese pages:
  - `harvester/templates/diocese_page.html`
  - `harvester/page_renderer.py`

- Updated test expectations in `test_train_matching.py` for:
  - OCR fallback order (Mistral → Gemini → OpenAI)
  - Gemini secret wiring in OCR workflow
