# Deep Audit — 22/05/2026

Audience: **Franky**. Non-technical. Plain English.

Ground rule used: if something says “saved” but did not really save, I call it out.

---

## 1) Repo map (1 page max)

### Top-level map

| Path | Type | Main language | What it is | Orphan/unused risk |
|---|---|---|---|---|
| `main.py` | File | Python | Main harvest command. Runs fetch, report, mega PDF, dashboard. | No |
| `train.py` | File | Python | Interactive recipe training flow. | No |
| `scheduler.py` | File | Python | Local weekly scheduler (`schedule` package). | Maybe (not used in GitHub Actions flow) |
| `harvester/` | Folder | Python | Core fetch/replay/report/stitch logic. | No |
| `ocr/` | Folder | Python | OCR conversion + HTML page generation. | No |
| `extension/` | Folder | JavaScript + HTML | Chrome extension (toolbar, sidepanel, popup, background). | No |
| `docs/` | Folder | HTML | GitHub Pages site files. | No |
| `Bulletins/` | Folder | JSON + HTML + artifacts | Current harvest outputs (`report.json`, dashboard). | No |
| `parishes/` | Folder | JSON + TXT + Markdown | Parish registry, evidence URLs, recipes, overrides, failure trackers. | No |
| `mega_pdf/` | Folder | HTML + artifacts | Viewer shell + generated diocesan mega PDFs. | No |
| `.github/workflows/` | Folder | YAML | CI/CD and harvest automation. | No |
| `ai_conversations/` | Folder | Markdown | Saved chat context for future sessions. | No |
| `updates.xml` | File | XML | Extension update manifest for self-hosted updates. | No |
| `test_*.py` files | Files | Python | Unit tests (106 passing locally). | No |
| `requirements*.txt` | Files | Text | Python dependencies. | No |
| `README.md` | File | Markdown | Setup and operator guide. | No |
| `__pycache__/` | Folder | Python cache | Local bytecode cache. Ignored by git. | **Yes (local clutter only)** |

### Orphan/unused flags

- `parishes/last_included.json` is referenced by sidepanel code (`extension/sidepanel.js:143`, `extension/sidepanel.js:347`) but is not present in `parishes/` now. So that panel section is fed with empty data every time.
- `parishes/recipes/unknown/` has 30 recipe files and at least 14 duplicate keys that also exist in proper diocesan folders (for example `ardmoreparish`, `bangorparish`). That is maintenance clutter. The write path defaults to `unknown` when diocese is missing (`extension/background.js:373-375`).

---

## 2) Component-by-component verdict table

| Component | Mark /10 | Works | Lies (claims success but fails) | Partly works | Waste of time | Notes |
|---|---:|---|---|---|---|---|
| Harvester core (`harvester/fetcher.py`) | 6 | Yes | Some | Yes | No | Gets many files, but fails hard on recipe drift and brittle sites. Latest run: 40 failed (`Bulletins/report.json:3-8`). |
| OCR pipeline (`ocr/convert_bulletin.py`, `ocr/generate_bulletin_pages.py`) | 7 | Yes | No | Yes | No | Works for generated viewers, but depends on successful mega PDFs first. |
| Mega PDF stitcher (`harvester/stitcher.py`) | 6 | Yes | No | Yes | No | Merges real PDFs well, but HTML/no-PDF parishes are pushed into a summary page, not rendered pages (`harvester/stitcher.py:262-301`). |
| Scheduler (`scheduler.py`) | 4 | Yes | No | Yes | **Maybe scrap** | Works locally, but GitHub Actions already does scheduled harvests. Duplicate pathway. |
| Chrome toolbar (`extension/content.js`) | 5 | Yes | **Yes** | Yes | No | Still has truthfulness gaps (see section 3). |
| Sidepanel / operator console (`extension/sidepanel.js`) | 6 | Yes | Some | Yes | No | Useful power tool, but noisy and has too many controls. |
| Popup (`extension/popup.js`) | 5 | Yes | Some | Yes | Maybe | Basic settings + diagnostics. Limited day-to-day value once configured. |
| GitHub Pages site (`docs/`) | 6 | Yes | No | Yes | No | Functional, but UX is still basic and fragmented. |
| GitHub Actions workflows | 7 | Yes | No | Yes | No | Strong automation. Still brittle around flaky websites and downstream failures. |
| Test suite (`test_*.py`) | 7 | Yes | No | Yes | No | Good coverage of extension messaging and pipeline basics. Local baseline passed: 106 tests. |
| Recipe storage (`parishes/recipes/`) | 4 | Yes | No | Yes | No | Structure improved (diocese folders), but `unknown/` duplicates are creating drift risk. |
| Parish registry (`parishes/*_bulletin_urls.txt`, contacts JSON) | 6 | Yes | No | Yes | No | Core source of truth, but many URLs are stale/dead and need cleanup policy. |

Brutal summary: this is **not broken junk**, but it is also **not trustworthy enough** yet for “set and forget.”

---

## 3) Truthfulness audit of the Parish Trainer toolbar

Remaining flows where UI can still mislead.

### A) Background bridge can report “ok” even when action result is unknown

- **Flow name**: Message bridge default success — `extension/background.js:14-19`
- **What it tells the user**: Any caller sees `{ok:true}` when response is not an object.
- **What actually happens on failure**: If page code returns non-object/undefined, UI can still treat it as success.
- **Severity**: **P0** (truth risk)
- **Suggested fix**: Never default to `{ok:true}`; require explicit `{ok:true}` from content script.

### B) “Marked as dead” message is shown without checking save result

- **Flow name**: Dead-site overlay success message — `extension/content.js:4232-4249`
- **What it tells the user**: “✅ Marked as dead. … harvester will skip this parish in future runs.”
- **What actually happens on failure**: It does not verify `ph_mark_download_url` success and does not wait for any confirmed response before showing green success.
- **Severity**: **P0**
- **Suggested fix**: Only show the green success text after confirmed response `{ok:true}` from the save path.

### C) Popup settings says “saved” without checking storage write error

- **Flow name**: Popup settings save banner — `extension/popup.js:97-105`
- **What it tells the user**: “✅ Settings saved.”
- **What actually happens on failure**: Callback does not check `chrome.runtime.lastError`; write failure can still show success.
- **Severity**: **P1**
- **Suggested fix**: Check `chrome.runtime.lastError` in callback and show red error if set.

### D) Sidepanel settings says “saved” without checking storage write error

- **Flow name**: Sidepanel settings save banner — `extension/sidepanel.js:119-123`
- **What it tells the user**: “✅ Settings saved.”
- **What actually happens on failure**: Same issue as popup: no `chrome.runtime.lastError` check.
- **Severity**: **P1**
- **Suggested fix**: Same as popup — gate success text on confirmed no-error callback.

### E) Diagnostic “toolbar ready” can be a false positive because of bridge behavior

- **Flow name**: Diagnostics script ping row — `extension/popup.js:239-249` + bridge default `extension/background.js:14-19`
- **What it tells the user**: “✅ Page script responding — toolbar ready.”
- **What actually happens on failure**: Can be green due to the default success fallback in bridge code.
- **Severity**: **P1**
- **Suggested fix**: Require ping response payload to include a strict marker (for example `{ok:true, pong:true}`).

---

## 4) Toolbar UI usefulness scorecard

| Element | Used for | Useful? | Why |
|---|---|---|---|
| `📄 Get a PDF` | Mark final PDF URL | Yes | Primary task. Keep. |
| `🖼️ Get an image (screenshot)` | Start crop flow | Yes | Needed for image bulletins. |
| `🖼️ Pick an image on this page` | Mark image URL directly | Maybe | Useful sometimes; overlaps with crop. |
| `🔗 I need to click something first` | Record click path | Yes | Needed for complex navigation sites. |
| `✨ Mark this element` | Auto-detect and mark | Maybe | Can save time but can choose wrong link. |
| `Crop Bulletin Image` | Manual crop | Yes | Needed fallback. |
| `📐 It's in a frame/viewer` | iframe/PDF viewer handling | Yes | Needed for wrapper sites (Portaferry class failures). |
| `📰 Capture newsletter column (auto)` | Highlight likely content area | Maybe | Nice helper, not core. |
| `🔍 Help me identify this page` | Detection helper | Yes | Good operator guidance. |
| `🤖 AI Training Mode` | Collect local samples | Maybe | Current version is limited (link guessing only). |
| `🤖 Ask AI` | Suggest URL | Maybe | Useful on some pages; no deep DOM/network intelligence yet. |
| `📋 Recipe Preview` + `↩ Undo` | Review/edit steps | Yes | Prevents bad pushes. |
| `⬆ Push Recipe to GitHub` | Save recipe | Yes | Core action. |
| `Update start_url` | Fix host drift | Yes | Useful when domain/path changed. |
| `🗑 Clear steps` | Reset session | Yes | Safety cleanup. |
| Sidepanel: `📌 override` | Fast temporary fix | Yes | High practical value. |
| Sidepanel: `☑ skip mega` | Exclude bad parish quickly | Yes | Prevents mega contamination. |
| Sidepanel: `☠ dead` | Mark dead URL | Yes | Needed for permanently dead domains. |
| Popup diagnostics | Debug setup | Maybe | Helpful at setup; low daily value. |

### Minimal toolbar recommendation (keep only 7 controls)

1. `📄 Get a PDF`
2. `🔗 I need to click something first`
3. `🖼️ Get an image (crop)`
4. `📐 It's in a frame/viewer`
5. `🔍 Help me identify this page`
6. `📋 Recipe Preview (+ Undo)`
7. `⬆ Push Recipe to GitHub`

Everything else should move behind an “Advanced” fold or be cut.

---

## 5) Why so many parish websites fail

Evidence used: latest `Bulletins/report.json` and open harvest issues #152, #111, #110, #68.

### Failure categories

| Category | Count | Example parishes | Proposed fix | Effort | Expected uplift |
|---|---:|---|---|---|---|
| DNS dead / expired domain | 7 (latest run) | Coleraine (St John), Urney and Castlefin, St Vincent de Paul Belfast | Mark as `inactive` recipe status and remove from active failure queue. | S | Medium (cuts noise fast) |
| SSL cert errors | 2 | St Mary’s Belfast, St Matthew’s | Add optional insecure retry mode for known-bad hosts, else mark inactive with reason. | M | Low-Med |
| Recipe drift (last-week URLs, wrong selectors, stale paths) | ~22 | Bellaghy, Clonmany, Aghyaran | Re-train + add freshness checks before accepting URL. | M | High |
| HTML pages with no clear PDF link | 1 clear + several weak pages | Three Patrons, Holy Rosary Belfast, St Agnes Belfast | Add rendered-page fallback (`print_to_pdf`) when no trusted PDF found. | M | Med |
| Image-only bulletin pain | 1 historical clear issue in open reports | Derriaghy (PNG in #68), Iskaheen (works but stale risk) | Add stronger image path: image list detect + multi-image to one PDF + OCR. | M | Med |
| Wix / iframe / PDF.js wrappers | 1 clear in latest | Portaferry (`viewer.html?file=...`) | Add wrapper unwrapping (`file=` param) + frame-aware fetch in replay/fetcher. | M | Med-High |
| Slow hosts / timeout-prone | 6 | Ballyclare and Ballygowan, Kilmore and Killyleagh, Portstewart | Per-host timeout/retry profile, not one-size-fits-all timeout. | M | Med |
| Amateur unstructured sites | 5-10 mixed | Saint Anthony, Nativity, Derriaghy class | Add “operator-first” learned recipe path and stale guardrails. | L | High over time |

### Notes from hard evidence

- Latest run has **40 failed** (`Bulletins/report.json:3-8`, `Bulletins/report.json:398-639`).
- Biggest repeated error is recipe mismatch: “Recipe download step did not find a matching document URL” and “Recipe finished without downloading a document” (`Bulletins/report.json:403-458`, `Bulletins/report.json:523-590`).
- Dead domains are explicitly identified in report errors (`Bulletins/report.json:487-638`).

---

## 6) PDF generation from HTML pages and image pages

### Why HTML-only parishes end up as “HTML link” in mega PDF

- In fetch flow, `html_link` entries return status `html_link` when no file is found (`harvester/fetcher.py:1448-1455`).
- Recipes can also explicitly return `html_link` (`harvester/replay.py:395-399`).
- Stitcher then puts these into the summary link page instead of real bulletin pages (`harvester/stitcher.py:188-190`, `harvester/stitcher.py:262-301`).

So yes: this behavior is deliberate today.

### Why image-bulletin parishes fail

- Image conversion only works when a direct image URL is fetched and Pillow can decode it (`harvester/replay.py:217-233`, `harvester/fetcher.py:905-925`).
- If image URL is hidden behind JS, lazy loaders, auth, or wrapper pages, this path fails.

### Concrete pipeline proposal (no code in this PR)

#### HTML → PDF

Use Playwright render-print path when no trusted PDF is found.

- Add fallback in `harvester/fetcher.py` inside `_scrape_and_download(...)` before final error return.
- Reuse existing `print_to_pdf` capability already in recipe replay (`harvester/replay.py:401-414`).
- New helper to add: `harvester/fetcher.py::_render_page_to_pdf(page, dest)` using `page.pdf(...)`.

#### Image(s) → PDF

Use multi-image assembly.

- Add helper in `harvester/fetcher.py`: `_download_images_as_single_pdf(urls, dest)`.
- Implement with Pillow (`PIL.Image`) or `img2pdf` style logic.
- For pages containing many bulletin images, collect and sort image candidates then merge to one PDF.

---

## 7) In-toolbar AI assistant design proposal (no code yet)

You already have a basic AI button. It is not enough. It only sends sampled links to Mistral (`extension/content.js:3164-3248`).

### Architecture options

| Option | Cost | Complexity | Privacy | “Set and forget”? | Can inspect live page? |
|---|---|---|---|---|---|
| A) Call OpenAI/Mistral from extension background | Ongoing API cost | M | DOM/HTML sent to vendor | Maybe | Yes, if you explicitly capture and send snapshot |
| B) Copilot API-style integration | Unclear/limited for extensions | L | Depends on GitHub integration terms | No (high dependency risk) | Partial/unclear |
| C) Local model via Ollama bridge | Low cash cost | L | Best privacy (local) | No (needs local service upkeep) | Yes |
| D) Cheap MVP: “Send DOM snapshot to GitHub issue + @copilot workflow” | Very low | S-M | Data lands in repo issues | Yes-ish | Indirect, delayed |

### Recommended option: **A (direct API in extension background)**

Why: easiest reliable path to real-time guidance in-browser.

### New files to add (future PR)

- `extension/ai_panel.html`
- `extension/ai_panel.js`
- `extension/ai_bridge.js`
- `extension/ai_schema.js` (message contract)
- `extension/ai_guardrails.js` (redaction + permissions)

### Message contract (panel ↔ page)

```json
{
  "type": "ai_analyze_page",
  "request_id": "uuid",
  "scope": {
    "dom": true,
    "html": true,
    "iframes": "metadata_only",
    "network": "pdf_related_only"
  },
  "user_goal": "Find this week's bulletin PDF",
  "page_context": {
    "url": "https://...",
    "title": "...",
    "selected_element": "optional css/xpath"
  }
}
```

And response:

```json
{
  "request_id": "uuid",
  "confidence": 0.0,
  "recommended_strategy": "click_path|direct_pdf|iframe_unwrap|image_to_pdf|html_print",
  "steps_for_franky": ["Step 1 ...", "Step 2 ..."],
  "candidate_urls": ["https://...pdf"],
  "warnings": ["This site looks stale"],
  "needs_user_confirmation": true
}
```

### Safe read-only access model

- Permission prompt before each deep inspect: “Allow AI to read this page?”
- Default to **metadata first** (URL/title/visible links), then escalate only if user accepts.
- Redact obvious secrets (cookies, auth tokens, hidden form passwords) before sending.
- Restrict network capture to PDF/DOCX/image URLs only.
- Never execute AI-returned JS on host page. AI suggests; user confirms; extension executes known-safe commands.

### “Learn from success” loop

On every confirmed successful bulletin download:

- Write `recipes/learned/<parish>.json` with:
  - page fingerprint (hostname, path pattern, key selectors)
  - successful strategy (`iframe_unwrap`, `print_to_pdf`, etc.)
  - selector chain / click sequence
  - last success timestamp
  - rolling success rate
- On next run, consult learned recipe first, then normal recipe fallback.

---

## 8) Self-host mega PDFs + OCR pages on Franky’s own sites

### (a) Direct CDN URL

Best direct URL style:

- `https://cdn.jsdelivr.net/gh/Frankytyrone/parish_harvester@main/mega_pdf/derry_mega_bulletin.pdf`
- `https://cdn.jsdelivr.net/gh/Frankytyrone/parish_harvester@main/mega_pdf/down_and_connor_mega_bulletin.pdf`

Why not raw GitHub URLs as primary:

- Raw can have caching/rate-limit/content-type quirks.

**Auto-updates?** Yes (with CDN cache lag).

### (b) GitHub Pages embed

#### PDF iframe

```html
<iframe
  src="https://frankytyrone.github.io/parish_harvester/mega_pdf/derry_mega_bulletin.pdf"
  width="100%" height="900" style="border:0;"
  title="Derry mega bulletin">
</iframe>
```

#### PDF object fallback

```html
<object
  data="https://frankytyrone.github.io/parish_harvester/mega_pdf/down_and_connor_mega_bulletin.pdf"
  type="application/pdf" width="100%" height="900">
  <a href="https://frankytyrone.github.io/parish_harvester/mega_pdf/down_and_connor_mega_bulletin.pdf">Download PDF</a>
</object>
```

#### OCR viewer embed

```html
<iframe
  src="https://frankytyrone.github.io/parish_harvester/bulletins/derry-2026-05-22.html"
  width="100%" height="1000" style="border:0;"
  title="Derry OCR viewer">
</iframe>
```

**Auto-updates?** Yes, if embed points to stable “latest” URL pattern.

### (c) JSON manifest

Generate `docs/manifest.json` with latest links:

```json
{
  "generated_at": "2026-05-22T10:00:00Z",
  "dioceses": {
    "derry": {
      "mega_pdf": "https://frankytyrone.github.io/parish_harvester/mega_pdf/derry_mega_bulletin.pdf",
      "ocr_viewer": "https://frankytyrone.github.io/parish_harvester/bulletins/derry-2026-05-22.html"
    }
  }
}
```

External site one-liner fetch pattern:

```html
<script>
fetch('https://frankytyrone.github.io/parish_harvester/manifest.json')
  .then(r => r.json())
  .then(m => {
    const d = m.dioceses.derry;
    document.getElementById('latest-link').href = d.mega_pdf;
  });
</script>
```

**Auto-updates?** Yes. Best clean integration.

### (d) Webhook fan-out

After harvest success, `notify.yml` sends POST to your site endpoints.

Payload example:

```json
{ "event": "harvest_complete", "generated_at": "...", "manifest_url": "https://.../manifest.json" }
```

**Auto-updates?** Yes, if target websites implement receiver.

---

## 9) Backend “problem dashboard” for failed websites (design)

### Data source

- Current run: `Bulletins/report.json` (`failed[]`, `html_links[]`).
- Trends: `parishes/consecutive_failures.json` and recent harvest report issues (#152, #111, #110, #68).

### Sidepanel tab

Add a new tab: **🚨 Problems**

Columns:
- Parish
- Failure category
- Last seen
- Consecutive failures
- Action button: **Fix now**

### “Fix now” one-click path

1. Open parish page in a new tab.
2. Auto-show toolbar.
3. Prompt retrain flow.
4. Push new recipe.
5. Save learning file.
6. Queue single-parish harvest dispatch first.

### `recipes/learned/` schema

```json
{
  "parish_key": "parishofexample",
  "fingerprint": {
    "host": "example.com",
    "path_hint": "/bulletin",
    "dom_markers": [".pdfemb-viewer", "iframe[src*='pdf']"]
  },
  "last_success_date": "2026-05-22",
  "success_rate": 0.78,
  "playbook": [
    {"action":"goto","url":"https://..."},
    {"action":"click","selector":"..."},
    {"action":"download","url_pattern":"*.pdf"}
  ]
}
```

### Memory behavior

- Harvester order:
  1) `recipes/learned/<parish>.json`
  2) standard recipe
  3) scrape fallback
- On success, append/refresh learned stats.

### Permanently dead parishes

Use recipe metadata:

```json
{ "status": "inactive", "reason": "DNS dead" }
```

Fetcher already skips inactive/dead recipes (`harvester/fetcher.py:1267-1289`).

---

## 10) GitHub Pages redesign brief (2026, not 2002)

Current site works but still looks basic (`docs/index.html`, `docs/bulletins/index.html`, `mega_pdf/index.html`).

### Visual direction

Use modern but simple patterns:
- Hero with “latest bulletin now” CTA
- Clean card grid per diocese
- Sticky top nav
- Dark/light auto-switch (`prefers-color-scheme`)
- Soft glass-style header + large readable buttons

### Information architecture

1. Diocese landing card
2. Latest mega PDF
3. OCR latest page
4. Archive list
5. Per-parish history (later phase)
6. Search box (OCR pages)

### Tech recommendation

**Stay vanilla HTML/CSS + one shared CSS + tiny JS search.**

Why: lowest maintenance for non-technical owner. No static-site generator overhead.

### Mobile-first checklist

- One-column cards under 768px
- Big tap targets
- Avoid fixed-height PDF panes on phones
- Lazy-load heavy embeds

### Accessibility checklist

- Semantic headings in strict order
- Keyboard-focus visible states
- Alt text for bulletin thumbnails
- Contrast checks for buttons

### 5-step rollout (safe)

1. Create shared `docs/assets/site.css`.
2. Restyle `docs/index.html` only first.
3. Restyle `docs/bulletins/index.html`.
4. Restyle `mega_pdf/index.html`.
5. Add simple client-side search on archive page.

---

## 11) “Far-out but easy” ideas (>=10)

| Idea | Wow /10 | Effort | Set-and-forget? | Recommend? |
|---|---:|---|---|---|
| AI 3-bullet summary for each parish bulletin | 8 | M | Yes | Yes |
| Weekly “what changed since last week” diff | 9 | M | Yes | Yes |
| RSS feed per diocese | 7 | S | Yes | Yes |
| WhatsApp/Signal push bot with latest links | 8 | M | Mostly | Maybe |
| Email digest (“Bulletin of the Week”) | 7 | S | Yes | Yes |
| Auto-translate bulletins (Irish/Polish/Ukrainian) | 8 | M | Yes | Maybe |
| Public API endpoint (`manifest.json` + feeds) | 7 | S | Yes | Yes |
| Search-all OCR text box across archive | 9 | M | Yes | Yes |
| “Parish reliability score” badge | 6 | S | Yes | Yes |
| Smart re-test queue: failed parishes first | 8 | S | Yes | Yes |
| Auto-create retrain tasks from failures | 7 | S | Yes | Yes |
| Liturgical highlights auto-extract | 8 | M | Yes | Maybe |

---

## 12) Prioritised action plan (top 10)

If I were you, I would do these in this order.

| # | Action | Effort | Value | Separate PR? | Depends on #169 merged first? |
|---:|---|---|---|---|---|
| 1 | Fix remaining truthfulness gaps (section 3 P0/P1) | S | High | Yes | **Yes** |
| 2 | Build “Problems” tab in sidepanel (read from `report.json` + failure counters) | M | High | Yes | Yes |
| 3 | Add learned-recipe memory store (`recipes/learned/`) and consult-first logic | M | High | Yes | Yes |
| 4 | Add HTML render fallback (`page.pdf`) when no PDF found | M | High | Yes | No |
| 5 | Add multi-image-to-PDF flow for image-heavy sites | M | High | Yes | No |
| 6 | Mark known dead DNS parishes as `inactive` to cut noise | S | High | Yes | No |
| 7 | Add per-host timeout/retry profiles for slow sites | M | Med-High | Yes | No |
| 8 | Create `docs/manifest.json` for external-site auto-embed | S | High | Yes | No |
| 9 | Trim toolbar to 7-core controls + hide extras in Advanced | M | Med | Yes | Yes |
| 10 | GitHub Pages facelift using one shared CSS file | M | Med | Yes | No |

---

## Executive summary (10 lines, worst findings)

1. The system still has truthfulness bugs: some green success states are not fully verified.
2. The background bridge can return fake success in edge cases (`extension/background.js:14-19`).
3. “Mark as dead website” shows green success without confirmed save (`extension/content.js:4232-4249`).
4. Latest run is still rough: 40 failures (`Bulletins/report.json:3-8`, `:398-639`).
5. Biggest failure class is recipe drift, not random network bad luck.
6. DNS-dead parishes are wasting your time and should be marked inactive now.
7. HTML-only handling is intentional today: mega PDF gets a link summary, not rendered pages.
8. Image handling works in simple cases but is fragile on modern script-heavy pages.
9. Extension UI has too many controls. Keep 7 and hide/cut the rest.
10. Biggest win next: fix trust signals + ship a “Problems” dashboard with one-click retrain.
