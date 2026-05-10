chrome.runtime.onMessage.addListener((message) => {
  window.postMessage({ direction: "from-isolated", message }, "*");
});

window.addEventListener("message", (event) => {
  if (event.source !== window) return;
  if (event.data && event.data.direction === "from-main") {
    const reqId = event.data.reqId || null;
    if (reqId) {
      // Caller expects a response — route it back via postMessage.
      chrome.runtime.sendMessage(event.data.message, (response) => {
        const lastErr = chrome.runtime.lastError;
        window.postMessage(
          {
            direction: "from-isolated-response",
            reqId,
            response: response || null,
            error: lastErr ? lastErr.message : null,
          },
          "*"
        );
      });
    } else {
      chrome.runtime.sendMessage(event.data.message);
    }
  }
});
