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

function renderDiagnostics(results) {
  if (!diagResultsEl) return;
  diagResultsEl.replaceChildren();
  for (const result of results) {
    const row = document.createElement("div");
    const icon = document.createElement("span");
    icon.textContent = result.ok ? "✅ " : "❌ ";
    icon.style.color = result.ok ? "#86efac" : "#fca5a5";
    const text = document.createElement("span");
    text.textContent = result.text;
    row.append(icon, text);
    diagResultsEl.appendChild(row);
  }
}

async function runDiagnostics() {
  const results = [];
  results.push({ ok: true, text: `Extension version: v${manifest.version}` });

  const settings = await new Promise((resolve) => {
    chrome.storage.local.get(["gh_pat", "gh_repo"], resolve);
  });
  const pat = typeof settings.gh_pat === "string" ? settings.gh_pat.trim() : "";
  const repo = typeof settings.gh_repo === "string" ? settings.gh_repo.trim() : "";
  results.push({ ok: Boolean(pat), text: pat ? "GitHub PAT saved." : "GitHub PAT missing." });
  results.push({ ok: Boolean(repo), text: repo ? `GitHub Repo saved: ${repo}` : "GitHub Repo missing." });

  const pingResult = await dispatchToActiveTab({ type: "ping" });
  if (pingResult?.ok) {
    results.push({ ok: true, text: "Content script responding." });
  } else {
    const compatPingResult = await dispatchToActiveTab({ type: "ph_ping" });
    if (compatPingResult?.ok) {
      results.push({ ok: true, text: "Content script responding." });
    } else {
      results.push({ ok: false, text: "Content script not responding — try refreshing the page." });
    }
  }

  results.push({ ok: true, text: "Background worker alive." });
  renderDiagnostics(results);
}

if (diagBtn) {
  diagBtn.addEventListener("click", () => {
    void runDiagnostics();
  });
}

void sendToActiveTab({ type: "show_toolbar" });
