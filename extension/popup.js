const statusEl = document.getElementById("status");

function setStatusText(text) {
  statusEl.textContent = text;
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
        if (!result) {
          setStatusText("Could not communicate with page. Try refreshing.");
        } else if (result.reason === "unsupported_url") {
          setStatusText("This tab cannot be scripted. Open a normal http/https page.");
        } else if (result.reason === "inject_failed") {
          setStatusText("Page script bridge failed to load. Refresh the page and try again.");
        } else if (result.reason === "receiver_unavailable") {
          setStatusText("Page bridge not responding. Refresh the tab and try again.");
        } else if (result.reason === "tab_not_found") {
          setStatusText("Could not access active tab.");
        } else {
          setStatusText(`Could not communicate with page. ${result.error || "Try refreshing."}`);
        }
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
  const statusEl2 = document.getElementById("gh-save-status");
  if (!pat || !repo) {
    statusEl2.textContent = "❌ Both PAT and repository are required.";
    statusEl2.style.color = "#fca5a5";
    return;
  }
  chrome.storage.local.set({ gh_pat: pat, gh_repo: repo }, () => {
    statusEl2.textContent = "✅ Settings saved.";
    statusEl2.style.color = "#86efac";
    setTimeout(() => { statusEl2.textContent = ""; }, 3000);
  });
});
