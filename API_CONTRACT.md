# BUS Core API Contract
Status: Authoritative declared-truth pass

This document describes the current supported BUS Core API as mounted by the runtime today. It is a truth-reconciliation document, not a design target. Mounted routes are not all equally canonical.

Its purpose is to preserve predictability and prevent silent contract drift. If a route exists but is secondary, legacy, stubbed, or drifted, it should be described that way instead of being promoted into the canonical surface.

## 1. Route Tiers and Auth Reality

- Canonical routes are the `/app/*` business and operator routes that the UI and operators should treat as authoritative.
- Supported operational routes are real protected admin/integration surfaces that exist and are supported, but they are not the core business contract.
- Secondary / legacy / drifted routes are mounted but non-canonical. They must not be presented as the preferred API surface for new callers.
- These tiers exist to keep Core predictable: the contract should make drift visible, not blur canonical and compatibility surfaces together.
- `GET /session/token` is the canonical session bootstrap route. It returns `{ "token": "<token>" }` and sets the configured session cookie (`bus_session` by default).
- Non-public routes require that session cookie. Current runtime enforcement is a mix of global middleware and route-local dependencies.
- Middleware-based auth is current truth for several supported routes. The handler does not declare route-local token auth for `/app/config`, `/app/update/check`, `/app/purchase`, `/app/stock/in`, `/app/stock/out`, `/app/ledger/history`, `/app/finance/*`, and `/app/logs`; protection comes from the global `session_guard` middleware.
- Write gating is also mixed by current runtime. Many mutating routes use `require_writes` or `require_write_access`, but `/app/purchase`, `/app/stock/in`, `/app/stock/out`, `/app/finance/expense`, and `/app/finance/refund` do not have a route-local write gate today.
- Owner-commit authorization is route-local on item, vendor/contact, recipe, and manufacture mutations. It is not uniformly applied to all business mutations.
- `/dev/*` routes and `GET /health/detailed` are dev-only. When `BUS_DEV != 1`, they return `404`. When `BUS_DEV = 1`, they still require a valid session cookie.

## 2. Canonical Routes

### Bootstrap and public

- `GET /session/token`
  - Canonical session bootstrap.
  - Returns `{ "token": ... }` and sets the session cookie.

- `GET /health`
  - Minimal public health probe.
  - Returns `{ "ok": true, "version": "<VERSION>" }`.

- `GET /`, `GET /ui`, `GET /ui/index.html`
  - Public redirects to the SPA shell.
  - Useful for runtime reachability, not part of the business API contract.

### Config, update, system, and backup/restore

- `GET /app/config`
  - Read the current runtime config object.
  - Auth is middleware-based, not route-local.

- `POST /app/config`
  - Write the runtime config object.
  - Requires `require_writes`.
  - Returns `{ "ok": true, "restart_required": true }`.

- `GET /app/update/check`
  - Canonical in-app update check.
  - Auth is middleware-based, not route-local.
  - Returns exactly:
    - `current_version`
    - `latest_version`
    - `update_available`
    - `download_url`
    - `error_code`
    - `error_message`

- `POST /app/update/stage`
  - Canonical manual update staging route.
  - Requires session auth and `require_writes`.
  - Executes trusted staging only after the user clicks the UI `Update` button.
  - Returns exactly:
    - `ok`
    - `status`
    - `current_version`
    - `latest_version`
    - `exe_path`
    - `restart_available`
    - `error_code`
    - `error_message`
  - Success means a newer version is verified and written to conservative version+sha keyed `verified_ready_versions` state; legacy `verified_ready` remains a compatibility/latest pointer.
  - It does not force restart, does not overwrite the running EXE, and does not itself launch the staged executable.
  - Launcher handoff, when enabled by config, is evaluated on next start after DB ownership lock.

- `GET /app/system/state`
  - Canonical system boot/state probe.
  - Returns:
    - `bus_mode`
    - `is_first_run`
    - `counts`
    - `demo_allowed`
    - `basis`
    - `build.version`
    - `build.internal_version`
    - `build.schema_version`
    - `status`

- `POST /app/system/start-fresh`
  - Switch to prod mode and initialize a fresh prod DB.
  - Requires session auth and `require_writes`.
  - Returns `{ "ok": true, "restart_required": true }`.

- `POST /app/db/export`
  - Create a DB export.
  - Protected router plus `require_writes`.
  - Requires a non-empty `password`.
  - Returns the export result object from the runtime helper.

- `GET /app/db/exports`
  - List export artifacts.
  - Protected router plus `require_writes`.
  - Returns `{ "ok": true, "exports": [...] }`.

- `POST /app/db/import/upload`
  - Upload a backup file for staged restore.
  - Protected router plus `require_writes`.
  - Multipart upload.
  - Returns the upload staging result, including staged `path` on success.

- `POST /app/db/import/preview`
  - Preview a staged restore.
  - Protected router plus `require_writes`.
  - Request body: `{ "path": "...", "password": "..." }`.
  - Returns the preview result object.
  - Stable `400` error codes include `path_out_of_roots`, `cannot_read_file`, `bad_container`, `decrypt_failed`, `password_required`, and `incompatible_schema`.

- `POST /app/db/import/commit`
  - Commit a staged restore.
  - Protected router plus `require_writes`.
  - Request body: `{ "path": "...", "password": "..." }`.
  - Returns the restore result object on success.
  - Runtime enters maintenance mode during the commit path.

### Items, vendors, contacts, and recipes

- `GET /app/items`
  - List item rows.
  - Excludes archived items by default.
  - `include_archived=true` returns both live and archived items.
  - Response is an array of item records with identity, dimension/uom, on-hand display fields, and FIFO display fields.

- `GET /app/items/{item_id}`
  - Get item detail.
  - Returns the item row plus `batches_summary`.
  - Archived items remain readable.

- `POST /app/items`
  - Create an item.
  - Requires `require_writes`, session auth, and owner commit.
  - Contract-stable fields are item/catalog fields such as `name`, `sku`, `dimension`, `uom`, `price`, `notes`, `vendor_id`, `location`, `item_type`, and `is_product`.
  - Returns the created item record.

- `PUT /app/items/{item_id}`
  - Update an item.
  - Requires `require_writes`, session auth, and owner commit.
  - Returns the updated item record.

- `DELETE /app/items/{item_id}`
  - Delete-or-archive item route.
  - Requires `require_writes`, session auth, and owner commit.
  - If history exists, the item is archived and the response is `{ "archived": true }`.
  - If no dependent history exists, the item is deleted and the response is `{ "ok": true }`.

- `GET /app/vendors`, `GET /app/contacts`
  - List vendor/contact facade records.
  - Supported filters: `q`, `role`, `role_in`, `is_vendor`, `is_org`, `organization_id`.

- `GET /app/vendors/{id}`, `GET /app/contacts/{id}`
  - Get a single vendor/contact record.
  - `404` when missing.

- `POST /app/vendors`, `POST /app/contacts`
  - Create a vendor/contact record.
  - Require session auth, `require_write_access`, and owner commit.
  - Return the created record.

- `PUT /app/vendors/{id}`, `PUT /app/contacts/{id}`
  - Update a vendor/contact record.
  - Require session auth, `require_write_access`, and owner commit.
  - Return the updated record.

- `DELETE /app/vendors/{id}`, `DELETE /app/contacts/{id}`
  - Delete a vendor/contact record.
  - Require session auth, `require_write_access`, and owner commit.
  - Support `cascade_children=true` for organization delete behavior.
  - Return `204 No Content` on success.

- `GET /app/recipes`
  - List recipe summaries.
  - Returns recipe records with `id`, `name`, `code`, `output_item_id`, `quantity_decimal`, `uom`, `archived`, and `notes`.

- `GET /app/recipes/{rid}`
  - Get recipe detail.
  - Returns the recipe plus `items[]` lines using `quantity_decimal` and `uom`.

- `POST /app/recipes`
  - Create a recipe.
  - Requires `require_writes`, session auth, and owner commit.
  - Uses v2 quantity fields only:
    - top level: `quantity_decimal`, `uom`
    - component lines: `items[].quantity_decimal`, `items[].uom`
  - Legacy quantity keys are rejected with `400` and `legacy_quantity_keys_forbidden`.

- `PUT /app/recipes/{rid}`
  - Update a recipe.
  - Requires `require_writes`, session auth, and owner commit.
  - Uses the same v2 quantity contract as create.

- `DELETE /app/recipes/{recipe_id}`
  - Delete a recipe.
  - Requires `require_writes`, session auth, and owner commit.
  - Returns `{ "ok": true, "deleted": <recipe_id> }`.

### Canonical stock, ledger, and manufacturing

- `POST /app/purchase`
  - Canonical purchase stock-in route.
  - Current auth is middleware-based, not route-local.
  - Current runtime does not add a route-local write gate.
  - Request body:
    - `item_id`
    - `quantity_decimal`
    - `uom`
    - `unit_cost_cents`
    - optional `source_id`
  - Returns the stock mutation result object from the service layer.

- `POST /app/stock/in`
  - Canonical stock-in route.
  - Current auth is middleware-based, not route-local.
  - Current runtime does not add a route-local write gate.
  - Request body:
    - `item_id`
    - `quantity_decimal`
    - `uom`
    - optional `unit_cost_cents`
    - optional `source_id`
  - Returns the stock mutation result object from the service layer.

- `POST /app/stock/out`
  - Canonical stock-out route.
  - Current auth is middleware-based, not route-local.
  - Current runtime does not add a route-local write gate.
  - Request body:
    - `item_id`
    - `quantity_decimal`
    - `uom`
    - `reason`
    - optional `note`
    - optional `record_cash_event`
    - optional `sell_unit_price_cents`
  - Returns the stock mutation result object, including line allocation detail.

- `GET /app/ledger/history`
  - Canonical movement history read route.
  - Current auth is middleware-based, not route-local.
  - Query params: `item_id`, `limit`, optional `include_base`.
  - Returns `{ "movements": [...] }`.
  - Each movement includes `id`, `item_id`, `batch_id`, `quantity_decimal`, `uom`, `unit_cost_cents`, `source_kind`, `source_id`, `is_oversold`, and `created_at`.
  - `qty_change` is hidden by default and appears only when `include_base=1` or dev mode exposes it.

- `POST /app/manufacture`
  - Canonical manufacturing run route.
  - Requires `require_writes`, session auth, and owner commit.
  - Accepts recipe-based or direct-output manufacturing payloads, but always requires `quantity_decimal` and `uom`.
  - Success response is intentionally small:
    - `ok`
    - `status`
    - `run_id`
    - `output_unit_cost_cents`
  - Shortage failures return `400` with structured shortage detail and a failed `run_id`.

### Canonical finance and app event feed

- `POST /app/finance/expense`
  - Record an expense cash event.
  - Current auth is middleware-based, not route-local.
  - Current runtime does not add a route-local write gate.
  - Request body:
    - `amount_cents`
    - optional `category`
    - optional `notes`
    - optional `created_at`
  - Returns `{ "ok": true, "id": <cash_event_id> }`.

- `POST /app/finance/refund`
  - Record a refund and optional inventory restock.
  - Current auth is middleware-based, not route-local.
  - Current runtime does not add a route-local write gate.
  - Request body:
    - `item_id`
    - `refund_amount_cents`
    - `quantity_decimal`
    - `uom`
    - `restock_inventory`
    - optional `related_source_id`
    - optional `restock_unit_cost_cents`
    - optional `category`
    - optional `notes`
    - optional `created_at`
  - Returns `{ "ok": true, "source_id": "<generated_source_id>" }`.

- `GET /app/finance/profit`
  - Profit snapshot for a date window.
  - Current auth is middleware-based, not route-local.
  - Query params: `from=YYYY-MM-DD`, `to=YYYY-MM-DD`.
  - Returns exactly:
    - `gross_sales_cents`
    - `returns_cents`
    - `net_sales_cents`
    - `cogs_cents`
    - `gross_profit_cents`
    - `from`
    - `to`

- `GET /app/finance/summary`
  - Finance KPI summary for a date window.
  - Current auth is middleware-based, not route-local.
  - Query params: `from=YYYY-MM-DD`, `to=YYYY-MM-DD`.
  - Returns totals plus `runs_count`, `units_produced`, `units_sold`, `from`, and `to`.
  - Invalid windows return `400`.

- `GET /app/finance/transactions`
  - Mixed finance transaction feed for a date window.
  - Current auth is middleware-based, not route-local.
  - Query params: `from=YYYY-MM-DD`, `to=YYYY-MM-DD`, `limit`.
  - Returns `{ "from": ..., "to": ..., "limit": ..., "count": ..., "transactions": [...] }`.
  - Current supported transaction kinds include `sale`, `refund`, `expense`, `manufacturing_run`, and `purchase_inferred`.

- `GET /app/logs`
  - App event feed used by the UI logs screen.
  - Current auth is middleware-based, not route-local.
  - Returns `{ "events": [...], "next_cursor_id": ... }`.
  - This is distinct from `GET /logs`, which returns the runtime text log tail.

## 3. Quantity and Response Semantics Locked by Current Runtime

- Canonical quantity fields are `quantity_decimal` and `uom`.
- Legacy quantity keys are forbidden on canonical stock, manufacture, recipe, and finance refund payloads:
  - `qty`
  - `qty_base`
  - `quantity_int`
  - `quantity`
  - `output_qty`
  - `qty_required`
  - `raw_qty`
- Quantity validation is server-side. The backend accepts units valid for the item's dimension, including basis units where the runtime supports them.
- Missing items during quantity normalization fail closed with `404 item_not_found`.
- Invalid quantity or invalid unit normalization fails with `400`.
- Stock and manufacturing shortage conditions fail with `400`; they are not successful partial completions.
- `/app/ledger/history` is the canonical read surface for movement history. It exposes normalized quantity fields by default and only exposes base `qty_change` when explicitly requested or when dev mode allows it.

## 4. Supported Operational Protected Surface

These routes are supported and mounted, but they are not the canonical business API. Most require the same session cookie as the canonical surface. Many mutating endpoints also use `require_writes`.

- Settings and OAuth
  - `GET|POST|DELETE /settings/google`
  - `GET|POST /settings/reader`
  - `POST /oauth/google/start`
  - `GET /oauth/google/callback`
  - `POST /oauth/google/revoke`
  - `GET /oauth/google/status`

- Catalog, indexing, and local-drive operations
  - `POST /catalog/open`
  - `POST /catalog/next`
  - `POST /catalog/close`
  - `GET|POST /index/state`
  - `GET /index/status`
  - `GET /drive/available_drives`
  - `GET /local/available_drives`
  - `GET /local/validate_path`
  - `POST /open/local`

- Policy, plans, plugins, and capability operations
  - `GET|POST /policy`
  - `POST /plans`
  - `GET /plans`
  - `GET /plans/{plan_id}`
  - `POST /plans/{plan_id}/preview`
  - `POST /plans/{plan_id}/commit`
  - `POST /plans/{plan_id}/export`
  - `GET /plugins`
  - `POST /plugins/{service_id}/read`
  - `POST /plugins/{pid}/enable`
  - `POST /probe`
  - `GET /capabilities`
  - `POST /execTransform`
  - `POST /policy.simulate`
  - `POST /nodes.manifest.sync`
  - `GET /transparency.report`

- Reader and organizer integration
  - `POST /reader/local/resolve_ids`
  - `POST /reader/local/resolve_paths`
  - `POST /organizer/duplicates/plan`
  - `POST /organizer/rename/plan`

- Runtime operations
  - `GET /logs`
  - `POST /server/restart`

## 5. Secondary, Legacy, and Drifted Routes

### Compatibility wrappers

These are mounted compatibility routes, not canonical routes for new callers. Where implemented as wrappers, they are expected to point callers at the canonical replacement, including `X-BUS-Deprecation` headers where the runtime currently emits them.

- `POST /app/manufacturing/run` -> use `POST /app/manufacture`
- `POST /app/ledger/purchase` -> use `POST /app/purchase`
- `POST /app/ledger/stock/out` -> use `POST /app/stock/out`
- `POST /app/ledger/stock_in` -> use `POST /app/stock/in`
- `POST /app/stock_in` -> use `POST /app/stock/in`
- `GET /app/movements` -> use `GET /app/ledger/history`
- `GET /app/ledger/movements` -> use `GET /app/ledger/history`
- `GET /app/ledger/valuation` -> use `GET /app/valuation`
- `POST /app/ledger/consume` -> use `POST /app/consume`
- `POST /app/ledger/adjust` -> use `POST /app/adjust`

### Legacy non-canonical business routes

- `POST /app/consume`
  - Legacy stock-out style mutation surface.
  - Not canonical.

- `POST /app/adjust`
  - Legacy adjustment surface.
  - Not canonical.

- `GET /app/valuation`
  - Legacy valuation read surface.
  - Not canonical.

- `POST /app/inventory/run`
  - Older direct delta inventory mutation surface.
  - Not canonical.

- `GET /app/manufacturing/runs`
  - Legacy journal-backed recent-runs read surface.
  - Not the canonical manufacturing API.

- `GET /app/manufacturing/history`
  - Alias for the same journal-backed recent-runs behavior.
  - Not the canonical manufacturing API.

### Secondary diagnostics and dev-only routes

- `GET /app/ledger/health`
  - Secondary ledger health/desync check.
  - Not a primary business contract route.

- `GET /app/ledger/debug/db`
  - Dev-only ledger DB diagnostic.
  - Secondary only.

- `GET /health/detailed`
  - Dev-only detailed health payload.
  - Secondary only.

- `/dev/*`
  - Secondary dev-only surfaces.
  - Hidden by `404` outside dev mode.

### Drifted or stubbed mounted routes

- `GET /app/transactions/summary`
  - Mounted stub.
  - Returns placeholder dashboard data.
  - Not canonical business contract.

- `GET /app/transactions`
  - Mounted stub.
  - Returns placeholder transaction-list data.
  - Not canonical business contract.

## 6. Remaining Known Drift

- UI drift remains around nonexistent backup endpoints such as `/app/backup` and `/app.db`. Those routes are not mounted and are not canonical.
- `/app/transactions` and `/app/transactions/summary` remain mounted stubs. They are real routes, but they are not canonical business contract.
- Some supported routes rely on middleware-based auth rather than route-local auth declarations. This document reflects that reality instead of normalizing it away.
- Some supported mutating routes also lack a route-local write gate today, notably `/app/purchase`, `/app/stock/in`, `/app/stock/out`, `/app/finance/expense`, and `/app/finance/refund`. That is current runtime truth, not a documented endorsement of a cleaner model.

