# AI Conversation Log — 2026-05-22

## Date
2026-05-22

## Login
Frankytyrone

## Repo
`Frankytyrone/parish_harvester`

## Summary
Franky chose **Option 1**: self-hosted CRX auto-update for Brave.
He did not want Chrome Web Store flow, fees, or repeated manual re-installs.
Goal: one manual install, then future updates from repo releases.

## Options considered

1. **Self-hosted CRX auto-update in Brave (picked)**
   - Why picked: Brave supports self-hosted Chromium update feeds.
   - Benefit: no store account, no fee, mostly set-and-forget.

2. **Chrome Web Store (unlisted/private link)**
   - Why not picked: extra account setup + store process was unwanted.

3. **Manual update prompt flow inside extension**
   - Why not picked: still requires clicks every release.

4. **Local symlink/dev workflow**
   - Why not picked: still manual and machine-specific.

## Files added/changed in this PR

- Added: `.github/workflows/release-extension.yml`
- Changed: `extension/manifest.json`
- Changed: `updates.xml`
- Added: `scripts/bump-version.mjs`
- Added: `docs/AUTO_UPDATE_SETUP.md`
- Added: `ai_conversations/2026-05-22-brave-auto-update.md`

## Open follow-ups

- Franky still needs to do one-time key setup in `docs/AUTO_UPDATE_SETUP.md`.
- Franky must paste real public key into `extension/manifest.json` `key` field.
- Franky must add repo secret `EXTENSION_PRIVATE_KEY` before first release run.

## Hand-off note to next AI

Before making claims, verify:
1. Secret `EXTENSION_PRIVATE_KEY` exists.
2. `manifest.json` has the real public `key` value (not placeholder).
3. A release tag (for example `v1.2.3`) exists and produced `.crx`.
4. `updates.xml` appid/version/codebase were updated by workflow.
