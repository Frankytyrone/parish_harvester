# AI Agent Instructions — READ BEFORE DOING ANYTHING

> **If you are an AI (Copilot, ChatGPT, Claude, Gemini, a coding agent, a
> review agent, or any future model) working in this repository, this file
> is a hard rule, not a suggestion.**

Repo owner: **Frankytyrone** (non-technical user).

---

## Rule 1 — Read the chat history FIRST

Before answering Frankytyrone's first message in any new session you MUST:

1. List the files in `ai_conversations/` (newest filename last — they are
   named `YYYY-MM-DD-short-topic.md`).
2. Read at least the **most recent 2 files** in that folder.
3. In your first reply, briefly confirm you have read them and list the
   open work items (sections A–E or the latest backlog) so Franky knows
   you are caught up.

Do NOT assume work from a previous session was completed. Verify against
the repo's actual state (PRs merged, files present) before claiming
anything is "done".

## Rule 2 — Save THIS conversation when it ends

Before the session ends, or whenever Franky says "save this chat" / "log
this" / anything similar, you MUST create a new file at:

```
ai_conversations/YYYY-MM-DD-short-topic.md
```

It must contain:
- Date and Franky's GitHub login.
- A plain-English summary of what was discussed.
- Every decision made.
- Every "standing request" / open backlog item Franky raised.
- Links to any PRs / issues / files touched.
- A hand-off note to the next AI.

Use the existing files in `ai_conversations/` as templates.

## Rule 3 — Franky's ground rules (non-negotiable)

- **Never EVER say something is done unless you have actually done it.**
- If you cannot do something, **say so immediately and clearly**.
- If you cannot access a repo / file / chat / API, **say so immediately**.
- Walk Franky through processes slowly — he is non-technical.
- Keep answers short and to the point. No information dumps.
- Be brutally honest in audits / reviews. Don't soften findings.
- Do not pretend.

## Rule 4 — Why this file exists

Franky loses Copilot Chat sessions regularly (sessions expire, browser
tabs close, plan limits hit). Every lost session = lost ideas + work
restarted from scratch + frustration. The `ai_conversations/` folder is
the **persistent memory** that fixes this. Treat it as sacred.

## Rule 5 — Don't delete or rewrite past logs

Past conversations are historical record. You may add **new** files. You
may not edit or delete old ones, even if they look outdated or wrong.
If something needs correcting, write a new dated file that supersedes it
and reference the old one.

---

## Quick links

- Saved chats: [`ai_conversations/`](./)
- Repo README: [`../README.md`](../README.md)
- Latest audit (when ready): `docs/audit/`
