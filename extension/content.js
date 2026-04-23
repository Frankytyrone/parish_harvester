const existingHost = document.getElementById('ph-training-host');
if (existingHost) existingHost.remove();

const cssPath = (el) => {
  if (!el || el.nodeType !== Node.ELEMENT_NODE) return '';
  const parts = [];
  let current = el;
  while (current && current.nodeType === Node.ELEMENT_NODE && parts.length < 6) {
    let selector = current.tagName.toLowerCase();
    if (current.id) {
      selector += '#' + current.id;
      parts.unshift(selector);
      break;
    }
    const parent = current.parentElement;
    if (parent) {
      const siblings = Array.from(parent.children).filter(c => c.tagName === current.tagName);
      if (siblings.length > 1) {
        selector += `:nth-of-type(${siblings.indexOf(current) + 1})`;
      }
    }
    parts.unshift(selector);
    current = current.parentElement;
  }
  return parts.join(' > ');
};

const host = document.createElement('div');
host.id = 'ph-training-host';
host.style.cssText = 'all:initial!important;position:fixed!important;right:12px!important;top:12px!important;z-index:2147483647!important;width:auto!important;height:auto!important;pointer-events:none!important;';
document.documentElement.appendChild(host);
const shadow = host.attachShadow({ mode: 'open' });
shadow.innerHTML = `
  <style>
    #ph-training-panel {
      position: relative;
      right: auto;
      top: auto;
      z-index: 2147483647;
      background: #111827;
      color: #f9fafb;
      padding: 10px 12px;
      border-radius: 10px;
      box-shadow: 0 8px 28px rgba(0,0,0,.35);
      font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif;
      font-size: 12px;
      max-width: 310px;
      pointer-events: auto;
    }
    #ph-title {
      font-weight: 700;
      margin-bottom: 6px;
    }
    #status {
      opacity: .92;
      margin-bottom: 8px;
      line-height: 1.35;
    }
    #ph-row {
      display: flex;
      gap: 6px;
      flex-wrap: wrap;
    }
    .ph-btn {
      border: none;
      border-radius: 8px;
      padding: 6px 8px;
      background: #2563eb;
      color: #fff;
      cursor: pointer;
      font-size: 12px;
    }
    #ph-training-image-menu {
      position: fixed;
      display: none;
      z-index: 2147483647;
      background: #111827;
      color: #f9fafb;
      border-radius: 8px;
      box-shadow: 0 8px 28px rgba(0,0,0,.35);
      padding: 6px 0;
      font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif;
      font-size: 12px;
      min-width: 210px;
      pointer-events: auto;
    }
    #mark-image-item {
      display: block;
      width: 100%;
      text-align: left;
      border: none;
      background: transparent;
      color: #f9fafb;
      padding: 8px 10px;
      cursor: pointer;
    }
  </style>
  <div id="ph-training-panel">
    <div id="ph-title">Parish Trainer</div>
    <div id="status">Right-click an image to mark bulletin image.</div>
    <div id="ph-row">
      <button id="html-btn" type="button" class="ph-btn">Mark Page as HTML</button>
      <button id="file-btn" type="button" class="ph-btn">Mark Current URL as File</button>
    </div>
  </div>
  <div id="ph-training-image-menu">
    <button id="mark-image-item" type="button">🖼️ Mark as Bulletin Image</button>
  </div>
`;

const status = shadow.getElementById('status');
const menu = shadow.getElementById('ph-training-image-menu');
const markImageItem = shadow.getElementById('mark-image-item');

shadow.getElementById('html-btn').addEventListener('click', () => {
  const url = window.location.href;
  window.ph_mark_html({ url });
  status.textContent = 'Marked HTML: ' + url;
});
shadow.getElementById('file-btn').addEventListener('click', () => {
  const url = window.location.href;
  window.ph_mark_download_url({ url });
  status.textContent = 'Marked file: ' + url;
});

let menuImage = null;
const closeMenu = () => {
  menu.style.display = 'none';
  menuImage = null;
};

markImageItem.addEventListener('click', () => {
  if (!menuImage) return;
  const raw = menuImage.currentSrc || menuImage.getAttribute('src') || '';
  if (!raw) return;
  const url = new URL(raw, window.location.href).href;
  window.ph_mark_image({ url });
  status.textContent = 'Marked image: ' + url;
  closeMenu();
});

document.addEventListener('contextmenu', (event) => {
  const target = event.target instanceof Element ? event.target.closest('img') : null;
  if (!target) {
    closeMenu();
    return;
  }
  event.preventDefault();
  menuImage = target;
  menu.style.left = `${event.clientX}px`;
  menu.style.top = `${event.clientY}px`;
  menu.style.display = 'block';
}, true);

document.addEventListener('click', () => closeMenu(), true);
window.addEventListener('scroll', () => closeMenu(), true);

document.addEventListener('click', (event) => {
  const target = event.target instanceof Element
    ? event.target.closest('a,button,[role],input[type="submit"],input[type="button"]')
    : null;
  if (!target) return;
  if (target.getRootNode() === shadow) {
    return;
  }
  window.ph_record_click({
    tag: (target.tagName || '').toLowerCase(),
    role: (target.getAttribute('role') || '').toLowerCase(),
    text: (target.innerText || target.textContent || '').trim().slice(0, 200),
    href: target.getAttribute('href') || '',
    css_path: cssPath(target),
  });
}, true);
