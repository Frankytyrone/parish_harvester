const statusEl = document.getElementById("status");

async function sendToActiveTab(message) {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id) {
    statusEl.textContent = "No active tab.";
    return;
  }

  chrome.tabs.sendMessage(tab.id, message, () => {
    if (chrome.runtime.lastError) {
      statusEl.textContent = "Could not communicate with page. Try refreshing or opening an http/https URL.";
      return;
    }

    if (message.type === "show_toolbar") {
      statusEl.textContent = "Toolbar shown.";
    } else if (message.type === "mark_html") {
      statusEl.textContent = "Marked HTML page";
    } else if (message.type === "mark_file") {
      statusEl.textContent = "Marked current URL as file";
    } else if (message.type === "mark_image") {
      statusEl.textContent = "Marked bulletin image";
    }
  });
}

document.getElementById("show-toolbar").addEventListener("click", () => {
  void sendToActiveTab({ type: "show_toolbar" });
});

document.getElementById("open-operator").addEventListener("click", () => {
  chrome.tabs.create({ url: chrome.runtime.getURL("sidepanel.html") });
  statusEl.textContent = "Opened operator console.";
});

document.getElementById("mark-html").addEventListener("click", () => {
  void sendToActiveTab({ type: "mark_html" });
});

document.getElementById("mark-file").addEventListener("click", () => {
  void sendToActiveTab({ type: "mark_file" });
});
