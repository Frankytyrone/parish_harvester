# AI Conversation Log — 2026-05-23: Content Script World Fix

**Date:** 2026-05-23
**Login:** @Frankytyrone
**Repo:** Frankytyrone/parish_harvester

---

## Plain-English summary

The AI chatbot in the floating toolbar could never see the saved Gemini key because the toolbar's code was running in the wrong JavaScript "world". Chrome does not let scripts in the MAIN world read from the extension's storage, so even though the Gemini key was safely saved in Settings, the toolbar kept showing the orange "Add your Gemini API key" banner. Moved it back to the correct world (ISOLATED). Also fixed the diagnostic logger so it actually records what happens (it now saves to storage instead of an in-memory variable that disappeared every time).

## What was wrong

`extension/manifest.json` had two `content_scripts` entries:

1. `ai_help.js` + `content.js` — running in `MAIN` world with `run_at: document_start`
2. `isolated.js` — running in `ISOLATED` world

Scripts running in the MAIN world share the page's JavaScript context and **cannot access `chrome.storage.local`**. So the toolbar's call to read the Gemini API key always returned nothing. That is why the orange banner stayed even though the key was right there.

## What was fixed

### Files touched

- `extension/manifest.json` — merged into a single ISOLATED-world entry (`ai_help.js`, `isolated.js`, `content.js`) with `run_at: document_idle`. Version bumped from **1.30.97** → **1.30.98**.
- `extension/background.js` — updated `_injectTrainerScripts` to inject all three files in ISOLATED world (no more MAIN injection).
- `extension/ai_help.js` — the ring-buffer logger now persists entries to `chrome.storage.local` under key `ph_ai_help_log` (capped at 50 entries). Each entry: `{ ts, attempt, succeeded, errorMessage }`.
- `extension/popup.js` — the "Copy diagnostic info" button now reads `ph_ai_help_log` directly from storage instead of trying to dispatch a message to the active tab (which was the reason for the "(unavailable on this tab)" line).
- `extension/content.js` — updated comment about world context.
- `test_extension_messaging.py` — added three new tests:
  1. No `"world": "MAIN"` in any content_scripts entry.
  2. Exactly one content_scripts entry covering `<all_urls>`.
  3. `ph_ai_help_log` key referenced in both `ai_help.js` (writer) and `popup.js` (reader).

## Test results

`python -m unittest test_extension_messaging` → **12 tests, all OK**.

## Hand-off note to next AI

1. Tell Franky to reload the extension in Brave at `brave://extensions` → click the ↻ refresh icon on Parish Trainer.
2. Open any parish website, click the floating toolbar's **🤖 AI Help** section, click **🔍 Analyse this page**. Gemini should reply within a few seconds.
3. After using AI Help, open the popup (click the Parish Trainer icon in the toolbar), run **Diagnostics**, and copy the dump. You should now see real log entries under "Recent AI Help log entries (last 5):" instead of "(unavailable on this tab)".
4. The release workflow and Brave auto-update are still pending — Franky needs to re-trigger the release after merging this PR. The stuck run `26333000751` should be checked; if it is still queued, disable/re-enable Actions.
5. Do NOT touch `.github/workflows/harvest.yml` (PR #185) or the release workflow until asked.
