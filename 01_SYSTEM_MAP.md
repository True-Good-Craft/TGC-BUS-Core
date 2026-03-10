# 01_SYSTEM_MAP

- Document purpose: Fast skeletal map of BUS Core runtime, authority owners, trust boundaries, and coupling hotspots.
- Primary authority basis: `core/api/http.py`, `launcher.py`, `core/ui/app.js`, `core/appdb/*`, `core/appdata/paths.py`, `core/runtime/core_alpha.py`.
- Best use: First read when locating canonical runtime surfaces or deciding where deeper truth lives.
- Refresh triggers: Entrypoint changes, router remounting, new mutable-state authority, startup-flow changes, new external service dependencies.
- Highest-risk drift areas: Alternate entrypoints, split config/session authority, version/update doc drift, repo-local mutable state outside AppData.
- Key dependent files / modules: `core/api/http.py`, `launcher.py`, `core/ui/app.js`, `core/config/manager.py`, `core/config/paths.py`, `core/appdb/engine.py`, `core/runtime/core_alpha.py`.

## Project identity

- BUS Core is a local-first business utility system with a FastAPI backend and a static SPA frontend.
- Repository evidence shows active domains for inventory, ledger/stock, recipes, manufacturing, contacts/vendors, finance, backups/imports, plugin-backed file/Drive cataloging, and opt-in update checks.
- Native runtime is Windows-first (`launcher.py`, `BUS-Core.spec`); container runtime also exists (`Dockerfile`, `docker-compose.yml`).

## System Authority Map

| Concern | Status | Authority location | Notes |
| --- | --- | --- | --- |
| Runtime HTTP surface | Canonical | `core/api/http.py::create_app()` and mounted routers | Referenced by `Dockerfile`, `docker-compose.yml`, `launcher.py`, and dev/smoke helper `scripts/launch.ps1`. |
| Native app entry | Canonical | `launcher.py` | Only supported native entry; starts BUS Core locally, opens `/ui/shell.html`, and manages tray lifecycle. |
| Container entry | Canonical | `Dockerfile` command `uvicorn core.api.http:create_app --factory` | Only supported container entry; same HTTP surface as native runtime. |
| Dev/smoke HTTP launcher | Secondary | `scripts/launch.ps1` | Scripted helper for smoke/dev automation against `core.api.http:create_app`; not a supported native runtime entry. |
| UI routing / boot | Canonical | `core/ui/app.js`, `core/ui/shell.html` | Hash routes, onboarding redirects, version badge, startup update check. |
| API contract | Canonical | Mounted routes in `core/api/http.py` and `core/api/routes/*` | Detailed in `02_API_AND_UI_CONTRACT_MAP.md`. |
| Persistence schema | Canonical | `core/appdb/models.py`, `core/appdb/models_recipes.py`, `core/api/http.py::startup_migrations()` | SQL files in `migrations/` are supplementary, not the only authority. |
| Durable settings config | Drifted | Split between `core/config/manager.py` and `core/config/paths.py` | Two live JSON config stores exist; see `03_DATA_CONFIG_AND_STATE_MODEL.md`. |
| Session/auth authority | Drifted | `session_guard`, `GET /session/token`, `tgc.security.require_token_ctx`, `core.api.http.require_token_ctx` | Multiple live token authorities; see `04_SECURITY_TRUST_AND_OPERATIONS.md`. |
| Update check behavior | Canonical | `core/api/routes/update.py`, `core/services/update.py`, `core/config/manager.py` | UI contract lives in `core/ui/js/update-check.js`. |
| Release version | Canonical | `core/version.py` | `VERSION` is the strict SemVer release authority; `INTERNAL_VERSION` is the working revision. |
| Repository docs | Secondary | `README.md`, `SOT.md`, `API_CONTRACT.md`, `CHANGELOG.md`, `docs/*` | Useful context; code wins on conflict. |

## Top-level Repository Skeleton

| Path | Main ownership |
| --- | --- |
| `core/` | Product code: backend, frontend, DB schema, services, runtime, plugins, adapters. |
| `tgc/` | App state, tokens, settings, logging, compatibility shims. |
| `config/` | Repository-shipped policy/plugin config. |
| `data/` | Repo-local mutable state used by some subsystems (`index_state.json`, `settings_plugins.json`). |
| `migrations/` | Supplemental SQL migration snippets. |
| `plugins/`, `plugins_user/` | Plugin discovery roots. |
| `scripts/` | Build, smoke, launch, release, seed helpers. |
| `docs/` | Secondary docs; not primary authority over code. |
| `.github/` | CI/publish workflows and build/release agent instructions. |
| `license/` | Runtime-served EULA/license assets. |

## Runtime Components

| Component | Status | Owner / entry | Talks to |
| --- | --- | --- | --- |
| FastAPI app | Canonical | `core/api/http.py` | SQLite, journals, secrets, broker, UI static assets, update manifest host. |
| Native launcher | Canonical | `launcher.py` | FastAPI app, browser, tray icon, local port. |
| SPA shell | Canonical | `core/ui/shell.html`, `core/ui/app.js` | `/session/token`, `/app/*`, `/openapi.json`, `/license/EULA.md`. |
| SQLite persistence | Canonical | `core/appdb/engine.py`, `core/appdb/models*.py` | AppData DB files or `BUS_DB` override. |
| Journals / logs | Canonical | `core/journal/*`, `core/api/http.py`, `tgc/logging_setup.py` | `%LOCALAPPDATA%\BUSCore\app\data\journals`, runtime log files. |
| Broker / providers | Canonical | `core/domain/bootstrap.py`, `core/adapters/*`, plugin loader | Local FS, Google Drive, plugin services. |
| Background indexer | Canonical | `core/api/http.py` | `data/index_state.json`, broker catalog surfaces. |
| Update check path | Canonical | `core/services/update.py` | Hosted manifest URL from config. |
| Removed legacy entry surfaces | Resolved | `app.py`, `tgc/http.py`, `core/main.py`, `tgc_controller.spec` | Deleted to prevent parallel runtime/package authority. |

## Startup and Request Skeleton

### Startup path

1. Native path: `launcher.py` prepares runtime dirs, calls `build_app()`, starts Uvicorn on `127.0.0.1:<port>`, opens `/ui/shell.html`.
2. App build: `build_app()` creates `CoreAlpha`, sets `RUN_ID`, writes `session_token.txt`, sets `LOG_FILE`, and logs the trust banner.
3. App init: `create_app()` attaches `AppState`, mounts domain routers, and exposes static assets.
4. Lifespan: `startup_migrations()`, `_buscore_writeflag_startup()`, `ensure_core_initialized()`, `_auto_index_if_stale()`, `_start_indexer_event()`.
5. DB startup: demo DB may be seeded via `scripts/dev_seed.py`; declared tables and additive schema patches are ensured.

### Request path

1. `session_guard` allows only public paths without a cookie-backed session.
2. Correlation and maintenance middleware run before handlers.
3. Route handlers resolve DB sessions, services, and broker/providers as needed.
4. Domain mutations may write DB rows, journal entries, audit records, and runtime logs.
5. Exception handlers normalize error envelopes; request logging appends `[request]` lines.

### UI boot path

1. `ensureToken()` calls `/session/token`.
2. UI reads `/openapi.json` for version display.
3. Startup update notice checks `/app/config` then `/app/update/check`.
4. Initial route redirect checks `/app/system/state`.
5. Demo mode plus missing local onboarding flag redirects to `#/welcome`.

## Component Interaction Edges

| Component | Direct dependencies | Owning files |
| --- | --- | --- |
| UI shell | Session bootstrap, system state, config, update check, domain APIs | `core/ui/app.js`, `core/ui/js/cards/*` |
| Inventory UI | Items, stock mutation, finance refund, vendor/contact lookup | `core/ui/js/cards/inventory.js`, `core/ui/js/api/canonical.js` |
| Manufacturing UI | Recipes, manufacture, ledger history | `core/ui/js/cards/manufacturing.js` |
| Settings/Admin UI | Config, update check, DB export/import | `core/ui/js/cards/settings.js`, `core/ui/js/cards/admin.js` |
| HTTP app | DB engine, journals, secrets, broker, capability registry | `core/api/http.py` |
| `CoreAlpha` | Policy engine, journal manager, broker, plugin discovery, capability registry | `core/runtime/core_alpha.py` |
| Broker/providers | Local FS roots, Google credentials/tokens, plugin registry | `core/adapters/fs/provider.py`, `core/adapters/drive/provider.py`, `core/plugins/loader.py` |

## Trust Boundaries

| Boundary | Status | What crosses it |
| --- | --- | --- |
| Browser UI <-> local FastAPI | Canonical | Session cookie, SPA API calls, static assets. |
| FastAPI <-> local DB/files | Canonical | DB writes, exports/imports, journals, logs, secrets, config. |
| FastAPI <-> OS actions | Canonical | Tray/browser launch, Explorer open, process exit/restart, local path validation. |
| FastAPI <-> external network | Canonical | Update manifest fetches, Google OAuth/token exchange, Google Drive API calls. |
| Runtime authority | Canonical | `launcher.py` (native), `core/api/http.py::create_app()` (HTTP surface), and Docker `uvicorn core.api.http:create_app --factory` are the only supported runtime paths. |

## Coupling Hotspots

| Hotspot | Status | Why it matters | Own in |
| --- | --- | --- | --- |
| Config split (`config.json` vs `app\config.json`) | Drifted | Settings, writes, and policy do not share one durable authority. | `03_DATA_CONFIG_AND_STATE_MODEL.md` |
| Session/token split | Drifted | Middleware, AppState token manager, global `SESSION_TOKEN`, and token file all participate. | `04_SECURITY_TRUST_AND_OPERATIONS.md` |
| Version/update authority drift | Narrowed drift | `core/version.py` is now the public release/update source, and `.github/workflows/release-mirror.yml` machine-checks `tag == v{VERSION}` before publishing manifest metadata; remaining drift is limited to unsigned/unverified artifact metadata and release-history dependence on GitHub release assets. | `05_RELEASE_UPDATE_AND_DEPLOYMENT_FLOW.md` |
| Repo-local mutable state | Drifted | Some live state is stored in repo `data/` instead of AppData. | `03_DATA_CONFIG_AND_STATE_MODEL.md` |
| Placeholder/stale UI surfaces | Drifted | `#/runs`, `#/import`, backup UI, and stub transaction widgets can mislead contract assumptions. | `02_API_AND_UI_CONTRACT_MAP.md` |
| Runtime authority | Canonical | Legacy alternate entry surfaces were removed; `scripts/launch.ps1` remains dev/smoke-only around the canonical factory. | This file |

## Freeze Notes

- Refresh on: entrypoint changes, router remounting, new runtime services, trust-boundary changes, or path-authority changes.
- Fastest invalidators: switching the canonical entrypoint, consolidating config/session authority, changing mounted route roots, or replacing the SPA shell.
- Check alongside: `02_API_AND_UI_CONTRACT_MAP.md` for route truth, `03_DATA_CONFIG_AND_STATE_MODEL.md` for storage authority, `04_SECURITY_TRUST_AND_OPERATIONS.md` for auth/trust splits, `05_RELEASE_UPDATE_AND_DEPLOYMENT_FLOW.md` for version/update authority.




