# AI Conversation Log — 2026-05-23: Release workflow stuck + AI Help in floating toolbar

**Date:** 2026-05-23
**Login:** @Frankytyrone
**Repo:** Frankytyrone/parish_harvester

---

## Summary

Continuation of the same day's work. Two parallel threads:

1. **Floating toolbar missing the Gemini AI Help button.** The Gemini chat panel
   from PR #183 was only added to the side panel, not to the in-page floating
   toolbar Franky actually uses while training parishes. Screenshot 2 showed
   "Page bridge not responding" in the popup; screenshot 3 confirmed the AI
   Help tab only exists in the side panel. A coding agent session was
   dispatched to add the same Gemini AI Help section directly into the
   floating in-page toolbar (`extension/content.js`), with shared logic
   factored out so the side panel and floating toolbar use the same code.

2. **`Release Parish Trainer extension` workflow run still stuck Queued for
   1+ hour.** Cancel button returned "Failed to cancel workflow" (screenshot 4).
   API confirms run id `26333000751` has been queued since 12:43 UTC with
   no runner ever assigned. The workflow YAML itself is fine. Suspected
   causes: (a) free-tier Actions minutes exhausted (earlier firewall
   warning mentioned `api.github.com/users/Frankytyrone/settings/billing/actions`
   being blocked), or (b) a wedged dispatch run that needs the
   "disable / re-enable Actions" reset.

---

## What was actually done this session

- Dispatched coding agent: **Add 🤖 AI Help (Gemini) to the floating in-page
  toolbar + carry over outstanding fixes**.
  - Primary: add real AI Help section to `extension/content.js`, refactor
    shared Gemini logic out of `sidepanel.js` into a shared helper, mirror
    UI (chat area, Ask input, Send, 🔍 Analyse this page, memory banner),
    re-use existing Gemini API key from `chrome.storage.local`, add
    `https://generativelanguage.googleapis.com/*` to `host_permissions` if
    needed, bump manifest patch version.
  - Secondary (only if small/safe): verify PR #184 fully fixed the "Fix now"
    diocese bug; improve "Page bridge not responding" to auto-retry once
    before erroring; ensure floating toolbar version reads from
    `chrome.runtime.getManifest().version`.
  - Explicit "do not touch": harvest.yml (PR #185 owns that), release
    workflow, recipe files, diocese data, do NOT mark any parish inactive.
- Saved this log file.

## What was NOT done (cannot do from chat)

- I cannot cancel a stuck Actions run from here. Only the repo owner via
  the GitHub UI / API token can. Franky was given the manual steps.
- I cannot check Franky's Actions minutes / billing balance.
- The `.crx` for v1.30.88 is still not attached to the release because
  the dispatch run never started. Brave auto-update is still inert.

## Instructions given to Franky (manual steps to unblock)

1. Check Actions minutes at https://github.com/settings/billing/summary.
2. Disable Actions for the repo at
   https://github.com/Frankytyrone/parish_harvester/settings/actions,
   wait 3 minutes, re-enable. This clears wedged dispatch runs.
3. Merge **PR #185** (harvest.yml YAML fix) BEFORE re-triggering the
   release workflow, otherwise every push keeps clogging the queue.
4. Until a `.crx` exists in the v1.30.x release, Brave will NOT
   auto-update — manual reload via `brave://extensions` → ↻ on Parish
   Trainer is the only way to see new toolbar code.

## Standing reminders (carried forward)

- **Franky decides which parishes are dead** — never mark inactive
  unilaterally. The training toolbar is the source of truth.
- Save every chat to `ai_conversations/` even if the session ends abruptly.
- Be brutally honest. Never claim something is done when it isn't.
- Walk through every step slowly. Non-technical user.

## Hand-off note to next AI

1. Read `AGENTS.md`, the previous two logs (`2026-05-23-brave-auto-update-and-release-stuck.md`
   and `2026-05-23-bundle-k-gemini-chat-raphoe.md`), and this file.
2. Check whether the **AI Help in floating toolbar PR** has been merged and
   whether Franky reloaded the extension in Brave to actually see it.
3. Check whether **PR #185** (harvest.yml YAML fix) has been merged. If not,
   suggest merging it first.
4. Check whether the stuck **`Release Parish Trainer extension` run
   `26333000751`** has been cleared. If not, walk Franky through
   disable/re-enable Actions again.
5. Once cleared and PR #185 is merged, re-trigger the release with the
   exact current `extension/manifest.json` version.
6. Verify a `.crx` file appears on the matching GitHub Release — without
   that, Brave auto-update will never work.
