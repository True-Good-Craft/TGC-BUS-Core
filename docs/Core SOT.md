# 🛠️ TGC BUS Core — Unified Source of Truth

**Version:** v0.11.0

**Updated:** 2026‑02‑19

**Status:** Beta

**Authority:** Code is truth. Where this document and code disagree, update this document.

---

## 1. Identity & Purpose

* 
**Company:** True Good Craft (TGC).


* 
**Product:** TGC BUS Core (Business Utility System).


* 
**Audience:** Small/micro shops (1–10 person teams), makers, and anti‑SaaS owners.


* **Primary Value:** Local-first data sovereignty. Keep inventory, manufacturing, and contacts on the owner’s machine without forced cloud or telemetry.



---

## 2. Architecture & Stack

### 2.1 Technical Stack

* 
**Backend:** Python 3.12 / FastAPI using a factory callable (`core.api.http:create_app`).


* 
**Database:** SQLite via SQLAlchemy ORM.


* 
**UI:** Single-page application (SPA) shell (`core/ui/shell.html`) with modular JS cards.


* 
**Server:** Uvicorn at `127.0.0.1:8765` (Local) or `0.0.0.0:8765` (Docker).



### 2.2 Deployment Modes

* 
**Native Windows:** Uses `%LOCALAPPDATA%\BUSCore\` for DB, config, and journals. Launch via `scripts/launch.ps1`.


* **Docker:** Uses `python:3.12-slim`. Persistence via volume mounted at `/data` (e.g., `BUS_DB=/data/app.db`). Runs as non-root `appuser`.



---

## 3. Domain Model & Invariants

### 3.1 Quantity & Cost Contracts

* 
**Normalization:** All operations must use decimal inputs (`quantity_decimal`, `unit_cost_decimal`) and normalize to integers via centralized helpers.


* 
**Storage:** Persisted strictly as `quantity_int` (base units) and `unit_cost_cents`.


* 
**Base Units:** Length (mm), Area (mm²), Volume (mm³), Weight (mg), Count (1 ea = 1000 milli-units).



### 3.2 Inventory & FIFO

* **FIFO Authority:** The oldest batches are consumed first; `unit_cost_cents` is copied 1:1 from batch to movement.


* 
**Valuation:** Inventory Value = `qty_on_hand` × `last_known_unit_cost`.


* 
**Atomicity:** Operations mutating both inventory and cash MUST occur inside a single DB transaction.



---

## 4. Feature Systems

### 4.1 Update Check System (New in v0.11.0)

* 
**Opt-in Only:** Disabled by default; no background threads or auto-installs.


* 
**Config:** Managed via `updates` section in `config.json` (enabled, channel, manifest_url).


* **Invariants:** Strict SemVer (x.y.z) required. Manifest fetches time out at 4 seconds.


* 
**UI:** Non-blocking banner appears if an update is found; manual download/verification required.



### 4.2 Manufacturing (Recipes & Runs)

* 
**Recipes:** Definitions for production (Canonical term: "Recipes," not "Blueprints").


* **Runs:** Execution is atomic. Output unit cost = total consumed cost / output qty.


* 
**Capacity:** Calculated based on the limiting component: `floor(on_hand / qty_required)`.



### 4.3 Onboarding & Demo

* 
**System State:** System emptiness is determined by the backend (`/app/system/state`), not UI flags.


* **Demo Loader:** Loads "AvoArrow Aeroworks" scenario. Must abort if existing data is present.



---

## 5. API & UI Routing

### 5.1 Key API Endpoints

* 
`GET /app/system/state`: First-run detection.


* 
`POST /app/stock/out`: Atomically handles sales/stock removal.


* 
`GET /app/update/check`: One-shot fetch for new versions (fail-soft).


* 
`POST /app/config`: Supports partial updates via deep merge.



### 5.2 UI Routes (SPA)

* 
`#/welcome`: Onboarding wizard.


* 
`#/home`: Dashboard (must fit one screen without scrolling).


* 
`#/finance`: Profit/loss and cashflow.


* 
`#/inventory`: Items and batch management.



---

## 6. Security & Stability

* **Dev Mode:** Enabled via `BUS_DEV=1`. Enables `/dev/*` routes and detailed error traces.


* **Backups:** Encrypted AES-GCM backups. Restore process triggers a maintenance mode and journal archiving.


* 
**No Telemetry:** All analytics are computed locally from the SQLite DB.



---

[DELTA HEADER]
SOT_VERSION_AT_START: (not specified in session)
SESSION_LABEL: UOM normalization + canonical endpoint enforcement – Phase 0–1 Lock
DATE: 2026-02-20
SCOPE: units, normalization, routing, endpoint canonicalization, deprecation
[/DELTA HEADER]

(1) OBJECTIVE

Lock and enforce:
1) Canonical Unit-of-Measurement (UOM) model
2) Canonical API endpoint surface
3) Deprecation policy for legacy endpoints
4) Drift-prevention rules between UI and backend

This delta establishes binding contracts. No alternative interpretations are allowed going forward.

---

(2) CANONICAL UNIT MODEL (BINDING)

2.1 Base Units (Storage Layer)

All inventory quantities MUST be stored internally as integer base units.

Canonical base units by dimension:

- length  → mm
- area    → mm2
- volume  → mm3
- weight  → mg
- count   → mc  (milli-count)

No other base unit is permitted.

2.2 Human Units

Human-facing units (UI input/output) MAY include:

- length: mm, cm, m
- area: mm2, cm2, m2
- volume: mm3, cm3, ml, l
- weight: mg, g, kg
- count: mc, ea

2.3 Count Dimension Rule (Critical)

The base unit for count is mc (milli-count).

- 1 ea = 1000 mc
- All count storage MUST use mc internally.
- ea MUST NEVER be used as a storage base.

Any code assuming ea is base=1 is non-compliant.

2.4 Normalization Authority

All quantity writes MUST pass through the canonical backend helper:

    normalize_quantity_to_base_int(quantity_decimal: str, uom: str, dimension: str) -> int

UI MUST NOT perform scaling multipliers.
UI MUST NOT convert to base units.
UI MUST send:

    {
      "quantity_decimal": "<string>",
      "uom": "<unit>"
    }

The backend is the single authority for unit conversion.

2.5 UI Drift Prevention Rule

The UI:

- MUST NOT contain hardcoded unit multipliers.
- MUST NOT multiply or divide by 10/100/1000 for storage purposes.
- MUST NOT store base unit integers client-side.

All multipliers live exclusively in backend conversion logic.

---

(3) CANONICAL API SURFACE (BINDING)

The following endpoints are the canonical public application surface:

Inventory & Ledger:

- POST  /app/stock/in
- POST  /app/stock/out
- POST  /app/purchase
- GET   /app/ledger/history

Manufacturing:

- POST  /app/manufacture

These endpoints are the authoritative names.
UI MUST use only these canonical paths.

---

(4) LEGACY ENDPOINT DEPRECATION POLICY

If legacy endpoints exist (examples include but are not limited to):

- /app/stock_in
- /app/manufacturing/run
- /app/ledger/movements
- /app/movements

They MUST be treated as deprecated compatibility layers.

4.1 Deprecation Requirements

Legacy endpoints:

- MAY remain temporarily for compatibility.
- MUST internally delegate to canonical handlers.
- MUST emit header:

    X-BUS-Deprecation: <canonical endpoint path>

Example:

    X-BUS-Deprecation: /app/stock/in

4.2 No Dual Logic Rule

There MUST NOT be duplicated business logic between canonical and legacy endpoints.
Canonical endpoints are the single source of truth.
Legacy endpoints are thin wrappers only.

---

(5) CONTRACT ENFORCEMENT RULES

5.1 Quantity Contract

All inventory-affecting endpoints MUST accept:

    quantity_decimal (string)
    uom (string)

Endpoints MUST reject legacy fields such as:

    qty
    qty_base
    quantity_int
    raw_qty

5.2 Manufacturing Contract

POST /app/manufacture MUST accept:

- Output quantity via normalized contract
- Component quantities via normalized contract
- All normalization performed server-side

5.3 Ledger Surface

GET /app/ledger/history is the canonical read surface for movement history.

UI MUST NOT call internal ledger routes or alternate naming variants.

---

(6) NON-COMPLIANCE DEFINITION

The following are considered drift and MUST be corrected if discovered:

- UI-side unit multipliers
- Count dimension stored as ea base=1
- UI calling non-canonical endpoints
- Multiple endpoint names performing identical logic without deprecation headers
- Any direct base-unit entry in UI

---

(7) ACCEPTANCE CRITERIA FOR PHASE 0–1

Phase 0–1 is complete when:

1) Canonical endpoints exist and are routable.
2) Legacy endpoints delegate and emit deprecation headers.
3) No duplicate business logic exists between route variants.
4) Base unit for count is mc across system.
5) UI contract for quantity is human decimal + uom only.
6) Tests confirm canonical endpoint availability.

This delta establishes the locked contract for all future unit and routing work.

END OF DELTA

[DELTA HEADER]
SOT_VERSION_AT_START: v0.11.0
SESSION_LABEL: Manufacturing validation hardening + deterministic smoke enforcement
DATE: 2026-02-22
SCOPE: manufacturing validation, shortage behavior, test determinism, smoke contract enforcement
[/DELTA HEADER]

(1) OBJECTIVE

Lock and formalize:

1) Deterministic manufacturing shortage behavior
2) Deterministic integration smoke testing
3) Removal of diagnostic instrumentation
4) Enforcement of non-mutating validation tests
5) Atomic shortage failure semantics

This delta converts previously verified behavior into binding system contract.

---

(2) MANUFACTURING SHORTAGE CONTRACT (BINDING)

2.1 Validation Authority

The authoritative shortage validation path is:

    validate_run(session, body)

It MUST:

- Compute required base quantities via canonical normalization.
- Compare required base quantities to on-hand base quantities.
- Produce structured shortages when required > on_hand.
- Perform no writes.
- Perform no inventory mutation.

2.2 Shortage Response Behavior

If shortages exist:

- A failed ManufacturingRun record MUST be created.
- The API MUST return HTTP 400.
- Response body MUST include:
    {
      "error": "insufficient_stock",
      "shortages": [...],
      "run_id": <failed run id>
    }

200 responses on shortage conditions are prohibited.

2.3 Determinism Rule

Manufacturing shortage evaluation MUST be purely arithmetic:

    shortage_amount = max(required_base - on_hand_base, 0)

No floating arithmetic.
No rounding drift.
All quantities MUST be integers at validation time.

2.4 No Silent Recovery

Manufacturing logic MUST NOT:

- Auto-adjust inventory.
- Auto-top-up missing components.
- Retry inside handler.
- Convert shortage into partial execution.

Shortage always aborts execution.

---

(3) MANUFACTURING SUCCESS CONTRACT (BINDING)

3.1 Atomic Execution

execute_run_txn(...) MUST:

- Allocate FIFO slices under DB lock.
- Record all input movements.
- Create output batch with computed unit_cost_cents.
- Append journal entry.
- Update qty_stored.
- Complete in a single transaction.

3.2 Cost Calculation Rule

Per-output unit cost MUST be:

    round_half_up_cents(total_input_cost_cents / output_qty_base)

Division by zero is prohibited.
All quantities MUST be integer base units.

---

(4) SMOKE TEST DETERMINISM CONTRACT

4.1 Smoke Must Not Mutate to Pass

Integration smoke tests MUST:

- Assert behavior.
- NOT auto-adjust stock to recover from failures.
- NOT retry failed manufacturing runs by mutating inventory.

Smoke must never alter business state to satisfy expected outcome.

4.2 Deterministic Shortage Values

Shortage tests MUST use impossible deterministic quantities:

Example:

    output_qty = 1000000
    qty_required = 1000000

Values must exceed realistic stock to guarantee shortage regardless of prior test state.

Smoke must not depend on previous inventory levels.

4.3 Progressive Test Flow (Canonical Order)

Smoke integration flow MUST follow this order:

1) Session acquisition
2) Items definition
3) Contacts CRUD
4) Inventory adjustments
5) FIFO purchase + consume
6) Recipe management
7) Manufacturing success case
8) Manufacturing shortage (recipe)
9) Manufacturing shortage (adhoc)
10) Export / Import / Restore
11) Cleanup

Shortage tests MUST execute after successful manufacturing.

---

(5) DIAGNOSTIC INSTRUMENTATION POLICY

Temporary diagnostic instrumentation:

- VALIDATE_RUN DEBUG prints
- Route hit debug prints
- Startup route dumps

MUST NOT exist in production code.

Debug-only tracking variables introduced for investigation
MUST be removed before merge.

Production console output must remain clean except for:

- Startup banner
- Trust mode banner
- Structured request logs

---

(6) TESTING LEVEL DEFINITION

System now enforces three validation layers:

6.1 Unit Tests (pytest)
- Validate normalization logic.
- Validate FIFO allocation.
- Validate shortage detection.
- Validate deprecation headers.
- Validate endpoint contracts.

6.2 Integration Smoke
- Exercises full HTTP surface.
- Validates movement ledger correctness.
- Validates manufacturing cost propagation.
- Validates shortage 400 responses.
- Validates export/import cycle.
- Validates cleanup invariants.

6.3 Transactional Integrity
- Manufacturing run is atomic.
- Restore process enforces exclusive DB handle.
- No partial writes permitted on shortage.

---

(7) ACCEPTANCE CRITERIA — MANUFACTURING HARDENING COMPLETE

Phase complete when:

1) Manufacturing shortage returns 400 deterministically.
2) Manufacturing success returns 200 deterministically.
3) Smoke passes on fresh DB twice consecutively.
4) pytest passes fully.
5) No debug instrumentation remains.
6) No float-based shortage calculations exist.
7) No auto-recovery logic exists in smoke.

All criteria satisfied as of this delta.

---

(8) NON-COMPLIANCE DEFINITION

The following are considered regressions:

- Shortage returns 200.
- Float quantities appear in shortage payload.
- Smoke mutates stock to satisfy expectations.
- Manufacturing retries internally.
- Debug logging left in production code.
- Partial manufacturing execution on insufficient stock.

Such regressions require immediate correction.

---

END OF DELTA


[DELTA HEADER]
SOT_VERSION_AT_START: v0.11.0
SESSION_LABEL: Manufacturing Quantity Contract v2 + Cost Authority Lock
DATE: 2026-02-22
SCOPE: unit storage authority, costing correction, canonical endpoint enforcement
SUPERSEDES: All prior deltas defining per_output_cents against base units
[/DELTA HEADER]
```

---

# (1) OBJECTIVE

This delta formally establishes:

1. A single authoritative quantity storage model.
2. A single authoritative costing model.
3. A locked canonical endpoint surface.
4. A strict separation between API, service, and storage units.

All manufacturing logic must conform to this delta.

---

# (2) STORAGE CONTRACT (ABSOLUTE)

## 2.1 Base-Unit Storage Rule

All persisted inventory quantities are stored as **base-unit integers only**.

This includes:

* ItemBatch.qty_remaining
* ItemMovement.qty_change
* ManufacturingRun.output_qty_base
* FIFO allocations
* Journal records

No floats may be persisted.

No Decimal may be persisted.

No human units may be persisted.

---

## 2.2 Canonical Multiplier Authority

The only valid base conversion is:

```
normalize_quantity_to_base_int(
    quantity_decimal: str,
    uom: str,
    dimension: str
) -> int
```

This function must:

* Use Decimal arithmetic
* Apply canonical_multiplier(dimension, uom)
* Use ROUND_HALF_UP to nearest base integer
* Return int

No other multiplication logic is permitted anywhere in backend code.

Grep rule:
No `* 100`, `* 1000`, `* 1e` may exist outside canonical helper.

---

# (3) COST AUTHORITY (BINDING)

## 3.1 Definition of unit_cost_cents

`unit_cost_cents` is defined as:

> Integer cents per human unit (`item.uom`), never per base unit.

This definition applies globally:

* Manufacturing output valuation
* Inventory valuation
* FIFO batch valuation
* Finance COGS calculation
* Profit reporting

There is no scenario where unit_cost_cents refers to base units.

---

## 3.2 Manufacturing Output Cost Formula (Corrected)

The only valid per-output cost calculation is:

```
human_output_qty =
    output_qty_base / canonical_multiplier(dimension, item.uom)

per_output_unit_cost_cents =
    round_half_up_cents(
        total_input_cost_cents / human_output_qty
    )
```

Dividing cents by base units is forbidden.

---

## 3.3 COGS Formula

COGS must be calculated as:

```
human_qty =
    qty_base / canonical_multiplier(dimension, item.uom)

cogs_cents +=
    round_half_up_cents(unit_cost_cents * human_qty)
```

Multiplying unit_cost_cents by base quantities is forbidden.

---

# (4) SERVICE LAYER CONTRACT

## 4.1 Entry Boundary

All inventory-mutating service functions must:

1. Accept human quantities from API layer.
2. Immediately normalize to base int.
3. Use base int for all internal comparisons and math.

After normalization:

* No float arithmetic allowed.
* No epsilon comparisons allowed.
* No variable may ambiguously represent both human and base.

Naming rule:

* qty_base
* qty_human

Ambiguous variable names (qty, amount, k reused) are forbidden.

---

## 4.2 Shortage Detection Rule

Shortage comparison must be:

```
if on_hand_base < required_base:
```

Both operands must be int.

Float comparisons are forbidden.

---

# (5) API BOUNDARY CONTRACT

## 5.1 Canonical Payload Shape

All canonical inventory-mutating endpoints must accept:

```
{
  "quantity_decimal": "<string>",
  "uom": "<string>"
}
```

No canonical endpoint may accept:

* qty
* qty_base
* quantity_int

---

## 5.2 Canonical Endpoint Surface (Locked)

The canonical public surface is:

* POST /app/stock/in
* POST /app/stock/out
* POST /app/purchase
* GET  /app/ledger/history
* POST /app/manufacture

These endpoints contain business logic.

---

## 5.3 Legacy Wrapper Rule

Any non-canonical endpoint:

* Must contain no business logic.
* Must translate legacy payload → canonical payload.
* Must call canonical handler directly.
* Must emit header:

```
X-BUS-Deprecation: <canonical path>
```

Duplicate logic between canonical and legacy endpoints is prohibited.

---

# (6) ROUNDING RULES

## 6.1 Base Normalization

Normalization uses:

* Decimal
* ROUND_HALF_UP
* Return int

## 6.2 Cost Rounding

Cost rounding uses:

```
round_half_up_cents()
```

No float-based rounding allowed.

---

# (7) INVARIANTS (ENFORCED)

The following must always be true:

I1: All DB quantity columns are int.

I2: No epsilon comparisons exist in manufacturing.

I3: unit_cost_cents is per human unit only.

I4: No Decimal reaches JSON serialization.

I5: FIFO operates exclusively on base ints.

I6: No backend code multiplies by hardcoded 100/1000 outside canonical helper.

---

# (8) NON-COMPLIANCE

The following require immediate rejection in review:

* Dividing cents by base units.
* Multiplying unit_cost_cents by base units.
* Float arithmetic in inventory comparisons.
* Business logic inside legacy wrappers.
* Ambiguous quantity variables.
* Endpoint drift from canonical surface.

---

END OF DELTA

