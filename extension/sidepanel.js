const statusEl = document.getElementById("status");

async function withActiveTab(callback) {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id) {
    statusEl.textContent = "No active tab.";
    return;
  }
  callback(tab.id);
}

async function sendToActiveTab(message, successText) {
  await withActiveTab((tabId) => {
    chrome.tabs.sendMessage(tabId, message, () => {
      if (chrome.runtime.lastError) {
        statusEl.textContent = "Could not communicate with page. Try refreshing or opening an http/https URL.";
        return;
      }
      statusEl.textContent = successText;
    });
  });
}

document.getElementById("mark-html").addEventListener("click", () => {
  void sendToActiveTab({ type: "mark_html" }, "Marked HTML page");
});

document.getElementById("mark-file").addEventListener("click", () => {
  void sendToActiveTab({ type: "mark_file" }, "Marked current URL as file");
});

document.getElementById("crop-btn").addEventListener("click", async () => {
  await sendToActiveTab({ type: "start_crop" }, "Click and drag to select the bulletin area...");
});

chrome.runtime.onMessage.addListener((message) => {
  if (message?.type !== "crop_done") {
    return;
  }
  const x = Number(message.x ?? 0);
  const y = Number(message.y ?? 0);
  const width = Number(message.width ?? 0);
  const height = Number(message.height ?? 0);
  const pageX = Number(message.pageX ?? x);
  const pageY = Number(message.pageY ?? y);
  const elementSelector = message.element_selector || "";

  statusEl.textContent = `Crop saved (${Math.round(width)}x${Math.round(height)})`;

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
