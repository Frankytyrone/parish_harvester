# AI Conversation Log — 2026-05-22 (Bundle A: Truth & Cleanup)

## Date / Login / Repo
2026-05-22 — `Frankytyrone` — `Frankytyrone/parish_harvester`

## Brutally honest summary (real fix vs workaround)
- **Real fix:** Extension success states now require explicit confirmation (`ok:true`) instead of defaulting to green success when results are missing/ambiguous.
- **Real fix:** Dead-website marking now waits for a confirmed round-trip response and fails visibly (with reason) on timeout/error.
- **Real fix:** Popup/sidepanel settings save now shows explicit red failure when Chrome storage reports an error.
- **Real fix:** Diagnostics ping now demands strict compatibility (`{ok:true,pong:true}`), so wrong/outdated page scripts no longer appear healthy.
- **Real fix:** DNS-dead parishes are marked inactive in recipes so fetcher skip logic can stop wasting attempts.
- **Cleanup only:** `parishes/recipes/unknown/` duplicate files were removed where diocesan copies already exist.
- **Workaround caveat:** Diagnostics still sends a legacy `ping` call before strict `ph_ping` for compatibility; only strict `ph_ping` now controls pass/fail.

## Files changed
- `extension/background.js`
- `extension/content.js`
- `extension/popup.js`
- `extension/sidepanel.js`
- `extension/isolated.js`
- `parishes/recipes/derry/parishofstjohncoleraine.json`
- `parishes/recipes/derry/urneyandcastlefinparish.json`
- `parishes/recipes/down_and_connor/corpuschristiparishbelfast.json`
- `parishes/recipes/down_and_connor/drumbocarryduff.json`
- `parishes/recipes/down_and_connor/holytrinityparishbelfast.json`
- `parishes/recipes/down_and_connor/stlukesparishbelfast.json`
- `parishes/recipes/down_and_connor/stvincentdepaulparishbelfast.json`
- Deleted duplicate files in `parishes/recipes/unknown/` (14 files)

## Fix 2 — Parishes marked inactive (with exact error strings)
1. `parishofstjohncoleraine` — `Website DNS no longer resolves (parishofstjohncoleraine.com).`
2. `urneyandcastlefinparish` — `Website DNS no longer resolves (urneyandcastlefinparish.com).`
3. `corpuschristiparishbelfast` — `Website DNS no longer resolves (corpuschristiparishbelfast.com).`
4. `drumbocarryduff` — `Website DNS no longer resolves (drumbocarryduff.ie).`
5. `holytrinityparishbelfast` — `Website DNS no longer resolves (holytrinityparishbelfast.com).`
6. `stlukesparishbelfast` — `Website DNS no longer resolves (stlukesparishbelfast.com).`
7. `stvincentdepaulparishbelfast` — `Website DNS no longer resolves (stvincentdepaulparishbelfast.com).`

Added keys for each:
- `"status": "inactive"`
- `"inactive_reason": "DNS dead (no such domain)"`
- `"inactive_marked": "2026-05-22"`

## Fix 3 — unknown/ duplicate cleanup
- **Before:** 30 files in `parishes/recipes/unknown/`
- **After:** 16 files
- **Deleted as confirmed duplicates:** 14 files (diocesan copy exists and is source of truth)

### unknown/ files retained (still need a diocese assigned — TODO for Franky)
- `carndonaghparish.json`
- `castledergparish.json`
- `clonmanyparish.json`
- `culdaffparish.json`
- `culmoreparish.json`
- `dmaparish.json`
- `drumquinparish.json`
- `errigalparish.json`
- `fahanparish.json`
- `greenlough.json`
- `iskaheenparish.json`
- `laveyparish.json`
- `leckpatrickparish.json`
- `magheraparishderry.json`
- `parishofdungiven.json`
- `parishofkilrea.json`

## Hand-off note for next AI
Next bundle = PR-B (smarter harvest)
