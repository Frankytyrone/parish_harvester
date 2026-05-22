# AI Conversation Log — 2026-05-22

- Date: 2026-05-22
- Login: Frankytyrone
- Repo: Frankytyrone/parish_harvester

## Summary

User flagged repeating red GitHub Actions runs. Two separate root causes were confirmed from logs:
1. `Harvest Parish Bulletins` failed in commit/cleanup git steps due to brittle stash/rebase/push flow and no-op commit edge cases.
2. `Deploy mega PDFs to GitHub Pages` failed when upstream harvest produced no mega PDF artifacts, even though that can be a valid week.

This PR applies a surgical workflow-only fix to both.

## Files changed

- `.github/workflows/harvest.yml`
- `.github/workflows/deploy-pages.yml`
- `.gitignore`
- `ai_conversations/2026-05-22-actions-failures-fix.md`

## Honest caveats (real fix vs workaround)

- **Real fix:** Replaced fragile stash/pull/pop commit logic in affected workflow steps with explicit staged-change check and push-retry loop (push → pull --rebase → retry up to 5).
- **Real fix:** Deploy workflow no longer hard-fails when no mega PDF artifacts are present; it now records a warning, marks deploy as intentionally skipped, and finishes green.
- **Safety-net workaround:** `continue-on-error: true` was added to the harvest commit step as a fallback guard. It should not be needed under normal operation, but it prevents that one step from hard-failing the whole run if an unexpected git edge case still appears.

## Open follow-ups (not part of this PR)

1. Harvest sometimes downloads only 1 of N parishes. That is a separate deep-audit/reliability problem and not addressed here.
2. Google Drive upload depends on secrets that might not be configured. Current behavior is safe (skip), but can still be noisy in logs.

## Hand-off note to next AI

This change intentionally touched only workflow/gitignore/chat-log files. If failures persist, investigate upstream harvest reliability separately from workflow commit/deploy orchestration.
