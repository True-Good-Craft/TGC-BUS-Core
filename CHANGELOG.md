# Changelog

## [Unreleased]

### Added
- Introduced `internal_version` as a separate working-revision field in the canonical version source, initialized to `1.0.2.0`.

### Changed
- Preserved strict SemVer `version` for release/update surfaces while documenting owner-only `version` bumps and agent-only `internal_version` bumps.

## [0.11.1] - 2026-03-08

### Changed
- Bumped the core patch version from `0.11.0` to `0.11.1`.
- Added this changelog entry to summarize the version bump update.

## [1.0.0] - 2026-03-05

### Added
- First-run onboarding wizard
- Demo dataset environment
- EULA acceptance with scroll lock
- Inventory batch visualization
- Settings UI grouping
- Backup + restore

### Fixed
- Inventory quantity rendering
- Batch remaining/original display
- EULA file path resolution

### Notes
BUS Core v1.0.0 marks the first stable release of the local-first shop ERP system.
## [1.0.0] - 2026-03-04

BUS Core v1.0.0 establishes the platform as a **local-first manufacturing ledger kernel** with deterministic database behavior, onboarding workflow, and controlled update signaling.

This release marks the first stable version of BUS Core.

### Added

- Deterministic first-run onboarding wizard.
- Mandatory EULA acceptance gate during onboarding.
- Demo environment using a pre-seeded demo database.
- "Start Fresh Shop" action to transition from demo environment to production database.
- System runtime mode support (`demo` vs `production`).
- Settings-based update check (manual, opt-in).
- Semantic versioning for BUS Core releases.
- Public API contract documentation.

### Changed

- Canonical UI routing stabilized in `core/ui/app.js`.
- First-run logic now relies on backend `/app/system/state`.
- Initial database state detection standardized.

### Fixed

- Hash routing suppression bug causing the first click to be ignored.
- Wizard redirect logic when default route already present.

### Notes

BUS Core remains:

- Local-first
- Offline-capable
- Zero telemetry
- Deterministic database behavior

Future releases will prioritize stability, bug fixes, and incremental polish rather than feature expansion.

### Added
- Opt-in update check system with `/app/update/check` for manifest-based version checks and normalized six-field response surface.

### Security
- Hardened update manifest fetch path with deterministic SSRF guards, redirect rejection (`follow_redirects=False`), JSON-only validation, and streaming 64KB size cap enforcement.

### UX
- Settings now supports manual “Check now” with conditional Download action, plus optional startup update notice if explicitly opted-in (`updates.enabled && updates.check_on_startup`).
- launcher: open /ui/shell.html without a hash to preserve deterministic first-run onboarding routing.

### Tests
- Added/updated update-check coverage for streaming size cap enforcement, strict SemVer handling, manifest URL validation and SSRF cases, redirect/content-type behavior, and response contract key stability.
- Finance page (`#/finance`) with KPI summary and transaction history.

### API
- Added finance read endpoints: `/app/finance/summary` and `/app/finance/transactions`.

### Correctness
- Enforced sales aggregation barriers by `source_id` and stock-authority COGS derivation from sold stock movements.
- Added double-count guard regression test for repeated summary reads.

### Tests
- Added `tests/api/test_finance_double_count_guard.py` and expanded finance suite coverage across summary, transactions, stock-authority, and validation scenarios.

- First-run onboarding wizard (`#/welcome`) with deterministic backend boot probe.

### API
- Added `/app/system/state` for first-run detection and readiness reporting.

### UX
- Auto-launch onboarding only on clean DB; Settings button to re-run onboarding.

### Tests
- Added/updated `system_state` tests covering empty/non-empty/status and canonical failure envelope.

## [0.12.0] — 2026-03-04 — Finance Stabilization & Archive Model

### Added
- `items.is_archived` column (additive, non-breaking).
- Archive semantics for Items.
- Smoke isolation wrapper (`scripts/smoke_isolated.ps1`).

### Changed
- `DELETE /app/items/{id}` now archives items with history instead of returning `409`.
- `GET /app/items` excludes archived items by default.
- Optional `?include_archived=true` query parameter added for full item listings.

### Fixed
- Prevented orphaned finance history via hard delete path by archiving when history exists.
- Ensured smoke tests cannot mutate working database by forcing temporary `BUS_DB` in smoke wrapper.

### Security / Integrity
- Ledger invariants preserved.
- Finance remains fail-closed for missing Item resolution.

## [0.11.0] — 2026-02-25 — System Normalisation

### Added
- **Canonical Unit Model**: All inventory quantities are now stored as integer base units (milli-count `mc` for count dimension; `1 ea = 1000 mc`). The canonical helper `normalize_quantity_to_base_int()` is the single authority for all unit conversions. Hardcoded multipliers outside this helper are non-compliant.
- **Cost Authority Rule**: `unit_cost_cents` is always cost-per-human-unit (`item.uom`). Multiplying `unit_cost_cents` by base quantities directly is forbidden. General and manufacturing cost formulas now convert base→human before applying costs.
- **Recipes v2 Contract**: Recipe payloads accept and respond with v2 fields; legacy `qty_base` keys are rejected.
- **Ledger History v2 Response**: `/app/ledger/history` returns human-readable fields (`quantity_decimal`, `uom`) by default; raw base fields hidden unless `?include_base=true`.
- **Finance Refund v2 Contract**: Refund endpoint enforces v2 payload; legacy `qty_base` on refund is rejected.
- **API Governance Document**: Added `API_CONTRACT.md` as the authoritative API contract reference.
- **UI Deep-link Routing (Phase B)**:
  - `index.html` de-brained to a redirect stub; single SPA authority is `shell.html` / `app.js`.
  - Legacy `router.js` disabled by default.
  - `app.js`: `normalizeHash`, alias redirects (`#/dashboard→#/home`, `#/items→#/inventory`, `#/vendors→#/contacts`), `BUS_ROUTE` param capture, dedicated 404 page.
  - Deep-links for `#/inventory/<id>`, `#/contacts/<id>`, `#/recipes/<id>` (happy path + not-found redirect).
- **Inventory UX Polish**: Dimension-safe UOM dropdown filtering; remaining qty display without legacy int reconstruction; metadata-only save; warn-on-blank-quantity.
- **Audit Tooling**: `scripts/ui_contract_audit.sh` and `scripts/ui_phaseA_structural_guard.sh` hardened (path normalisation, controlled exclusions, zero false positives).
- **Test Coverage**: Phase 2A/2B/2D regression suites; smoke harness deterministic with canonical stock-in/out seeding; FIFO ordering assertions; count items with explicit `uom=ea`.
- **Launcher**: Tray icon now uses `core/ui/Logo.png` via pystray for correct Windows tray display.

### Changed
- Manufacturing service: output quantities and all intermediate values use base-integer arithmetic. `float()` removed from cost path; `Decimal` used throughout for round-half-up cost authority.
- Manufacturing costing: per-output unit cost computed as `round_half_up_cents(total_input_cost_cents / human_output_qty)`. Division by base output quantity forbidden.
- Smoke harness: replaced `/app/adjust` seeding with canonical `/app/stock/in` and `/app/stock/out` v2 contracts; deterministic end-to-end runs green.
- SOT.md: sealed with Phase 0–1 authority locks and Phase 2A–2D verification evidence.

### Breaking Changes
- **`qty_base` keys removed from Recipes, Ledger, and Finance (Refund) responses**. Consumers must migrate to `quantity_decimal` + `uom` fields. See Migration Notes below.
- **Base unit for count is `mc` (milli-count), NOT `ea`**. Any code that assumed `ea` as storage base with multiplier=1 is non-compliant. Use `normalize_quantity_to_base_int()`.
- **Manufacturing endpoint rejects legacy `quantity` key**. Use `quantity_decimal` + `uom` in all manufacture run payloads.

### Migration Notes
1. **Recipes payload**: Replace `qty_base: <int>` with `quantity_decimal: "<decimal>"` + `uom: "<uom>"` in recipe component definitions.
2. **Ledger history clients**: Default response no longer includes `qty_change` (base int). Use `quantity_decimal` + `uom`. Pass `?include_base=true` if base fields are required for internal audit.
3. **Finance refund**: Remove `qty_base` from refund payloads. Use `quantity_decimal` + `uom`.
4. **Count inventory**: Any client computing `qty * price` directly must call the backend cost API. Count items use `mc` base; 1 unit = 1000 mc in storage.
5. **Manufacturing runs**: Replace `quantity` payload key with `quantity_decimal` (string decimal) + `uom`.

## [0.10.1] — 2026-02-10
### Added
- Registered pytest markers in `pytest.ini` for `unit`, `api`, `integration`, `smoke`, and `slow`.
- Added `tests/TEST_PLAN.md` and `tests/RUNNING_TESTS.md` to document coverage and test execution.
- Added a high-signal finance invariant test for refund cash-only behavior.

### Changed
- Hardened plugin import-guard tests to use tmp-path plugin roots and avoid repository pollution.
- Reduced duplicated smoke assertions in manufacturing flow tests while preserving core invariants.
- Strengthened inventory journal purchase assertions by validating `qty_stored` updates.
- Marked index/path tests as `unit` and removed brittle path bootstrap setup.

## [0.8.8] — 2025-12-08
### Changed
- Windows restore: reliable on SQLite/Windows via lazy SQLAlchemy engine (NullPool), indexer worker-only, explicit stop around restore, WAL checkpoint + handle disposal, bounded exclusive check, atomic replace (MoveFileEx), and journal archive/recreate. Returns `{ "restart_required": true }` on success.
- Smoke harness: commit uses authenticated WebSession (no background job cookie loss); fast fail for restore lock contention; deterministic end-to-end run now green.
- Logging: clear `[restore] …` breadcrumbs; consistent request log lines.

### Fixed
- Restore 401 during `/app/db/import/commit` when executed from background jobs (cookies lost). Smoke now maintains session and validates error envelope shapes.

### Removed
- Redundant/stale dev scripts and assets (see repo pruning below).

## [0.8.7] — 2025-12-08
### Changed
- Error UX: all non-2xx responses are visible; `400` keeps dialogs open (field errors), `5xx/timeout` shows persistent banner; unified error parsing for string/object/list variants.

## [0.8.6] — deferred
- Routing/deep-links polish moved to last pre-0.9 batch (UI).

## v0.8.3
- Journals append only after database commits; restore archives and recreates journals.
- Password-based AES-GCM exports to `%LOCALAPPDATA%/BUSCore/exports` with preview/commit restore flow.
- Admin UI card for export/restore plus smoke coverage for reversible restores.

## v0.8.2
- Single-run POST contract for manufacturing runs.
- Fail-fast manufacturing (shortages=400, no writes).
- Atomic commit on success.
- Output costing rule (round-half-up).
- Manufacturing never oversells.
- Adjustments aligned to FIFO semantics.

## v0.8.1
- Core is tierless; removed all licensing logic and Pro gating.
- `/health` is tier-blind: returns only `{ ok, version }`.
- Deleted `/dev/license` and license.json handling.
- Removed Pro-only features (RFQ, batch automation, scheduled runs).
- **UI:** Removed license/tier badge and all “Pro/Upgrade” wording.

