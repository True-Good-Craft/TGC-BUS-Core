# 03_DATA_CONFIG_AND_STATE_MODEL

- Document purpose: Authority map for persistent, mutable, generated, and runtime state in BUS Core, with an emphasis on one durable authority per class of state.
- Primary authority basis: `core/appdata/paths.py`, `core/appdb/engine.py`, `core/appdb/models.py`, `core/appdb/models_recipes.py`, `core/config/manager.py`, `core/api/routes/system_state.py`, `core/api/http.py`.
- Best use: Determine where state lives, which file or component owns it, and whether authority is canonical, split, or repo-local.
- Refresh triggers: DB schema changes, path-helper changes, config-key changes, onboarding/first-run logic changes, state file relocations.
- Highest-risk drift areas: Repo-local mutable state, mixed session state, ORM-vs-startup schema differences, and localStorage layered over backend first-run truth.
- Key dependent files / modules: `core/appdata/paths.py`, `core/appdb/engine.py`, `core/appdb/models.py`, `core/appdb/models_recipes.py`, `core/config/manager.py`, `core/plugins/loader.py`, `core/api/routes/system_state.py`.

## State Authority Matrix

Stability in this phase depends on one durable authority per class of state. Durable business and operator state should live in local Core-owned storage, with AppData-backed files and the SQLite database as the primary authorities. Repo-local mutable state is still present in places, but where it exists it should be treated as drift or technical debt rather than the preferred long-term shape.

| State concern | Backing | Status | Authority | Notes |
| --- | --- | --- | --- | --- |
| Inventory, vendors/contacts, ledger, finance, recipes, manufacturing | DB-backed | Canonical | SQLite schema in `core/appdb/models.py` and `core/appdb/models_recipes.py` | Main durable business state. |
| DB path selection | Config/env-derived | Canonical | `core/appdata/paths.py::resolve_db_path()` | Uses `BUS_DB` override or bus mode. |
| Bus mode (`demo` / `prod`) | File/env-backed | Canonical | `core/appdata/paths.py::resolve_bus_mode()` | Priority: `bus_mode.json`, env var, flag file, default. |
| App runtime config | File-backed | Canonical | `%LOCALAPPDATA%\BUSCore\config.json` via `core/config/manager.py` | Single durable app-runtime authority for launcher, UI, backup, updates, write gate, and persisted policy fields. |
| Legacy app-local config fallback | File-backed | Legacy | `%LOCALAPPDATA%\BUSCore\app\config.json` via compatibility reads in `core/config/manager.py` | Read-only fallback for recognized old keys (`writes_enabled`, `role`, `plan_only`) when canonical values are absent. |
| Reader roots / Drive include settings | File-backed | Canonical | `%LOCALAPPDATA%\BUSCore\settings_reader.json` via `core/settings/reader_state.py` | Governs local FS and Drive provider behavior. |
| Plugin enabled flags | Repo-local file-backed | Drifted | `data/settings_plugins.json` via `core/plugins/loader.py` | Live mutable state outside AppData; treat as drift/technical debt relative to the local durable authority model. |
| Background index freshness | Repo-local file-backed | Drifted | `data/index_state.json` via `core/api/http.py` | Live mutable state outside AppData; also drift relative to the local durable authority model. |
| First-run / demo readiness | Derived runtime state | Canonical | `GET /app/system/state` from DB counts + bus mode | UI adds secondary local flags on top. |
| Onboarding complete / EULA accepted / imperial mode | localStorage/UI state | Secondary | `core/ui/app.js` | UI-facing state only; not the source of business truth. |
| Session/auth state | Cookie + DB-backed auth sessions plus legacy runtime token | Claimed/unclaimed gate and management API implemented | `core.api.http`, `core/api/routes/auth.py`, `core/api/routes/users.py`, `core/auth/*`, `auth_sessions`, `AppState.tokens`, `session_token.txt`, `tgc.security.require_token_ctx` | Zero users preserves legacy local `bus_session` behavior. One or more users makes DB-backed `bus_auth_session` the authority for protected routes. Session management can list/revoke auth sessions without exposing tokens or hashes. `tgc.security.require_token_ctx` remains a compatibility wrapper over `core.api.http`. |
| User accounts and identity state | DB-backed | Implemented as claimed-mode identity and management authority | `core/appdb/models_auth.py`, `core/auth/*` helpers, `core/api/routes/auth.py`, `core/api/routes/users.py`, and Security UI modules | Canonical state includes users, roles, permissions, sessions, recovery-code hashes, and audit events. `session_guard` uses auth user count to choose unclaimed vs claimed mode. User management can create/update/enable/disable users, assign roles, reset passwords, revoke sessions, and list audit events. Owner setup/user creation/password reset enforce a modest minimum password length. UI `localStorage` must not become auth, role, permission, recovery, or session authority. |
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
| `auth_users` / user table | Implemented claimed-mode management authority | DB-backed user authority; zero users means unclaimed mode, one or more users means claimed mode. No users are created automatically. User management never returns password hashes, and password inputs must pass the central minimum-length policy before hashing. |
| `auth_roles` / user-role tables | Implemented permission authority | Role and permission authority for route-local checks. At least one enabled owner must always remain once claimed; role changes cannot strip the last enabled owner. |
| `auth_sessions` | Implemented claimed-mode gate and management authority | DB-backed session rows for `bus_auth_session`; `/session/token` remains unclaimed compatibility and returns `login_required` in claimed mode. Session management can list/revoke rows without returning raw token/hash material. |
| `auth_recovery_codes` | Implemented for owner setup | Owner setup stores recovery-code hashes only and returns plaintext recovery codes once. Recovery-code reset/use route is not implemented yet. |
| `auth_audit_events` | Implemented for auth and user-management routes | Auth/user-management audit trail for owner setup, login success/failure, logout, user create/update/disable/enable/password reset/role change, and session revoke. Audit listing redacts secret-like detail keys. |

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

This AppData tree is the intended durable local ownership boundary for Core-managed state on Windows. When state belongs to Core and must persist for operators, AppData-backed storage is the canonical target unless an explicit exception is documented and justified in code.

| Path | Status | Purpose |
| --- | --- | --- |
| `%LOCALAPPDATA%\BUSCore\config.json` | Canonical | Main app-runtime config for UI, launcher, updates, write gate, and persisted policy fields. |
| `%LOCALAPPDATA%\BUSCore\app\config.json` | Legacy | Non-authoritative compatibility input for recognized pre-reconciliation keys only. |
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

These files exist today, but they are not ideal durable authorities. They are best understood as repo-local drift that increases the risk of portability, update, and operator-trust problems.

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
| `%LOCALAPPDATA%\BUSCore\config.json` | Canonical | `launcher.*`, `ui.theme`, `backup.default_directory`, `dev.writes_enabled`, `updates.*`, `policy.role`, `policy.plan_only` | `core/config/manager.py` |
| `%LOCALAPPDATA%\BUSCore\app\config.json` | Legacy compatibility input | Read-only fallback for `writes_enabled`, `role`, `plan_only` only when canonical values are absent | `core/config/manager.py` compatibility read path |
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

## DB-backed auth state and route surface

This section records the DB-backed auth model as of Phase 3. The route surface adds owner setup, login, logout, auth state, current-user lookup, session rows, recovery-code hashes, and auth audit events. The global gate now cuts over by mode: zero users preserves legacy local `bus_session`; one or more users requires valid `bus_auth_session` for protected routes. It does not add UI, route-local permission enforcement for existing `/app/*` routes, or user-management routes.

| State | Status | Intended authority | Required invariant |
| --- | --- | --- | --- |
| Users | Implemented schema/helper skeleton | DB-backed auth table in `core/appdb/models_auth.py`; helpers in `core/auth/store.py` | Zero users means unclaimed mode; one or more users means claimed mode. No hidden or default usable admin may exist. |
| Roles and permissions | Implemented schema skeleton | DB-backed role/permission tables in `core/appdb/models_auth.py`; constants in `core/auth/permissions.py` | Claimed mode must always retain at least one enabled owner. |
| Sessions | Implemented claimed-mode gate authority | DB-backed session table plus token generation/hash helpers in `core/auth/sessions.py`; cookie name `bus_auth_session` | Claimed protected routes require a valid, unexpired, unrevoked auth session. Legacy `bus_session` remains valid only in unclaimed mode. |
| Recovery codes | Implemented for owner setup | DB-backed recovery-code hash table | Recovery codes are shown once by owner setup and stored only as hashes. Recovery-code reset/use route comes later. |
| Audit events | Implemented for auth routes | DB-backed audit event table plus `core/auth/audit.py` helper | Owner setup, login success/failure, and logout write auth audit events. Broader sensitive-operation audit integration comes later. |

UI `localStorage` may support display preferences or non-authoritative setup hints, but it must not become canonical user, role, session, recovery-code, permission, or audit authority.

## Objective state risks

- Canonical: durable app-runtime config authority is `%LOCALAPPDATA%\BUSCore\config.json`; `%LOCALAPPDATA%\BUSCore\app\config.json` remains legacy compatibility input only.
- Drifted: some live mutable state (`data/index_state.json`, `data/settings_plugins.json`) lives in repo `data/`, not AppData, which weakens the one-authority-per-state-class model.
- Narrowed drift: validator authority is canonical in `core.api.http`, but session/auth state still spans cookie, `AppState.tokens`, global `SESSION_TOKEN`, and a token file.
- Drifted: `vendors.name` is declared unique in ORM metadata, but startup migration logic drops the unique-name index and recreates a non-unique one.
- Secondary: onboarding suppression and EULA acceptance are localStorage flags layered on top of backend first-run truth.
- Secondary: SQL migration snippets exist, but runtime schema authority is still primarily code-driven startup logic.

## Freeze Notes

- Refresh on: schema changes, path helper changes, config-key additions/removals, onboarding/first-run logic changes, or state-file relocations.
- Fastest invalidators: changing canonical config load rules, moving repo-local state into AppData, changing bus-mode resolution, or replacing startup migration logic.
- Check alongside: `01_SYSTEM_MAP.md` for high-level authority location and `04_SECURITY_TRUST_AND_OPERATIONS.md` for session/token and write-gate implications.
