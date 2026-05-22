# AI Conversation Log — 2026-05-22 (Bundle B: Smarter Harvest)

## Date / Login / Repo
2026-05-22 — `Frankytyrone` — `Frankytyrone/parish_harvester`

## Brutally honest summary (real fix vs workaround)
- **Real fix:** HTML-only bulletin pages now get one last Playwright render-to-PDF attempt before the harvester gives up and records a plain `html_link`.
- **Real fix:** Pages with multiple bulletin images can now be assembled into one A4 multi-page PDF, including lazy-loaded images fetched through the live Playwright page when available.
- **Real fix:** Slow hosts can now use longer navigation timeouts and more retries without slowing every other parish down.
- **Workaround caveat:** HTML render fallback still only helps if the page itself is printable without login, bot protection, or hard browser errors.
- **Workaround caveat:** Image fallback still depends on the page exposing real image URLs in the DOM after load; if a site hides them behind custom JS/XHR tricks, this may still miss.

## Files changed
- `harvester/fetcher.py`
- `harvester/replay.py`
- `parishes/host_profiles.json`
- `test_html_render_fallback.py`
- `test_image_pdf_pipeline.py`
- `test_host_profiles.py`
- `ai_conversations/2026-05-22-bundle-b-smarter-harvest.md`

## Expected impact
- **HTML render fallback:** Three Patrons / Holy Rosary Belfast / St Agnes Belfast should stop ending up as summary links when the bulletin page itself is printable.
- **Image → PDF pipeline:** Derriaghy should benefit when the bulletin is exposed as multiple page images instead of one direct PDF.
- **Per-host timeout profiles:** Ballyclare and Ballygowan / Kilmore and Killyleagh / Portstewart should get more breathing room before the harvester gives up.

## What this will NOT fix
- DNS-dead hosts.
- Hard SSL failures.
- Sites that require login or interactive anti-bot checks.
- Pages that render blank content even when Playwright prints them.
- Bulletin images that are never exposed to the browser as normal image URLs.

## Caveats
- HTML render fallback is gated by per-recipe opt-out (`disable_html_render_fallback`). No existing recipe files were changed.
- Image fallback is gated by per-recipe opt-out (`disable_image_pdf_fallback`). No existing recipe files were changed.
- Host profiles only tune timeout length / retry count / wait-after-load. They do **not** change which failures qualify for a retry.

## Hand-off note for next AI
Next bundle = PR-C (Problems dashboard + AI chatbot + learning memory)
