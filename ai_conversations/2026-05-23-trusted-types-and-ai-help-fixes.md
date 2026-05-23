# AI Conversation Log — 2026-05-23: Trusted Types + AI Help tab selection + better diagnostics

**Date:** 2026-05-23  
**Login:** @Frankytyrone  
**Repo:** Frankytyrone/parish_harvester

---

## Plain-English summary

This PR fixes three real blockers in the extension:

1. Brave Trusted Types errors were breaking parts of the floating toolbar. I replaced risky `innerHTML = ...` usage in the extension UI code with safe DOM-building/clear methods.
2. AI Help now avoids extension/internal tabs when trying to analyse a page. If the console tab is focused, it now looks for a real parish page tab and gives a clear message if none is open.
3. The popup Diagnostics copy output is now much more useful for remote troubleshooting, including extension/browser info, tab type, key presence checks, memory keys, and recent AI Help event logs.

I also bumped extension version from **1.30.95** to **1.30.96**.

## Files touched

- `extension/content.js`
- `extension/ai_help.js`
- `extension/sidepanel.js`
- `extension/popup.js`
- `extension/popup.html`
- `extension/manifest.json`
- `test_extension_messaging.py`
- `ai_conversations/2026-05-23-trusted-types-and-ai-help-fixes.md`

## Hand-off note for next AI

- Brave still will not auto-update until the release workflow is restored and a `.crx` is built.
- `Release Parish Trainer extension` run id `26333000751` may still be wedged; do not re-trigger the release until it is gone.
- PR #185 (harvest YAML fix) must be merged before re-enabling the release workflow.
