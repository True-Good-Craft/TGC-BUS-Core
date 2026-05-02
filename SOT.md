# TGC BUS Core — Unified Source of Truth

**Version:** v1.1.1 **Updated:** 2026-05-02 **Status:** Stable **Authority:** `core/version.py` is the version authority. Where this document and code disagree, update this document.

---

## 1. Identity & Purpose

* **Company:** True Good Craft (TGC).

* **Product:** TGC BUS Core (Business Utility System).

* **Audience:** Small and micro shops, makers, and anti-SaaS operators who need durable local control.

* **Constitutional doctrine:** BUS Core is the sovereign local system of record. It MUST remain fully usable offline, on local infrastructure, without Pro, without accounts, and without forced cloud dependency.

* **Trust posture:** Predictability, stability, operator safety, and long-term reliability are first-order product requirements. Feature growth does not outrank trust preservation.

* **Authority boundary:** Core owns the canonical business logic, durable data model, and operator-safe base workflows. Pro may automate, orchestrate, integrate, or accelerate around Core, but it MUST NOT supersede Core or redefine Core logic.

* **Product framing:** Core is the product and trust anchor, not a crippled free tier. The system must remain complete and useful on its own.



---

## 2. Architecture & Deployment

### Technical Stack

* **Backend:** Python 3.12 / FastAPI using a factory callable (`core.api.http:create_app`).

* **Database:** SQLite via SQLAlchemy ORM.

* **UI:** Single-page application (SPA) shell (`core/ui/shell.html`) with modular JS cards.

* **Server:** Uvicorn at `127.0.0.1:8765` (native local) or `0.0.0.0:8765` inside the Docker container, with default Docker Compose host publishing restricted to `127.0.0.1:8765:8765`. Browser CORS defaults are loopback-only (`http://127.0.0.1:8765`, `http://localhost:8765`); wildcard CORS is not part of the supported default runtime.



### Deployment Modes

* **Native Windows:** Uses `%LOCALAPPDATA%\BUSCore\` for DB, config, and journals. Launch via `launcher.py` (or the thin wrapper `Run Core.bat`).

* **Docker:** Uses `python:3.12-slim`. Persistence via volume mounted at `/data` (e.g., `BUS_DB=/data/app.db`). Runs as non-root `appuser`. Docker Compose is loopback-only by default and must not publish BUS Core to LAN/public interfaces without explicit operator action and stronger access controls.

* **Dev/smoke helper:** `scripts/launch.ps1` runs the same `core.api.http:create_app` factory for scripted local checks only; it is not the supported native app entry.

---

## 3. Version Authority & Governance

### Canonical Version Fields

* **Canonical source:** `core/version.py`.

* **`VERSION`:** Canonical public/release/runtime version and MUST remain strict SemVer `X.Y.Z`.

* **`INTERNAL_VERSION`:** Internal working revision and MUST use `X.Y.Z.R`.

* **Initialization rule:** When introduced alongside release version `1.0.2`, `INTERNAL_VERSION` starts at `1.0.2.0`.

### Authority Rules

* Only the owner may intentionally bump `VERSION`.

* Agents MUST NOT bump `VERSION` without explicit owner instruction.

* Agents MAY bump only `INTERNAL_VERSION`, and MUST do so on meaningful repo changes.

* Meaningful agent changes MUST also update `CHANGELOG.md`, this SOT when behavior/contracts/authority change, and any governance docs affected by version-policy changes.

### Security hardening traceability (RID boundary token)

* RID/root-signature path token handling is treated as boundary-adjacent integrity logic because it participates in allowed-root path resolution used by runtime commit flows.

* RID compatibility posture is old-read/new-write: valid legacy `local:<sig10>:<payload>` values remain accepted for compatibility, while new RID generation emits hardened `local:v2:<sig32>:<payload>` values.

* RID parsing/resolution MUST be strict and fail-closed (malformed grammar, bad prefix/version, bad signature shape, invalid payload decoding, root mismatch, traversal/escape, ambiguous root match).

* When RID fields are present in plan actions (`src_id`, `dst_parent_id`), invalid RID values MUST NOT silently downgrade into unsafe raw-path fallback for that field.

* Security hardening that changes boundary behavior must be mirrored into `CHANGELOG.md`, `SOT.md`, and affected governance/security docs to prevent policy drift.

* Current hardening posture also treats sandbox command construction, admin preview DOM rendering, and import/local path resolution as boundary-sensitive surfaces: sandbox subprocess argv must remain BUS Core-owned and fixed, untrusted preview metadata must render as text, and user-influenced filesystem paths must resolve under explicit allowed roots before use.

* `scripts/validate_change_trace.py` is the hard traceability guard: if code/control surfaces change, both `CHANGELOG.md` and `core/version.py` MUST be in the same diff, and `INTERNAL_VERSION` MUST be bumped for meaningful repo changes.

* `.github/workflows/security-audit.yml` is the canonical security-tooling workflow. It runs Bandit against `core`, `tgc`, `scripts`, and `launcher.py`; Medium/High findings fail CI while Low findings remain visible advisory output. It also runs `pip-audit` against `requirements.txt` in advisory mode until BUS Core has a fully pinned/locked audit input.

### Release and Update Boundary

* Strict SemVer consumers MUST continue reading `VERSION` only.

* `INTERNAL_VERSION` is not part of release tags, manifest generation, `latest.version`, update-check comparison logic, or any other strict SemVer validation path.

* Release tags MUST equal `v{VERSION}`, and `.github/workflows/release-mirror.yml` machine-checks `tag == core/version.py::VERSION` before publishing manifest metadata.

* Published manifest `latest.version` MUST come from `core/version.py::VERSION`; tags remain a checked release boundary, not a second public version authority.

* `scripts/validate_version_governance.py` machine-checks the version mirrors, and `.github/workflows/governance-guard.yml` runs both governance validators on `push`, `pull_request`, and `workflow_dispatch`.

* Canonical public release artifact naming MUST be `BUS-Core-<VERSION>.zip`; manifest download URLs MUST be absolute Lighthouse URLs in the form `https://lighthouse.buscore.ca/releases/BUS-Core-<VERSION>.zip`.

* Current release automation publishes the stable manifest lane only. `updates.channel` exists structurally in Core configuration, but no current workflow publishes multiple channel manifests.

* `.github/workflows/release-mirror.yml` is the manifest signing authority for release publication. It generates `stable.json`, signs it into `stable.signed.json` with `scripts/sign_manifest.py`, fails if GitHub secret `BUSCORE_MANIFEST_SIGNING_PRIVATE_KEY` is missing, verifies the signed manifest, and uploads the signed file as `manifest/core/stable.json`. Lighthouse serves/proxies the signed manifest but does not own signing authority.

* Allowed Core update channels are `stable`, `test`, `partner-3dque`, `lts-1.1`, and `security-hotfix`. Non-stable channels MUST require an explicit channel-specific manifest entry and MUST NOT silently fall back to a public channel-less stable/latest manifest.

* Current and future manifests MUST preserve backward compatibility for deployed Core clients by keeping top-level `latest.version` and `latest.download.url`. Additive metadata, a `channels` map, and the top-level embedded `signature` object are allowed, and `channels.stable` SHOULD mirror top-level `latest` unless a release owner intentionally documents a divergence.

* Manifest authenticity support uses Ed25519. Embedded manifest signatures cover deterministic canonical JSON of the manifest with the top-level `signature` removed. The production public manifest key is pinned in Core with key ID `bus-core-prod-ed25519-2026-04-25`; the private signing key MUST NOT be committed and currently lives only in the GitHub secret `BUSCORE_MANIFEST_SIGNING_PRIVATE_KEY`.

* Client-side signed-manifest enforcement is required for manual update staging (`POST /app/update/stage`) and remains off for read-only update checks. Unsigned manifest compatibility is intentionally preserved only for discovery/check behavior, not for artifact staging.

* This release is an update-chain hardening bridge release. Manual staging requires trusted signed manifest metadata, hash-verifies downloaded ZIP artifacts against manifest `sha256` metadata while enforcing declared size when present, safely extracts hash-verified ZIPs into the local update cache, verifies EXE Authenticode/publisher/thumbprint trust, and promotes only consistent `verified_ready` state. It still does not force restart or auto-apply an update while Core is running.

* BUS Core has a DB/app ownership lock that prevents multiple live owners of the same DB/app root. Launcher preflight blocks duplicate native launches before browser open / uvicorn bind, and the app-level lock remains defense-in-depth. This ownership lock is a prerequisite for future verified version handoff, but this bridge release does not add staged update application.

* Windows code signing is currently a manual post-build ceremony. `scripts/build_core.ps1` builds the onefile EXE and prints optional `signtool sign` / `signtool verify` commands; it does not sign or verify artifacts automatically.

* Docker is a separate deployment lane. `.github/workflows/publish-image.yml` currently publishes GHCR `latest` and commit-SHA image tags only; it does not publish SemVer tags, sign images, generate SBOM/provenance, scan images, or define a formal Docker update policy. Default Compose networking is host-loopback only because BUS Core is local-first software and the session bootstrap model is not designed for multi-user network hosting.

---

## 4. Canonical Unit Model & Storage Contract
### Storage Layer (Absolute)

* All inventory quantities MUST be stored internally as integer base units.


* This applies to `ItemBatch.qty_remaining`, `ItemMovement.qty_change`, `ManufacturingRun.output_qty_base`, FIFO allocations, and Journal records.


* No floats, no Decimals, and no human units may be persisted.



### Canonical Base Units by Dimension

* Length → `mm`.


* Area → `mm2`.


* Volume → `mm3`.


* Weight → `mg`.


* Count → `mc` (milli-count).



### Count Dimension Rule (Critical)

* The base unit for count is `mc` (milli-count) across the system.


* 1 `ea` = 1000 `mc`.


* 
`ea` MUST NEVER be used as a storage base. Any code assuming `ea` is base=1 is non-compliant.



### Human Units (UI Input/Output)

* Permitted human units include `mm`, `cm`, `m` (length); `mm2`, `cm2`, `m2` (area); `mm3`, `cm3`, `ml`, `l` (volume); `mg`, `g`, `kg` (weight); and `mc`, `ea` (count).

### UI Count Presentation Policy

* `mc` remains a canonical backend/storage-supported count unit.

* User-facing UI selectors should treat `mc` as internal-only and present operator-facing count units (for example `ea`) unless an explicit advanced/internal workflow is intended.

* Hiding `mc` in UI presentation MUST NOT change backend unit authority, conversion rules, or API contract support for `mc`.



### Normalization Authority

* All quantity writes MUST pass through the canonical backend helper: `normalize_quantity_to_base_int(quantity_decimal: str, uom: str, dimension: str) -> int`.


* This helper is the single authority for unit conversion. It must use Decimal arithmetic, apply canonical multipliers, use `ROUND_HALF_UP` to the nearest base integer, and return an `int`.


* No backend code may multiply by hardcoded 100, 1000, or 1e outside this canonical helper.



### UI Drift Prevention

* The UI MUST NOT contain hardcoded unit multipliers.


* The UI MUST NOT store base unit integers client-side.


* All multipliers live exclusively in backend conversion logic.



---

## 4. Cost Authority & Valuation

### The `unit_cost_cents` Domain

* 
`unit_cost_cents` is ALWAYS defined as integer cents per HUMAN UNIT (`item.uom`).


* It is NEVER cost per base unit.


* For example, if `item.uom` = "ea", `unit_cost_cents` is the cost per 1 ea. If `item.uom` = "g" or "ml", it is the cost per 1 g or 1 ml.


* Base units are storage-only constructs and must not be used as a costing domain.



### Cost Calculation Formulas

* **General Cost:** Base quantities must first be converted to human quantities (`human_qty_decimal`). Cost is then calculated as `round_half_up_cents(unit_cost_cents * human_qty_decimal)`. Multiplying `unit_cost_cents` by base quantities directly is strictly prohibited.


* 
**Manufacturing Cost:** Convert each consumed base quantity to a human quantity exactly once, multiply by `unit_cost_cents`, and sum to find total input costs in cents. Per-output unit cost is `round_half_up_cents(total_input_cost_cents / human_output_qty)`. Division by base output quantity is forbidden.


* 
**Finance COGS:** Convert movement base quantity to human quantity, then multiply by `unit_cost_cents`.



### Inventory & FIFO Rules

* **FIFO Authority:** The oldest batches are consumed first; `unit_cost_cents` is copied 1:1 from batch to movement.


* 
**Valuation:** Inventory Value = `qty_on_hand` × `last_known_unit_cost`.


* Operations mutating both inventory and cash MUST occur inside a single DB transaction.



---

## 5. Service Layer & Mutation Authority

### Single Mutation Entry Rule

* All inventory-affecting operations MUST enter the system through a single service-layer mutation authority (e.g., `perform_stock_in`).


* Routes MUST NOT directly mutate inventory quantities, allocate FIFO, update `qty_stored`, or append journal entries.


* Inventory mutations are centralized in `core/services/stock_mutation.py` (routes must not call ledger primitives).



### Service Boundary Contract

* All inventory-mutating service functions must accept human quantities from the API layer, immediately normalize them to base int, and use base int for all internal comparisons and math.


* Ambiguous variable names are forbidden; strict naming using `qty_base` or `qty_human` is required.


* No float arithmetic or epsilon comparisons are allowed. No variable may ambiguously represent both human and base units.



---

## 6. API Routing & Payload Contracts

### Payload Shape Authority

* All inventory-affecting endpoints MUST accept only `quantity_decimal` (string) and `uom` (string).


* Endpoints MUST reject legacy fields such as `qty`, `qty_base`, `quantity_int`, and `raw_qty`.



### Canonical API Surface

* 
**Inventory & Ledger:** `POST /app/stock/in`, `POST /app/stock/out`, `POST /app/purchase`, `GET /app/ledger/history`.


* 
**Manufacturing:** `POST /app/manufacture`.


* UI MUST use only these canonical paths. `GET /app/ledger/history` is the canonical read surface for movement history.


* Legacy endpoints may exist but are non-authoritative and must wrap canonical handlers per the Phase 1 delta.


### Route-Local Protection Rule

* Sensitive `/app/*` reads MUST declare an explicit route-local session-token dependency unless the route is intentionally documented as public.

* Sensitive `/app/*` mutations MUST declare explicit route-local session-token and write-gate dependencies. Global session middleware remains defense-in-depth, not the only authority.

* Owner commit enforcement MUST be added only where the existing domain policy requires it; adding owner commit to a domain that did not previously require it is a behavior/authority change.



### Legacy Endpoint Deprecation Policy

* Legacy endpoints (e.g., `/app/stock_in`) MUST be treated as deprecated compatibility layers.


* They MUST NOT duplicate business logic. They are thin wrappers that translate legacy payloads to canonical ones and call canonical handlers directly.


* Wrappers MUST emit the header: `X-BUS-Deprecation: <canonical endpoint path>`.



### UI Routes (SPA)

* 
`#/welcome`: Onboarding wizard.


* 
`#/home`: Dashboard (must fit one screen without scrolling).


* 
`#/finance`: Profit/loss and cashflow.


* 
`#/inventory`: Items and batch management.



---

## 7. Manufacturing (Recipes & Runs)

### Definitions

* 
**Recipes:** Definitions for production (Canonical term: "Recipes," not "Blueprints").



### Shortage Contract (Deterministic)

* 
`validate_run(session, body)` is the authoritative shortage validation path. It computes required base quantities, compares to on-hand base quantities, and performs NO writes or inventory mutations.


* Shortage comparison must strictly be `if on_hand_base < required_base:` using integer operands. Float comparisons are forbidden.


* If shortages exist, a failed `ManufacturingRun` record MUST be created, and the API MUST return HTTP 400 with the payload `{ "error": "insufficient_stock", "shortages": [...], "run_id": <failed run id> }`. HTTP 200 responses on shortage conditions are prohibited.


* Manufacturing logic MUST NOT auto-adjust inventory, top-up components, retry, or convert shortages into partial executions.



### Execution & Atomicity

* 
`execute_run_txn(...)` MUST record all input movements, create output batches, append journal entries, complete in a single transaction, and calculate output costs natively.



---

## 8. Feature Systems

### Update Check System

*
**Default-on / opt-out:** Missing `updates.enabled` and `updates.check_on_startup` are treated as `true`. The UI runs one non-blocking startup check only when `updates.enabled !== false` and `updates.check_on_startup !== false`.


*
**Config:** Update settings live in `%LOCALAPPDATA%\BUSCore\config.json` under `updates` (`enabled`, `channel`, `manifest_url`, `check_on_startup`). Strict SemVer required, and fetches time out at 4 seconds.


*
**Channel/config hardening:** Missing `updates.channel` defaults to `stable`. Valid channels are `stable`, `test`, `partner-3dque`, `lts-1.1`, and `security-hotfix`. Invalid channels are rejected on save and safely loaded as `stable`. `updates.manifest_url` is trust-sensitive: only `http(s)` schemes are allowed, HTTPS is required outside explicit dev/test allowance, and localhost/private/link-local/loopback/unspecified manifest hosts are blocked outside `BUS_DEV=1` or `BUS_ALLOW_DEV_UPDATE_MANIFEST_URLS=1`.


*
**Config Authority:** `%LOCALAPPDATA%\BUSCore\config.json` is the canonical app-runtime config file. `%LOCALAPPDATA%\BUSCore\app\config.json` is legacy compatibility input only for recognized older keys when canonical values are absent.


*
**Manual check:** Manual "Check now" always calls `GET /app/update/check` regardless of the startup-check setting.


*
**Manual download only:** BUS Core does not auto-download, auto-install, stage, run, or apply update artifacts.


*
**Artifact trust limits:** The in-app update check validates manifest URL policy, JSON shape/content type, response size, and strict SemVer. It does not verify artifact hash, signature, publisher, or artifact size before surfacing a release `download_url`.


*
**Manifest validation and authenticity:** Supported manifest shapes are legacy direct stable manifests, canonical top-level `latest`, `channels.<channel>`, top-level channel-keyed entries, signature envelopes, and backward-compatible embedded signatures. Stable remains backward-compatible with top-level `latest.version` and `latest.download.url`. Non-stable channels require an explicit channel-specific entry and must not fall back to channel-less public stable/latest metadata. Optional artifact metadata (`sha256`, `size_bytes`, `release_notes_url`, `signature_url`, artifact kind/type/platform, publisher, signer) is shape-validated when present. Ed25519 verification and deterministic JSON canonicalization exist, including embedded top-level signatures that cover the manifest with `signature` removed. Manual update staging requires a trusted signed manifest; read-only update check does not yet require signatures.


*
**Trusted manifest key policy:** Core pins production manifest public key ID `bus-core-prod-ed25519-2026-04-25`. Public keys are safe to commit; private manifest signing keys must stay outside the repo. Release signing currently uses GitHub secret `BUSCORE_MANIFEST_SIGNING_PRIVATE_KEY`.
*
**Trusted manifest key policy:** Core pins production manifest public key ID `bus-core-prod-ed25519-2026-04-25`. Public keys are safe to commit; private manifest signing keys must stay outside the repo. Release signing currently uses GitHub secret `BUSCORE_MANIFEST_SIGNING_PRIVATE_KEY`.
*
**Backward-compatible manifest requirement:** Public manifests must keep top-level `latest.version` and `latest.download.url` so existing deployed BUS Core clients can still detect a newer version and open the Lighthouse-provided download link. Channel-aware and metadata-rich fields must remain additive.


*
**Local update cache/state lifecycle:** `%LOCALAPPDATA%\BUSCore\updates\` is the update cache root with `manifests\`, `downloads\`, and `versions\` subdirectories plus `updates\state.json`. `hash_verified` means a downloaded ZIP in `updates\downloads\` matched signed manifest `declared_sha256` metadata and optional declared size when present. `extracted` means that same `hash_verified` ZIP was safely unpacked into `updates\versions\<version>\` and exactly one EXE candidate path was recorded. `exe_verified` means the extracted EXE passed Authenticode/publisher/thumbprint trust checks. `verified_ready` is written only when `hash_verified`, `extracted`, and `exe_verified` agree and confined cache files still exist.

*
**Backward-compatible manifest requirement:** Public manifests must keep top-level `latest.version` and `latest.download.url` so existing deployed BUS Core clients can still detect a newer version and open the Lighthouse-provided download link. Channel-aware and metadata-rich fields must remain additive.


*
**Local update cache/state lifecycle:** `%LOCALAPPDATA%\BUSCore\updates\` is the update cache root with `manifests\`, `downloads\`, and `versions\` subdirectories plus `updates\state.json`. `hash_verified` means a downloaded ZIP in `updates\downloads\` matched signed manifest `declared_sha256` metadata and optional declared size when present. `extracted` means that same `hash_verified` ZIP was safely unpacked into `updates\versions\<version>\` and exactly one EXE candidate path was recorded. `exe_verified` means the extracted EXE passed Authenticode/publisher/thumbprint trust checks. `verified_ready` is written only when `hash_verified`, `extracted`, and `exe_verified` agree and confined cache files still exist.


*
**Background behavior:** There is no hidden periodic update polling loop and no `localStorage` stale/success timestamp tracking for update checks.


*
**UI:** Non-blocking banner appears if an update is found.

#### Phase 0A Behavior Correction (2026-04-24)

* `UpdatesConfig.enabled` is now default-on (`true`) when missing; `updates.check_on_startup` remains default-on when missing.

* Startup update checks are one-shot and require both update gates to be not explicitly false.

* Manual "Check now" remains available even when startup checks are disabled.

* The previous hidden 15-minute stale recheck loop and `bus.updates.last_success_ms` tracking were removed.

* This correction did not add auto-update behavior. Later bridge work added internal ZIP hash verification plus safe extraction helpers, but it still did not add executable trust verification, verified-ready promotion, handoff, or UI-driven update application.

#### Phase 1-3 Bridge Hardening (2026-04-24)

* Phase 1 made update channel and manifest URL behavior explicit and policy-validated without changing Lighthouse, Docker, release automation, or update installation behavior.

* Phase 2 added manifest schema validation while preserving legacy stable/current `latest.version` + `latest.download.url` compatibility and the six-field `/app/update/check` response.

* Phase 3 added internal `ManifestRelease` carry-forward for declared artifact metadata so future verification can use already-validated manifest values.

* Phase 3 fix restored the public API error-code contract: policy-blocked localhost/private/link-local/loopback/unspecified manifest URLs return `manifest_url_not_allowed`, while malformed URLs and bad schemes remain `invalid_manifest_url`.

* Remaining update-chain work includes EXE Authenticode/publisher verification, `verified_ready` promotion rules, safe handoff/launch behavior, keeping the manual signing ceremony explicit, Docker release hardening if that lane becomes release-governed, and preserving DB ownership/single-instance control before any staged/apply update path.

* This bridge release still performs no auto-download, no auto-install, no executable launch, and no handoff. Artifact download and extraction exist only as internal helpers; executable trust verification is still incomplete.

#### Secure Update Foundation (2026-04-25)

* DB/app ownership locking prevents two live BUS Core owners from using the same DB/app root. Launcher preflight blocks a duplicate native instance before browser open / uvicorn bind, and the app-level lock remains defense-in-depth.

* The update cache/state model now supports conservative `hash_verified`, `extracted`, `exe_verified`, and `verified_ready` stages under `%LOCALAPPDATA%\BUSCore\updates\state.json`. `verified_ready` is written only after ZIP hash, safe extraction, EXE trust, version/channel/hash/path consistency, and confined-file existence checks succeed.

* Manifest authenticity primitives support Ed25519 signatures, deterministic canonical JSON, signature envelopes, and embedded top-level signatures. Embedded signatures preserve public compatibility by keeping top-level `latest.version` and `latest.download.url`; the signature covers canonical JSON after removing top-level `signature`.

* The production manifest public key is pinned in Core as `bus-core-prod-ed25519-2026-04-25`. Release publication signs manifests with `scripts/sign_manifest.py` using GitHub secret `BUSCORE_MANIFEST_SIGNING_PRIVATE_KEY`; the helper has no publishing side effects and removes any previous top-level signature before signing.

* `.github/workflows/release-mirror.yml` now signs generated `stable.json` into `stable.signed.json`, verifies backward-compatible fields plus `signature.alg` / `signature.key_id`, verifies the embedded signature with Core's pinned public key policy, and uploads the signed manifest as `manifest/core/stable.json`.

* Internal helpers can download a ZIP into `updates\downloads\`, verify SHA256 and optional declared size against signed manifest metadata, then safely extract that ZIP into `updates\versions\<version>\` through a temporary extraction directory while rejecting unsafe archive contents and zero/multiple EXE candidates.

* Enforcement is deliberately scoped: read-only update check keeps unsigned manifest compatibility, but manual update staging requires trusted signed manifests and verifies ZIP hash, safe extraction, EXE Authenticode/publisher/thumbprint trust, and `verified_ready` consistency before restart guidance. Forced restart/auto-apply behavior remains out of scope.



### Onboarding & Demo

* System emptiness is determined strictly by the backend (`/app/system/state`).


* The "AvoArrow Aeroworks" Demo Loader must abort if existing data is present.



---

## 9. Security & Diagnostics

* **Session Authority:** `GET /session/token` is the canonical session bootstrap surface. It returns the current token and sets the `bus_session` cookie. Non-public routes require that cookie via the global session guard.

* **Validator Authority:** `core.api.http` (`session_guard`, `validate_session_token`, `require_token_ctx`) is the canonical protected-route validator. `tgc.security.require_token_ctx` is a compatibility wrapper and must delegate to the canonical path.

* **Token Mirrors:** `SESSION_TOKEN` and `session_token.txt` are secondary/bootstrap mirrors and are not the canonical runtime validation authority.

* **Dev Mode:** `BUS_DEV=1` exposes dev-only surfaces and detailed error traces, but it does NOT bypass session auth.

* **`/dev/*` Guarding:** When `BUS_DEV` is not `1`, `/dev/*` routes MUST return `404` to stay hidden. When `BUS_DEV=1`, `/dev/*` routes still require a valid session cookie. `GET /health/detailed` follows the same dev-only policy even though it is not under `/dev/*`.


* **Backups:** Encrypted AES-GCM backups. Restore process triggers maintenance mode and journal archiving.


* 
**No Telemetry:** All analytics are computed locally from the SQLite DB.


* 
**Diagnostic Instrumentation Policy:** Temporary diagnostic instrumentation (e.g., debug prints, route dumps) MUST NOT exist in production code. Debug-only tracking variables must be removed before merge.

* **Swallowed Exception Policy:** Empty `except: pass` handlers are not allowed by default. Intentional non-fatal handlers are limited to best-effort cleanup, optional platform/UI behavior, cache invalidation, telemetry-free journal side effects, config/tracker cleanup, and migration/compatibility fallbacks; each must use a narrow exception type where practical plus safe type-only logging or an explanatory comment. Raw exception details, sensitive paths, secrets, tokens, passwords, and DB URLs must not be returned to clients or logged from these paths. Security/auth/write/restore/update failures must fail closed or return controlled errors unless the failure is explicitly non-critical cleanup or an already-missing resource condition.



---

## 10. Testing Levels & Determinism Contracts

### Testing Architecture

* 
**Unit Tests (pytest):** Validate normalization logic, FIFO allocation, shortage detection, and endpoint contracts.


* 
**Integration Smoke:** Exercises full HTTP surface, validates ledger correctness, cost propagation, and 400 shortage responses.


* 
**Transactional Integrity:** Enforces that manufacturing runs are atomic, restore processes enforce exclusive DB handles, and no partial writes are permitted on shortages.



### Smoke Test Determinism Rule

* Smoke tests MUST NOT auto-adjust stock to recover from failures or retry runs by mutating inventory. Smoke must never alter business state to satisfy expected outcomes.


* Shortage tests MUST use impossible deterministic quantities (e.g., `1000000`) to guarantee shortage regardless of prior test state. Shortage tests MUST execute after successful manufacturing cases in the canonical flow.



---

## 11. System Invariants & Non-Compliance Definitions

The following are strictly considered regressions or architectural drift and MUST be corrected immediately upon discovery:

* 
**Storage & Units:** UI-side unit multipliers, base units stored client-side, storing the count dimension as `ea` base=1, or storing non-integer (float/Decimal) quantities in DB.


* 
**Costing & Math:** Multiplying `unit_cost_cents` by base quantities, dividing cents by base quantities to derive unit costs, introducing fractional cents, or using float arithmetic for cost math.


* 
**Manufacturing Logic:** Shortages returning HTTP 200, float quantities in shortage payloads, float calculations in inventory comparisons, partial manufacturing executions on insufficient stock, or manufacturing retrying internally.


* 
**Architecture:** Business logic inside legacy wrappers, duplicate endpoints lacking deprecation headers, bypassing the canonical service boundary, or using ambiguous quantity variable names (like `qty` or `amount` instead of `qty_base`/`qty_human`).


---

## 12. Changelog

### v0.11.0 — 2026-02-22 — Phase 1 Architectural Authority Lock

* Canonical /app endpoint surface enforced (stock/in, stock/out, purchase, ledger/history, manufacture).


* Legacy endpoints converted to wrapper-only with X-BUS-Deprecation.


* Canonical quantity contract enforced: quantity_decimal + uom; legacy qty keys rejected.


* Inventory mutation centralized in core/services/stock_mutation.py.


* Drift-guard tests added to prevent route-level mutation primitives and UOM guessing regressions.


# SoT DELTA — Phase 1 Architectural Authority Lock — POST-WORK VERIFIED

[DELTA HEADER]
SOT_VERSION_AT_START: v0.11.0
SESSION_LABEL: Phase 1 Architectural Authority Lock (Canonical Surface + Wrapper Discipline + Single Mutation Authority)
DATE: 2026-02-22
SCOPE: canonical endpoints, legacy wrapper policy, quantity contract enforcement, mutation authority, drift-guard tests
COMMIT: d736b12
BRANCH: work
[/DELTA HEADER]

## (1) CANONICAL PUBLIC API SURFACE (AUTHORITATIVE)
- POST /app/stock/in
- POST /app/stock/out
- POST /app/purchase
- GET  /app/ledger/history
- POST /app/manufacture

## (2) LEGACY ENDPOINT POLICY (BINDING)
- Legacy endpoints may exist only as thin wrappers.
- Wrappers MAY ONLY: translate payload keys, cast types, delegate to canonical handler, set X-BUS-Deprecation, return result unmodified.
- Wrappers MUST NOT: normalize quantities, call multipliers, query DB beyond read-only default-uom lookup, call FIFO/ledger primitives, or mutate DB.

## (3) CANONICAL QUANTITY CONTRACT (BINDING)
Canonical endpoints accept only:
- quantity_decimal: string
- uom: string
Forbidden legacy keys (reject with 400):
- qty
- qty_base
- quantity_int
- quantity

## (4) SINGLE MUTATION AUTHORITY (BINDING)
- All inventory mutation must flow through: core/services/stock_mutation.py
- Route modules must not call: add_batch, fifo_consume, append_inventory (directly).

## (5) REQUIRED RESPONSE HEADER (LEGACY WRAPPERS)
- Legacy wrappers MUST emit: X-BUS-Deprecation: <canonical path>

## (6) DRIFT-GUARD TESTS (NORMATIVE PROTECTION CLAUSE)
- Drift guard tests exist to prevent regression:
  - forbids mutation primitives in core/api/routes/*
  - forbids UOM guessing patterns in core/api/routes/*
- These tests are considered part of the contract enforcement (future changes must update SoT + tests together).

## (7) EVIDENCE (PASTE VERBATIM OUTPUTS)

```text
TARGET CHECKS:
POST   /app/stock/in => PRESENT
POST   /app/stock/out => PRESENT
POST   /app/purchase => PRESENT
GET    /app/ledger/history => PRESENT
POST   /app/manufacture => PRESENT
```

```text

```

```text
core/api/routes/ledger_api.py:263:    payload.setdefault("uom", "mc")
core/api/routes/manufacturing.py:264:    payload.setdefault("uom", "ea")
```

```text
.......................................   [100%]
70 passed, 2 skipped in 23.96s
```



# SoT DELTA — Manufacturing Base-Unit Convergence — Phase 2A — POST-WORK VERIFIED

[DELTA HEADER]
SOT_VERSION_AT_START: v0.11.0
SESSION_LABEL: Manufacturing Base-Unit Convergence — Phase 2A (Storage & Validation Authority) — POST-WORK VERIFIED
DATE: 2026-02-22
SCOPE: manufacturing validate_run determinism, base-int scaling, base-int persistence, journal base-int quantities
COMMIT: 9ab8b10
BRANCH: docs/phase2a-postwork-sot
[/DELTA HEADER]

## (1) IMPLEMENTED CHANGES (CLAIMS)
- validate_run converts requested output (quantity_decimal+uom) to output_qty_base (int) and uses base-int comparisons only.
- Recipe scaling uses Decimal ratio and quantizes required_base exactly once with ROUND_HALF_UP.
- Shortage calculation uses: max(required_base - on_hand_base, 0) (int-only).
- execute_run_txn consumes component qty as base ints and produces output qty as base ints.
- manufacturing_runs.output_qty persists base-int output quantity (output_qty_base).
- Manufacturing journal records quantities as base ints only (output_qty_base and consumed_qty_base).
- Canonical API remains human-only; no base quantities exposed in JSON responses.
- Cost math is unchanged in Phase 2A (explicitly deferred to Phase 2B).

## (2) INVARIANTS SATISFIED
- No epsilon comparisons exist in manufacturing code (1e-9 removed).
- No float math participates in validate_run scaling or shortage comparisons.
- No ambiguous unit variables (base vars are suffixed *_base).

## (3) EVIDENCE (PASTE VERBATIM OUTPUTS)

```text
docs/phase2a-postwork-sot
9ab8b10
```

```text
........................................................................ [100%]
72 passed, 2 skipped in 25.34s
```

```text

```

```text
[db] BUS_DB (APPDATA) -> /root/.buscore/app/app.db
TARGET CHECKS:
POST   /app/stock/in => PRESENT
POST   /app/stock/out => PRESENT
POST   /app/purchase => PRESENT
GET    /app/ledger/history => PRESENT
POST   /app/manufacture => PRESENT
```

```text
115:def _scale_ratio(output_qty_base: int, recipe_output_qty_base: int) -> Decimal:
116:    if int(recipe_output_qty_base) <= 0:
117:        raise ValueError("recipe_output_qty_base_must_be_positive")
118:    return Decimal(int(output_qty_base)) / Decimal(int(recipe_output_qty_base))
132:        output_qty_base = _to_base_qty_for_item(session, output_item_id, body.quantity_decimal, body.uom)
133:        recipe_output_qty_base = int(recipe.output_qty or 0)
135:            scale = _scale_ratio(output_qty_base, recipe_output_qty_base)
158:        output_qty_base = _to_base_qty_for_item(session, output_item_id, body.quantity_decimal, body.uom)
184:    return output_item_id, required, output_qty_base, format_shortages(shortages)
193:    output_qty_base: int,
200:        output_qty=int(output_qty_base),
238:    per_output_cents = round_half_up_cents(cost_inputs_cents / float(output_qty_base))
241:        qty_initial=int(output_qty_base),
242:        qty_remaining=int(output_qty_base),
258:                "out_qty_base": int(output_qty_base),
269:            qty_change=int(output_qty_base),
284:        output_item.qty_stored = int(output_item.qty_stored or 0) + int(output_qty_base)
290:            "output_qty_base": int(output_qty_base),
302:        "output_qty_base": int(output_qty_base),
```

## (4) NOTES / KNOWN FOLLOW-UPS (NON-BLOCKING)
- Cost authority corrections (per_output_unit_cost_cents derived from human qty) are Phase 2B.

---

## 13. UI Authority Freeze (fortheemperor)

### Canonical UI Authority Status

* `core/ui/css/app.css` is the canonical styling authority for shared shell, cards, forms, buttons, status, and page composition patterns.

* `core/ui/shell.html` remains primarily structural and route-hosting; meaningful style authority has been substantially reduced via staged migration.

* `core/ui/app.js` and route cards should render semantic class hooks and avoid new inline presentation authority.

### Active Module Standardization Snapshot

* Standardized for presentation authority: settings, contacts/vendors, recipes, finance, logs.

* Partially standardized with scoped deferred work: inventory, manufacturing.

### Legacy/Removal Truth

* Removed dead modules: `core/ui/js/cards/dev.js`, `core/ui/js/cards/fixkit.js`, `core/ui/js/cards/organizer.js`, `core/ui/js/cards/tasks.js`, `core/ui/js/cards/writes.js`.

* Deferred quarantine/legacy candidates still unresolved: `core/ui/js/cards/home_donuts.js`, `core/ui/js/cards/tools.js`, `core/ui/js/cards/backup.js`.

### Contract-to-Form Parity Truth (Completed Modules)

* Inventory parity remediation completed for documented Step 1 scope (quantity intent correction, sold non-count guard, cents normalization, vendor coercion).

* Contacts parity remediation completed for documented Step 2 scope (name-only required parity, organization controls, role-derivation alignment).

* Manufacturing parity remediation completed for documented Step 3 scope (run quantity input and structured shortage/error display), while ad-hoc UI remains intentionally deferred.

* Recipes parity remediation completed for documented Step 4 scope (item-compatible UOM selection, strict numeric validation, safer backend error rendering, explicit component-row policy).

### Write Gate Authority Finding

* Runtime write blocking is enforced by backend gate authority (`require_write_access` / `require_writes`) with persisted authority via `dev.writes_enabled` and startup runtime resolution.

* Fresh-install default truth is write-enabled unless explicitly overridden by persisted config (`dev.writes_enabled`) or environment read-only controls.

* Active UI does not expose a direct writes toggle control even though persisted authority exists.

### Deferred Follow-on Work (Explicit)

* Small Settings pass: admin/export-restore guard/error-display polish where contract-backed.

* Active Settings UI no longer owns `close_to_tray`; launcher close behavior remains compatibility config only unless explicitly reintroduced.

* Theme control is currently system-only/stubbed in active UI until alternate theme systems are intentionally shipped.

* Update-check display/settings logic cleanup pass (UI behavior/presentation-level only).

* Legacy/quarantine resolution decisions and implementation for remaining deferred cards (`home_donuts`, `tools`, `backup`).

* UI-vs-backend count-unit authority reconciliation follow-up for `core/ui/js/lib/units.js` vs canonical backend/SOT count base model.
- Finance COGS authority corrections are Phase 2C.

### v0.11.0 — 2026-02-22 — Phase 2B Manufacturing Cost Authority
- Allocation costing uses base→human conversion once (Decimal), no float()
- Per-output cost divides by human output quantity
- Regression test locks human-unit cost authority (count dimension)

# SoT DELTA — Manufacturing Base-Unit Convergence — Phase 2B — POST-WORK VERIFIED

[DELTA HEADER]
SOT_VERSION_AT_START: v0.11.0
SESSION_LABEL: Manufacturing Base-Unit Convergence — Phase 2B (Cost Authority) — POST-WORK VERIFIED
DATE: 2026-02-22
SCOPE: manufacturing cost authority, base→human conversion once, float ban, regression test lock
COMMIT: 0095935
BRANCH: docs/phase2b-postwork-sot
[/DELTA HEADER]

## (1) IMPLEMENTED CHANGES (CLAIMS)
- Manufacturing costing now treats unit_cost_cents as cents per human unit (item.uom).
- Allocation cost uses base→human conversion exactly once per allocation quantity.
- per_output_unit_cost_cents divides by human output quantity (never output_qty_base).
- No float() usage exists in manufacturing cost computations.
- Added regression test enforcing human-unit cost authority for count-dimension items (ea with base mc).

## (2) FORBIDDEN PATTERNS (NOW ENFORCED)
- No float() in manufacturing service costing path.
- No division by output_qty_base for per-output cost.
- No multiplication of unit_cost_cents by alloc["qty"] directly.

## (3) EVIDENCE (PASTE VERBATIM OUTPUTS)

```text
docs/phase2b-postwork-sot
0095935
```

```text
........................................................................ [ 98%]
.                                                                        [100%]
73 passed, 2 skipped in 26.20s
```

```text

```

```text

```

```text
120:def test_cost_authority_uses_human_units_for_count_dimension(request: pytest.FixtureRequest):
```

## (4) NOTES / FOLLOW-UPS (NON-BLOCKING)
- Finance COGS cost authority is Phase 2C.
- Optional tightening later: make _basis_uom_for_item treat multiplier==0 as invalid (fallback to default_unit_for).

### v0.11.0 — 2026-02-22 — Phase 2C Finance COGS Authority
- /app/finance/profit COGS uses base→human conversion once (Decimal), no float()
- COGS line cost uses unit_cost_cents × human_qty (never × base qty)
- Regression test locks human-unit COGS for count items (mc/ea)

# SoT DELTA — Finance Cost Authority — Phase 2C — POST-WORK VERIFIED

[DELTA HEADER]
SOT_VERSION_AT_START: v0.11.0
SESSION_LABEL: Finance Cost Authority — Phase 2C (COGS Human-Unit Discipline) — POST-WORK VERIFIED
DATE: 2026-02-22
SCOPE: /app/finance/profit COGS math, base→human conversion once, float ban, regression test lock
COMMIT: a1fb6db
BRANCH: docs/phase2c-postwork-sot
[/DELTA HEADER]

## (1) IMPLEMENTED CHANGES (CLAIMS)
- Finance COGS now treats unit_cost_cents as cents per human unit (basis_uom).
- Each movement’s base qty is converted to human qty exactly once using uom_multiplier.
- Line cost is computed as: round_half_up_cents(Decimal(unit_cost_cents) * human_qty).
- COGS is the sum of line costs (human-unit authority).
- No float() usage exists in the finance COGS path.
- Added regression test locking human-unit COGS for count items (mc/ea multiplier).

## (2) FORBIDDEN PATTERNS (NOW ENFORCED)
- No unit_cost_cents * qty_base multiplication for COGS.
- No float() in finance COGS computation.

## (3) EVIDENCE (PASTE VERBATIM OUTPUTS)

```text
docs/phase2c-postwork-sot
a1fb6db
```

```text
...............................
......................................... [ 97%]
..                                                                       [100%]
74 passed, 2 skipped in 39.11s
```

```text

```

```text

```

```text
194:def test_profit_cogs_uses_human_unit_cost_not_base_qty(bus_client):
```

## (4) NOTES / FOLLOW-UPS (NON-BLOCKING)
- Optional: unify round_half_up_cents helper with manufacturing/shared utility to avoid duplication.

### v0.11.0 — 2026-02-22 — Smoke Harness Canonical Contract Alignment
- Smoke scripts/tests use canonical /app endpoints and canonical quantity payloads
- Smoke runs twice on fresh DBs (BUS_DB override) to prove determinism

# SoT DELTA — Smoke Harness Canonical Contract Alignment — POST-WORK VERIFIED

[DELTA HEADER]
SOT_VERSION_AT_START: v0.11.0
SESSION_LABEL: Smoke Harness Canonical Contract Alignment (Endpoints + Quantity Contract) — POST-WORK VERIFIED
DATE: 2026-02-22
SCOPE: smoke scripts/tests, canonical endpoints usage, canonical quantity payloads, fresh DB determinism
COMMIT: b3fce38
BRANCH: docs/smoke-postwork-sot
[/DELTA HEADER]

## (1) IMPLEMENTED CHANGES (CLAIMS)
- Smoke harness uses canonical /app endpoints only (no legacy endpoint calls).
- Smoke payloads use canonical quantity contract only: quantity_decimal (string) + uom (string).
- Smoke avoids deprecated keys: qty, qty_base, quantity, quantity_int, output_qty.
- Smoke replaces legacy /app/consume usage with canonical /app/stock/out (reason="other", record_cash_event=false) where needed.
- Smoke executes twice on fresh DBs using BUS_DB override to prove determinism.

## (2) EVIDENCE (PASTE VERBATIM OUTPUTS)

```text
docs/smoke-postwork-sot
b3fce38
```

```text
..                                                                       [100%]
2 passed in 3.06s
```

```text
..                                                                       [100%]
2 passed in 2.97s
```

```text

```

```text
[db] BUS_DB (APPDATA) -> /root/.buscore/app/app.db
TARGET CHECKS:
POST   /app/stock/in => PRESENT
POST   /app/stock/out => PRESENT
POST   /app/purchase => PRESENT
GET    /app/ledger/history => PRESENT
POST   /app/manufacture => PRESENT
```

## (3) NOTES / FOLLOW-UPS (NON-BLOCKING)
- PowerShell runner exists for Windows-local full smoke execution; CI may rely on python smoke evidence.

# SoT DELTA — UI Contract Expansion — v2 Quantity Everywhere (Recipes + Refund + Ledger Human Fields) — AUTHORIZATION DELTA (EVIDENCE FILLED)

[DELTA HEADER]
SOT_VERSION_AT_START: v0.11.0
SESSION_LABEL: UI Contract Expansion — v2 Quantity Everywhere (Recipes + Refund + Ledger Human Fields) — AUTHORIZATION DELTA (EVIDENCE FILLED)
DATE: 2026-02-23
SCOPE: evidence placeholders completed from Phase 2D + UI Phase B results
[/DELTA HEADER]

## EVIDENCE

### pytest outputs
```text
$ pytest -q tests/api/test_finance_v1.py
......                                                                   [100%]
6 passed in 7.72s
```

```text
$ pytest -q tests/api/test_recipes_v2_contract.py
..                                                                       [100%]
2 passed in 3.33s
```

```text
$ pytest -q tests/api/test_ledger_history_v2_response.py
..                                                                       [100%]
2 passed in 3.23s
```

### JSON excerpts (runtime contract checks)
```json
{
  "refund_legacy": {
    "status": 400,
    "body": {
      "detail": {
        "error": "legacy_quantity_keys_forbidden",
        "keys": [
          "qty_base"
        ],
        "message": null
      }
    }
  },
  "recipes_v2": {
    "status": 200,
    "body": {
      "quantity_decimal": "1",
      "uom": "ea",
      "items": [
        {
          "quantity_decimal": "2",
          "uom": "ea"
        }
      ]
    }
  }
}
```

### ledger/history response-shape lock from tests
```text
$ sed -n '34,63p' tests/api/test_ledger_history_v2_response.py
    history = client.get(f"/app/ledger/history?item_id={item_id}&limit=10")
    assert history.status_code == 200, history.text
    payload = history.json()
    assert payload["movements"]
    movement = payload["movements"][0]
    assert "quantity_decimal" in movement
    assert "uom" in movement
    assert "qty_change" not in movement

    history = client.get(f"/app/ledger/history?item_id={item_id}&limit=10&include_base=1")
    assert history.status_code == 200, history.text
    payload = history.json()
    assert payload["movements"]
    movement = payload["movements"][0]
    assert "quantity_decimal" in movement
    assert "uom" in movement
    assert "qty_change" in movement
```

# SoT DELTA — Final Seal (Phase 2D + UI Phase B)

[DELTA HEADER]
SOT_VERSION_AT_START: v0.11.0
SESSION_LABEL: Seal — Phase 2D v2 Contracts Implemented + UI Phase B Full Purge Verified
DATE: 2026-02-23
SCOPE: evidence + verification locks only
[/DELTA HEADER]

## (1) Objective
Seal the Phase 2D backend contract expansion and UI Phase B full purge with final verification evidence suitable for release readiness.

## (2) What was sealed
- recipes v2 contract
- finance refund v2 contract
- ledger history v2 response (human fields, base hidden by default)
- UI full purge (no legacy keys anywhere in audit scope, no conversion signatures)

## (3) Verification evidence blocks (raw outputs)

### ui_contract_audit PASS output
```text
$ ./scripts/ui_contract_audit.sh
UI contract audit: PASS
  forbidden endpoints: 0
  forbidden payload keys: 0
  multiplier/base logic: 0
  finance legacy fields: 0
  canonical containment violations: 0
  report: reports/ui_contract_audit.md
```

### node --check outputs
```text
$ node --check core/ui/js/cards/recipes.js
$ node --check core/ui/js/cards/manufacturing.js
$ node --check core/ui/js/cards/inventory.js
```

### pytest outputs
```text
$ pytest -q tests/api/test_finance_v1.py
......                                                                   [100%]
6 passed in 7.72s

$ pytest -q tests/api/test_recipes_v2_contract.py
..                                                                       [100%]
2 passed in 3.33s

$ pytest -q tests/api/test_ledger_history_v2_response.py
..                                                                       [100%]
2 passed in 3.23s
```

### smoke harness run #1 output (fresh DB via pytest tmp_path fixture)
```text
$ pytest -q tests/smoke/test_manufacturing_flow.py
..                                                                       [100%]
2 passed in 3.31s
```

### smoke harness run #2 output (fresh DB via pytest tmp_path fixture)
```text
$ pytest -q tests/smoke/test_manufacturing_flow.py
..                                                                       [100%]
2 passed in 3.23s
```

## (4) Acceptance statement
DONE = TRUE

# SoT DELTA — Smoke Harness Finalization — Phase 2D Compatible, Deterministic, PS 5.1 Clean

[DELTA HEADER]
SOT_VERSION_AT_START: v0.11.0
SESSION_LABEL: Smoke Harness Finalization — Phase 2D Compatible, Deterministic, PS 5.1 Clean
DATE: 2026-02-23
SCOPE: smoke.ps1 cleanup + evidence
[/DELTA HEADER]

## (1) Objective
Restore a wall-of-green deterministic smoke harness under Phase 2D contracts while removing investigation-only debug noise.

## (2) What changed
- Removed investigation-only debug noise from stock-in/ledger correlation path.
- Kept correlation checks (batch_id/source_id) and changed diagnostics to failure-only output.
- Kept ParseDec strict normalization and fail-loud behavior with no success-path diagnostics.
- Fixed cleanup decimal absolute-value handling to PowerShell 5.1-compatible usage.

## (3) Evidence blocks (raw outputs)

### Smoke run #1 full output
```text
$ powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\smoke.ps1
bash: command not found: powershell
```

### Smoke run #2 full output
```text
$ powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\smoke.ps1
bash: command not found: powershell
```

### git diff summary
```text
$ git show --stat --oneline d4a29fb
d4a29fb test(smoke): finalize harness output (remove debug spam), fix cleanup abs
 scripts/smoke.ps1 | 54 +++++++-----------------------------------------------
 1 file changed, 7 insertions(+), 47 deletions(-)
```

```text
$ git show --name-only --oneline d4a29fb
d4a29fb test(smoke): finalize harness output (remove debug spam), fix cleanup abs
scripts/smoke.ps1
```


[DELTA HEADER]
SOT_VERSION_AT_START: v0.11.0
SESSION_LABEL: UI Phase B — Routing & Deep-link Completion + Inventory UX Polish + Audit Tooling Hardening
DATE: 2026-02-24
SCOPE: UI only (routing/entrypoint hardening, deep-link behavior, inventory UX), tooling only (audit scripts)
BRANCH: systemnormalisation
COMMIT: pending
[/DELTA HEADER]

## (1) OBJECTIVE
Complete Phase B UI routing/deep-link contract and inventory UX polish while keeping backend/API contracts unchanged, and harden Phase A/B audit tooling to reduce false positives.

## (2) COMPLETED WORK
- index.html de-brained to redirect stub -> shell.html (no second SPA brain)
- legacy router.js disabled by default (single router authority is app.js)
- app.js routing contract:
  - normalizeHash
  - alias redirects (#/dashboard→#/home, #/items→#/inventory, #/vendors→#/contacts, param aliases)
  - param matching for /<id> routes with BUS_ROUTE capture
  - dedicated 404 with link to #/home
  - placeholder routes for #/runs and #/import (if implemented)
- Deep-link realization using BUS_ROUTE:
  - Inventory (#/inventory/<id>): opens existing detail UI or not-found redirect
  - Contacts (#/contacts/<id>): expands existing detail row or not-found redirect
  - Recipes (#/recipes/<id>): opens existing detail UI or not-found redirect (this patch)
- Inventory UX polish:
  - dimension-safe UOM dropdown filtering
  - remaining qty display in batch table (no legacy int fields; no parseInt reconstruction)
  - metadata-only save allowed (quantity optional unless opening batch)
  - warn-on-blank quantity behavior (not blocking)
- Audit tooling polish:
  - ui_contract_audit.sh hardened (path normalization + controlled exclusions)
  - ui_phaseA_structural_guard.sh scoped to avoid token/units false positives; all guards PASS

## (3) ACCEPTANCE (CHECKLIST)
- Both scripts PASS:
  - scripts/ui_contract_audit.sh
  - scripts/ui_phaseA_structural_guard.sh (Guard 5 NOTE only acceptable)
- Deep-links verified manually:
  - #/inventory/<id>, #/contacts/<id>, #/recipes/<id> (happy + not-found)
- Unknown route shows 404 and link back to #/home

## (4) EVIDENCE PLACEHOLDERS (operator fills)
- Paste outputs:
  ```text
  <output of scripts/ui_contract_audit.sh>
  ```

  ```text
  <output of scripts/ui_phaseA_structural_guard.sh>
  ```

- Manual smoke checklist completion notes


[DELTA HEADER]
SOT_VERSION_AT_START: v0.11.0
SESSION_LABEL: Post-Stabilization Wrap — Transaction Boundary + SOLD Correlation + Smoke Verification
DATE: 2026-02-25
SCOPE: stabilization validation closure; correlation wiring fix; invariant tests; smoke evidence capture; doc alignment
[/DELTA HEADER]

(1) OBJECTIVE
Close remaining pre-merge stabilization gates for PR #478 by:

- Enforcing route-owned transaction boundaries (no commits/begins inside service mutation helpers).
- Fixing inventory journal correlation integrity for stock-out SOLD path.
- Recording canonical smoke harness execution as authoritative evidence (operator-provided log).
- Confirming full pytest suite pass after stabilization changes.

This delta is documentation/governance only and does not alter domain business logic.

(2) BINDING INVARIANTS (RE-AFFIRMED)
2.1 Transaction Ownership
- Service/helper layers MUST NOT call commit() or own transaction boundaries (begin() / nested begin).
- Routes/orchestration layers own commit/rollback/atomic blocks.

2.2 Correlation Integrity — SOLD Stock-Out
- For SOLD stock-out, define effective_source_id as the value actually used to correlate FIFO/movements and CashEvent.
- Inventory journal source_id MUST equal effective_source_id.
- If caller does not provide a ref/source_id, a generated UUID is the effective_source_id and MUST be reflected in journal entries.

(3) CHANGES COMPLETED (STABILIZATION CLOSURE)
3.1 Transaction ownership audit status
- Service-layer audits for commit()/begin() within core/services show no matches in this pass.

3.2 Journal correlation wiring status (SOLD path)
- Correlation invariants are covered by tests asserting journal/source consistency against effective correlation id in both no-ref and provided-ref SOLD paths.

3.3 Invariant tests present
- test_stock_out_sold_without_ref_uses_generated_source_id_across_surfaces
- test_stock_out_sold_with_ref_uses_provided_source_id_across_surfaces

3.4 Handoff evidence pointer doc
- Added release handoff evidence pointer document for PR #478.

(4) EVIDENCE (REQUIRED FOR RELEASE READINESS)
4.1 Pytest
- Full suite status in this pass: 83 passed, 2 skipped.

4.2 Service-layer commit/begin audit
- rg -n "commit\(" core/services/ => no matches
- rg -n "begin\(" core/services/ => no matches

4.3 Canonical smoke harness execution
- Canonical smoke entrypoint: scripts/smoke.ps1
- Operator-run smoke log is authoritative evidence and must be attached to PR artifacts.
- If cleanup warnings are present but smoke concludes PASS, classify as non-blocking unless elevated by Release Agent.

(5) ACCEPTANCE CRITERIA (MERGE GATE)
Validation-complete when all are true:
- No service-layer commits/begins exist in stock mutation helper scope.
- SOLD stock-out journal source_id equals effective correlation id used by FIFO/movements and CashEvent.
- Correlation tests exist and pass.
- Canonical smoke harness passes with real operator execution evidence attached.
- Full pytest suite passes.
- No merge/tag performed as part of validation closure.


[DELTA HEADER]
SOT_VERSION_AT_START: v0.11.0
SESSION_LABEL: UI Hardening + Copilot Thread Closure (Fail-Closed UoM, Header Authority, NaN Guard)
DATE: 2026-02-25
SCOPE: documentation/governance record of changes already merged into branch
[/DELTA HEADER]

(1) OBJECTIVE
Record post-stabilization Copilot thread-closure outcomes already implemented on branch for UI hardening, launcher defensive behavior, and test-stub header authority handling, without introducing new backend/domain behavior. This governance delta is additive and aligned to v0.11.0 authority rules.

(2) CHANGES RECORDED
UI
- Inventory action flows removed default-to-`ea` UoM fallback in selectable item metadata and enforce fail-closed handling when UoM is absent.
- Stock-out/refund submit paths use explicit inline messaging: `UoM missing; cannot proceed.` and prevent proceeding without a provided unit.
- Purchase canonical payload now includes `unit_cost_cents` only when parsed value is finite (prevents invalid numeric serialization paths such as NaN-to-null artifacts).
- Manufacturing display formatting no longer injects `ea` as a default display unit.
- Manufacturing recent-runs panel applies UI-only grouping keyed by `source_id` for display labeling; no domain quantity/cost derivation was added.

Launcher
- Tray/logo image load path is guarded; failures produce a warning and use safe fallback imagery to avoid hard crash.

Test stub
- Local httpx shim now preserves caller-provided `Content-Type`; `application/json` is injected only when absent.

Tests
- Added regression coverage asserting caller `Content-Type` preservation in the httpx shim.
- Smoke test concatenated output key string remained intentionally unchanged; clarifying comment added to preserve test intent/readability.

(3) GOVERNANCE NOTES
- No UoM guessing/defaulting is permitted for action paths; missing UoM remains fail-closed.
- UI recent-runs grouping is presentation-only and does not compute or derive domain quantities, costs, or accounting outputs.
- No business logic expansion, no cost-authority math changes, no v2 quantity contract changes, and no backend validation relaxation are recorded in this delta.

(4) EVIDENCE
- UI fail-closed UoM and fallback removal: `core/ui/js/cards/inventory.js`, `core/ui/js/cards/manufacturing.js`.
- UI finite guard for purchase `unit_cost_cents`: `core/ui/js/api/canonical.js`.
- Launcher icon defensive guard: `launcher.py`.
- httpx shim header authority + regression test: `httpx/__init__.py`, `tests/test_httpx_stub_headers.py`.
- Smoke test intent comment: `tests/smoke/test_manufacturing_flow.py`.
- Verification evidence from closure pass: pytest passed (`84 passed, 2 skipped`).
- Canonical smoke harness (`scripts/smoke.ps1`) was not executed in Linux environment due to missing `pwsh`; operator-run Windows smoke evidence may be attached separately.

(5) ACCEPTANCE CRITERIA
Release-agent validation for this delta is complete when:
- `pytest` is re-run and passes in the target release environment.
- Canonical smoke harness is run via `scripts/smoke.ps1` in a suitable Windows/PowerShell-capable environment and results are attached.
- Spot-check confirms no reintroduction of UoM defaulting in action flows and no header-clobber behavior in the httpx shim.

[DELTA HEADER]
SOT_VERSION_AT_START: v0.11.0
SESSION_LABEL: BUS Core Lighthouse — Release Manifest Proxy + Aggregate Infra Counters + Discord Ops Channel
DATE: 2026-02-26
SCOPE: release distribution surface, update manifest hosting, aggregate counters, ops notifications (external to Core runtime)
[/DELTA HEADER]

(1) OBJECTIVE

Introduce BUS Core Lighthouse as an official TGC/BUS Core companion service that:

Proxies and normalizes the public update manifest used by Core's update-check feature (which is default-on / opt-out for checks and manual download only)

Core sot

Provides a stable “latest download” redirect endpoint for the website/app to use

Tracks only aggregate daily totals for:

update checks

latest-download clicks

operational errors

Posts periodic summaries to a dedicated Discord infrastructure channel for human monitoring

This service exists to harden the release/update surface without changing Core’s “no forced cloud” product posture.

(2) SYSTEM IDENTITY / OWNERSHIP

2.1 Name
BUS Core Lighthouse (“Lighthouse”)

2.2 Relationship to BUS Core

Lighthouse is a separate program/service owned by TGC and operated as part of the BUS Core ecosystem.

Lighthouse is not required for Core's local runtime to function; it exists to support configurable update checking and public release distribution.

2.3 Non-goals

Lighthouse is not a telemetry system.

Lighthouse does not identify users, does not maintain install IDs, and does not attempt to derive “active users.”

Lighthouse does not auto-update Core and does not run code on client machines.

(3) POLICY COMPATIBILITY WITH CORE (“NO TELEMETRY”)

Core’s product stance is local-first and “no forced cloud / no telemetry” 

Core sot

, and Core analytics are computed locally 

Core sot

.

Therefore Lighthouse is permitted only under these constraints:

Aggregate-only counting (daily totals)

No user identifiers (no install_id, no device ID, no account ID, no cookies)

No IP storage (no raw IP retention; no hashed IP uniqueness systems)

No behavioral profiling or cross-day user linking

Lighthouse is strictly an ops/release surface tool, not a product analytics channel

If Lighthouse is ever expanded beyond aggregate counters, it requires a new explicit SoT delta and must preserve Core’s default telemetry posture of “Disabled (local-only)” 

#TGC-BUS-Core SOT

.

(4) CANONICAL MANIFEST CONTRACT (PUBLIC)

4.1 Canonical manifest location (stable channel)
Core’s update system uses a hosted manifest URL configured under updates.manifest_url 

Core sot

. The canonical stable manifest is:

https://lighthouse.buscore.ca/update/check

4.2 Canonical manifest schema (minimum required fields)

The stable manifest MUST be valid JSON. Backward-compatible manifests MUST keep top-level strict SemVer `latest.version` and `latest.download.url` so deployed BUS Core clients can still detect updates and open the Lighthouse-provided download link. Newer Core clients may also consume additive metadata and channel-specific entries. Current hosted manifests include:

min_supported (string, SemVer x.y.z)

latest.version (string, SemVer x.y.z)

latest.release_notes_url (string URL)

latest.download.url (string URL)

latest.download.sha256 (string, lowercase hex)

latest.size_bytes (integer)

Optional future-compatible fields may include a top-level `channels` map, a top-level embedded `signature` object, and declared artifact metadata such as `latest.download.signature_url`, artifact kind/type/platform, publisher, and signer. These fields are additive and must not require removing or renaming top-level `latest.version` or `latest.download.url`.

4.3 Manifest determinism rules

The manifest is the single source of truth for “latest release” metadata.

Publishing a new release requires `core/version.py::VERSION`, the strict external release tag `v{VERSION}`, and hosted manifest metadata to agree. The release mirror workflow machine-checks that tag/version match before publishing manifest metadata.

Canonical public release assets referenced by Lighthouse/manifest metadata MUST use `BUS-Core-<VERSION>.zip` naming.

Manifest must never contain placeholders or non-JSON tokens. Release publication signs the manifest metadata with an embedded Ed25519 `signature` object. Manual update staging requires that signature to verify against Core's active pinned manifest public keys before download/extract/EXE trust work begins; read-only update check still preserves unsigned compatibility. Checksum, size, release-notes, artifact signature URL, publisher, signer, and artifact-kind fields are currently validated for shape and may be retained internally as declared manifest metadata.

(5) LIGHTHOUSE SERVICE CONTRACT

5.1 Public endpoints (canonical)

Lighthouse exposes a minimal public surface:

A) GET /update/check

Fetches the canonical manifest (updates.manifest_url equivalent) and returns it (proxy behavior).

Increments daily aggregate counter: update_checks.

Fail-soft: manifest fetch failures must not crash the service; return a clear error envelope.

B) GET /download/latest

Fetches the canonical manifest.

Extracts latest.download.url.

Increments daily aggregate counter: downloads.

Returns 302 redirect to the latest.download.url.

5.2 Storage model (aggregate daily totals only)

Lighthouse persists only daily totals (one row per day, UTC day key):

day (YYYY-MM-DD, UTC)

update_checks (int)

downloads (int)

errors (int)

No event log and no per-request storage is permitted in Lighthouse v1.

5.3 Ops notification (Discord)

Lighthouse posts periodic summary messages to a dedicated Discord channel via webhook.

Webhook URL is treated as a secret and must not be committed to public repositories.

Posting failures increment the errors counter.

(6) INTERACTION WITH CORE UPDATE CHECK SYSTEM

Core's Update Check system remains unchanged in product boundary:

Update checks are default-on / opt-out. Startup checks are one-shot and run only when `updates.enabled` is not false and `updates.check_on_startup` is not false.

Core sot

Manual "Check now" remains available. There is no auto-download, auto-install, staging, or update runner behavior.

Core sot

GET /app/update/check remains the canonical in-app one-shot check surface

Core sot

Manifest checksum, size, release-notes, and artifact signature-style metadata are declared manifest metadata. Core validates their shape and retains them internally; manual update staging requires a trusted signed manifest before using `sha256` and `size_bytes` to hash-verify a cached ZIP artifact. Read-only update check still does not require signatures.

Lighthouse is allowed to exist as the public manifest proxy + download redirect target that Core and the website can point at. This does not convert Core into a telemetry product.

(7) ACCEPTANCE CRITERIA

Lighthouse v1 is considered complete when:

GET /update/check returns the stable manifest successfully.

GET /download/latest redirects to latest.download.url from the manifest.

D1 (or equivalent storage) contains a daily row with incrementing:

update_checks

downloads

Discord webhook posting is verified by an observed message in the infra channel.

No user identifiers are stored, emitted, or derived.

Failure modes are fail-soft (manifest unavailable does not crash; counters tolerate storage errors).

(8) NON-COMPLIANCE (REGRESSIONS)

The following changes are regressions and forbidden without a new SoT delta:

Adding install IDs, client IDs, cookies, fingerprinting, or any user-unique identifier

Storing or hashing IPs for uniqueness

Event logging per request (“analytics events”) in Lighthouse

Auto-downloading or auto-installing updates

Making Core depend on Lighthouse for normal local operation

Background polling loops that violate Core's one-shot, default-on / opt-out update check posture

Core sot

# SoT DELTA — Update Check System — Default-on / Opt-out Manifest Fetch + SSRF Guards + Streaming Size Cap

SOT_VERSION_AT_START: v0.11.0
SESSION_LABEL: Update Check System — Default-on / Opt-out Manifest Fetch + SSRF Guards + Streaming Size Cap
DATE: 2026-02-28
BRANCH: updatecheck

## Scope
This delta documents the implemented in-app Update Check system behavior and hardening on branch `updatecheck`.

## Canonical Endpoint
- New endpoint: `GET /app/update/check`.
- Response contract remains exactly:
  - `current_version`
  - `latest_version`
  - `update_available`
  - `download_url`
  - `error_code`
  - `error_message`

## Config Surface (`updates.*`)
- `updates.enabled`: `true` (default)
- `updates.channel`: "stable" (default)
- `updates.manifest_url`: "https://lighthouse.buscore.ca/update/check" (default)
- `updates.check_on_startup`: `true` (default)

## Behavioral Gates
- Manual "Check now" is always allowed and calls `/app/update/check` even when `updates.enabled=false` or `updates.check_on_startup=false`.
- Startup check is gated at UI level only and runs one-shot only when:
  - `updates.enabled !== false`
  - `updates.check_on_startup !== false`
- No background polling loops are present. Phase 0A removed the hidden 15-minute stale recheck loop and `bus.updates.last_success_ms` tracking.
- No auto-download, auto-install, staging, update runner, or installer behavior was introduced.

## Safety / Hardening
- Strict SemVer enforcement for versions: `X.Y.Z` only.
- Timeout cap: 4 seconds.
- Redirects are not followed (`follow_redirects=False`); 3xx is treated as an error.
- Configured update channels are restricted to `stable`, `test`, `partner-3dque`, `lts-1.1`, and `security-hotfix`.
- Stable accepts backward-compatible top-level `latest.version` and `latest.download.url` manifests; non-stable channels require explicit `channels.<channel>`, top-level channel-keyed, or direct manifests with matching channel metadata.
- Deterministic SSRF blocking on manifest URL for:
  - `localhost` / `localhost.`
  - literal private, link-local, loopback, and `0.0.0.0` IP hosts
- Manifest is JSON-only (`Content-Type` must include `application/json` when present).
- Manifest read is streaming with a hard 64KB cap (`65536` bytes).
- Optional artifact metadata (`sha256`, `size_bytes`, `release_notes_url`, `signature_url`, artifact kind/type/platform, publisher, signer) is shape-validated when present and retained internally as declared manifest metadata by `ManifestRelease`.
- Read-only update check still surfaces compatible manifest discovery data without requiring signed manifests. Manual update staging requires a trusted signed manifest before any artifact hash/extract/EXE trust pipeline step.

## UI Behavior
- Settings includes update controls and manual “Check now”.
- When `update_available=true` and `download_url` is present, UI exposes a Download action using:
  - `window.open(url, '_blank', 'noopener')`
- Startup notice remains non-blocking and auto-hides.


# SoT DELTA — Finance Page — KPI Summary + Transaction History + Stock-Authority COGS

SOT_VERSION_AT_START: v0.11.0
SESSION_LABEL: Finance Page — KPI Summary + Transaction History + Stock-Authority COGS
DATE: 2026-02-28
BRANCH: financepage

## (1) UI SURFACE
- Added SPA route `#/finance`.
- Finance screen renders date range inputs, KPI summary tiles, and a transaction history table backed by finance read endpoints.

## (2) NEW READ ENDPOINTS
- `GET /app/finance/summary?from=YYYY-MM-DD&to=YYYY-MM-DD`
- `GET /app/finance/transactions?from=YYYY-MM-DD&to=YYYY-MM-DD&limit=N`

## (3) AUTHORITY RULES
- Units sold and COGS are derived from stock movements (`ItemMovement` with `source_kind="sold"`).
- Cash events with `kind="sale"` represent revenue intent and are grouped by `source_id` for sale totals in transaction aggregation.
- Purchase rows can appear in transaction history as `purchase_inferred`, sourced from `ItemMovement` where `source_kind="purchase"` (cash value may be unknown outside movement-derived inferred amount).

## (4) DETERMINISM / ANTI-DRIFT GUARDS
- Sales transaction aggregation uses explicit per-`source_id` grouping maps for cash totals, COGS totals, and created-at selection.
- Transaction ordering uses parsed timestamps with stable tie-breakers to ensure deterministic ordering.
- Regression coverage includes repeated summary-read guards to prevent double-counting drift across identical calls.


# SoT Delta

SOT_VERSION_AT_START: v0.11.1
SESSION_LABEL: Finance Stabilization — Delete Guard → Archive Model
DATE: 2026-03-04
BRANCH: work

## Finance Fail-Closed (Confirmed)

- Finance endpoints remain fail-closed when Item resolution fails.
- Missing Item during aggregation returns HTTP 400 with structured `item_not_found`.
- No silent skipping of orphaned history is permitted.

## Item Deletion Contract (Updated)

`DELETE /app/items/{id}` is dual-mode:

- If no history exists:
  - Hard delete occurs.
  - Returns `{ "ok": true }`.

- If any history exists (`ItemMovement`, `CashEvent`, `ManufacturingRun`):
  - Item is archived (`is_archived = true`).
  - Returns `{ "archived": true }`.
  - Hard delete is forbidden in this case.

- Repeated `DELETE` on archived item with history is idempotent and returns `{ "archived": true }`.

## Archive Semantics

- `items.is_archived BOOLEAN NOT NULL DEFAULT 0` added.
- `GET /app/items` excludes archived items by default.
- `GET /app/items?include_archived=true` returns all items.
- `GET /app/items/{id}` returns archived items normally.

Archived items remain resolvable for:

- Finance aggregation
- Ledger joins
- Historical queries

## Smoke Isolation

- `scripts/smoke_isolated.ps1` introduced.
- Smoke now forces temporary `BUS_DB` path.
- Working DB cannot be mutated by smoke runs.

## Invariants (Unchanged)

- Backend remains authority for finance math.
- No float math introduced.
- COGS derived only from sold stock movements.
- No cascade delete of ledger history.
## SoT Delta

SOT_VERSION_AT_START: v0.11.0  
SESSION_LABEL: First-Run Onboarding — System State Probe + Welcome Wizard + Readiness Status  
DATE: 2026-02-28  
BRANCH: firstrunwiz

### Backend: `/app/system/state` boot probe

- New endpoint: `GET /app/system/state`.
- Response includes:
  - `is_first_run`
  - `counts` (deterministic `COUNT_KEYS` order)
  - `demo_allowed`
  - `basis`
  - `build`
  - `status`

### First-run criteria

- `is_first_run` is `true` only when all tracked counts are `0`.
- `demo_allowed` mirrors `is_first_run`.

### Additive build metadata

- `build.version`
- `build.schema_version`

### Additive readiness status

- `status="empty"` when `is_first_run` is `true`.
- `status="needs_migration"` when data is non-empty and `build.schema_version == "baseline"`.
- `status="ready"` otherwise.

### UI behavior

- New route: `#/welcome`.
- Route guard behavior:
  - ensures token first,
  - fetches `/app/system/state`,
  - redirects only when first-run and onboarding is not completed and route is not allowlisted,
  - fail-soft behavior: if system-state fetch fails or payload is invalid, no redirect is applied.
- Settings includes **Run onboarding** action that clears onboarding completion flag and routes to `#/welcome`.

### Error behavior (documented)

- On backend failure, `/app/system/state` raises stable detail `"system_state_unavailable"`.
- Response envelope follows canonical global HTTP exception normalization (string detail normalized by global handler into the standard `detail` object shape).

## SoT Delta

SOT_VERSION_AT_START: v0.11.0  
SESSION_LABEL: Canonical UI Entry Point — Hash-Free Launch for Deterministic First-Run  
DATE: 2026-03-04  
BRANCH: main

### Canonical entry URL

- Canonical launcher/open entry URL is `/ui/shell.html` with **no hash fragment**.
- Launchers must not pre-seed `#/home` (or any route hash) at browser-open time.

### First-run routing authority

- First-run routing decision remains in SPA boot logic using `/app/system/state` plus local onboarding completion flag (`bus.onboarding.completed`).
- Manual deep links that include hashes (for example `#/manufacturing`) remain supported and are not overridden by launcher URL construction.

### Files updated in this delta

- `launcher.py`
- `scripts/up.ps1`
- `scripts/up.sh`
- `README.md`

## SoT Delta

SOT_VERSION_AT_START: v0.12.0  
SESSION_LABEL: Deterministic Demo Mode + Mandatory EULA  
DATE: 2026-03-04  
BRANCH: demo-mode-first-run

Summary:

BUS Core now ships with deterministic demo mode for onboarding.

Behavior:

Fresh installs launch into demo mode using a pre-seeded demo database.

The onboarding wizard runs automatically and requires EULA acceptance.

After onboarding users may convert the system to production mode using the "Start Fresh Shop" action.

Production mode initializes a new empty database and disables demo functionality.

Scope:

- Adds runtime database mode support.
- Introduces demo database.
- Adds EULA requirement during onboarding.
- Adds system endpoint to transition from demo to production.

Acceptance Criteria:

Fresh install produces deterministic demo environment and onboarding wizard with EULA gate.
Transition to production mode results in clean database with no demo data.

## SoT Delta

SOT_VERSION_AT_START: v0.12.0  
SESSION_LABEL: v1.0.0 Release Preparation  
DATE: 2026-03-04  
BRANCH: main

### Summary

BUS Core v1.0.0 establishes the system as a stable, local-first manufacturing ledger kernel with deterministic first-run behavior and controlled update signaling.

### Key Capabilities

- Deterministic database initialization.
- Canonical API contract.
- Stable ledger and inventory movement model.
- Manufacturing run tracking.
- Financial profit calculation endpoints.
- Deterministic onboarding wizard.

### First-Run Behavior

Fresh installs now initialize into demo mode using a pre-seeded demo database.

The onboarding wizard launches automatically and requires explicit EULA acceptance before the user may enter the application.

After onboarding, the system exposes a "Start Fresh Shop" action that initializes a clean production database and disables demo mode.

### Runtime Modes

BUS Core supports two runtime modes:

demo
- Uses demo database.
- Onboarding wizard active.
- Demo banner visible.

production
- Uses standard database.
- Wizard disabled.
- Demo indicators removed.

### Acceptance Criteria

A fresh installation must:

- Launch BUS Core successfully.
- Detect first-run state.
- Start onboarding wizard.
- Require EULA acceptance.
- Present demo dataset.
- Allow deterministic transition to production database.

These conditions define the stable baseline for BUS Core v1.0.0.

## SoT Delta

SOT_VERSION_AT_START: v0.12.0  
SESSION_LABEL: Pre-1.0 UX hardening — EULA viewer, inventory quantity fix, settings layout cleanup  
DATE: 2026-03-05  
BRANCH: pre1.0-polish  

### EULA Viewer

The onboarding EULA step now loads `/EULA.md` dynamically and displays it in a scrollable container.

Acceptance checkbox remains disabled until the user scrolls to the end of the document.

This ensures the user must at least reach the end of the license before continuing.

### Inventory Rendering

Inventory UI previously rendered quantity objects directly, producing `[object Object]`.

Renderer now extracts the numeric quantity field only.

Backend schema remains unchanged.

### Settings Layout

Settings page reorganized into logical UI cards:

System  
Updates  
Interface  
Data Management

This change is purely visual and does not modify configuration logic.

## SoT Delta

SOT_VERSION_AT_START: v0.12.0  
SESSION_LABEL: Pre-1.0 UX hardening follow-up — EULA listener guard, CSS variable fix, EULA persistence  
DATE: 2026-03-05  
BRANCH: pre1.0-polish  

### EULA Viewer Hardening

Scroll listener now attaches only once to prevent duplicated handlers after re-renders.

Checkbox also unlocks when the EULA content fits entirely within the viewer container.

### EULA Persistence

Acceptance of the BUS Core EULA is now stored in localStorage so returning users are not forced to accept again.

### CSS Token Alignment

EULA viewer and settings layout styles updated to use BUS Core theme tokens:

--border-color  
--card-bg

