# AI Conversation Log — 2026-05-22 (Session 2)

> Follow-up to `2026-05-22-pr169-review-and-deep-dive-request.md`.
> See `AGENTS.md` for the rules every future AI must follow.

## Date / Login / Repo
2026-05-22 — `Frankytyrone` — `Frankytyrone/parish_harvester`

## What got merged today
- **PR #169** — Toolbar truthfulness + UK dates + recipe step unification.
- **PR #170** — Deep audit document (`docs/audit/2026-05-22-deep-audit.md`).
- **PR #171** — Brave self-hosted CRX auto-update pipeline (release workflow, `updates.xml`, manifest `key`, `bump-version.mjs`, `docs/AUTO_UPDATE_SETUP.md`). Conflict was resolved by Copilot inside the PR.
- **PR #172** — Fix for the recurring red Actions runs (harvest commit race + deploy-pages false-positive on empty artifacts).

Plus committed earlier today:
- `ai_conversations/AGENTS.md` — hard rules for all future AI sessions.
- `ai_conversations/2026-05-22-pr169-review-and-deep-dive-request.md` — session 1 transcript.

## Audit headline findings (full file: `docs/audit/2026-05-22-deep-audit.md`)
- Repo scored honestly, mostly 4–7/10. Not broken, not yet trustworthy.
- 5 remaining truthfulness gaps in toolbar (background bridge default-success; "Marked as dead" green-without-verify; popup/sidepanel settings save; diagnostics ping).
- 40 failed parishes in latest run. Biggest cause = **recipe drift**, not random network issues.
- 7 DNS-dead parishes should be marked `inactive` now to stop noise.
- HTML-only parishes deliberately become summary links — needs a `page.pdf()` fallback path.
- Image-heavy / lazy-loaded image bulletins fail — needs multi-image → PDF pipeline.
- Toolbar has too many buttons; recommend trimming to 7 core controls.
- In-toolbar AI assistant: recommend Option A (call Mistral/OpenAI from background) with permission-prompted DOM read + `recipes/learned/<parish>.json` "learn from success" loop.
- GitHub Pages still looks dated — small CSS-only modernisation recommended.

## Top-10 action plan (from audit §12) — **the agreed execution order**
1. Truthfulness P0/P1 fixes (toolbar).
2. "Problems" tab in sidepanel (read `report.json` + failure counters + 1-click retrain).
3. Learned-recipe memory store (`recipes/learned/`) consulted first by harvester.
4. HTML→PDF render fallback in fetcher.
5. Multi-image→PDF pipeline.
6. Mark known-dead-DNS parishes as `inactive`.
7. Per-host timeout/retry profiles.
8. `docs/manifest.json` for external-site auto-embed.
9. Trim toolbar to 7 controls + "Advanced" fold.
10. GitHub Pages facelift (one shared CSS).

## Open follow-ups Franky still needs to do himself
- Brave auto-update one-time setup (`docs/AUTO_UPDATE_SETUP.md`) — generate `key.pem`, add `EXTENSION_PRIVATE_KEY` repo secret, paste public key into `manifest.json`. Franky is non-technical; offered a "browser-only" path via a helper workflow.
- Cut first signed release tag (`v1.30.66`) once setup is done.

## Compute discipline (Franky's request)
- Bundle related fixes per PR.
- Don't re-audit; trust the audit doc.
- Don't re-ask for confirmation we already have.
- Don't dump info; ship PRs.

## Hand-off note to next AI
Read this file + `AGENTS.md` + the audit (`docs/audit/2026-05-22-deep-audit.md`) before answering. Then ask Franky which action plan item to ship next.
