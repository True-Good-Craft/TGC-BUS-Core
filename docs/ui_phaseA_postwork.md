# UI Phase A Post-Work Summary

## Completed Phase A Changes
- Centralized UI network authority so direct `fetch()` usage is constrained to the network subsystem (`api.js` + `token.js`).
- Relocated the global fetch wrapper install into `token.js` so network behavior is initialized from the token/network layer.
- Removed legacy inventory run wiring and aligned inventory mutations to canonical movement endpoints.
- Hardened quantity contract usage for mutation paths to `quantity_decimal` + explicit `uom`.
- Removed silent payload `uom: 'ea'` fallback patterns in key inventory/manufacturing submit paths and added fail-closed guards.
- Removed inventory UI fallback reliance on legacy `item?.qty` prefill.
- Removed inventory batch-details dependence on legacy integer fields (`remaining_int`/`original_int`) and parse-int reconstruction.

## Pre-Smoke Gate
1. `./scripts/ui_contract_audit.sh`
2. `./scripts/ui_phaseA_structural_guard.sh`
- Both scripts must PASS before manual smoke.
- If either FAILs, fix the reported violations; do not proceed.

## Manual Smoke Checklist
- Inventory adjustments: run +5 and -2 paths.
- Inventory stock-out: test `sold` and `other` reasons.
- Refund flow: test restock off and restock on (including required restock cost behavior).
- Manufacturing: test Run Production happy path and missing-uom guard behavior.
- Navigation/reload sanity: bounce `#/home` ↔ `#/inventory` ↔ `#/manufacturing` and reload.

## Known Non-Scope / Phase B
- index.html is a redirect stub; legacy router.js is disabled by default; shell/app.js is routing authority.
- Conversion wrapper logic remains in place by design for this phase.
- Conversion purge/refinement is explicitly deferred to Phase B.
