# AI Conversation Log — 2026-05-22

> **Purpose of this file:** Franky (repo owner, non-technical) sometimes loses
> access to a Copilot Chat session. This file is a saved transcript so the
> *next* AI session can pick up where the last one left off without losing
> context. **Future AI: read this before answering Franky's first question.**
>
> Franky's ground rules (must follow):
> - Never say something is done unless it actually is.
> - If you cannot do something, say so immediately and clearly.
> - If you cannot access a repo / file / chat, say so immediately.
> - Walk Franky through processes slowly, like he is new to a PC.
> - Keep answers short and to the point.
>
> Location convention: save all future chat logs under `ai_conversations/`
> with filename `YYYY-MM-DD-short-topic.md`.

---

## Session date
2026-05-22 — user `Frankytyrone`

## Repo
`Frankytyrone/parish_harvester` — Parish Bulletin harvesting app
(Python 53.5%, JavaScript 35.9%, HTML 10.6%)

## What was discussed

### 1. PR #169 review
PR #169 "Make Parish Trainer save feedback truthful, unify recipe steps,
standardize UK dates, and remove misleading viewer/toolbar UI"
(https://github.com/Frankytyrone/parish_harvester/pull/169)

**Verdict:** The PR does what it claims. I (the prior AI) verified file-by-file:

| Claim | Verified in diff? |
|---|---|
| `mark_*` handlers return `{ok, reason}` instead of bare bool | ✅ `extension/content.js` |
| `[PH-SAVE]` console logging on request/response cycle | ✅ both `content.js` and `sidepanel.js` |
| `data-status="pending\|success\|error"` on status banners | ✅ both files |
| Unified `recipeSteps` array (deleted `sessionSteps` + `standaloneSteps`) | ✅ |
| Crop save only confirms after page acknowledges | ✅ `sidepanel.js` |
| UK date helpers `formatUkDate` (JS) and `format_uk_date` (Python) | ✅ added in `sidepanel.js`, `ocr/generate_bulletin_pages.py`, `harvester/stitcher.py`, `main.py` |
| UK dates on dashboard / archive / viewer / mega PDF / CLI / harvest issue | ✅ |
| Removed "Jump to OCR Text" pill | ✅ |
| Removed top "Download PDF" pill, kept one in PDF panel header | ✅ |
| OCR search: live match count + Prev/Next + scroll-to-match | ✅ |
| New tests: `test_extension_messaging.py` + updates to existing tests | ✅ |

**Blocker before merge:** PR is still in **draft** state and no CI check runs
were reported on head commit `e53691af`. Franky should:
1. Click "Ready for review" on the PR.
2. Wait for CI green.
3. Then merge.

### 2. "Next PRs lined up" — there are none
Only PR #169 is open. All other open items are auto-generated harvest reports
(issues #152, #111, #110, #68 …). Suggested next work areas:
- Retrain recipes for `Clonmany`, `Aghyaran`, `Ardstraw East`.
- Mark dead-domain parishes inactive (DNS no longer resolves):
  Coleraine St John, Urney and Castlefin, Corpus Christi Belfast,
  Drumbo and Carryduff, Holy Trinity Belfast, St Luke's Belfast,
  St Vincent de Paul Belfast.
- Fix SSL/cert errors: St Mary's Belfast, St Matthew's.

### 3. Lost chat session
Franky lost access to a previous Copilot Chat (URL
`https://github.com/copilot/c/fd6c1eb6-e31c-4625-bee3-4c1cf6415022`) that
contained 3 PRs he was working on. **I could not access that chat** — Copilot
Chat sessions are private to the browser/account session and there is no API
to read them. That's why this transcript file exists from now on.

---

## Franky's standing requests (open work items for future AI)

These are NOT done yet. Treat them as a backlog:

### A. Deep dive of the repo
Find:
- What works.
- What is useless / dead code on the toolbar.
- What fails silently (says "✅ saved" but did not actually save). PR #169
  fixed several of these; audit again after merge to find the rest.

### B. Build an in-toolbar AI assistant
A chat panel inside the Parish Trainer Chrome extension toolbar so Franky can
talk to an AI live while training a recipe. The AI should be able to:
- Read the current webpage's DOM.
- Suggest which element on the page is the bulletin PDF.
- Detect hidden / background-loaded PDFs.
- Tell Franky step-by-step what to click.
- Flag toolbar buttons that are useless / never needed.

### C. Slim down + reorganise the repo
Specifically:
- Parishes are currently all piled into one file. Split them per-diocese
  (e.g. `parishes/derry/...`, `parishes/down_and_connor/...`).
- Remove genuinely dead code/UI rather than just hiding it.

### D. Trustworthy recipe-update feedback
When Franky pushes a recipe from the toolbar he wants:
- Confirmation that the **only** thing changed is that parish's recipe file.
- Confirmation that the mega PDF and OCR for that parish were regenerated.
- A clear "❌ did not change" message if anything failed.
- If implementing this end-to-end is too complex, **leave the current
  behaviour alone** rather than half-implementing it.

### E. Make GitHub Pages site look modern
Current `docs/index.html` and `docs/bulletins/index.html` look "2002-ish".
Needs a modern responsive redesign. Suggestions to include: card grid,
modern typography, dark/light mode, mobile-friendly layout, better archive
browse UX.

---

## Hand-off note to the next AI

When Franky opens a new chat, your first message should:
1. Acknowledge you've read `ai_conversations/` (this folder).
2. List the open items A–E above.
3. Ask which one he wants to tackle first.

Do NOT silently assume work from a previous session was finished. Always
verify against the repo's actual state (PRs, file contents) before claiming
anything is "done".
