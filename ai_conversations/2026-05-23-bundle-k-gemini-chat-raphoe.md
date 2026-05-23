# AI Conversation Log — 2026-05-23: Bundle K Gemini Chat + Raphoe

**Date:** 2026-05-23  
**Login:** @Frankytyrone  
**Repo:** Frankytyrone/parish_harvester  
**Branch:** `copilot/add-gemini-ai-chat-panel`

---

## Summary

Franky asked for one PR that does three real things:

1. Add a **real Gemini-powered AI Help chat panel** inside the Parish Trainer extension UI.
2. Wire up **Raphoe Diocese** for harvesting using the uploaded Raphoe URL list.
3. Add **Raphoe** to the public GitHub Pages website.

This session implemented those changes in the repo and verified the main changed areas with targeted tests.

---

## What was changed

### 1) Gemini AI Help panel in the extension

- Added a new **🤖 AI Help** tab to `extension/sidepanel.html`.
- Added a chat area, text box, **Send** button, and **🔍 Analyse this page** button.
- Added Gemini API key fields to both:
  - `extension/popup.html`
  - `extension/sidepanel.html`
- Updated:
  - `extension/popup.js`
  - `extension/sidepanel.js`

The new AI panel now:

- Reads the current page context from the active parish tab.
- Collects:
  - URL
  - title
  - whether the page is `http://`
  - iframe URLs
  - direct PDF links
  - likely bulletin images
  - Google Drive / Facebook / MCN Live links
  - page text sample
- Sends that context to **Gemini 1.5 Flash**.
- Gives plain-English capture advice.
- Stores a simple memory per hostname in `chrome.storage.local` using:
  - `ph_ai_memory_<hostname>`
- Shows a “last time this worked” banner when memory exists.

### 2) Raphoe Diocese wiring

- Replaced the old uploaded file with the new convention-matching file:
  - `parishes/raphoe_diocese_bulletin_urls.txt`
- Deleted the old spaced filename:
  - `parishes/raphoe diocese urls.txt`
- Reformatted the Raphoe evidence file into grouped parish sections with `# --- Parish Name ---` headers.
- Added direct-download conversions for Google Drive file links.
- Marked Facebook / MCN / Google Drive folder entries as `html_link`-style manual links.
- Added `# key:` overrides where needed so Raphoe entries line up with existing recipe keys or stable names.
- Added:
  - `parishes/raphoe_diocese_contacts.json`

### 3) Raphoe in extension parish directory + website

- Added Raphoe to `PD_EVIDENCE_FILES` in `extension/sidepanel.js`.
- Added Raphoe slug handling and Raphoe recipe lookup path.
- Updated `harvester/site_builder.py` so the website can show live diocese sections using evidence-file parish links.
- Regenerated:
  - `docs/index.html`
  - `docs/dioceses/raphoe/index.html`
- Added:
  - `docs/bulletins/raphoe/index.html`

---

## Decisions made

- **Gemini** is the chat provider used for the new help panel.
- The existing **Mistral** code for other parts of the system was left in place.
- The AI panel uses **plain English** and simple capture-step guidance.
- Raphoe website parish lists are now derived from the **evidence file**, not just from existing recipe files.
- The user provided a screenshot URL of the AI Help tab that can be used as the UI reference if needed:
  - `https://github.com/user-attachments/assets/5732e767-651a-4d24-abbe-37901a6fea63`

---

## Tests and verification

### Baseline before changes

- `python -m unittest` initially failed because the sandbox did not yet have repo dependencies installed.
- After installing requirements, the suite ran properly.

### Targeted tests run after changes

- `python -m unittest test_extension_messaging test_landing_page test_site_builder test_page_renderer test_raphoe_assets test_train_matching.ParishMatchingTests.test_operator_console_hides_wizard_and_uses_directory_details`
- Result: **passed**

### Full suite run after changes

- `python -m unittest`
- Result: **1 pre-existing failure remains**

Pre-existing failing test:

- `test_train_matching.ParishMatchingTests.test_popup_version_and_diagnostics_controls_exist`

Reason:

- It expects `extension/manifest.json` to use the GitHub Pages `update_url`
- The repo currently still has the raw GitHub URL in the manifest
- This failure existed before this work and was not part of Bundle K

---

## Files touched

- `extension/popup.html`
- `extension/popup.js`
- `extension/sidepanel.html`
- `extension/sidepanel.js`
- `harvester/site_builder.py`
- `docs/index.html`
- `docs/dioceses/raphoe/index.html`
- `docs/bulletins/raphoe/index.html`
- `parishes/raphoe_diocese_bulletin_urls.txt`
- `parishes/raphoe_diocese_contacts.json`
- `test_extension_messaging.py`
- `test_landing_page.py`
- `test_site_builder.py`
- `test_train_matching.py`
- `test_raphoe_assets.py`

Deleted:

- `parishes/raphoe diocese urls.txt`

---

## Open / follow-up items

- Check the live extension manually in Chrome with a real Gemini API key.
- Decide later whether to fix the unrelated `manifest.json` `update_url` mismatch that is already failing one repo test.
- If desired, add Raphoe RSS / calendar footer links later when Raphoe feed/calendar files exist.

---

## Hand-off note to next AI

1. Do **not** claim the AI panel is fully proven until it is tested inside the real extension with a real Gemini key on actual parish sites.
2. The main code and UI are now present in the repo.
3. There is one **known unrelated failing unit test** about `extension/manifest.json` `update_url`.
4. The required chat log for this session has now been saved, so this session should not be lost.
