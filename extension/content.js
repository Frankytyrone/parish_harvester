(() => {
  let cropOverlay = null;
  let lastCropSignature = "";
  let toolbar = null;

  // Build a stable key so the same crop payload isn't submitted twice.
  const cropSignature = (payload) =>
    `${payload.x},${payload.y},${payload.width},${payload.height},${payload.pageX},${payload.pageY},${payload.element_selector || ""}`;

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
    lastCropSignature = cropSignature(payload);
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

  const createToolbar = () => {
    const bar = document.createElement("div");
    bar.id = "ph-floating-toolbar";
    bar.style.cssText = [
      "position: fixed",
      "top: 10px",
      "left: 50%",
      "transform: translateX(-50%)",
      "z-index: 2147483646",
      "background: #111827",
      "color: #f9fafb",
      "font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif",
      "font-size: 12px",
      "border-radius: 8px",
      "box-shadow: 0 4px 16px rgba(0,0,0,0.55)",
      "display: flex",
      "flex-direction: column",
      "min-width: 0",
      "user-select: none",
      "pointer-events: auto",
    ].join(";");

    // Header / drag handle
    const header = document.createElement("div");
    header.style.cssText = [
      "display: flex",
      "align-items: center",
      "justify-content: space-between",
      "padding: 5px 8px",
      "background: #1f2937",
      "border-radius: 8px 8px 0 0",
      "cursor: grab",
      "gap: 8px",
    ].join(";");

    const title = document.createElement("span");
    title.textContent = "⠿ Parish Trainer";
    title.style.cssText = "font-weight:600;font-size:11px;opacity:0.9;white-space:nowrap;";
    header.appendChild(title);

    const closeBtn = document.createElement("button");
    closeBtn.textContent = "✕";
    closeBtn.title = "Hide toolbar";
    closeBtn.style.cssText = [
      "background: none",
      "border: none",
      "color: #9ca3af",
      "cursor: pointer",
      "font-size: 12px",
      "line-height: 1",
      "padding: 0 2px",
    ].join(";");
    closeBtn.addEventListener("click", () => {
      bar.dataset.phHidden = "true";
      bar.style.display = "none";
    });
    header.appendChild(closeBtn);
    bar.appendChild(header);

    // Buttons row
    const row = document.createElement("div");
    row.style.cssText = "display:flex;gap:6px;padding:8px;flex-wrap:wrap;";

    const makeBtn = (label, handler) => {
      const btn = document.createElement("button");
      btn.textContent = label;
      btn.style.cssText = [
        "border: none",
        "border-radius: 6px",
        "padding: 5px 8px",
        "background: #2563eb",
        "color: #fff",
        "cursor: pointer",
        "font-size: 11px",
        "white-space: nowrap",
      ].join(";");
      btn.addEventListener("click", handler);
      return btn;
    };

    row.appendChild(makeBtn("Mark Page as HTML", () => {
      if (window.ph_mark_html) {
        window.ph_mark_html({ url: window.location.href });
      } else {
        console.warn("Parish Trainer: ph_mark_html binding is unavailable.");
      }
    }));

    row.appendChild(makeBtn("Mark Current URL as File", () => {
      if (window.ph_mark_download_url) {
        window.ph_mark_download_url({ url: window.location.href });
      } else {
        console.warn("Parish Trainer: ph_mark_download_url binding is unavailable.");
      }
    }));

    row.appendChild(makeBtn("Crop Bulletin Image", () => {
      bar.dataset.phHidden = "true";
      bar.style.display = "none";
      startCrop();
    }));

    bar.appendChild(row);

    // Drag behaviour
    let isDragging = false;
    let dragOffsetX = 0;
    let dragOffsetY = 0;

    header.addEventListener("mousedown", (event) => {
      if (event.button !== 0) return;
      isDragging = true;
      // Switch from centered transform to explicit left/top
      const rect = bar.getBoundingClientRect();
      bar.style.transform = "none";
      bar.style.left = `${rect.left}px`;
      bar.style.top = `${rect.top}px`;
      dragOffsetX = event.clientX - rect.left;
      dragOffsetY = event.clientY - rect.top;
      header.style.cursor = "grabbing";
      event.preventDefault();
    });

    document.addEventListener("mousemove", (event) => {
      if (!isDragging) return;
      // If the button was released outside the browser window, cancel drag.
      if (!event.buttons) {
        isDragging = false;
        header.style.cursor = "grab";
        return;
      }
      bar.style.left = `${event.clientX - dragOffsetX}px`;
      bar.style.top = `${event.clientY - dragOffsetY}px`;
    });

    document.addEventListener("mouseup", () => {
      if (!isDragging) return;
      isDragging = false;
      header.style.cursor = "grab";
    });

    return bar;
  };

  chrome.runtime.onMessage.addListener((message) => {
    if (message?.type === "toggle_toolbar") {
      if (!toolbar) {
        toolbar = createToolbar();
        document.documentElement.appendChild(toolbar);
      } else if (toolbar.dataset.phHidden === "true") {
        toolbar.dataset.phHidden = "false";
        toolbar.style.display = "flex";
      } else {
        toolbar.dataset.phHidden = "true";
        toolbar.style.display = "none";
      }
      return;
    }

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
      const payload = message?.x != null ? message : null;
      if (!payload) {
        return;
      }
      if (cropSignature(payload) === lastCropSignature) {
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
