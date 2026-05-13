# 04_SECURITY_TRUST_AND_OPERATIONS

- Document purpose: Fast trust, auth, enforcement, sensitive-operation, and audit reference for BUS Core, treating trust as a product requirement as well as a security concern.
- Primary authority basis: `core/api/http.py`, `core/api/security.py`, `tgc/security.py`, `tgc/tokens.py`, `core/policy/*`, `core/secrets/manager.py`, `core/utils/export.py`, `core/services/capabilities/registry.py`, `core/runtime/manifest_trust.py`, `core/runtime/manifest_keys.py`, `pyproject.toml`, `SECURITY.md`, `docs/security/remediation_audit_log.md`.
- Best use: Determine who can do what, where enforcement happens, and which trust splits remain live in code.
- Refresh triggers: Session/auth changes, route guard changes, write-policy changes, secrets handling changes, backup/import flow changes, provider integration changes, manifest-signing changes.
- Highest-risk drift areas: Split token authority, future route-local guard drift, Docker/LAN exposure drift, optional owner-policy enforcement, remaining release/Docker artifact governance gaps, and license/manifest mismatch.
- Key dependent files / modules: `core/api/http.py`, `core/api/security.py`, `tgc/security.py`, `tgc/state.py`, `tgc/tokens.py`, `core/policy/guard.py`, `core/secrets/manager.py`, `core/utils/export.py`, `core/services/capabilities/registry.py`, `core/runtime/manifest_trust.py`, `core/runtime/manifest_keys.py`.

## Trust and Enforcement Matrix

Core trust is not only about preventing compromise. It is also about preserving operator certainty: no surprise lock-in, no hidden cloud dependency, no ambiguous auth boundary, and no silent shift in who owns the canonical business logic or durable state.

## Static-analysis governance overlay

- Bandit is governed as a trust-preservation signal, not a scanner-green objective; behavior-preserving true fixes are preferred over broad rewrites.
- Suppressions must be exact-line and evidence-justified. If a suppression is removed and the same finding reproduces, the suppression may be restored only on the exact reported line.
- Security remediation that changes repo policy/process must be reflected in `CHANGELOG.md` and `SOT.md` in addition to security docs, to prevent governance drift.
- RID/path-token resolution (`core/reader/ids.py`) is treated as part of the local-file trust boundary and now uses compatibility-aware hardening (new-write `local:v2:<sig32>:<payload>`, old-read legacy support).
- B324 in `core/reader/ids.py` is resolved via real hardening (stronger active RID signature construction and strict fail-closed validation), without suppression-based handling.
- Commit-path enforcement is tightened so present RID fields are authoritative for resolution and invalid RID values do not silently downgrade to raw-path fallback.
- Sandbox transform execution is now a fixed-command boundary: subprocess argv is limited to BUS Core-owned runner arguments, while `plugin_id`, `fn`, and transform payload move through stdin JSON only and malformed stdin is rejected in the runner.
- Restore/import preview metadata in the admin UI is now rendered with DOM text nodes rather than dynamic `innerHTML`, so path/schema/count values are treated as text and not markup.
- Local open/validate, import/export preview/commit, and plugin UI asset paths now resolve through explicit allowed roots before filesystem access or OS-open behavior.

## Swallowed Exception Policy

- Empty `except: pass` and `except Exception: pass` handlers are not allowed by default.
- Swallowed exceptions are allowed only for best-effort cleanup, optional platform/UI behavior, cache invalidation, telemetry-free journal side effects, config/tracker cleanup, or migration/compatibility fallbacks.
- Each swallowed exception must use a narrow exception type where practical, and must include safe type-only logging or an explanatory comment that states why failure is intentionally non-fatal.
- API responses must not return raw exception details from swallowed or remediated exception paths.
- Logs must not include secrets, tokens, raw DB URLs, passwords, or full sensitive paths from these handlers.
- Security, auth, write, restore, and update failures must not be silently ignored unless the failure is explicitly non-critical cleanup or an already-missing resource condition.

| Concern | Status | Enforced by | Scope | Notes |
| --- | --- | --- | --- | --- |
| Session gate for non-public routes | Canonical claimed/unclaimed gate | `session_guard` middleware | Broad route surface | Zero users preserves legacy local `bus_session`; one or more users requires valid DB-backed `bus_auth_session` for protected routes. |
| Route-local token checks | Canonical with compatibility wrapper | `core.api.http.require_token_ctx` plus `tgc.security.require_token_ctx` | Sensitive reads/writes in routed modules | `core.api.http` owns validation; in claimed mode it accepts the auth context attached by `session_guard`. `tgc.security.require_token_ctx` is a compatibility wrapper only. |
| Route-local permission checks | Implemented for covered families | `core.auth.dependencies.require_permission()` | Covered protected API routes | In unclaimed mode permission deps return a synthetic local owner context so legacy local workflows continue. In claimed mode missing/invalid sessions return `401`, insufficient permission returns `403`, and owner role resolves to all known permissions. User/session/audit management routes use `users.read`, `users.manage`, `sessions.manage`, and `audit.read`. |
| Write gate | Canonical | `require_write_access()` / `require_writes()` | Writes and selected admin routes | Controlled by app state plus env/config. |
| Owner/tester commit gate | Canonical | `require_owner_commit()` | Selected write operations | Strict role/plan enforcement activates only when `BUS_POLICY_ENFORCE=1`. |
| Dev-only gate | Canonical | `session_guard` path check plus `require_dev()` | `/dev/*` routes and detailed health | `/dev/*` stays hidden as 404 when disabled; when enabled, session auth still applies. |
| Capability manifest validation | Canonical | HMAC signature in `core/services/capabilities/registry.py` | `/capabilities`, `/nodes.manifest.sync` | Local manifest trust only. |
| Security tooling evidence | Canonical | `.github/workflows/security-audit.yml`, `SECURITY.md` | CI security checks | Bandit runs on Python source with Medium/High findings blocking CI; `pip-audit` runs against `requirements.txt` in advisory mode until dependencies have a fully pinned audit input. |
| Docker default network exposure | Canonical | `docker-compose.yml` | Host-published container port | Default Compose binding is `127.0.0.1:8765:8765`. Container-internal `0.0.0.0` is retained for Docker runtime behavior, but host exposure must stay loopback-only by default. |
| Update manifest validation | Canonical | `core/services/update.py` | `/app/update/check` | URL/content-type/size/SemVer, channel selection, supported manifest-shape, optional signed-manifest unwrapping, and optional declared metadata shape validation. Read-only check preserves unsigned-manifest compatibility. |
| Manual update staging endpoint | Canonical | `core/api/routes/update.py`, `core/services/update_stage.py` | `POST /app/update/stage` | Session-authenticated and write-gated; runs trusted staging only when user clicks Update. |
| Manifest authenticity enforcement | Canonical for staging | `core/runtime/manifest_trust.py`, `core/runtime/manifest_keys.py`, `core/api/routes/update.py`, release mirror workflow | Manifest metadata used by staging | Ed25519 verification and embedded signatures exist; production public key `bus-core-prod-ed25519-2026-04-25` is pinned. `/app/update/stage` requires a trusted signed manifest; `/app/update/check` remains compatibility/read-only. |
| Claimed owner identity model | Global gate, permissions, backend management, and UI flow implemented | `core/api/http.py`, `core/api/routes/auth.py`, `core/api/routes/users.py`, `core/auth/dependencies.py`, `core/auth/management.py`, `core/appdb/models_auth.py`, `core/ui/app.js`, `core/ui/js/auth.js`, `core/ui/js/auth-ui.js`, `core/ui/js/security.js`, low-level `core/auth/*` helpers | User accounts, roles, permissions, sessions, recovery-code hashes, audit events, and frontend claim/login/security management | `/auth/state`, `/auth/setup-owner`, `/auth/login`, `/auth/logout`, `/auth/me`, `/app/users`, `/app/roles`, `/app/sessions`, and `/app/audit` exist. The SPA calls `/auth/state` before protected app mount, preserves unclaimed local mode, shows login before normal screens in claimed mode without a current session, and exposes `#/security` management controls according to current-user permissions. Backend route-local permissions remain authoritative. |
| Release artifact hash verification | Bridge groundwork | `core/services/update_artifact.py`, `core/runtime/update_cache.py` | Cached ZIP under `updates\downloads\` | Internal helper requires declared `sha256`, enforces declared `size_bytes` when present, verifies the downloaded ZIP against signed manifest metadata, and records `hash_verified` only. |
| Safe ZIP extraction | Bridge groundwork | `core/services/update_extract.py`, `core/runtime/update_cache.py` | Local update cache under `updates\versions\<version>\` | Internal helper stages extraction through a temp dir, rejects zip-slip / absolute / escaping / suspicious entries, requires exactly one `.exe`, and records `extracted` only. |
| Executable trust verification | Bridge groundwork | `core/services/update_exe_trust.py`, `core/runtime/update_cache.py` | Extracted EXE | Internal helper requires Windows Authenticode `Status == Valid`, True Good Craft signer-subject matching, and the pinned signer thumbprint `55474AA9A2D562022A6590D487045E069457F985`, then records `exe_verified` only. |
| Conservative ready promotion | Bridge groundwork | `core/services/update_promote.py`, `core/runtime/update_cache.py` | Local update cache state | Internal helper writes `verified_ready` only when `hash_verified`, `extracted`, and `exe_verified` agree on version/channel/hash/path data and the confined ZIP, version directory, and EXE still exist. |
| Verified handoff on next start | Canonical | `launcher.py` | Native launcher startup | After DB ownership lock, launcher may hand off to `verified_ready` based on launch policy (`ask`, `always_newest`, `current_only`) without overwriting the running EXE. |

## Trust model

### Product trust requirements

- Core must remain locally operable and fully useful without accounts, Pro, or forced cloud dependency.
- External integrations and update checks must remain additive and bounded, not hidden prerequisites for normal operation.
- Auth and write authority should be explicit enough that operators are not surprised about what is protected by middleware only versus route-local guards.
- Current docs should describe live drift plainly rather than implying a cleaner runtime than the code actually provides.

### Evidence-backed

| Topic | Status | Repository evidence |
| --- | --- | --- |
| Local-first runtime | Canonical | Local DB, AppData state, localhost default binding, no telemetry path in main runtime. |
| External dependencies | Canonical | Google OAuth/Drive APIs and hosted update manifest fetches are the main external calls. |
| Policy engine | Canonical | `CoreAlpha` loads deny-by-default rules from `config/policy.json`. |
| Writes default model | Canonical | Writes are enabled unless env/config disables them. |
| Capability trust | Canonical | Capability manifest is signed locally and verified on sync. |

### Limited-confidence inference

- The codebase intent is stricter than the current route-by-route enforcement consistency, but the repository does not contain a single definitive enforcement matrix beyond the code itself.

## Auth, token, and session handling

### Authorities

| Authority | Status | Location | Notes |
| --- | --- | --- | --- |
| Session bootstrap route | Canonical unclaimed compatibility | `GET /session/token` in `core/api/http.py` | Returns `{ token }` and sets `bus_session` only while zero auth users exist; returns `login_required` in claimed mode. |
| AppState token manager | Canonical | `tgc/tokens.py`, `tgc/state.py` | `TokenManager.current()` is the runtime token source that the canonical validator compares against. |
| Validator authority | Canonical | `core.api.http::{session_guard, validate_session_token, require_token_ctx}` | Middleware, protected-router deps, and direct auth deps all flow through this path. Claimed mode uses DB-backed `bus_auth_session` context attached by middleware. |
| Route-local token dependency compatibility shim | Compatibility wrapper | `tgc.security.require_token_ctx` | Delegates to `core.api.http.require_token_ctx()` and carries no independent validation logic. |
| Global session token | Secondary | `core/api/http.py::SESSION_TOKEN` | Runtime mirror persisted to `session_token.txt`; fallback/bootstrap state only, not the normal validator authority. |
| Token file | Secondary | `%LOCALAPPDATA%\BUSCore\app\data\session_token.txt` | Written by `build_app()` / bootstrap path. |
| Legacy alternate token surfaces | Removed | `app.py`, `tgc/http.py` | Conflicting parallel `/session/token` contracts were removed from the repo. |

- Intended session contract: `GET /session/token` remains the legacy bootstrap surface only in unclaimed mode. Once claimed, `/session/token` returns `login_required`, and non-public routes require a valid DB-backed `bus_auth_session` even when `BUS_DEV=1`.
- Intended dev-route contract: `/dev/*` returns `404` whenever `BUS_DEV!=1`; when `BUS_DEV=1`, those routes are available but still require a valid mode-appropriate session cookie.
- Docker/host exposure contract: BUS Core is local-first software. Docker Compose defaults to loopback-only publishing, and the default session model is for local loopback use, not multi-user LAN/public hosting. Non-loopback deployment requires explicit operator action, a separate advanced/unsafe override, and stronger network/access controls.

This is the core trust boundary as implemented today: local runtime first, bounded optional network calls, DB-backed claimed-mode identity, and legacy bootstrap compatibility only while unclaimed.

### Claimed/unclaimed account model

Phase 3 implemented the global claimed-mode gate. Phase 4 implemented route-local permission checks for covered protected route families. Phase 5 implements user, role, session, and audit management routes. Phase 6 adds the frontend claim/login/logout/current-user/Security management flow on top of those APIs without changing backend auth authority. Phase 7 hardening confirms bootstrap/public surfaces, session/cookie safety, permission boundaries, owner invariants, UI storage posture, and guard-script coverage. Release-blocker hardening adds owner recovery, recovery-code regeneration, DB-backed recovery rate limiting, explicit session idle/max-age enforcement, frontend permission resync, and duplicate OpenAPI operation-ID cleanup.

| Mode | Trigger | Required behavior |
| --- | --- | --- |
| Unclaimed mode | Canonical auth user table has zero users | BUS Core remains usable in current local-first/simple mode; legacy `/session/token` / `bus_session` compatibility remains valid for protected routes; first-run/account setup is not mandatory; no default usable admin exists. |
| Claimed mode | Canonical auth user table has one or more real users | Protected routes require valid DB-backed `bus_auth_session`; legacy `bus_session` is ignored as app-route authority; auth session context is attached to `request.state`; covered route families enforce route-local permissions; user/session/audit management routes require explicit management permissions; sensitive auth and user-management actions write audit events. |

Iron-grip invariants for claimed mode and follow-on user management:

- No default usable admin or owner may be created, including `admin` / `admin`, blank usernames, blank passwords, short passwords below the configured minimum, or hidden pre-created owners that can log in.
- `POST /auth/setup-owner` may succeed only while the auth user table has zero users. Once any user exists, setup-owner must reject permanently unless the DB is deliberately reset or restored.
- `/session/token` remains unclaimed runtime-token compatibility. It returns `login_required` in claimed mode and must not grant app access, mint identity, or bypass login.
- Claimed `bus_auth_session` rows are rejected when revoked, past `expires_at`, older than 30 days from creation, or idle for more than 12 hours. Valid sessions touch `last_seen_at` only after the configured touch interval; re-authentication creates a fresh session rather than using refresh tokens.
- User/account state must be DB-backed canonical state: users, roles, sessions, recovery-code hashes, and audit events. UI `localStorage` is convenience only and cannot become auth authority.
- The SPA may display claim/login/logout/current-user and hide navigation or Security controls based on current-user permissions, but that hiding is operator convenience only. It must not store passwords, recovery codes, session tokens, or permission authority in `localStorage`. Security UI management actions that can affect permissions or sessions must re-fetch auth state so current-user navigation/actions update without reload; `401` returns show login and `403` returns show a permission state.
- Once claimed, BUS Core prevents disabling the last enabled owner, deleting the last enabled owner when a delete route exists, or removing owner role/authority from the last enabled owner. Phase 5 centralizes this in `core.auth.management.assert_not_last_enabled_owner()`.
- Backend permission checks are the security boundary. Covered protected routes use explicit dependencies such as `require_permission("inventory.read")` and `require_permission("inventory.write")`; UI hiding/showing buttons is convenience only.

Phase 4 route-local permission coverage includes inventory/items, ledger/stock, recipes, manufacturing, vendors/contacts, finance, logs, config/update/system, backup/import/export, settings/google, settings/reader, policy, plans, plugins, local path/open, restart, capabilities, and transparency routes. Reader, organizer, provider catalog/index, and drive scan routes remain deferred pending a distinct provider/catalog permission vocabulary.
- Phase 5 route-local permission coverage adds `/app/users`, `/app/roles`, `/app/sessions`, and `/app/audit`. User/session mutations retain write gates; session and audit payloads must not expose raw session tokens, session hashes, password hashes, recovery codes, or secret values.
- Phase 6 UI coverage adds `/auth/state` boot gating, owner setup/recovery-code display, login/logout, current-user chrome, and `#/security` user/session/audit management views. Unclaimed mode must not force setup, and claimed mode without a session must show login before normal app screens or protected `/app/*` calls.
- Phase 7 hardening keeps the UI contract audit active for forbidden quoted legacy endpoints, legacy endpoint tokens, finance legacy fields, and canonical endpoint containment. Narrow allowlists cover only known compatibility code: the imperial-unit wrapper in `core/ui/js/token.js` and the recipe unit label in `core/ui/js/cards/recipes.js`.
- Recovery codes must be generated as one-time codes, shown once, stored only as hashes, single-use, and audited when used. `/auth/recover` returns generic failure for wrong username, wrong/used code, and lockout states; successful recovery burns the code, resets the password under current password policy, revokes active sessions, requires login afterward, and writes `auth.recovery_used` without secret detail. Failed recovery attempts are DB-backed and limited to 5 failures per normalized username/client window with a 15-minute lockout. Printed recovery codes do not expire after 15 minutes; they remain valid until used or regenerated.
- Recovery-code regeneration requires claimed `users.manage` authority, invalidates unused old codes, returns new plaintext codes once, stores only hashes, and writes `auth.recovery_codes_regenerated` without plaintext code detail.
- OpenAPI operation IDs must be unique; dual-mounted routes use explicit operation IDs when function names would collide.

Sensitive claimed-mode audit events now include owner setup, login success/failure, logout, user created/updated/disabled/enabled, password reset, roles changed, and session revoked. Broader runtime audit events for backup export/restore, config changes, finance writes, inventory writes, manufacturing runs, and system restart/start-fresh remain future expansion.


### Route-level enforcement inconsistencies

| Route family | Status | Route-local guard pattern |
| --- | --- | --- |
| Items, vendors/contacts, recipes, system state, canonical manufacture | Canonical | Explicit token deps; writes also use write gate and owner commit. |
| Ledger, finance, config, update check/stage, and app-log routes | Canonical | Explicit token deps on sensitive reads; explicit token + `require_writes` on sensitive mutations. Owner commit was not added where the existing domain policy did not already require it. |
| `/app/db/*`, `/settings/*`, `/plans*`, `/plugins*`, `/probe`, `/capabilities`, `/logs`, local path ops | Canonical | Protected router applies token dependency; many writes also require write gate. |
| Transaction stubs and older direct routes not yet consolidated into domain routers | Drifted | Global middleware still protects non-public paths, but route-local dependency coverage is not yet uniform across the whole app. |

## Sensitive write operations

| Operation | Status | Routes / files | Enforcement observed | Notes |
| --- | --- | --- | --- | --- |
| DB export | Canonical | `POST /app/db/export`, `core/utils/export.py` | Protected router + `require_writes`; password required | Produces encrypted `.db.gcm` file. |
| DB import preview | Canonical | `POST /app/db/import/preview` | Protected router + `require_writes` | File path must stay under exports dir. |
| DB import commit / restore | Canonical | `POST /app/db/import/commit`, `core/utils/export.py`, `core/backup/restore_commit.py` | Protected router + `require_writes` | Enters maintenance mode, stops indexer, swaps DB, archives journals, writes audit line. |
| Start fresh shop | Canonical | `POST /app/system/start-fresh` | Explicit token + `require_writes` | Recreates prod DB and flips bus mode to prod. |
| Item writes | Canonical | `/app/items` `POST|PUT|DELETE` | Explicit token + `require_writes` + owner commit | Delete can archive instead of hard-delete. |
| Vendor/contact writes | Canonical | `/app/vendors*`, `/app/contacts*` | Explicit token + write access + owner commit | Shared-table mutation surface. |
| Recipe writes | Canonical | `/app/recipes*` mutations | Explicit token + `require_writes` + owner commit | Also appends journal entries. |
| Manufacturing run | Canonical | `POST /app/manufacture` | Explicit token + `require_writes` + owner commit | Writes manufacturing run + journals. |
| Ledger mutations | Canonical | `/app/purchase`, `/app/stock/in`, `/app/stock/out`, `/app/consume`, `/app/adjust` | Explicit token + `require_writes` | Owner commit is not currently part of this domain policy. |
| Finance mutations | Canonical | `/app/finance/expense`, `/app/finance/refund` | Explicit token + `require_writes` | Owner commit is not currently part of this domain policy. |
| Config and policy writes | Canonical | `/app/config`, `/policy`, `/settings/google`, `/settings/reader`, `/plans*`, `/plugins/{pid}/enable` | `/app/config` has explicit token + `require_writes`; other admin routes are protected router + write gate where applicable | Owner commit is not universal across these admin writes. |
| Open local path / restart server | Canonical | `/open/local`, `/server/restart` | Protected router + `require_writes` | Performs OS-visible side effects. |

### Path and subprocess boundaries

- Sandbox transform subprocess execution is constrained to a fixed BUS Core-owned command (`sys.executable -m core.runtime.sandbox_runner`); dynamic transform fields are not allowed in argv.
- Import preview/commit accepts only paths that resolve under `EXPORTS_DIR`; staged uploads are written under the same canonical exports root.
- Local validate/open accepts only paths that resolve under configured `local_fs` roots; resolved safe paths are the only values passed to Explorer, `os.startfile`, or `xdg-open`.
- Plugin UI asset resolution is constrained to `PLUGIN_UI_BASES/<plugin>/ui` roots and must remain in-root after normalization.

## Adapters and integrations

| Integration | Status | Files | Trust / permission implications |
| --- | --- | --- | --- |
| Google OAuth | Canonical | `/oauth/google/*`, `core/secrets/manager.py` | Stores client credentials and refresh token locally; default callback hardcodes `http://127.0.0.1:8765/oauth/google/callback`. |
| Google Drive provider | Canonical | `core/adapters/drive/provider.py` | Exchanges refresh token for access token and reads Drive metadata. |
| Local filesystem provider | Canonical | `core/adapters/fs/provider.py` | Restricts traversal to allow-listed local roots. |
| Organizer plan routes | Canonical | `core/organizer/api.py` | Generates file-operation plans only under allowed roots. |
| Plugin broker and transforms | Canonical | `core/runtime/core_alpha.py`, `core/api/http.py` | Runs provider probes and transform proposals; Windows plugin-host sandbox check exists. |
| Update manifest host | Canonical | `core/services/update.py` | Outbound fetch only; security relevance is manifest validation, not install execution. |
| Manifest signing key | Operational secret | GitHub secret `BUSCORE_MANIFEST_SIGNING_PRIVATE_KEY` | Private Ed25519 signing key must never be committed. Public key is pinned in Core and is safe to commit. |

## Logs and audit surfaces

| Surface | Status | What is recorded | Location |
| --- | --- | --- | --- |
| Request log middleware | Canonical | Path, method, elapsed ms, run id, status | Runtime log file from `LOG_FILE` / `LOGS` |
| AppState logger | Canonical | General app log via `tgc.logging_setup.py` | `buscore.log` under AppState data dir |
| Text log API | Canonical | Last 200 runtime log lines | `GET /logs` |
| Event log API | Canonical | Item movement events, not text logs | `GET /app/logs` |
| Inventory/manufacturing/recipe journals | Canonical | Domain journal lines | `%LOCALAPPDATA%\BUSCore\app\data\journals\*.jsonl` |
| Restore/import audit | Canonical | Import source path and preview counts | `plugin_audit.jsonl` |
| Transparency report | Canonical | Policy mode, plugin/capability summary, manifest/journal paths | `GET /transparency.report` |

## Security-relevant config and secrets

| Item | Status | Location | Purpose |
| --- | --- | --- | --- |
| `ALLOW_WRITES`, `READ_ONLY` | Canonical | Environment | Global write-enable defaults. |
| `BUS_POLICY_ENFORCE` | Canonical | Environment | Enables strict owner/plan enforcement. |
| `BUS_DEV` | Canonical | Environment | Enables dev routes and unsanitized error detail behavior. |
| `updates.manifest_url` | Canonical | `%LOCALAPPDATA%\BUSCore\config.json` | Outbound update-manifest location. |
| `writes_enabled` | Canonical | `%LOCALAPPDATA%\BUSCore\config.json` `dev.writes_enabled`, with app state as runtime mirror and `%LOCALAPPDATA%\BUSCore\app\config.json` as legacy fallback only | Durable write gate now lives under the canonical root config file. |
| `role`, `plan_only` | Canonical | `%LOCALAPPDATA%\BUSCore\config.json` `policy.*`, with `%LOCALAPPDATA%\BUSCore\app\config.json` as legacy fallback only | Commit-policy inputs, only strictly enforced when `BUS_POLICY_ENFORCE=1`. |
| Google client ID / secret / refresh token | Canonical | OS keyring or `%LOCALAPPDATA%\BUSCore\secrets\secrets.json.enc` | OAuth and Drive access. |
| Capability HMAC key | Canonical | `%LOCALAPPDATA%\BUSCore\state\capabilities_hmac.key` | Signs capability manifest. |
| Manifest signing private key | External release secret | GitHub secret `BUSCORE_MANIFEST_SIGNING_PRIVATE_KEY` | Used by release mirror only to sign public manifest metadata; private material must stay outside the repo. |
| Manifest signing public key | Canonical public key | `core/runtime/manifest_keys.py` | Ed25519 production public key pinned as `bus-core-prod-ed25519-2026-04-25`; safe to commit. |

## Evidence-backed findings

- Narrowed drift: `core.api.http` now owns validator authority, but runtime token state still spans `AppState.tokens`, global `SESSION_TOKEN`, and a token file.
- Canonical: scoped ledger, finance, config, update-check, and app-log routes now carry explicit route-local token dependencies, and sensitive mutations carry explicit write-gate dependencies.
- Canonical: browser CORS is restricted to explicit loopback origins (`http://127.0.0.1:8765`, `http://localhost:8765`) with explicit methods/headers; wildcard CORS is not part of the default local-first runtime.
- Canonical: `.github/workflows/security-audit.yml` provides repeatable Bandit and dependency-audit evidence. Bandit Medium/High findings block CI; dependency audit is advisory while requirements remain range-based rather than locked.
- Drifted: `core/services/capabilities/registry.py` injects a `license` block with `PolyForm-Noncommercial-1.0.0`, which conflicts with the repo-wide AGPL labeling elsewhere.
- Canonical: legacy alternate `/session/token` surfaces (`app.py`, `tgc/http.py`) were removed; `core/api/http.py` is the only supported bootstrap route.
- Canonical: `docker-compose.yml` publishes the BUS Core port to `127.0.0.1` by default so Docker mode follows the local-first loopback trust model; bare `8765:8765` publishing is reserved for explicitly documented unsafe/advanced LAN overrides.
- Canonical: backup import/export paths enforce password-based decryption, exports-root path confinement, maintenance mode, and journal archiving during restore.
- Canonical: update manifest fetch blocks localhost and literal private/loopback/link-local/unspecified IP hosts, rejects redirects, caps response size, validates allowed channel selection, and validates supported manifest shapes.
- Canonical: manifest authenticity support exists with Ed25519 canonical JSON verification, envelope support, backward-compatible embedded top-level signatures, and a pinned production public key. Release publication signs manifests before upload, and `/app/update/stage` now requires trusted signed manifests before artifact staging.
- Canonical bridge groundwork: optional artifact metadata is validated for shape and retained internally as declared manifest-provided values by `ManifestRelease`.
- Canonical: `/app/update/check` remains read/check-only with unsigned compatibility, while manual `POST /app/update/stage` requires a trusted signed manifest and performs trusted staging behind auth and write-gate controls.

The current security posture is therefore trustworthy in some important local-first ways, but not yet fully consolidated. The right documentation posture is honesty about remaining auth, config, and release-validation drift rather than overstating cleanliness.

## Limited-confidence inference

- The repository appears to be mid-consolidation between older and newer auth/write-governance approaches, but the exact intended end-state is not determined from repository evidence.

## Freeze Notes

- Refresh on: token/session flow changes, route-guard changes, provider integration changes, restore/export changes, manifest-signing changes, or policy enforcement changes.
- Fastest invalidators: consolidating token authority, adding new sensitive routes without route-local guards, publishing Docker defaults beyond loopback, reintroducing wildcard/default-open CORS, changing secrets storage, or altering update validation behavior.
- Check alongside: `02_API_AND_UI_CONTRACT_MAP.md` for route ownership and `05_RELEASE_UPDATE_AND_DEPLOYMENT_FLOW.md` for update-path release validation details.
