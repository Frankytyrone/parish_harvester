chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: "mark-bulletin-image",
    title: "Mark as Bulletin Image",
    contexts: ["image"],
  });
});

chrome.contextMenus.onClicked.addListener((info, tab) => {
  if (info.menuItemId === "mark-bulletin-image" && tab?.id) {
    chrome.tabs.sendMessage(tab.id, {
      type: "mark_image",
      url: info.srcUrl,
    });
  }
});

chrome.action.onClicked.addListener((tab) => {
  if (!tab?.id) {
    return;
  }
  chrome.tabs.sendMessage(tab.id, { type: "toggle_toolbar" });
});

// Automatically show the toolbar when a page finishes loading.
// content.js will only display it when Playwright training bindings are
// present, so this does not affect normal browsing sessions.
chrome.tabs.onUpdated.addListener((tabId, changeInfo) => {
  if (changeInfo.status === "complete") {
    chrome.tabs.sendMessage(tabId, { type: "show_toolbar" }).catch(() => {});
  }
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
