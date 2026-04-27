(() => {
  // ── Session state ────────────────────────────────────────────────────────
  let cropOverlay = null;
  let lastCropSignature = "";
  let toolbar = null;
  let sessionSteps = []; // {type, label} tracked in the training UI
  let pickLinkActive = false;
  let pickLinkHighlightEl = null;
  let pickLinkCancelListeners = [];
  let _stepsListEl = null; // set by createToolbar
  let _refreshRecipeCount = null; // callback set by createToolbar

  // ── Helpers ───────────────────────────────────────────────────────────────

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
        const siblings = Array.from(parent.children).filter(
          (c) => c.tagName === current.tagName
        );
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
      if (!(el instanceof Element)) continue;
      const img = el.closest("img");
      if (img) return cssPath(img);
      const container = el.closest("figure,article,section,main,div");
      if (container) return cssPath(container);
      return cssPath(el);
    }
    return "";
  };

  // Build a stable Playwright-friendly selector for a link/button element.
  const buildStableLinkSelector = (el) => {
    if (!el) return "";
    const tag = el.tagName.toLowerCase();
    const text = (el.innerText || el.textContent || "")
      .trim()
      .replace(/\s+/g, " ")
      .slice(0, 80);
    const role = el.getAttribute("role") || "";
    if (text && text.length >= 3 && text.length <= 60) {
      return `${tag}:has-text("${text.replace(/"/g, '\\"')}")`;
    }
    if (role) {
      return `[role="${role}"]:has-text("${text.replace(/"/g, '\\"')}")`;
    }
    return cssPath(el);
  };

  // Returns true if the URL looks like a downloadable document.
  const isDocumentUrl = (url) => {
    if (!url) return false;
    const lower = url.toLowerCase().split("?")[0];
    const docExts = [".pdf", ".docx", ".doc", ".pptx", ".ppt", ".odt", ".ods"];
    if (docExts.some((ext) => lower.endsWith(ext))) return true;
    if (
      lower.includes("drive.google.com/file") ||
      lower.includes("docs.google.com/viewer") ||
      lower.includes("drive.google.com/uc?") ||
      lower.includes("drive.google.com/open?")
    )
      return true;
    return false;
  };

  // Detect what kind of bulletin page we are on and give plain-language guidance.
  const detectPageType = () => {
    const url = window.location.href.toLowerCase();
    if (url.endsWith(".pdf") || url.includes(".pdf?") || url.includes("/pdf/")) {
      return {
        emoji: "📄",
        summary: "This page IS a PDF document.",
        advice: "Click \"Yes, it's a PDF\" to record this URL as the bulletin file.",
      };
    }
    const iframes = Array.from(document.querySelectorAll("iframe[src]"));
    const pdfIframes = iframes.filter((f) => {
      const src = (f.getAttribute("src") || "").toLowerCase();
      return (
        src.endsWith(".pdf") ||
        src.includes(".pdf?") ||
        src.includes("docs.google.com/viewer") ||
        src.includes("drive.google.com/file")
      );
    });
    if (pdfIframes.length > 0) {
      return {
        emoji: "🖼️",
        summary: `This page embeds ${pdfIframes.length} PDF frame(s).`,
        advice: "Click \"It's embedded in a frame\" to choose the correct frame.",
      };
    }
    const pdfLinks = document.querySelectorAll('a[href*=".pdf"]');
    if (pdfLinks.length > 0) {
      return {
        emoji: "🔗",
        summary: `Found ${pdfLinks.length} PDF link(s) on this page.`,
        advice: "Click \"No, I need to click a link\" to select the correct one.",
      };
    }
    const images = document.querySelectorAll("img");
    const bulletinImages = Array.from(images).filter((img) => {
      const src = (
        (img.getAttribute("src") || "") +
        " " +
        (img.getAttribute("alt") || "")
      ).toLowerCase();
      return (
        src.includes("bulletin") ||
        src.includes("newsletter") ||
        src.includes("notice")
      );
    });
    if (bulletinImages.length > 0) {
      return {
        emoji: "🖼️",
        summary: `Found ${bulletinImages.length} possible image bulletin(s).`,
        advice: "Click \"Yes, it's an image\" to crop or mark the image bulletin.",
      };
    }
    const allLinks = document.querySelectorAll("a[href],button");
    if (allLinks.length > 0) {
      return {
        emoji: "📋",
        summary: "HTML listing page — no direct PDF detected.",
        advice: "Click \"No, I need to click a link\" to point to the bulletin link.",
      };
    }
    return {
      emoji: "❓",
      summary: "Page type not automatically detected.",
      advice: "Try navigating to the bulletin page first, then use Guided Mode.",
    };
  };

  // ── Session step tracking ─────────────────────────────────────────────────

  const addSessionStep = (type, label) => {
    sessionSteps.push({ type, label });
    if (_stepsListEl) _renderSessionSteps();
    if (_refreshRecipeCount) _refreshRecipeCount();
  };

  const undoSessionStep = () => {
    if (sessionSteps.length === 0) return null;
    const removed = sessionSteps.pop();
    if (_stepsListEl) _renderSessionSteps();
    if (_refreshRecipeCount) _refreshRecipeCount();
    if (typeof window.ph_undo_step === "function") {
      try {
        window.ph_undo_step({ step_type: removed.type });
      } catch (_e) {
        // ph_undo_step may not be available in all training sessions
      }
    }
    return removed;
  };

  const _renderSessionSteps = () => {
    if (!_stepsListEl) return;
    _stepsListEl.innerHTML = "";
    if (sessionSteps.length === 0) {
      const empty = document.createElement("div");
      empty.style.cssText = "opacity:0.55;font-size:10px;padding:2px 0;";
      empty.textContent = "No steps recorded yet.";
      _stepsListEl.appendChild(empty);
      return;
    }
    sessionSteps.forEach((step, i) => {
      const item = document.createElement("div");
      item.style.cssText = [
        "display:flex",
        "align-items:flex-start",
        "gap:4px",
        "padding:3px 0",
        "border-bottom:1px solid #374151",
        "font-size:10px",
      ].join(";");
      const num = document.createElement("span");
      num.style.cssText = "color:#6b7280;min-width:14px;flex-shrink:0;";
      num.textContent = `${i + 1}.`;
      const txt = document.createElement("span");
      txt.style.cssText = "flex:1;word-break:break-all;line-height:1.35;";
      txt.textContent = step.label;
      item.appendChild(num);
      item.appendChild(txt);
      _stepsListEl.appendChild(item);
    });
  };

  // ── Pick Link Mode ────────────────────────────────────────────────────────

  const stopPickLinkMode = () => {
    if (!pickLinkActive) return;
    pickLinkActive = false;
    if (pickLinkHighlightEl && pickLinkHighlightEl.parentNode) {
      pickLinkHighlightEl.parentNode.removeChild(pickLinkHighlightEl);
    }
    pickLinkHighlightEl = null;
    pickLinkCancelListeners.forEach(({ el, type, fn }) =>
      el.removeEventListener(type, fn, true)
    );
    pickLinkCancelListeners = [];
    document.body.style.cursor = "";
  };

  const startPickLinkMode = (onPick, showStatus) => {
    if (pickLinkActive) stopPickLinkMode();
    pickLinkActive = true;
    document.body.style.cursor = "crosshair";
    if (showStatus) {
      showStatus(
        "🎯 Hover over a link and click to select it. Press Escape to cancel.",
        "info"
      );
    }

    const highlight = document.createElement("div");
    Object.assign(highlight.style, {
      position: "fixed",
      pointerEvents: "none",
      border: "2px solid #f59e0b",
      background: "rgba(245,158,11,0.12)",
      borderRadius: "4px",
      zIndex: "2147483645",
      display: "none",
      boxSizing: "border-box",
    });
    document.documentElement.appendChild(highlight);
    pickLinkHighlightEl = highlight;

    const CANDIDATE_SELECTOR = 'a[href],button,[role="button"],[role="link"]';

    const onMouseMove = (e) => {
      if (!pickLinkActive) return;
      const el = document.elementFromPoint(e.clientX, e.clientY);
      if (el && el.closest("#ph-floating-toolbar")) {
        highlight.style.display = "none";
        return;
      }
      const candidate = el ? el.closest(CANDIDATE_SELECTOR) : null;
      if (candidate) {
        const r = candidate.getBoundingClientRect();
        Object.assign(highlight.style, {
          display: "block",
          left: `${r.left - 2}px`,
          top: `${r.top - 2}px`,
          width: `${r.width + 4}px`,
          height: `${r.height + 4}px`,
        });
      } else {
        highlight.style.display = "none";
      }
    };

    const onClick = (e) => {
      if (!pickLinkActive) return;
      if (
        e.target instanceof Element &&
        e.target.closest("#ph-floating-toolbar")
      )
        return;
      const el =
        e.target instanceof Element ? e.target.closest(CANDIDATE_SELECTOR) : null;
      if (!el) return;
      e.preventDefault();
      e.stopImmediatePropagation();
      stopPickLinkMode();
      onPick(el);
    };

    const onKeyDown = (e) => {
      if (e.key === "Escape") {
        stopPickLinkMode();
        if (showStatus) showStatus("❌ Link selection cancelled.", "error");
      }
    };

    document.addEventListener("mousemove", onMouseMove, true);
    document.addEventListener("click", onClick, true);
    document.addEventListener("keydown", onKeyDown, true);
    pickLinkCancelListeners = [
      { el: document, type: "mousemove", fn: onMouseMove },
      { el: document, type: "click", fn: onClick },
      { el: document, type: "keydown", fn: onKeyDown },
    ];
  };

  // ── Safety-checked mark download URL ─────────────────────────────────────

  const markDownloadUrlSafe = (url, showStatus, forceConfirm) => {
    if (!url) {
      if (showStatus) showStatus("❌ No URL to mark.", "error");
      return;
    }
    if (!isDocumentUrl(url) && !forceConfirm) {
      const preview = url.length > 60 ? url.slice(0, 57) + "…" : url;
      if (showStatus) {
        showStatus(
          `⚠️ "${preview}" doesn't look like a PDF/document. See "Mark Anyway" button below.`,
          "warn"
        );
      }
      window.dispatchEvent(
        new CustomEvent("ph-confirm-mark-download", { detail: { url } })
      );
      return;
    }
    if (window.ph_mark_download_url) {
      try {
        window.ph_mark_download_url({ url });
        addSessionStep("mark_file", `📄 File: ${url.slice(-50)}`);
        if (showStatus) showStatus("✅ Bulletin file URL recorded.");
      } catch (_e) {
        if (showStatus)
          showStatus(
            "❌ Could not communicate with page. Try refreshing.",
            "error"
          );
      }
    } else {
      console.warn("Parish Trainer: ph_mark_download_url binding is unavailable.");
      if (showStatus)
        showStatus("❌ Training binding unavailable. Try refreshing.", "error");
    }
  };

  // ── Iframe picker panel ───────────────────────────────────────────────────

  const buildIframePickerPanel = (showStatus) => {
    const iframes = Array.from(document.querySelectorAll("iframe[src]"));
    if (iframes.length === 0) {
      if (showStatus) showStatus("ℹ️ No iframes found on this page.", "info");
      return null;
    }

    const panel = document.createElement("div");
    panel.style.cssText = [
      "background:#0f172a",
      "border-radius:4px",
      "padding:6px",
      "font-size:10px",
    ].join(";");

    const heading = document.createElement("div");
    heading.style.cssText = "font-weight:600;margin-bottom:6px;color:#93c5fd;";
    heading.textContent = `Found ${iframes.length} iframe(s) — click to select the bulletin:`;
    panel.appendChild(heading);

    iframes.forEach((frame, idx) => {
      const src = frame.getAttribute("src") || "";
      const lowerSrc = src.toLowerCase();
      let resolvedUrl = src;
      let isBulletin = false;

      // Unwrap Google Docs viewer URL
      if (
        lowerSrc.includes("docs.google.com/viewer") ||
        lowerSrc.includes("docs.google.com/gview")
      ) {
        try {
          const urlParam = new URL(src, window.location.href).searchParams.get("url");
          if (urlParam) {
            resolvedUrl = decodeURIComponent(urlParam);
            isBulletin = true;
          }
        } catch (_e) {
          // keep original src
        }
      } else if (
        lowerSrc.endsWith(".pdf") ||
        lowerSrc.includes(".pdf?") ||
        lowerSrc.includes("drive.google.com/file")
      ) {
        isBulletin = true;
      }

      let hostname = "";
      try {
        hostname = new URL(src, window.location.href).hostname;
      } catch (_e) {
        hostname = src.slice(0, 30);
      }
      const preview = src.length > 50 ? src.slice(0, 47) + "…" : src;

      const row = document.createElement("div");
      row.style.cssText = [
        "display:flex",
        "align-items:flex-start",
        "gap:5px",
        "padding:5px",
        "border-radius:4px",
        "cursor:pointer",
        "border:1px solid " + (isBulletin ? "#16a34a" : "#374151"),
        "background:" + (isBulletin ? "rgba(22,163,74,0.08)" : "transparent"),
        "margin-bottom:4px",
      ].join(";");

      const badge = document.createElement("span");
      badge.style.cssText =
        "background:#374151;border-radius:3px;padding:1px 4px;font-size:9px;white-space:nowrap;flex-shrink:0;";
      badge.textContent = `#${idx + 1}`;

      const info = document.createElement("div");
      info.style.cssText = "flex:1;word-break:break-all;line-height:1.3;";
      const mainText = document.createElement("div");
      mainText.textContent = `${isBulletin ? "✅ " : ""}${hostname} — ${preview}`;
      info.appendChild(mainText);
      if (!isBulletin) {
        const warn = document.createElement("div");
        warn.style.cssText = "color:#f59e0b;font-size:9px;margin-top:2px;";
        warn.textContent = "⚠️ Not clearly a document — confirm before using";
        info.appendChild(warn);
      }

      row.appendChild(badge);
      row.appendChild(info);

      row.addEventListener("mouseenter", () => {
        row.style.background = isBulletin
          ? "rgba(22,163,74,0.2)"
          : "rgba(255,255,255,0.05)";
      });
      row.addEventListener("mouseleave", () => {
        row.style.background = isBulletin ? "rgba(22,163,74,0.08)" : "transparent";
      });

      row.addEventListener("click", () => {
        markDownloadUrlSafe(resolvedUrl, showStatus, isBulletin);
        if (isDocumentUrl(resolvedUrl)) {
          if (panel.parentNode) panel.parentNode.removeChild(panel);
        }
      });

      panel.appendChild(row);
    });

    return panel;
  };

  // ── Crop overlay ──────────────────────────────────────────────────────────

  let cropSectionIndicator = null;

  const emitCrop = (payload) => {
    lastCropSignature = cropSignature(payload);
    if (window.ph_mark_crop) {
      window.ph_mark_crop(payload);
    } else {
      console.warn("Parish Trainer: ph_mark_crop binding is unavailable.");
    }
    addSessionStep("crop", "✂️ Crop recorded");
    window.postMessage(
      { direction: "from-main", message: { type: "crop_done", ...payload } },
      "*"
    );
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
    cropSectionIndicator.textContent = `${count} section${
      count !== 1 ? "s" : ""
    } saved — draw the next section`;
    document.documentElement.appendChild(cropSectionIndicator);
  };

  const startCrop = () => {
    removeCropOverlay();

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
        const barTop =
          top + height + barH + 8 <= viewH
            ? top + height + 6
            : top - barH - 6;
        const barLeft = Math.min(
          Math.max(left + width / 2 - barW / 2, 6),
          viewW - barW - 6
        );
        optionsBar.style.left = `${barLeft}px`;
        optionsBar.style.top  = `${Math.max(4, barTop)}px`;
      };

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
            if (width < MIN_CROP_SIZE)  {
              width = MIN_CROP_SIZE;
              if (xDir === -1) left = snapBox.left + snapBox.width - MIN_CROP_SIZE;
            }
            if (height < MIN_CROP_SIZE) {
              height = MIN_CROP_SIZE;
              if (yDir === -1) top  = snapBox.top  + snapBox.height - MIN_CROP_SIZE;
            }
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
        requestAnimationFrame(syncOptionsBar);
      };

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
          if (sections.length === 0) removeCropOverlay();
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
    };

    beginDrawing();
  };

  // ── createToolbar ─────────────────────────────────────────────────────────

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
      "min-width: 320px",
      "max-width: 420px",
      "user-select: none",
      "pointer-events: auto",
    ].join(";");

    // ── Header / drag handle ───────────────────────────────────────────────
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

    const guidedBadge = document.createElement("span");
    guidedBadge.textContent = "Guided ✓";
    guidedBadge.title = "Guided Mode ON — follow the steps below";
    guidedBadge.style.cssText = [
      "background:#16a34a",
      "color:#fff",
      "border-radius:4px",
      "padding:1px 5px",
      "font-size:9px",
      "font-weight:600",
      "white-space:nowrap",
    ].join(";");
    header.appendChild(guidedBadge);

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
      "margin-left: auto",
    ].join(";");
    closeBtn.addEventListener("click", () => {
      bar.dataset.phHidden = "true";
      bar.style.display = "none";
      stopPickLinkMode();
    });
    header.appendChild(closeBtn);
    bar.appendChild(header);

    // ── Status bar ─────────────────────────────────────────────────────────
    const statusBar = document.createElement("div");
    statusBar.style.cssText = [
      "display: none",
      "padding: 5px 10px",
      "font-size: 10px",
      "text-align: center",
      "line-height: 1.4",
      "word-break: break-word",
      "border-radius: 0 0 8px 8px",
      "transition: opacity 0.3s",
    ].join(";");

    let statusTimer = null;
    const showStatus = (message, type) => {
      clearTimeout(statusTimer);
      // Remove any existing "Mark Anyway" buttons
      const old = statusBar.querySelector(".ph-mark-anyway");
      if (old) statusBar.removeChild(old);
      statusBar.textContent = message;
      statusBar.style.display = "block";
      statusBar.style.opacity = "1";
      if (type === "error") {
        statusBar.style.background = "#7f1d1d";
        statusBar.style.color = "#fca5a5";
      } else if (type === "warn") {
        statusBar.style.background = "#78350f";
        statusBar.style.color = "#fde68a";
      } else if (type === "info") {
        statusBar.style.background = "#1e3a5f";
        statusBar.style.color = "#93c5fd";
      } else {
        statusBar.style.background = "#14532d";
        statusBar.style.color = "#86efac";
      }
      statusTimer = setTimeout(() => {
        statusBar.style.opacity = "0";
        setTimeout(() => { statusBar.style.display = "none"; }, 300);
      }, 6000);
    };

    // ── Body container ─────────────────────────────────────────────────────
    const body = document.createElement("div");
    body.style.cssText = "padding:8px;display:flex;flex-direction:column;gap:6px;";

    // Helper: small styled button
    const makeSmallBtn = (label, bg, onClick, tooltip) => {
      const btn = document.createElement("button");
      btn.textContent = label;
      if (tooltip) btn.title = tooltip;
      btn.style.cssText = [
        "border: none",
        "border-radius: 6px",
        "padding: 6px 10px",
        "background: " + (bg || "#2563eb"),
        "color: #fff",
        "cursor: pointer",
        "font-size: 11px",
        "text-align: left",
        "white-space: normal",
        "font-family: inherit",
        "line-height: 1.3",
        "width: 100%",
      ].join(";");
      btn.addEventListener("mouseenter", () => { btn.style.filter = "brightness(1.15)"; });
      btn.addEventListener("mouseleave", () => { btn.style.filter = ""; });
      btn.addEventListener("click", onClick);
      return btn;
    };

    // ── GUIDED MODE WIZARD ─────────────────────────────────────────────────
    const guidedPanel = document.createElement("div");
    guidedPanel.style.cssText = [
      "background:#1e293b",
      "border:1px solid #2563eb",
      "border-radius:6px",
      "padding:8px",
    ].join(";");

    const wizardQ = document.createElement("div");
    wizardQ.style.cssText = "font-size:11px;font-weight:600;margin-bottom:6px;color:#93c5fd;";
    wizardQ.textContent = "Step 1: Do you see the bulletin on screen?";

    const wizardBtns = document.createElement("div");
    wizardBtns.style.cssText = "display:flex;flex-direction:column;gap:5px;";

    const stuckLink = document.createElement("div");
    stuckLink.style.cssText =
      "font-size:9px;color:#6b7280;margin-top:4px;cursor:pointer;text-decoration:underline;display:inline-block;";
    stuckLink.textContent = "I'm stuck — show all options";
    stuckLink.title = "Open the advanced section with all manual controls";
    stuckLink.addEventListener("click", () => {
      advancedSection.style.display =
        advancedSection.style.display === "none" ? "block" : "none";
    });

    const resetGuidedPanel = () => {
      guidedPanel.innerHTML = "";
      guidedPanel.appendChild(wizardQ);
      guidedPanel.appendChild(wizardBtns);
      guidedPanel.appendChild(stuckLink);
    };

    // Show a confirmation step after a link is picked
    const showPickConfirmation = (selectedEl) => {
      const selector = buildStableLinkSelector(selectedEl);
      const href = selectedEl.getAttribute("href") || "";
      const text = (selectedEl.innerText || selectedEl.textContent || "")
        .trim()
        .slice(0, 60);

      guidedPanel.innerHTML = "";

      const confirmQ = document.createElement("div");
      confirmQ.style.cssText = "font-weight:600;color:#93c5fd;margin-bottom:6px;font-size:11px;";
      confirmQ.textContent = "Is this the right link?";
      guidedPanel.appendChild(confirmQ);

      const preview = document.createElement("div");
      preview.style.cssText = [
        "background:#0f172a",
        "border-radius:4px",
        "padding:5px",
        "margin-bottom:6px",
        "word-break:break-all",
        "line-height:1.4",
        "font-size:10px",
      ].join(";");
      preview.innerHTML =
        `<strong>Text:</strong> ${text || "(no text)"}<br>` +
        `<strong>Href:</strong> ${(href || "(none)").slice(0, 70)}<br>` +
        `<strong>Selector:</strong> <code style="font-size:9px;">${selector}</code>`;
      guidedPanel.appendChild(preview);

      const btnRow = document.createElement("div");
      btnRow.style.cssText = "display:flex;gap:5px;";

      const looksRightBtn = makeSmallBtn(
        "👍 Looks right",
        "#16a34a",
        () => {
          if (window.ph_record_click) {
            try {
              window.ph_record_click({
                tag: (selectedEl.tagName || "").toLowerCase(),
                role: (selectedEl.getAttribute("role") || "").toLowerCase(),
                text: (selectedEl.innerText || selectedEl.textContent || "")
                  .trim()
                  .slice(0, 200),
                href: selectedEl.getAttribute("href") || "",
                css_path: cssPath(selectedEl),
              });
              addSessionStep("click", `🔗 Click: "${text || selector}"`);
              showStatus(`✅ Click step recorded: "${text || selector}"`);
            } catch (_e) {
              showStatus("❌ Could not record click.", "error");
            }
          }
          resetGuidedPanel();
        },
        "Record this click as a training step"
      );

      const pickAgainBtn = makeSmallBtn(
        "🔄 Pick again",
        "#374151",
        () => {
          resetGuidedPanel();
          startPickLinkMode(showPickConfirmation, showStatus);
        },
        "Select a different link"
      );
      pickAgainBtn.style.width = "auto";

      btnRow.appendChild(looksRightBtn);
      btnRow.appendChild(pickAgainBtn);
      guidedPanel.appendChild(btnRow);

      // Briefly highlight the chosen element on the page
      if (selectedEl instanceof Element) {
        const prevOutline = selectedEl.style.outline;
        selectedEl.style.outline = "3px solid #f59e0b";
        selectedEl.scrollIntoView({ behavior: "smooth", block: "nearest" });
        setTimeout(() => {
          if (selectedEl.style.outline === "3px solid #f59e0b") {
            selectedEl.style.outline = prevOutline;
          }
        }, 3000);
      }
    };

    // Wizard buttons (Guided Mode ON by default)
    wizardBtns.appendChild(
      makeSmallBtn(
        "✅ Yes, it's a PDF — mark this URL",
        "#16a34a",
        () => markDownloadUrlSafe(window.location.href, showStatus, false),
        "The browser is showing a PDF — record this URL as the bulletin file"
      )
    );
    wizardBtns.appendChild(
      makeSmallBtn(
        "🖼️ Yes, it's an image — crop it",
        "#2563eb",
        () => {
          bar.dataset.phHidden = "true";
          bar.style.display = "none";
          startCrop();
        },
        "The bulletin is shown as an image — draw a crop rectangle"
      )
    );
    wizardBtns.appendChild(
      makeSmallBtn(
        "📄 No — I need to click a link first",
        "#2563eb",
        () => startPickLinkMode(showPickConfirmation, showStatus),
        "Hover over links and click one to record a navigation step"
      )
    );
    wizardBtns.appendChild(
      makeSmallBtn(
        "📐 It's embedded in a frame / viewer",
        "#2563eb",
        () => {
          const pickerPanel = buildIframePickerPanel(showStatus);
          if (pickerPanel) {
            guidedPanel.innerHTML = "";
            const backBtn = makeSmallBtn("← Back", "#374151", resetGuidedPanel);
            backBtn.style.width = "auto";
            backBtn.style.marginBottom = "6px";
            guidedPanel.appendChild(backBtn);
            guidedPanel.appendChild(pickerPanel);
          }
        },
        "The bulletin is inside an iframe or Google Docs viewer — pick the frame"
      )
    );

    guidedPanel.appendChild(wizardQ);
    guidedPanel.appendChild(wizardBtns);
    guidedPanel.appendChild(stuckLink);
    body.appendChild(guidedPanel);

    // Listen for messages from the side-panel / isolated world that request
    // pick modes — they need to run inside the createToolbar closure.
    window.addEventListener("ph-start-pick-link", () => {
      startPickLinkMode(showPickConfirmation, showStatus);
    });
    window.addEventListener("ph-start-pick-iframe", () => {
      const pickerPanel = buildIframePickerPanel(showStatus);
      if (pickerPanel) {
        guidedPanel.innerHTML = "";
        const backBtn = makeSmallBtn("← Back", "#374151", resetGuidedPanel);
        backBtn.style.width = "auto";
        backBtn.style.marginBottom = "6px";
        guidedPanel.appendChild(backBtn);
        guidedPanel.appendChild(pickerPanel);
      }
    });

    // ── IDENTIFY PAGE ──────────────────────────────────────────────────────
    const identifyBtn = document.createElement("button");
    identifyBtn.textContent = "🔍 Help me identify this page";
    identifyBtn.title = "Run automatic detection to see what kind of bulletin page you are on";
    identifyBtn.style.cssText = [
      "border: none",
      "border-radius: 6px",
      "padding: 5px 8px",
      "background: #374151",
      "color: #d1d5db",
      "cursor: pointer",
      "font-size: 10px",
      "white-space: nowrap",
      "font-family: inherit",
      "width: 100%",
      "text-align: left",
    ].join(";");

    const identifyResult = document.createElement("div");
    identifyResult.style.cssText = [
      "display:none",
      "background:#0f172a",
      "border:1px solid #374151",
      "border-radius:6px",
      "padding:6px 8px",
      "font-size:10px",
      "line-height:1.45",
    ].join(";");

    identifyBtn.addEventListener("click", () => {
      const result = detectPageType();
      identifyResult.style.display = "block";
      identifyResult.innerHTML =
        `<span style="font-size:15px;">${result.emoji}</span> ` +
        `<strong style="color:#f9fafb;">${result.summary}</strong><br>` +
        `<span style="color:#9ca3af;">${result.advice}</span>`;
    });

    body.appendChild(identifyBtn);
    body.appendChild(identifyResult);

    // ── RECIPE PREVIEW ─────────────────────────────────────────────────────
    const recipeSection = document.createElement("div");
    recipeSection.style.cssText = [
      "background:#1e293b",
      "border:1px solid #374151",
      "border-radius:6px",
      "overflow:hidden",
    ].join(";");

    const recipeHeaderEl = document.createElement("div");
    recipeHeaderEl.style.cssText = [
      "display:flex",
      "align-items:center",
      "justify-content:space-between",
      "padding:5px 8px",
      "cursor:pointer",
    ].join(";");

    const recipeTitleEl = document.createElement("span");
    recipeTitleEl.style.cssText = "font-size:10px;font-weight:600;";
    recipeTitleEl.textContent = "📋 Recipe Preview (0 steps)";

    const recipeToggleEl = document.createElement("span");
    recipeToggleEl.style.cssText = "font-size:10px;color:#6b7280;";
    recipeToggleEl.textContent = "▶";

    recipeHeaderEl.appendChild(recipeTitleEl);
    recipeHeaderEl.appendChild(recipeToggleEl);

    const recipeBodyEl = document.createElement("div");
    recipeBodyEl.style.cssText = "padding:6px 8px;display:none;";

    const stepsListEl = document.createElement("div");
    stepsListEl.style.cssText = "margin-bottom:6px;";
    // Wire up the module-level reference so addSessionStep can find it
    _stepsListEl = stepsListEl;
    _renderSessionSteps();

    const undoBtn = document.createElement("button");
    undoBtn.textContent = "↩ Undo Last Step";
    undoBtn.title = "Remove the last recorded step from this session";
    undoBtn.style.cssText = [
      "border: none",
      "border-radius: 5px",
      "padding: 4px 8px",
      "background: #78350f",
      "color: #fde68a",
      "cursor: pointer",
      "font-size: 10px",
      "font-family: inherit",
    ].join(";");
    undoBtn.addEventListener("click", () => {
      const removed = undoSessionStep();
      if (removed) {
        showStatus(`↩ Undone: ${removed.label}`);
      } else {
        showStatus("ℹ️ Nothing to undo.", "info");
      }
    });

    recipeBodyEl.appendChild(stepsListEl);
    recipeBodyEl.appendChild(undoBtn);
    recipeSection.appendChild(recipeHeaderEl);
    recipeSection.appendChild(recipeBodyEl);

    // Wire up the recipe count refresh callback
    _refreshRecipeCount = () => {
      recipeTitleEl.textContent = `📋 Recipe Preview (${sessionSteps.length} step${
        sessionSteps.length !== 1 ? "s" : ""
      })`;
    };

    let recipeOpen = false;
    recipeHeaderEl.addEventListener("click", () => {
      recipeOpen = !recipeOpen;
      recipeBodyEl.style.display = recipeOpen ? "block" : "none";
      recipeToggleEl.textContent = recipeOpen ? "▼" : "▶";
    });

    body.appendChild(recipeSection);

    // ── ADVANCED SECTION ───────────────────────────────────────────────────
    // These buttons keep their original labels so existing tests still pass.
    const advancedSection = document.createElement("div");
    advancedSection.style.cssText = [
      "background:#1e293b",
      "border:1px solid #374151",
      "border-radius:6px",
      "overflow:hidden",
      "display:none",
    ].join(";");

    const advancedHeaderEl = document.createElement("div");
    advancedHeaderEl.style.cssText = [
      "display:flex",
      "align-items:center",
      "justify-content:space-between",
      "padding:5px 8px",
      "cursor:pointer",
    ].join(";");

    const advancedTitleEl = document.createElement("span");
    advancedTitleEl.style.cssText = "font-size:10px;font-weight:600;color:#9ca3af;";
    advancedTitleEl.textContent = "⚙️ Advanced Options";

    const advancedToggleEl = document.createElement("span");
    advancedToggleEl.style.cssText = "font-size:10px;color:#6b7280;";
    advancedToggleEl.textContent = "▶";

    advancedHeaderEl.appendChild(advancedTitleEl);
    advancedHeaderEl.appendChild(advancedToggleEl);

    const advancedBodyEl = document.createElement("div");
    advancedBodyEl.style.cssText = "padding:6px 8px;display:none;";

    let advOpen = false;
    advancedHeaderEl.addEventListener("click", () => {
      advOpen = !advOpen;
      advancedBodyEl.style.display = advOpen ? "block" : "none";
      advancedToggleEl.textContent = advOpen ? "▼" : "▶";
    });

    const row = document.createElement("div");
    row.style.cssText = "display:flex;gap:5px;flex-wrap:wrap;";

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
        "font-family: inherit",
      ].join(";");
      btn.addEventListener("click", handler);
      return btn;
    };

    row.appendChild(
      makeBtn("Mark Page as HTML", () => {
        if (window.ph_mark_html) {
          try {
            window.ph_mark_html({ url: window.location.href });
            addSessionStep("mark_html", `🔗 HTML: ${window.location.pathname}`);
            showStatus("✅ Marked as HTML bulletin page.");
          } catch (_e) {
            showStatus("❌ Could not communicate with page. Try refreshing.", "error");
          }
        } else {
          console.warn("Parish Trainer: ph_mark_html binding is unavailable.");
          showStatus("❌ Could not communicate with page. Try refreshing.", "error");
        }
      })
    );

    // "Mark Current URL as File" is kept for backward compatibility.
    // Safety validation is applied via markDownloadUrlSafe.
    row.appendChild(
      makeBtn("Mark Current URL as File", () => {
        markDownloadUrlSafe(window.location.href, showStatus, false);
      })
    );

    row.appendChild(
      makeBtn("Crop Bulletin Image", () => {
        bar.dataset.phHidden = "true";
        bar.style.display = "none";
        startCrop();
      })
    );

    advancedBodyEl.appendChild(row);
    advancedSection.appendChild(advancedHeaderEl);
    advancedSection.appendChild(advancedBodyEl);
    body.appendChild(advancedSection);

    bar.appendChild(body);
    bar.appendChild(statusBar);

    // ── "Mark Anyway" confirmation button for non-document URLs ───────────
    window.addEventListener("ph-confirm-mark-download", (e) => {
      const url = e.detail && e.detail.url;
      if (!url) return;
      clearTimeout(statusTimer);
      statusBar.style.display = "block";
      statusBar.style.background = "#78350f";
      statusBar.style.color = "#fde68a";
      statusBar.style.opacity = "1";

      const old = statusBar.querySelector(".ph-mark-anyway");
      if (old) statusBar.removeChild(old);

      const markAnywayBtn = document.createElement("button");
      markAnywayBtn.className = "ph-mark-anyway";
      markAnywayBtn.textContent = "⚠️ Mark Anyway";
      markAnywayBtn.style.cssText = [
        "border:none",
        "border-radius:4px",
        "padding:3px 8px",
        "background:#dc2626",
        "color:#fff",
        "cursor:pointer",
        "font-size:10px",
        "margin-left:6px",
        "font-family:inherit",
        "vertical-align:middle",
      ].join(";");
      markAnywayBtn.addEventListener("click", () => {
        markDownloadUrlSafe(url, showStatus, true);
        if (markAnywayBtn.parentNode) {
          markAnywayBtn.parentNode.removeChild(markAnywayBtn);
        }
      });
      statusBar.appendChild(markAnywayBtn);
    });

    // ── Drag behaviour ─────────────────────────────────────────────────────
    let isDragging = false;
    let dragOffsetX = 0;
    let dragOffsetY = 0;

    header.addEventListener("mousedown", (event) => {
      if (event.button !== 0) return;
      isDragging = true;
      const r = bar.getBoundingClientRect();
      bar.style.transform = "none";
      bar.style.left = `${r.left}px`;
      bar.style.top = `${r.top}px`;
      dragOffsetX = event.clientX - r.left;
      dragOffsetY = event.clientY - r.top;
      header.style.cursor = "grabbing";
      event.preventDefault();
    });

    document.addEventListener("mousemove", (event) => {
      if (!isDragging) return;
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

  // ── Message listener from isolated world / side panel ────────────────────

  window.addEventListener("message", (event) => {
    if (event.source !== window) return;
    if (event.data && event.data.direction === "from-isolated") {
      const message = event.data.message;

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

      if (message?.type === "show_toolbar") {
        if (!toolbar) {
          toolbar = createToolbar();
          document.documentElement.appendChild(toolbar);
          console.log("✅ Parish Trainer toolbar ready");
        } else if (toolbar.dataset.phHidden === "true") {
          toolbar.dataset.phHidden = "false";
          toolbar.style.display = "flex";
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
        addSessionStep("mark_html", `🔗 HTML: ${window.location.pathname}`);
        return;
      }
      if (type === "mark_file") {
        if (!window.ph_mark_download_url) {
          console.warn("Parish Trainer: ph_mark_download_url binding is unavailable.");
          return;
        }
        window.ph_mark_download_url({ url: window.location.href });
        addSessionStep("mark_file", `📄 File: ${window.location.pathname}`);
        return;
      }
      if (type === "mark_image" && message?.url) {
        if (!window.ph_mark_image) {
          console.warn("Parish Trainer: ph_mark_image binding is unavailable.");
          return;
        }
        window.ph_mark_image({ url: message.url });
        addSessionStep("mark_image", `🖼️ Image: ${message.url.slice(-45)}`);
        return;
      }
      if (type === "start_crop") {
        startCrop();
        return;
      }
      if (type === "start_pick_link") {
        // Show the toolbar if hidden so the confirmation panel is visible
        if (!toolbar) {
          toolbar = createToolbar();
          document.documentElement.appendChild(toolbar);
        } else {
          toolbar.dataset.phHidden = "false";
          toolbar.style.display = "flex";
        }
        // startPickLinkMode and showPickConfirmation live in the toolbar closure,
        // so we trigger via a custom event that the toolbar can hear.
        window.dispatchEvent(new CustomEvent("ph-start-pick-link"));
        return;
      }
      if (type === "start_pick_iframe") {
        if (!toolbar) {
          toolbar = createToolbar();
          document.documentElement.appendChild(toolbar);
        } else {
          toolbar.dataset.phHidden = "false";
          toolbar.style.display = "flex";
        }
        window.dispatchEvent(new CustomEvent("ph-start-pick-iframe"));
        return;
      }
      if (type === "mark_crop") {
        const payload = message?.x != null ? message : null;
        if (!payload) return;
        if (cropSignature(payload) === lastCropSignature) return;
        if (!window.ph_mark_crop) {
          console.warn("Parish Trainer: ph_mark_crop binding is unavailable.");
          return;
        }
        window.ph_mark_crop(payload);
      }
    }
  });

  // ── Click recording ───────────────────────────────────────────────────────

  document.addEventListener(
    "click",
    (event) => {
      // Skip clicks inside the floating toolbar itself
      if (
        event.target instanceof Element &&
        event.target.closest("#ph-floating-toolbar")
      )
        return;
      // Skip clicks during pick-link mode (handled by the dedicated handler)
      if (pickLinkActive) return;

      const target =
        event.target instanceof Element
          ? event.target.closest(
              'a,button,[role],input[type="submit"],input[type="button"]'
            )
          : null;
      if (!target) return;
      if (!window.ph_record_click) return;
      const clickData = {
        tag: (target.tagName || "").toLowerCase(),
        role: (target.getAttribute("role") || "").toLowerCase(),
        text: (target.innerText || target.textContent || "").trim().slice(0, 200),
        href: target.getAttribute("href") || "",
        css_path: cssPath(target),
      };
      window.ph_record_click(clickData);
      const label = clickData.text
        ? `🔗 Click: "${clickData.text.slice(0, 40)}"`
        : `🔗 Click: ${clickData.css_path.slice(0, 40)}`;
      addSessionStep("click", label);
    },
    true
  );

  // ── Auto-show toolbar when Playwright training bindings are detected ──────

  const _TRAINING_BINDINGS = ["ph_mark_html", "ph_mark_download_url", "ph_mark_crop"];
  const _AUTO_SHOW_DELAYS_MS = [0, 300, 1000, 2500];

  const _tryAutoShowToolbar = () => {
    if (toolbar) return;
    if (_TRAINING_BINDINGS.some((b) => typeof window[b] === "function")) {
      toolbar = createToolbar();
      document.documentElement.appendChild(toolbar);
      console.log("✅ Parish Trainer toolbar ready");
    }
  };

  _AUTO_SHOW_DELAYS_MS.forEach((delay) => setTimeout(_tryAutoShowToolbar, delay));
})();
