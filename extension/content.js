(() => {
  // ── Session state ────────────────────────────────────────────────────────
  let cropOverlay = null;
  let lastCropSignature = "";
  let toolbar = null;
  let sessionSteps = []; // {type, label} tracked in the training UI
  let pickLinkActive = false;
  let pickLinkHighlightEl = null;
  let pickLinkCancelListeners = [];
  let pickImageActive = false;
  let pickImageHighlightEl = null;
  let pickImageCancelListeners = [];
  let pickedImages = []; // accumulates {url, el} when picking multiple
  let _stepsListEl = null; // set by createToolbar
  let _refreshRecipeCount = null; // callback set by createToolbar

  // ── Standalone recipe accumulator ────────────────────────────────────────
  // When the Playwright training bindings (window.ph_*) are absent, the
  // extension operates in "standalone" mode.  Steps are stored here so the
  // user can later push the recipe directly to GitHub without running train.py.
  const standaloneSteps = []; // {action, ...} — recipe step objects
  let standaloneStartUrl = "";

  const _inStandaloneMode = () => typeof window.ph_mark_download_url !== "function";

  const standaloneAddStep = (step) => {
    if (!_inStandaloneMode()) return;
    // Replace an existing download/image/html step if one already exists
    const terminal = ["download", "image", "html"];
    if (terminal.includes(step.action)) {
      const idx = standaloneSteps.findIndex((s) => terminal.includes(s.action));
      if (idx >= 0) {
        standaloneSteps.splice(idx, 1);
      }
    }
    standaloneSteps.push(step);
    if (!standaloneStartUrl) {
      standaloneStartUrl = window.location.href;
    }
  };

  const standaloneUndo = (actionType) => {
    if (!_inStandaloneMode()) return;
    for (let i = standaloneSteps.length - 1; i >= 0; i--) {
      if (standaloneSteps[i].action === actionType) {
        standaloneSteps.splice(i, 1);
        break;
      }
    }
  };

  const buildStandaloneRecipe = (parishKey, displayName, diocese) => {
    const steps = [];
    if (standaloneStartUrl) {
      steps.push({ action: "goto", url: standaloneStartUrl });
    }
    steps.push(...standaloneSteps);
    return {
      version: 1,
      parish_key: parishKey,
      display_name: displayName,
      diocese: diocese || "",
      start_url: standaloneStartUrl || window.location.href,
      steps,
    };
  };

  const clearStandaloneRecipe = () => {
    standaloneSteps.length = 0;
    standaloneStartUrl = "";
  };

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

  // ── URL date extraction and candidate scoring ──────────────────────────────

  // Month abbreviation (first 3 letters, lowercase) → month number
  const _MONTH_ABBR_MAP = {
    jan: 1, feb: 2, mar: 3, apr: 4, may: 5, jun: 6,
    jul: 7, aug: 8, sep: 9, oct: 10, nov: 11, dec: 12,
  };

  /**
   * Extract the best date from a URL / filename string.
   * Returns {year, month, day} or null.
   * month and/or day may be 0 when not found (partial date).
   * Handles: ISO (2026-04-26), WP path (/2026/04/26/), ordinal slug
   * (26th-April-2026), ISO-nodash (20260426), DDMMYYYY (26042026),
   * year-month path (/2026/04/), and bare year (2026).
   */
  const extractDateFromUrl = (text) => {
    let s;
    try { s = decodeURIComponent(text).toLowerCase(); } catch (_e) { s = text.toLowerCase(); }

    // ISO: 2026-04-26
    let m = s.match(/\b(20\d{2})-(0[1-9]|1[0-2])-([0-2]\d|3[01])\b/);
    if (m) return { year: +m[1], month: +m[2], day: +m[3] };

    // WP path: /2026/04/26/
    m = s.match(/\/(20\d{2})\/(0[1-9]|1[0-2])\/([0-2]\d|3[01])\//);
    if (m) return { year: +m[1], month: +m[2], day: +m[3] };

    // Ordinal / plain slug: 26th-april-2026, 3rd-may-2026, 26-april-2026, 26_april_2026
    m = s.match(/\b(\d{1,2})(?:st|nd|rd|th)?[-_]([a-z]{3,9})[-_](20\d{2})\b/);
    if (m) {
      const mo = _MONTH_ABBR_MAP[m[2].slice(0, 3)];
      if (mo) return { year: +m[3], month: mo, day: +m[1] };
    }

    // ISO nodash: 20260426 (8 consecutive digits)
    m = s.match(/(?<!\d)(20\d{2})(0[1-9]|1[0-2])([0-2]\d|3[01])(?!\d)/);
    if (m) return { year: +m[1], month: +m[2], day: +m[3] };

    // DDMMYYYY: 26042026 (last resort — inherently ambiguous, restrict to 2020-2039 to reduce false positives)
    m = s.match(/(?<!\d)([0-2]\d|3[01])(0[1-9]|1[0-2])(20[2-3]\d)(?!\d)/);
    if (m) return { year: +m[3], month: +m[2], day: +m[1] };

    // WP year/month path: /2026/04/ (partial — no day)
    m = s.match(/\/(20\d{2})\/(0[1-9]|1[0-2])\//);
    if (m) return { year: +m[1], month: +m[2], day: 0 };

    // Bare year only (fallback — match any 20xx year)
    m = s.match(/\b(20\d{2})\b/);
    if (m) return { year: +m[1], month: 0, day: 0 };

    return null;
  };

  // Approximate date scores for named liturgical events (used when no numeric date found).
  const _NAMED_BULLETIN_SCORES = {
    "easter sunday": { month: 4, day: 15 },
    "palm sunday": { month: 4, day: 8 },
    "good friday": { month: 4, day: 14 },
    "ash wednesday": { month: 3, day: 5 },
    "pentecost": { month: 5, day: 19 },
    "corpus christi": { month: 6, day: 15 },
    "christmas": { month: 12, day: 25 },
  };

  /**
   * Score a URL+label candidate for bulletin date ranking.
   * Higher total = better candidate (newer date, better keywords, pdf preferred).
   * Returns {dateScore, tieBreaker, hasDate, hasFullDate, total}.
   * NOTE: domIdx is accepted for API compatibility but is NOT included in tieBreaker —
   * callers should store domIdx separately and use the date-first sort helper below.
   */
  const scoreUrlCandidateStr = (url, label, domIdx) => {
    let decoded;
    try { decoded = decodeURIComponent((url || "") + " " + (label || "")).toLowerCase(); }
    catch (_e) { decoded = ((url || "") + " " + (label || "")).toLowerCase(); }
    let d = extractDateFromUrl(decoded);
    const keywordBonus = /\b(bulletin|newsletter|notice)\b/.test(decoded) ? 5 : 0;
    const pdfBonus = /\.pdf(\?|$)/.test(decoded) ? 3 : 0;
    const docxBonus = /\.docx(\?|$)/.test(decoded) ? 1 : 0;
    const uploadsBonus = decoded.includes("/uploads/") || decoded.includes("/wp-content/") ? 2 : 0;
    // If no numeric date found, check for named liturgical events
    if (!d) {
      for (const [name, approx] of Object.entries(_NAMED_BULLETIN_SCORES)) {
        if (decoded.includes(name)) {
          const approxYear = new Date().getFullYear();
          const dateScore = approxYear * 10000 + approx.month * 100 + approx.day;
          const tieBreaker = keywordBonus + pdfBonus + docxBonus + uploadsBonus;
          return {
            dateScore,
            tieBreaker,
            hasDate: true,
            hasFullDate: false,
            total: dateScore * 100 + tieBreaker,
          };
        }
      }
    }
    const dateScore = d ? d.year * 10000 + d.month * 100 + d.day : 0;
    const hasFullDate = d !== null && d.month > 0 && d.day > 0;
    const hasDate = d !== null && d.year > 0;
    // tieBreaker does NOT include domIdx — position is handled by the sort comparator
    const tieBreaker = keywordBonus + pdfBonus + docxBonus + uploadsBonus;
    return { dateScore, tieBreaker, hasDate, hasFullDate, total: dateScore * 100 + tieBreaker };
  };

  /**
   * Comparator for scored bulletin candidates.
   * When dates are available, date always wins (newest first).
   * Falls back to inverted domIdx (later on page = better) only when no dates exist.
   */
  const _bulletinDateSortFn = (a, b) => {
    if (a.hasFullDate && b.hasFullDate) return b.dateScore - a.dateScore;
    if (a.hasFullDate) return -1;
    if (b.hasFullDate) return 1;
    if (a.hasDate && b.hasDate) return b.dateScore - a.dateScore;
    if (a.hasDate) return -1;
    if (b.hasDate) return 1;
    // Neither has a date — later on page wins (many pages list newest at the bottom)
    return (b.domIdx || 0) - (a.domIdx || 0);
  };

  /**
   * Return a human-readable date string from a URL+label pair, or null if no date found.
   */
  const getDisplayDate = (url, label) => {
    let decoded;
    try { decoded = decodeURIComponent((url || "") + " " + (label || "")).toLowerCase(); }
    catch (_e) { decoded = ((url || "") + " " + (label || "")).toLowerCase(); }
    const d = extractDateFromUrl(decoded);
    if (!d || !d.year) return null;
    const months = ["","Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
    if (d.month > 0 && d.day > 0) return `${d.day} ${months[d.month]} ${d.year}`;
    if (d.month > 0) return `${months[d.month]} ${d.year}`;
    return `${d.year}`;
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

    // 3a. Wix PDF viewer detection — must run BEFORE generic pdfIframes check
    const wixViewerIframes = iframes.filter((f) => {
      const src = f.getAttribute("src") || "";
      try {
        const hostname = new URL(src, window.location.href).hostname.toLowerCase();
        return (
          hostname === "wixlabs-pdf-dev.appspot.com" ||
          hostname.startsWith("wixlabs-pdf")
        );
      } catch (_e) {
        return false;
      }
    });

    if (wixViewerIframes.length > 0) {
      // Try to extract the real PDF URL from the Wix viewer src
      let extractedPdfUrl = null;
      for (const frame of wixViewerIframes) {
        try {
          const wixUrl = new URL(frame.getAttribute("src") || "", window.location.href);
          const pdfParam =
            wixUrl.searchParams.get("url") ||
            wixUrl.searchParams.get("PDF_URL") ||
            wixUrl.searchParams.get("pdf") ||
            wixUrl.searchParams.get("file");
          if (pdfParam) {
            extractedPdfUrl = decodeURIComponent(pdfParam);
            break;
          }
        } catch (_e) {}
      }
      return {
        emoji: "📄",
        summary: extractedPdfUrl
          ? `Wix PDF viewer detected — found the PDF URL automatically.`
          : `Wix PDF viewer detected (${wixViewerIframes.length} viewer(s)).`,
        advice: extractedPdfUrl
          ? `Click "It's in a frame / viewer" to record the extracted PDF URL directly.`
          : `💡 Click the ↓ download icon at the TOP of the viewer. When a new tab opens with the PDF, come back and click 📄 Get a PDF.`,
        type: "wix_viewer",
        wixPdfUrl: extractedPdfUrl,
      };
    }

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

  // ── Pick Image Mode ───────────────────────────────────────────────────────

  const stopPickImageMode = () => {
    if (!pickImageActive) return;
    pickImageActive = false;
    if (pickImageHighlightEl && pickImageHighlightEl.parentNode) {
      pickImageHighlightEl.parentNode.removeChild(pickImageHighlightEl);
    }
    pickImageHighlightEl = null;
    pickImageCancelListeners.forEach(({ el, type, fn }) =>
      el.removeEventListener(type, fn, true)
    );
    pickImageCancelListeners = [];
    document.body.style.cursor = "";
  };

  const startPickImageMode = (onPick, showStatus) => {
    if (pickImageActive) stopPickImageMode();
    pickImageActive = true;
    document.body.style.cursor = "crosshair";
    if (showStatus) {
      showStatus(
        "🖼️ Hover over an image and click to select it. Press Escape to cancel.",
        "info"
      );
    }

    const highlight = document.createElement("div");
    Object.assign(highlight.style, {
      position: "fixed",
      pointerEvents: "none",
      border: "3px solid #f59e0b",
      background: "rgba(245,158,11,0.15)",
      borderRadius: "4px",
      zIndex: "2147483645",
      display: "none",
      boxSizing: "border-box",
    });
    document.documentElement.appendChild(highlight);
    pickImageHighlightEl = highlight;

    const IMAGE_SELECTOR = "img[src]";

    const onMouseMove = (e) => {
      if (!pickImageActive) return;
      const el = document.elementFromPoint(e.clientX, e.clientY);
      if (el && el.closest("#ph-floating-toolbar")) {
        highlight.style.display = "none";
        return;
      }
      const candidate = el
        ? el.closest(IMAGE_SELECTOR) || (el.tagName === "IMG" ? el : null)
        : null;
      if (candidate) {
        const r = candidate.getBoundingClientRect();
        Object.assign(highlight.style, {
          display: "block",
          left: `${r.left - 3}px`,
          top: `${r.top - 3}px`,
          width: `${r.width + 6}px`,
          height: `${r.height + 6}px`,
        });
      } else {
        highlight.style.display = "none";
      }
    };

    const onClick = (e) => {
      if (!pickImageActive) return;
      if (e.target instanceof Element && e.target.closest("#ph-floating-toolbar"))
        return;
      const el =
        e.target instanceof Element
          ? e.target.closest(IMAGE_SELECTOR) ||
            (e.target.tagName === "IMG" ? e.target : null)
          : null;
      if (!el) return;
      e.preventDefault();
      e.stopImmediatePropagation();
      stopPickImageMode();
      onPick(el);
    };

    const onKeyDown = (e) => {
      if (e.key === "Escape") {
        stopPickImageMode();
        if (showStatus) showStatus("❌ Image selection cancelled.", "info");
      }
    };

    document.addEventListener("mousemove", onMouseMove, true);
    document.addEventListener("click", onClick, true);
    document.addEventListener("keydown", onKeyDown, true);
    pickImageCancelListeners = [
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
      // Standalone mode: accumulate step locally for later GitHub push
      standaloneAddStep({ action: "download", url });
      addSessionStep("mark_file", `📄 File: ${url.slice(-50)}`);
      if (showStatus) showStatus("✅ File URL saved (standalone). Use ⬆ Push Recipe to save to GitHub.");
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
      let isWixViewer = false;

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
      } else if ((() => {
          try {
            const hostname = new URL(src, window.location.href).hostname.toLowerCase();
            return hostname === "wixlabs-pdf-dev.appspot.com" || hostname.startsWith("wixlabs-pdf");
          } catch (_e) { return false; }
        })()) {
        // Unwrap Wix PDF viewer URL
        try {
          const wixUrl = new URL(src, window.location.href);
          const pdfParam =
            wixUrl.searchParams.get("url") ||
            wixUrl.searchParams.get("PDF_URL") ||
            wixUrl.searchParams.get("pdf") ||
            wixUrl.searchParams.get("file");
          if (pdfParam) {
            resolvedUrl = decodeURIComponent(pdfParam);
            isBulletin = true;
          } else {
            // Can't extract URL — mark as Wix viewer so we show special instruction
            isWixViewer = true;
          }
        } catch (_e) {
          isWixViewer = true;
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
      if (isWixViewer) {
        const wixNote = document.createElement("div");
        wixNote.style.cssText = "color:#93c5fd;font-size:9px;margin-top:2px;line-height:1.4;";
        wixNote.textContent = "💡 Wix PDF viewer — click the ↓ download icon at the TOP of the viewer. When a new tab opens with the PDF, come back and click 📄 Get a PDF.";
        info.appendChild(wixNote);
      } else if (!isBulletin) {
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

  // ── Chrome interstitial detection helpers ─────────────────────────────────

  const detectChromeInterstitial = () => {
    return (
      document.getElementById("main-frame-error") !== null ||
      document.getElementById("security-interstitial-content") !== null ||
      (document.body && document.body.id === "t")
    );
  };

  const tryClickChromeInterstitialProceed = () => {
    const btn =
      document.getElementById("proceed-link") ||
      document.getElementById("proceed-button") ||
      document.querySelector("#proceed-link, #proceed-button, .proceed-button, [id*='proceed']");
    if (btn) { try { btn.click(); } catch (_e) {} }
  };

  // ── createToolbar ─────────────────────────────────────────────────────────

  const createToolbar = () => {
    const bar = document.createElement("div");
    bar.id = "ph-floating-toolbar";
    bar.setAttribute("role", "toolbar");
    bar.setAttribute("aria-label", "Parish Trainer");
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
      "overflow: hidden",
      `max-height: calc(${window.innerHeight}px - 40px)`,
    ].join(";");
    window.addEventListener("resize", () => {
      bar.style.maxHeight = `calc(${window.innerHeight}px - 40px)`;
    });

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
    closeBtn.type = "button";
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
      stopPickImageMode();
    });
    header.appendChild(closeBtn);

    const dockBtn = document.createElement("button");
    dockBtn.type = "button";
    dockBtn.textContent = "⊡";
    dockBtn.title = "Snap to top-right corner";
    dockBtn.style.cssText = [
      "background: none",
      "border: none",
      "color: #9ca3af",
      "cursor: pointer",
      "font-size: 12px",
      "line-height: 1",
      "padding: 0 2px",
    ].join(";");
    dockBtn.addEventListener("click", () => {
      bar.style.left = window.innerWidth - bar.offsetWidth - 10 + "px";
      bar.style.top = "10px";
      bar.style.transform = "";
    });
    header.appendChild(dockBtn);

    // Interstitial banner (shown when Chrome blocks the page)
    if (detectChromeInterstitial()) {
      const interstitialBanner = document.createElement("div");
      interstitialBanner.id = "ph-interstitial-banner";
      interstitialBanner.style.cssText = [
        "background:#7f1d1d",
        "color:#fca5a5",
        "padding:8px 10px",
        "font-size:11px",
        "line-height:1.5",
        "border-radius:8px 8px 0 0",
      ].join(";");
      const msg = document.createElement("div");
      msg.textContent = "⚠️ Chrome is blocking this page (connection not private).";
      const instruction = document.createElement("div");
      instruction.style.cssText = "margin-top:4px;font-weight:600;";
      instruction.textContent = "👉 Click Advanced → Proceed to [site] (unsafe), then click Continue here.";
      const continueBtn = document.createElement("button");
      continueBtn.type = "button";
      continueBtn.textContent = "Continue here ↩";
      continueBtn.style.cssText = [
        "margin-top:6px","border:none","border-radius:4px",
        "padding:4px 10px","background:#dc2626","color:#fff",
        "cursor:pointer","font-size:10px","font-family:inherit",
      ].join(";");
      continueBtn.addEventListener("click", () => {
        tryClickChromeInterstitialProceed();
        if (interstitialBanner.parentNode) interstitialBanner.parentNode.removeChild(interstitialBanner);
      });
      interstitialBanner.appendChild(msg);
      interstitialBanner.appendChild(instruction);
      interstitialBanner.appendChild(continueBtn);
      bar.appendChild(interstitialBanner);
    }

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

    // Show a "please choose" panel when the top candidate is ambiguous.
    const showPickMultipleChoice = (candidates, hasAnyDate) => {
      guidedPanel.innerHTML = "";

      const heading = document.createElement("div");
      heading.style.cssText = "font-weight:600;color:#fbbf24;margin-bottom:6px;font-size:11px;";
      heading.textContent = hasAnyDate
        ? "Multiple dated bulletins found — please pick one:"
        : "No dates detected — please pick the correct bulletin:";
      guidedPanel.appendChild(heading);

      if (hasAnyDate) {
        const note = document.createElement("div");
        note.style.cssText = "font-size:9px;color:#6b7280;margin-bottom:4px;";
        note.textContent = "Sorted newest-first. ⭐ = most likely this week's bulletin.";
        guidedPanel.appendChild(note);
      }

      // Warn if the page lists oldest first (newest candidate appeared last on page)
      const looksReversed = candidates.length > 2 &&
        candidates[0].hasFullDate &&
        candidates[0].domIdx > candidates[candidates.length - 1].domIdx;
      if (looksReversed) {
        const reversedNote = document.createElement("div");
        reversedNote.style.cssText = "color:#fbbf24;font-size:9px;margin-bottom:5px;padding:3px 5px;background:#451a03;border-radius:3px;";
        reversedNote.textContent = "⚠️ This page lists oldest first — showing newest at top.";
        guidedPanel.appendChild(reversedNote);
      }

      // Find candidate closest to today to highlight as "this week"
      // Use real Date arithmetic so month boundaries work correctly
      const today = new Date();
      const todayMs = today.getTime();
      const MS_PER_DAY = 86400000;
      const thisWeekCandidate = candidates.find(c => {
        if (!c.hasFullDate) return false;
        const year = Math.floor(c.dateScore / 10000);
        const month = Math.floor((c.dateScore % 10000) / 100);
        const day = c.dateScore % 100;
        const candidateMs = new Date(year, month - 1, day).getTime();
        return Math.abs(todayMs - candidateMs) <= 7 * MS_PER_DAY;
      }) || (candidates.length > 0 && candidates[0].hasFullDate ? candidates[0] : null);

      // Split into dated and undated groups
      const datedCandidates = candidates.filter(c => c.hasDate);
      const undatedCandidates = candidates.filter(c => !c.hasDate);

      const renderCandidate = (candidate, idx, isRecommended) => {
        const { el, url, label } = candidate;
        const row = document.createElement("div");
        row.style.cssText = [
          "display:flex",
          "align-items:center",
          "gap:5px",
          "padding:4px",
          "margin-bottom:4px",
          "background:#0f172a",
          "border-radius:4px",
        ].join(";");

        // Highlight this week's candidate with a green border
        if (candidate === thisWeekCandidate) {
          row.style.border = "1px solid #16a34a";
          row.style.background = "#052e16";
        }

        const info = document.createElement("div");
        info.style.cssText = [
          "flex:1",
          "font-size:9px",
          "word-break:break-all",
          "color:#d1d5db",
          "line-height:1.35",
        ].join(";");

        // Date badge
        const displayDate = getDisplayDate(url, label);
        if (displayDate) {
          const dateBadge = document.createElement("span");
          dateBadge.style.cssText = "color:#fbbf24;font-size:9px;font-weight:600;display:block;margin-bottom:1px;";
          dateBadge.textContent = `📅 ${displayDate}`;
          info.appendChild(dateBadge);
        }

        const textSpan = document.createElement("span");
        textSpan.style.cssText = "white-space:pre-wrap;";
        const shortUrl = (url || "").length > 55 ? (url || "").slice(0, 52) + "…" : (url || "");
        const shortLabel = (label || "").slice(0, 40);
        const prefix = isRecommended ? "⭐ Recommended (newest)\n" : "";
        textSpan.textContent = prefix + (shortLabel ? shortLabel + "\n" + shortUrl : shortUrl);
        info.appendChild(textSpan);

        const pickBtn = document.createElement("button");
        pickBtn.textContent = "Use this";
        pickBtn.style.cssText = [
          "border:none",
          "border-radius:3px",
          "padding:3px 7px",
          "background:#2563eb",
          "color:#fff",
          "cursor:pointer",
          "font-size:9px",
          "font-family:inherit",
          "flex-shrink:0",
        ].join(";");
        pickBtn.addEventListener("click", () => showPickConfirmation(el));
        row.appendChild(info);
        row.appendChild(pickBtn);
        guidedPanel.appendChild(row);
      };

      datedCandidates.forEach((c, idx) => renderCandidate(c, idx, idx === 0 && hasAnyDate));

      if (undatedCandidates.length > 0) {
        const sep = document.createElement("div");
        sep.style.cssText = "color:#6b7280;font-size:9px;margin:4px 0 2px;border-top:1px solid #374151;padding-top:4px;";
        sep.textContent = "⚠️ No date found — review manually:";
        guidedPanel.appendChild(sep);
        undatedCandidates.forEach((c, idx) => renderCandidate(c, idx, false));
      }

      const cancelBtn = document.createElement("button");
      cancelBtn.type = "button";
      cancelBtn.textContent = "↩ Cancel";
      cancelBtn.style.cssText = [
        "border:none",
        "border-radius:3px",
        "padding:3px 8px",
        "background:#374151",
        "color:#d1d5db",
        "cursor:pointer",
        "font-size:9px",
        "font-family:inherit",
        "margin-top:4px",
      ].join(";");
      cancelBtn.addEventListener("click", resetGuidedPanel);
      guidedPanel.appendChild(cancelBtn);
    };

    // Show confirmation after an image is picked
    const showPickImageConfirmation = (imgEl) => {
      const src = imgEl.getAttribute("src") || "";
      const alt = imgEl.getAttribute("alt") || "";
      const absUrl = (() => {
        try {
          return new URL(src, window.location.href).href;
        } catch (_e) {
          return src;
        }
      })();

      guidedPanel.innerHTML = "";

      const heading = document.createElement("div");
      heading.style.cssText =
        "font-weight:600;color:#93c5fd;margin-bottom:6px;font-size:11px;";
      heading.textContent =
        pickedImages.length > 0
          ? `Is this image #${pickedImages.length + 1} correct?`
          : "Is this the right image?";
      guidedPanel.appendChild(heading);

      const preview = document.createElement("div");
      preview.style.cssText = [
        "background:#0f172a",
        "border-radius:4px",
        "padding:5px",
        "margin-bottom:6px",
        "text-align:center",
      ].join(";");

      const thumb = document.createElement("img");
      thumb.src = absUrl;
      thumb.style.cssText =
        "max-width:100%;max-height:80px;border-radius:3px;display:block;margin:0 auto 4px;";
      thumb.alt = alt || "selected image";
      preview.appendChild(thumb);

      const urlText = document.createElement("div");
      urlText.style.cssText = "font-size:9px;color:#9ca3af;word-break:break-all;";
      urlText.textContent =
        absUrl.length > 70 ? absUrl.slice(0, 67) + "…" : absUrl;
      preview.appendChild(urlText);
      if (alt) {
        const altText = document.createElement("div");
        altText.style.cssText = "font-size:9px;color:#6b7280;margin-top:2px;";
        altText.textContent = `Alt: "${alt}"`;
        preview.appendChild(altText);
      }
      guidedPanel.appendChild(preview);

      if (pickedImages.length > 0) {
        const countNote = document.createElement("div");
        countNote.style.cssText = "font-size:9px;color:#fbbf24;margin-bottom:5px;";
        countNote.textContent = `Already picked ${pickedImages.length} image(s). Add this one too?`;
        guidedPanel.appendChild(countNote);
      }

      const btnRow = document.createElement("div");
      btnRow.style.cssText = "display:flex;flex-direction:column;gap:4px;";

      const confirmBtn = makeSmallBtn(
        pickedImages.length > 0 ? "✅ Yes — add this image" : "✅ Yes, use this image",
        "#16a34a",
        () => {
          pickedImages.push({ url: absUrl, el: imgEl });
          if (window.ph_mark_image) {
            try {
              window.ph_mark_image({ url: absUrl });
              addSessionStep("mark_image", `🖼️ Image: ${absUrl.slice(-50)}`);
              showStatus(`✅ Image recorded: ${absUrl.slice(-40)}`);
            } catch (_e) {
              showStatus("❌ Could not record image. Try refreshing.", "error");
            }
          } else {
            addSessionStep("mark_image", `🖼️ Image: ${absUrl.slice(-50)}`);
            showStatus(`✅ Image noted: ${absUrl.slice(-40)}`);
          }
          pickedImages = [];
          resetGuidedPanel();
        },
        "Record this image as the bulletin"
      );

      const addAnotherBtn = makeSmallBtn(
        "➕ Pick another image too",
        "#2563eb",
        () => {
          pickedImages.push({ url: absUrl, el: imgEl });
          showStatus(
            `✅ Image ${pickedImages.length} saved. Now pick the next one.`,
            "info"
          );
          resetGuidedPanel();
          startPickImageMode(showPickImageConfirmation, showStatus);
        },
        "Add another image (e.g. multi-page bulletin)"
      );

      const pickAgainBtn = makeSmallBtn(
        "🔄 Pick a different image",
        "#374151",
        () => {
          resetGuidedPanel();
          startPickImageMode(showPickImageConfirmation, showStatus);
        },
        "Select a different image"
      );

      const cancelBtn = makeSmallBtn("↩ Cancel", "#374151", () => {
        pickedImages = [];
        resetGuidedPanel();
      });
      cancelBtn.style.fontSize = "10px";
      cancelBtn.style.padding = "4px 8px";

      btnRow.appendChild(confirmBtn);
      if (pickedImages.length === 0) btnRow.appendChild(addAnotherBtn);
      btnRow.appendChild(pickAgainBtn);
      btnRow.appendChild(cancelBtn);
      guidedPanel.appendChild(btnRow);

      if (imgEl instanceof Element) {
        const prev = imgEl.style.outline;
        imgEl.style.outline = "3px solid #f59e0b";
        imgEl.scrollIntoView({ behavior: "smooth", block: "nearest" });
        setTimeout(() => {
          if (imgEl.style.outline === "3px solid #f59e0b") imgEl.style.outline = prev;
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
        "🖼️ Pick an image on this page",
        "#2563eb",
        () => {
          pickedImages = [];
          startPickImageMode(showPickImageConfirmation, showStatus);
        },
        "Click to hover-select an existing image on the page — no cropping needed"
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
    wizardBtns.appendChild(
      makeSmallBtn(
        "🚫 No bulletin here (skip)",
        "#6b7280",
        () => {
          if (typeof window.ph_mark_download_url === "function") {
            try {
              window.ph_mark_download_url({ url: "no_bulletin", type: "no_bulletin" });
            } catch (_e) {}
          }
          addSessionStep("no_bulletin", "🚫 No bulletin — skipped");
          showStatus("🚫 Marked as no bulletin. You can now close this tab or move on.");
        },
        "Record that this parish has no bulletin and skip it"
      )
    );

    guidedPanel.appendChild(wizardQ);
    guidedPanel.appendChild(wizardBtns);
    guidedPanel.appendChild(stuckLink);
    bar.appendChild(guidedPanel);

    // Listen for messages from the side-panel / isolated world that request
    // pick modes — they need to run inside the createToolbar closure.
    window.addEventListener("ph-start-pick-link", () => {
      startPickLinkMode(showPickConfirmation, showStatus);
    });
    window.addEventListener("ph-start-pick-image-mode", () => {
      pickedImages = [];
      startPickImageMode(showPickImageConfirmation, showStatus);
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
    window.addEventListener("ph-document-detected", (e) => {
      const url = (e.detail && e.detail.url) || "";
      const short = url.length > 50 ? url.slice(0, 47) + "…" : url;
      showStatus(`🔍 Document detected in network: ${short}`, "info");
    });

    // ── IDENTIFY PAGE ──────────────────────────────────────────────────────
    const identifyBtn = document.createElement("button");
    identifyBtn.type = "button";
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
      "max-height: 160px",
      "overflow-y: auto",
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
            // Score each link using extracted date + keyword/filetype tie-breakers.
            const scored = pickableLinks.map((el, idx) => {
              const url = el.getAttribute("href") || "";
              const label = (el.innerText || el.textContent || "").trim();
              const s = scoreUrlCandidateStr(url, label, idx);
              return { el, url, label, domIdx: idx, ...s };
            });
            scored.sort(_bulletinDateSortFn);

            // Ambiguous: no dates found at all, or top two candidates share the
            // same date score (cannot tell which is newer).
            const hasAnyDate = scored.some((c) => c.hasDate);
            const ambiguous =
              !hasAnyDate ||
              (scored.length > 1 && scored[0].dateScore === scored[1].dateScore);

            if (!ambiguous) {
              showPickConfirmation(scored[0].el);
            } else {
              showPickMultipleChoice(scored.slice(0, 3), hasAnyDate);
            }
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

                // Sort detected URLs by date score (newest first)
                const scoredUrls = urls.map((url, idx) => ({
                  url,
                  domIdx: idx,
                  ...scoreUrlCandidateStr(url, "", idx),
                }));
                scoredUrls.sort(_bulletinDateSortFn);
                const hasAnyUrlDate = scoredUrls.some((c) => c.hasDate);

                heading.textContent = `🕵️ Detected ${urls.length} document URL(s) — sorted by recency:`;
                identifyResult.appendChild(heading);

                // Explain the recommendation or warn that no dates were found
                const note = document.createElement("div");
                note.style.cssText = "font-size:9px;margin-bottom:5px;";
                if (hasAnyUrlDate) {
                  note.style.color = "#6b7280";
                  note.textContent = "⭐ marks the recommended pick (looks like the newest dated bulletin).";
                } else {
                  note.style.color = "#fbbf24";
                  note.textContent = "⚠️ No dates detected in URLs — please review and pick manually.";
                }
                identifyResult.appendChild(note);

                scoredUrls.forEach(({ url, hasDate }, rankIdx) => {
                  const row = document.createElement("div");
                  row.style.cssText =
                    "display:flex;gap:5px;margin-bottom:3px;align-items:center;";
                  // Highlight the top recommended URL when we have date info
                  if (rankIdx === 0 && hasDate) {
                    row.style.cssText +=
                      "background:#052e16;border-radius:3px;padding:2px 3px;";
                  }
                  const preview = document.createElement("span");
                  preview.style.cssText =
                    "flex:1;font-size:9px;word-break:break-all;line-height:1.35;white-space:pre-wrap;";
                  preview.style.color = (rankIdx === 0 && hasDate) ? "#86efac" : "#d1d5db";
                  let labelText = "";
                  if (rankIdx === 0 && hasDate) {
                    labelText = "⭐ Recommended (newest)\n";
                  }
                  labelText += url.length > 70 ? url.slice(0, 67) + "…" : url;
                  preview.textContent = labelText;
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

      // Wix PDF viewer handling
      if (result.type === "wix_viewer") {
        if (result.wixPdfUrl) {
          // We extracted the URL — offer a one-click record button
          const useExtractedBtn = makeSmallBtn(
            "📄 Use extracted PDF URL",
            "#16a34a",
            () => markDownloadUrlSafe(result.wixPdfUrl, showStatus, true),
            "Record the PDF URL extracted from the Wix viewer"
          );
          useExtractedBtn.style.marginTop = "6px";
          identifyResult.appendChild(useExtractedBtn);
        }
        // Always show the iframe picker button for Wix
        const iframeBtn = makeSmallBtn(
          "📐 Open frame picker",
          "#2563eb",
          () => window.dispatchEvent(new CustomEvent("ph-start-pick-iframe")),
          "Open the iframe picker to select the Wix viewer"
        );
        iframeBtn.style.marginTop = "6px";
        identifyResult.appendChild(iframeBtn);
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
    undoBtn.type = "button";
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
          // Standalone mode — accumulate step for later GitHub push
          standaloneAddStep({ action: "html", url: window.location.href });
          addSessionStep("mark_html", `🔗 HTML: ${window.location.pathname}`);
          showStatus("✅ HTML page URL saved (standalone). Use ⬆ Push Recipe to save to GitHub.");
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

    // ── Quick Bulletin Fix (standalone mode) ──────────────────────────────
    // Prominent one-click path: navigate to the real bulletin PDF/page, then
    // use this section to save it as the recipe for a named parish without
    // having to record any intermediate click steps.  This is the primary
    // manual override path when the auto-scraper picked the wrong bulletin.
    if (_inStandaloneMode()) {
      const quickFixSection = document.createElement("div");
      quickFixSection.id = "ph-quick-fix";
      quickFixSection.style.cssText = [
        "background:#1e293b",
        "border:2px solid #f59e0b",
        "border-radius:6px",
        "padding:8px",
        "margin-top:6px",
      ].join(";");

      const qfTitle = document.createElement("div");
      qfTitle.style.cssText = "font-size:10px;font-weight:700;color:#fbbf24;margin-bottom:4px;";
      qfTitle.textContent = "📌 Fix Wrong Bulletin (direct override)";
      quickFixSection.appendChild(qfTitle);

      const qfNote = document.createElement("div");
      qfNote.style.cssText = "font-size:9px;color:#9ca3af;margin-bottom:6px;line-height:1.4;";
      qfNote.textContent =
        "Navigate to the correct bulletin PDF (or the page that links to it), " +
        "enter the parish key below, and click Fix. " +
        "This pushes a minimal recipe that overwrites any wrong one.";
      quickFixSection.appendChild(qfNote);

      // URL row
      const qfUrlLabel = document.createElement("div");
      qfUrlLabel.style.cssText = "font-size:9px;color:#93c5fd;margin-bottom:2px;";
      qfUrlLabel.textContent = "Bulletin URL (current page or paste PDF URL):";
      quickFixSection.appendChild(qfUrlLabel);

      const qfUrlInput = document.createElement("input");
      qfUrlInput.type = "url";
      qfUrlInput.id = "ph-qf-url";
      qfUrlInput.placeholder = "https://parish.com/bulletin.pdf";
      qfUrlInput.value = window.location.href;
      qfUrlInput.style.cssText = [
        "width:100%",
        "border:1px solid #374151",
        "border-radius:4px",
        "padding:4px 6px",
        "background:#0f172a",
        "color:#f9fafb",
        "font-size:10px",
        "margin-bottom:4px",
        "box-sizing:border-box",
        "font-family:inherit",
      ].join(";");
      quickFixSection.appendChild(qfUrlInput);

      // Parish key row
      const qfKeyLabel = document.createElement("div");
      qfKeyLabel.style.cssText = "font-size:9px;color:#93c5fd;margin-bottom:2px;";
      qfKeyLabel.textContent = "Parish key (e.g. ballycastleparish):";
      quickFixSection.appendChild(qfKeyLabel);

      const qfKeyInput = document.createElement("input");
      qfKeyInput.type = "text";
      qfKeyInput.id = "ph-qf-key";
      qfKeyInput.placeholder = "ballycastleparish";
      qfKeyInput.style.cssText = [
        "width:100%",
        "border:1px solid #374151",
        "border-radius:4px",
        "padding:4px 6px",
        "background:#0f172a",
        "color:#f9fafb",
        "font-size:10px",
        "margin-bottom:4px",
        "box-sizing:border-box",
        "font-family:inherit",
      ].join(";");
      quickFixSection.appendChild(qfKeyInput);

      // Display name row
      const qfNameLabel = document.createElement("div");
      qfNameLabel.style.cssText = "font-size:9px;color:#93c5fd;margin-bottom:2px;";
      qfNameLabel.textContent = "Parish display name (e.g. Ballycastle Parish):";
      quickFixSection.appendChild(qfNameLabel);

      const qfNameInput = document.createElement("input");
      qfNameInput.type = "text";
      qfNameInput.id = "ph-qf-name";
      qfNameInput.placeholder = "Ballycastle Parish";
      qfNameInput.style.cssText = [
        "width:100%",
        "border:1px solid #374151",
        "border-radius:4px",
        "padding:4px 6px",
        "background:#0f172a",
        "color:#f9fafb",
        "font-size:10px",
        "margin-bottom:4px",
        "box-sizing:border-box",
        "font-family:inherit",
      ].join(";");
      quickFixSection.appendChild(qfNameInput);

      // Pre-populate diocese from storage
      const qfDioceseInput = document.createElement("input");
      qfDioceseInput.type = "text";
      qfDioceseInput.id = "ph-qf-diocese";
      qfDioceseInput.placeholder = "derry_diocese (optional)";
      qfDioceseInput.style.cssText = [
        "width:100%",
        "border:1px solid #374151",
        "border-radius:4px",
        "padding:4px 6px",
        "background:#0f172a",
        "color:#f9fafb",
        "font-size:10px",
        "margin-bottom:6px",
        "box-sizing:border-box",
        "font-family:inherit",
      ].join(";");
      chrome.storage.local.get(["ph_last_diocese"], (r) => {
        if (r.ph_last_diocese) qfDioceseInput.value = r.ph_last_diocese;
      });
      quickFixSection.appendChild(qfDioceseInput);

      const qfBtn = document.createElement("button");
      qfBtn.type = "button";
      qfBtn.textContent = "📌 Fix This Bulletin Now";
      qfBtn.style.cssText = [
        "border:none",
        "border-radius:6px",
        "padding:8px 10px",
        "background:#f59e0b",
        "color:#000",
        "cursor:pointer",
        "font-size:11px",
        "font-weight:700",
        "text-align:center",
        "font-family:inherit",
        "line-height:1.3",
        "width:100%",
        "margin-bottom:4px",
      ].join(";");
      qfBtn.addEventListener("mouseenter", () => { qfBtn.style.filter = "brightness(1.1)"; });
      qfBtn.addEventListener("mouseleave", () => { qfBtn.style.filter = ""; });
      qfBtn.addEventListener("click", async () => {
        const url = qfUrlInput.value.trim();
        const key = qfKeyInput.value.trim().toLowerCase().replace(/\s+/g, "");
        const name = qfNameInput.value.trim();
        const diocese = qfDioceseInput.value.trim();

        if (!url) { showStatus("❌ Bulletin URL is required.", "error"); return; }
        if (!key)  { showStatus("❌ Parish key is required.", "error"); return; }
        if (!name) { showStatus("❌ Display name is required.", "error"); return; }

        // Determine the correct recipe step: download for document URLs, html otherwise
        const action = isDocumentUrl(url) ? "download" : "html";
        const startUrl = window.location.href;

        // Build a minimal recipe: goto the page we are on now, then download/html the target
        const recipe = {
          version: 1,
          parish_key: key,
          display_name: name,
          diocese: diocese || "",
          start_url: startUrl,
          steps: [
            { action: "goto", url: startUrl },
            { action, url },
          ],
        };

        qfBtn.disabled = true;
        qfBtn.textContent = "⏳ Pushing fix…";
        showStatus("⏳ Pushing bulletin fix to GitHub…", "info");

        try {
          const response = await new Promise((resolve, reject) => {
            chrome.runtime.sendMessage({ type: "push_recipe", parish_key: key, recipe }, (res) => {
              if (chrome.runtime.lastError) { reject(new Error(chrome.runtime.lastError.message)); return; }
              resolve(res);
            });
          });
          if (response && response.ok) {
            showStatus(`✅ Bulletin fix saved! ${response.url}`);
            if (diocese) chrome.storage.local.set({ ph_last_diocese: diocese });
          } else {
            showStatus(`❌ ${(response && response.error) || "Unknown error"}`, "error");
          }
        } catch (err) {
          showStatus(`❌ ${err.message}`, "error");
        } finally {
          qfBtn.disabled = false;
          qfBtn.textContent = "📌 Fix This Bulletin Now";
        }
      });
      quickFixSection.appendChild(qfBtn);

      body.appendChild(quickFixSection);
    }

    // ── Push Recipe to GitHub (standalone mode) ───────────────────────────
    // Only rendered when the Playwright bindings are absent.  Uses the
    // standaloneSteps[] accumulated above to build a recipe JSON and push
    // it directly to the repo via the GitHub Contents API.
    if (_inStandaloneMode()) {
      const pushSection = document.createElement("div");
      pushSection.id = "ph-push-section";
      pushSection.style.cssText = [
        "background:#1e293b",
        "border:1px solid #16a34a",
        "border-radius:6px",
        "padding:8px",
        "margin-top:6px",
      ].join(";");

      const pushTitle = document.createElement("div");
      pushTitle.style.cssText = "font-size:10px;font-weight:600;color:#86efac;margin-bottom:6px;";
      pushTitle.textContent = "⬆ Push Recipe to GitHub";
      pushSection.appendChild(pushTitle);

      const makeInput = (placeholder, id) => {
        const inp = document.createElement("input");
        inp.type = "text";
        inp.placeholder = placeholder;
        inp.id = id;
        inp.style.cssText = [
          "width:100%",
          "border:1px solid #374151",
          "border-radius:4px",
          "padding:4px 6px",
          "background:#0f172a",
          "color:#f9fafb",
          "font-size:10px",
          "margin-bottom:4px",
          "box-sizing:border-box",
          "font-family:inherit",
        ].join(";");
        return inp;
      };

      const keyInput = makeInput("Parish key — e.g. ardmoreparish", "ph-parish-key");
      const nameInput = makeInput("Display name — e.g. Ardmore Parish", "ph-display-name");
      const dioceseInput = makeInput("Diocese — e.g. derry_diocese", "ph-diocese");
      pushSection.appendChild(keyInput);
      pushSection.appendChild(nameInput);
      pushSection.appendChild(dioceseInput);

      // Pre-populate diocese from storage
      chrome.storage.local.get(["ph_last_diocese"], (r) => {
        if (r.ph_last_diocese) dioceseInput.value = r.ph_last_diocese;
      });

      const stepCountEl = document.createElement("div");
      stepCountEl.style.cssText = "font-size:9px;color:#6b7280;margin-bottom:5px;";
      const refreshStepCount = () => {
        stepCountEl.textContent = `${standaloneSteps.length} step(s) recorded`;
      };
      refreshStepCount();
      pushSection.appendChild(stepCountEl);

      // Keep count in sync with session steps
      const origRefreshRecipeCount = _refreshRecipeCount;
      _refreshRecipeCount = () => {
        if (origRefreshRecipeCount) origRefreshRecipeCount();
        refreshStepCount();
      };

      const pushBtn = document.createElement("button");
      pushBtn.type = "button";
      pushBtn.textContent = "⬆ Push Recipe to GitHub";
      pushBtn.style.cssText = [
        "border:none",
        "border-radius:6px",
        "padding:6px 10px",
        "background:#16a34a",
        "color:#fff",
        "cursor:pointer",
        "font-size:11px",
        "text-align:left",
        "white-space:normal",
        "font-family:inherit",
        "line-height:1.3",
        "width:100%",
        "margin-bottom:4px",
      ].join(";");
      pushBtn.addEventListener("click", async () => {
        const key = keyInput.value.trim().toLowerCase().replace(/\s+/g, "");
        const name = nameInput.value.trim();
        const diocese = dioceseInput.value.trim();
        if (!key) { showStatus("❌ Parish key is required.", "error"); return; }
        if (!name) { showStatus("❌ Display name is required.", "error"); return; }
        if (standaloneSteps.length === 0) { showStatus("⚠️ No steps recorded yet.", "warn"); return; }

        const recipe = buildStandaloneRecipe(key, name, diocese);
        pushBtn.disabled = true;
        pushBtn.textContent = "⏳ Pushing…";
        showStatus("⏳ Pushing recipe to GitHub…", "info");

        try {
          const response = await new Promise((resolve, reject) => {
            chrome.runtime.sendMessage({ type: "push_recipe", parish_key: key, recipe }, (res) => {
              if (chrome.runtime.lastError) { reject(new Error(chrome.runtime.lastError.message)); return; }
              resolve(res);
            });
          });
          if (response && response.ok) {
            showStatus(`✅ Recipe saved! ${response.url}`, "ok");
            if (diocese) chrome.storage.local.set({ ph_last_diocese: diocese });
            clearStandaloneRecipe();
            refreshStepCount();
          } else {
            showStatus(`❌ ${(response && response.error) || "Unknown error"}`, "error");
          }
        } catch (err) {
          showStatus(`❌ ${err.message}`, "error");
        } finally {
          pushBtn.disabled = false;
          pushBtn.textContent = "⬆ Push Recipe to GitHub";
        }
      });
      pushSection.appendChild(pushBtn);

      const clearBtn = document.createElement("button");
      clearBtn.type = "button";
      clearBtn.textContent = "🗑 Clear steps";
      clearBtn.style.cssText = [
        "border:1px solid #374151",
        "border-radius:6px",
        "padding:4px 8px",
        "background:transparent",
        "color:#9ca3af",
        "cursor:pointer",
        "font-size:10px",
        "font-family:inherit",
        "width:100%",
      ].join(";");
      clearBtn.addEventListener("click", () => {
        clearStandaloneRecipe();
        sessionSteps.length = 0;
        if (_stepsListEl) _stepsListEl.innerHTML = "";
        refreshStepCount();
        showStatus("🗑 Steps cleared.", "info");
      });
      pushSection.appendChild(clearBtn);

      body.appendChild(pushSection);
    }

    // ── Scroll container wraps body so the toolbar is scrollable when tall ─
    const scrollContainer = document.createElement("div");
    scrollContainer.id = "ph-toolbar-scroll";
    scrollContainer.style.cssText = "overflow-y: auto;flex: 1 1 auto;min-height: 0;";
    scrollContainer.appendChild(body);
    bar.appendChild(scrollContainer);
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
      const bw = bar.offsetWidth;
      const bh = bar.offsetHeight;
      const clampedLeft = Math.max(0, Math.min(event.clientX - dragOffsetX, window.innerWidth - bw));
      const clampedTop  = Math.max(0, Math.min(event.clientY - dragOffsetY, window.innerHeight - bh));
      bar.style.left = `${clampedLeft}px`;
      bar.style.top  = `${clampedTop}px`;
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
          // In standalone (private addon) mode, only create the toolbar when the
          // user explicitly clicks the extension icon (toggle_toolbar).  During a
          // Playwright training session the ph_* bindings are already present so
          // we auto-create here to restore the toolbar after page navigations.
          const inTrainingMode = _TRAINING_BINDINGS.some(
            (b) => typeof window[b] === "function"
          );
          if (inTrainingMode) {
            toolbar = createToolbar();
            document.documentElement.appendChild(toolbar);
            console.log("✅ Parish Trainer toolbar ready");
          }
        } else if (toolbar.dataset.phHidden === "true") {
          toolbar.dataset.phHidden = "false";
          toolbar.style.display = "flex";
        }
        return;
      }

      const type = message?.type;
      if (type === "mark_html") {
        if (window.ph_mark_html) {
          window.ph_mark_html({ url: window.location.href });
        } else {
          // Standalone mode
          standaloneAddStep({ action: "html", url: window.location.href });
        }
        addSessionStep("mark_html", `🔗 HTML: ${window.location.pathname}`);
        return;
      }
      if (type === "mark_file") {
        if (window.ph_mark_download_url) {
          window.ph_mark_download_url({ url: window.location.href });
        } else {
          // Standalone mode
          standaloneAddStep({ action: "download", url: window.location.href });
        }
        addSessionStep("mark_file", `📄 File: ${window.location.pathname}`);
        return;
      }
      if (type === "mark_image" && message?.url) {
        if (window.ph_mark_image) {
          window.ph_mark_image({ url: message.url });
        } else {
          // Standalone mode
          standaloneAddStep({ action: "image", url: message.url });
        }
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
      if (type === "start_pick_image") {
        if (!toolbar) {
          toolbar = createToolbar();
          document.documentElement.appendChild(toolbar);
        } else {
          toolbar.dataset.phHidden = "false";
          toolbar.style.display = "flex";
        }
        window.dispatchEvent(new CustomEvent("ph-start-pick-image-mode"));
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
      if (type === "document_url_detected") {
        const url = message?.url || "";
        if (toolbar) {
          toolbar.dataset.phHidden = "false";
          toolbar.style.display = "flex";
        }
        window.dispatchEvent(new CustomEvent("ph-document-detected", { detail: { url } }));
        return;
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
      const clickData = {
        tag: (target.tagName || "").toLowerCase(),
        role: (target.getAttribute("role") || "").toLowerCase(),
        text: (target.innerText || target.textContent || "").trim().slice(0, 200),
        href: target.getAttribute("href") || "",
        css_path: cssPath(target),
      };
      const label = clickData.text
        ? `🔗 Click: "${clickData.text.slice(0, 40)}"`
        : `🔗 Click: ${clickData.css_path.slice(0, 40)}`;
      if (window.ph_record_click) {
        window.ph_record_click(clickData);
        addSessionStep("click", label);
      } else if (_inStandaloneMode() && toolbar && toolbar.style.display !== "none") {
        // Standalone mode: record the navigation click for the recipe
        const text = clickData.text;
        const href = clickData.href;
        const selector = text && text.length >= 3 && text.length <= 60
          ? `${clickData.tag}:has-text("${text.replace(/\\/g, "\\\\").replace(/"/g, '\\"')}")`
          : clickData.css_path;
        const step = { action: "click", selector };
        const fallbacks = [];
        if (href && href.toLowerCase().endsWith(".pdf")) fallbacks.push("a[href$='.pdf']");
        else if (href && href.toLowerCase().endsWith(".docx")) fallbacks.push("a[href$='.docx']");
        if (clickData.css_path && clickData.css_path !== selector) fallbacks.push(clickData.css_path);
        if (fallbacks.length) step.fallback_selectors = fallbacks;
        standaloneAddStep(step);
        addSessionStep("click", label);
      }
    },
    true
  );

  // ── Dead page overlay ────────────────────────────────────────────────────────
  const _showDeadPageOverlay = () => {
    // Already shown?
    if (document.getElementById("ph-dead-page-overlay")) return;

    const overlay = document.createElement("div");
    overlay.id = "ph-dead-page-overlay";
    Object.assign(overlay.style, {
      position: "fixed",
      top: "20px",
      left: "50%",
      transform: "translateX(-50%)",
      zIndex: "2147483647",
      background: "#1f2937",
      color: "#f9fafb",
      fontFamily: "system-ui, -apple-system, sans-serif",
      fontSize: "13px",
      borderRadius: "10px",
      boxShadow: "0 4px 24px rgba(0,0,0,0.7)",
      padding: "16px 20px",
      maxWidth: "420px",
      width: "90vw",
      textAlign: "center",
      border: "2px solid #dc2626",
    });

    const icon = document.createElement("div");
    icon.textContent = "🔴";
    icon.style.cssText = "font-size:28px;margin-bottom:8px;";
    overlay.appendChild(icon);

    const heading = document.createElement("div");
    heading.textContent = "This website appears to be dead or unreachable.";
    heading.style.cssText = "font-weight:700;font-size:14px;margin-bottom:6px;color:#fca5a5;";
    overlay.appendChild(heading);

    const sub = document.createElement("div");
    sub.textContent = "You can mark it as dead in the terminal window — press D then Enter.";
    sub.style.cssText = "color:#9ca3af;font-size:11px;margin-bottom:12px;line-height:1.5;";
    overlay.appendChild(sub);

    const markBtn = document.createElement("button");
    markBtn.textContent = "🗑️ Mark as Dead Website";
    markBtn.type = "button";
    Object.assign(markBtn.style, {
      border: "none",
      borderRadius: "6px",
      padding: "10px 20px",
      background: "#dc2626",
      color: "#fff",
      cursor: "pointer",
      fontSize: "13px",
      fontWeight: "600",
      fontFamily: "inherit",
      width: "100%",
      marginBottom: "8px",
    });
    markBtn.addEventListener("click", () => {
      // Signal to Playwright / train.py via the binding if available
      if (typeof window.ph_mark_download_url === "function") {
        try {
          window.ph_mark_download_url({ url: "dead_url", type: "dead_url" });
        } catch (_e) {}
      }
      // Also post a message the isolated world can pick up
      window.postMessage(
        { direction: "from-main", message: { type: "mark_dead_url" } },
        "*"
      );
      heading.textContent = "✅ Marked as dead. You can close this tab.";
      heading.style.color = "#86efac";
      markBtn.disabled = true;
      markBtn.style.opacity = "0.5";
      sub.textContent = "The harvester will skip this parish in future runs.";
    });
    overlay.appendChild(markBtn);

    const dismissBtn = document.createElement("button");
    dismissBtn.textContent = "Dismiss";
    dismissBtn.type = "button";
    Object.assign(dismissBtn.style, {
      border: "1px solid #374151",
      borderRadius: "6px",
      padding: "6px 14px",
      background: "transparent",
      color: "#9ca3af",
      cursor: "pointer",
      fontSize: "11px",
      fontFamily: "inherit",
    });
    dismissBtn.addEventListener("click", () => {
      if (overlay.parentNode) overlay.parentNode.removeChild(overlay);
    });
    overlay.appendChild(dismissBtn);

    document.documentElement.appendChild(overlay);
  };

  // Detect Chrome net-error pages and show the dead overlay
  const _detectAndShowDeadOverlay = () => {
    const isDeadPage = (
      document.getElementById("main-frame-error") !== null ||
      window.location.href.startsWith("chrome-error://") ||
      (document.title && (
        document.title.toLowerCase().includes("err_name_not_resolved") ||
        document.title.toLowerCase().includes("err_connection_refused") ||
        document.title.toLowerCase().includes("err_connection_timed_out") ||
        document.title.toLowerCase().includes("this site can't be reached") ||
        document.title.toLowerCase().includes("this webpage is not available")
      ))
    );
    if (isDeadPage) _showDeadPageOverlay();
  };

  // Run on load and after short delays (Chrome error pages may render slowly)
  _detectAndShowDeadOverlay();
  setTimeout(_detectAndShowDeadOverlay, 500);
  setTimeout(_detectAndShowDeadOverlay, 1500);

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
