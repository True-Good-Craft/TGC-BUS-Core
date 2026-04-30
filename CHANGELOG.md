# Changelog

## [1.0.4] - 2026-04-24

### Changed
- Bumped `VERSION` from `1.0.3` to `1.0.4`
- Bumped `INTERNAL_VERSION` from `1.0.3.3` to `1.0.4.0`

## [1.0.3] - Previous Release
- Bumped `VERSION` from `1.0.2` to `1.0.3`

## [Unreleased]

### Fixed
- Fixed Manufacturing stock display so recipe input/output rows show current on-hand inventory values instead of `—`.
- Aligned Manufacturing stock rendering with Inventory's item display helper.
- Fixed item-entry workflow so adding a vendor from the item form preserves current item fields.
- Added in-form vendor creation flow that returns to the item form and selects the newly created vendor.

### Added
- Added `.github/workflows/security-audit.yml` with Bandit source scanning, Medium/High Bandit CI failure, Low-severity advisory reporting, and advisory `pip-audit` evidence against `requirements.txt`.
- Added tracked governance summary for the completed security hardening pass: route-local guard consistency, Docker loopback default, loopback-only CORS, signed-manifest update staging, active security-audit workflow, and the local post-hardening OWASP 2025 reassessment. The OWASP report itself remains a local ignored report and is not release evidence on its own.
- Added explicit remaining-work framing for security governance: structured security audit events, dependency lockfile / blocking dependency audit, backup/restore safeguards, fallback secrets hardening, plugin/provider trust boundaries, and no LAN/public/multi-user hosting claim.
- Added update-staging signature-enforcement tests covering unsigned, trusted signed, bad-signature, unknown-key, explicit unsigned opt-out, and unchanged read-only update-check behavior.
- Added a focused CORS loopback policy test that source-checks the FastAPI middleware configuration and verifies allowed loopback, rejected untrusted-origin, no-wildcard, and same-origin unaffected behavior.
- Added a Docker loopback binding governance test that fails if default Compose publishing regresses to bare `8765:8765` and allows LAN exposure only in explicitly named, documented unsafe/advanced override files.
- Added route-guard consistency regression coverage for scoped ledger, finance, config, update, and app-log routes, including source-level mutation/read guard checks plus anonymous and writes-disabled API checks.
- Added secure-update foundation documentation for the post-v1.0.4 bridge work: DB/app ownership locking, local update cache/state scaffolding, Ed25519 manifest trust primitives, embedded backward-compatible manifest signatures, the pinned production manifest public-key policy, the release-side `scripts/sign_manifest.py` helper, and release-mirror manifest signing before upload.
- Added `scripts/validate_version_governance.py` to machine-check `pyproject.toml`, `SOT.md`, and `scripts/_win_version_info.txt` against the canonical values in `core/version.py`.
- Added `scripts/validate_change_trace.py`, `scripts/governance-check.ps1`, and `.github/workflows/governance-guard.yml` so code/control-surface changes fail hard unless `CHANGELOG.md` and `core/version.py` are part of the same change set.
- Added fortheemperor UI authority freeze documentation capturing canonical UI styling authority, active module standardization status, completed parity remediation scope, and deferred follow-on work.
- Added config-authority drift guards that assert `%LOCALAPPDATA%\BUSCore\config.json` is the canonical app-runtime config file, `%LOCALAPPDATA%\BUSCore\app\config.json` is legacy compatibility input only, and startup/write-policy code follows that contract.
- Added targeted config behavior tests for canonical write-gate persistence, canonical policy persistence, and one-way legacy fallback reads.
- Added release/update drift guards that verify release tooling reads `core/version.py`, targets the canonical public `BUS-Core-<VERSION>.zip` artifact name, and keeps `INTERNAL_VERSION` out of public SemVer consumers.
- Added auth-authority drift guards that verify `core.api.http` remains the canonical validator path, `tgc.security.require_token_ctx` is compatibility-only, and the authority docs stay aligned.
- Added update channel/config hardening for the manual update-check path: allowed channels are `stable`, `test`, `partner-3dque`, `lts-1.1`, and `security-hotfix`; missing channel defaults to `stable`; unsafe manifest URL schemes and local/private manifest hosts remain rejected outside explicit dev mode.
- Added manifest schema validation for supported legacy, canonical `latest`, `channels.<channel>`, and top-level channel-keyed manifest shapes while preserving the six-field `/app/update/check` response.
- Added internal `ManifestRelease` metadata carry-forward so validated manifest-provided `sha256`, `size_bytes`, release notes, signature URL, artifact kind/type/platform, publisher, and signer fields can be retained as declared metadata for future verification work.
- Added an internal update-artifact download helper that caches release ZIPs under `%LOCALAPPDATA%\BUSCore\updates\downloads\`, requires manifest-declared `sha256`, enforces `size_bytes` when present, verifies the downloaded ZIP hash against signed manifest metadata, and records `hash_verified` state only.
- Added a safe ZIP extraction helper that unpacks `hash_verified` artifacts into `%LOCALAPPDATA%\BUSCore\updates\versions\<version>\` via a temporary extraction directory, rejects zip-slip / absolute-path / escaping / suspicious ZIP entries, requires exactly one `.exe` candidate, and records `extracted` state only.
- Added Windows EXE trust verification for extracted update artifacts: the verifier requires Authenticode `Status == Valid`, True Good Craft signer-subject matching, and the pinned production signer thumbprint `55474AA9A2D562022A6590D487045E069457F985`, then records conservative `exe_verified` state only.
- Added a narrow `verified_ready` promotion helper that writes `verified_ready` only when `hash_verified`, `extracted`, and `exe_verified` all agree on version/channel/hash/path data and the cached ZIP, extracted version directory, and extracted EXE still exist inside the confined update-cache roots.

### Changed
- Bumped `INTERNAL_VERSION` from `1.1.0.5` to `1.1.0.6` for the Manufacturing/Inventory UI correctness patch without changing public `VERSION`.
- Bumped `INTERNAL_VERSION` from `1.1.0.4` to `1.1.0.5` for security-tooling workflow governance without changing public `VERSION`.
- Required signed manifests for the default `/app/update/stage` service path while leaving read-only `/app/update/check` unsigned-manifest compatibility unchanged.
- Bumped `INTERNAL_VERSION` from `1.1.0.3` to `1.1.0.4` for update-staging signed-manifest enforcement without changing public `VERSION`.
- Restricted default FastAPI CORS from wildcard origins/methods to explicit loopback origins and explicit methods/headers, aligning browser-origin policy with BUS Core's local-first trust model.
- Bumped `INTERNAL_VERSION` from `1.1.0.2` to `1.1.0.3` for CORS loopback restriction without changing public `VERSION`.
- Hardened Docker Compose default exposure to publish BUS Core on host loopback only (`127.0.0.1:8765:8765`) while preserving the container-internal Uvicorn bind, and updated runtime/security/release docs to state LAN/public exposure is unsafe by default.
- Bumped `INTERNAL_VERSION` from `1.1.0.1` to `1.1.0.2` for Docker loopback exposure hardening without changing public `VERSION`.
- Added explicit route-local session-token dependencies to sensitive ledger, finance, config, update-check, and app-log reads; added explicit route-local token + write-gate dependencies to ledger, finance, config, and update-stage mutations without changing payload contracts or public `VERSION`.
- Reconciled stale `pyproject.toml` and `SOT.md` public-version mirrors to the existing canonical `VERSION` value `1.1.0` from `core/version.py`.
- Bumped `INTERNAL_VERSION` from `1.1.0.0` to `1.1.0.1` for the route-local guard consistency patch without changing public `VERSION`.
- Sidebar update UX now uses a manual `Update` button instead of a raw download link as the primary action; it calls `POST /app/update/stage` only on user click, shows in-progress status, and reports verified-ready restart guidance without forcing restart.
- Updated security/release docs (`README.md`, `04_SECURITY_TRUST_AND_OPERATIONS.md`, `05_RELEASE_UPDATE_AND_DEPLOYMENT_FLOW.md`) to reflect current behavior accurately: `/app/update/check` remains read-only, manual `/app/update/stage` performs trusted staging, launcher policy-based handoff occurs after DB lock on next start, and there is no overwrite, forced restart, or startup auto-stage.
- Bumped `INTERNAL_VERSION` from `1.0.4.4` to `1.0.4.5` for the EXE trust, `verified_ready`, and targeted governance/docs pass without changing public `VERSION`.
- Bumped `INTERNAL_VERSION` from `1.0.4.2` to `1.0.4.3` for the release-mirror tooling separation and manifest-signing script import-path hardening without changing public `VERSION`.
- Updated `.github/workflows/release-mirror.yml` to separate tooling checkout (`tooling_ref`) from release identity (`release_tag`), enabling manual `workflow_dispatch` backfills to use current signing tooling while mirroring historical releases like `v1.0.4`.
- Added `workflow_dispatch` inputs `release_tag` and `tooling_ref` to release-mirror workflow; `release_tag` specifies the historical release to mirror, `tooling_ref` (default: `main`) specifies the repo ref to checkout for current `scripts/sign_manifest.py` and other tooling.
- Added pre-sign debug step to release-mirror workflow that verifies `scripts/sign_manifest.py` exists before signing, failing with a clear error message if the checked-out `tooling_ref` is missing the signing script.
- Added PYTHONPATH environment variable to release-mirror signing step to ensure core module imports resolve correctly in GitHub Actions.
- Added repo-root sys.path bootstrap to `scripts/sign_manifest.py` so it can be run directly from shell or CI without requiring PYTHONPATH to be preset, allowing `from core.runtime.manifest_trust import ...` to succeed.
- Updated `05_RELEASE_UPDATE_AND_DEPLOYMENT_FLOW.md` release-flow documentation to reflect that manual `workflow_dispatch` backfills validate `release_tag` as strict `vX.Y.Z` and derive manifest versioning from that requested tag instead of from the checked-out tooling ref.
- Bumped `INTERNAL_VERSION` from `1.0.4.1` to `1.0.4.2` for the secure-update foundation governance/signing-pipeline alignment pass without changing public `VERSION`.
- Documented that the release mirror now signs generated `stable.json` into `stable.signed.json` with `BUSCORE_MANIFEST_SIGNING_PRIVATE_KEY`, verifies backward-compatible `latest.version` / `latest.download.url` plus Ed25519 signature metadata, verifies against Core's pinned public key policy, and publishes the signed manifest in place as `manifest/core/stable.json`.
- Clarified secure-update limits: read-only update-check unsigned compatibility remains available, manual update staging now requires trusted signed manifests, internal helpers support hash-verified ZIP download, safe extraction, EXE Authenticode/publisher/thumbprint verification, and conservative `verified_ready` promotion inside the local update cache, but there is still no forced restart or auto-apply behavior.
- Added launcher-level DB ownership preflight so duplicate native launches are rejected before migrations, server bind, or browser open while retaining the app-level startup guard for server-only entrypoints.
- Bumped `INTERNAL_VERSION` from `1.0.4.0` to `1.0.4.1` for the DB ownership/single-instance launcher hardening without changing public `VERSION`.
- Bumped `INTERNAL_VERSION` from `1.0.3.2` to `1.0.3.3` for the final pre-release update-hardening governance pass without changing public `VERSION`.
- Corrected release mirror asset naming authority from `TGC-BUS-Core-<VERSION>.zip` to `BUS-Core-<VERSION>.zip` so release download, R2 mirror path, and manifest `latest.download.url` naming are aligned with the canonical artifact convention.
- Documented this release as an update-chain hardening bridge release: manifest compatibility is preserved for existing clients using top-level `latest.version` and `latest.download.url`, while new clients can consume channel-aware/additive metadata.
- Hardened non-stable update channel behavior so partner/test/LTS/security-hotfix lanes require explicit channel entries and do not silently fall back to public channel-less stable/latest manifests.
- Hardened manifest metadata handling so optional `sha256`, `size_bytes`, `release_notes_url`, `signature_url`, artifact token fields, publisher, and signer metadata are validated for shape when present and retained internally as declared values only.
- Restored the API error-code contract for blocked localhost/private/link-local/loopback/unspecified manifest URLs: policy-denied hosts return `manifest_url_not_allowed`, while malformed URLs and bad schemes remain `invalid_manifest_url`.
- Documented Phase 0A update-check behavior correction: update checks are default-on / opt-out, startup checks are one-shot and gated by `updates.enabled !== false` plus `updates.check_on_startup !== false`, manual "Check now" remains available, and hidden 15-minute polling/localStorage stale tracking has been removed.
- Corrected release-pipeline documentation to state current limits plainly: BUS Core does not auto-download/install/stage updates, does not verify artifact hash/signature/publisher/size yet, code signing remains manual post-build, release automation publishes the stable lane only, and Docker images are currently GHCR `latest` plus commit-SHA tags without SemVer tags, signing, SBOM/provenance, scanning, or formal Docker update policy.
- Corrected the Bandit remediation audit log: `pyproject.toml` currently has no `[tool.bandit]` baseline, so previous wording that claimed one was added was documentation drift.
- Bumped `INTERNAL_VERSION` from `1.0.3.1` to `1.0.3.2` for the RID security hardening governance-alignment pass without changing public `VERSION`.
- Hardened local RID handling as boundary-adjacent integrity logic: new RID generation now emits `local:v2:<sig32>:<payload>` using a stronger signature construction.
- Preserved backward compatibility for valid standing legacy RIDs (`local:<sig10>:<payload>`) via old-read/new-write behavior.
- Tightened commit path authority so when `src_id` / `dst_parent_id` are present, RID resolution is authoritative and invalid RID values fail closed instead of silently downgrading to raw-path fallback.
- Added strict RID parsing and payload validation (grammar, prefix/version, signature shape, URL-safe Base64 decode, UTF-8 decode, root match, traversal/escape, ambiguous root handling) with explicit fail-closed outcomes.
- Resolved Bandit `B324` in `core/reader/ids.py` via real hardening (no suppression, no `usedforsecurity=False` workaround).
- Reconciled `pyproject.toml` and `scripts/_win_version_info.txt` to the canonical public `VERSION` value `1.0.3` from `core/version.py`.
- Bumped `INTERNAL_VERSION` from `1.0.3.0` to `1.0.3.1` for this governance/build-enforcement repository change.
- Updated the release and agent governance docs to reference the new hard validation scripts and workflow instead of prose-only policy.
- Completed a docs-only governance and stability realignment across SOT, system maps, contract docs, release docs, and README so BUS Core is described consistently as the sovereign local trust anchor rather than an expansion-stage product.
- Corrected the stale `SOT.md` header from `v1.0.2` to `v1.0.3` to match the canonical release authority in `core/version.py`.
- Final fortheemperor cleanup: aligned `dev.writes_enabled` config-model default with fresh-install write-enabled truth, removed active Settings ownership of `close_to_tray`, stubbed Theme control to honest system-only mode, and strengthened sidebar BUS Core brand composition.
- Bumped `INTERNAL_VERSION` from `1.0.2.9` to `1.0.2.10` without changing public `VERSION`.
- Completed fortheemperor UI authority cleanup and route/module standardization passes across settings, contacts/vendors, manufacturing, inventory, and recipes using narrow reviewable changes.
- Completed contract-to-form parity remediation scopes for inventory, contacts, manufacturing, and recipes.
- Updated Recipes count-unit presentation policy so internal base unit `mc` is UI-hidden and operator-facing selectors present `ea`, while preserving backend/storage authority.
- Recorded write-gate operator-control finding: persisted `dev.writes_enabled` authority exists, while active UI has no direct writes toggle exposure.
- Removed dead UI card modules: `core/ui/js/cards/dev.js`, `core/ui/js/cards/fixkit.js`, `core/ui/js/cards/organizer.js`, `core/ui/js/cards/tasks.js`, `core/ui/js/cards/writes.js`.
- Bumped `INTERNAL_VERSION` from `1.0.2.8` to `1.0.2.9` without changing public `VERSION`.
- Bumped `INTERNAL_VERSION` from `1.0.2.7` to `1.0.2.8` without changing public `VERSION`.
- Normalized `/app/system/state` and `/app/system/start-fresh` internal failures to return stable structured error envelopes instead of raw string details.
- Made the Home transaction dashboard disclose placeholder-only data whenever `/app/transactions*` still returns stub responses, instead of rendering stub-backed widgets as if they were live business data.
- Aligned manufacturing journaling with the canonical journal authority so runtime writes, restore/archive behavior, and isolated smoke all use `BUS_MANUFACTURING_JOURNAL` or the shared runtime `JOURNAL_DIR` instead of a separate LOCALAPPDATA-only path.
- Refreshed `scripts/_win_version_info.txt` to canonical `1.0.2` metadata so the tracked Windows version-info template matches the current build output.
- Corrected the release validation helpers so `smoke_isolated.ps1` quotes the dev-helper launch path under spaced Windows repo roots, auto-selects a free local port when `8765` is already occupied, `scripts/smoke.ps1` honors the wrapper's `%LOCALAPPDATA%` isolation path and `BUS_DB`-derived journal location, and `scripts/release-check.ps1` now hard-fails when smoke or build exits non-zero.
- Bumped `INTERNAL_VERSION` from `1.0.2.6` to `1.0.2.7` without changing public `VERSION`.
- Reconciled `API_CONTRACT.md` against the live runtime so canonical business routes, supported operational protected routes, and secondary or legacy or drifted routes are documented as separate tiers.
- Corrected the declared contract for update check, system state, finance, item archive-delete behavior, canonical ledger history, and manufacturing run responses to match the current mounted surface and tests.
- Documented the current auth truth plainly where supported routes depend on middleware protection or lack a route-local write gate, rather than implying a cleaner authority model than the runtime actually uses.
- Bumped `INTERNAL_VERSION` from `1.0.2.5` to `1.0.2.6` without changing public `VERSION`.
- Reconciled auth validator authority so `core.api.http` owns protected-route validation, `AppState.tokens` is the canonical runtime token source, and `tgc.security.require_token_ctx` now delegates as a compatibility wrapper.
- Demoted `SESSION_TOKEN` and `session_token.txt` to secondary bootstrap/runtime mirrors instead of the normal request-validation authority.
- Reconciled config authority so `%LOCALAPPDATA%\BUSCore\config.json` is the single app-runtime settings authority, while `%LOCALAPPDATA%\BUSCore\app\config.json` is read only as a one-way legacy fallback for recognized older keys.
- Moved durable `writes_enabled`, `role`, and `plan_only` persistence under the canonical root config file without changing public `/app/config` or `/policy` route shapes.
- Aligned `SOT.md`, the config/security authority maps, and the Settings UI copy with the exact canonical Windows path strings the config-authority drift guards enforce.
- Reconciled release authority so `.github/workflows/release-mirror.yml` reads `core/version.py`, fails unless the release tag equals `v{VERSION}`, and publishes manifest `latest.version` from canonical `VERSION`.
- Repaired `scripts/release-check.ps1` to validate the real current release chain: `smoke_isolated.ps1`, `build_core.ps1`, and the expected `dist/BUS-Core.exe` plus `dist/BUS-Core-<VERSION>.exe` artifacts.
- Aligned release/update documentation and README wording with actual behavior: Lighthouse remains the default manifest URL, checksum metadata may be published, and the app does not verify checksum, signature, publisher, or artifact size before surfacing `download_url`.

### Tests
- Passed `node --check core/ui/js/cards/manufacturing.js`.
- Passed `node --check core/ui/js/cards/inventory.js`.
- Passed `node --check core/ui/js/lib/item-display.js`.
- Passed `git diff --check -- core/ui/js/lib/item-display.js core/ui/js/cards/inventory.js core/ui/js/cards/manufacturing.js`.
- Smoke was reported green for this focused UI correctness patch.
- UI contract audit was not completed: `scripts/ui_contract_audit.ps1` currently fails to parse at line 103, and `scripts/ui_contract_audit.sh` currently fails under bash because CRLF leaves `set: pipefail\r: invalid option name`.
- Added focused update-policy and manifest-validation coverage for allowed/rejected channels, stable backward compatibility, non-stable channel isolation, invalid metadata rejection, declared metadata retention, and the localhost/private-host error-code contract.
- Added targeted RID security coverage in `tests/test_reader_rid_security.py` for legacy compatibility, v2 resolution, malformed/tampered rejection, and mixed legacy/v2 commit-reader flows.
- Added Phase D validation coverage asserting the Home dashboard keeps explicit placeholder disclosure while it still depends on `/app/transactions*` stub routes.
- Extended config drift coverage to assert canonical path ownership, one-way legacy fallback behavior, and config startup wiring.
- Added auth-authority coverage for wrapper delegation, runtime-token precedence, configured session cookie extraction, shared route protection behavior, and code/docs drift alignment.
- Extended version drift coverage to assert release workflow tag/version checks, canonical asset naming, and truthful `release-check.ps1` wiring.

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
- Settings-based update check (manual; current startup-check default is documented under `[Unreleased]`).
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
- Initial update check system with `/app/update/check` for manifest-based version checks and normalized six-field response surface.

### Security
- Hardened update manifest fetch path with deterministic SSRF guards, redirect rejection (`follow_redirects=False`), JSON-only validation, and streaming 64KB size cap enforcement.

### UX
- Settings now supports manual "Check now" with conditional Download action, plus optional startup update notice when both update config gates allow it.
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
