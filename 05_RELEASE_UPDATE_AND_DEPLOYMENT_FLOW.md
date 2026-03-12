# 05_RELEASE_UPDATE_AND_DEPLOYMENT_FLOW

- Document purpose: Fast operational reference for version authority, build outputs, release flow, update-check behavior, and deployment assumptions.
- Primary authority basis: `core/version.py`, `scripts/build_core.ps1`, `scripts/release-check.ps1`, `BUS-Core.spec`, `core/api/routes/update.py`, `core/services/update.py`, `.github/workflows/release-mirror.yml`, `.github/workflows/publish-image.yml`.
- Best use: Validate what is actually implemented for shipping and update checks, and separate that from older docs or tooling assumptions.
- Refresh triggers: Version bumps, build script changes, manifest URL changes, update-service changes, CI/workflow changes, signing or artifact-validation changes.
- Highest-risk drift areas: docs overstating release signing or artifact verification, disabled non-release CI, and any future split between release tags and `core/version.py`.
- Key dependent files / modules: `core/version.py`, `scripts/build_core.ps1`, `scripts/release-check.ps1`, `BUS-Core.spec`, `core/config/manager.py`, `core/api/routes/update.py`, `core/services/update.py`, `.github/workflows/release-mirror.yml`.

## Version and Update Authority Matrix

| Concern | Implemented authority | Doc / tooling assumption | Status | Notes |
| --- | --- | --- | --- | --- |
| Runtime version | `core/version.py` | FastAPI app version, build script read from same source | Canonical | `VERSION` is the owner-controlled public/release SemVer source. |
| Internal working version | `core/version.py` | Internal reports may expose `INTERNAL_VERSION` | Canonical | `INTERNAL_VERSION` is `X.Y.Z.R`, for repo working revisions only, and must not flow into strict SemVer consumers. |
| Package metadata version | `pyproject.toml` | Packaging stub only | Canonical mirror | Kept aligned to `core/version.py` strict SemVer `VERSION`. |
| Release tag boundary | `.github/workflows/release-mirror.yml` checks `tag == v{VERSION}` | GitHub release tags | Canonical boundary | Tags remain strict external SemVer, but are machine-checked against `core/version.py` before manifest publication. |
| Published manifest `latest.version` | `.github/workflows/release-mirror.yml` reads `core/version.py` | Hosted manifest consumers | Canonical | Published from canonical `VERSION`, not derived from tag parsing alone. |
| Update-check route contract | `core/api/routes/update.py` | UI Settings/update notice consumes this response | Canonical | Fixed six-field response. |
| Update manifest URL | `%LOCALAPPDATA%\BUSCore\config.json` `updates.manifest_url` | `SOT.md` | Canonical | Code and docs use the Lighthouse endpoint. |
| Manifest `download_url` | `core/services/update.py` extracts and returns it | UI opens it in browser | Canonical | No artifact validation beyond manifest parsing. |
| Manifest checksum / hash | No consuming code found | Manifest may publish `sha256` metadata | Drifted but explicit | Update-check path ignores checksum fields today. |
| Release artifact signature verification | No in-app verification path found | Build script prints manual signing hints only | Drifted but explicit | README and docs must not imply automatic signed-release enforcement. |

## Build and package outputs

| Output | Status | Produced by | Destination |
| --- | --- | --- | --- |
| Windows one-file EXE | Canonical | `scripts/build_core.ps1` + `BUS-Core.spec` | `dist/BUS-Core.exe`, copied to `dist/BUS-Core-<VERSION>.exe` |
| Canonical public release package (ZIP) | Canonical | Manual release packaging + GitHub release asset | `TGC-BUS-Core-<VERSION>.zip` (GitHub release), mirrored to R2 `releases/TGC-BUS-Core-<VERSION>.zip` |
| Windows version metadata file | Canonical | `scripts/build_core.ps1` | `scripts/_win_version_info.txt` |
| Bundled UI/license assets | Canonical | `BUS-Core.spec` | Embedded in PyInstaller artifact |
| Docker image | Canonical | `Dockerfile`, `.github/workflows/publish-image.yml` | GHCR tags `latest` and `:<sha>` |
| Container runtime | Canonical | `docker-compose.yml` | Exposes `8765`, persists `/data/app.db` |

## Observed Release Flow

1. `core/version.py` is the canonical public version source; runtime and build surfaces read strict SemVer `VERSION`.
2. `scripts/build_core.ps1` reads `VERSION` from `core/version.py` unless an explicit override is passed, validates `X.Y.Z`, writes Windows version metadata, builds the one-file EXE, and copies `dist/BUS-Core.exe` to `dist/BUS-Core-<VERSION>.exe`.
3. `scripts/release-check.ps1` now validates the current release chain truthfully: isolated smoke, canonical build script, and artifact existence checks for both current EXE names.
4. `.github/workflows/release-mirror.yml` checks out the tagged ref, reads `VERSION` from `core/version.py`, and fails unless the release tag exactly equals `v{VERSION}`.
5. The same workflow downloads the exact `TGC-BUS-Core-<VERSION>.zip` release asset, computes `sha256`, uploads the asset to R2 `releases/<asset-name>`, and publishes manifest `latest.version` plus an authoritative absolute `latest.download.url` from canonical `VERSION` using `https://lighthouse.buscore.ca/releases/TGC-BUS-Core-<VERSION>.zip`.
6. `.github/workflows/publish-image.yml` remains a separate container-publish workflow and does not govern Windows release/update version authority.
7. `scripts/build_core.ps1` prints manual `signtool` commands for signing and signature verification, but the repo does not automate those steps.

## Observed Update Check Flow

1. UI startup notice or Settings `Check now` calls `GET /app/update/check`.
2. Route loads `updates.enabled`, `updates.channel`, `updates.manifest_url`, and `updates.check_on_startup` from `%LOCALAPPDATA%\BUSCore\config.json`.
3. `UpdateService.check()` validates the current runtime version as strict SemVer.
4. Service validates the manifest URL, fetches JSON with timeout and size caps, normalizes supported manifest shapes, and compares `latest.version` against runtime `VERSION`.
5. Route returns normalized response keys: `current_version`, `latest_version`, `update_available`, `download_url`, `error_code`, `error_message`.
6. UI exposes `download_url` in a browser tab when an update is available.
7. No in-app download, installer handoff, checksum verification, or signature verification was found.

## Implemented vs documented vs assumed release/update elements

| Element | Implemented in code | Documented only | Assumed by tooling | Status |
| --- | --- | --- | --- | --- |
| Runtime version source | Yes | Yes | Yes | Canonical |
| Release tag must equal `VERSION` | Yes | Yes | Yes | Canonical |
| Published manifest `latest.version` from `VERSION` | Yes | Yes | Yes | Canonical |
| Default manifest URL | Yes (`lighthouse.buscore.ca/update/check`) | Yes (`lighthouse.buscore.ca/update/check`) | No | Canonical |
| Manual update check UI | Yes | Yes | No | Canonical |
| Startup update notice | Yes | Yes | No | Canonical |
| Manifest channel support | Yes | Yes | No | Canonical |
| Release notes link from manifest | No | Yes | No | Drifted |
| Manifest checksum/hash use | No | Yes | No | Drifted |
| Binary signing execution | Manual script hint only | Some older docs implied more | No | Drifted |
| Truthful release-check helper | Yes | Yes | Yes | Canonical |

## External infrastructure references

| Reference | Status | Where it appears | Notes |
| --- | --- | --- | --- |
| `https://lighthouse.buscore.ca/update/check` | Canonical | `core/config/manager.py` default updates config, `SOT.md` | Current default update endpoint. |
| `https://buscore.ca` | Secondary | `README.md` | Public site reference only. |
| GHCR `ghcr.io/true-good-craft/tgc-bus-core` | Canonical | README + publish workflow | Container distribution path. |

## Fragile coupling points

| Coupling point | Status | Why it matters |
| --- | --- | --- |
| `core/version.py` vs docs/governance text | Secondary | Runtime/build/workflow truth is canonical in code; human docs must stay in sync. |
| `scripts/release-check.ps1` vs actual smoke/build chain | Canonical | Helper now validates the real current scripts and artifact names. |
| Disabled CI/build-test workflows | Drifted | General automation remains sparse even though release/update authority is now explicit. |
| Update path trusts surfaced `download_url` after manifest validation | Drifted | No artifact checksum/signature verification in app path. |
| Release history in manifest | Narrowed drift | Current release publication is canonical, but history still reflects GitHub release metadata filtered by canonical `TGC-BUS-Core-*.zip` assets. |

## Freeze Notes

- Refresh on: version bumps, build script/spec changes, update-service changes, manifest URL changes, workflow changes, or signing/validation changes.
- Fastest invalidators: changing the canonical version source, changing release asset naming, adding real artifact verification, or rewriting release publication flow.
- Check alongside: `02_API_AND_UI_CONTRACT_MAP.md` for `/app/update/check` contract shape and `04_SECURITY_TRUST_AND_OPERATIONS.md` for update-path security implications.

## Internal Version Boundary

- `VERSION` remains the only value allowed into release tags, published manifest `latest.version`, and update comparison logic.
- `INTERNAL_VERSION` is for repo working-revision tracking only.
- `.github/workflows/release-mirror.yml` now machine-checks `tag == v{VERSION}` before publishing release metadata.
- Remaining unresolved drift is narrow and explicit: manifest checksum/signature metadata may be published, but the app does not consume or verify it, and release history still depends on GitHub release metadata plus matching BUS-Core assets.
