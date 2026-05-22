# 🗺️ What Is This?

**👉 Read this first if you're new to this repository.**

---

## 🎯 What this repo does in one sentence

Every Sunday morning, this repository automatically downloads the weekly bulletin from every Catholic parish in the Derry and Down & Connor dioceses, stitches them into one big PDF, and publishes them to a free public website — all with no monthly cost and no human intervention needed.

---

## 🧠 The 60-second tour

- **Every Sunday 8am** — GitHub automatically runs the harvester. No one presses a button.
- **The harvester visits each parish website** and downloads their PDF bulletin for the week.
- **It stitches all PDFs into one "mega PDF"** per diocese so you can read everything in one document.
- **It publishes everything to a free website** (GitHub Pages) — PDFs, text, search, calendar events.
- **AI reads each bulletin** and pulls out a 3-bullet summary and a list of upcoming events.
- **A public calendar file (.ics)** is generated each week — anyone can subscribe in Google or Apple Calendar.
- **Nothing costs money** — GitHub Actions, GitHub Pages, and all AI providers used here are free.

---

## 🗺️ Where everything lives

```
parish_harvester/
│
├── parishes/           ← The "recipes" for finding each parish's bulletin
│   ├── recipes/        ← Step-by-step instructions for each parish website
│   └── retention_policy.json  ← How long to keep old files before archiving
│
├── harvester/          ← The Python code that does the work
│   ├── fetcher.py      ← Visits parish websites and downloads PDFs
│   ├── stitcher.py     ← Stitches PDFs into one mega PDF
│   ├── ai_router.py    ← Sends text to AI (tries Gemini, then Groq, then Mistral)
│   ├── events_extractor.py  ← Pulls dated events out of bulletin text
│   ├── retention.py    ← Archives old files to keep repo under 5 GB
│   └── cost_tracker.py ← Writes the cost dashboard
│
├── ocr/                ← Converts PDFs to readable text and HTML viewer pages
│
├── docs/               ← The public website (hosted on GitHub Pages)
│   ├── index.html      ← Home page / dashboard
│   ├── mega_pdf/       ← The stitched mega PDFs
│   ├── bulletins/      ← Side-by-side PDF + text viewer pages
│   ├── feeds/          ← RSS feeds for news readers
│   ├── calendars/      ← .ics calendar files (subscribe in Google/Apple Calendar)
│   ├── search/         ← Search all bulletins
│   ├── COST_DASHBOARD.md  ← Traffic-light cost tracker (auto-updated each run)
│   └── sitemap.html    ← Visual map of every public page
│
├── extension/          ← A Chrome/Brave browser extension for training new parishes
│
├── .github/workflows/  ← Automated jobs that run on GitHub's computers
│   ├── harvest.yml     ← Main Sunday harvest
│   ├── retention.yml   ← Archives old files after each harvest
│   └── deploy-pages.yml  ← Publishes the website
│
├── Bulletins/          ← Temporary working area (not published)
│   └── events/         ← Raw JSON event data before calendar generation
│
├── ai_conversations/   ← Saved chats with AI assistants (the project memory)
├── WHAT_IS_THIS.md     ← This file
├── SITE_MAP.md         ← List of every public URL
└── README.md           ← Technical overview
```

---

## 🔄 How a weekly harvest works

1. **Sunday 8am** — GitHub's timer wakes up the harvest workflow.
2. **It reads each parish "recipe"** — a saved set of instructions for finding that parish's bulletin PDF.
3. **For each parish**, it opens the website, follows the recipe, and downloads the PDF.
4. **All downloaded PDFs are stitched together** into one big PDF per diocese.
5. **The AI reads each bulletin** and writes a 3-bullet summary and a list of dated events.
6. **Event data is saved** to `Bulletins/events/<diocese>/<parish>.json`.
7. **The manifest builder runs** — it writes the manifest file, RSS feeds, and public .ics calendar files.
8. **The cost dashboard is updated** — traffic-light status of all free-tier limits.
9. **The website is published** — all of `docs/` is pushed to GitHub Pages.
10. **The retention workflow runs** — files older than 8 weeks are compressed into zip archives.

---

## 🌐 What's on the public website

Every URL below is free and publicly accessible at no cost.

| URL | What it is |
|-----|------------|
| `https://frankytyrone.github.io/parish_harvester/` | Home page / dashboard |
| `.../mega_pdf/derry_mega_bulletin.pdf` | Derry Diocese mega PDF |
| `.../mega_pdf/down_and_connor_mega_bulletin.pdf` | Down & Connor mega PDF |
| `.../bulletins/index.html` | OCR bulletin archive index |
| `.../bulletins/derry-YYYY-MM-DD.html` | Derry OCR viewer page |
| `.../feeds/derry_diocese.xml` | Derry RSS feed |
| `.../feeds/down_and_connor.xml` | Down & Connor RSS feed |
| `.../calendars/derry.ics` | Derry events calendar |
| `.../calendars/down_and_connor.ics` | Down & Connor events calendar |
| `.../calendars/all.ics` | All parishes combined calendar |
| `.../search/` | Full-text bulletin search |
| `.../badges/` | Parish reliability scores |
| `.../sitemap.html` | Visual site map |
| `.../COST_DASHBOARD.md` | Cost & quota tracker |
| `.../EMBEDDING.md` | Embedding guide |

---

## 🤖 What the AI does (and doesn't)

**What it does:**
- Reads each bulletin's OCR text and writes a 3-bullet plain-English summary.
- Extracts every dated event (Mass times, fundraisers, meetings, sacrament prep) and saves them as calendar data.
- Tries three free AI services in order: Gemini Flash → Groq → Mistral. If all fail, it skips silently — the harvest continues without AI features.

**What it doesn't do:**
- It does not invent events. If AI fails, the events list is empty — never made up.
- It does not write recipes. You train those manually with the browser extension.
- It does not guarantee 100% accuracy. AI misses things, especially on unusual bulletin layouts.
- It is never the only thing keeping the harvest running. Even with no AI keys, bulletins are still downloaded and published.

**Cost:** £0/month. All three AI providers offer free tiers with no credit card required.

---

## 🧰 What the browser extension does

The browser extension (for Chrome and Brave) lets you train the harvester to find the bulletin on any parish website:

1. You open a parish's website in your browser.
2. You click the extension icon and click "Start Training".
3. You click through to where the bulletin PDF is.
4. The extension records your steps as a "recipe".
5. Next Sunday, the harvester follows that recipe automatically — no human needed.

The extension also lets you add new parishes and review failures from the previous week.

---

## 💷 What this costs Franky

**Right now: £0/month.**

See the live cost dashboard: [docs/COST_DASHBOARD.md](docs/COST_DASHBOARD.md)

| Resource | Free limit | Current usage |
|----------|------------|---------------|
| GitHub Actions (harvest runs) | Unlimited (public repo) | ~5 min/week |
| GitHub Pages (website hosting) | 100 GB/month bandwidth | Very low |
| Repository storage | 5 GB hard cap | See dashboard |
| AI (Gemini + Groq + Mistral) | Free tiers | £0 |

The only real risk to ongoing £0 cost is **repository storage**. The retention workflow automatically archives old files to keep the repo under 5 GB. If you ever see a 🔴 on the cost dashboard, run the retention workflow manually.

---

## 🛟 What happens if Franky cancels Copilot Pro tomorrow

**Short answer: everything keeps working.**

The weekly harvest, AI summaries, event extraction, calendar generation, cost monitoring, and archiving all run on GitHub Actions — not on Copilot. They will keep running forever as long as the repository exists.

**What you lose** by cancelling Copilot Pro:
- The ability to ask an AI assistant to add new features via chat.
- That's it.

**What keeps working after cancelling:**
- ✅ Sunday auto-harvest
- ✅ Mega PDF generation
- ✅ OCR text viewer pages
- ✅ AI summaries and event extraction (uses free Gemini/Groq/Mistral, not Copilot)
- ✅ Public .ics calendar feeds
- ✅ RSS feeds
- ✅ Full-text search
- ✅ Cost dashboard
- ✅ Retention / archiving
- ✅ The whole public website

---

## 🚨 What can go wrong

**1. A parish website changes layout and the recipe breaks.**

What it looks like: that parish shows as "failed" in the weekly harvest report issue on GitHub. The other parishes are unaffected.

What to do: open the browser extension, click the parish name, re-train the recipe.

---

**2. Repository storage hits 5 GB.**

What it looks like: GitHub may warn you by email, or you'll see a 🔴 in `docs/COST_DASHBOARD.md`.

What to do: Go to GitHub Actions → Retention workflow → Run workflow → set `dry_run: false`.

---

**3. An AI provider stops working (API key expired, service down).**

What it looks like: bulletin summaries and event lists will be empty for that run. The harvest itself still completes.

What to do: check the secrets in GitHub (Settings → Secrets → Actions). Renew the API key.

---

## 🆘 Who to ask for help when I'm not around

- **GitHub support**: https://support.github.com
- **GitHub Pages docs**: https://docs.github.com/en/pages
- **GitHub Actions docs**: https://docs.github.com/en/actions
- **Google Gemini free API**: https://aistudio.google.com/apikey
- **Groq free API**: https://console.groq.com/keys
- **Copilot Memory** (if you want to continue from where we left off): https://github.com/settings/copilot/memory

If you hire a developer to help, point them at this file and at `ai_conversations/AGENTS.md` — both explain the project from scratch.
