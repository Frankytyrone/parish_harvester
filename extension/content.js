(() => {
  let cropOverlay = null;
  let lastCropSignature = "";

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

  let cropSectionIndicator = null;

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

  const removeSectionIndicator = () => {
    if (cropSectionIndicator && cropSectionIndicator.parentNode) {
      cropSectionIndicator.parentNode.removeChild(cropSectionIndicator);
    }
    cropSectionIndicator = null;
  };

  const showSectionIndicator = (count) => {
    removeSectionIndicator();
    cropSectionIndicator = document.createElement("div");
    Object.assign(cropSectionIndicator.style, {
      position: "fixed",
      top: "12px",
      right: "12px",
      zIndex: "2147483646",
      background: "rgba(37,99,235,0.92)",
      color: "#fff",
      borderRadius: "8px",
      padding: "10px 16px",
      fontSize: "14px",
      fontFamily: "system-ui, -apple-system, sans-serif",
      boxShadow: "0 2px 8px rgba(0,0,0,0.4)",
      userSelect: "none",
      lineHeight: "1.4",
    });
    cropSectionIndicator.textContent =
      `${count} section${count !== 1 ? "s" : ""} saved — draw the next section`;
    document.documentElement.appendChild(cropSectionIndicator);
  };

  const startCrop = () => {
    removeCropOverlay();

    // Sections saved by "Add More" — shared across repeated drawing sessions.
    const sections = [];

    const HANDLE_SIZE = 12;
    const MIN_CROP_SIZE = 5;

    const beginDrawing = () => {
      const overlay = document.createElement("div");
      Object.assign(overlay.style, {
        position: "fixed",
        top: "0",
        left: "0",
        width: "100%",
        height: "100%",
        zIndex: "2147483647",
        cursor: "crosshair",
        background: "rgba(37,99,235,0.02)",
        userSelect: "none",
      });

      const rect = document.createElement("div");
      Object.assign(rect.style, {
        position: "fixed",
        border: "2px dashed #3b82f6",
        background: "rgba(59,130,246,0.15)",
        pointerEvents: "none",
        display: "none",
        boxSizing: "border-box",
      });
      overlay.appendChild(rect);

      let startX = 0;
      let startY = 0;
      let dragging = false;
      let editMode = false;
      let cropBox = { left: 0, top: 0, width: 0, height: 0 };
      const handles = [];
      let optionsBar = null;

      // ------------------------------------------------------------------
      // Rect / handle sync helpers
      // ------------------------------------------------------------------
      const syncRect = () => {
        const { left, top, width, height } = cropBox;
        rect.style.display = "block";
        rect.style.left = `${left}px`;
        rect.style.top = `${top}px`;
        rect.style.width = `${width}px`;
        rect.style.height = `${height}px`;
      };

      const handlePositions = [
        { xFrac: 0,   yFrac: 0   },
        { xFrac: 0.5, yFrac: 0   },
        { xFrac: 1,   yFrac: 0   },
        { xFrac: 1,   yFrac: 0.5 },
        { xFrac: 1,   yFrac: 1   },
        { xFrac: 0.5, yFrac: 1   },
        { xFrac: 0,   yFrac: 1   },
        { xFrac: 0,   yFrac: 0.5 },
      ];

      const syncHandles = () => {
        const { left, top, width, height } = cropBox;
        handles.forEach((h, i) => {
          const p = handlePositions[i];
          h.el.style.left = `${left + p.xFrac * width - HANDLE_SIZE / 2}px`;
          h.el.style.top  = `${top  + p.yFrac * height - HANDLE_SIZE / 2}px`;
        });
      };

      const syncOptionsBar = () => {
        if (!optionsBar) return;
        const { left, top, width, height } = cropBox;
        const barH = 52;
        const barW = optionsBar.offsetWidth || 300;
        const viewH = window.innerHeight;
        const viewW = window.innerWidth;
        const barTop = (top + height + barH + 8 <= viewH)
          ? top + height + 6
          : top - barH - 6;
        const barLeft = Math.min(Math.max(left + width / 2 - barW / 2, 6), viewW - barW - 6);
        optionsBar.style.left = `${barLeft}px`;
        optionsBar.style.top  = `${Math.max(4, barTop)}px`;
      };

      // ------------------------------------------------------------------
      // Build a single resize handle
      // ------------------------------------------------------------------
      const makeCursor = (xDir, yDir) => {
        if (xDir === 0)  return yDir < 0 ? "n-resize"  : "s-resize";
        if (yDir === 0)  return xDir < 0 ? "w-resize"  : "e-resize";
        if (xDir < 0)    return yDir < 0 ? "nw-resize" : "sw-resize";
        return yDir < 0 ? "ne-resize" : "se-resize";
      };

      const createHandle = (xDir, yDir) => {
        const el = document.createElement("div");
        Object.assign(el.style, {
          position: "fixed",
          width: `${HANDLE_SIZE}px`,
          height: `${HANDLE_SIZE}px`,
          background: "#fff",
          border: "2px solid #3b82f6",
          borderRadius: "2px",
          cursor: makeCursor(xDir, yDir),
          zIndex: "2147483647",
          boxSizing: "border-box",
        });

        el.addEventListener("mousedown", (e) => {
          e.stopPropagation();
          e.preventDefault();
          const startRX = e.clientX;
          const startRY = e.clientY;
          const snapBox = { ...cropBox };

          const onMM = (me) => {
            const dx = me.clientX - startRX;
            const dy = me.clientY - startRY;
            let { left, top, width, height } = snapBox;
            if (xDir === -1) { left = snapBox.left + dx; width = snapBox.width - dx; }
            else if (xDir === 1) { width = snapBox.width + dx; }
            if (yDir === -1) { top = snapBox.top + dy; height = snapBox.height - dy; }
            else if (yDir === 1) { height = snapBox.height + dy; }
            if (width < MIN_CROP_SIZE)  { width = MIN_CROP_SIZE;  if (xDir === -1) left = snapBox.left + snapBox.width - MIN_CROP_SIZE; }
            if (height < MIN_CROP_SIZE) { height = MIN_CROP_SIZE; if (yDir === -1) top  = snapBox.top  + snapBox.height - MIN_CROP_SIZE; }
            cropBox = { left, top, width, height };
            syncRect();
            syncHandles();
            syncOptionsBar();
          };

          const onMU = () => {
            document.removeEventListener("mousemove", onMM);
            document.removeEventListener("mouseup", onMU);
          };
          document.addEventListener("mousemove", onMM);
          document.addEventListener("mouseup", onMU);
        });
        return el;
      };

      // ------------------------------------------------------------------
      // Enter edit mode (handles + options bar) after drawing
      // ------------------------------------------------------------------
      const showEditMode = () => {
        editMode = true;
        overlay.style.cursor = "default";
        overlay.style.background = "transparent";

        const handleDirs = [
          [-1, -1], [0, -1], [1, -1],
          [ 1,  0],
          [ 1,  1], [0,  1], [-1,  1],
          [-1,  0],
        ];
        handleDirs.forEach(([xDir, yDir]) => {
          const el = createHandle(xDir, yDir);
          overlay.appendChild(el);
          handles.push({ el, xDir, yDir });
        });
        syncHandles();

        // Options bar
        optionsBar = document.createElement("div");
        Object.assign(optionsBar.style, {
          position: "fixed",
          zIndex: "2147483647",
          background: "#1e293b",
          border: "1px solid #3b82f6",
          borderRadius: "8px",
          padding: "6px 10px",
          display: "flex",
          gap: "8px",
          alignItems: "center",
          boxShadow: "0 4px 16px rgba(0,0,0,0.55)",
          fontFamily: "system-ui, -apple-system, sans-serif",
        });

        const makeBtn = (label, bg, onClick) => {
          const btn = document.createElement("button");
          btn.textContent = label;
          Object.assign(btn.style, {
            border: "none",
            borderRadius: "6px",
            padding: "9px 18px",
            background: bg,
            color: "#fff",
            cursor: "pointer",
            fontSize: "14px",
            fontWeight: "600",
            fontFamily: "inherit",
            whiteSpace: "nowrap",
          });
          btn.addEventListener("mousedown", (e) => e.stopPropagation());
          btn.addEventListener("click", (e) => { e.stopPropagation(); onClick(); });
          return btn;
        };

        const confirmBtn = makeBtn("Confirm", "#16a34a", () => {
          const { left, top, width, height } = cropBox;
          if (width < MIN_CROP_SIZE || height < MIN_CROP_SIZE) return;
          const pageX = left + window.scrollX;
          const pageY = top  + window.scrollY;
          const element_selector = nearestElementSelector(left + width / 2, top + height / 2);
          const lastSection = { x: left, y: top, width, height, pageX, pageY, element_selector };
          removeSectionIndicator();
          removeCropOverlay();
          const allSections = [...sections, lastSection];
          if (allSections.length > 1) {
            emitCrop({ ...lastSection, sections: allSections });
          } else {
            emitCrop(lastSection);
          }
        });

        const addMoreBtn = makeBtn("Add More", "#2563eb", () => {
          const { left, top, width, height } = cropBox;
          if (width < MIN_CROP_SIZE || height < MIN_CROP_SIZE) return;
          const pageX = left + window.scrollX;
          const pageY = top  + window.scrollY;
          const element_selector = nearestElementSelector(left + width / 2, top + height / 2);
          sections.push({ x: left, y: top, width, height, pageX, pageY, element_selector });
          removeCropOverlay();
          showSectionIndicator(sections.length);
          // Start a fresh drawing session that shares the same sections array.
          beginDrawing();
        });

        const cancelBtn = makeBtn("Cancel", "#dc2626", () => {
          removeSectionIndicator();
          removeCropOverlay();
        });

        optionsBar.appendChild(confirmBtn);
        optionsBar.appendChild(addMoreBtn);
        optionsBar.appendChild(cancelBtn);
        overlay.appendChild(optionsBar);

        // Defer measurement until after DOM paint so offsetWidth is correct.
        requestAnimationFrame(syncOptionsBar);
      };

      // ------------------------------------------------------------------
      // Drawing-mode mouse handlers
      // ------------------------------------------------------------------
      const onMove = (event) => {
        if (!dragging || editMode) return;
        const currentX = event.clientX;
        const currentY = event.clientY;
        cropBox = {
          left:   Math.min(startX, currentX),
          top:    Math.min(startY, currentY),
          width:  Math.abs(currentX - startX),
          height: Math.abs(currentY - startY),
        };
        syncRect();
      };

      const finish = (event) => {
        if (!dragging) return;
        dragging = false;
        const endX = event.clientX;
        const endY = event.clientY;
        cropBox = {
          left:   Math.min(startX, endX),
          top:    Math.min(startY, endY),
          width:  Math.abs(endX - startX),
          height: Math.abs(endY - startY),
        };
        if (cropBox.width < MIN_CROP_SIZE || cropBox.height < MIN_CROP_SIZE) {
          // Tiny drag — cancel only if no sections saved yet.
          if (sections.length === 0) {
            removeCropOverlay();
          }
          return;
        }
        syncRect();
        showEditMode();
      };

      overlay.addEventListener("mousedown", (event) => {
        if (editMode) return;
        event.preventDefault();
        startX = event.clientX;
        startY = event.clientY;
        dragging = true;
        rect.style.display = "none";
      });
      overlay.addEventListener("mousemove", onMove);
      overlay.addEventListener("mouseup", finish);
      overlay.addEventListener("mouseleave", (event) => {
        if (dragging && !editMode) finish(event);
      });

      cropOverlay = overlay;
      document.documentElement.appendChild(overlay);
    }; // end beginDrawing

    beginDrawing();
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
