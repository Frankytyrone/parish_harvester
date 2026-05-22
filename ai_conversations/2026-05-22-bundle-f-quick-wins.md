# AI Conversation Log — 2026-05-22 (Bundle F: Quick Wins)

## Date / Login / Repo
2026-05-22 — `Frankytyrone` — `Frankytyrone/parish_harvester`

## Summary (real wins vs workaround)
- Real fix: harvest ordering now prioritises parishes with the highest consecutive failure counts first, with an escape hatch (`PARISH_HARVEST_NO_PRIORITY=1`) for old-order debugging.
- Real fix: manifest build now also publishes `docs/reliability.json` and a static badges page to surface parish reliability tiers from learned recipe data (with failure-count fallback).
- Real fix: a new optional email digest workflow can send "Bulletin of the Week" after successful harvest runs when SMTP secrets are configured.
- Real fix with honest limitation: per-diocese RSS files are now generated, but each feed currently contains only the latest item because there is no persistent item archive yet.

## Files added / changed
- Added: `harvester/priority_queue.py`
- Added: `test_priority_queue.py`
- Added: `docs/badges/index.html`
- Added: `docs/EMAIL_DIGEST_SETUP.md`
- Added: `.github/workflows/email-digest.yml`
- Added: `ai_conversations/2026-05-22-bundle-f-quick-wins.md`
- Changed: `main.py`
- Changed: `harvester/manifest_builder.py`
- Changed: `test_manifest_builder.py`
- Changed: `docs/index.html`

## Caveats
- Email digest needs SMTP secrets (`SMTP_SERVER`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `DIGEST_FROM`, `DIGEST_TO`) or it cleanly warns and exits.
- RSS output is single-item per diocese for now; multi-item history requires a persistent archive source in a future bundle.
- Priority queue depends on `parishes/consecutive_failures.json` being maintained by the existing pipeline.
- Reliability is best-effort: learned recipe stats are used first; missing stats fall back to consecutive failures, otherwise tier is `grey`.

## Hand-off note
Bundles A–E complete. F adds quick wins. Next session: pick from remaining §11 ideas (OCR search F5, AI summaries F6, week-diff F7, translations F8, push bot F9, liturgical highlights F10).
