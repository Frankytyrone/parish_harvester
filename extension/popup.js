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
    return "Page bridge not responding. Refresh the tab, or click the toolbar icon again, then retry.";
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
  let result = await dispatchToActiveTab(message);
  if (!result?.ok && result.reason === "receiver_unavailable") {
    await new Promise((resolve) => setTimeout(resolve, 500));
    result = await dispatchToActiveTab(message);
  }
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

chrome.storage.local.get(["gh_pat", "gh_repo", "mistral_api_key", "gemini_api_key"], (r) => {
  const patInput  = document.getElementById("gh-pat");
  const repoInput = document.getElementById("gh-repo");
  const mistralInput = document.getElementById("mistral-api-key");
  const geminiInput = document.getElementById("gemini-api-key");
  if (patInput  && r.gh_pat)  patInput.value  = r.gh_pat;
  if (repoInput && r.gh_repo) repoInput.value = r.gh_repo;
  if (mistralInput && r.mistral_api_key) mistralInput.value = r.mistral_api_key;
  if (geminiInput && r.gemini_api_key) geminiInput.value = r.gemini_api_key;
});

document.getElementById("gh-save").addEventListener("click", () => {
  const pat  = (document.getElementById("gh-pat").value  || "").trim();
  const repo = (document.getElementById("gh-repo").value || "").trim();
  const mistralApiKey = (document.getElementById("mistral-api-key").value || "").trim();
  const geminiApiKey = (document.getElementById("gemini-api-key").value || "").trim();
  const ghStatusEl = document.getElementById("gh-save-status");
  chrome.storage.local.set({
    gh_pat: pat,
    gh_repo: repo,
    mistral_api_key: mistralApiKey,
    gemini_api_key: geminiApiKey,
  }, () => {
    if (chrome.runtime.lastError) {
      ghStatusEl.textContent = `❌ Save failed: ${chrome.runtime.lastError.message}`;
      ghStatusEl.style.color = "#fca5a5";
      setTimeout(() => { ghStatusEl.textContent = ""; }, 4000);
      return;
    }
    if (!pat || !repo) {
      ghStatusEl.textContent = "⚠️ Saved. Add GitHub PAT + repo to enable recipe push.";
      ghStatusEl.style.color = "#fde68a";
    } else {
      ghStatusEl.textContent = "✅ Settings saved.";
      ghStatusEl.style.color = "#86efac";
    }
    setTimeout(() => { ghStatusEl.textContent = ""; }, 3000);
  });
});

const diagBtn = document.getElementById("run-diag");
const diagResultsEl = document.getElementById("diag-results");
const diagCopyBtn = document.getElementById("diag-copy");

// Holds plain-text lines for "Copy diagnostic info (paste to AI)"
let _diagTextLines = [];
const _diagCopyButtonLabel = "📋 Copy diagnostic info (paste to AI)";

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
}

function _maskGeminiKey(value) {
  const key = String(value || "").trim();
  if (!key) return "no";
  if (key.length <= 8) return "****";
  return `${key.slice(0, 4)}…${key.slice(-4)}`;
}

function _clipLinesTo4000Chars(lines) {
  // Keep the copied dump comfortably under ~4 KB for easy paste into chat tools.
  const safeLines = [];
  let used = 0;
  let truncated = false;
  for (const line of lines) {
    const next = String(line || "");
    const delta = next.length + 1;
    if (used + delta > 4000) {
      truncated = true;
      break;
    }
    safeLines.push(next);
    used += delta;
  }
  if (truncated && safeLines.length > 0) {
    safeLines.push("... (output truncated)");
  }
  return safeLines;
}

async function _fetchGitHubUserLogin(pat) {
  if (!pat) return "";
  try {
    const patRes = await fetch("https://api.github.com/user", {
      headers: { Authorization: `token ${pat}`, "User-Agent": "ParishHarvester" },
    });
    if (!patRes.ok) return "";
    const patData = await patRes.json();
    return String(patData?.login || "");
  } catch (_e) {
    return "";
  }
}

async function runDiagnostics() {
  if (!diagResultsEl) return;
  diagResultsEl.replaceChildren();
  _diagTextLines = [];
  if (diagCopyBtn) diagCopyBtn.style.display = "none";

  const versionLine = `Extension version: ${chrome.runtime.getManifest().version}`;
  const userAgentLine = `Browser user-agent: ${navigator.userAgent || "n/a"}`;
  const [activeTab] = await chrome.tabs.query({ active: true, currentWindow: true });
  const activeUrl = String(activeTab?.url || "").trim();
  const activeTabIsHttp = /^https?:\/\//i.test(activeUrl);
  const activeTabUrlLine = `Active tab URL: ${activeTabIsHttp ? activeUrl : "n/a — extension tab"}`;
  const activeTabTypeLine = `Active tab is real http(s) page: ${activeTabIsHttp ? "yes" : "no"}`;

  const allLocalStorage = await new Promise((resolve) => chrome.storage.local.get(null, resolve));
  const pat = typeof allLocalStorage.gh_pat === "string" ? allLocalStorage.gh_pat.trim() : "";
  const repo = typeof allLocalStorage.gh_repo === "string" ? allLocalStorage.gh_repo.trim() : "";
  const mistralKey = typeof allLocalStorage.mistral_api_key === "string" ? allLocalStorage.mistral_api_key.trim() : "";
  const geminiKey = typeof allLocalStorage.gemini_api_key === "string" ? allLocalStorage.gemini_api_key.trim() : "";
  const ghLogin = await _fetchGitHubUserLogin(pat);

  const patLine = `GitHub PAT present: ${pat ? "yes" : "no"}${ghLogin ? ` (authenticated user: ${ghLogin})` : ""}`;
  const repoLine = `GitHub repo configured: ${repo || "n/a"}`;
  const mistralLine = `Mistral key present: ${mistralKey ? "yes" : "no"}`;
  const geminiLine = `Gemini key present: ${geminiKey ? "yes" : "no"}${geminiKey ? ` (${_maskGeminiKey(geminiKey)})` : ""}`;

  const memoryKeys = Object.keys(allLocalStorage || {})
    .filter((key) => key.startsWith("ph_ai_memory_"))
    .slice(-10);
  const memoryHeader = "Last 10 ph_ai_memory_* keys:";
  const memoryLines = memoryKeys.length > 0 ? memoryKeys.map((key) => `- ${key}`) : ["- (none)"];

  let aiLogLines = ["- (none yet)"];
  const aiLogData = allLocalStorage["ph_ai_help_log"];
  if (Array.isArray(aiLogData) && aiLogData.length > 0) {
    aiLogLines = aiLogData.slice(-5).map((entry) => {
      const status = entry?.succeeded ? "ok" : "failed";
      const ts = entry?.ts || "n/a";
      const msg = String(entry?.errorMessage || "").slice(0, 120);
      return `- ${ts} | ${entry?.attempt || "unknown"} | ${status}${msg ? ` | ${msg}` : ""}`;
    });
  }

  const dumpLines = _clipLinesTo4000Chars([
    "Parish Trainer diagnostic dump",
    "============================",
    versionLine,
    userAgentLine,
    activeTabUrlLine,
    activeTabTypeLine,
    patLine,
    repoLine,
    mistralLine,
    geminiLine,
    memoryHeader,
    ...memoryLines,
    "Recent AI Help log entries (last 5):",
    ...aiLogLines,
    "Paste this whole block to your AI assistant.",
  ]);
  _diagTextLines = dumpLines;

  _addDiagRow("ℹ️", versionLine);
  _addDiagRow("📄", activeTabUrlLine);
  _addDiagRow("🔍", activeTabTypeLine);
  _addDiagRow("🔐", patLine);
  _addDiagRow("📦", repoLine);
  _addDiagRow("🤖", geminiLine);
  _addDiagRow("📋", "Diagnostic text is ready to copy.");

  if (diagCopyBtn) diagCopyBtn.style.display = "";
}

if (diagBtn) {
  diagBtn.addEventListener("click", () => {
    void runDiagnostics();
  });
}

if (diagCopyBtn) {
  diagCopyBtn.style.display = "none";
  diagCopyBtn.textContent = _diagCopyButtonLabel;
  diagCopyBtn.addEventListener("click", () => {
    const text = _diagTextLines.join("\n");
    navigator.clipboard.writeText(text).then(() => {
      diagCopyBtn.textContent = "✅ Copied!";
      setTimeout(() => { diagCopyBtn.textContent = _diagCopyButtonLabel; }, 2000);
    }).catch((_e) => {
      console.error("Parish Trainer: clipboard copy failed:", _e);
      diagCopyBtn.textContent = "❌ Copy failed";
      setTimeout(() => { diagCopyBtn.textContent = _diagCopyButtonLabel; }, 2000);
    });
  });
}

void sendToActiveTab({ type: "show_toolbar" });
