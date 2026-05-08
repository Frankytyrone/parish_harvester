const statusEl = document.getElementById("status");

function setStatus(text, type) {
  statusEl.textContent = text;
  statusEl.className = type || "ok";
}

async function withActiveTab(callback) {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id) {
    setStatus("No active tab.", "err");
    return;
  }
  callback(tab.id);
}

async function sendToActiveTab(message, successText) {
  await withActiveTab((tabId) => {
    chrome.tabs.sendMessage(tabId, message, () => {
      if (chrome.runtime.lastError) {
        setStatus(
          "Could not communicate with page. Try refreshing.",
          "err"
        );
        return;
      }
      setStatus(successText, "ok");
    });
  });
}

// ── Guided Mode wizard ────────────────────────────────────────────────────

document.getElementById("wizard-pdf").addEventListener("click", () => {
  void sendToActiveTab({ type: "mark_file" }, "✅ Bulletin PDF URL recorded.");
});

document.getElementById("wizard-image").addEventListener("click", () => {
  void sendToActiveTab(
    { type: "start_crop" },
    "🖼️ Draw a rectangle around the bulletin image…"
  );
});

document.getElementById("wizard-link").addEventListener("click", () => {
  void sendToActiveTab(
    { type: "start_pick_link" },
    "🎯 Hover over a link and click to select it…"
  );
});

document.getElementById("wizard-pick-image").addEventListener("click", () => {
  void sendToActiveTab(
    { type: "start_pick_image" },
    "🖼️ Hover over an image and click to select it…"
  );
});

document.getElementById("wizard-iframe").addEventListener("click", () => {
  void sendToActiveTab(
    { type: "start_pick_iframe" },
    "📐 Opening iframe picker in the toolbar…"
  );
});

// ── Advanced / fallback buttons ───────────────────────────────────────────

document.getElementById("mark-html").addEventListener("click", () => {
  void sendToActiveTab({ type: "mark_html" }, "✅ Marked as HTML page");
});

document.getElementById("mark-file").addEventListener("click", () => {
  void sendToActiveTab({ type: "mark_file" }, "✅ Marked current URL as file");
});

document.getElementById("crop-btn").addEventListener("click", async () => {
  await sendToActiveTab(
    { type: "start_crop" },
    "Click and drag to select the bulletin area…"
  );
});

// ── GitHub Settings ────────────────────────────────────────────────────────

// Load saved settings on open
chrome.storage.local.get(["gh_pat", "gh_repo"], (r) => {
  const patInput  = document.getElementById("gh-pat");
  const repoInput = document.getElementById("gh-repo");
  if (patInput  && r.gh_pat)  patInput.value  = r.gh_pat;
  if (repoInput && r.gh_repo) repoInput.value = r.gh_repo;
});

document.getElementById("gh-save").addEventListener("click", () => {
  const pat  = (document.getElementById("gh-pat").value  || "").trim();
  const repo = (document.getElementById("gh-repo").value || "").trim();
  const status = document.getElementById("gh-save-status");
  if (!pat || !repo) {
    status.textContent = "❌ Both PAT and repository are required.";
    status.style.color = "#fca5a5";
    return;
  }
  chrome.storage.local.set({ gh_pat: pat, gh_repo: repo }, () => {
    status.textContent = "✅ Settings saved.";
    status.style.color = "#86efac";
    setTimeout(() => { status.textContent = ""; }, 3000);
  });
});




// ── Parish Directory ───────────────────────────────────────────────────────
//
// Shows all parishes grouped by diocese with:
//   • Click name  → open the parish bulletin page
//   • ✏️  button  → edit the # page: URL in the evidence file
//   • ☠️  button  → push a dead recipe to GitHub
//   • exclude ☑   → add / remove the parish key from parishes/mega_excludes.json

const PD_EVIDENCE_FILES = {
  "Derry Diocese":         "parishes/derry_diocese_bulletin_urls.txt",
  "Down & Connor Diocese": "parishes/down_and_connor_bulletin_urls.txt",
};
const MEGA_EXCLUDES_PATH = "parishes/mega_excludes.json";
const MANUAL_OVERRIDES_PATH = "parishes/manual_overrides.json";

// Replicate Python's _url_to_key logic
function _pdUrlToKey(url, headerName = "") {
  try {
    const parsed = new URL(url);
    let hostname = parsed.hostname.toLowerCase().replace(/^www\d*\./, "");
    if (/\bi\d+\.wp\.com\b/.test(hostname)) {
      const parts = parsed.pathname.replace(/^\//, "").split("/");
      if (parts.length > 0) {
        const real = parts[0].toLowerCase().replace(/^www\d*\./, "");
        const segs = real.split(".");
        if (segs.length >= 2) return segs[0];
      }
    }
    if (hostname === "filesafe.space" || hostname.endsWith(".filesafe.space") || hostname === "google.com" || hostname.endsWith(".google.com")) {
      if (headerName) return headerName.toLowerCase().split("(")[0].trim().replace(/[^a-z0-9]/g, "");
      return hostname.split(".")[0].replace(/[^a-z0-9]/g, "");
    }
    return hostname.split(".")[0] || hostname;
  } catch (_e) {
    return "";
  }
}

function _pdParseEvidence(text, dioceseName) {
  const parishes = [];
  let cur = null;

  for (const rawLine of text.split("\n")) {
    const line = rawLine.trim();
    const nameMatch = line.match(/^#\s*---\s*(.+?)\s*---\s*$/);
    if (nameMatch) {
      if (cur) parishes.push(cur);
      cur = { name: nameMatch[1], diocese: dioceseName, pageUrl: null, keyOverride: null, bulletinUrls: [], disabled: false, key: null };
      continue;
    }
    if (!cur) continue;
    const pageMatch = line.match(/^#\s*page:\s*(.+)$/i);
    if (pageMatch) { cur.pageUrl = pageMatch[1].trim(); continue; }
    const keyMatch = line.match(/^#\s*key:\s*(.+)$/i);
    if (keyMatch) { cur.keyOverride = keyMatch[1].trim(); continue; }
    if (/^#\s*DISABLED/i.test(line)) { cur.disabled = true; }
    if (line.startsWith("#") || !line) continue;
    cur.bulletinUrls.push(line);
  }
  if (cur) parishes.push(cur);

  for (const p of parishes) {
    const firstUrl = p.bulletinUrls[0] || p.pageUrl || "";
    p.key = p.keyOverride || (firstUrl ? _pdUrlToKey(firstUrl, p.name) : "");
  }
  return parishes;
}

// Update the # page: URL for a named parish in an evidence file text blob
function _pdUpdatePageUrl(fileText, parishName, newUrl) {
  const lines = fileText.split("\n");
  const escaped = parishName.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const headerRe = new RegExp(`^#\\s*---\\s*${escaped}\\s*---`, "i");
  let inSection = false;
  let replaced  = false;
  let headerIdx = -1;

  for (let i = 0; i < lines.length; i++) {
    if (headerRe.test(lines[i].trim())) {
      inSection = true; headerIdx = i; continue;
    }
    if (inSection) {
      if (/^#\s*---/.test(lines[i].trim())) {
        if (!replaced && headerIdx >= 0) lines.splice(headerIdx + 1, 0, `# page: ${newUrl}`);
        break;
      }
      if (/^#\s*page:/i.test(lines[i].trim())) {
        lines[i] = `# page: ${newUrl}`; replaced = true; break;
      }
    }
  }
  if (!replaced && headerIdx >= 0) lines.splice(headerIdx + 1, 0, `# page: ${newUrl}`);
  return lines.join("\n");
}

// ── Communication helpers ─────────────────────────────────────────────────

function _pdGhFetch(path) {
  return new Promise((resolve, reject) => {
    chrome.runtime.sendMessage({ type: "fetch_github_file", path }, (res) => {
      if (chrome.runtime.lastError) { reject(new Error(chrome.runtime.lastError.message)); return; }
      if (!res?.ok) { reject(new Error(res?.error || "unknown")); return; }
      resolve({ content: res.content, sha: res.sha });
    });
  });
}

function _pdGhPush(path, content, commitMsg) {
  return new Promise((resolve, reject) => {
    chrome.runtime.sendMessage({ type: "push_github_file", path, content, commitMessage: commitMsg }, (res) => {
      if (chrome.runtime.lastError) { reject(new Error(chrome.runtime.lastError.message)); return; }
      resolve(res);
    });
  });
}

// ── Mega-excludes helpers ─────────────────────────────────────────────────

let _pdExcludes = null; // cached array of parish keys

async function _pdLoadExcludes() {
  if (_pdExcludes !== null) return _pdExcludes;
  try {
    const { content } = await _pdGhFetch(MEGA_EXCLUDES_PATH);
    _pdExcludes = JSON.parse(content);
  } catch (_e) {
    _pdExcludes = [];
  }
  return _pdExcludes;
}

async function _pdSaveExcludes(excludes) {
  _pdExcludes = excludes;
  const content = JSON.stringify(excludes.sort(), null, 2);
  return _pdGhPush(MEGA_EXCLUDES_PATH, content, "excludes: update mega PDF exclude list [from extension]");
}

// ── Manual bulletin overrides ───────────────────────────────────────────────

let _pdOverrides = null; // key -> {url,type,updated_at,source}

function _pdInferOverrideType(url) {
  const lower = (url || "").toLowerCase();
  if (lower.endsWith(".docx")) return "docx";
  if (lower.match(/\.(jpg|jpeg|png|webp)(\?|$)/)) return "image";
  if (lower.endsWith(".pdf") || lower.includes(".pdf?")) return "download";
  return "html";
}

async function _pdLoadOverrides() {
  if (_pdOverrides !== null) return _pdOverrides;
  try {
    const { content } = await _pdGhFetch(MANUAL_OVERRIDES_PATH);
    const parsed = JSON.parse(content);
    _pdOverrides = parsed && typeof parsed === "object" ? parsed : {};
  } catch (_e) {
    _pdOverrides = {};
  }
  return _pdOverrides;
}

async function _pdSaveOverrides(overrides) {
  _pdOverrides = overrides;
  const content = JSON.stringify(overrides, null, 2);
  return _pdGhPush(
    MANUAL_OVERRIDES_PATH,
    content,
    "overrides: update manual bulletin URL overrides [from extension]"
  );
}

function _pdGetOverride(parishKey) {
  if (!_pdOverrides || !parishKey) return null;
  const raw = _pdOverrides[parishKey];
  if (!raw || typeof raw !== "object") return null;
  if (typeof raw.url !== "string" || !/^https?:\/\//i.test(raw.url)) return null;
  return raw;
}

// ── Recipe status cache ────────────────────────────────────────────────────
const _pdRecipeCache = {}; // key → "ok" | "dead" | "none"

async function _pdCheckRecipe(key) {
  if (_pdRecipeCache[key]) return _pdRecipeCache[key];
  try {
    const { content } = await _pdGhFetch(`parishes/recipes/${key}.json`);
    const data = JSON.parse(content);
    _pdRecipeCache[key] = data.status === "dead_url" ? "dead" : "ok";
  } catch (_e) {
    _pdRecipeCache[key] = "none";
  }
  return _pdRecipeCache[key];
}

// ── Rendering ─────────────────────────────────────────────────────────────

let _pdAllParishes  = [];
let _pdDioceseTexts = {}; // dioceseName → { text, path }

function _pdStatusDot(parish) {
  if (parish.disabled) return "⚫";
  if (_pdGetOverride(parish.key)) return "📌";
  const rs = _pdRecipeCache[parish.key];
  if (rs === "dead") return "🔴";
  if (rs === "ok")   return "🟢";
  if (rs === "none") return "🟡";
  return "⬜";
}

const _PD_DOT_TITLES = { "🟢": "Recipe trained", "🟡": "Needs training", "🔴": "Dead website", "⚫": "Disabled", "📌": "Manual override URL set", "⬜": "Checking…" };

function _pdRenderAll(searchTerm, excludes) {
  const container = document.getElementById("parish-dir-content");
  container.innerHTML = "";
  const lc = (searchTerm || "").toLowerCase();

  const byDiocese = {};
  for (const p of _pdAllParishes) {
    if (lc && !p.name.toLowerCase().includes(lc) && !(p.key || "").includes(lc)) continue;
    if (!byDiocese[p.diocese]) byDiocese[p.diocese] = [];
    byDiocese[p.diocese].push(p);
  }

  for (const [diocese, parishes] of Object.entries(byDiocese)) {
    const dioceseEl = document.createElement("div");
    dioceseEl.className = "pd-diocese";
    const title = document.createElement("div");
    title.className = "pd-diocese-title";
    title.textContent = `${diocese} (${parishes.length})`;
    dioceseEl.appendChild(title);
    for (const parish of parishes) dioceseEl.appendChild(_pdBuildRow(parish, excludes));
    container.appendChild(dioceseEl);
  }

  if (!container.children.length) {
    container.textContent = lc ? "No matching parishes." : "No parishes loaded.";
    container.style.color = "#6b7280";
    container.style.fontSize = "10px";
  }
}

function _pdBuildRow(parish, excludes) {
  const wrap = document.createElement("div");
  wrap.dataset.key = parish.key;

  const row = document.createElement("div");
  row.className = "pd-row";

  const dot = document.createElement("span");
  dot.className = "pd-status";
  dot.textContent = _pdStatusDot(parish);
  dot.title = _PD_DOT_TITLES[dot.textContent] || "";
  row.appendChild(dot);

  const nameEl = document.createElement("span");
  nameEl.className = "pd-name" + (parish.disabled ? " disabled" : "");
  nameEl.textContent = parish.name;
  nameEl.title = parish.pageUrl || parish.bulletinUrls[0] || parish.key;
  if (parish.pageUrl || parish.bulletinUrls[0]) {
    nameEl.addEventListener("click", () => chrome.tabs.create({ url: parish.pageUrl || parish.bulletinUrls[0] }));
  }
  row.appendChild(nameEl);

  const editBtn = document.createElement("button");
  editBtn.className = "pd-btn";
  editBtn.textContent = "✏️";
  editBtn.title = "Edit bulletin page URL";
  editBtn.addEventListener("click", () => _pdShowEditRow(wrap, parish));
  row.appendChild(editBtn);

  const overrideBtn = document.createElement("button");
  overrideBtn.className = "pd-btn";
  overrideBtn.textContent = "📌";
  overrideBtn.title = "Set manual bulletin override from active tab URL";
  overrideBtn.addEventListener("click", () => _pdSetOverrideFromActiveTab(parish, dot, clearOverrideBtn));
  row.appendChild(overrideBtn);

  const clearOverrideBtn = document.createElement("button");
  clearOverrideBtn.className = "pd-btn";
  clearOverrideBtn.textContent = "🧹";
  clearOverrideBtn.title = "Clear manual bulletin override";
  clearOverrideBtn.disabled = !_pdGetOverride(parish.key);
  clearOverrideBtn.style.opacity = clearOverrideBtn.disabled ? "0.4" : "1";
  clearOverrideBtn.addEventListener("click", () => _pdClearOverride(parish, dot, clearOverrideBtn));
  row.appendChild(clearOverrideBtn);

  if (!parish.disabled) {
    const deadBtn = document.createElement("button");
    deadBtn.className = "pd-btn red";
    deadBtn.textContent = "☠";
    deadBtn.title = "Mark as dead website";
    deadBtn.addEventListener("click", () => _pdMarkDead(parish, dot, deadBtn));
    row.appendChild(deadBtn);
  }

  const excl = document.createElement("input");
  excl.type = "checkbox";
  excl.className = "pd-excl";
  excl.title = "Exclude from mega PDF this week";
  excl.checked = excludes.includes(parish.key);
  excl.addEventListener("change", async () => {
    excl.disabled = true;
    try {
      const current = await _pdLoadExcludes();
      const updated = excl.checked
        ? [...new Set([...current, parish.key])]
        : current.filter((k) => k !== parish.key);
      const res = await _pdSaveExcludes(updated);
      if (!res?.ok) { excl.checked = !excl.checked; setStatus(`❌ ${res?.error || "Save failed."}`, "err"); }
      else setStatus(`✅ ${parish.name} ${excl.checked ? "excluded from" : "included in"} mega PDF.`, "ok");
    } catch (err) {
      excl.checked = !excl.checked; setStatus(`❌ ${err.message}`, "err");
    } finally {
      excl.disabled = false;
    }
  });
  row.appendChild(excl);

  const exclLabel = document.createElement("span");
  exclLabel.className = "pd-excl-label";
  exclLabel.textContent = "skip";
  row.appendChild(exclLabel);

  wrap.appendChild(row);
  return wrap;
}

function _pdShowEditRow(wrap, parish) {
  const existing = wrap.querySelector(".pd-edit-row");
  if (existing) { existing.remove(); return; }

  const info = _pdDioceseTexts[parish.diocese];
  const editRow = document.createElement("div");
  editRow.className = "pd-edit-row";

  const label = document.createElement("div");
  label.style.cssText = "font-size:9px;color:#93c5fd;";
  label.textContent = "Bulletin listing page URL:";
  editRow.appendChild(label);

  const inp = document.createElement("input");
  inp.type = "url";
  inp.value = parish.pageUrl || "";
  inp.placeholder = "https://parish.com/bulletins";
  editRow.appendChild(inp);

  const btnRow = document.createElement("div");
  btnRow.className = "pd-edit-btns";

  const saveBtn = document.createElement("button");
  saveBtn.type = "button";
  saveBtn.className = "green";
  saveBtn.textContent = "💾 Save";
  saveBtn.addEventListener("click", async () => {
    const newUrl = inp.value.trim();
    if (!newUrl) { setStatus("❌ URL is required.", "err"); return; }
    if (!info)   { setStatus("❌ Evidence file not loaded.", "err"); return; }
    saveBtn.disabled = true; saveBtn.textContent = "⏳";
    try {
      const updated = _pdUpdatePageUrl(info.text, parish.name, newUrl);
      const res = await _pdGhPush(info.path, updated, `evidence: update page URL for ${parish.name} [from extension]`);
      if (res?.ok) {
        info.text = updated;
        parish.pageUrl = newUrl;
        setStatus(`✅ Saved page URL for ${parish.name}.`, "ok");
        editRow.remove();
      } else {
        setStatus(`❌ ${res?.error || "Save failed."}`, "err");
      }
    } catch (err) {
      setStatus(`❌ ${err.message}`, "err");
    } finally {
      saveBtn.disabled = false; saveBtn.textContent = "💾 Save";
    }
  });
  btnRow.appendChild(saveBtn);

  const cancelBtn = document.createElement("button");
  cancelBtn.type = "button";
  cancelBtn.style.cssText = "background:#374151;color:#d1d5db;";
  cancelBtn.textContent = "✕ Cancel";
  cancelBtn.addEventListener("click", () => editRow.remove());
  btnRow.appendChild(cancelBtn);

  editRow.appendChild(btnRow);
  wrap.appendChild(editRow);
  inp.focus();
}

async function _pdSetOverrideFromActiveTab(parish, dotEl, clearBtn) {
  let tab;
  try {
    [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  } catch (err) {
    setStatus(`❌ Could not read active tab: ${err.message}`, "err");
    return;
  }
  const url = (tab?.url || "").trim();
  if (!/^https?:\/\//i.test(url)) {
    setStatus("❌ Active tab URL must be http/https.", "err");
    return;
  }
  const type = _pdInferOverrideType(url);
  const overrides = await _pdLoadOverrides();
  overrides[parish.key] = {
    url,
    type,
    updated_at: new Date().toISOString(),
    source: "extension-sidepanel",
  };
  const res = await _pdSaveOverrides(overrides);
  if (!res?.ok) {
    setStatus(`❌ ${res?.error || "Failed to save override."}`, "err");
    return;
  }
  dotEl.textContent = "📌";
  dotEl.title = _PD_DOT_TITLES["📌"];
  clearBtn.disabled = false;
  clearBtn.style.opacity = "1";
  setStatus(`✅ Saved manual override for ${parish.name}.`, "ok");
}

async function _pdClearOverride(parish, dotEl, clearBtn) {
  const overrides = await _pdLoadOverrides();
  if (!overrides[parish.key]) {
    setStatus(`ℹ️ ${parish.name} has no override set.`, "info");
    return;
  }
  delete overrides[parish.key];
  const res = await _pdSaveOverrides(overrides);
  if (!res?.ok) {
    setStatus(`❌ ${res?.error || "Failed to clear override."}`, "err");
    return;
  }
  dotEl.textContent = _pdStatusDot(parish);
  dotEl.title = _PD_DOT_TITLES[dotEl.textContent] || "";
  clearBtn.disabled = true;
  clearBtn.style.opacity = "0.4";
  setStatus(`✅ Cleared override for ${parish.name}.`, "ok");
}

async function _pdMarkDead(parish, dotEl, btnEl) {
  if (!confirm(`Mark "${parish.name}" as a dead website?\nThis pushes a dead recipe to GitHub.`)) return;
  btnEl.disabled = true;
  setStatus(`⏳ Marking ${parish.name} as dead…`, "ok");
  try {
    const recipe = {
      parish: parish.name,
      url: parish.pageUrl || parish.bulletinUrls[0] || "",
      status: "dead_url",
      dead_reason: "Marked dead from browser extension.",
    };
    const res = await new Promise((resolve, reject) => {
      chrome.runtime.sendMessage({ type: "push_recipe", parish_key: parish.key, recipe }, (r) => {
        if (chrome.runtime.lastError) { reject(new Error(chrome.runtime.lastError.message)); return; }
        resolve(r);
      });
    });
    if (res?.ok) {
      _pdRecipeCache[parish.key] = "dead";
      dotEl.textContent = "🔴";
      dotEl.title = "Dead website";
      setStatus(`✅ ${parish.name} marked as dead.`, "ok");
    } else {
      setStatus(`❌ ${res?.error || "Failed."}`, "err");
    }
  } catch (err) {
    setStatus(`❌ ${err.message}`, "err");
  } finally {
    btnEl.disabled = false;
  }
}

// ── Main load ─────────────────────────────────────────────────────────────

async function loadParishDirectory() {
  const loadingEl = document.getElementById("parish-dir-loading");
  const errorEl   = document.getElementById("parish-dir-error");
  const container = document.getElementById("parish-dir-content");
  loadingEl.style.display = "block";
  errorEl.style.display   = "none";
  container.innerHTML     = "";
  _pdAllParishes = []; _pdDioceseTexts = {}; _pdExcludes = null; _pdOverrides = null;

  try {
    const [excludes, _overrides, ...evidenceResults] = await Promise.all([
      _pdLoadExcludes(),
      _pdLoadOverrides(),
      ...Object.entries(PD_EVIDENCE_FILES).map(([diocese, path]) =>
        _pdGhFetch(path)
          .then(({ content }) => ({ diocese, path, content }))
          .catch((e) => ({ diocese, path, error: e.message }))
      ),
    ]);

    for (const r of evidenceResults) {
      if (r.error) { console.warn(`Parish Directory: ${r.diocese}: ${r.error}`); continue; }
      _pdDioceseTexts[r.diocese] = { text: r.content, path: r.path };
      _pdAllParishes.push(..._pdParseEvidence(r.content, r.diocese));
    }

    if (_pdAllParishes.length === 0) {
      errorEl.textContent = "⚠️ No parishes loaded — check GitHub settings.";
      errorEl.style.display = "block";
      return;
    }

    loadingEl.style.display = "none";
    _pdRenderAll("", excludes);

    // Asynchronously load recipe status and refresh dots
    (async () => {
      await Promise.all(_pdAllParishes.map((p) => p.key ? _pdCheckRecipe(p.key) : Promise.resolve()));
      const c = document.getElementById("parish-dir-content");
      for (const p of _pdAllParishes) {
        if (!p.key) continue;
        const el = c.querySelector(`[data-key="${CSS.escape(p.key)}"] .pd-status`);
        if (el) { el.textContent = _pdStatusDot(p); el.title = _PD_DOT_TITLES[el.textContent] || ""; }
      }
    })();

  } catch (err) {
    loadingEl.style.display = "none";
    errorEl.textContent = `❌ ${err.message}`;
    errorEl.style.display = "block";
  }
}

document.getElementById("parish-dir-details").addEventListener("toggle", function () {
  if (this.open && _pdAllParishes.length === 0) loadParishDirectory();
});
document.getElementById("pd-refresh").addEventListener("click", () => {
  Object.keys(_pdRecipeCache).forEach((k) => delete _pdRecipeCache[k]);
  _pdExcludes = null;
  _pdOverrides = null;
  loadParishDirectory();
});
document.getElementById("pd-search").addEventListener("input", function () {
  if (_pdAllParishes.length > 0) _pdRenderAll(this.value, _pdExcludes || []);
});

// ── Crop done notification ─────────────────────────────────────────────────

chrome.runtime.onMessage.addListener((message) => {
  if (message?.type !== "crop_done") return;
  const x = Number(message.x ?? 0);
  const y = Number(message.y ?? 0);
  const width = Number(message.width ?? 0);
  const height = Number(message.height ?? 0);
  const pageX = Number(message.pageX ?? x);
  const pageY = Number(message.pageY ?? y);
  const elementSelector = message.element_selector || "";

  setStatus(`✂️ Crop saved (${Math.round(width)}×${Math.round(height)})`, "ok");

  void withActiveTab((tabId) => {
    chrome.tabs.sendMessage(tabId, {
      type: "mark_crop",
      x,
      y,
      width,
      height,
      pageX,
      pageY,
      element_selector: elementSelector,
    });
  });
});
