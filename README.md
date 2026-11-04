# TGC Business Utility System — BUS Core
[![Open BUS Core](https://img.shields.io/badge/Open%20BUS%20Core-Run%20It%20Now-FF6D00?style=for-the-badge&logo=windows&logoColor=white)](https://buscore.ca/?src=github_readme_1)

Manufacturing operations software for small shops.


A practical inventory and manufacturing system for small shops that need durable control.


Run BUS Core yourself for free, or have True Good Craft host and manage it for you. The self-managed product requires no hosted account or subscription, remains usable offline, and keeps its data portable.


![License](https://img.shields.io/badge/License-AGPLv3-blue.svg)
![Docker](https://img.shields.io/badge/Docker-GHCR-blue?logo=docker)
![Platform](https://img.shields.io/badge/Platform-Windows-blue.svg)
![Status](https://img.shields.io/badge/Status-Stable-brightgreen.svg)
[![Discord](https://img.shields.io/badge/Discord-Join%20Us-7289da.svg)](https://discord.gg/qp3rc5CxdM)
[![Sponsor](https://img.shields.io/badge/Sponsor-GitHub%20Sponsors-24292f.svg?logo=githubsponsors)](https://github.com/sponsors/truegoodcraft)

<a href="https://sourceforge.net/projects/tgc-bus-core/" target="_blank" rel="noopener noreferrer"><img src="https://a.fsdn.com/con/app/syndication/badge_img_direct/oss-rising-star/oss-rising-star/?variant_id=sf" alt="BUS Core is a SourceForge Rising Star (November 2026)" width="72" height="72"/></a>


---

## What Is BUS Core?

BUS Core is the sovereign local system of record for workshops that build real things in small batches.

It is meant to be boring in the right ways: stable, predictable, reviewable, and fully usable on its own.

Core owns the canonical business logic, local data model, and operator-safe base workflows. Managed hosting and services remain optional and must not create a divergent BUS fork.

It replaces:

- Spreadsheets
- Paper logs
- Ad-hoc tracking systems
- Expensive SaaS platforms

With:

- One local database
- Real production costing
- Ledger and movement history
- Complete data ownership

It is built for operators who want control and continuity, not SaaS dependency.

---

## Who BUS Core Is For

- Small manufacturing shops
- Makerspaces
- Custom fabricators
- Repair and prototyping shops
- Solo operators

If you build physical products and want local authority over inventory, costing, and operating records, BUS Core is for you.


Use case example:
https://buscore.ca/use-cases/laser-engraving-shop/?src=github_readme_usecase


---

## What It Tracks

- **Materials & Consumables**  
  Track stock by unit (grams, millimeters, milliliters, each), with batch numbers, cost, and purchase dates.

- **Recipes**  
  Define how materials become products. Costs are calculated using FIFO from real purchase batches.

- **Jobs & Invoices**
  Track customer work, create local draft invoices from jobs, issue invoices, mark them paid, void mistakes, and print invoice HTML for browser print or save-to-PDF.

- **Manufacturing & Products**
  Manufacture products from recipes, set product prices, and compare real costs to sales.

- **Vendors**  
  Track supplier pricing and purchasing history over time.

BUS Core focuses on operations and production costing.  
It is not a full accounting system—and is not trying to be.

## What Changed Since Laser Everything

- Clearer Product / Recipe / Output Item language for the first setup path, with the recipe UI labeling the selected result as Output Product.
- Better stock-out sale price guidance, including usual product price display and below-usual warnings.
- Readable shortage messages for manufacturing and stock-out failures.
- Manufacturing history labels such as `Run #6`.
- Finance date presets for common recent, month, quarter, and year views.

## Product Direction

BUS Core remains a maintained manufacturing operations product. Reliability, safety, backups, data protection, release hygiene, and operator clarity remain priorities, while future product work follows demonstrated manufacturing needs. Operators may run the complete open-source product themselves or use the deployed Managed BUS inquiry when they want True Good Craft to host, update, back up, monitor, and support it through a scoped service engagement.

Managed BUS is not yet represented here as a generally available production service. A public intake and a credible isolated deployment baseline must exist first.

## Still Not Included

BUS Core remains serious manufacturing operations software, not a full accounting suite. It does not include full POS, full accounting, QuickBooks/Wave sync, automatic reorder, full job scheduling, cloud synchronization, payment links, customer portals, or recurring billing.

BUS Core v1.4.2 makes optional version-aware update checks and includes a strict optional product-telemetry client: it waits for first-run disclosure, blocks new emits/new flush starts when disabled, queues only allowlisted events, makes at most three trigger-driven delivery attempts, and never blocks local work. Disabling does not cancel a sender request already in flight. Retry eligibility alone does not schedule a future wake, and shutdown does not wait for delivery. A queued event is complete only after Lighthouse acknowledges its exact event ID; rejected, exhausted, or queue-overflowed events are retained in a bounded local dead-letter file and exposed only as aggregate delivery diagnostics. Payloads contain only the event name, event ID, timestamp, app version, release channel, and coarse operating-system category. They contain no persistent installation identifier. Customer, supplier, employee, item, recipe, invoice, email, document, filepath, financial, quantity, database, username, and machine-fingerprint content cannot enter the payload constructor. SOT-authorized signals are limited to first launch, once-per-version release adoption, startup/manual update checks, successful update staging, reliability, and one-time successful use of major product areas; the additional repeatable restore/import outcomes currently implemented are documented as unresolved code/SOT drift in `OPERATIONS.md`. BUS Core does not report module opens, active days, sessions, returning installations, engagement, or retention. Local delivery truth is available through the protected telemetry status route and local state described in `OPERATIONS.md`; Home and `/transparency.report` are not current telemetry authorities. The schema-1.0 receiver/migration baseline was deployed and production-verified at Lighthouse 1.27.0 with migration 0015; Lighthouse's own SOT is authority for its current deployed version, and this BUS Core release remains owner-controlled.

---

## Key Features

- **Open Source Core** — AGPLv3-licensed local infrastructure
- **Precision Inventory** — FIFO batch valuation with metric units
- **Manufacturing Engine** — Recipe-based builds with atomic commits
- **Jobs & Invoices** — Local job tracking and invoice truth without cloud billing dependency
- **Ledger & Audit Trail** — Complete movement history
- **Local & Private** — SQLite database with password-based encrypted backup export support
- **Theme Variants** — Forge Dark default plus Clean Light, Workshop Slate, and High Contrast UI variants
- **Windows Native, Docker Optional** — Native Windows runtime, container support for other environments

---

## Getting Started

### Prerequisites

- Windows (primary support)
- Linux / macOS (supported via Docker)

---

## Installation (Windows)

1. Download the latest release.
2. Run the `.exe` file.
3. No installer required.

> Note: Windows Defender or SmartScreen may warn on first run. This repo does not currently guarantee automated code-signing for every Windows release.

The application runs in the **system tray**.  
Double-click the tray icon to open the dashboard.

---

## Development Mode

Enable development features with the canonical launcher flag or environment variable:

```powershell
$env:BUS_DEV = "1"
python launcher.py --dev
```

On shells that support inline environment assignment:

```bash
BUS_DEV=1 python launcher.py --dev
```

`BUS_DEV=1` exposes development-only surfaces and detailed errors. It does not bypass session authentication and does not suppress or redirect native product telemetry. Run `scripts/smoke.ps1` separately when that test action is approved.

Development scripts are included in the source tree.

---

## Architecture

Read [`AGENTS.md`](AGENTS.md) before repository work, [`SOT.md`](SOT.md) for canonical behavior and architecture, and [`OPERATIONS.md`](OPERATIONS.md) for side-effect-aware diagnostics and Lighthouse/telemetry access.

---

## Interface Gallery

Screenshots are being refreshed for the current Product / Recipe / Manufacturing workflow. The workflow and release notes above are the authority for the current Core experience.

---

## Run with Docker

```bash
docker compose up --build

# or, without Compose:
docker pull ghcr.io/true-good-craft/tgc-bus-core:latest
docker run -p 127.0.0.1:8765:8765 ghcr.io/true-good-craft/tgc-bus-core:latest
```

Docker is optional. Native Windows builds are supported.

Docker Compose defaults to loopback-only host publishing: `127.0.0.1:8765:8765`. BUS Core is local-first software; it is not safe for LAN or public exposure by default. The default session model is intended for local loopback use, not multi-user network hosting. Any non-loopback Docker deployment requires explicit operator action, a clearly separated override, and stronger access controls around the host, network, and `/session/token` bootstrap surface.



### Auto-Open Scripts

#### Windows

```powershell
scripts\up.ps1
```

#### macOS / Linux

```bash
./scripts/up.sh
```

### Health Check

```bash
curl http://localhost:8765/health
```

`/health` proves only that a process responds with its public version. The request is logged; it does not prove database, telemetry, Lighthouse, or Agent Smith health. Do not start BUS Core merely to obtain this response.

UI:

```
http://localhost:8765/ui/shell.html
```

### Stop

```bash
docker compose down
# or
docker rm -f bus-core
```

---

## Run Natively (Windows)

Docker is optional.

```powershell
pip install -r requirements.txt

python launcher.py
# or
.\Run Core.bat
```

`launcher.py` is the canonical native entry. It boots the canonical HTTP runtime from `core.api.http:create_app()` and opens `/ui/shell.html`.

UI:

```
http://localhost:8765/ui/shell.html
```

---
## Data & Persistence

* All data is stored locally in SQLite.
* Docker deployments persist data in `/data`.
* Default database path:

```bash
BUS_DB=/data/app.db
```

Backups can be encrypted using AES-GCM.

---

## Philosophy

BUS Core is built on three principles:

1. Local-first by default
2. Predictable, operator-safe behavior
3. User owns their data and operating continuity

Software for small shops should preserve trust, not manufacture dependency.

---

## Support BUS Core

BUS Core is supported through GitHub Sponsors and the BUS Core support page:

- GitHub Sponsors: https://github.com/sponsors/truegoodcraft
- BUS Core support: https://buscore.ca/support

## Acknowledgements

In November 2026, BUS Core received a [SourceForge](https://sourceforge.net/projects/tgc-bus-core/) Rising Star award. Thank you to everyone who has downloaded, tested, reported bugs, and shared BUS Core with other shops.

## Security & Release Verification

BUS Core runs locally and does not require network access for normal use.

- Windows release builds are produced from `scripts/build_core.ps1` and `BUS-Core.spec`; `-Release` enables Authenticode signing and the verified release ZIP bundle.
- Release mode requires the governed Python 3.11 build environment, the pinned PyInstaller toolchain, a current-user code-signing certificate matching the configured thumbprint, and Windows SDK `signtool`. Pass `-SignToolPath` when `signtool.exe` is not on `PATH`.
- Runtime and release dependencies are installed from platform-specific, hash-locked graphs; see [`docs/dependency-management.md`](docs/dependency-management.md) for the governed refresh and verification procedure.
- The build fails closed unless the onefile archive is complete, unsigned and signed launch smoke succeeds, the signer thumbprint and Authenticode signature verify, copied hashes match, and the final ZIP contains the expected executable and packaged documents.
- Update checks are default-on / opt-out. The sidebar startup controller is the only automatic owner and requests `source=startup`; the backend runs at most one startup check per app launch and enforces both `updates.enabled` and `updates.check_on_startup`. Manual `source=manual` checks remain available regardless of those automatic-check settings.
- Manual "Check now" remains available even when startup checks are disabled.
- The exact `GET /app/update/check` route is currently public. A performed check is non-staging discovery, but it is not a passive diagnostic: it makes the configured outbound request, writes request evidence, can affect Lighthouse count/rate/error evidence, and may enqueue product telemetry. While the first-check flag remains false, each performed check retries its best-effort config write; after a write succeeds, later checks do not rewrite it.
- Update-route analytics and optional product-event delivery are independent Lighthouse signal streams. Neither is a people, authenticated-client, unique-install, adoption, engagement, or retention count.
- BUS Core does not auto-download, auto-install, auto-stage on startup, or force restart.
- The sidebar "Update" button is manual and write-gated. It calls `/app/update/stage` only after the user clicks it.
- The update check path validates manifest URL policy, JSON/content type, payload size, strict SemVer, supported manifest shapes, configured channel selection, optional signed-manifest unwrapping, and optional artifact metadata shape.
- Current manifests must remain backward-compatible for deployed clients by keeping top-level `latest.version` and `latest.download.url`; new clients can additionally read `channels.<channel>`, additive metadata, and the top-level embedded Ed25519 `signature`.
- The release mirror signs the public manifest before upload using a private key stored outside the repo in GitHub secret `BUSCORE_MANIFEST_SIGNING_PRIVATE_KEY`; the matching public key is pinned in Core as `bus-core-prod-ed25519-2026-04-25`.
- Manual update staging now requires trusted signed manifests. Non-staging `/app/update/check` discovery still preserves unsigned-manifest compatibility.
- `/app/update/stage` runs the trusted manual staging chain: signed release selection, hash-verified ZIP download, safe extraction, EXE Authenticode plus True Good Craft signer checks with pinned thumbprint, and conservative version+sha keyed `verified_ready_versions` promotion. Legacy `verified_ready` is the compatibility/latest record and remains an active launcher fallback for valid older state.
- `/app/update/check` does not stage or launch artifacts, but it changes local and remote analytics evidence when a check is performed.
- BUS Core does not overwrite the running EXE. After successful staging, the launcher can hand off on next start (after DB ownership lock) using configured verified launch policy.
- Channel support exists in Core config for `stable`, `test`, `partner-3dque`, `lts-1.1`, and `security-hotfix`, but current release automation publishes the stable manifest lane only.
- BUS Core has DB/app ownership locking to prevent two live owners of the same DB/app root.
- Docker is a separate deployment lane. Docker Compose publishes the app to host loopback only by default; the container-internal Uvicorn bind remains `0.0.0.0` so Docker networking works. Current GHCR images are tagged `latest` and commit SHA only; there are no SemVer image tags, image signatures, SBOM/provenance artifacts, image scans, or formal Docker update policy yet.
- Builds remain reproducible from source.

Note: Windows Defender or SmartScreen warnings may appear for new releases, especially when a binary is unsigned or has not yet built reputation.

## License

BUS Core is licensed under the GNU AGPLv3.

You are free to use, modify, and self-host it.
If you offer it as a network service, you must provide source access.

See `LICENSE` for details.

[https://buscore.ca](https://buscore.ca/?src=github_readme_1)

Maintained by True Good Craft (Canada)



