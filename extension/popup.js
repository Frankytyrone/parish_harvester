const manifest = chrome.runtime.getManifest();
const versionEl = document.getElementById("ext-version");
if (versionEl) versionEl.textContent = `v${manifest.version}`;

const statusEl = document.getElementById("status");

function setStatusText(text) {
  statusEl.textContent = text;
}

function formatDispatchError(result) {
  if (!result) return "Could not communicate with page. Try refreshing.";
  if (result.reason === "unsupported_url") {
    return "This tab cannot be scripted. Open a normal http/https page.";
  }
  if (result.reason === "inject_failed") {
    return "Page script bridge failed to load. Refresh the page and try again.";
  }
  if (result.reason === "receiver_unavailable") {
    return "Page bridge not responding. Refresh the tab and try again.";
  }
  if (result.reason === "tab_not_found") {
    return "Could not access active tab.";
  }
  return `Could not communicate with page. ${result.error || "Try refreshing."}`;
}

async function dispatchToActiveTab(message) {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id) {
    return { ok: false, reason: "tab_not_found" };
  }
  if (!/^https?:\/\//i.test(tab.url || "")) {
    return { ok: false, reason: "unsupported_url" };
  }

  return await new Promise((resolve) => {
    chrome.runtime.sendMessage(
      {
        type: "dispatch_to_tab",
        tabId: tab.id,
        payload: message,
        allowInject: true,
      },
      (result) => {
        if (chrome.runtime.lastError) {
          resolve({
            ok: false,
            reason: "runtime_error",
            error: chrome.runtime.lastError.message,
          });
          return;
        }
        resolve(result || { ok: false, reason: "dispatch_error" });
      }
    );
  });
}

async function sendToActiveTab(message) {
  const result = await dispatchToActiveTab(message);
  if (!result?.ok) {
    if (result.reason === "runtime_error") {
      setStatusText(`Could not communicate with extension background: ${result.error}`);
      return;
    }
    setStatusText(formatDispatchError(result));
    return;
  }

  if (message.type === "show_toolbar") {
    setStatusText("Toolbar shown.");
  }
}

document.getElementById("open-operator").addEventListener("click", () => {
  chrome.tabs.create({ url: chrome.runtime.getURL("sidepanel.html") });
  setStatusText("Opened operator console.");
});

// ── GitHub Settings ────────────────────────────────────────────────────────

chrome.storage.local.get(["gh_pat", "gh_repo"], (r) => {
  const patInput  = document.getElementById("gh-pat");
  const repoInput = document.getElementById("gh-repo");
  if (patInput  && r.gh_pat)  patInput.value  = r.gh_pat;
  if (repoInput && r.gh_repo) repoInput.value = r.gh_repo;
});

document.getElementById("gh-save").addEventListener("click", () => {
  const pat  = (document.getElementById("gh-pat").value  || "").trim();
  const repo = (document.getElementById("gh-repo").value || "").trim();
  const ghStatusEl = document.getElementById("gh-save-status");
  if (!pat || !repo) {
    ghStatusEl.textContent = "❌ Both PAT and repository are required.";
    ghStatusEl.style.color = "#fca5a5";
    return;
  }
  chrome.storage.local.set({ gh_pat: pat, gh_repo: repo }, () => {
    ghStatusEl.textContent = "✅ Settings saved.";
    ghStatusEl.style.color = "#86efac";
    setTimeout(() => { ghStatusEl.textContent = ""; }, 3000);
  });
});

const diagBtn = document.getElementById("run-diag");
const diagResultsEl = document.getElementById("diag-results");
const diagCopyBtn = document.getElementById("diag-copy");

// Holds plain-text lines for "Copy Debug Info"
let _diagTextLines = [];

function _addDiagRow(icon, text) {
  if (!diagResultsEl) return null;
  const row = document.createElement("div");
  row.style.cssText = "display:flex;align-items:baseline;gap:4px;";
  const iconEl = document.createElement("span");
  iconEl.textContent = icon + " ";
  const textEl = document.createElement("span");
  textEl.textContent = text;
  row.append(iconEl, textEl);
  diagResultsEl.appendChild(row);
  return row;
}

function _updateDiagRow(row, icon, text) {
  if (!row) return;
  row.children[0].textContent = icon + " ";
  row.children[1].textContent = text;
  _diagTextLines.push(icon + " " + text);
}

async function runDiagnostics() {
  if (!diagResultsEl) return;
  diagResultsEl.replaceChildren();
  _diagTextLines = [];
  if (diagCopyBtn) diagCopyBtn.style.display = "none";

  // 1. Version
  const versionLine = `Extension version: v${manifest.version}`;
  _addDiagRow("ℹ️", versionLine);
  _diagTextLines.push("ℹ️ " + versionLine);

  // 2. Current page URL
  const [activeTab] = await chrome.tabs.query({ active: true, currentWindow: true });
  const pageUrl = activeTab?.url || "(unknown)";
  const truncatedUrl = pageUrl.length > 60 ? pageUrl.slice(0, 57) + "…" : pageUrl;
  const urlLine = `Current page: ${truncatedUrl}`;
  _addDiagRow("📄", urlLine);
  _diagTextLines.push("📄 " + urlLine);

  // 3. GitHub PAT check
  const patRow = _addDiagRow("⏳", "Checking GitHub PAT…");
  const settings = await new Promise((resolve) => {
    chrome.storage.local.get(["gh_pat", "gh_repo"], resolve);
  });
  const pat = typeof settings.gh_pat === "string" ? settings.gh_pat.trim() : "";
  const repo = typeof settings.gh_repo === "string" ? settings.gh_repo.trim() : "";

  let patValid = false;
  if (!pat) {
    _updateDiagRow(patRow, "❌", "GitHub PAT missing — open Settings below and paste your token");
  } else {
    try {
      const patRes = await fetch("https://api.github.com/user", {
        headers: { Authorization: `token ${pat}`, "User-Agent": "ParishHarvester" },
      });
      if (patRes.ok) {
        const patData = await patRes.json();
        const login = patData.login || "";
        patValid = true;
        _updateDiagRow(patRow, "✅", `GitHub PAT valid — authenticated as ${login}`);
      } else if (patRes.status === 401) {
        _updateDiagRow(patRow, "❌", "GitHub PAT is INVALID or expired — go to Settings and enter a new one");
      } else {
        _updateDiagRow(patRow, "❌", `GitHub PAT check failed (HTTP ${patRes.status})`);
      }
    } catch (_e) {
      _updateDiagRow(patRow, "❌", "GitHub PAT check failed — network error");
    }
  }

  // 4. GitHub Repo check
  const repoRow = _addDiagRow("⏳", "Checking GitHub Repo…");
  if (!repo) {
    _updateDiagRow(repoRow, "❌", "No repo saved — open Settings and enter owner/repo");
  } else if (!patValid) {
    _updateDiagRow(repoRow, "⚠️", "Repo check skipped — fix PAT first");
  } else {
    try {
      const repoRes = await fetch(`https://api.github.com/repos/${repo}`, {
        headers: { Authorization: `token ${pat}`, "User-Agent": "ParishHarvester" },
      });
      if (repoRes.ok) {
        _updateDiagRow(repoRow, "✅", `Repo '${repo}' found and accessible`);
      } else if (repoRes.status === 404) {
        _updateDiagRow(repoRow, "❌", `Repo '${repo}' NOT FOUND — check the spelling in Settings`);
      } else {
        _updateDiagRow(repoRow, "❌", `Repo check failed (HTTP ${repoRes.status})`);
      }
    } catch (_e) {
      _updateDiagRow(repoRow, "❌", "Repo check failed — network error");
    }
  }

  // 5. Mistral API key check
  const mistralRow = _addDiagRow("⏳", "Checking Mistral API key…");
  const mistralSettings = await new Promise((resolve) => {
    chrome.storage.local.get(["mistral_api_key"], resolve);
  });
  const mistralKey = typeof mistralSettings.mistral_api_key === "string"
    ? mistralSettings.mistral_api_key.trim() : "";
  if (!mistralKey) {
    _updateDiagRow(mistralRow, "ℹ️", "Mistral not configured locally (runs server-side via GitHub secret)");
  } else {
    try {
      const mistralRes = await fetch("https://api.mistral.ai/v1/models", {
        headers: { Authorization: `Bearer ${mistralKey}`, "User-Agent": "ParishHarvester" },
      });
      if (mistralRes.ok) {
        _updateDiagRow(mistralRow, "✅", "Mistral API key valid");
      } else if (mistralRes.status === 401) {
        _updateDiagRow(mistralRow, "❌", "Mistral API key invalid");
      } else {
        _updateDiagRow(mistralRow, "❌", `Mistral check failed (HTTP ${mistralRes.status})`);
      }
    } catch (_e) {
      _updateDiagRow(mistralRow, "❌", "Mistral check failed — network error");
    }
  }

  // 6. Content script check
  const scriptRow = _addDiagRow("⏳", "Pinging page script…");
  const pingResult = await dispatchToActiveTab({ type: "ping" });
  let scriptOk = pingResult?.ok;
  if (!scriptOk) {
    const compatPingResult = await dispatchToActiveTab({ type: "ph_ping" });
    scriptOk = compatPingResult?.ok;
  }
  if (scriptOk) {
    _updateDiagRow(scriptRow, "✅", "Page script responding — toolbar ready");
  } else {
    _updateDiagRow(scriptRow, "❌", "Page script not responding — are you on a normal http/https page? Try refreshing.");
  }

  // 7. Standalone steps recorded
  const stepsRow = _addDiagRow("⏳", "Checking recorded steps…");
  if (scriptOk) {
    const stepsResult = await dispatchToActiveTab({ type: "get_standalone_steps" });
    if (stepsResult?.ok && typeof stepsResult.count === "number") {
      const count = stepsResult.count;
      if (count > 0) {
        _updateDiagRow(stepsRow, "📋", `Steps recorded this session: ${count}`);
      } else {
        _updateDiagRow(stepsRow, "📋", "No steps recorded yet this session");
      }
    } else {
      _updateDiagRow(stepsRow, "📋", "Steps count unavailable");
    }
  } else {
    _updateDiagRow(stepsRow, "📋", "Steps count unavailable (page script not responding)");
  }

  if (diagCopyBtn) diagCopyBtn.style.display = "";
}

if (diagBtn) {
  diagBtn.addEventListener("click", () => {
    void runDiagnostics();
  });
}

if (diagCopyBtn) {
  diagCopyBtn.style.display = "none";
  diagCopyBtn.addEventListener("click", () => {
    const text = _diagTextLines.join("\n");
    navigator.clipboard.writeText(text).then(() => {
      const orig = diagCopyBtn.textContent;
      diagCopyBtn.textContent = "✅ Copied!";
      setTimeout(() => { diagCopyBtn.textContent = orig; }, 2000);
    }).catch(() => {
      diagCopyBtn.textContent = "❌ Copy failed";
      setTimeout(() => { diagCopyBtn.textContent = "📋 Copy Debug Info"; }, 2000);
    });
  });
}

void sendToActiveTab({ type: "show_toolbar" });
