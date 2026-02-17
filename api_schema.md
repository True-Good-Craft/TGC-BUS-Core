# BUS Core API Schema — Hardened & Automation-Grade
> **Version:** Hardened Implementation (February 2026)  
> **Base URL:** `http://127.0.0.1:8765`  
> **Authentication:** Cookie-based via GET `/session/token`  
> **Scope:** Core ledger, manufacturing, finance, items, vendors, recipes endpoints  
> **Status:** Reconciled against live FastAPI routes & Pydantic models & smoke.ps1  

---

## Table of Contents

0. [Authentication Flow](#authentication-flow-authoritative)
1. [Route Reconciliation Report](#route-reconciliation-report)
2. [Canonical Contracts](#canonical-contracts)
3. [Items Endpoints](#items-endpoints)
4. [Vendors Endpoints](#vendors-endpoints)
5. [Recipes Endpoints](#recipes-endpoints)
6. [Manufacturing Endpoints](#manufacturing-endpoints)
7. [Ledger & Inventory Endpoints](#ledger--inventory-endpoints)
8. [Finance Endpoints](#finance-endpoints)
9. [Dashboard Endpoints](#dashboard-endpoints)
10. [Behavioral Invariants](#behavioral-invariants)
11. [Deterministic Test Data Creation Order](#deterministic-test-data-creation-order)
12. [Deferred Sections (Core-Only Scope)](#deferred-sections-core-only-scope)
13. [Schema Drift Report](#schema-drift-report)
14. [OpenAPI 3.0.0 Specification](#openapi-300-specification)

---

## Authentication Flow (Authoritative)

**Source of Truth:** [scripts/smoke.ps1](scripts/smoke.ps1) (lines 167–183)

### Session Establishment

1. **Call GET /session/token** (no request body required)
   ```
   GET http://127.0.0.1:8765/session/token
   ```

2. **Server responds with HTTP 200** and sets a session cookie
   ```
   Set-Cookie: <cookie_name>=<cookie_value>; Path=/; ...
   ```

3. **Client must persist the cookie** (via session object or cookie jar)
   - **Python (requests):** Use `requests.Session()` — cookies persist automatically
   - **PowerShell:** Use `Invoke-RestMethod -WebSession $session` — cookies persist automatically
   - **JavaScript (fetch):** Use `credentials: 'include'`
   - **Manual cookie management:** Extract cookie from Set-Cookie header, include in Cookie header on all subsequent requests

4. **Reuse cookie on all `/app/*` endpoints**
   ```
   GET /app/items
   Cookie: <cookie_name>=<cookie_value>
   ```

5. **Result:** HTTP 200; 401 if cookie missing or expired

### Key Behaviors

| Behavior | Details |
|----------|---------|
| **Method** | GET (not POST) |
| **No Request Body** | Empty or omitted |
| **Cookie Persistence** | Server sets cookie; client reuses automatically |
| **Cookie Name** | Varies by deployment (e.g., `bus_session`, `session`, `sessionid`) |
| **Cookie Scope** | All `/app/*` endpoints require valid cookie |
| **Expiration** | Implementation-dependent; re-call `/session/token` if 401 occurs |
| **CSRF Headers** | Not required for GET /session/token |

### Client Examples

**Python (requests.Session):**
```python
session = requests.Session()
session.get("http://127.0.0.1:8765/session/token")
# Cookies now persisted in session.cookies
response = session.get("http://127.0.0.1:8765/app/items")
```

**PowerShell (Invoke-RestMethod):**
```powershell
$session = New-Object Microsoft.PowerShell.Commands.WebRequestSession
Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:8765/session/token" -WebSession $session
# Cookies now persisted in $session.Cookies
$response = Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:8765/app/items" -WebSession $session
```

---

## Route Reconciliation Report

### Summary

| Area | Endpoints | Status | Notes |
|------|-----------|--------|-------|
| **Items** | 6 | ✓ Implemented | GET list, GET detail, GET summary, POST, PUT, DELETE |
| **Vendors** | 5 + 5 (contacts facade) | ✓ Implemented | CRUD + parallel contacts endpoints |
| **Recipes** | 5 | ✓ Implemented | GET list, GET detail, POST, PUT, DELETE |
| **Manufacturing** | 3 | ✓ Implemented | POST run, GET runs, GET history |
| **Ledger** | 8 | ✓ Implemented | purchase, consume, adjust, stock/out, valuation, movements, stock_in, debug/db |
| **Finance** | 4 | ✓ Implemented | expense, refund, profit, cash-event |
| **Dashboard** | 1 | ✓ Implemented | GET summary |
| **Transactions** | 2 | ⚠ **UNIMPLEMENTED (STUBS)** | `/app/transactions/summary`, `/app/transactions` return placeholder responses |

**Total Core Endpoints:** 34 implemented + 2 stubs = 36 documented  
**Audit Date:** 2026-02-17  
**Source Files:** `core/api/routes/{items,vendors,recipes,manufacturing,ledger_api,finance_api,dashboard_api,transactions}.py`

### Key Findings

1. **Fully Reconciled:** All documented core endpoints match actual FastAPI routes
2. **Sales Endpoint:** No standalone `POST /app/finance/sale`. Sales created via `POST /app/ledger/stock/out?reason=sold&record_cash_event=true` (atomic inventory + cash event)
3. **Quantity Contract:** All inventory endpoints enforce `quantity_decimal` (string) + `uom` input; legacy `qty` field rejected
4. **Monetary Fields:** All costs stored as integers (cents): `unit_cost_cents`, `amount_cents`, `unit_price_cents`
5. **Transaction Stubs:** `/app/transactions/summary` and `/app/transactions` currently return placeholder `{"stub": true}` responses; flagged for future implementation or removal

---

## Canonical Contracts

### Quantity Contract (Normalization)

**Input Format:**
- **Field:** `quantity_decimal` (required in POST/PUT body)
- **Type:** string
- **Constraint:** Must parse to `Decimal`, > 0
- **Processing:** Validated by `normalize_quantity_to_base_int()` in [core/api/quantity_contract.py](core/api/quantity_contract.py)

**Storage Format:**
- **Internal:** Integer (base units)
- **Calculation:** `quantity_decimal` × `UNIT_MULTIPLIER[dimension][uom]` = `qty_base_int`
- **Example:** dimension='weight', uom='kg', quantity_decimal='10.5' → qty_base_int=1050 (100× multiplier)

**UOM Multipliers (Extracted from core/metrics/metric.py UNIT_MULTIPLIER):**

| Dimension | UOM | Base Unit | Multiplier | Example |
|-----------|-----|-----------|-----------|---------| 
| `count` | `mc`, `ea` | mc (micro-count) | 1, 1000 | 1 ea = 1,000 base units |
| `weight` | `mg`, `g`, `kg` | mg (milligram) | 1, 1000, 1000000 | 1 g = 1,000 base units; 1 kg = 1,000,000 base units |
| `length` | `mm`, `cm`, `m` | mm (millimeter) | 1, 10, 1000 | 1 cm = 10 base units; 1 m = 1,000 base units |
| `area` | `mm2`, `cm2`, `m2` | mm2 | 1, 100, 1000000 | 1 cm2 = 100 base units; 1 m2 = 1,000,000 base units |
| `volume` | `mm3`, `cm3`, `ml`, `l`, `m3` | mm3 | 1, 1000, 1000, 1000000, 1000000000 | 1 cm3 = 1,000 base units; 1 ml = 1,000 base units; 1 l = 1,000,000 base units |

**Validation Errors:**
- `400 bad_request` if `quantity_decimal` cannot parse to `Decimal`
- `400 unsupported_uom` if `uom` not valid for `dimension`
- `400 fractional_base_quantity_not_allowed` if `quantity_decimal × multiplier` is not an integer
- `400 invalid_quantity` if result ≤ 0

**Display/Response Format:**
- API responses include both `qty_base_int` (internal) and `qty_display` (e.g., "10.5" + " kg")
- UI constructs display as: `quantity_decimal` + " " + `uom`

---

### Monetary Contract

**All Financial Fields in Cents (Integer):**
- **Fields:** `unit_cost_cents`, `amount_cents`, `unit_price_cents`, `refund_amount_cents`, `restock_unit_cost_cents`
- **Type:** Integer (uint64)
- **Range:** 0 to 9,223,372,036,854,775,807 (max int64)
- **No Decimals:** All values quantized to nearest cent; no sub-cent precision
- **Storage:** Direct integer; no float representation in DB
- **Display:** Divide by 100 for USD: `amount_cents / 100 = $X.XX`

**Example:**
- Input: `unit_price_cents = 1999` → stored as integer 1999 (cents)
- Display: `1999 / 100 = 19.99` → formatted `"$19.99"`

**Exception — Items.price Field (Legacy):**
- **Type:** Float (NOT cents)
- **Storage:** [core/appdb/models.py](core/appdb/models.py#L61) defines `price = Column(Float, default=0)`
- **Use:** Display/informational only; **NOT used in ledger cost calculations**
- **Example:** Item.price = 19.99 (float), never converted to cents for COGS or margin calculations

---

### Source & Linkage Contract

**source_kind (Enumerated String)**

Used to classify origin of inventory movement or cash event:

| Value | Applies To | Meaning |
|-------|-----------|---------|
| `purchase` | ItemBatch, ItemMovement | Purchase order stock-in |
| `consume` | ItemMovement | Manual consumption |
| `sold` | ItemMovement | Sold via `stock/out` with `reason=sold` |
| `adjustment` | ItemMovement | Manual in/out adjustment |
| `refund_restock` | ItemMovement | Stock restored via refund |
| `manufacturing` | ItemMovement | Consumed/produced in manufacturing run |
| `seed` | ItemBatch | Initial seed data |
| `stock_in` | ItemBatch, ItemMovement | Generic stock-in |
| `expense` | CashEvent | Non-inventory expense |

**source_id (String, Optional but Tracking)**
- UUID hex or database primary key ID
- Links movement/event to originating transaction
- Used to trace multi-table operations

**related_source_id (String, Optional, Secondary Link)**
- Example: Refund CashEvent → `related_source_id` = original Sale CashEvent.id (for cost lookup)

---

### Timestamp Contract

**Format:** ISO 8601, UTC timezone
- **Example:** `"2024-01-15T14:30:45Z"`
- **Precision:** Database microsecond; API returns second precision with `Z` suffix
- **Parsing:** Accept both with/without `Z`; interpreted as UTC

---

### CashEvent.kind Enumeration

| Value | Semantics | Sign | Linking |
|-------|-----------|------|---------|
| `sale` | Revenue from inventory sale | Positive | ItemMovement (qty_change < 0) with source_kind="sold" |
| `refund` | Return of sale revenue | **Negative** | ItemMovement optional (qty_change > 0, source_kind="refund_restock") |
| `expense` | Non-inventory cost | **Negative** | No ItemMovement |

---

## Items Endpoints

### GET `/app/items`

**Auth Required:** Yes  
**Writes Required:** No  
**Owner Commit Required:** No  
**Status:** Implemented

List all items with on-hand stock and FIFO cost calculations.

**Response:** HTTP 200 `List[ItemOut]`

```json
[
  {
    "id": 1,
    "name": "Widget A",
    "sku": "WID-001",
    "uom": "ea",
    "qty_stored": 1000,
    "qty": 10.0,
    "price": 19.99,
    "is_product": true,
    "notes": "Primary widget",
    "vendor": "Vendor Inc",
    "location": "Shelf A1",
    "created_at": "2024-01-01T12:00:00Z",
    "stock_on_hand_int": 1000,
    "stock_on_hand_display": {"unit": "ea", "value": "10.000"},
    "fifo_unit_cost_cents": 1000,
    "fifo_unit_cost_display": "$10.00 / ea"
  }
]
```

---

### GET `/app/items/{item_id}`

**Auth Required:** Yes  
**Status:** Implemented

Get detailed item with batch summary.

**Path Parameters:**
- `item_id` (integer, required, > 0)

**Errors:**
- **404:** `item_not_found`

---

### GET `/app/items/{item_id}/summary`

**Auth Required:** Yes  
**Status:** Implemented

Get item inventory summary with recent movements.

**Errors:**
- **404:** `item_not_found`

---

### POST `/app/items`

**Auth Required:** Yes  
**Writes Required:** Yes  
**Owner Commit Required:** Yes  
**Status:** Implemented

Create or upsert item.

**Request Body:**

| Field | Type | Required | Constraint | Notes |
|-------|------|----------|-----------|-------|
| `name` | string | Yes | Min 1 char | — |
| `dimension` | string | Yes | Enum: count, length, area, volume, weight | — |
| `uom` | string | Yes | Valid for dimension | — |
| `price` or `price_decimal` | float | No | ≥ 0 | **Display-only; informational; NOT used in ledger cost calculations (which use unit_cost_cents)** |
| `is_product` | boolean | No | Default: false | — |
| `vendor_id` | integer | No | Must exist | — |

**Errors:**
- **400:** `invalid_dimension` or `unsupported_uom`
- **403:** `owner_commit_required`
- **422:** `validation_error`

---

### PUT `/app/items/{item_id}`

**Auth Required:** Yes  
**Writes Required:** Yes  
**Owner Commit Required:** Yes  
**Status:** Implemented

Update item (all fields optional).

**Errors:**
- **404:** `item_not_found`
- **403:** `owner_commit_required`

---

### DELETE `/app/items/{item_id}`

**Auth Required:** Yes  
**Writes Required:** Yes  
**Owner Commit Required:** Yes  
**Status:** Implemented

Delete item and associated batches.

**Errors:**
- **404:** `item_not_found`
- **403:** `owner_commit_required`

---

## Vendors Endpoints

### GET `/app/vendors`

**Auth Required:** Yes  
**Status:** Implemented

List vendors with filtering.

**Query Parameters:**
- `q` (string, optional): Search query
- `role` (string, optional): vendor, contact, both, any
- `is_vendor` (string, optional): "true" or "false"
- `is_org` (string, optional): "true" or "false"
- `organization_id` (integer, optional): Filter by parent organization

**Response:** HTTP 200 `List[VendorOut]`

---

### GET `/app/vendors/{id}`

**Auth Required:** Yes  
**Status:** Implemented

**Errors:** **404:** `vendor_not_found`

---

### POST `/app/vendors`

**Auth Required:** Yes  
**Writes Required:** Yes  
**Owner Commit Required:** Yes  
**Status:** Implemented

Create vendor.

**Request Body:**

| Field | Type | Required | Constraint |
|-------|------|----------|-----------|
| `name` | string | Yes | Min 1 char |
| `role` | string | Yes | vendor, contact, both |

---

### PUT `/app/vendors/{id}`

**Auth Required:** Yes  
**Writes Required:** Yes  
**Owner Commit Required:** Yes  
**Status:** Implemented

Update vendor.

---

### DELETE `/app/vendors/{id}`

**Auth Required:** Yes  
**Writes Required:** Yes  
**Owner Commit Required:** Yes  
**Status:** Implemented

Delete vendor.

**Query Parameters:**
- `cascade_children` (boolean, default=false)

---

### Contacts Endpoints

Same CRUD at `/app/contacts` (facade).

---

## Recipes Endpoints

### GET `/app/recipes`

**Auth Required:** Yes  
**Status:** Implemented

List all recipes.

---

### GET `/app/recipes/{rid}`

**Auth Required:** Yes  
**Status:** Implemented

Get recipe detail with ingredients.

---

### POST `/app/recipes`

**Auth Required:** Yes  
**Writes Required:** Yes  
**Owner Commit Required:** Yes  
**Status:** Implemented

Create recipe.

**Request Body:**

| Field | Type | Required |
|-------|------|----------|
| `name` | string | Yes |
| `output_item_id` | integer | Yes |
| `output_qty` | number | Yes |
| `items` | array | Yes |

---

### PUT `/app/recipes/{rid}`

**Auth Required:** Yes  
**Writes Required:** Yes  
**Owner Commit Required:** Yes  
**Status:** Implemented

Update recipe (replaces ingredients).

---

### DELETE `/app/recipes/{recipe_id}`

**Auth Required:** Yes  
**Writes Required:** Yes  
**Owner Commit Required:** Yes  
**Status:** Implemented

Delete recipe.

---

## Manufacturing Endpoints

### POST `/app/manufacturing/run`

**Auth Required:** Yes  
**Writes Required:** Yes  
**Owner Commit Required:** Yes  
**Status:** Implemented

Execute manufacturing run (atomic: FIFO consume ingredients, produce output, create movements).

**Request Body (Recipe-Based):**
```json
{
  "recipe_id": 1,
  "output_qty": 10,
  "notes": "Production run"
}
```

**Request Body (Ad-Hoc):**
```json
{
  "output_item_id": 1,
  "output_qty": 10,
  "components": [
    {"item_id": 2, "qty_required": 50, "is_optional": false}
  ]
}
```

**Errors:**
- **400:** `recipe_not_found` or `item_not_found`
- **400:** `insufficient_stock` (see shortages array)
- **400:** `oversell_prevention_blocked_manufacturing`
- **403:** `owner_commit_required`

**Output Unit Cost Calculation:**
- **Formula:** `total_ingredient_cost_cents / produced_quantity`
- **Implementation:** Calculated via Decimal, quantized to 0.0001 (ten-thousandths of a cent), using ROUND_HALF_UP rounding (from [core/api/routes/manufacturing.py](core/api/routes/manufacturing.py#L191-192))
- **Storage:** Stored as integer in ItemBatch.unit_cost_cents (cents)
- **Example:** Ingredients cost 50,000 cents total; produce 100 units → output_unit_cost_cents = 500 (5.00 per unit)

**Behavioral Notes:**
- **Atomic:** Ingredient consumption + output batch + movements in single transaction
- **FIFO:** Oldest batches consumed first
- **Oversell Prevention:** Manufacturing cannot create oversold movements

---

### GET `/app/manufacturing/runs`

**Auth Required:** Yes  
**Status:** Implemented

List recent runs from journal.

**Query Parameters:**
- `days` (integer, default=30, range=1–365)

---

### GET `/app/manufacturing/history`

**Auth Required:** Yes  
**Status:** Implemented

Alias for `/app/manufacturing/runs`.

---

## Ledger & Inventory Endpoints

### POST `/app/ledger/purchase`

**Auth Required:** Yes  
**Status:** Implemented

Record purchase (stock-in with cost). Creates ItemBatch.

**Request Body:**

| Field | Type | Required | Constraint |
|-------|------|----------|-----------|
| `item_id` | integer | Yes | Must exist |
| `quantity_decimal` | string | Yes | Parses to Decimal > 0 |
| `uom` | string | Yes | Valid for item's dimension |
| `unit_cost_cents` | integer | Yes | ≥ 0 |

**Validation:** Rejects legacy `qty` field (422).

**Errors:**
- **404:** `item_not_found`
- **400:** `unsupported_uom` or `invalid_quantity`
- **422:** `legacy_qty_field_not_allowed`

---

### POST `/app/ledger/consume`

**Auth Required:** Yes  
**Status:** Implemented

Consume stock via FIFO. Creates ItemMovements (qty_change < 0).

**Request Body:**

| Field | Type | Required |
|-------|------|----------|
| `item_id` | integer | Yes |
| `quantity_decimal` | string | Yes |
| `uom` | string | Yes |

**Errors:**
- **404:** `item_not_found`
- **400:** `insufficient_stock` or `invalid_quantity`

---

### POST `/app/ledger/adjust`

**Auth Required:** Yes  
**Status:** Implemented

Adjust stock in or out.

**Request Body:**

| Field | Type | Required |
|-------|------|----------|
| `item_id` | integer | Yes |
| `quantity_decimal` | string | Yes |
| `direction` | string | Yes |

---

### POST `/app/ledger/stock/out`

**Auth Required:** Yes  
**Status:** Implemented

Stock out (sale/loss/theft/other). Optional atomic CashEvent for sales.

**Request Body:**

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `item_id` | integer | Yes | — |
| `quantity_decimal` | string | Yes | — |
| `uom` | string | Yes | — |
| `reason` | string | Yes | sold, loss, theft, other |
| `record_cash_event` | boolean | No | **Required if reason="sold"** |
| `sell_unit_price_cents` | integer | No | **Required if reason="sold"** |

**Canonical Sale Endpoint:** This is THE entrypoint for recording sales (reason="sold" + record_cash_event=true).

**Errors:**
- **404:** `item_not_found`
- **400:** `insufficient_stock`, `sold_cash_event_count_only`, `missing_sell_unit_price_cents`

---

### GET `/app/ledger/valuation`

**Auth Required:** Yes  
**Status:** Implemented

Get inventory valuation.

**Query Parameters:**
- `item_id` (integer, optional)

---

### GET `/app/ledger/movements`

**Auth Required:** Yes  
**Status:** Implemented

List item movements.

**Query Parameters:**
- `item_id` (integer, optional)
- `limit` (integer, default=100, max=1000)

---

### POST `/app/ledger/stock_in`

**Auth Required:** Yes  
**Status:** Implemented

Stock in (alternative to purchase).

**Request Body:**

| Field | Type | Required |
|-------|------|----------|
| `item_id` | integer | Yes |
| `uom` | string | Yes |
| `quantity_decimal` | string | Yes |
| `unit_cost_decimal` | string | No |
| `vendor_id` | integer | No |

---

## Finance Endpoints

### POST `/app/finance/expense`

**Auth Required:** Yes  
**Status:** Implemented

Record expense.

**Request Body:**

| Field | Type | Required |
|-------|------|----------|
| `amount_cents` | integer | Yes |
| `category` | string | No |
| `notes` | string | No |

---

### POST `/app/finance/refund`

**Auth Required:** Yes  
**Status:** Implemented

Record refund with optional restocking.

**Request Body:**

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `item_id` | integer | Yes | — |
| `refund_amount_cents` | integer | Yes | > 0 |
| `quantity_decimal` | string | Yes | — |
| `uom` | string | Yes | — |
| `restock_inventory` | boolean | Yes | — |
| `related_source_id` | string | No | Original sale CashEvent.id (for cost lookup) |
| `restock_unit_cost_cents` | integer | No | **Required if restock=true and no related_source_id** |

**Validation Rules:**
- If `restock_inventory=true` AND no `related_source_id`, then `restock_unit_cost_cents` REQUIRED
- If `related_source_id` provided, system looks up weighted-average cost from original sale movements

**Errors:**
- **404:** `item_not_found`
- **400:** `restock_unit_cost_required_without_related_source_id`, `related_source_id_not_found_for_item`

---

### GET `/app/finance/profit`

**Auth Required:** Yes  
**Status:** Implemented

Get profit/margin summary for date window.

**Query Parameters:**

| Parameter | Type | Meaning |
|-----------|------|---------|
| `start` | string (ISO8601) | Window start |
| `end` | string (ISO8601) | Window end |
| `range` | string | Preset: 7d, 30d, 90d, ytd, all |
| `from` | string (YYYY-MM-DD) | Alternate start |
| `to` | string (YYYY-MM-DD) | Alternate end |

**Response:** HTTP 200

```json
{
  "window": {
    "start": "2024-01-01T00:00:00Z",
    "end": "2024-01-31T23:59:59Z"
  },
  "gross_revenue_cents": 100000,
  "refunds_cents": 5000,
  "net_revenue_cents": 95000,
  "cogs_cents": 50000,
  "gross_profit_cents": 45000,
  "margin_percent": 47.37
}
```

**Errors:**
- **400:** `invalid_iso8601_datetime` or `invalid_range`

---

### GET `/app/finance/cash-event/{source_id}`

**Auth Required:** Yes  
**Status:** Implemented

Trace cash event with linked movements.

**Errors:**
- **404:** `cash_event_not_found`

---

## Dashboard Endpoints

### GET `/app/dashboard/summary`

**Auth Required:** Yes  
**Status:** Implemented

Get dashboard summary (inventory, revenue, costs, profit).

**Query Parameters:**
- `start` (string, ISO8601, optional)
- `end` (string, ISO8601, optional)

**Errors:**
- **400:** `invalid_iso8601_datetime`

---

## Behavioral Invariants

All rules enforced by codebase:

| Rule | File | Enforcement | Behavior |
|------|------|-------------|----------|
| **FIFO Allocation** | [core/appdb/ledger.py](core/appdb/ledger.py#L24-150) | `fifo_consume()` function | Oldest batch (created_at, then id) allocated first; cost from allocated batch used for COGS |
| **Oversell Prevention** | [migrations/2025-12-manufacturing.sql](migrations/2025-12-manufacturing-no-oversell.sql) | SQL CHECK constraint | Manufacturing ≠ oversold (rejected 400) |
| **Atomic Transaction** | [ledger_api.py](core/api/routes/ledger_api.py#L275-320) | Nested transaction (SAVEPOINT) | Inventory + cash events in single transaction; rollback together; journal append decoupled |
| **Cash Event Link** | [finance_api.py](core/api/routes/finance_api.py#L86-140) | Refund logic | Refund → related_source_id links to original CashEvent.id (for cost lookup) |
| **Dev Mode Gate** | [core/api/utils/devguard.py](core/api/utils/devguard.py) | Check `BUS_DEV=1` | `/health/detailed`, `/dev/*` require env var; 401 if not set |
| **Owner Commit** | [core/policy/guard.py](core/policy/guard.py) | `require_owner_commit()` | Sensitive writes (items, recipes, manufacturing, vendors) require policy validation; 403 if not committed |
| **Refund Restock** | [finance_api.py](core/api/routes/finance_api.py#L105-140) | Optional logic | If restock=true: creates source_kind="refund_restock" movement linked via source_id; requires cost (explicit or lookup) |
| **Margin Calc** | [core/api/read_models.py](core/api/read_models.py#L47-104) | Formula | (net_revenue - cogs) / net_revenue; FIFO cost allocation; cogs only for sold items |
| **Writes Toggle** | [core/config/writes.py](core/config/writes.py) | Dev mode `/dev/writes` | All POST/PUT/DELETE return 400 if disabled |

---

## Deterministic Test Data Creation Order

Follow this exact sequence to build valid test history.

### 1. Create Vendor

`POST /app/vendors`

```json
{
  "name": "Supplier Corp",
  "contact": "contact@supplier.com",
  "role": "vendor"
}
```

**Dependencies:** None  
**Failure:** 422 (validation), 409 (duplicate)  
**Success:** vendor_id

---

### 2. Create Items (3 minimum: output, ingredient A, ingredient B)

`POST /app/items`

**Item 1 (Output):**
```json
{
  "name": "Widget A",
  "dimension": "count",
  "uom": "ea",
  "price_decimal": 19.99,
  "is_product": true,
  "vendor_id": 1
}
```

**Item 2 (Ingredient A):**
```json
{
  "name": "Component A",
  "dimension": "count",
  "uom": "ea",
  "is_product": false
}
```

**Item 3 (Ingredient B):**
```json
{
  "name": "Component B",
  "dimension": "weight",
  "uom": "g",
  "is_product": false
}
```

**Dependencies:** Vendor (step 1)  
**Failure:** 404 (vendor not found), 422 (invalid dimension/uom)  
**Success:** item_id=1, 2, 3

---

### 3. Create Purchases (Stock-In Batches)

`POST /app/ledger/purchase`

**Batch for Item A (500 units):**
```json
{
  "item_id": 2,
  "quantity_decimal": "5",
  "uom": "ea",
  "unit_cost_cents": 500
}
```

**Batch for Item B (1000g):**
```json
{
  "item_id": 3,
  "quantity_decimal": "1000",
  "uom": "g",
  "unit_cost_cents": 50
}
```

**Dependencies:** Items (step 2)  
**Failure:** 404 (item not found), 400 (invalid uom)  
**Success:** Inventory created and on-hand updated

---

### 4. Create Recipe (Optional)

`POST /app/recipes`

```json
{
  "name": "Widget Assembly",
  "output_item_id": 1,
  "output_qty": 1,
  "items": [
    {"item_id": 2, "qty_required": 5},
    {"item_id": 3, "qty_required": 100}
  ]
}
```

**Dependencies:** Items (step 2)  
**Success:** recipe_id=1

---

### 5. Execute Manufacturing Run (If Recipe Created)

`POST /app/manufacturing/run`

```json
{
  "recipe_id": 1,
  "output_qty": 10
}
```

**Dependencies:** Recipe (step 4), sufficient inventory (step 3)  
**Failure:** 400 (insufficient stock or oversell block)  
**Success:** Consumes FIFO; produces output

---

### 6. Create Consumption

`POST /app/ledger/consume`

```json
{
  "item_id": 2,
  "quantity_decimal": "1",
  "uom": "ea"
}
```

**Failure:** 400 (insufficient stock)

---

### 7. Record Sale (Canonical Sale Entrypoint)

`POST /app/ledger/stock/out`

```json
{
  "item_id": 1,
  "quantity_decimal": "5",
  "uom": "ea",
  "reason": "sold",
  "record_cash_event": true,
  "sell_unit_price_cents": 2499
}
```

**Dependencies:** Item with stock > 0  
**Failure:** 400 (insufficient stock, sold_cash_event_count_only)  
**Success:** Creates ItemMovement + CashEvent atomically

---

### 8. Record Refund

`POST /app/finance/refund`

```json
{
  "item_id": 1,
  "refund_amount_cents": 2499,
  "quantity_decimal": "1",
  "uom": "ea",
  "restock_inventory": true,
  "related_source_id": "abc123def456"
}
```

**Dependencies:** Sale (step 7) source_id  
**Failure:** 400 (restock_unit_cost_required_without_related_source_id)  
**Success:** Creates CashEvent + optional restock movement

---

### 9. Query Profit

`GET /app/finance/profit?range=all`

**Dependencies:** At least one sale (step 7)  
**Success:** Returns revenue, COGS (FIFO), profit, margin

---

### Failure Code Reference

| Code | Condition | Recovery |
|------|-----------|----------|
| **400** | Business rule violation (insufficient stock, oversell, constraint) | Adjust qty or create more inventory |
| **401** | Not authenticated | Call `POST /session/token` |
| **403** | Owner commit required | Commit policy via `/app/policy` |
| **404** | Entity not found | Verify ID exists |
| **409** | Duplicate (if unique constraint) | Use different name |
| **422** | Validation error (type mismatch, invalid format) | Check request body schema |

---

## Deferred Sections (Core-Only Scope)

The following are documented but **NOT hardened** in this revision:

- **Health & Status:** `/health`, `/health/detailed`
- **Transactions (STUB):** `/app/transactions/summary`, `/app/transactions`
- **Configuration:** `/app/config` GET/POST
- **Settings & Integrations:** Google Drive, reader settings
- **Plans:** `/app/plans/*`
- **Plugins:** `/app/plugins/*`
- **Catalog & Indexing:** `/app/catalog/*`, `/app/index/*`
- **Reader & Organizer:** `/app/reader/*`, `/app/organizer/*`
- **Database Operations:** `/app/db/export`, `/app/db/import/*`
- **Development Endpoints:** `/dev/*` (beyond writes/db/where)
- **Policy & Transparency:** `/app/policy`, `/app/policy.simulate`, `/app/transparency.report`
- **OAuth:** `/oauth/google/*`
- **Server:** `/app/server/restart`, `/app/inventory/run`
- **Logs:** `/app/logs`

**Note:** `/session/token` (GET) is **NOW HARDENED** (see [Authentication Flow](#authentication-flow-authoritative)).

These will be hardened in subsequent iterations.

---

## Schema Drift Report

### Confirmed Discrepancies & Resolutions

| Endpoint | Drift | Resolution |
|----------|-------|-----------|
| **Authentication** | Original schema suggested POST /session/token; actual contract is GET | **FIXED:** Corrected to GET/session/token; automatic cookie persistence via requests.Session / WebSession |
| **Items Response** | Schema doesn't clarify computed fields: `stock_on_hand_int`, `stock_on_hand_display`, `fifo_unit_cost_display` | All marked as **read-only** in responses; `qty` field marked as display-only |
| **Sale Endpoint** | Schema suggests `POST /app/finance/sale` but no such route exists | Clarified: Sales via `POST /app/ledger/stock/out?reason=sold&record_cash_event=true` — **canonical entrypoint** |
| **Transactions STUBS** | Documented as full endpoints but code returns `{"stub": true}` | Marked as **UNIMPLEMENTED**; recommend removal or future implementation |
| **Legacy Fields** | Schema accepts both `qty` and `qty_stored`; `price` and `price_decimal` | Ledger endpoints reject `qty` field (422); Items accept both for backward compatibility; `price_decimal` canonical |
| **Refund Cost Lookup** | Schema doesn't explain weighted-average cost behavior | Documented: if `related_source_id` provided, weighted-average calculated from original sale movements |
| **Manufacturing Cost** | Formula not clearly specified | Added: output_unit_cost_cents = total_ingredient_cost_cents / produced_quantity; quantized to 0.0001 using ROUND_HALF_UP; stored as integer cents |

### No Breaking Changes

All documented endpoints match actual FastAPI routes. Discrepancies are **clarifications** only, not route-level changes.

---

## Authoritative Behavior Source

**Critical:** All contracts, invariants, and calculations documented in this schema are derived from the following authoritative source files:

| Component | Source File | Relevant Lines |
|-----------|-------------|----------------|
| **Quantity Normalization** | [core/api/quantity_contract.py](core/api/quantity_contract.py) | L1-89 |
| **UOM Multipliers** | [core/metrics/metric.py](core/metrics/metric.py) | L1-25 (UNIT_MULTIPLIER dict) |
| **FIFO Allocation** | [core/appdb/ledger.py](core/appdb/ledger.py) | fifo_consume() function |
| **Atomic Transactions** | [core/api/routes/ledger_api.py](core/api/routes/ledger_api.py), [core/api/routes/finance_api.py](core/api/routes/finance_api.py) | db.begin_nested() or db.begin() scope |
| **Refund Cost Lookup** | [core/api/routes/finance_api.py](core/api/routes/finance_api.py) | L105-140 (related_source_id logic) |
| **Manufacturing Cost** | [core/api/routes/manufacturing.py](core/api/routes/manufacturing.py) | L191-192 (Decimal quantization) |
| **Items.price Field** | [core/appdb/models.py](core/appdb/models.py), [core/api/routes/items.py](core/api/routes/items.py) | Item.price = Column(Float) |
| **Oversell Prevention** | [migrations/2025-12-manufacturing-no-oversell.sql](migrations/2025-12-manufacturing-no-oversell.sql) | SQL CHECK constraint |
| **Dev Mode Gating** | [core/api/utils/devguard.py](core/api/utils/devguard.py) | BUS_DEV env var check |
| **Owner Commit** | [core/policy/guard.py](core/policy/guard.py) | require_owner_commit() decorator |

**If conflict exists between this documentation and the code, code is authoritative.** This schema serves as a guide; the codebase in the source files above is the definitive specification.

---

## OpenAPI 3.0.0 Specification

```json
{
  "openapi": "3.0.0",
  "info": {
    "title": "BUS Core API — Hardened Schema",
    "description": "Automation-grade API for inventory, manufacturing, finance",
    "version": "1.0.0-hardened",
    "license": {
      "name": "AGPL-3.0-or-later"
    }
  },
  "servers": [
    {
      "url": "http://127.0.0.1:8765",
      "description": "Local development"
    }
  ],
  "paths": {
    "/app/items": {
      "get": {
        "summary": "List all items",
        "operationId": "get_items",
        "tags": ["items"],
        "security": [{"session": []}],
        "responses": {
          "200": {
            "description": "List of items"
          },
          "401": {
            "description": "Unauthorized"
          }
        }
      },
      "post": {
        "summary": "Create or upsert item",
        "operationId": "create_item",
        "tags": ["items"],
        "security": [{"session": []}],
        "requestBody": {
          "required": true,
          "content": {
            "application/json": {
              "schema": {"$ref": "#/components/schemas/ItemIn"}
            }
          }
        },
        "responses": {
          "201": {"description": "Item created"},
          "403": {"description": "Owner commit required"},
          "422": {"description": "Validation error"}
        }
      }
    },
    "/app/ledger/purchase": {
      "post": {
        "summary": "Record purchase (stock-in with cost)",
        "operationId": "ledger_purchase",
        "tags": ["ledger"],
        "security": [{"session": []}],
        "requestBody": {
          "required": true,
          "content": {
            "application/json": {
              "schema": {"$ref": "#/components/schemas/PurchaseIn"}
            }
          }
        },
        "responses": {
          "200": {"description": "Purchase recorded"},
          "400": {"description": "Bad request"},
          "404": {"description": "Item not found"}
        }
      }
    },
    "/app/ledger/stock/out": {
      "post": {
        "summary": "Stock out (CANONICAL SALE ENTRYPOINT when reason=sold, record_cash_event=true)",
        "operationId": "ledger_stock_out",
        "tags": ["ledger"],
        "security": [{"session": []}],
        "requestBody": {
          "required": true,
          "content": {
            "application/json": {
              "schema": {"$ref": "#/components/schemas/StockOutIn"}
            }
          }
        },
        "responses": {
          "200": {"description": "Stock out recorded"},
          "400": {"description": "Insufficient stock or constraint violation"}
        }
      }
    },
    "/app/manufacturing/run": {
      "post": {
        "summary": "Execute manufacturing run",
        "operationId": "manufacturing_run",
        "tags": ["manufacturing"],
        "security": [{"session": []}],
        "requestBody": {
          "required": true,
          "content": {
            "application/json": {
              "schema": {
                "oneOf": [
                  {"$ref": "#/components/schemas/ManufacturingRunRecipeIn"},
                  {"$ref": "#/components/schemas/ManufacturingRunAdHocIn"}
                ]
              }
            }
          }
        },
        "responses": {
          "200": {"description": "Run completed"},
          "400": {"description": "Insufficient stock or oversell prevented"}
        }
      }
    },
    "/app/finance/refund": {
      "post": {
        "summary": "Record refund with optional restocking",
        "operationId": "finance_refund",
        "tags": ["finance"],
        "security": [{"session": []}],
        "requestBody": {
          "required": true,
          "content": {
            "application/json": {
              "schema": {"$ref": "#/components/schemas/RefundIn"}
            }
          }
        },
        "responses": {
          "200": {"description": "Refund recorded"},
          "400": {"description": "Missing cost or invalid related_source_id"}
        }
      }
    },
    "/app/finance/profit": {
      "get": {
        "summary": "Get profit/margin summary",
        "operationId": "finance_profit",
        "tags": ["finance"],
        "security": [{"session": []}],
        "parameters": [
          {
            "name": "start",
            "in": "query",
            "schema": {"type": "string", "format": "date-time"}
          },
          {
            "name": "end",
            "in": "query",
            "schema": {"type": "string", "format": "date-time"}
          },
          {
            "name": "range",
            "in": "query",
            "schema": {"type": "string", "enum": ["7d", "30d", "90d", "ytd", "all"]}
          }
        ],
        "responses": {
          "200": {"description": "Profit summary"},
          "400": {"description": "Invalid parameters"}
        }
      }
    },
    "/app/dashboard/summary": {
      "get": {
        "summary": "Get dashboard summary",
        "operationId": "dashboard_summary",
        "tags": ["dashboard"],
        "security": [{"session": []}],
        "responses": {
          "200": {"description": "Dashboard summary"},
          "400": {"description": "Invalid parameters"}
        }
      }
    }
  },
  "components": {
    "schemas": {
      "ItemIn": {
        "type": "object",
        "properties": {
          "name": {"type": "string"},
          "dimension": {"type": "string", "enum": ["count", "length", "area", "volume", "weight"]},
          "uom": {"type": "string"},
          "price_decimal": {"type": "number", "minimum": 0}
        },
        "required": ["name", "dimension", "uom"]
      },
      "ItemOut": {
        "type": "object",
        "description": "Item details with computed read-only fields",
        "properties": {
          "id": {"type": "integer"},
          "name": {"type": "string"},
          "sku": {"type": ["string", "null"]},
          "dimension": {"type": "string"},
          "uom": {"type": "string"},
          "qty_stored": {"type": "integer", "description": "Internal base units (integer)"},
          "qty": {"type": "number", "description": "Display format (read-only, computed)"},
          "price": {"type": ["number", "null"], "description": "Float USD (display-only, not used in cost calculations)"},
          "is_product": {"type": "boolean"},
          "notes": {"type": ["string", "null"]},
          "vendor": {"type": ["string", "null"]},
          "location": {"type": ["string", "null"]},
          "created_at": {"type": "string", "format": "date-time"},
          "stock_on_hand_int": {"type": "integer", "description": "Base units (read-only)"},
          "stock_on_hand_display": {"type": "object", "properties": {"unit": {"type": "string"}, "value": {"type": "string"}}, "description": "Formatted display (read-only)"},
          "fifo_unit_cost_cents": {"type": ["integer", "null"], "description": "FIFO cost in cents (read-only)"},
          "fifo_unit_cost_display": {"type": ["string", "null"], "description": "Formatted cost display (read-only)"}
        },
        "required": ["id", "name", "dimension", "uom", "qty_stored"]
      },
      "CashEventOut": {
        "type": "object",
        "description": "Cash event (sale, refund, expense)",
        "properties": {
          "id": {"type": "integer"},
          "kind": {"type": "string", "enum": ["sale", "refund", "expense"]},
          "category": {"type": ["string", "null"]},
          "amount_cents": {"type": "integer"},
          "source_id": {"type": ["string", "null"]},
          "related_source_id": {"type": ["string", "null"], "description": "For refunds: ID of original sale CashEvent for cost lookup"},
          "item_id": {"type": ["integer", "null"]},
          "qty_base": {"type": ["integer", "null"]},
          "created_at": {"type": "string", "format": "date-time"}
        }
      },
      "ErrorResponse": {
        "type": "object",
        "description": "Standard error response",
        "properties": {
          "error": {"type": "string", "description": "Error code (bad_request, item_not_found, insufficient_stock, etc.)"},
          "message": {"type": "string"},
          "fields": {"type": "object", "description": "Context-specific field errors"}
        },
        "required": ["error"]
      },
      "PurchaseIn": {
        "type": "object",
        "properties": {
          "item_id": {"type": "integer"},
          "quantity_decimal": {"type": "string"},
          "uom": {"type": "string"},
          "unit_cost_cents": {"type": "integer", "minimum": 0}
        },
        "required": ["item_id", "quantity_decimal", "uom", "unit_cost_cents"]
      },
      "StockOutIn": {
        "type": "object",
        "properties": {
          "item_id": {"type": "integer"},
          "quantity_decimal": {"type": "string"},
          "uom": {"type": "string"},
          "reason": {"type": "string", "enum": ["sold", "loss", "theft", "other"]},
          "record_cash_event": {"type": "boolean"},
          "sell_unit_price_cents": {"type": "integer", "minimum": 0}
        },
        "required": ["item_id", "quantity_decimal", "uom", "reason"]
      },
      "RefundIn": {
        "type": "object",
        "properties": {
          "item_id": {"type": "integer"},
          "refund_amount_cents": {"type": "integer", "minimum": 1},
          "quantity_decimal": {"type": "string"},
          "uom": {"type": "string"},
          "restock_inventory": {"type": "boolean"},
          "related_source_id": {"type": "string"},
          "restock_unit_cost_cents": {"type": "integer", "minimum": 0}
        },
        "required": ["item_id", "refund_amount_cents", "quantity_decimal", "uom", "restock_inventory"]
      },
      "ManufacturingRunRecipeIn": {
        "type": "object",
        "properties": {
          "recipe_id": {"type": "integer"},
          "output_qty": {"type": "number", "minimum": 0}
        },
        "required": ["recipe_id", "output_qty"]
      },
      "ManufacturingRunAdHocIn": {
        "type": "object",
        "properties": {
          "output_item_id": {"type": "integer"},
          "output_qty": {"type": "number", "minimum": 0},
          "components": {"type": "array"}
        },
        "required": ["output_item_id", "output_qty", "components"]
      }
    },
    "securitySchemes": {
      "session": {
        "type": "apiKey",
        "in": "cookie",
        "name": "bus_session"
      }
    }
  }
}
```

---

**End of Hardened API Schema**

*Last Updated: 2026-02-17*  
*Reconciliation Status: Complete (Core endpoints)*  
*Production Validation: Pending*