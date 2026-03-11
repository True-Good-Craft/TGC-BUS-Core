# TGC Business Utility System — BUS Core

![License](https://img.shields.io/badge/License-AGPLv3-blue.svg)
![Docker](https://img.shields.io/badge/Docker-GHCR-blue?logo=docker)
![Platform](https://img.shields.io/badge/Platform-Windows-blue.svg)
![Status](https://img.shields.io/badge/Status-Stable-brightgreen.svg)
[![Discord](https://img.shields.io/badge/Discord-Join%20Us-7289da.svg)](https://discord.gg/qp3rc5CxdM)




A local-first inventory and manufacturing system for small shops and solo makers.

No cloud. No accounts. No subscriptions.  
Your data stays on your machine.

---

## What Is BUS Core?

BUS Core is designed for workshops that build real things in small batches.

It replaces:

- Spreadsheets
- Paper logs
- Ad-hoc tracking systems
- Expensive SaaS platforms

With:

- One local database
- Real production costing
- Full audit history
- Complete data ownership

It is built for operators who want control, not dashboards.

---

## Who BUS Core Is For

- Small manufacturing shops (1–20 people)
- Makerspaces
- Custom fabricators
- Repair and prototyping shops
- Solo operators

If you build physical products in low to medium volume, BUS Core is for you.

---

## What It Tracks

- **Materials & Consumables**  
  Track stock by unit (grams, millimeters, milliliters, each), with batch numbers, cost, and purchase dates.

- **Blueprints (Recipes)**  
  Define how materials become products. Costs are calculated using FIFO from real purchase batches.

- **Assemblies & Products**  
  Build items from blueprints, set prices, and compare real costs to sales.

- **Vendors**  
  Track supplier pricing and purchasing history over time.

BUS Core focuses on operations and production costing.  
It is not a full accounting system—and is not trying to be.

---

## Key Features

- **Open Source** — 100% free (AGPLv3)
- **Precision Inventory** — FIFO batch valuation with metric units
- **Manufacturing Engine** — Recipe-based builds with atomic commits
- **Ledger & Audit Trail** — Complete movement history
- **Local & Private** — SQLite database with encrypted backups
- **Cross-Platform** — Windows, Linux, and macOS

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

Enable development features by setting:

```bash
BUS_ENV=dev
````

This enables:

* Console output
* Debug endpoints
* Smoke tests (`scripts/smoke.ps1`)

Development scripts are included in the source tree.

---

## Architecture

See [`SOT.md`](SOT.md) for the canonical Source of Truth and system architecture.

---

## Interface Gallery

|                   Dashboard                   |                      Inventory                     |
| :-------------------------------------------: | :------------------------------------------------: |
| <img src="screenshots/Home.jpg" width="100%"> | <img src="screenshots/Inventory.jpg" width="100%"> |

|                      Manufacturing                     |                     Recipes                     |
| :----------------------------------------------------: | :---------------------------------------------: |
| <img src="screenshots/Manufacturing.jpg" width="100%"> | <img src="screenshots/Recipe.jpg" width="100%"> |

|                      Logs                     |                      Settings                     |
| :-------------------------------------------: | :-----------------------------------------------: |
| <img src="screenshots/Logs.jpg" width="100%"> | <img src="screenshots/Settings.jpg" width="100%"> |

---

## Run with Docker

```bash
docker pull ghcr.io/true-good-craft/tgc-bus-core:latest

docker run -p 8765:8765 ghcr.io/true-good-craft/tgc-bus-core:latest
```

(Docker is optional. Native Windows builds are supported.)



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
2. No artificial limits
3. User owns their data

Software should serve small operators, not extract from them.

---

## Security & Release Verification

BUS Core runs locally and does not require network access for normal use.

- Windows release builds are produced from `scripts/build_core.ps1` and `BUS-Core.spec`.
- `scripts/build_core.ps1` prints optional manual `signtool` commands, but this repo does not currently guarantee automated code-signing for every release.
- The update check path validates manifest URL, JSON shape, payload size, and strict SemVer only.
- The app does not currently verify artifact checksum or signature before surfacing a release `download_url`.
- Builds remain reproducible from source.

Note: Windows Defender or SmartScreen warnings may appear for new releases, especially when a binary is unsigned or has not yet built reputation.

## License

BUS Core is licensed under the GNU AGPLv3.

You are free to use, modify, and self-host it.
If you offer it as a network service, you must provide source access.

See `LICENSE` for details.

https://buscore.ca

Maintained by True Good Craft (Canada)




