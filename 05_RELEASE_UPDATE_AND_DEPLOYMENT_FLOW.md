# 05_RELEASE_UPDATE_AND_DEPLOYMENT_FLOW

- Document purpose: Fast operational reference for version authority, build outputs, release flow, update-check behavior, and deployment assumptions.
- Primary authority basis: `core/version.py`, `scripts/build_core.ps1`, `BUS-Core.spec`, `Dockerfile`, `core/api/routes/update.py`, `core/services/update.py`, `.github/workflows/publish-image.yml`.
- Best use: Validate what is actually implemented for shipping and update checks, and separate that from older docs or tooling assumptions.
- Refresh triggers: Version bumps, build script changes, manifest URL changes, update-service changes, CI/workflow changes, signing or artifact-validation changes.
- Highest-risk drift areas: Runtime version drift vs docs/package metadata, default manifest URL drift, disabled CI, stale `release-check` script, missing artifact checksum/signature verification.
- Key dependent files / modules: `core/version.py`, `scripts/build_core.ps1`, `scripts/release-check.ps1`, `BUS-Core.spec`, `core/config/manager.py`, `core/api/routes/update.py`, `core/services/update.py`, `.github/workflows/publish-image.yml`.

## Version and Update Authority Matrix

| Concern | Implemented authority | Doc / tooling assumption | Status | Notes |
| --- | --- | --- | --- | --- |
| Runtime version | `core/version.py` | FastAPI app version, build script read from same source | Canonical | Main version truth. |
| Package metadata version | `pyproject.toml` | Packaging stub only | Drifted | Still `0.11.0` while runtime is `1.0.0`. |
| SoT/changelog version text | `SOT.md`, `CHANGELOG.md` | Human docs | Secondary | Useful evidence, but not code authority; some entries drift or duplicate. |
| Update-check route contract | `core/api/routes/update.py` | UI Settings/update notice consumes this response | Canonical | Fixed six-field response. |
| Update manifest URL | `%LOCALAPPDATA%\BUSCore\config.json` `updates.manifest_url` | `SOT.md` documents different default URL | Drifted | Code default is Workers URL, docs point to `buscore.ca`. |
| Manifest version field | `core/services/update.py` strict SemVer parsing | Docs also describe SemVer | Canonical | Must be `X.Y.Z`. |
| Manifest `download_url` | `core/services/update.py` extracts and returns it | UI opens it in browser | Canonical | No artifact validation beyond manifest parsing. |
| Manifest checksum / hash | No consuming code found | `SOT.md` describes hash/size expectations | Drifted | Update-check path ignores checksum fields. |
| Manifest release-notes URL | No consuming code found | `SOT.md` implies notes link in manifest | Drifted | UI does not surface release notes. |
| Release artifact signature verification | No in-app verification path found | README/build notes mention signing | Drifted | Build script prints manual `signtool` steps only. |

## Build and package outputs

| Output | Status | Produced by | Destination |
| --- | --- | --- | --- |
| Windows one-file EXE | Canonical | `scripts/build_core.ps1` + `BUS-Core.spec` | `dist/BUS-Core.exe`, copied to `dist/BUS-Core-<VERSION>.exe` |
| Windows version metadata file | Canonical | `scripts/build_core.ps1` | `scripts/_win_version_info.txt` |
| Bundled UI/license assets | Canonical | `BUS-Core.spec` | Embedded in PyInstaller artifact |
| Docker image | Canonical | `Dockerfile`, `.github/workflows/publish-image.yml` | GHCR tags `latest` and `:<sha>` |
| Container runtime | Canonical | `docker-compose.yml` | Exposes `8765`, persists `/data/app.db` |

## Observed Release Flow

1. Version source is `core/version.py`; build script reads this unless explicitly overridden.
2. Windows build requires a pre-existing `.venv` with Python `3.11.x`.
3. `scripts/build_core.ps1` deletes old `build/` and `dist/`, writes `scripts/_win_version_info.txt`, and runs PyInstaller with `BUS-Core.spec`.
4. The script verifies one-file output exists at `dist/BUS-Core.exe` and copies it to `dist/BUS-Core-<VERSION>.exe`.
5. The same script prints `signtool` commands for signing and signature verification but does not execute them.
6. Docker/image build path is separate: `Dockerfile` builds the runtime image, and `.github/workflows/publish-image.yml` publishes to GHCR on `main`.
7. Repository evidence for GitHub Release creation, manifest publishing, artifact hosting, and release-note publication beyond these steps is Not determined from repository evidence.

## Observed Update Check Flow

1. UI startup notice or Settings `Check now` calls `GET /app/update/check`.
2. Route loads `updates.enabled`, `updates.channel`, `updates.manifest_url`, and `updates.check_on_startup` from `%LOCALAPPDATA%\BUSCore\config.json`.
3. `UpdateService.check()` validates the current runtime version as strict SemVer.
4. Service validates the manifest URL:
   - non-empty string
   - `http` or `https`
   - hostname present
   - not `localhost`
   - not a literal private, loopback, unspecified, or link-local IP
5. Service fetches manifest with:
   - timeout `4.0` seconds
   - `follow_redirects=False`
   - max payload size `65,536` bytes
   - JSON content-type check when header is present
6. Accepted manifest forms are:
   - direct `{ version, download_url }`
   - nested `{ latest: { version, download: { url } } }`
   - channel-selected entries under `channels.<channel>` or `<channel>`
7. Route returns normalized response keys:
   - `current_version`
   - `latest_version`
   - `update_available`
   - `download_url`
   - `error_code`
   - `error_message`
8. UI behavior:
   - startup notice only when `updates.enabled && updates.check_on_startup`
   - manual check is always available in Settings
   - `download_url` opens in a new browser tab
9. No in-app download, installer handoff, checksum verification, or signature verification was found.

## Implemented vs documented vs assumed release/update elements

| Element | Implemented in code | Documented only | Assumed by tooling | Status |
| --- | --- | --- | --- | --- |
| Runtime version source | Yes | Yes | Yes | Canonical |
| Default manifest URL | Yes (`buscore-lighthouse...workers.dev`) | Yes (`buscore.ca/manifest/core/stable.json`) | No | Drifted |
| Manual update check UI | Yes | Yes | No | Canonical |
| Startup update notice | Yes | Yes | No | Canonical |
| Manifest channel support | Yes | Yes | No | Canonical |
| Release notes link from manifest | No | Yes | No | Drifted |
| Manifest checksum/hash use | No | Yes | No | Drifted |
| In-app artifact install | No | Some docs imply release/update surface | No | Secondary |
| Binary signing execution | Manual script hint only | README implies signed releases | No | Drifted |
| CI release validation | Disabled workflows present | Release-check script exists | Yes | Drifted |

## External infrastructure references

| Reference | Status | Where it appears | Notes |
| --- | --- | --- | --- |
| `https://buscore-lighthouse.jamie-eb1.workers.dev/update/check` | Canonical | `core/config/manager.py` default updates config | Current code default manifest endpoint. |
| `https://buscore.ca/manifest/core/stable.json` | Secondary | `SOT.md` | Documented default, not current code default. |
| `https://buscore.ca` | Secondary | `README.md` | Public site reference only. |
| GHCR `ghcr.io/true-good-craft/tgc-bus-core` | Canonical | README + publish workflow | Container distribution path. |

## Deployment assumptions

| Assumption | Status | Evidence |
| --- | --- | --- |
| Native server binds `127.0.0.1:8765` by default | Canonical | `launcher.py`, `tgc/settings.py`, `README.md` |
| Docker binds `0.0.0.0:8765` and persists DB at `/data/app.db` | Canonical | `Dockerfile`, `docker-compose.yml` |
| SPA entry is `/ui/shell.html` | Canonical | `core/api/http.py`, `launcher.py` |
| Google OAuth callback defaults to `http://127.0.0.1:8765/oauth/google/callback` | Canonical | `core/api/http.py` |
| Hosted manifest must return version + download URL | Canonical | `core/services/update.py` |
| Hosted release-note URL is consumed by app | Drifted | No code path found | Mentioned only in docs expectations. |

## Fragile coupling points

| Coupling point | Status | Why it matters |
| --- | --- | --- |
| `core/version.py` vs `pyproject.toml` / `SOT.md` / `CHANGELOG.md` | Drifted | Version truth differs across code, package stub, and docs. |
| Code default manifest URL vs documented manifest URL | Drifted | Update-check behavior and docs disagree on the default authority. |
| `scripts/release-check.ps1` -> missing `build-windows.ps1` | Drifted | Release helper references a script not present in repo. |
| Disabled CI/build-test workflows | Drifted | Automated release validation is not active despite workflow presence. |
| UI update UX depends on fixed six-field route payload | Canonical | Contract break would immediately affect Settings/startup notice behavior. |
| Update path trusts surfaced `download_url` after manifest validation | Drifted | No artifact checksum/signature verification in app path. |

## Freeze Notes

- Refresh on: version bumps, build script/spec changes, update-service changes, manifest URL changes, workflow changes, or signing/validation changes.
- Fastest invalidators: aligning version authorities, changing manifest schema or endpoint, enabling real artifact verification, or replacing the build/release scripts.
- Check alongside: `02_API_AND_UI_CONTRACT_MAP.md` for `/app/update/check` contract shape and `04_SECURITY_TRUST_AND_OPERATIONS.md` for update-path security implications.
