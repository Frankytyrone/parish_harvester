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
