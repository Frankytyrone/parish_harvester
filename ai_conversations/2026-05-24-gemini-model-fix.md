# AI Conversation Log — 2026-05-24: Gemini model fix for floating toolbar AI Help

**Date:** 2026-05-24  
**Login:** @Frankytyrone  
**Repo:** Frankytyrone/parish_harvester

---

## Plain-English summary

The Gemini API key is working, but AI Help in the floating toolbar was still failing because the extension was calling an outdated model name at the `v1beta` endpoint.

This update switches AI Help from `gemini-1.5-flash` to `gemini-2.5-flash`, adds a clear user-facing fallback when a model is unavailable, and improves `ph_ai_help_log` details so debugging now includes model, endpoint version, response status, and the first part of Google’s error text.

## Decisions made

1. Keep the fix minimal and local to extension AI Help path only (`extension/ai_help.js`).
2. Add explicit constants for Gemini model + endpoint version to avoid future hardcoded drift.
3. On 404/model-not-supported responses, surface plain-English message:
   - `Gemini model unavailable in this build. Please update the extension.`
4. Extend test coverage in `test_extension_messaging.py` for:
   - old hardcoded model string removed
   - new model constant present
   - enhanced logging metadata fields present
5. Bump extension patch version from `1.30.99` → `1.30.100`.

## Files touched

- `extension/ai_help.js`
- `test_extension_messaging.py`
- `extension/manifest.json`
- `ai_conversations/2026-05-24-gemini-model-fix.md`

## Standing requests / open backlog carried forward

- Do not touch release workflow in this task.
- Do not touch harvest workflow in this task.
- Do not touch recipe/parish data.
- Do not mark any parish inactive.

## Hand-off note to next AI

After this merges, Franky must reload the extension at `brave://extensions` (↻ Parish Trainer) and then re-test **🤖 AI Help** on a real parish page.

If AI Help still fails, copy popup diagnostics and check new `ph_ai_help_log` entries for:
- model attempted
- endpoint version
- HTTP status
- Google error text preview
