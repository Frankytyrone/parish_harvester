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
    const response = await chrome.tabs.sendMessage(tabId, message);
    if (response && typeof response === "object") {
      return response;
    }
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
    return { ...firstAttempt, route: "direct" };
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
    return { ...secondAttempt, route: "reinject" };
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

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type !== "lookup_parish_for_url") return false;
  (async () => {
    try {
      const url = String(message.url || "").trim();
      const hostname = (() => {
        try {
          return new URL(url).hostname.toLowerCase();
        } catch (_e) {
          return "";
        }
      })();
      if (!hostname) {
        sendResponse({ ok: false });
        return;
      }
      const { ph_hostname_map } = await chrome.storage.local.get(["ph_hostname_map"]);
      const parish = ph_hostname_map && typeof ph_hostname_map === "object"
        ? ph_hostname_map[hostname]
        : null;
      if (!parish) {
        sendResponse({ ok: false });
        return;
      }
      sendResponse({ ok: true, parish });
    } catch (_e) {
      sendResponse({ ok: false });
    }
  })();
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

const _githubApiError = async (resp) => {
  try {
    const body = await resp.json();
    const msg = body.message || resp.statusText;
    if (resp.status === 401) return `GitHub authentication failed — your Personal Access Token may be invalid or expired. Open Settings and re-enter it. (${msg})`;
    if (resp.status === 403) return `GitHub access denied — your PAT may lack 'repo' write scope. Open Settings and check permissions. (${msg})`;
    if (resp.status === 404) return `Repository not found — check the repo name in Settings (expected format: owner/repo). (${msg})`;
    if (resp.status === 409) return `GitHub conflict (${resp.status}): ${msg} — reload the extension and try again.`;
    if (resp.status === 422) return `GitHub validation error: ${msg}`;
    return `GitHub API error ${resp.status}: ${msg}`;
  } catch (_e) {
    return `GitHub API error ${resp.status}: ${resp.statusText}`;
  }
};

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type !== "push_recipe") return false;

  (async () => {
    try {
      const { gh_pat, gh_repo } = await chrome.storage.local.get(["gh_pat", "gh_repo"]);
      if (!gh_pat || !gh_repo) {
        sendResponse({ ok: false, error: "GitHub PAT or repo not configured. Open the extension popup → ⚙️ Settings and enter your PAT and repo." });
        return;
      }

      const key = (message.parish_key || "")
        .trim()
        .toLowerCase()
        .replace(/\s+/g, "_");
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

      // Fetch existing file SHA (needed for updates) and existing recipe.
      let existingSha = null;
      let existingRecipe = null;
      try {
        const getResp = await fetch(apiBase, { headers });
        if (getResp.ok) {
          const existing = await getResp.json();
          existingSha = existing.sha || null;
          try {
            const decoded = decodeURIComponent(
              atob(existing.content.replace(/\n/g, ""))
                .split("")
                .map((c) => "%" + ("00" + c.charCodeAt(0).toString(16)).slice(-2))
                .join("")
            );
            existingRecipe = JSON.parse(decoded);
          } catch (_parseErr) { /* use new recipe as-is */ }
        } else if (getResp.status !== 404) {
          // Non-404 failure fetching the existing file — warn but proceed (treat as new).
          console.warn(`Parish Trainer: could not check existing recipe (${getResp.status})`);
        }
      } catch (_e) { /* file does not exist yet — that's fine */ }

      // Preserve stable fields from the existing recipe when updating.
      const incoming = message.recipe || {};
      const recipe = existingRecipe ? {
        ...existingRecipe,
        // Always overwrite with the freshly-recorded steps and metadata.
        ...incoming,
        // Keep the original display_name / diocese unless the new one is non-empty.
        display_name: (incoming.display_name && incoming.display_name.trim()) ? incoming.display_name.trim() : existingRecipe.display_name,
        diocese:      (incoming.diocese      && incoming.diocese.trim())      ? incoming.diocese.trim()      : existingRecipe.diocese,
      } : incoming;

      // Set recorded_date to today.
      recipe.recorded_date = new Date().toISOString().slice(0, 10);
      recipe.parish_key = key;
      const recipeDiocese = (recipe.diocese || "").trim();

      const recipeJson = JSON.stringify(recipe, null, 2);
      const encoded    = btoa(unescape(encodeURIComponent(recipeJson)));

      const body = {
        message: `chore: update recipe for ${key} [${recipeDiocese || "unknown diocese"}]`,
        content: encoded,
        ...(existingSha ? { sha: existingSha } : {}),
      };

      const putResp = await fetch(apiBase, {
        method: "PUT",
        headers,
        body: JSON.stringify(body),
      });

      if (!putResp.ok) {
        sendResponse({ ok: false, error: await _githubApiError(putResp) });
        return;
      }

      const result = await putResp.json();
      const htmlUrl = result?.content?.html_url || `https://github.com/${gh_repo}/blob/main/${filePath}`;

      // After saving the recipe, immediately trigger a workflow_dispatch so
      // the Mega PDF is rebuilt for just this parish right away.
      let dispatchOk = false;
      let dispatchError = "";
      try {
        const dispatchResp = await fetch(
          `https://api.github.com/repos/${gh_repo}/actions/workflows/harvest.yml/dispatches`,
          {
            method: "POST",
            headers: {
              Authorization: `token ${gh_pat}`,
              Accept: "application/vnd.github+json",
              "Content-Type": "application/json",
              "X-GitHub-Api-Version": "2022-11-28",
            },
            body: JSON.stringify({
              ref: "main",
              inputs: {
                diocese: "all",
                target_parish: key,
              },
            }),
          }
        );
        dispatchOk = dispatchResp.status === 204;
        if (!dispatchOk) {
          if (dispatchResp.status === 403) {
            dispatchError = "Your GitHub PAT is missing the 'workflow' scope. Go to github.com/settings/tokens, click your token, tick the 'workflow' checkbox, then regenerate and save it in the extension settings.";
          } else {
            dispatchError = await _githubApiError(dispatchResp);
          }
        }
      } catch (dispatchErr) {
        dispatchError = String(dispatchErr);
      }

      sendResponse({
        ok: true,
        url: htmlUrl,
        filePath,
        updated: !!existingSha,
        dispatchOk,
        dispatchError,
      });
    } catch (err) {
      sendResponse({ ok: false, error: `Unexpected error: ${String(err)}. Try reloading the extension.` });
    }
  })();

  return true; // keep message channel open for async response
});
