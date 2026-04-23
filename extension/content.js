(() => {
  const cssPath = (el) => {
    if (!el || el.nodeType !== Node.ELEMENT_NODE) return "";
    const parts = [];
    let current = el;
    while (current && current.nodeType === Node.ELEMENT_NODE && parts.length < 6) {
      let selector = current.tagName.toLowerCase();
      if (current.id) {
        selector += "#" + current.id;
        parts.unshift(selector);
        break;
      }
      const parent = current.parentElement;
      if (parent) {
        const siblings = Array.from(parent.children).filter((c) => c.tagName === current.tagName);
        if (siblings.length > 1) {
          selector += `:nth-of-type(${siblings.indexOf(current) + 1})`;
        }
      }
      parts.unshift(selector);
      current = current.parentElement;
    }
    return parts.join(" > ");
  };

  chrome.runtime.onMessage.addListener((message) => {
    const type = message?.type;
    if (type === "mark_html") {
      if (!window.ph_mark_html) {
        console.warn("Parish Trainer: ph_mark_html binding is unavailable.");
        return;
      }
      window.ph_mark_html({ url: window.location.href });
      return;
    }
    if (type === "mark_file") {
      if (!window.ph_mark_download_url) {
        console.warn("Parish Trainer: ph_mark_download_url binding is unavailable.");
        return;
      }
      window.ph_mark_download_url({ url: window.location.href });
      return;
    }
    if (type === "mark_image" && message?.url) {
      if (!window.ph_mark_image) {
        console.warn("Parish Trainer: ph_mark_image binding is unavailable.");
        return;
      }
      window.ph_mark_image({ url: message.url });
    }
  });

  document.addEventListener(
    "click",
    (event) => {
      const target =
        event.target instanceof Element
          ? event.target.closest("a,button,[role],input[type=\"submit\"],input[type=\"button\"]")
          : null;
      if (!target) return;
      if (!window.ph_record_click) {
        return;
      }
      window.ph_record_click({
        tag: (target.tagName || "").toLowerCase(),
        role: (target.getAttribute("role") || "").toLowerCase(),
        text: (target.innerText || target.textContent || "").trim().slice(0, 200),
        href: target.getAttribute("href") || "",
        css_path: cssPath(target),
      });
    },
    true
  );
})();
