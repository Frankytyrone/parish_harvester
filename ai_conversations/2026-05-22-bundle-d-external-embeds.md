# AI Conversation Log — 2026-05-22 (Bundle D: External Embeds)

## Date / Login / Repo
2026-05-22 — `Frankytyrone` — `Frankytyrone/parish_harvester`

## Summary (real fix vs workaround)
- Real fix delivered: a generated `docs/manifest.json` is now produced from harvest outputs so external websites can auto-resolve latest bulletin URLs via one stable endpoint.
- Real fix delivered: copy/paste embedding docs + runnable snippet examples page were added for non-technical handoff.
- Honest workaround note: Snippet C uses `derry-latest.html`, but that stable OCR URL does not exist yet because OCR pages are currently date-stamped; Snippet D/E (manifest-based) are the reliable auto-updating path.

## Files added / changed
- Added: `harvester/manifest_builder.py`
- Added: `test_manifest_builder.py`
- Added: `docs/EMBEDDING.md`
- Added: `docs/embed-examples.html`
- Added: `ai_conversations/2026-05-22-bundle-d-external-embeds.md`
- Changed: `main.py` (non-fatal manifest build call at end of harvest)
- Changed: `.github/workflows/harvest.yml` (includes `docs/manifest.json` in existing `git add -f` list)
- Changed: `docs/index.html` (added links to embedding docs/examples)

## Caveats
- GitHub Pages can cache updates for ~10 minutes after publish.
- jsDelivr can cache for up to 7 days.
- iOS Safari PDF iframes are unreliable; object/download fallback is safer on mobile-heavy sites.

## Hand-off note
Next bundle = PR-E (trim toolbar to 7 controls + GitHub Pages CSS facelift).
