# 04_SECURITY_TRUST_AND_OPERATIONS

- Document purpose: Fast trust, auth, enforcement, sensitive-operation, and audit reference for BUS Core, treating trust as a product requirement as well as a security concern.
- Primary authority basis: `core/api/http.py`, `core/api/security.py`, `tgc/security.py`, `tgc/tokens.py`, `core/policy/*`, `core/secrets/manager.py`, `core/utils/export.py`, `core/services/capabilities/registry.py`, `core/runtime/manifest_trust.py`, `core/runtime/manifest_keys.py`, `pyproject.toml`, `SECURITY.md`, `docs/security/remediation_audit_log.md`.
- Best use: Determine who can do what, where enforcement happens, and which trust splits remain live in code.
- Refresh triggers: Session/auth changes, route guard changes, write-policy changes, secrets handling changes, backup/import flow changes, provider integration changes, manifest-signing changes.
- Highest-risk drift areas: Split token authority, inconsistent route-local guard patterns, optional owner-policy enforcement, release-artifact validation absence, and license/manifest mismatch.
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

| Concern | Status | Enforced by | Scope | Notes |
| --- | --- | --- | --- | --- |
| Session gate for non-public routes | Canonical | `session_guard` middleware | Broad route surface | Main route-entry auth barrier. |
| Route-local token checks | Canonical with compatibility wrapper | `core.api.http.require_token_ctx` plus `tgc.security.require_token_ctx` | Selected modules/routes | `core.api.http` owns validation; `tgc.security.require_token_ctx` is a compatibility wrapper only. |
| Write gate | Canonical | `require_write_access()` / `require_writes()` | Writes and selected admin routes | Controlled by app state plus env/config. |
| Owner/tester commit gate | Canonical | `require_owner_commit()` | Selected write operations | Strict role/plan enforcement activates only when `BUS_POLICY_ENFORCE=1`. |
| Dev-only gate | Canonical | `session_guard` path check plus `require_dev()` | `/dev/*` routes and detailed health | `/dev/*` stays hidden as 404 when disabled; when enabled, session auth still applies. |
| Capability manifest validation | Canonical | HMAC signature in `core/services/capabilities/registry.py` | `/capabilities`, `/nodes.manifest.sync` | Local manifest trust only. |
| Update manifest validation | Canonical | `core/services/update.py` | `/app/update/check` | URL/content-type/size/SemVer, channel selection, supported manifest-shape, optional signed-manifest unwrapping, and optional declared metadata shape validation. |
| Manifest authenticity primitives | Bridge groundwork | `core/runtime/manifest_trust.py`, `core/runtime/manifest_keys.py`, `scripts/sign_manifest.py`, release mirror workflow | Manifest metadata | Ed25519 verification and embedded signatures exist; production public key `bus-core-prod-ed25519-2026-04-25` is pinned, but client enforcement remains off and unsigned compatibility remains available. |
| Release artifact hash verification | Bridge groundwork | `core/services/update_artifact.py`, `core/runtime/update_cache.py` | Cached ZIP under `updates\downloads\` | Internal helper requires declared `sha256`, enforces declared `size_bytes` when present, verifies the downloaded ZIP against signed manifest metadata, and records `hash_verified` only. |
| Safe ZIP extraction | Bridge groundwork | `core/services/update_extract.py`, `core/runtime/update_cache.py` | Local update cache under `updates\versions\<version>\` | Internal helper stages extraction through a temp dir, rejects zip-slip / absolute / escaping / suspicious entries, requires exactly one `.exe`, and records `extracted` only. |
| Executable trust verification | Drifted | No Authenticode/publisher verification path found | Extracted EXE | Extracted artifacts are not yet publisher-verified or runnable-trusted; `verified_ready` and handoff remain future work. |

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
| Session bootstrap route | Canonical | `GET /session/token` in `core/api/http.py` | Returns `{ token }` and sets cookie. |
| AppState token manager | Canonical | `tgc/tokens.py`, `tgc/state.py` | `TokenManager.current()` is the runtime token source that the canonical validator compares against. |
| Validator authority | Canonical | `core.api.http::{session_guard, validate_session_token, require_token_ctx}` | Middleware, protected-router deps, and direct auth deps all flow through this path. |
| Route-local token dependency compatibility shim | Compatibility wrapper | `tgc.security.require_token_ctx` | Delegates to `core.api.http.require_token_ctx()` and carries no independent validation logic. |
| Global session token | Secondary | `core/api/http.py::SESSION_TOKEN` | Runtime mirror persisted to `session_token.txt`; fallback/bootstrap state only, not the normal validator authority. |
| Token file | Secondary | `%LOCALAPPDATA%\BUSCore\app\data\session_token.txt` | Written by `build_app()` / bootstrap path. |
| Legacy alternate token surfaces | Removed | `app.py`, `tgc/http.py` | Conflicting parallel `/session/token` contracts were removed from the repo. |

- Intended session contract: `GET /session/token` is the only bootstrap surface, it sets the `bus_session` cookie, and non-public routes remain cookie-authenticated even when `BUS_DEV=1`.
- Intended dev-route contract: `/dev/*` returns `404` whenever `BUS_DEV!=1`; when `BUS_DEV=1`, those routes are available but still require a valid session cookie.

This is the core trust boundary as implemented today: local runtime first, bounded optional network calls, and a single supported bootstrap route. Remaining auth ambiguity must stay documented plainly because it affects operator trust even when the app still functions.


### Route-level enforcement inconsistencies

| Route family | Status | Route-local guard pattern |
| --- | --- | --- |
| Items, vendors/contacts, recipes, system state, canonical manufacture | Canonical | Explicit token deps; writes also use write gate and owner commit. |
| `/app/db/*`, `/settings/*`, `/plans*`, `/plugins*`, `/probe`, `/capabilities`, `/logs`, local path ops | Canonical | Protected router applies token dependency; many writes also require write gate. |
| `ledger_api` canonical mutations and reads (`/app/purchase`, `/app/stock/in`, `/app/stock/out`, `/app/ledger/history`, etc.) | Drifted | Route-local token/write deps are absent in module code; protection relies on global middleware. |
| `finance_api` mutations and reads | Drifted | Route-local token/write deps are absent in module code; protection relies on global middleware. |
| `config GET`, `update GET`, `logs_api GET`, transaction stubs | Drifted | Route-local token deps are absent; global middleware still protects non-public paths. |

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
| Ledger mutations | Drifted | `/app/purchase`, `/app/stock/in`, `/app/stock/out`, `/app/consume`, `/app/adjust` | No route-local auth/write deps in module | Still behind global middleware; route-local pattern differs from other write domains. |
| Finance mutations | Drifted | `/app/finance/expense`, `/app/finance/refund` | No route-local auth/write deps in module | Same mismatch as ledger routes. |
| Config and policy writes | Canonical | `/app/config`, `/policy`, `/settings/google`, `/settings/reader`, `/plans*`, `/plugins/{pid}/enable` | Usually protected router + `require_writes` | Owner commit is not universal across these admin writes. |
| Open local path / restart server | Canonical | `/open/local`, `/server/restart` | Protected router + `require_writes` | Performs OS-visible side effects. |

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
- Drifted: `ledger_api` and `finance_api` rely on global middleware rather than the explicit route-local auth/write pattern used by other write domains.
- Drifted: CORS is configured with `allow_origins=["*"]` and `allow_methods=["*"]` on the local server.
- Drifted: `core/services/capabilities/registry.py` injects a `license` block with `PolyForm-Noncommercial-1.0.0`, which conflicts with the repo-wide AGPL labeling elsewhere.
- Canonical: legacy alternate `/session/token` surfaces (`app.py`, `tgc/http.py`) were removed; `core/api/http.py` is the only supported bootstrap route.
- Canonical: backup import/export paths enforce password-based decryption, exports-root path confinement, maintenance mode, and journal archiving during restore.
- Canonical: update manifest fetch blocks localhost and literal private/loopback/link-local/unspecified IP hosts, rejects redirects, caps response size, validates allowed channel selection, and validates supported manifest shapes.
- Canonical bridge groundwork: manifest authenticity support exists with Ed25519 canonical JSON verification, envelope support, backward-compatible embedded top-level signatures, and a pinned production public key. Release publication signs manifests before upload, but Core does not yet require signed manifests.
- Canonical bridge groundwork: optional artifact metadata is validated for shape and retained internally as declared manifest-provided values by `ManifestRelease`.
- Narrowed drift: internal helpers now hash-verify downloaded release ZIPs against signed manifest metadata and safely extract them into the local update cache, but `/app/update/check` still only surfaces `download_url` and executable trust is incomplete until EXE Authenticode/publisher verification exists.

The current security posture is therefore trustworthy in some important local-first ways, but not yet fully consolidated. The right documentation posture is honesty about remaining auth, config, and release-validation drift rather than overstating cleanliness.

## Limited-confidence inference

- The repository appears to be mid-consolidation between older and newer auth/write-governance approaches, but the exact intended end-state is not determined from repository evidence.

## Freeze Notes

- Refresh on: token/session flow changes, route-guard changes, provider integration changes, restore/export changes, manifest-signing changes, or policy enforcement changes.
- Fastest invalidators: consolidating token authority, moving ledger/finance to explicit route-local guards, changing secrets storage, or altering update validation behavior.
- Check alongside: `02_API_AND_UI_CONTRACT_MAP.md` for route ownership and `05_RELEASE_UPDATE_AND_DEPLOYMENT_FLOW.md` for update-path release validation details.
