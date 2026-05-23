(() => {
  const AI_SYSTEM_PROMPT = `You are an assistant inside a Catholic parish bulletin harvesting Chrome extension.
The user is non-technical. Be brief, warm, and practical.

Your job is to look at information about the current web page and tell the user:
1. What type of bulletin this page has (PDF, image, HTML, iframe, Google Drive, Facebook, none found)
2. Whether there are any issues (no SSL = http://, page still loading, login required, Facebook blocks automation)
3. The exact steps to capture the bulletin using the Parish Trainer toolbar buttons

Toolbar buttons available:
- "Get a PDF (recommended)" — for direct PDF links
- "I need to click something first" — for pages where you must click a link to reveal the PDF
- "Get an image (newsletter screenshot)" — for image bulletins (JPEG/PNG)
- "It's in a frame / viewer" — for iframes containing PDFs
- "Help me identify this page" — runs auto-detection

Keep answers to 3-5 short sentences. Do not use jargon. If unsure, say so honestly.`;

  function memoryKey(hostname) {
    return `ph_ai_memory_${hostname || "unknown"}`;
  }

  function looksLikeBulletinImage(src, textHint = "") {
    const lowerSrc = String(src || "").toLowerCase();
    const lowerHint = String(textHint || "").toLowerCase();
    return (
      /\.(jpe?g|png|webp)(?:$|[?#])/i.test(lowerSrc) ||
      /bulletin|newsletter|parish|weekly/.test(lowerSrc) ||
      /bulletin|newsletter/.test(lowerHint)
    );
  }

  function classifyPageContext(pageContext) {
    const ctx = pageContext || {};
    const iframeSrcs = Array.isArray(ctx.iframes) ? ctx.iframes : [];
    const pdfLinks = Array.isArray(ctx.pdfLinks) ? ctx.pdfLinks : [];
    const imageLinks = Array.isArray(ctx.images) ? ctx.images : [];
    const directPdf = /\.pdf(?:$|[?#])/i.test(String(ctx.url || ""));
    const iframePdf = iframeSrcs.some((src) => /\.pdf(?:$|[?#])/i.test(src) || /drive\.google|docs\.google|viewer/i.test(src));
    const isDrive = Boolean(ctx.hasGoogleDrive || /drive\.google|drive\.usercontent\.google\.com/i.test(String(ctx.url || "")));
    const isFacebook = Boolean(ctx.hasFacebook || /facebook\.com/i.test(String(ctx.url || "")));
    const isMcn = Boolean(ctx.hasMcnLive || /mcn\.live/i.test(String(ctx.url || "")));
    const hasImages = imageLinks.length > 0;
    const warnings = [];

    if (ctx.isHttp) warnings.push("This page has no SSL (http://), so it may load slowly or be blocked.");
    if (ctx.readyState && ctx.readyState !== "complete") warnings.push("This page still looks like it is loading.");
    if (Number(ctx.loadingIframeCount || 0) > 0) warnings.push("Some iframes still look like they are loading — wait 30 seconds and ask again.");
    if (isFacebook) warnings.push("Facebook blocks automation, so this may need to be done manually.");
    if (isMcn) warnings.push("MCN Live is a camera stream, so there may be no bulletin file to capture automatically.");

    if (isFacebook) {
      return {
        type: "Facebook page",
        stepsSummary: "Open the Facebook post or photo manually. If you only get text, use print to PDF or copy the text.",
        warnings,
      };
    }
    if (isMcn) {
      return {
        type: "MCN Live camera page",
        stepsSummary: "This is usually just a livestream page. Look for a separate bulletin link on the parish site, or save the page link only.",
        warnings,
      };
    }
    if (isDrive) {
      return {
        type: "Google Drive link",
        stepsSummary: "Open the Drive file or folder first. If it opens a PDF file, use Get a PDF. If it is only a folder, choose the bulletin file manually first.",
        warnings,
      };
    }
    if (directPdf || pdfLinks.length > 0) {
      return {
        type: "Direct PDF link",
        stepsSummary: pdfLinks.length > 0
          ? 'Click "Get a PDF (recommended)". If the PDF only appears after another click, click "I need to click something first" first.'
          : 'This page is already a PDF, so click "Get a PDF (recommended)".',
        warnings,
      };
    }
    if (iframePdf || iframeSrcs.length > 0) {
      return {
        type: "PDF hidden inside an iframe",
        stepsSummary: 'Click "It\'s in a frame / viewer". If nothing appears yet, wait for the frame to finish loading and try again.',
        warnings,
      };
    }
    if (hasImages) {
      return {
        type: "Image bulletin",
        stepsSummary: 'Use "Get an image (newsletter screenshot)". If there are several pages, capture each bulletin image you need.',
        warnings,
      };
    }
    return {
      type: "HTML page with no PDF found",
      stepsSummary: 'Use "Help me identify this page" first. If there is still no PDF, print the page to PDF or capture the text manually.',
      warnings,
    };
  }

  function probeCurrentPageContext() {
    const absolutize = (value) => {
      try {
        return new URL(value, window.location.href).href;
      } catch (_e) {
        return "";
      }
    };

    const hrefs = Array.from(document.querySelectorAll("a[href]")).map((a) => absolutize(a.getAttribute("href") || ""));
    const iframes = Array.from(document.querySelectorAll("iframe")).map((frame) => ({
      src: absolutize(frame.getAttribute("src") || frame.src || ""),
      loading: String(frame.getAttribute("src") || frame.src || "").trim() === "",
    }));
    const images = Array.from(document.querySelectorAll("img")).map((img) => ({
      src: absolutize(img.getAttribute("src") || img.src || ""),
      hint: [img.getAttribute("alt"), img.getAttribute("title"), img.className].filter(Boolean).join(" "),
    }));

    return {
      url: window.location.href,
      title: document.title || "",
      hostname: window.location.hostname || "",
      isHttp: window.location.protocol === "http:",
      readyState: document.readyState || "",
      iframes: iframes.map((item) => item.src).filter(Boolean),
      loadingIframeCount: iframes.filter((item) => item.loading || !item.src).length,
      pdfLinks: hrefs.filter((href) => /\.pdf(?:$|[?#])/i.test(href)).slice(0, 10),
      images: images
        .filter((img) => looksLikeBulletinImage(img.src, img.hint))
        .map((img) => img.src)
        .filter(Boolean)
        .slice(0, 5),
      hasGoogleDrive: hrefs.some((href) => /drive\.google\.com/i.test(href)),
      hasFacebook: hrefs.some((href) => /facebook\.com/i.test(href)),
      hasMcnLive: hrefs.some((href) => /mcn\.live/i.test(href)),
      bodyText: String(document.body?.innerText || "").replace(/\s+/g, " ").trim().slice(0, 2000),
    };
  }

  function assertContext(context) {
    if (!context || !context.url) {
      throw new Error("Could not read this page yet. Refresh the page and try again.");
    }
    return context;
  }

  async function gatherPageContextFromCurrentPage() {
    return assertContext(probeCurrentPageContext());
  }

  async function gatherPageContextFromTabId(tabId) {
    if (!tabId) throw new Error("Open the parish website in a normal tab first.");
    if (!chrome?.scripting?.executeScript) throw new Error("Page scanner unavailable.");
    const results = await chrome.scripting.executeScript({
      target: { tabId },
      func: probeCurrentPageContext,
    });
    return assertContext(results?.[0]?.result || null);
  }

  async function gatherPageContextFromBestTab(getBestTab) {
    const tab = await getBestTab();
    if (!tab?.id) throw new Error("Open the parish website in a normal tab first.");
    return gatherPageContextFromTabId(tab.id);
  }

  async function _storageGet(keys, storageGet) {
    if (typeof storageGet === "function") return storageGet(keys);
    return await new Promise((resolve) => {
      if (!chrome?.storage?.local) {
        resolve({});
        return;
      }
      chrome.storage.local.get(keys, (result) => resolve(result || {}));
    });
  }

  async function _storageSet(payload, storageSet) {
    if (typeof storageSet === "function") return storageSet(payload);
    return await new Promise((resolve) => {
      if (!chrome?.storage?.local) {
        resolve(false);
        return;
      }
      chrome.storage.local.set(payload, () => resolve(!chrome.runtime?.lastError));
    });
  }

  async function askGemini({ userMessage, pageContext, messages = [], currentMemory = null, storageGet, apiKey = "" }) {
    const settings = await _storageGet(["gemini_api_key"], storageGet);
    const resolvedApiKey = String(apiKey || settings.gemini_api_key || "").trim();
    if (!resolvedApiKey) throw new Error("missing_api_key");

    const memoryText = currentMemory
      ? `Last saved memory for this host: ${currentMemory.type} — ${currentMemory.steps_summary}. Confirmed: ${currentMemory.confirmed ? "yes" : "no"}.`
      : "No saved memory for this host yet.";
    const summary = classifyPageContext(pageContext);
    const history = messages.slice(-6).map((message) => `${message.role}: ${message.text}`).join("\n");
    const prompt = [
      AI_SYSTEM_PROMPT,
      "",
      memoryText,
      `Likely bulletin type from page scan: ${summary.type}.`,
      `Likely capture steps: ${summary.stepsSummary}`,
      summary.warnings.length ? `Warnings: ${summary.warnings.join(" ")}` : "Warnings: none obvious.",
      "",
      "Page context:",
      JSON.stringify(pageContext, null, 2),
      "",
      history ? `Recent chat:\n${history}\n` : "",
      `User question: ${userMessage}`,
    ].filter(Boolean).join("\n");

    const response = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key=${encodeURIComponent(resolvedApiKey)}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        contents: [{ role: "user", parts: [{ text: prompt }] }],
        generationConfig: {
          temperature: 0.2,
          maxOutputTokens: 300,
        },
      }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(String(data?.error?.message || `HTTP ${response.status}`));
    }
    const text = ((data?.candidates || [])[0]?.content?.parts || [])
      .map((part) => String(part?.text || ""))
      .join("\n")
      .trim();
    if (!text) throw new Error("Gemini returned an empty reply.");
    return text;
  }

  async function saveHostMemory({ hostname, pageContext, storageSet }) {
    const summary = classifyPageContext(pageContext);
    if (
      !hostname ||
      !summary?.type ||
      (/no PDF found/i.test(summary.type) &&
        !pageContext?.pdfLinks?.length &&
        !pageContext?.iframes?.length &&
        !pageContext?.images?.length &&
        !pageContext?.hasGoogleDrive &&
        !pageContext?.hasFacebook &&
        !pageContext?.hasMcnLive)
    ) {
      return null;
    }
    const payload = {
      type: summary.type,
      steps_summary: summary.stepsSummary,
      last_used: new Date().toISOString(),
      confirmed: false,
    };
    await _storageSet({ [memoryKey(hostname)]: payload }, storageSet);
    return payload;
  }

  globalThis.PhAiHelp = {
    memoryKey,
    classifyPageContext,
    gatherPageContextFromCurrentPage,
    gatherPageContextFromBestTab,
    askGemini,
    saveHostMemory,
  };
})();
