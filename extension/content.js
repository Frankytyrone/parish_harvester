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
    // Escape backslashes first, then double-quotes, for a valid Playwright selector
    const escapeForSelector = (s) => s.replace(/\\/g, "\\\\").replace(/"/g, '\\"');
    if (text && text.length >= 3 && text.length <= 60) {
      return `${tag}:has-text("${escapeForSelector(text)}")`;
    }
    if (role) {
      return `[role="${role}"]:has-text("${escapeForSelector(text)}")`;
    }
    return cssPath(el);
  };

  // Returns true if the URL looks like a downloadable document.
  const isDocumentUrl = (url) => {
    if (!url) return false;
    // Check Google Drive / Docs patterns on the full URL (including query string)
    // before stripping query parameters, since these patterns often live in the query.
    const lowerFull = url.toLowerCase();
    if (
      lowerFull.includes("drive.google.com/file") ||
      lowerFull.includes("docs.google.com/viewer") ||
      lowerFull.includes("drive.google.com/uc?") ||
      lowerFull.includes("drive.google.com/open?")
    )
      return true;
    // Check file extensions on the path (before the query string)
    const lowerPath = lowerFull.split("?")[0];
    const docExts = [".pdf", ".docx", ".doc", ".pptx", ".ppt", ".odt", ".ods"];
    if (docExts.some((ext) => lowerPath.endsWith(ext))) return true;
    return false;
  };

  // Detect what kind of bulletin page we are on and give plain-language guidance.
  const detectPageType = () => {
    const url = window.location.href.toLowerCase();

    // 1. Current page IS a PDF
    if (url.endsWith(".pdf") || url.includes(".pdf?") || url.includes("/pdf/")) {
      return {
        emoji: "📄",
        summary: "This page IS a PDF document.",
        advice: "Click \"Yes, it's a PDF\" to record this URL as the bulletin file.",
        type: "direct_pdf",
      };
    }

    // 2. WordPress PDF Embedder plugin — check original <a> tags AND viewer elements
    const pdfembEls = Array.from(
      document.querySelectorAll(
        'a.pdfemb-viewer, a[class*="pdfemb"], [id^="pdfemb-embed-"], [class*="pdfemb-embed"]'
      )
    );
    // Filter to those that have a usable href or contain a child PDF iframe/embed
    const pdfembLinks = pdfembEls.filter((el) => {
      const href =
        el.getAttribute("href") ||
        el.getAttribute("data-url") ||
        el.getAttribute("data-pdfurl") ||
        "";
      if (href.length > 0) return true;
      // For viewer wrapper divs, look for a nested iframe/embed with a PDF src
      const inner =
        el.querySelector && el.querySelector("iframe[src], embed[src]");
      return (
        inner && (inner.getAttribute("src") || "").toLowerCase().includes(".pdf")
      );
    });
    if (pdfembEls.length > 0 || pdfembLinks.length > 0) {
      const count = Math.max(pdfembEls.length, pdfembLinks.length);
      // Collect anchor elements only (need href for "Pick newest" feature)
      const anchors = pdfembEls.filter(
        (el) =>
          el.tagName === "A" &&
          (el.getAttribute("href") ||
            el.getAttribute("data-url") ||
            el.getAttribute("data-pdfurl"))
      );
      return {
        emoji: "🔗",
        summary: `PDF listing page — found ${count} PDF Embedder link(s) (WordPress plugin).`,
        advice:
          'Use "No — I need to click a link" or "Pick newest bulletin" below to record the right bulletin link.',
        type: "pdfemb",
        links: anchors,
      };
    }

    // 3. iframes with PDF or viewer content
    const iframes = Array.from(document.querySelectorAll("iframe[src]"));
    const pdfIframes = iframes.filter((f) => {
      const src = (f.getAttribute("src") || "").toLowerCase();
      return (
        src.endsWith(".pdf") ||
        src.includes(".pdf?") ||
        src.includes("docs.google.com/viewer") ||
        src.includes("docs.google.com/gview") ||
        src.includes("drive.google.com/file")
      );
    });
    if (pdfIframes.length > 0) {
      return {
        emoji: "🖼️",
        summary: `This page embeds ${pdfIframes.length} PDF frame(s).`,
        advice: "Click \"It's embedded in a frame\" to choose the correct frame.",
        type: "iframe",
      };
    }
    if (iframes.length > 0) {
      return {
        emoji: "🖼️",
        summary: `Found ${iframes.length} frame(s) — may contain a PDF viewer.`,
        advice:
          "Click \"It's embedded in a frame\" to inspect the frames, or use \"Deep Detect\" if the PDF loads in the background.",
        type: "iframe_maybe",
      };
    }

    // 4. <embed> or <object> with PDF content
    const pdfEmbeds = Array.from(
      document.querySelectorAll("embed[src],object[data]")
    ).filter((el) => {
      const src = (
        el.getAttribute("src") ||
        el.getAttribute("data") ||
        ""
      ).toLowerCase();
      return (
        src.includes(".pdf") || el.getAttribute("type") === "application/pdf"
      );
    });
    if (pdfEmbeds.length > 0) {
      return {
        emoji: "📎",
        summary: `Found ${pdfEmbeds.length} embedded PDF object(s).`,
        advice:
          'If the bulletin is showing here, use "Yes, it\'s a PDF". Otherwise try "Deep Detect".',
        type: "embed",
      };
    }

    // 5. Generic PDF / document links
    const pdfLinks = Array.from(document.querySelectorAll("a[href]")).filter(
      (a) => {
        const href = (a.getAttribute("href") || "").toLowerCase();
        return (
          href.includes(".pdf") ||
          href.includes(".docx") ||
          href.includes("/wp-content/uploads/")
        );
      }
    );
    if (pdfLinks.length > 0) {
      const bulletinLinks = pdfLinks.filter((a) => {
        const text = (
          (a.innerText || a.textContent || "") +
          " " +
          (a.getAttribute("href") || "")
        ).toLowerCase();
        return /bulletin|newsletter|notice|\b\d{1,2}(st|nd|rd|th)?.{0,8}(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)/i.test(
          text
        );
      });
      return {
        emoji: "🔗",
        summary: `Found ${pdfLinks.length} PDF link(s)${
          bulletinLinks.length > 0
            ? ` (${bulletinLinks.length} look like weekly bulletins)`
            : ""
        }.`,
        advice:
          "Click \"No — I need to click a link\" to select the correct bulletin.",
        type: "pdf_links",
        links: pdfLinks,
        bulletinLinks,
      };
    }

    // 6. Image bulletins
    const bulletinImages = Array.from(document.querySelectorAll("img")).filter(
      (img) => {
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
      }
    );
    if (bulletinImages.length > 0) {
      return {
        emoji: "🖼️",
        summary: `Found ${bulletinImages.length} possible image bulletin(s).`,
        advice: "Click \"Yes, it's an image\" to crop or mark the image bulletin.",
        type: "image",
      };
    }

    const allLinks = document.querySelectorAll("a[href],button");
    if (allLinks.length > 0) {
      return {
        emoji: "📋",
        summary: "HTML page — no PDF or document links detected.",
        advice:
          'Try "Deep Detect" to listen for background PDF loads, or "No — I need to click a link" to navigate to the bulletin.',
        type: "html",
      };
    }
    return {
      emoji: "❓",
      summary: "Page type not automatically detected.",
      advice:
        "Navigate to the parish bulletin page first, then try again.",
      type: "unknown",
    };
  };

  // ── Deep Detect: monitor network requests for document URLs ──────────────

  const startDeepDetect = (onDetected, showStatus, durationMs = 10000) => {
    const detectedUrls = new Map();
    const origXHR = window.XMLHttpRequest;
    const origFetch = window.fetch;

    const trackUrl = (rawUrl) => {
      if (!rawUrl) return;
      try {
        const abs = new URL(String(rawUrl), window.location.href).href;
        if (isDocumentUrl(abs) && !detectedUrls.has(abs)) {
          detectedUrls.set(abs, true);
        }
      } catch (_e) {
        // ignore unparseable URLs
      }
    };

    // Patch XMLHttpRequest
    function PatchedXHR() {
      const xhr = new origXHR();
      const origOpen = xhr.open.bind(xhr);
      xhr.open = function (method, url, ...rest) {
        trackUrl(url);
        return origOpen(method, url, ...rest);
      };
      return xhr;
    }
    Object.setPrototypeOf(PatchedXHR, origXHR);
    PatchedXHR.prototype = origXHR.prototype;
    window.XMLHttpRequest = PatchedXHR;

    // Patch fetch
    window.fetch = function (input, ...rest) {
      const url =
        typeof input === "string"
          ? input
          : input instanceof Request
          ? input.url
          : "";
      trackUrl(url);
      return origFetch.call(this, input, ...rest);
    };

    // Scan already-loaded resources via Performance API
    try {
      (window.performance.getEntriesByType("resource") || []).forEach((e) =>
        trackUrl(e.name)
      );
    } catch (_e) {}

    // Watch new resource loads via PerformanceObserver
    let observer = null;
    try {
      observer = new PerformanceObserver((list) =>
        list.getEntries().forEach((e) => trackUrl(e.name))
      );
      observer.observe({ entryTypes: ["resource"] });
    } catch (_e) {}

    if (showStatus) {
      showStatus(
        "🔍 Deep Detect active — interact with the page for 10 s…",
        "info"
      );
    }

    setTimeout(() => {
      window.XMLHttpRequest = origXHR;
      window.fetch = origFetch;
      if (observer) observer.disconnect();
      onDetected(Array.from(detectedUrls.keys()));
    }, durationMs);
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
        if (showStatus) showStatus("❌ Link selection cancelled.", "info");
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
      if (showStatus)
        showStatus(
          "ℹ️ No iframes on this page. Try \"Pick Bulletin Link\" for PDF links.",
          "info"
        );
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

      // Scroll hint shown while the overlay is active
      const scrollHint = document.createElement("div");
      Object.assign(scrollHint.style, {
        position: "fixed",
        bottom: "14px",
        left: "50%",
        transform: "translateX(-50%)",
        zIndex: "2147483647",
        background: "rgba(30,41,59,0.92)",
        color: "#93c5fd",
        borderRadius: "6px",
        padding: "5px 14px",
        fontSize: "11px",
        fontFamily: "system-ui, -apple-system, sans-serif",
        pointerEvents: "none",
        whiteSpace: "nowrap",
        boxShadow: "0 2px 8px rgba(0,0,0,0.4)",
      });
      scrollHint.textContent =
        "🖱 Scroll with mouse wheel · drag near top/bottom edge to auto-scroll · Add More for multi-section";
      overlay.appendChild(scrollHint);

      let startX = 0;
      let startY = 0;
      let scrollYAtDragStart = 0;
      let lastMouseClientX = 0;
      let lastMouseClientY = 0;
      let autoScrollRAF = null;
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
        lastMouseClientX = event.clientX;
        lastMouseClientY = event.clientY;
        const scrollDelta = window.scrollY - scrollYAtDragStart;
        const adjustedStartY = startY - scrollDelta;
        cropBox = {
          left:   Math.min(startX, event.clientX),
          top:    Math.min(adjustedStartY, event.clientY),
          width:  Math.abs(event.clientX - startX),
          height: Math.abs(event.clientY - adjustedStartY),
        };
        syncRect();
      };

      const finish = (event) => {
        if (!dragging) return;
        dragging = false;
        if (autoScrollRAF !== null) {
          cancelAnimationFrame(autoScrollRAF);
          autoScrollRAF = null;
        }
        const endX = event.clientX;
        const endY = event.clientY;
        const scrollDelta = window.scrollY - scrollYAtDragStart;
        const adjustedStartY = startY - scrollDelta;
        cropBox = {
          left:   Math.min(startX, endX),
          top:    Math.min(adjustedStartY, endY),
          width:  Math.abs(endX - startX),
          height: Math.abs(endY - adjustedStartY),
        };
        if (cropBox.width < MIN_CROP_SIZE || cropBox.height < MIN_CROP_SIZE) {
          if (sections.length === 0) removeCropOverlay();
          return;
        }
        syncRect();
        showEditMode();
      };

      // ── Auto-scroll while dragging near the top/bottom edge ──────────────
      const AUTOSCROLL_EDGE_PX = 60;
      const AUTOSCROLL_SPEED_PX = 8;

      const autoScrollTick = () => {
        if (!dragging || editMode) {
          autoScrollRAF = null;
          return;
        }
        let scrollDir = 0;
        if (lastMouseClientY < AUTOSCROLL_EDGE_PX) {
          scrollDir = -AUTOSCROLL_SPEED_PX;
        } else if (lastMouseClientY > window.innerHeight - AUTOSCROLL_EDGE_PX) {
          scrollDir = AUTOSCROLL_SPEED_PX;
        }
        if (scrollDir !== 0) {
          window.scrollBy(0, scrollDir);
          const scrollDelta = window.scrollY - scrollYAtDragStart;
          const adjustedStartY = startY - scrollDelta;
          cropBox = {
            left:   Math.min(startX, lastMouseClientX),
            top:    Math.min(adjustedStartY, lastMouseClientY),
            width:  Math.abs(lastMouseClientX - startX),
            height: Math.abs(lastMouseClientY - adjustedStartY),
          };
          syncRect();
        }
        autoScrollRAF = requestAnimationFrame(autoScrollTick);
      };

      overlay.addEventListener("mousedown", (event) => {
        if (editMode) return;
        event.preventDefault();
        startX = event.clientX;
        startY = event.clientY;
        scrollYAtDragStart = window.scrollY;
        lastMouseClientX = event.clientX;
        lastMouseClientY = event.clientY;
        dragging = true;
        rect.style.display = "none";
        autoScrollRAF = requestAnimationFrame(autoScrollTick);
      });

      // Allow mouse-wheel scrolling while the overlay is active.
      overlay.addEventListener("wheel", (event) => {
        event.preventDefault();
        window.scrollBy(0, event.deltaY);
        if (dragging) {
          const scrollDelta = window.scrollY - scrollYAtDragStart;
          const adjustedStartY = startY - scrollDelta;
          cropBox = {
            left:   Math.min(startX, lastMouseClientX),
            top:    Math.min(adjustedStartY, lastMouseClientY),
            width:  Math.abs(lastMouseClientX - startX),
            height: Math.abs(lastMouseClientY - adjustedStartY),
          };
          syncRect();
        }
      }, { passive: false });
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
    wizardQ.textContent = "What do you see on screen?";

    const wizardBtns = document.createElement("div");
    wizardBtns.style.cssText = "display:flex;flex-direction:column;gap:5px;";

    const stuckLink = document.createElement("button");
    stuckLink.type = "button";
    stuckLink.style.cssText = [
      "font-size:9px",
      "color:#6b7280",
      "margin-top:4px",
      "cursor:pointer",
      "text-decoration:underline",
      "background:none",
      "border:none",
      "padding:0",
      "font-family:inherit",
      "display:inline-block",
    ].join(";");
    stuckLink.textContent = "I'm stuck — show all options";
    stuckLink.title = "Open the advanced section with all manual controls";
    stuckLink.addEventListener("click", () => {
      const isHidden = advancedSection.style.display === "none";
      advancedSection.style.display = isHidden ? "block" : "none";
      if (isHidden) {
        // Auto-expand the body so content is immediately visible
        advOpen = true;
        advancedBodyEl.style.display = "block";
        advancedToggleEl.textContent = "▼";
      }
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

      const makePreviewRow = (label, value) => {
        const row = document.createElement("div");
        const strong = document.createElement("strong");
        strong.textContent = label + ": ";
        const span = document.createElement("span");
        span.textContent = value;
        row.appendChild(strong);
        row.appendChild(span);
        return row;
      };
      preview.appendChild(makePreviewRow("Text", text || "(no text)"));
      preview.appendChild(makePreviewRow("Href", (href || "(none)").slice(0, 70)));
      const selectorRow = document.createElement("div");
      const selectorLabel = document.createElement("strong");
      selectorLabel.textContent = "Selector: ";
      const selectorCode = document.createElement("code");
      selectorCode.style.cssText = "font-size:9px;";
      selectorCode.textContent = selector;
      selectorRow.appendChild(selectorLabel);
      selectorRow.appendChild(selectorCode);
      preview.appendChild(selectorRow);
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

    // Wizard buttons (Guided Mode — 3 simple choices)
    wizardBtns.appendChild(
      makeSmallBtn(
        "📄 Get a PDF (recommended)",
        "#16a34a",
        () => markDownloadUrlSafe(window.location.href, showStatus, false),
        "The bulletin is a PDF — record this URL as the bulletin file"
      )
    );
    wizardBtns.appendChild(
      makeSmallBtn(
        "🖼️ Get an image (newsletter screenshot)",
        "#2563eb",
        () => {
          bar.dataset.phHidden = "true";
          bar.style.display = "none";
          startCrop();
        },
        "The bulletin is an image on screen — draw a rectangle to capture it"
      )
    );
    wizardBtns.appendChild(
      makeSmallBtn(
        "🔗 I need to click something first",
        "#2563eb",
        () => startPickLinkMode(showPickConfirmation, showStatus),
        "Click a link or button to navigate to the bulletin"
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
      identifyResult.innerHTML = "";

      const emojiSpan = document.createElement("span");
      emojiSpan.style.cssText = "font-size:15px;";
      emojiSpan.textContent = result.emoji;

      const summaryStrong = document.createElement("strong");
      summaryStrong.style.cssText = "color:#f9fafb;";
      summaryStrong.textContent = result.summary;

      const adviceSpan = document.createElement("span");
      adviceSpan.style.cssText = "color:#9ca3af;display:block;margin-top:2px;";
      adviceSpan.textContent = result.advice;

      identifyResult.appendChild(emojiSpan);
      identifyResult.appendChild(document.createTextNode(" "));
      identifyResult.appendChild(summaryStrong);
      identifyResult.appendChild(adviceSpan);

      // "Pick newest bulletin" shortcut for pdfemb / pdf_links pages
      const pickableLinks = result.links || [];
      if (
        (result.type === "pdfemb" || result.type === "pdf_links") &&
        pickableLinks.length > 0
      ) {
        const pickNewestBtn = makeSmallBtn(
          `🎯 Pick newest bulletin (${pickableLinks.length} link${
            pickableLinks.length !== 1 ? "s" : ""
          } found)`,
          "#16a34a",
          () => {
            // Score each link by date recency: year (most important) → month → day
            // A higher score means a more recent (or more date-complete) link.
            const YEAR_WEIGHT  = 10000;
            const MONTH_WEIGHT = 100;
            const DAY_WEIGHT   = 1;
            const scored = pickableLinks.map((el) => {
              const combined = (
                (el.innerText || el.textContent || "") +
                " " +
                (el.getAttribute("href") || "")
              ).toLowerCase();
              // Extract the last 4-digit year starting with "20"
              const yearMatches = combined.match(/20\d{2}/g) || [];
              const yearVal = yearMatches.length
                ? parseInt(yearMatches[yearMatches.length - 1])
                : 0;
              // Match a written month name to avoid false positives from
              // unrelated numbers (e.g. "12th Sunday" would otherwise score month=12)
              const MONTH_NAMES =
                "jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec";
              const monthMatch = combined.match(
                new RegExp("\\b(" + MONTH_NAMES + ")[a-z]*\\b")
              );
              const MONTH_MAP = {
                jan: 1, feb: 2,  mar: 3,  apr: 4,
                may: 5, jun: 6,  jul: 7,  aug: 8,
                sep: 9, oct: 10, nov: 11, dec: 12,
              };
              const monthVal = monthMatch ? (MONTH_MAP[monthMatch[1]] || 0) : 0;
              // Extract a 1-or-2-digit day near the month name
              const dayMatch = combined.match(
                /\b([12]?\d|3[01])(st|nd|rd|th)?\b/
              );
              const dayVal = dayMatch ? parseInt(dayMatch[1]) : 0;
              return {
                el,
                score:
                  yearVal * YEAR_WEIGHT +
                  monthVal * MONTH_WEIGHT +
                  dayVal * DAY_WEIGHT,
              };
            });
            scored.sort((a, b) => b.score - a.score);
            showPickConfirmation(scored[0].el);
          },
          "Automatically selects the most recent bulletin link for you to confirm"
        );
        pickNewestBtn.style.marginTop = "6px";
        identifyResult.appendChild(pickNewestBtn);
      }

      // "Deep Detect" button for pages with no obvious document content
      if (
        result.type === "html" ||
        result.type === "unknown" ||
        result.type === "embed" ||
        result.type === "iframe_maybe"
      ) {
        const deepBtn = makeSmallBtn(
          "🕵️ Deep Detect (10 s) — watch for hidden PDF loads",
          "#4b5563",
          () => {
            deepBtn.disabled = true;
            deepBtn.style.opacity = "0.5";
            startDeepDetect(
              (urls) => {
                deepBtn.disabled = false;
                deepBtn.style.opacity = "1";
                if (urls.length === 0) {
                  showStatus(
                    "Deep Detect: no document URLs detected in 10 s.",
                    "info"
                  );
                  return;
                }
                identifyResult.innerHTML = "";
                const heading = document.createElement("div");
                heading.style.cssText =
                  "font-weight:600;color:#93c5fd;margin-bottom:5px;font-size:10px;";
                heading.textContent = `🕵️ Detected ${urls.length} document URL(s):`;
                identifyResult.appendChild(heading);
                urls.forEach((url) => {
                  const row = document.createElement("div");
                  row.style.cssText =
                    "display:flex;gap:5px;margin-bottom:3px;align-items:center;";
                  const preview = document.createElement("span");
                  preview.style.cssText =
                    "flex:1;font-size:9px;word-break:break-all;color:#d1d5db;";
                  preview.textContent =
                    url.length > 70 ? url.slice(0, 67) + "…" : url;
                  const useBtn = document.createElement("button");
                  useBtn.textContent = "Use";
                  useBtn.style.cssText = [
                    "border:none",
                    "border-radius:3px",
                    "padding:2px 6px",
                    "background:#16a34a",
                    "color:#fff",
                    "cursor:pointer",
                    "font-size:9px",
                    "font-family:inherit",
                    "flex-shrink:0",
                  ].join(";");
                  useBtn.addEventListener("click", () =>
                    markDownloadUrlSafe(url, showStatus, isDocumentUrl(url))
                  );
                  row.appendChild(preview);
                  row.appendChild(useBtn);
                  identifyResult.appendChild(row);
                });
              },
              showStatus
            );
          },
          "Listens for any PDF/DOCX requests the page makes in the background — interact with the page to trigger loads"
        );
        deepBtn.style.marginTop = "6px";
        identifyResult.appendChild(deepBtn);
      }
    });

    // identifyBtn and identifyResult are added to the Advanced section below.

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

    // ── Iframe picker in Advanced ─────────────────────────────────────────
    const iframePickerBtn = makeBtn("📐 It's in a frame / viewer", () => {
      const pickerPanel = buildIframePickerPanel(showStatus);
      if (pickerPanel) {
        guidedPanel.innerHTML = "";
        const backBtn = makeSmallBtn("← Back", "#374151", resetGuidedPanel);
        backBtn.style.width = "auto";
        backBtn.style.marginBottom = "6px";
        guidedPanel.appendChild(backBtn);
        guidedPanel.appendChild(pickerPanel);
        advancedSection.style.display = "none";
      }
    });
    iframePickerBtn.style.marginTop = "5px";
    advancedBodyEl.appendChild(iframePickerBtn);

    // ── Capture newsletter column (auto) ──────────────────────────────────
    const CONTENT_SELECTORS = [
      "article",
      ".entry-content",
      ".post-content",
      ".content-area",
      ".inside-article",
      ".site-content",
      '[role="main"]',
      "main",
    ];
    const captureAreaBtn = makeBtn("📰 Capture newsletter column (auto)", () => {
      let found = null;
      for (const sel of CONTENT_SELECTORS) {
        const el = document.querySelector(sel);
        if (el) { found = el; break; }
      }
      if (!found) {
        showStatus("ℹ️ No main content column detected — try crop manually.", "info");
        return;
      }
      const prevOutline = found.style.outline;
      found.style.outline = "3px solid #f59e0b";
      found.scrollIntoView({ behavior: "smooth", block: "nearest" });
      showStatus(
        "📰 Content column highlighted in orange. Use crop (or Add More) to capture it.",
        "info"
      );
      setTimeout(() => {
        if (found.style.outline === "3px solid #f59e0b") {
          found.style.outline = prevOutline;
        }
      }, 5000);
    });
    advancedBodyEl.appendChild(captureAreaBtn);

    // ── Identify page (moved from main body to Advanced) ──────────────────
    identifyBtn.style.marginTop = "5px";
    advancedBodyEl.appendChild(identifyBtn);
    advancedBodyEl.appendChild(identifyResult);
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
