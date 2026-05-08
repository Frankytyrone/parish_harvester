# Parish Trainer — Browser Extension

A floating toolbar that lets you record or manually override which bulletin URL belongs to each parish.  Works in two modes:

| Mode | When | Purpose |
|---|---|---|
| **Training mode** | Inside a Playwright session launched by `train.py` | Record click steps, PDF links, image crops, iframes, etc. to build a recipe |
| **Standalone mode** | Loaded as a private Chrome/Brave extension, outside `train.py` | Fix a wrong/old/missed bulletin on the fly and push the correction straight to GitHub |

---

## 1 · Installation as a private Chrome/Brave extension

1. Clone or download this repository to your computer.
2. Open Chrome or Brave and go to `chrome://extensions` (or `brave://extensions`).
3. Enable **Developer mode** (toggle in the top-right corner).
4. Click **Load unpacked**.
5. Navigate to the `extension/` folder inside the cloned repository and select it.
6. The **Parish Trainer** extension icon (⠿) appears in your browser toolbar.

> **Tip**: Pin the extension so the icon is always visible — right-click it and choose *Pin*.

---

## 2 · One-time GitHub setup (standalone mode only)

To be able to push recipe corrections directly to GitHub you need a Personal Access Token (PAT):

1. Go to <https://github.com/settings/tokens> → *Generate new token (classic)*.
2. Give it a name (e.g. `parish-trainer`), and tick the **`repo`** scope.
3. Copy the generated token (starts with `ghp_`).
4. Click the Parish Trainer icon in your browser.
5. Expand **🔑 GitHub Settings (one-time setup)** in the side panel.
6. Paste your PAT into *Personal Access Token*.
7. Enter the repository in the form `owner/repo` — e.g. `Frankytyrone/parish_harvester`.
8. Click **💾 Save settings**.

> Settings are stored locally in the browser with `chrome.storage.local` — they never leave your machine except when the extension makes GitHub API calls.

---

## 3 · How the toolbar works

### Opening and closing the toolbar

| Action | Result |
|---|---|
| Click the **Parish Trainer** icon in the browser toolbar | Toggle the floating toolbar on/off on the current page |
| Click **✕** inside the toolbar | Hide the toolbar |
| Click **⊡** inside the toolbar | Snap the toolbar to the top-right corner |
| Drag the toolbar header | Move the toolbar anywhere on the screen |

### The guided wizard (main buttons)

| Button | What it does |
|---|---|
| **📄 Get a PDF** | Records the current page URL as the bulletin PDF download step |
| **🖼️ Get an image** | Lets you draw a rectangle around a newsletter image on screen |
| **🖼️ Pick an image on this page** | Hover-click an existing `<img>` element to use it as the bulletin |
| **🔗 I need to click something first** | Click-to-select any link/button to record a navigation step |
| **🚫 No bulletin here (skip)** | Mark the parish as having no bulletin this week |

### Advanced / More options (hidden by default)

Click **I'm stuck — show all options** or open the ⚙️ section to reveal:

| Button | What it does |
|---|---|
| **📐 It's in a frame / viewer** | Inspect iframes on the page and pick the one containing the bulletin |
| **Mark Page as HTML** | Record that the current URL itself is an HTML bulletin page |
| **Mark Current URL as File** | Record the current URL as a direct file download |
| **Crop Bulletin Image** | Draw a selection rectangle to capture part of the screen as an image |
| **📰 Capture newsletter column** | Auto-highlight the main article column for cropping |
| **🔍 Help me identify this page** | Run automatic detection to see what kind of content is on the page, including a *Deep Detect* option that listens for background PDF loads |

### Recipe Preview

The **📋 Recipe Preview** section (collapsed by default) shows all steps recorded in the current session.  Use **↩ Undo Last Step** to remove the most recently recorded step.

---

## 4 · Manual on-the-fly bulletin correction (standalone mode)

This is the primary reason to install the extension as a private add-on.

### Scenario: the auto-scraper downloaded the wrong/old bulletin

1. Open Chrome/Brave with the Parish Trainer extension loaded.
2. Navigate to the parish website (e.g. Ballycastle Parish).
3. Find and navigate to the **correct** current bulletin PDF.  You can:
   - Click through to the PDF so the URL in the address bar is the PDF URL, **or**
   - Stay on the bulletin listing page if the PDF URL is visible as a link.
4. Click the **Parish Trainer** icon to open the toolbar.
5. You will see **📌 Fix Wrong Bulletin (direct override)** near the bottom.
6. Fill in:
   - **Bulletin URL** — the PDF URL you just found (pre-filled with the current page URL — change it if the PDF is linked, not directly open)
   - **Parish key** — the short identifier used in `parishes/recipes/` (e.g. `ballycastleparish`)
   - **Display name** — human-readable name (e.g. `Ballycastle Parish`)
   - **Diocese** — e.g. `derry_diocese` (optional but recommended; remembered between sessions)
7. Click **📌 Fix This Bulletin Now**.
8. The extension pushes a minimal recipe to `parishes/recipes/<key>.json` in GitHub.  The next harvest run will use this recipe instead of whatever it guessed before.

> **What recipe is pushed?**  A minimal two-step recipe:
> `goto(<current page URL>)` → `download(<bulletin URL>)`.
> This wins over any previous guessed recipe because the recipe file now exists and replay finds it first.

### Scenario: the bulletin is behind a click (multi-step)

Use the full wizard instead of the Quick Fix:

1. Navigate to the parish bulletin listing page.
2. Click the extension icon.
3. Click **🔗 I need to click something first** and click the correct bulletin link.
4. The toolbar now shows the link's details — click **👍 Looks right** to confirm.
5. If the next page is a PDF, click **📄 Get a PDF**.
6. In the **⬆ Push Recipe to GitHub** section at the bottom, fill in the parish key, display name, and diocese, then click **⬆ Push Recipe to GitHub**.

---

## 5 · Using the toolbar during `train.py` training sessions

When `train.py` launches a Chromium window the toolbar appears automatically.  The workflow is the same as standalone mode but steps are sent directly to Playwright and saved to the recipe file on disk rather than pushed to GitHub via the API.

1. Run `python train.py "<Parish Name>"` from the terminal.
2. A browser window opens on the parish bulletin page.
3. The floating toolbar appears automatically.
4. Follow the guided wizard to record the steps.
5. When you are done, press **Enter** in the terminal to save the recipe.

> During training the **⬆ Push Recipe** and **📌 Fix Wrong Bulletin** sections are hidden — Playwright handles saving directly.

---

## 6 · Parish Directory (side panel)

Open the **📋 Parish Directory** section to see all known parishes grouped by diocese.

| Control | Effect |
|---|---|
| Click parish name | Opens the parish bulletin page in a new tab |
| **✏️** button | Edit the `# page:` URL in the evidence file and push to GitHub |
| **☠** button | Push a `dead_url` recipe to mark the website as dead |
| **skip ☑** checkbox | Add/remove the parish key from `parishes/mega_excludes.json` (excludes it from the mega PDF this week) |

Use the search box to filter by parish name or key.

---

## 7 · Troubleshooting

| Problem | Solution |
|---|---|
| Toolbar does not appear when I click the icon | Make sure you are on an `http://` or `https://` page (not `chrome://` or a new-tab page) |
| "Could not communicate with page" | Reload the page and try again |
| "GitHub PAT or repo not configured" | Open the **🔑 GitHub Settings** section and save your PAT and repo |
| Push fails with a 401 or 403 error | Your PAT has expired or lacks the `repo` scope — generate a new one |
| Push fails with a 409 conflict | Someone else pushed to the same recipe file at the same time — refresh the page and try again |
| Toolbar appears on every website automatically | This only happens during Playwright training sessions; in standalone mode the toolbar only appears when you click the extension icon |
| Recipe file already exists and I want to overwrite it | The extension fetches the current SHA and overwrites cleanly — no manual deletion needed |

---

## 8 · File overview

| File | Purpose |
|---|---|
| `manifest.json` | Extension manifest (MV3) |
| `content.js` | Floating toolbar injected into every page (MAIN world) |
| `isolated.js` | Message bridge between the page and the extension background (ISOLATED world) |
| `background.js` | Service worker: handles action clicks, context menus, and GitHub API calls |
| `popup.html` / `popup.js` | Minimal popup (fallback if side panel is not available) |
| `sidepanel.html` / `sidepanel.js` | Full-featured side panel with parish directory, GitHub settings, and wizard buttons |
