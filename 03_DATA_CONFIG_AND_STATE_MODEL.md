# 03_DATA_CONFIG_AND_STATE_MODEL

- Document purpose: Authority map for persistent, mutable, generated, and runtime state in BUS Core.
- Primary authority basis: `core/appdata/paths.py`, `core/appdb/engine.py`, `core/appdb/models.py`, `core/appdb/models_recipes.py`, `core/config/manager.py`, `core/api/routes/system_state.py`, `core/api/http.py`.
- Best use: Determine where state lives, which file or component owns it, and whether authority is canonical, split, or repo-local.
- Refresh triggers: DB schema changes, path-helper changes, config-key changes, onboarding/first-run logic changes, state file relocations.
- Highest-risk drift areas: Repo-local mutable state, mixed session state, ORM-vs-startup schema differences, localStorage vs backend first-run state.
- Key dependent files / modules: `core/appdata/paths.py`, `core/appdb/engine.py`, `core/appdb/models.py`, `core/appdb/models_recipes.py`, `core/config/manager.py`, `core/plugins/loader.py`, `core/api/routes/system_state.py`.

## State Authority Matrix

| State concern | Backing | Status | Authority | Notes |
| --- | --- | --- | --- | --- |
| Inventory, vendors/contacts, ledger, finance, recipes, manufacturing | DB-backed | Canonical | SQLite schema in `core/appdb/models.py` and `core/appdb/models_recipes.py` | Main durable business state. |
| DB path selection | Config/env-derived | Canonical | `core/appdata/paths.py::resolve_db_path()` | Uses `BUS_DB` override or bus mode. |
| Bus mode (`demo` / `prod`) | File/env-backed | Canonical | `core/appdata/paths.py::resolve_bus_mode()` | Priority: `bus_mode.json`, env var, flag file, default. |
| App runtime config | File-backed | Canonical | `%LOCALAPPDATA%\\BUSCore\\config.json` via `core/config/manager.py` | Single app-runtime authority for launcher, UI, backup, updates, write gate, and persisted policy fields. |
| Legacy app-local config fallback | File-backed | Legacy | `%LOCALAPPDATA%\\BUSCore\\app\\config.json` via compatibility reads in `core/config/manager.py` | Read-only fallback for recognized old keys (`writes_enabled`, `role`, `plan_only`) when canonical values are absent. |
| Reader roots / Drive include settings | File-backed | Canonical | `%LOCALAPPDATA%\BUSCore\settings_reader.json` via `core/settings/reader_state.py` | Governs local FS and Drive provider behavior. |
| Plugin enabled flags | Repo-local file-backed | Drifted | `data/settings_plugins.json` via `core/plugins/loader.py` | Lives outside AppData tree. |
| Background index freshness | Repo-local file-backed | Drifted | `data/index_state.json` via `core/api/http.py` | Also outside AppData tree. |
| First-run / demo readiness | Derived runtime state | Canonical | `GET /app/system/state` from DB counts + bus mode | UI adds secondary local flags on top. |
| Onboarding complete / EULA accepted / imperial mode | localStorage/UI state | Secondary | `core/ui/app.js` | UI-facing state only; not the source of business truth. |
| Session/auth state | Cookie + in-memory + file-backed | Drifted | `session_guard`, `AppState.tokens`, global `SESSION_TOKEN`, `session_token.txt` | Split across multiple live authorities. |
| Capability manifest | File-backed generated state | Canonical | `%LOCALAPPDATA%\BUSCore\state\system_manifest.json` | Signed with local HMAC key. |

## Persistence model

### Database engine and location

| Concern | Status | Authority | Evidence |
| --- | --- | --- | --- |
| DB engine | Canonical | SQLite via SQLAlchemy | `core/appdb/engine.py`, `core/config/paths.py` |
| Windows production DB | Canonical | `%LOCALAPPDATA%\BUSCore\app\app.db` | `core/appdata/paths.py` |
| Windows demo DB | Canonical | `%LOCALAPPDATA%\BUSCore\app\app_demo.db` | `core/appdata/paths.py` |
| Explicit DB override | Canonical | `BUS_DB` env var | `core/appdata/paths.py` |
| Container DB | Canonical | `/data/app.db` through `BUS_DB=/data/app.db` | `Dockerfile`, `docker-compose.yml` |
| Legacy repo DB migration | Secondary | One-time copy from repo `data/app.db` in prod mode if AppData DB does not exist | `core/appdb/engine.py` |

### Entity summary

| Entity / table | Status | Key fields / invariants |
| --- | --- | --- |
| `vendors` | Canonical | Shared vendor/contact/org table with `role`, `is_vendor`, `is_org`, `organization_id`, `meta`. |
| `items` | Canonical | `dimension` constrained to `length|area|volume|weight|count`; `qty_stored` base-int; `is_archived` supports soft-retention. |
| `item_batches` | Canonical | FIFO layers with `qty_initial`, `qty_remaining`, `unit_cost_cents`, `source_kind`, `source_id`. |
| `item_movements` | Canonical | Base-int movement history; manufacturing oversell is forbidden by constraint/trigger. |
| `cash_events` | Canonical | Finance ledger with `kind`, `amount_cents`, item linkage, and source correlation. |
| `recipes` / `recipe_items` | Canonical | Output and component quantities are stored as base-int values. |
| `manufacturing_runs` | Canonical | Execution history with `status`, `output_qty`, `meta`. |

### Schema and migration authority

| Concern | Status | Authority | Notes |
| --- | --- | --- | --- |
| Declared schema | Canonical | `core/appdb/models.py`, `core/appdb/models_recipes.py` | Primary table/column contract. |
| Startup schema materialization | Canonical | `Base.metadata.create_all()` in `core/api/http.py::startup_migrations()` | Main runtime migration path. |
| Additive startup patches | Canonical | `_ensure_schema_upgrades()` in `core/api/http.py` | Adds columns/indexes and normalizes vendor name index. |
| SQL migration snippets | Secondary | `migrations/*.sql` | Supplemental evidence; not the only migration authority. |
| Alembic / formal migration runner | Not determined from repository evidence | No `migrations/env.py` or versions tree detected | Formal migration toolchain not present in repo. |

## Storage locations by class

### Canonical AppData-backed durable state

| Path | Status | Purpose |
| --- | --- | --- |
| `%LOCALAPPDATA%\\BUSCore\\config.json` | Canonical | Main app-runtime config for UI, launcher, updates, write gate, and persisted policy fields. |
| `%LOCALAPPDATA%\\BUSCore\\app\\config.json` | Legacy | Non-authoritative compatibility input for recognized pre-reconciliation keys only. |
| `%LOCALAPPDATA%\BUSCore\app\bus_mode.json` | Canonical | Primary persisted bus mode selector. |
| `%LOCALAPPDATA%\BUSCore\app\bus_mode.flag` | Legacy | Alternate bus mode source. |
| `%LOCALAPPDATA%\BUSCore\app\app.db` | Canonical | Production DB. |
| `%LOCALAPPDATA%\BUSCore\app\app_demo.db` | Canonical | Demo DB. |
| `%LOCALAPPDATA%\BUSCore\settings_reader.json` | Canonical | Reader/local-root settings. |
| `%LOCALAPPDATA%\BUSCore\exports\*.db.gcm` | Canonical | Encrypted exports and staged uploads. |
| `%LOCALAPPDATA%\BUSCore\secrets\master.key` | Canonical | Secret-store file fallback key. |
| `%LOCALAPPDATA%\BUSCore\secrets\secrets.json.enc` | Canonical | Encrypted secret-store fallback payload. |
| `%LOCALAPPDATA%\BUSCore\state\system_manifest.json` | Canonical | Signed capability manifest. |
| `%LOCALAPPDATA%\BUSCore\state\capabilities_hmac.key` | Canonical | Capability-manifest signing key. |

### Repo-local mutable state

| Path | Status | Purpose |
| --- | --- | --- |
| `data/index_state.json` | Drifted | Drive/local index freshness state. |
| `data/settings_plugins.json` | Drifted | Plugin enabled flags. |

### Generated artifacts and journals

| Path / artifact | Status | Purpose |
| --- | --- | --- |
| `%LOCALAPPDATA%\BUSCore\app\data\journals\inventory.jsonl` | Canonical | Inventory journal. |
| `%LOCALAPPDATA%\BUSCore\app\data\journals\manufacturing.jsonl` | Canonical | Manufacturing journal and recent-runs source. |
| `%LOCALAPPDATA%\BUSCore\app\data\journals\recipes.jsonl` | Canonical | Recipe mutation journal. |
| `%LOCALAPPDATA%\BUSCore\app\data\journals\plugin_audit.jsonl` | Canonical | Restore/import audit log. |
| `%LOCALAPPDATA%\BUSCore\app\logs\core_<RUN_ID>.log` | Canonical | Runtime request/application log. |
| `dist/`, `build/`, `reports/snapshots/` | Secondary | Build outputs and snapshot artifacts. |

### Ephemeral runtime state

| State | Status | Authority |
| --- | --- | --- |
| OAuth state cache (`_OAUTH_STATES`) | Canonical | In-process memory in `core/api/http.py` |
| `RUN_ID`, `LOG_FILE`, background index task state | Canonical | In-process memory in `core/api/http.py` |
| `window.BUS_ROUTE`, `runtimeSystemState` | Secondary | SPA in-memory route/runtime state |
| `startupCheckDone` | Secondary | UI in-memory update-notice guard |

## Configuration authorities

| Config authority | Status | Stored keys | Owner |
| --- | --- | --- | --- |
| `%LOCALAPPDATA%\\BUSCore\\config.json` | Canonical | `launcher.*`, `ui.theme`, `backup.default_directory`, `dev.writes_enabled`, `updates.*`, `policy.role`, `policy.plan_only` | `core/config/manager.py` |
| `%LOCALAPPDATA%\\BUSCore\\app\\config.json` | Legacy compatibility input | Read-only fallback for `writes_enabled`, `role`, `plan_only` only when canonical values are absent | `core/config/manager.py` compatibility read path |
| `%LOCALAPPDATA%\BUSCore\settings_reader.json` | Canonical | `enabled`, `local_roots`, `drive_includes.*` | `core/settings/reader_state.py` |
| `config/policy.json` | Canonical | `version`, `mode`, `rules[]` | `core/runtime/policy.py` |
| `config/plugins.json` | Canonical repo-shipped config | Discovery/command-bus plugin registry toggles | `core/registry/plugins_json.py` |

## First-run and onboarding authority

| Concern | Status | Authority | Notes |
| --- | --- | --- | --- |
| Demo vs prod mode | Canonical | `resolve_bus_mode()` and `bus_mode.json` | Defaults to demo unless overridden. |
| Demo DB seeding | Canonical | `core/api/http.py::_ensure_demo_seed_database()` | Seeds via `scripts/dev_seed.py`. |
| First-run detection | Canonical | `core/api/routes/system_state.py` | Derived from DB counts across six tables. |
| Onboarding completion flag | Secondary | `localStorage["bus.onboarding.completed"]` | UI-only suppression flag. |
| EULA acceptance flag | Secondary | `localStorage["buscore.eulaAccepted"]` | UI-only acceptance state. |
| Start fresh action | Canonical | `POST /app/system/start-fresh` | Switches bus mode to prod and recreates prod DB. |

## Objective state risks

- Canonical: durable app-runtime config authority is `%LOCALAPPDATA%\\BUSCore\\config.json`; `%LOCALAPPDATA%\\BUSCore\\app\\config.json` remains legacy compatibility input only.
- Drifted: some live mutable state (`data/index_state.json`, `data/settings_plugins.json`) lives in repo `data/`, not AppData.
- Drifted: session/auth state is split across cookie, AppState token manager, global `SESSION_TOKEN`, and a token file.
- Drifted: `vendors.name` is declared unique in ORM metadata, but startup migration logic drops the unique-name index and recreates a non-unique one.
- Secondary: onboarding suppression and EULA acceptance are localStorage flags layered on top of backend first-run truth.
- Secondary: SQL migration snippets exist, but runtime schema authority is still primarily code-driven startup logic.

## Freeze Notes

- Refresh on: schema changes, path helper changes, config-key additions/removals, onboarding/first-run logic changes, or state-file relocations.
- Fastest invalidators: changing canonical config load rules, moving repo-local state into AppData, changing bus-mode resolution, or replacing startup migration logic.
- Check alongside: `01_SYSTEM_MAP.md` for high-level authority location and `04_SECURITY_TRUST_AND_OPERATIONS.md` for session/token and write-gate implications.

