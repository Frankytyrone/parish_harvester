(() => {
  let cropOverlay = null;
  let lastCropSignature = "";

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

  const nearestElementSelector = (x, y) => {
    const candidates = document.elementsFromPoint(x, y);
    for (const el of candidates) {
      if (!(el instanceof Element)) {
        continue;
      }
      const img = el.closest("img");
      if (img) {
        return cssPath(img);
      }
      const container = el.closest("figure,article,section,main,div");
      if (container) {
        return cssPath(container);
      }
      return cssPath(el);
    }
    return "";
  };

  const emitCrop = (payload) => {
    lastCropSignature = JSON.stringify(payload);
    if (window.ph_mark_crop) {
      window.ph_mark_crop(payload);
    } else {
      console.warn("Parish Trainer: ph_mark_crop binding is unavailable.");
    }
    chrome.runtime.sendMessage({ type: "crop_done", ...payload });
  };

  const removeCropOverlay = () => {
    if (cropOverlay && cropOverlay.parentNode) {
      cropOverlay.parentNode.removeChild(cropOverlay);
    }
    cropOverlay = null;
  };

  const startCrop = () => {
    removeCropOverlay();

    const overlay = document.createElement("div");
    overlay.style.position = "fixed";
    overlay.style.top = "0";
    overlay.style.left = "0";
    overlay.style.width = "100%";
    overlay.style.height = "100%";
    overlay.style.zIndex = "2147483647";
    overlay.style.cursor = "crosshair";
    overlay.style.background = "rgba(37,99,235,0.02)";
    overlay.style.userSelect = "none";

    const rect = document.createElement("div");
    rect.style.position = "fixed";
    rect.style.border = "2px dashed #3b82f6";
    rect.style.background = "rgba(59,130,246,0.2)";
    rect.style.pointerEvents = "none";
    rect.style.display = "none";
    overlay.appendChild(rect);

    let startX = 0;
    let startY = 0;
    let dragging = false;

    const onMove = (event) => {
      if (!dragging) return;
      const currentX = event.clientX;
      const currentY = event.clientY;
      const left = Math.min(startX, currentX);
      const top = Math.min(startY, currentY);
      const width = Math.abs(currentX - startX);
      const height = Math.abs(currentY - startY);
      rect.style.display = "block";
      rect.style.left = `${left}px`;
      rect.style.top = `${top}px`;
      rect.style.width = `${width}px`;
      rect.style.height = `${height}px`;
    };

    const finish = (event) => {
      if (!dragging) {
        removeCropOverlay();
        return;
      }
      dragging = false;
      const endX = event.clientX;
      const endY = event.clientY;
      const x = Math.min(startX, endX);
      const y = Math.min(startY, endY);
      const width = Math.abs(endX - startX);
      const height = Math.abs(endY - startY);
      const pageX = x + window.scrollX;
      const pageY = y + window.scrollY;
      const element_selector = nearestElementSelector(x + width / 2, y + height / 2);
      removeCropOverlay();
      if (width < 5 || height < 5) {
        return;
      }
      emitCrop({ x, y, width, height, pageX, pageY, element_selector });
    };

    overlay.addEventListener("mousedown", (event) => {
      event.preventDefault();
      startX = event.clientX;
      startY = event.clientY;
      dragging = true;
      rect.style.display = "none";
    });
    overlay.addEventListener("mousemove", onMove);
    overlay.addEventListener("mouseup", finish);
    overlay.addEventListener("mouseleave", (event) => {
      if (dragging) {
        finish(event);
      }
    });

    cropOverlay = overlay;
    document.documentElement.appendChild(overlay);
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
      return;
    }
    if (type === "start_crop") {
      startCrop();
      return;
    }
    if (type === "mark_crop") {
      const payload = {
        x: Number(message?.x ?? 0),
        y: Number(message?.y ?? 0),
        width: Number(message?.width ?? 0),
        height: Number(message?.height ?? 0),
        pageX: Number(message?.pageX ?? message?.x ?? 0),
        pageY: Number(message?.pageY ?? message?.y ?? 0),
        element_selector: message?.element_selector || "",
      };
      if (JSON.stringify(payload) === lastCropSignature) {
        return;
      }
      if (!window.ph_mark_crop) {
        console.warn("Parish Trainer: ph_mark_crop binding is unavailable.");
        return;
      }
      window.ph_mark_crop(payload);
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
