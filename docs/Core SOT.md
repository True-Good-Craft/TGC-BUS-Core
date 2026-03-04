# 🛠️ TGC BUS Core — Unified Source of Truth

**Version:** v0.11.0 (Reflecting Phase 0–1 Locks, Cost Authority & Manufacturing Hardening) **Updated:** 2026‑02‑22 **Status:** Beta **Authority:** Code is truth. Where this document and code disagree, update this document.

---

## 1. Identity & Purpose

* 
**Company:** True Good Craft (TGC).


* 
**Product:** TGC BUS Core (Business Utility System).


* 
**Audience:** Small/micro shops (1–10 person teams), makers, and anti‑SaaS owners.


* 
**Primary Value:** Local-first data sovereignty. Keep inventory, manufacturing, and contacts on the owner’s machine without forced cloud or telemetry.



---

## 2. Architecture & Deployment

### Technical Stack

* 
**Backend:** Python 3.12 / FastAPI using a factory callable (`core.api.http:create_app`).


* 
**Database:** SQLite via SQLAlchemy ORM.


* 
**UI:** Single-page application (SPA) shell (`core/ui/shell.html`) with modular JS cards.


* 
**Server:** Uvicorn at `127.0.0.1:8765` (Local) or `0.0.0.0:8765` (Docker).



### Deployment Modes

* 
**Native Windows:** Uses `%LOCALAPPDATA%\BUSCore\` for DB, config, and journals. Launch via `scripts/launch.ps1`.


* 
**Docker:** Uses `python:3.12-slim`. Persistence via volume mounted at `/data` (e.g., `BUS_DB=/data/app.db`). Runs as non-root `appuser`.



---

## 3. Canonical Unit Model & Storage Contract

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


* 
**General Setup:** `GET /app/system/state` (First-run detection), `GET /app/update/check` (One-shot fetch), `POST /app/config`.


* UI MUST use only these canonical paths. `GET /app/ledger/history` is the canonical read surface for movement history.



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
**Opt-in Only:** Disabled by default; no background threads or auto-installs.


* 
**Config:** Managed via `updates` section in `config.json` (enabled, channel, manifest_url). Strict SemVer required, and fetches time out at 4 seconds.


* 
**UI:** Non-blocking banner appears if an update is found.



### Onboarding & Demo

* System emptiness is determined strictly by the backend (`/app/system/state`).


* The "AvoArrow Aeroworks" Demo Loader must abort if existing data is present.



---

## 9. Security & Diagnostics

* **Dev Mode:** Enabled via `BUS_DEV=1`. Enables `/dev/*` routes and detailed error traces.


* **Backups:** Encrypted AES-GCM backups. Restore process triggers maintenance mode and journal archiving.


* 
**No Telemetry:** All analytics are computed locally from the SQLite DB.


* 
**Diagnostic Instrumentation Policy:** Temporary diagnostic instrumentation (e.g., debug prints, route dumps) MUST NOT exist in production code. Debug-only tracking variables must be removed before merge.



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

