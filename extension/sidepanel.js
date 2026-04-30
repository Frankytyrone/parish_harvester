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
