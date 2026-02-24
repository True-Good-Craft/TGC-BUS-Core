# BUS Core API Contract — Canonical & Governance Locked
Version: v0.11.x (Post Phase B)
Status: Authoritative

## 1. Authority Model
- **SoT supremacy:** `SOT.md` is canonical governance. Any contract drift MUST start with an explicit SoT delta.
- **Backend frozen contract boundary:** Any change to mounted API paths, payload keys, response shape, or quantity/cost semantics at canonical endpoints is a contract change and MUST NOT ship without SoT delta plus this document update.
- **Canonical endpoint authority:** Canonical inventory/manufacturing/ledger endpoints are under `/app/*` and are the only authoritative UI mutation/read paths for those domains.
- **UI network authority:** UI network access is contained to `core/ui/js/api.js` and `core/ui/js/token.js`; all UI cards/modules MUST call through canonical client helpers and MUST NOT issue ad hoc fetches.
- **Canonical containment rule:** **Any code outside the canonical client calling canonical endpoints is a VIOLATION.**
- **Legacy wrappers rule:** **Legacy routes may exist only as wrappers and are forbidden for new code.** Wrappers MUST only translate/deprecate and forward to canonical handlers.

## 2. Canonical Public Surface

### Inventory / Ledger / Manufacture (Phase A canonical set)
- `POST /app/stock/in`
  - Purpose: Stock-in mutation using v2 quantity fields.
  - Key request fields: `item_id`, `quantity_decimal`, `uom`, optional `unit_cost_cents`, optional `source_id`.
  - Key response fields: `ok`, `item_id`, movement/allocation fields from stock mutation service.
  - Error behaviors: `400` invalid quantity or forbidden legacy quantity keys; `404` `item_not_found`; `401` when auth/token gate fails.

- `POST /app/stock/out`
  - Purpose: Stock-out mutation with reason/cash metadata.
  - Key request fields: `item_id`, `quantity_decimal`, `uom`, `reason`; optional `note`, `record_cash_event`, `sell_unit_price_cents`.
  - Key response fields: `ok`, `lines` (batch/qty/cost allocations), stock mutation result envelope.
  - Error behaviors: `400` invalid quantity, forbidden legacy quantity keys, or shortages; `404` `item_not_found`; `401` auth/token failure.

- `POST /app/purchase`
  - Purpose: Purchase stock-in with unit cost authority.
  - Key request fields: `item_id`, `quantity_decimal`, `uom`, `unit_cost_cents`; optional `source_id`.
  - Key response fields: purchase/stock-in mutation result envelope (`ok`, line/movement info).
  - Error behaviors: `400` invalid quantity or forbidden legacy quantity keys; `404` `item_not_found`; `401` auth/token failure.

- `GET /app/ledger/history`
  - Purpose: Canonical movement history read surface.
  - Key request fields: optional query `item_id`, `limit`.
  - Key response fields: list of normalized movement records (IDs, item, quantity display/base-derived fields, costs, metadata).
  - Error behaviors: `401` auth/token failure. `400`/`404` not explicitly enforced in route for normal usage.

- `POST /app/manufacture`
  - Purpose: Canonical manufacturing run (recipe or ad hoc components) with v2 quantities.
  - Key request fields: either `recipe_id` or `output_item_id` + `components[]`; `quantity_decimal`, `uom`; optional `notes`.
  - Key response fields: manufacturing result (`ok`), run identifiers, consumed/produced line summaries.
  - Error behaviors: `400` invalid payload/quantity/shortage; `404` missing recipe/item; `401` auth/token failure.

### Items / Catalog
- `GET /app/items`
  - Purpose: List catalog/inventory items.
  - Key request fields: none.
  - Key response fields: array of item records (`id`, `name`, `sku`, `dimension`, `uom`, stock/cost display fields).
  - Error behaviors: `401` auth/token failure.

- `GET /app/items/{item_id}`
  - Purpose: Fetch single item detail.
  - Key request fields: path `item_id`.
  - Key response fields: item detail record.
  - Error behaviors: `404` when item missing; `401` auth/token failure.

- `POST /app/items`
  - Purpose: Create item.
  - Key request fields: item identity + unit metadata (name/sku/dimension/uom), optional costing and vendor links.
  - Key response fields: created item record.
  - Error behaviors: `400` validation; `401` auth/token failure.

- `PUT /app/items/{item_id}`
  - Purpose: Update item.
  - Key request fields: path `item_id`, mutable item fields.
  - Key response fields: updated item record.
  - Error behaviors: `404` item missing; `400` validation; `401` auth/token failure.

- `DELETE /app/items/{item_id}`
  - Purpose: Delete item.
  - Key request fields: path `item_id`.
  - Key response fields: delete confirmation (`ok`/deleted id shape).
  - Error behaviors: `404` item missing; `401` auth/token failure.

### Contacts / Vendors
- `GET /app/vendors`, `GET /app/contacts`
  - Purpose: List vendor/contact entities (facade-filtered).
  - Key request fields: optional `q`, `role`, `role_in`, `is_vendor`, `is_org`, `organization_id`.
  - Key response fields: array of vendor/contact records.
  - Error behaviors: `401` auth/token failure.

- `GET /app/vendors/{id}`, `GET /app/contacts/{id}`
  - Purpose: Fetch single vendor/contact.
  - Key request fields: path `id`.
  - Key response fields: vendor/contact record.
  - Error behaviors: `404` Not found; `401` auth/token failure.

- `POST /app/vendors`, `POST /app/contacts`
  - Purpose: Create vendor/contact.
  - Key request fields: `name` + optional role/organization/contact metadata.
  - Key response fields: created record.
  - Error behaviors: `401` auth/token failure.

- `PUT /app/vendors/{id}`, `PUT /app/contacts/{id}`
  - Purpose: Update vendor/contact.
  - Key request fields: path `id` + mutable fields.
  - Key response fields: updated record.
  - Error behaviors: `404` Not found; `401` auth/token failure.

- `DELETE /app/vendors/{id}`, `DELETE /app/contacts/{id}`
  - Purpose: Delete vendor/contact.
  - Key request fields: path `id`, optional query `cascade_children` for org deletion behavior.
  - Key response fields: `204` no-content.
  - Error behaviors: `404` Not found; `401` auth/token failure.

### Recipes
- `GET /app/recipes`
  - Purpose: List recipes.
  - Key request fields: none.
  - Key response fields: recipe summaries (id/name/output item/output quantity/uom/archive status).
  - Error behaviors: `401` auth/token failure.

- `GET /app/recipes/{rid}`
  - Purpose: Get recipe detail.
  - Key request fields: path `rid`.
  - Key response fields: recipe + item lines with quantity/uom details.
  - Error behaviors: `404` Not found; `401` auth/token failure.

- `POST /app/recipes`
  - Purpose: Create recipe.
  - Key request fields: `name`, `output_item_id`, `output_qty`, optional `uom`, `notes`, `items[]` each with `item_id`, `quantity_decimal`, `uom`, optionality/sort.
  - Key response fields: created recipe detail.
  - Error behaviors: `400` invalid quantity/input; `404` referenced item missing; `401` auth/token failure.

- `PUT /app/recipes/{rid}`
  - Purpose: Update recipe.
  - Key request fields: path `rid`, mutable recipe fields and optional `items[]` replacement.
  - Key response fields: updated recipe detail.
  - Error behaviors: `400` invalid quantity/input; `404` recipe/item missing; `401` auth/token failure.

- `DELETE /app/recipes/{recipe_id}`
  - Purpose: Delete recipe.
  - Key request fields: path `recipe_id`.
  - Key response fields: `{ ok, deleted }`.
  - Error behaviors: `404` Not found; `401` auth/token failure.

### Finance endpoints
- `POST /app/finance/expense`
  - Purpose: Record cash expense.
  - Key request fields: `at`, `amount_cents`, `category`; optional `note`, `related_source_id`.
  - Key response fields: `{ ok, entry }`.
  - Error behaviors: `400` validation; `401` auth/token failure.

- `POST /app/finance/refund`
  - Purpose: Record refund; optional inventory restock flow.
  - Key request fields: `at`, `amount_cents`, optional `note`, `related_source_id`, `restock_inventory`, `restock_item_id`, `restock_qty`, `restock_unit_cost_cents`.
  - Key response fields: `{ ok, entry, restock }` (restock block when applied).
  - Error behaviors: `400` invalid restock prerequisites/validation; `404` restock item missing; `401` auth/token failure.

- `GET /app/finance/profit`
  - Purpose: Profit snapshot by date range.
  - Key request fields: query `from`, `to`.
  - Key response fields: totals (`sales_cents`, `expenses_cents`, `refunds_cents`, `cogs_cents`, `profit_cents`) and range metadata.
  - Error behaviors: `400` invalid date/query; `401` auth/token failure.

### Maintenance / Config endpoints
- `POST /app/db/export`
  - Purpose: Create encrypted/plain DB export artifact.
  - Key request fields: optional `password`.
  - Key response fields: export file metadata/path token.
  - Error behaviors: `401` auth/token failure.

- `GET /app/db/exports`
  - Purpose: List available exports.
  - Key request fields: none.
  - Key response fields: export entries.
  - Error behaviors: `401` auth/token failure.

- `POST /app/db/import/upload`
  - Purpose: Upload backup file for staged import.
  - Key request fields: multipart file upload.
  - Key response fields: staged `path` token.
  - Error behaviors: `400` invalid upload; `401` auth/token failure.

- `POST /app/db/import/preview`
  - Purpose: Preview import metadata/compat before commit.
  - Key request fields: `path`, optional `password`.
  - Key response fields: preview summary and checks.
  - Error behaviors: `400` preview failure; `401` auth/token failure.

- `POST /app/db/import/commit`
  - Purpose: Commit staged import/restore.
  - Key request fields: `path`, optional `password`.
  - Key response fields: `{ ok, restart_required }`-style restore result.
  - Error behaviors: `400` commit failure; `401` auth/token failure.

- `GET /app/config`
  - Purpose: Read runtime config.
  - Key request fields: none.
  - Key response fields: config object.
  - Error behaviors: Not specified / Not observed.

- `POST /app/config`
  - Purpose: Write runtime config.
  - Key request fields: config object payload.
  - Key response fields: `{ ok, restart_required }`.
  - Error behaviors: `401` when writes/auth gate fails; `400` validation if payload invalid.

### Auth
- `GET /session/token`
  - Purpose: Return CSRF/session token and set session cookie.
  - Key request fields: none.
  - Key response fields: `{ token }` and cookie set.
  - Error behaviors: Not specified / Not observed.

### Deprecated / Legacy Wrappers (Forbidden for new code)
- `POST /app/ledger/purchase` — **DEPRECATED WRAPPER** to `/app/purchase`.
- `POST /app/ledger/stock/out` — **DEPRECATED WRAPPER** to `/app/stock/out`.
- `POST /app/ledger/stock_in` and `POST /app/stock_in` — **DEPRECATED WRAPPER** to `/app/stock/in`.
- `GET /app/ledger/movements` — **DEPRECATED WRAPPER** to `/app/ledger/history`.
- `POST /app/manufacturing/run` — **DEPRECATED WRAPPER** to `/app/manufacture`.
- `GET /app/manufacturing/runs` and `GET /app/manufacturing/history` — legacy reads; canonical replacement not specified / not observed.
- `POST /app/consume`, `POST /app/adjust`, `GET /app/valuation`, `GET /app/ledger/valuation`, `POST /app/inventory/run` — legacy/non-canonical inventory surface.
- UI MUST NOT call deprecated wrappers or legacy/non-canonical routes.

## 3. Quantity Contract (Authoritative v2)
- Canonical quantity input object:
  - `quantity_decimal`: string decimal representation.
    - MUST parse as numeric decimal in backend.
    - Sign/zero constraints are endpoint-specific (`> 0` enforced for purchase/stock flows and recipe component requirements where validated).
  - `uom`: string.
    - MUST be valid for the item dimension.
- Forbidden legacy keys (explicit): `qty`, `qty_base`, `quantity_int`, `quantity`, `output_qty`, `qty_required`, `raw_qty`.
- All base-unit conversion happens **ONLY in backend**.
- Base integer fields never appear at canonical boundary.

### Dimension table
- `count`: `mc` (base), `ea`
- `length`: `mm` (base), `cm`, `m`
- `weight`: `mg` (base), `g`, `kg`
- `area`: `mm2` (base), `cm2`, `m2`
- `volume`: `mm3` (base), `cm3`, `ml`, `l`, `m3`

### Validation and error behaviors
- Invalid or unsupported `uom` for dimension MUST return `400` (`invalid_quantity`/unsupported unit error path).
- Legacy quantity keys in canonical payload MUST return `400` with `legacy_quantity_keys_forbidden` details.
- Item lookup failures during quantity normalization MUST return `404` (`item_not_found`).
- Stock shortages during stock-out/manufacture flows MUST return `400` shortage details.

### stockIn vs stockOut sign conventions
- Canonical API request quantities are positive human values (`quantity_decimal`); stock direction is inferred by endpoint (`/app/stock/in` vs `/app/stock/out`).
- Negative quantity semantics at canonical boundary: Not observed as supported.

## 4. Cost & COGS Authority
- `unit_cost_cents` is authoritative as **integer cents per HUMAN unit** (`item.uom` domain), never per base unit.
- Manufacturing per-output costing authority divides total input cost by **human output quantity** (`quantity_decimal` domain), not base integer output quantity.
- COGS valuation/FIFO authority remains backend-owned.
- UI MUST NOT compute domain cost/COGS math; UI MUST display server-provided values only.
- FIFO cost-layer internals beyond declared authority: Not specified / Not observed.

## 5. UI Containment Rules (Enforced)
- Only `core/ui/js/api.js` and `core/ui/js/token.js` may call `fetch()`.
- No `window.fetch` patch outside `core/ui/js/token.js`.
- UI must send only v2 quantity fields (`quantity_decimal` + `uom`) to canonical mutation routes.
- No silent `uom` fallbacks (e.g., `'ea'`) in mutation payload paths.
- Mandatory gates before manual smoke/merge:
  - `scripts/ui_contract_audit.sh` MUST PASS.
  - `scripts/ui_phaseA_structural_guard.sh` MUST PASS (Guard 5 NOTE allowed).

## 6. Drift Prevention & Extension Rules
Required process for endpoint/contract changes:
1. Update SoT (delta).
2. Implement backend change (only if governance permits; otherwise STOP).
3. Update canonical UI client (`core/ui/js/api/canonical.js`) for any UI-facing surface.
4. Update guard scripts (`scripts/ui_contract_audit.sh`, `scripts/ui_phaseA_structural_guard.sh`) when allow-lists/patterns change.
5. Update `API_CONTRACT.md`.
6. Run both audit scripts and require PASS (Guard 5 NOTE allowed by guard policy).
7. Only then implement/merge UI usage.

- **No endpoint may be added or changed without updating `API_CONTRACT.md`.**

## 7. Regeneration Rules (OpenAPI vs Governance)
- `/openapi.json` is machine schema output.
- `API_CONTRACT.md` is governance and boundary contract.
- If OpenAPI contradicts `API_CONTRACT.md`, a SoT delta is REQUIRED; do not silently reconcile.
