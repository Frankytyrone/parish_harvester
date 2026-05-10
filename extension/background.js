const SCRIPTABLE_PROTOCOLS = new Set(["http:", "https:"]);

function _tabUrlIsScriptable(url) {
  if (!url || typeof url !== "string") return false;
  try {
    return SCRIPTABLE_PROTOCOLS.has(new URL(url).protocol);
  } catch (_err) {
    return false;
  }
}

async function _sendMessageToTab(tabId, message) {
  try {
    await chrome.tabs.sendMessage(tabId, message);
    return { ok: true };
  } catch (err) {
    return { ok: false, error: String(err) };
  }
}

async function _injectTrainerScripts(tabId) {
  try {
    await chrome.scripting.executeScript({
      target: { tabId },
      files: ["isolated.js"],
      world: "ISOLATED",
    });
    await chrome.scripting.executeScript({
      target: { tabId },
      files: ["content.js"],
      world: "MAIN",
    });
    return { ok: true };
  } catch (err) {
    return { ok: false, error: String(err) };
  }
}

async function sendToTab(tabId, message, options = {}) {
  const { allowInject = true } = options;
  if (!tabId) {
    return { ok: false, reason: "no_tab_id", error: "No tab ID supplied." };
  }

  let tab;
  try {
    tab = await chrome.tabs.get(tabId);
  } catch (err) {
    return { ok: false, reason: "tab_not_found", error: String(err) };
  }

  if (!_tabUrlIsScriptable(tab?.url || "")) {
    return {
      ok: false,
      reason: "unsupported_url",
      error: "Active tab is not a regular http/https page.",
      tabUrl: tab?.url || "",
    };
  }

  const firstAttempt = await _sendMessageToTab(tabId, message);
  if (firstAttempt.ok) {
    return { ok: true, route: "direct" };
  }

  if (!allowInject) {
    return {
      ok: false,
      reason: "receiver_unavailable",
      error: firstAttempt.error || "Could not reach page receiver.",
      tabUrl: tab?.url || "",
    };
  }

  const injected = await _injectTrainerScripts(tabId);
  if (!injected.ok) {
    return {
      ok: false,
      reason: "inject_failed",
      error: injected.error || "Failed to inject extension scripts.",
      tabUrl: tab?.url || "",
    };
  }

  const secondAttempt = await _sendMessageToTab(tabId, message);
  if (secondAttempt.ok) {
    return { ok: true, route: "reinject" };
  }

  return {
    ok: false,
    reason: "receiver_unavailable",
    error: secondAttempt.error || "Content script did not receive message.",
    tabUrl: tab?.url || "",
  };
}

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.removeAll(() => {
    chrome.contextMenus.create({
      id: "mark-bulletin-image",
      title: "Mark as Bulletin Image",
      contexts: ["image"],
    });
  });
});

chrome.contextMenus.onClicked.addListener((info, tab) => {
  if (info.menuItemId === "mark-bulletin-image" && tab?.id) {
    void sendToTab(tab.id, {
      type: "mark_image",
      url: info.srcUrl,
    });
  }
});

chrome.action.onClicked.addListener((tab) => {
  if (!tab?.id) {
    return;
  }
  void sendToTab(tab.id, { type: "toggle_toolbar" });
});


chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type !== "dispatch_to_tab") return false;
  (async () => {
    const tabId = Number(message.tabId || 0);
    const payload = message.payload || {};
    const allowInject = message.allowInject !== false;
    const result = await sendToTab(tabId, payload, { allowInject });
    sendResponse(result);
  })().catch((err) => {
    sendResponse({
      ok: false,
      reason: "dispatch_error",
      error: String(err),
    });
  });
  return true;
});

// ── GitHub recipe push ────────────────────────────────────────────────────
//
// Handles "push_recipe" messages from content.js / sidepanel.js.
// Reads the stored GitHub PAT and repo from chrome.storage.local, then
// creates or updates the recipe file via the GitHub Contents API.
//
// Required storage keys:
//   gh_pat   — personal access token with repo write scope
//   gh_repo  — owner/repo  (e.g. "Frankytyrone/parish_harvester")
//
// Message shape:
//   { type: "push_recipe", parish_key: string, recipe: object }
//
// Reply shape (sent back via sendResponse):
//   { ok: true,  url: string }   — on success
//   { ok: false, error: string } — on failure

// ── Generic GitHub file fetch ─────────────────────────────────────────────
//
// Message shape: { type: "fetch_github_file", path: string }
// Reply:         { ok: true, content: string } | { ok: false, error: string }

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type !== "fetch_github_file") return false;

  (async () => {
    try {
      const { gh_pat, gh_repo } = await chrome.storage.local.get(["gh_pat", "gh_repo"]);
      if (!gh_pat || !gh_repo) {
        sendResponse({ ok: false, error: "GitHub PAT or repo not configured." });
        return;
      }
      const apiUrl = `https://api.github.com/repos/${gh_repo}/contents/${message.path}`;
      const resp = await fetch(apiUrl, {
        headers: {
          Authorization: `token ${gh_pat}`,
          Accept: "application/vnd.github+json",
          "X-GitHub-Api-Version": "2022-11-28",
        },
      });
      if (!resp.ok) {
        sendResponse({ ok: false, error: `GitHub ${resp.status}: ${resp.statusText}` });
        return;
      }
      const data = await resp.json();
      // content is base64-encoded by GitHub API
      const decoded = decodeURIComponent(
        atob(data.content.replace(/\n/g, ""))
          .split("")
          .map((c) => "%" + ("00" + c.charCodeAt(0).toString(16)).slice(-2))
          .join("")
      );
      sendResponse({ ok: true, content: decoded, sha: data.sha });
    } catch (err) {
      sendResponse({ ok: false, error: String(err) });
    }
  })();

  return true;
});

// ── Generic GitHub file push ──────────────────────────────────────────────
//
// Message shape:
//   { type: "push_github_file", path: string, content: string, commitMessage: string }
// Reply: { ok: true, url: string } | { ok: false, error: string }

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type !== "push_github_file") return false;

  (async () => {
    try {
      const { gh_pat, gh_repo } = await chrome.storage.local.get(["gh_pat", "gh_repo"]);
      if (!gh_pat || !gh_repo) {
        sendResponse({ ok: false, error: "GitHub PAT or repo not configured." });
        return;
      }

      const filePath = (message.path || "").trim();
      if (!filePath) { sendResponse({ ok: false, error: "No file path provided." }); return; }

      const apiBase = `https://api.github.com/repos/${gh_repo}/contents/${filePath}`;
      const headers = {
        Authorization: `token ${gh_pat}`,
        Accept: "application/vnd.github+json",
        "Content-Type": "application/json",
        "X-GitHub-Api-Version": "2022-11-28",
      };

      // Get current SHA (for updates)
      let existingSha = null;
      try {
        const getResp = await fetch(apiBase, { headers });
        if (getResp.ok) { existingSha = (await getResp.json()).sha || null; }
      } catch (_e) { /* new file */ }

      const encoded = btoa(unescape(encodeURIComponent(message.content || "")));
      const body = {
        message: message.commitMessage || `update ${filePath} [from extension]`,
        content: encoded,
        ...(existingSha ? { sha: existingSha } : {}),
      };

      const putResp = await fetch(apiBase, { method: "PUT", headers, body: JSON.stringify(body) });
      if (!putResp.ok) {
        const err = await putResp.json().catch(() => ({}));
        sendResponse({ ok: false, error: `GitHub API error ${putResp.status}: ${err.message || putResp.statusText}` });
        return;
      }

      const result = await putResp.json();
      sendResponse({ ok: true, url: result?.content?.html_url || `https://github.com/${gh_repo}/blob/main/${filePath}` });
    } catch (err) {
      sendResponse({ ok: false, error: String(err) });
    }
  })();

  return true;
});

// ── Recipe push ───────────────────────────────────────────────────────────

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type !== "push_recipe") return false;

  (async () => {
    try {
      const { gh_pat, gh_repo } = await chrome.storage.local.get(["gh_pat", "gh_repo"]);
      if (!gh_pat || !gh_repo) {
        sendResponse({ ok: false, error: "GitHub PAT or repo not configured. Open the extension sidepanel → ⚙️ Settings." });
        return;
      }

      const key = (message.parish_key || "").trim();
      if (!key) {
        sendResponse({ ok: false, error: "No parish_key provided." });
        return;
      }

      const filePath = `parishes/recipes/${key}.json`;
      const apiBase  = `https://api.github.com/repos/${gh_repo}/contents/${filePath}`;
      const headers  = {
        Authorization: `token ${gh_pat}`,
        Accept: "application/vnd.github+json",
        "Content-Type": "application/json",
        "X-GitHub-Api-Version": "2022-11-28",
      };

      // Fetch existing file SHA (needed for updates)
      let existingSha = null;
      try {
        const getResp = await fetch(apiBase, { headers });
        if (getResp.ok) {
          const existing = await getResp.json();
          existingSha = existing.sha || null;
        }
      } catch (_e) { /* file does not exist yet — that's fine */ }

      const recipeJson = JSON.stringify(message.recipe, null, 2);
      const encoded    = btoa(unescape(encodeURIComponent(recipeJson)));

      const body = {
        message: `recipe: ${existingSha ? "update" : "add"} ${key} [from extension]`,
        content: encoded,
        ...(existingSha ? { sha: existingSha } : {}),
      };

      const putResp = await fetch(apiBase, {
        method: "PUT",
        headers,
        body: JSON.stringify(body),
      });

      if (!putResp.ok) {
        const err = await putResp.json().catch(() => ({}));
        sendResponse({ ok: false, error: `GitHub API error ${putResp.status}: ${err.message || putResp.statusText}` });
        return;
      }

      const result = await putResp.json();
      const htmlUrl = result?.content?.html_url || `https://github.com/${gh_repo}/blob/main/${filePath}`;
      sendResponse({ ok: true, url: htmlUrl });
    } catch (err) {
      sendResponse({ ok: false, error: String(err) });
    }
  })();

  return true; // keep message channel open for async response
});
