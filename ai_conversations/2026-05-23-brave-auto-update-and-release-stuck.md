# AI Conversation Log — 2026-05-23: Brave auto-update + stuck release workflow

**Date:** 2026-05-23
**Login:** @Frankytyrone
**Repo:** Frankytyrone/parish_harvester

---

## Summary

Continuation after PR #183 (Bundle K) and PR #184 (Fix-now diocese + dispatch
warning) were merged. Session focused on:

1. Getting the **Brave auto-update** pipeline finished so the extension updates
   itself without manual reloads.
2. Trying to run the **Release Parish Trainer extension** workflow to build and
   attach `parish_trainer.crx` to a `v1.30.88` GitHub Release.
3. A separate YAML failure in `harvest.yml` line 166 that was failing every
   harvest run.
4. Franky's repeated frustration that the toolbar still wasn't visibly updating
   in Brave.

---

## What was actually done in the repo this session

- `extension/manifest.json` — placeholder `PASTE_BASE64_DER_PUBLIC_KEY_HERE`
  was replaced with the real base64 DER public key Franky provided in
  `harvester toolbar keys.txt`.
- `updates.xml` — created/updated at repo root with the real extension ID
  `aohmhajdfdmhjjjoddleaikdfajgdjok` and version `1.30.88`, pointing at
  `https://github.com/Frankytyrone/parish_harvester/releases/download/v1.30.88/parish_trainer.crx`.
- A GitHub Release `v1.30.88` was created by Franky via the web UI, but
  **only "Source code" assets are attached** — no `.crx` file yet.
- Coding agent dispatched to fix the YAML syntax error in
  `.github/workflows/harvest.yml` line 166 (broken Python f-string with
  backslash and column-0 continuation lines that terminated the YAML block
  scalar). → **PR #185** open, not yet merged.

## What is NOT done (open issues at end of session)

- **PR #185** (`Fix YAML syntax error in harvest.yml + pin actions/download-artifact to patched v4.1.3`)
  is still open as a draft. Until it merges, every harvest run keeps failing.
- The **`Release Parish Trainer extension`** workflow run sat in **Queued**
  for 30+ minutes and Franky could not cancel it from the UI. No `.crx`
  file is attached to the `v1.30.88` release yet, so Brave auto-update
  still has nothing to download.
- Because there is no `.crx` in the release, **Brave will NOT auto-update**
  from 1.30.78 to 1.30.88. Franky still has to reload the extension
  manually via `brave://extensions` → ↻ on the Parish Trainer card.
- The **Gemini AI Help panel** is in the merged code but has not been
  verified end-to-end on a real parish site with a real Gemini API key.
- Recurring harvest failures on Bellaghy, Ballinascreen, Buncrana,
  Greenlough, Three Patrons, Aghyaran, Ardstraw East, Clonmany, DMA,
  Drumquin, Fahan, Kilrea, Lavey, Leckpatrick — Franky will decide via
  the toolbar which are dead vs need retraining. **Do not mark inactive
  without his instruction.**

## Decisions / standing requests reaffirmed

- Franky decides which parishes are dead — that is the whole point of the
  training toolbar. AI must not mark parishes inactive unilaterally.
- Every chat must be saved to `ai_conversations/` even if it ends abruptly.
- AI must walk Franky through steps slowly, never claim something is done
  when it isn't, and say immediately if it cannot access a repo or tool.

## Why the release workflow is stuck (best guess)

`release-extension.yml` is `workflow_dispatch` with an `Extension version`
input. Franky entered `1.30.88` which matches the manifest. The run shows
`Queued` for 30+ minutes with no other yellow jobs in the queue. Possible
causes still to verify next session:

1. GitHub Actions runner outage / regional queue delay (transient).
2. Account spending limit hit — the firewall warning mentioned
   `api.github.com/users/Frankytyrone/settings/billing/actions` being
   blocked, which can also indicate billing-side throttling.
3. Repo Actions permissions / approvals required on first run of a new
   workflow file.

Next session should:
- Cancel or wait out the stuck run.
- Check `Settings → Actions → General → Workflow permissions` and
  `Settings → Billing`.
- Re-run with `1.30.88` once PR #185 is merged so harvest stops failing
  every time something is pushed.

## Files touched this session

- `extension/manifest.json` (real public key inserted)
- `updates.xml` (extension ID + version 1.30.88)
- PR #185 (open): `.github/workflows/harvest.yml`,
  `.github/workflows/ocr-bulletin.yml`, `.github/workflows/deploy-pages.yml`
- `ai_conversations/2026-05-23-brave-auto-update-and-release-stuck.md` (this file)

## Hand-off note to next AI

1. **Read this file + `AGENTS.md` + `2026-05-23-bundle-k-gemini-chat-raphoe.md`
   before answering.**
2. First job: check whether **PR #185** is merged. If not, suggest merging
   it so the harvest workflow stops failing on every push.
3. Second job: check whether the `Release Parish Trainer extension` run
   ever completed and whether `parish_trainer.crx` is attached to the
   `v1.30.88` release. If not, that is why Brave still won't auto-update.
4. Until the `.crx` is published, the **only** way Franky sees new toolbar
   code in Brave is: `brave://extensions` → click ↻ reload on Parish Trainer.
5. The Gemini AI Help tab requires a free key from
   https://aistudio.google.com/app/apikey pasted into the toolbar settings.
   It has not been verified live yet.
6. Do **not** mark any parish inactive. Franky decides via the toolbar.
