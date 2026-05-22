# Set up `bulletins.parishpress.net` (simple steps)

This adds a **new subdomain** for bulletins only.
It does **not** change your main Divi website at `parishpress.net`.

## Step 1 — Add one DNS record at your domain registrar

For domain: `parishpress.net`

Create exactly this record:

- **Type:** `CNAME`
- **Host/Name:** `bulletins`
- **Value/Target:** `frankytyrone.github.io`
- **TTL:** default

## Step 2 — Confirm in GitHub Pages settings

Open:
`https://github.com/Frankytyrone/parish_harvester/settings/pages`

Then:

1. Check that **Custom domain** shows `bulletins.parishpress.net`
2. Once status turns green, tick **Enforce HTTPS**

## Step 3 — Wait for DNS + certificate

DNS and HTTPS setup can take up to 24 hours.

Don't panic if GitHub shows a warning for a few hours — that is normal while DNS propagates.

---

## Important note

`parishpress.ie` already redirects to `parishpress.net`.
Leave that as-is. No changes needed there.
