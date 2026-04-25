# 02_API_AND_UI_CONTRACT_MAP

- Document purpose: Operational contract index for backend route surface, frontend screens, and UI/backend dependency edges, used to preserve predictability and expose drift before it becomes silent contract breakage.
- Primary authority basis: Mounted routes in `core/api/http.py`, `core/api/routes/*`, `core/reader/api.py`, `core/organizer/api.py`, and SPA usage in `core/ui/app.js`, `core/ui/js/**/*`.
- Best use: Contract checking, route inventory, UI/backend coherence review, wrapper/drift detection.
- Refresh triggers: Route additions/removals, router remounting, screen changes, payload shape changes, legacy-wrapper cleanup.
- Highest-risk drift areas: Missing backup endpoints, stub transaction endpoints used by the UI, `/app/logs` vs `/logs` naming collision, and mixed route-level guard patterns.
- Key dependent files / modules: `core/api/http.py`, `core/api/routes/items.py`, `core/api/routes/recipes.py`, `core/api/routes/manufacturing.py`, `core/api/routes/ledger_api.py`, `core/api/routes/finance_api.py`, `core/ui/app.js`, `core/ui/js/cards/*`.

## Top Contract Drift Risks

This map exists to keep authority boundaries explicit. Canonical, supported, secondary, and legacy or drifted surfaces are separated so operators and maintainers can see where predictability is guaranteed and where compatibility or debt still exists.

- Drifted: `core/ui/js/cards/backup.js` expects `/app/backup` or `/app.db`; no matching mounted backend route was found.
- Drifted: `core/ui/js/cards/home_donuts.js` uses `/app/transactions/summary` and `/app/transactions`, but both endpoints are explicit stubs.
- Canonical: `/session/token` authority is only `core/api/http.py`; legacy alternate runtime surfaces that previously conflicted here were removed.
- Drifted: `/app/logs` is the UI event-feed endpoint, while `/logs` is the text runtime log tail; similar names, different contracts.
- Drifted: Some mounted `/app/*` mutations rely on global middleware rather than route-local auth/write dependencies; see `04_SECURITY_TRUST_AND_OPERATIONS.md`.

Silent contract drift is a stability risk. The purpose of this document is not to enlarge the declared surface, but to keep the live supported surface explicit and reviewable.

## Public and bootstrap routes

| Method | Path | Status | Purpose | Primary handler |
| --- | --- | --- | --- | --- |
| `GET` | `/` | Canonical | Redirect to `/ui/shell.html`. | `core/api/http.py` |
| `GET` | `/ui` | Canonical | Redirect to SPA shell. | `core/api/http.py` |
| `GET` | `/ui/index.html` | Canonical | Redirect stub to SPA shell. | `core/api/http.py` |
| `GET` | `/favicon.ico` | Canonical | Favicon response. | `core/api/http.py` |
| `GET` | `/health` | Canonical | Minimal health/version response. | `core/api/http.py` |
| `GET` | `/health/detailed` | Secondary | Dev-only detailed health payload. | `core/api/http.py` |
| `GET` | `/dev/paths` | Secondary | Path diagnostics. | `core/api/http.py` |
| `GET` | `/session/token` | Canonical | Mint/read current session token and set cookie. | `core/api/http.py` |
| `GET` | `/ui/plugins/{plugin_id}` | Canonical | Serve plugin UI root asset. | `core/api/http.py` |
| `GET` | `/ui/plugins/{plugin_id}/{resource_path:path}` | Canonical | Serve plugin UI asset path. | `core/api/http.py` |

## Canonical `/app/*` routes

### App/system/config/admin surface

| Method | Path | Status | Guard note | Purpose | Primary handler |
| --- | --- | --- | --- | --- | --- |
| `GET` | `/app/config` | Canonical | Route-local token/write deps absent; protected by global middleware | Read runtime UI/update/launcher config. | `core/api/routes/config.py` |
| `POST` | `/app/config` | Canonical | `require_writes`; route-local token dep absent | Write runtime UI/update/launcher config. | `core/api/routes/config.py` |
| `GET` | `/app/update/check` | Canonical | Route-local token/write deps absent | One-shot update check. | `core/api/routes/update.py` |
| `GET` | `/app/system/state` | Canonical | Explicit token dep | Return bus mode, first-run, counts, build/schema status. | `core/api/routes/system_state.py` |
| `POST` | `/app/system/start-fresh` | Canonical | Explicit token + `require_writes` | Switch demo -> prod and initialize fresh prod DB. | `core/api/routes/system_state.py` |
| `POST` | `/app/db/export` | Canonical | Protected router + `require_writes` | Create encrypted DB export. | `core/api/http.py` |
| `GET` | `/app/db/exports` | Canonical | Protected router + `require_writes` | List export files. | `core/api/http.py` |
| `POST` | `/app/db/import/upload` | Canonical | Protected router + `require_writes` | Upload backup file to staging area. | `core/api/http.py` |
| `POST` | `/app/db/import/preview` | Canonical | Protected router + `require_writes` | Preview staged import file. | `core/api/http.py` |
| `POST` | `/app/db/import/commit` | Canonical | Protected router + `require_writes` | Replace live DB from staged backup. | `core/api/http.py` |

### Catalog, contacts, and recipes

| Method | Path | Status | Guard note | Purpose | Primary handler |
| --- | --- | --- | --- | --- | --- |
| `GET` | `/app/items` | Canonical | Explicit token dep | List items with on-hand/FIFO display fields. | `core/api/routes/items.py` |
| `GET` | `/app/items/{item_id}` | Canonical | Explicit token dep | Get item detail plus batch summary. | `core/api/routes/items.py` |
| `POST` | `/app/items` | Canonical | Explicit token + `require_writes` + owner commit | Create item. | `core/api/routes/items.py` |
| `PUT` | `/app/items/{item_id}` | Canonical | Explicit token + `require_writes` + owner commit | Update item. | `core/api/routes/items.py` |
| `DELETE` | `/app/items/{item_id}` | Canonical | Explicit token + `require_writes` + owner commit | Delete or archive item. | `core/api/routes/items.py` |
| `GET` | `/app/vendors` | Canonical | Explicit token dep | List vendor/org facade. | `core/api/routes/vendors.py` |
| `GET` | `/app/vendors/{id}` | Canonical | Explicit token dep | Get vendor/org record. | `core/api/routes/vendors.py` |
| `POST` | `/app/vendors` | Canonical | Explicit token + write access + owner commit | Create vendor/org record. | `core/api/routes/vendors.py` |
| `PUT` | `/app/vendors/{id}` | Canonical | Explicit token + write access + owner commit | Update vendor/org record. | `core/api/routes/vendors.py` |
| `DELETE` | `/app/vendors/{id}` | Canonical | Explicit token + write access + owner commit | Delete vendor/org record. | `core/api/routes/vendors.py` |
| `GET` | `/app/contacts` | Canonical | Explicit token dep | List contact facade. | `core/api/routes/vendors.py` |
| `GET` | `/app/contacts/{id}` | Canonical | Explicit token dep | Get contact record. | `core/api/routes/vendors.py` |
| `POST` | `/app/contacts` | Canonical | Explicit token + write access + owner commit | Create contact record. | `core/api/routes/vendors.py` |
| `PUT` | `/app/contacts/{id}` | Canonical | Explicit token + write access + owner commit | Update contact record. | `core/api/routes/vendors.py` |
| `DELETE` | `/app/contacts/{id}` | Canonical | Explicit token + write access + owner commit | Delete contact record. | `core/api/routes/vendors.py` |
| `GET` | `/app/recipes` | Canonical | Explicit token dep | List recipes. | `core/api/routes/recipes.py` |
| `GET` | `/app/recipes/{rid}` | Canonical | Explicit token dep | Get recipe detail. | `core/api/routes/recipes.py` |
| `POST` | `/app/recipes` | Canonical | Explicit token + `require_writes` + owner commit | Create recipe. | `core/api/routes/recipes.py` |
| `PUT` | `/app/recipes/{rid}` | Canonical | Explicit token + `require_writes` + owner commit | Update recipe. | `core/api/routes/recipes.py` |
| `DELETE` | `/app/recipes/{recipe_id}` | Canonical | Explicit token + `require_writes` + owner commit | Delete recipe. | `core/api/routes/recipes.py` |

### Inventory, manufacturing, finance, and logs

| Method | Path | Status | Guard note | Purpose | Primary handler |
| --- | --- | --- | --- | --- | --- |
| `POST` | `/app/manufacture` | Canonical | Explicit token + `require_writes` + owner commit | Canonical manufacturing run. | `core/api/routes/manufacturing.py` |
| `POST` | `/app/purchase` | Canonical | Route-local auth/write deps absent | Canonical purchase/stock-in mutation. | `core/api/routes/ledger_api.py` |
| `POST` | `/app/stock/in` | Canonical | Route-local auth/write deps absent | Canonical stock-in mutation. | `core/api/routes/ledger_api.py` |
| `POST` | `/app/stock/out` | Canonical | Route-local auth/write deps absent | Canonical stock-out mutation. | `core/api/routes/ledger_api.py` |
| `GET` | `/app/ledger/history` | Canonical | Route-local token dep absent | Canonical movement history. | `core/api/routes/ledger_api.py` |
| `POST` | `/app/finance/expense` | Canonical | Route-local auth/write deps absent | Record expense cash event. | `core/api/routes/finance_api.py` |
| `POST` | `/app/finance/refund` | Canonical | Route-local auth/write deps absent | Record refund and optional restock. | `core/api/routes/finance_api.py` |
| `GET` | `/app/finance/profit` | Canonical | Route-local token dep absent | Profit snapshot. | `core/api/routes/finance_api.py` |
| `GET` | `/app/finance/summary` | Canonical | Route-local token dep absent | Finance KPI summary. | `core/api/routes/finance_api.py` |
| `GET` | `/app/finance/transactions` | Canonical | Route-local token dep absent | Mixed transaction feed. | `core/api/routes/finance_api.py` |
| `GET` | `/app/logs` | Canonical | Route-local token dep absent | Inventory/ledger event feed used by UI logs page. | `core/api/routes/logs_api.py` |

## Drifted or non-canonical `/app/*` surfaces

| Method | Path | Status | Why it is not canonical | Primary handler |
| --- | --- | --- | --- | --- |
| `POST` | `/app/inventory/run` | Legacy | Older direct delta mutation outside canonical stock APIs. | `core/api/http.py` |
| `GET` | `/app/transactions/summary` | Drifted | Explicit stub used by home dashboard. | `core/api/routes/transactions.py` |
| `GET` | `/app/transactions` | Drifted | Explicit stub used by home dashboard. | `core/api/routes/transactions.py` |
| `POST` | `/app/consume` | Legacy | Older ledger mutation surface. | `core/api/routes/ledger_api.py` |
| `POST` | `/app/adjust` | Legacy | Older adjustment surface. | `core/api/routes/ledger_api.py` |
| `GET` | `/app/valuation` | Legacy | Older valuation read surface. | `core/api/routes/ledger_api.py` |
| `GET` | `/app/ledger/health` | Secondary | Diagnostic health/desync surface, not the primary business contract. | `core/api/routes/ledger_api.py` |
| `GET` | `/app/ledger/debug/db` | Secondary | Dev-only DB diagnostic. | `core/api/routes/ledger_api.py` |

## Non-`/app` utility, admin, integration, and dev routes

| Method | Path | Status | Purpose | Primary handler |
| --- | --- | --- | --- | --- |
| `GET` | `/settings/google` | Canonical | Read masked Google credential status. | `core/api/http.py` |
| `POST` | `/settings/google` | Canonical | Save Google client credentials. | `core/api/http.py` |
| `DELETE` | `/settings/google` | Canonical | Clear Google credentials/refresh token. | `core/api/http.py` |
| `GET` | `/settings/reader` | Canonical | Read reader/local-root settings. | `core/api/http.py` |
| `POST` | `/settings/reader` | Canonical | Save reader/local-root settings. | `core/api/http.py` |
| `POST` | `/catalog/open` | Canonical | Open provider catalog stream. | `core/api/http.py` |
| `POST` | `/catalog/next` | Canonical | Read next catalog page. | `core/api/http.py` |
| `POST` | `/catalog/close` | Canonical | Close catalog stream. | `core/api/http.py` |
| `GET` | `/index/state` | Canonical | Read persisted index state. | `core/api/http.py` |
| `POST` | `/index/state` | Canonical | Update persisted index state. | `core/api/http.py` |
| `GET` | `/index/status` | Canonical | Compare current provider state vs saved index state. | `core/api/http.py` |
| `GET` | `/drive/available_drives` | Canonical | List Google shared drives. | `core/api/http.py` |
| `GET` | `/policy` | Canonical | Read owner/tester policy model. | `core/api/http.py` |
| `POST` | `/policy` | Canonical | Save owner/tester policy model. | `core/api/http.py` |
| `POST` | `/plans` | Canonical | Create plan. | `core/api/http.py` |
| `GET` | `/plans` | Canonical | List plans. | `core/api/http.py` |
| `GET` | `/plans/{plan_id}` | Canonical | Get plan. | `core/api/http.py` |
| `POST` | `/plans/{plan_id}/preview` | Canonical | Preview plan stats. | `core/api/http.py` |
| `POST` | `/plans/{plan_id}/commit` | Canonical | Commit plan actions. | `core/api/http.py` |
| `POST` | `/plans/{plan_id}/export` | Canonical | Export plan JSON. | `core/api/http.py` |
| `GET` | `/plugins` | Canonical | List loaded plugins/descriptors. | `core/api/http.py` |
| `POST` | `/plugins/{service_id}/read` | Canonical | Plugin read op dispatch. | `core/api/http.py` |
| `POST` | `/plugins/{pid}/enable` | Canonical | Toggle plugin enabled flag. | `core/api/http.py` |
| `POST` | `/probe` | Canonical | Probe providers/plugins. | `core/api/http.py` |
| `GET` | `/capabilities` | Canonical | Return signed capability manifest. | `core/api/http.py` |
| `POST` | `/execTransform` | Canonical | Execute transform proposal path. | `core/api/http.py` |
| `POST` | `/policy.simulate` | Canonical | Evaluate policy decision. | `core/api/http.py` |
| `POST` | `/nodes.manifest.sync` | Canonical | Validate signed manifest payload. | `core/api/http.py` |
| `GET` | `/transparency.report` | Canonical | Runtime transparency report. | `core/api/http.py` |
| `GET` | `/logs` | Canonical | Return text runtime log tail. | `core/api/http.py` |
| `GET` | `/local/available_drives` | Canonical | Enumerate local drives/mounts. | `core/api/http.py` |
| `GET` | `/local/validate_path` | Canonical | Validate local directory path. | `core/api/http.py` |
| `POST` | `/open/local` | Canonical | Open allow-listed local path in OS explorer. | `core/api/http.py` |
| `POST` | `/app/update/stage` | Canonical | Manual trusted update staging behind session auth and write gate; prepares `verified_ready` only. | `core/api/routes/update.py` |
| `POST` | `/server/restart` | Canonical | Exit process for manual restart. | `core/api/http.py` |
| `POST` | `/reader/local/resolve_ids` | Canonical | Map local paths -> reader IDs. | `core/reader/api.py` |
| `POST` | `/reader/local/resolve_paths` | Canonical | Map reader IDs -> local paths. | `core/reader/api.py` |
| `POST` | `/organizer/duplicates/plan` | Canonical | Generate duplicate-move plan. | `core/organizer/api.py` |
| `POST` | `/organizer/rename/plan` | Canonical | Generate rename-normalization plan. | `core/organizer/api.py` |
| `POST` | `/oauth/google/start` | Canonical | Start Google OAuth flow. | `core/api/http.py` |
| `GET` | `/oauth/google/callback` | Canonical | Exchange code for refresh token. | `core/api/http.py` |
| `POST` | `/oauth/google/revoke` | Canonical | Revoke/clear refresh token. | `core/api/http.py` |
| `GET` | `/oauth/google/status` | Canonical | Return Google connection status. | `core/api/http.py` |
| `GET` | `/dev/writes` | Secondary | Dev-only writes-enabled flag; `404` when `BUS_DEV!=1`, session auth required when `BUS_DEV=1`. | `core/api/routes/dev.py` |
| `POST` | `/dev/writes` | Secondary | Stubbed dev endpoint; returns `404`; same dev/auth guard model as other `/dev/*` routes. | `core/api/routes/dev.py` |
| `GET` | `/dev/db/where` | Secondary | Dev-only DB path diagnostic; `404` when `BUS_DEV!=1`, session auth required when `BUS_DEV=1`. | `core/api/routes/dev.py` |
| `GET` | `/dev/paths` | Secondary | Dev-only path diagnostic; `404` when `BUS_DEV!=1`, session auth required when `BUS_DEV=1`. | `core/api/http.py` |
| `GET` | `/dev/journal/info` | Secondary | Tail inventory journal; `404` when `BUS_DEV!=1`, session auth required when `BUS_DEV=1`. | `core/api/http.py` |
| `GET` | `/dev/ping_plugin` | Secondary | Windows sandbox/plugin-host handshake check; `404` when `BUS_DEV!=1`, session auth required when `BUS_DEV=1`. | `core/api/http.py` |

## Legacy wrappers and aliases

| Method | Path | Status | Canonical replacement |
| --- | --- | --- | --- |
| `POST` | `/app/manufacturing/run` | Legacy | `/app/manufacture` |
| `GET` | `/app/manufacturing/runs` | Legacy | No separate canonical replacement; see journal-backed recent runs behavior in `core/api/routes/manufacturing.py`. |
| `GET` | `/app/manufacturing/history` | Legacy | Same behavior as `/app/manufacturing/runs`. |
| `POST` | `/app/ledger/purchase` | Legacy | `/app/purchase` |
| `POST` | `/app/ledger/stock/out` | Legacy | `/app/stock/out` |
| `POST` | `/app/ledger/stock_in` | Legacy | `/app/stock/in` |
| `POST` | `/app/stock_in` | Legacy | `/app/stock/in` |
| `GET` | `/app/movements` | Legacy | `/app/ledger/history` |
| `GET` | `/app/ledger/movements` | Legacy | `/app/ledger/history` |
| `GET` | `/app/ledger/valuation` | Legacy | `/app/valuation` |
| `POST` | `/app/ledger/consume` | Legacy | `/app/consume` |
| `POST` | `/app/ledger/adjust` | Legacy | `/app/adjust` |

## Frontend route and screen inventory

| Hash route | Status | Screen / behavior | Main files |
| --- | --- | --- | --- |
| `#/home` | Canonical | Home dashboard with version badge and transaction widgets. | `core/ui/app.js`, `core/ui/js/cards/home.js`, `core/ui/js/cards/home_donuts.js` |
| `#/welcome` | Canonical | Onboarding/EULA/demo-mode entry flow. | `core/ui/app.js` |
| `#/inventory` | Canonical | Inventory screen; supports `#/inventory/{id}`. | `core/ui/js/cards/inventory.js` |
| `#/manufacturing` | Canonical | Manufacturing run screen. | `core/ui/js/cards/manufacturing.js` |
| `#/recipes` | Canonical | Recipe screen; supports `#/recipes/{id}`. | `core/ui/js/cards/recipes.js` |
| `#/contacts` | Canonical | Contacts/vendors/orgs screen; supports `#/contacts/{id}`. | `core/ui/js/cards/vendors.js` |
| `#/settings` | Canonical | Settings + admin/backup/import/export. | `core/ui/js/cards/settings.js`, `core/ui/js/cards/admin.js` |
| `#/logs` | Canonical | UI event-log screen backed by `/app/logs`. | `core/ui/js/logs.js` |
| `#/finance` | Canonical | Finance KPI + transactions screen. | `core/ui/js/cards/finance.js` |
| `#/runs` | Drifted | Placeholder screen; detail route also normalizes. | `core/ui/app.js` |
| `#/import` | Drifted | Placeholder screen; real import UI is under Settings/Admin. | `core/ui/app.js` |
| `#/`, empty hash | Canonical | Normalized at boot; route table still maps bare root to inventory. | `core/ui/app.js` |
| `#/admin`, `#/dashboard`, `#/items`, `#/vendors` and item/vendor detail aliases | Legacy | Aliases redirected to canonical hash routes. | `core/ui/app.js` |

## Frontend expectations that do not cleanly map to live backend behavior

| UI expectation | Status | Backend reality | Evidence |
| --- | --- | --- | --- |
| Backup export via `/app/backup` or `/app.db` | Drifted | No mounted route found. | `core/ui/js/cards/backup.js`, route inventory above |
| Home dashboard transaction widgets | Drifted | Endpoints exist but are explicit stubs, not full business data. | `core/ui/js/cards/home_donuts.js`, `core/api/routes/transactions.py` |
| Dedicated `#/runs` and `#/import` screens | Drifted | Routes exist in SPA but render placeholders only. | `core/ui/app.js` |

## UI-to-API dependency map

| Screen | Direct API dependencies |
| --- | --- |
| Welcome/onboarding | `/session/token`, `/app/system/state`, `/app/system/start-fresh`, `/license/EULA.md` |
| Home | `/openapi.json`, `/app/transactions/summary?window=30d`, `/app/transactions?limit=10` |
| Inventory | `/app/items`, `/app/items/{id}`, `/app/stock/in`, `/app/stock/out`, `/app/purchase`, `/app/finance/refund`, `/app/vendors?is_vendor=true`, `/app/contacts?is_vendor=true`, `/app/items/{id}` `DELETE` |
| Manufacturing | `/app/recipes`, `/app/recipes/{id}`, `/app/manufacture`, `/app/ledger/history` |
| Recipes | `/app/items`, `/app/recipes`, `/app/recipes/{id}`, `/app/recipes` `POST`, `/app/recipes/{id}` `PUT|DELETE` |
| Contacts | `/app/vendors?is_org=true`, `/app/vendors?is_vendor=true`, `/app/contacts?...`, `/app/contacts` `POST`, `/app/vendors/{id}` `PUT|DELETE`, `/app/contacts/{id}` `PUT|DELETE` |
| Settings | `/app/config`, `/app/update/check`, `/app/update/stage` |
| Settings/Admin | `/app/db/export`, `/app/db/exports`, `/app/db/import/upload`, `/app/db/import/preview`, `/app/db/import/commit` |
| Logs | `/app/logs?limit=...&cursor_id=...` |
| Finance | `/app/finance/summary?from=...&to=...`, `/app/finance/transactions?from=...&to=...&limit=100` |

## Update UX and Handoff Notes

- The Settings/sidebar update UX is a manual `Update` button, not a raw download-link primary action.
- `GET /app/update/check` remains read-only and only reports update availability/state.
- `POST /app/update/stage` performs the trusted staging chain and can return `verified_ready` plus restart guidance, but it does not force restart.
- Launcher handoff to `verified_ready` happens only on next start, after DB ownership lock, and follows configured verified launch policy.
- The running EXE is not overwritten; staged versions remain confined under the local update cache until a later launcher handoff.

## Contract-sensitive payloads

| Surface | Status | Key contract |
| --- | --- | --- |
| `/session/token` | Canonical | Returns `{ token }` and sets session cookie. |
| `/app/system/state` | Canonical | Returns `bus_mode`, `is_first_run`, `counts`, `basis`, `build.version`, `build.schema_version`, `status`. |
| `/app/update/check` | Canonical | Returns exactly `current_version`, `latest_version`, `update_available`, `download_url`, `error_code`, `error_message`. |
| `/app/items*` | Canonical | Item rows include identity, unit/dimension, FIFO/on-hand display fields, vendor/location/type fields, and detail batch summary. |
| `/app/recipes*` | Canonical | Uses `quantity_decimal` + `uom`; legacy quantity keys are rejected. |
| `/app/manufacture` | Canonical | Requires `quantity_decimal` + `uom`; success returns `ok`, `status`, `run_id`, `output_unit_cost_cents`. |
| `/app/ledger/history` | Canonical | Returns `{ movements: [...] }`; base `qty_change` is hidden unless `include_base=true` or `BUS_DEV=1`. |
| `/app/finance/summary` | Canonical | Returns KPI totals plus `runs_count`, `units_produced`, `units_sold`, `from`, `to`. |
| `/app/finance/transactions` | Canonical | Returns mixed transaction kinds including `sale`, `refund`, `expense`, `manufacturing_run`, `purchase_inferred`. |
| `/app/db/import/*` | Canonical | Upload stages a file path; preview/commit require `{ path, password }`. |

## Freeze Notes

- Refresh on: mounted route changes, wrapper removals, screen rewrites, payload-key changes, or guard-model changes that affect contract assumptions.
- Fastest invalidators: deleting legacy wrappers, implementing real home transactions, adding/removing `/app/*` routes, or replacing the SPA router.
- Check alongside: `04_SECURITY_TRUST_AND_OPERATIONS.md` for guard/enforcement truth and `05_RELEASE_UPDATE_AND_DEPLOYMENT_FLOW.md` for update-check contract details.

