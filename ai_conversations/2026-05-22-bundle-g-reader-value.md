# AI Conversation Log — 2026-05-22 (Bundle G: Reader Value)

## Date / Login / Repo
2026-05-22 — `Frankytyrone` — `Frankytyrone/parish_harvester`

## Summary (real win vs workaround)
- Real fix: per-parish summary JSON and weekly diff JSON are now generated during OCR page build from one shared OCR text read.
- Honest limitation: AI summaries only appear when `MISTRAL_API_KEY` is configured; otherwise files are still written with `bullets: null` and a transparent error.
- Real fix with best-effort caveat: weekly diffs compare against prior viewer pages in a ±3 day window around one week earlier; sparse archive means expected `no_prior_bulletin_found` notes.
- Real fix with cap: `docs/search-index.json` is generated from bulletin archive OCR text and capped at 5 MB by dropping oldest documents first.

## Files added / changed
- Added: `harvester/ai_summaries.py`
- Added: `harvester/weekly_diff.py`
- Added: `docs/search/index.html`
- Added: `test_ai_summaries.py`
- Added: `test_weekly_diff.py`
- Added: `ai_conversations/2026-05-22-bundle-g-reader-value.md`
- Changed: `ocr/generate_bulletin_pages.py`
- Changed: `harvester/manifest_builder.py`
- Changed: `docs/index.html`

## Caveats
- Mistral summary cost scales with parish count (about 150 API calls/week if all parishes run).
- Diff output is empty with note `no_prior_bulletin_found` when no earlier bulletin is found in the date window.
- Search index keeps only first 4,000 OCR chars per document and enforces a 5 MB total cap.

## Hand-off note
Bundles A–G complete. Remaining §11 ideas: F8 translations, F9 push bot, F10 liturgical highlights. Also a future bundle to address Snippet C's missing `*-latest.html` URL noted in Bundle D.
