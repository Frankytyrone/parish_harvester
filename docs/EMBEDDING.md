# Embedding Parish Bulletins (Copy/Paste)

## What this gives you
Paste these snippets into any website. They will always show the latest bulletins automatically.

## Snippet A — Single mega PDF (simplest)
```html
<iframe
  src="https://frankytyrone.github.io/parish_harvester/mega_pdf/derry_mega_bulletin.pdf"
  width="100%"
  height="900"
  style="border:0"
  title="Derry mega bulletin">
</iframe>
```
Note: change `derry` to `down_and_connor` for the other diocese.

## Snippet B — PDF with download fallback
```html
<object
  data="https://frankytyrone.github.io/parish_harvester/mega_pdf/derry_mega_bulletin.pdf"
  type="application/pdf"
  width="100%"
  height="900">
  <p>
    PDF preview not supported on this device/browser.
    <a href="https://frankytyrone.github.io/parish_harvester/mega_pdf/derry_mega_bulletin.pdf">Download the latest bulletin</a>.
  </p>
</object>
```

## Snippet C — OCR viewer embed (text-searchable)
```html
<iframe
  src="https://frankytyrone.github.io/parish_harvester/bulletins/derry-latest.html"
  width="100%"
  height="1000"
  style="border:0"
  title="Derry OCR viewer">
</iframe>
```
⚠️ Caveat: `derry-latest.html` does **not** exist yet (OCR pages are dated files like `derry-YYYY-MM-DD.html`). If you need a stable auto-updating URL now, use Snippet D or Snippet E.

## Snippet D — Auto-updating link via the manifest (recommended)
```html
<a id="latest-bulletin-link" href="#">Loading latest bulletin…</a>
<script>
fetch('https://frankytyrone.github.io/parish_harvester/manifest.json')
  .then((r) => r.json())
  .then((m) => {
    const d = m.dioceses.derry_diocese;
    if (!d || !d.mega_pdf) return;
    const a = document.getElementById('latest-bulletin-link');
    a.href = d.mega_pdf;
    a.textContent = `Open latest ${d.display_name} bulletin (${m.target_date})`;
  })
  .catch(() => {
    const a = document.getElementById('latest-bulletin-link');
    a.textContent = 'Could not load bulletin link right now.';
  });
</script>
```

## Snippet E — Auto-updating iframe
```html
<iframe id="latest-bulletin-frame" width="100%" height="900" style="border:0" title="Latest bulletin"></iframe>
<script>
fetch('https://frankytyrone.github.io/parish_harvester/manifest.json')
  .then((r) => r.json())
  .then((m) => {
    const d = m.dioceses.derry_diocese;
    if (!d || !d.mega_pdf) return;
    document.getElementById('latest-bulletin-frame').src = d.mega_pdf;
  });
</script>
```

## Snippet F — CDN URL alternative (jsDelivr)
Use the same mega PDF pattern on jsDelivr:

- `https://cdn.jsdelivr.net/gh/Frankytyrone/parish_harvester@main/mega_pdf/derry_mega_bulletin.pdf`
- `https://cdn.jsdelivr.net/gh/Frankytyrone/parish_harvester@main/mega_pdf/down_and_connor_mega_bulletin.pdf`

Honest caveat: jsDelivr can cache for up to 7 days. Use the Pages manifest URL (`manifest.json`) when freshness matters most.

## Manifest endpoint reference
Endpoint:

- `https://frankytyrone.github.io/parish_harvester/manifest.json`

Schema:

```json
{
  "generated_at": "2026-05-22T10:00:00Z",
  "target_date": "2026-05-22",
  "dioceses": {
    "derry_diocese": {
      "display_name": "Derry Diocese",
      "mega_pdf": "https://frankytyrone.github.io/parish_harvester/mega_pdf/derry_mega_bulletin.pdf",
      "mega_pdf_cdn": "https://cdn.jsdelivr.net/gh/Frankytyrone/parish_harvester@main/mega_pdf/derry_mega_bulletin.pdf",
      "ocr_viewer": "https://frankytyrone.github.io/parish_harvester/bulletins/derry-2026-05-22.html",
      "downloaded": 32,
      "html_links": 8,
      "failed": 5,
      "success_rate": "86.5%"
    },
    "down_and_connor": {
      "display_name": "Down and Connor",
      "mega_pdf": "https://frankytyrone.github.io/parish_harvester/mega_pdf/down_and_connor_mega_bulletin.pdf",
      "mega_pdf_cdn": "https://cdn.jsdelivr.net/gh/Frankytyrone/parish_harvester@main/mega_pdf/down_and_connor_mega_bulletin.pdf",
      "ocr_viewer": "https://frankytyrone.github.io/parish_harvester/bulletins/down_and_connor-2026-05-22.html",
      "downloaded": 41,
      "html_links": 6,
      "failed": 4,
      "success_rate": "91.1%"
    }
  }
}
```

## Mobile note
PDF iframes are unreliable on iOS Safari. For mobile-heavy audiences, prefer Snippet B (object + direct download fallback).

## Update frequency
Bulletins refresh every Sunday after the GitHub Actions harvest completes. External sites using Snippet D/E usually see new content within ~10 minutes of publish.

## Caching note
GitHub Pages does not support per-file cache headers here, so `manifest.json` can be cached briefly. Expect up to ~10 minutes before fresh data is visible everywhere.

## Troubleshooting
- **Embed blocked on your site:** your page must be HTTPS. Browsers block mixed-content (`http://` host page embedding `https://` assets can still have related content issues).
- **Manifest fetch failing:** check browser console for network errors. GitHub Pages serves `manifest.json` directly (no special CORS setup needed for normal fetch usage).
- **Nothing appears in iframe/object:** confirm the URL is correct and opens directly in a browser tab first.
- **Still broken:** open browser DevTools Console and Network tabs, then reload and check for 404/blocked requests.
