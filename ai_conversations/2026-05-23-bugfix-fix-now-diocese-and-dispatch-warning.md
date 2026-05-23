## Bugfix summary (2026-05-23)

- Updated `extension/sidepanel.js` in `_problemsRenderRows()` so **Fix now** now looks up `row.parish` in `_pdAllParishes` and writes:
  - `chrome.storage.local.set({ ph_training_parish: { key, name, diocese } })`
  before opening the tab. This ensures recipe saves land in the correct diocese folder instead of `parishes/recipes/unknown/`.

- Updated `_pdDispatchHarvest()` caller messaging in `extension/sidepanel.js` so dispatch-trigger failure after a successful recipe save is shown as a **warning** (amber), not a red error. New message clarifies separation:
  - `Recipe saved OK. Harvest trigger failed — check GitHub token has workflow scope.`

- Added amber warning style in `extension/sidepanel.html` via `#status.warn` to support the new warning status.
