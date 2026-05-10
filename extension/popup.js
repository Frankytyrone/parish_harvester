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

async function sendToActiveTab(message) {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id) {
    setStatusText("No active tab.");
    return;
  }
  if (!/^https?:\/\//i.test(tab.url || "")) {
    setStatusText("This tab is not scriptable. Open a normal http/https page.");
    return;
  }

  chrome.runtime.sendMessage(
    {
      type: "dispatch_to_tab",
      tabId: tab.id,
      payload: message,
      allowInject: true,
    },
    (result) => {
      if (chrome.runtime.lastError) {
        setStatusText(`Could not communicate with extension background: ${chrome.runtime.lastError.message}`);
        return;
      }
      if (!result?.ok) {
        setStatusText(formatDispatchError(result));
        return;
      }

      if (message.type === "show_toolbar") {
        setStatusText("Toolbar shown.");
      }
    }
  );
}

document.getElementById("show-toolbar").addEventListener("click", () => {
  void sendToActiveTab({ type: "show_toolbar" });
});

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
