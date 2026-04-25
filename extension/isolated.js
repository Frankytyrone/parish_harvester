chrome.runtime.onMessage.addListener((message) => {
  window.postMessage({ direction: "from-isolated", message }, "*");
});

window.addEventListener("message", (event) => {
  if (event.source !== window) return;
  if (event.data && event.data.direction === "from-main") {
    chrome.runtime.sendMessage(event.data.message);
  }
});
