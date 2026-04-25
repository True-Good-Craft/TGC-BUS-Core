# 05_RELEASE_UPDATE_AND_DEPLOYMENT_FLOW

- Document purpose: Fast operational reference for version authority, build outputs, release flow, update-check behavior, and deployment assumptions, with emphasis on trustworthy infrastructure and explicit release authority.
- Primary authority basis: `core/version.py`, `scripts/validate_version_governance.py`, `scripts/validate_change_trace.py`, `scripts/build_core.ps1`, `scripts/release-check.ps1`, `BUS-Core.spec`, `core/api/routes/update.py`, `core/services/update.py`, `.github/workflows/governance-guard.yml`, `.github/workflows/release-mirror.yml`, `.github/workflows/publish-image.yml`.
- Best use: Validate what is actually implemented for shipping and update checks, and separate that from older docs or tooling assumptions.
- Refresh triggers: Version bumps, build script changes, manifest URL changes, update-service changes, CI/workflow changes, signing or artifact-validation changes.
- Highest-risk drift areas: docs overstating release signing or artifact verification, any future bypass of `.github/workflows/governance-guard.yml`, and any future split between release tags and `core/version.py`.
- Key dependent files / modules: `core/version.py`, `scripts/build_core.ps1`, `scripts/release-check.ps1`, `BUS-Core.spec`, `core/config/manager.py`, `core/api/routes/update.py`, `core/services/update.py`, `.github/workflows/release-mirror.yml`.

## Version and Update Authority Matrix

In the current stabilization phase, trustworthy release infrastructure means operators can tell where version truth lives, what the app validates, and what it does not. Update checks are default-on / opt-out for a one-shot startup notice, manual checks remain available, and the app must stay honest about the limits of current verification.

| Concern | Implemented authority | Doc / tooling assumption | Status | Notes |
| --- | --- | --- | --- | --- |
| Runtime version | `core/version.py` | FastAPI app version, build script read from same source | Canonical | `VERSION` is the owner-controlled public/release SemVer source. |
| Internal working version | `core/version.py` | Internal reports may expose `INTERNAL_VERSION` | Canonical | `INTERNAL_VERSION` is `X.Y.Z.R`, for repo working revisions only, and must not flow into strict SemVer consumers. |
| Package metadata version | `pyproject.toml` | Packaging stub only | Checked mirror | `scripts/validate_version_governance.py` now fails if `pyproject.toml` diverges from canonical `core/version.py::VERSION`. |
| Version-governance mirrors | `scripts/validate_version_governance.py` + `.github/workflows/governance-guard.yml` | `SOT.md`, Windows version metadata, package metadata | Canonical guard | Canonical version mirrors are now machine-checked on push, pull request, and manual workflow runs. |
| Release tag boundary | `.github/workflows/release-mirror.yml` checks `tag == v{VERSION}` | GitHub release tags | Canonical boundary | Tags remain strict external SemVer, but are machine-checked against `core/version.py` before manifest publication. |
| Published manifest `latest.version` | `.github/workflows/release-mirror.yml` reads `core/version.py` | Hosted manifest consumers | Canonical | Published from canonical `VERSION`, not derived from tag parsing alone. |
| Published manifest signature | `.github/workflows/release-mirror.yml` runs `scripts/sign_manifest.py` | GitHub Actions release workflow | Canonical | Generated `stable.json` is signed into `stable.signed.json`; missing `BUSCORE_MANIFEST_SIGNING_PRIVATE_KEY` fails the workflow before upload. |
| Manifest public-key trust policy | `core/runtime/manifest_keys.py` | Core runtime verifier and release workflow verification step | Canonical | Production public key `bus-core-prod-ed25519-2026-04-25` is pinned in Core; private key must never be committed. |
| Update-check route contract | `core/api/routes/update.py` | UI Settings/update notice consumes this response | Canonical | Fixed six-field response. |
| Update manifest URL | `%LOCALAPPDATA%\BUSCore\config.json` `updates.manifest_url` | `SOT.md` | Canonical | Code and docs use the Lighthouse endpoint. |
| Manifest `download_url` | `core/services/update.py` extracts and returns it | UI opens it in browser | Canonical | No artifact verification beyond manifest parsing, optional manifest signature support, and metadata validation. |
| Manifest checksum / hash | `core/services/update.py` validates and carries declared metadata when present | Manifest may publish `sha256` metadata | Bridge groundwork | Update-check path retains declared metadata internally but does not verify artifact bytes. |
| Local update cache/state skeleton | `core/runtime/update_cache.py` / update state model | Future verified handoff | Bridge groundwork | `%LOCALAPPDATA%\BUSCore\updates\` can hold `manifests\`, `downloads\`, `versions\`, and `state.json`; `verified_ready` is a shape only. |
| DB/app ownership lock | Launcher preflight plus app-level lock | Future verified handoff prerequisite | Canonical | Same DB/app root cannot have two live BUS Core owners. |
| Manifest channel selection | `core/config/update_policy.py` + `core/services/update.py` | Configured channel decides selected release entry | Canonical | Non-stable channels require explicit channel-specific entries and must not fall back to public latest. |
| Release artifact signature verification | No in-app verification path found | Build script prints manual signing hints only | Drifted but explicit | README and docs must not imply automatic signed-release enforcement. |

## Build and package outputs

| Output | Status | Produced by | Destination |
| --- | --- | --- | --- |
| Windows one-file EXE | Canonical | `scripts/build_core.ps1` + `BUS-Core.spec` | `dist/BUS-Core.exe`, copied to `dist/BUS-Core-<VERSION>.exe` |
| Canonical public release package (ZIP) | Canonical | Manual release packaging + GitHub release asset | `BUS-Core-<VERSION>.zip` (GitHub release), mirrored to R2 `releases/BUS-Core-<VERSION>.zip` |
| Windows version metadata file | Canonical | `scripts/build_core.ps1` | `scripts/_win_version_info.txt` |
| Bundled UI/license assets | Canonical | `BUS-Core.spec` | Embedded in PyInstaller artifact |
| Docker image | Canonical | `Dockerfile`, `.github/workflows/publish-image.yml` | GHCR tags `latest` and `:<sha>` |
| Container runtime | Canonical | `docker-compose.yml` | Exposes `8765`, persists `/data/app.db` |

## Observed Release Flow

1. `core/version.py` is the canonical public version source; runtime and build surfaces read strict SemVer `VERSION`.
2. `scripts/build_core.ps1` reads `VERSION` from `core/version.py` unless an explicit override is passed, validates `X.Y.Z`, writes Windows version metadata, builds the one-file EXE, and copies `dist/BUS-Core.exe` to `dist/BUS-Core-<VERSION>.exe`.
3. `scripts/release-check.ps1` now validates the current release chain truthfully: isolated smoke, canonical build script, and artifact existence checks for both current EXE names.
4. `.github/workflows/release-mirror.yml` now separates tooling checkout from release identity: release-triggered runs still check out the published tag, while manual `workflow_dispatch` backfills may check out a current tooling ref such as `main` and mirror an older `release_tag` independently.
5. For published releases, the workflow still reads `VERSION` from `core/version.py` and fails unless the release tag exactly equals `v{VERSION}`. For manual backfills, it validates the requested `release_tag` as strict `vX.Y.Z`, derives manifest `latest.version` and expected asset name from that requested tag, and uses the same tag for release download and release notes URL generation.
6. The same workflow downloads the exact `BUS-Core-<VERSION>.zip` release asset, computes `sha256`, uploads the asset to R2 `releases/<asset-name>`, and generates manifest `latest.version` plus an authoritative absolute `latest.download.url` using `https://lighthouse.buscore.ca/releases/BUS-Core-<VERSION>.zip`.
7. Before signing, the workflow now prints the working directory, lists `scripts/`, and fails clearly if `scripts/sign_manifest.py` is missing from the checked-out tooling ref. It then signs generated `stable.json` into `stable.signed.json` with `scripts/sign_manifest.py`, key ID `bus-core-prod-ed25519-2026-04-25`, and GitHub secret `BUSCORE_MANIFEST_SIGNING_PRIVATE_KEY`. If that secret is missing, the workflow fails clearly and does not silently publish an unsigned manifest.
8. The workflow verifies that the signed manifest preserves `latest.version` and `latest.download.url`, contains `signature.alg = Ed25519` and the expected key ID, and verifies the embedded signature using Core's pinned public key policy before upload.
9. The signed manifest is uploaded in place to R2 as `manifest/core/stable.json`. Lighthouse serves/proxies that manifest, but Lighthouse does not own signing authority; the GitHub Actions release workflow does.
10. `.github/workflows/publish-image.yml` remains a separate container-publish workflow and does not govern Windows release/update version authority.
11. `scripts/build_core.ps1` prints manual `signtool` commands for signing and signature verification, but the repo does not automate those steps.

This flow is trustworthy to the extent that version authority is singular and machine-checked. It is not yet a cryptographically verified end-to-end updater, and the docs should not imply otherwise.

Manifest compatibility is a release boundary for this bridge release: deployed clients must still find top-level `latest.version` and `latest.download.url`, while newer clients may additionally read additive metadata, `channels.<channel>` entries, and a top-level embedded `signature`. `channels.stable` should mirror top-level `latest` unless a release owner intentionally documents a divergence. The embedded signature covers deterministic canonical JSON of the manifest after removing top-level `signature`.

## Observed Update Check Flow

1. UI startup notice or Settings `Check now` calls `GET /app/update/check`.
2. Startup gating happens in the UI using `updates.enabled !== false` and `updates.check_on_startup !== false`; manual `Check now` still calls the route regardless of those two gates.
3. Route loads the configured `updates.channel` and `updates.manifest_url` from `%LOCALAPPDATA%\BUSCore\config.json`.
4. `UpdateService.check()` validates the current runtime version as strict SemVer.
5. Service validates the manifest URL and configured channel, fetches JSON with timeout and size caps, normalizes supported manifest shapes, supports signed manifest unwrapping when present, validates optional metadata shape, and compares the selected release version against runtime `VERSION`.
6. Route returns normalized response keys: `current_version`, `latest_version`, `update_available`, `download_url`, `error_code`, `error_message`.
7. UI exposes `download_url` in a browser tab when an update is available.
8. No in-app download, installer handoff, ZIP checksum verification, artifact signature verification, publisher verification, or artifact-size verification is implemented. Client-side signed-manifest enforcement is also not enabled yet; unsigned compatibility remains available.

Update checks are part of the trust model because they are optional and non-blocking. Core remains usable without them, and an unavailable manifest host should not prevent normal local operation.

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
| Embedded manifest signing publication | Yes | Yes | Yes | Canonical |
| Client requires signed manifest | No | Future work only | No | Explicitly not enabled |
| Local update cache/state skeleton | Yes | Yes | No | Bridge groundwork |
| `verified_ready` state from real artifacts | No | Future work only | No | Shape only; no real artifact verification writes yet |
| Release notes link from manifest | Internal declared metadata only | Yes | No | Bridge groundwork |
| Manifest checksum/hash use | Internal declared metadata only | Yes | No | Bridge groundwork |
| Artifact signature/publisher/size verification | No | Future work only | No | Drifted but explicit |
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
| Governance guard workflow bypass | Narrowed drift | General automation remains sparse, but version and change-trace governance now fail through an active dedicated workflow. |
| Update path surfaces `download_url` after manifest validation | Bridge drift | Manifest metadata is validated and retained as declared values, but no artifact checksum/signature/publisher/size verification exists in the app path. |
| Release history in manifest | Narrowed drift | Current release publication is canonical, but history still reflects GitHub release metadata filtered by canonical `BUS-Core-*.zip` assets. |
| Manifest signing key custody | Canonical but operational | Private key lives outside repo in GitHub secret `BUSCORE_MANIFEST_SIGNING_PRIVATE_KEY`; public key is pinned in Core. |

Release and update trust here depends more on clear authority and honest limits than on a large automation footprint. The current boundary is: canonical version authority exists, authority mirrors and change-trace requirements are machine-checked, tag alignment is checked, manifests are signed during release publication, update metadata is normalized, channel-specific manifests are selected explicitly, declared artifact metadata is carried forward internally, and artifact integrity is not yet enforced by the runtime.

Known remaining release/update work is explicit: enabling client-side signed-manifest enforcement, artifact hash/signature/publisher/size verification, real artifact download/extraction, verified-ready writes from real artifacts, update handoff, preserving the manual Windows signing ceremony until automation is practical, and Docker release hardening if the container lane needs governed releases.

## Freeze Notes

- Refresh on: version bumps, build script/spec changes, update-service changes, manifest URL changes, workflow changes, or signing/validation changes.
- Fastest invalidators: changing the canonical version source, changing release asset naming, adding real artifact verification, or rewriting release publication flow.
- Check alongside: `02_API_AND_UI_CONTRACT_MAP.md` for `/app/update/check` contract shape and `04_SECURITY_TRUST_AND_OPERATIONS.md` for update-path security implications.

## Internal Version Boundary

- `VERSION` remains the only value allowed into release tags, published manifest `latest.version`, and update comparison logic.
- `INTERNAL_VERSION` is for repo working-revision tracking only.
- `.github/workflows/release-mirror.yml` now machine-checks `tag == v{VERSION}` before publishing release metadata.
- Remaining unresolved drift is narrow and explicit: manifests are signed during release publication, but client enforcement is still off; manifest checksum/artifact-signature/publisher/size metadata may be published and retained internally as declared metadata, but the app does not verify artifact bytes or publisher identity, and release history still depends on GitHub release metadata plus matching BUS-Core assets.

## Manifest Key Rotation

- Add the new production public key to `core/runtime/manifest_keys.py` as active.
- Publish manifests signed with the new key ID after clients have the new public key.
- Mark the old key deprecated while older clients migrate.
- Revoke or remove the old key only after supported clients trust the replacement.
