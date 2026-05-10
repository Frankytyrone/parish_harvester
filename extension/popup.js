const statusEl = document.getElementById("status");

function setStatus(text) {
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
    setStatus("No active tab.");
    return;
  }
  if (!/^https?:\/\//i.test(tab.url || "")) {
    setStatus("This tab is not scriptable. Open a normal http/https page.");
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
        setStatus(`Could not communicate with extension background: ${chrome.runtime.lastError.message}`);
        return;
      }
      if (!result?.ok) {
        setStatus(formatDispatchError(result));
        return;
      }

      if (message.type === "show_toolbar") {
        setStatus("Toolbar shown.");
      } else if (message.type === "mark_html") {
        setStatus("Marked HTML page.");
      } else if (message.type === "mark_file") {
        setStatus("Marked current URL as file.");
      } else if (message.type === "mark_image") {
        setStatus("Marked bulletin image.");
      }
    }
  );
}

document.getElementById("show-toolbar").addEventListener("click", () => {
  void sendToActiveTab({ type: "show_toolbar" });
});

document.getElementById("open-operator").addEventListener("click", () => {
  chrome.tabs.create({ url: chrome.runtime.getURL("sidepanel.html") });
  setStatus("Opened operator console.");
});

document.getElementById("mark-html").addEventListener("click", () => {
  void sendToActiveTab({ type: "mark_html" });
});

document.getElementById("mark-file").addEventListener("click", () => {
  void sendToActiveTab({ type: "mark_file" });
});
