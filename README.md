# TGC (Buisness Utility System) - BUS Core (Beta)

![License](https://img.shields.io/badge/License-AGPLv3-blue.svg)
![Platform](https://img.shields.io/badge/Platform-Windows-blue.svg)
![Status](https://img.shields.io/badge/Status-Beta-orange.svg)
[![Discord](https://img.shields.io/badge/Discord-Join%20Us-7289da.svg)](https://discord.gg/qp3rc5CxdM)



BUS-Core

A free, local-first inventory and manufacturing tracker for small Buisness and single-person workshops.

No cloud. No accounts. No subscriptions.

If this is enough for you, that’s the point.

##
At its core, BUS-Core helps you track everything that moves through your shop:

Materials & Consumables: Record stock by unit (grams, millimeters, milliliters, or each), with batch numbers, purchase price, and date added.

Blueprints(Recipe): Define the recipes that turn raw materials into assemblies or finished goods. BUS-Core automatically calculates cost of goods based on the FIFO (First-In, First-Out) batches you’ve actually purchased.

Assemblies & Products: Produce items using your blueprints and set a final selling price—then compare the real cost of input materials against sales to measure margin and waste.

Vendors: Link materials and consumables to vendors and track their pricing history over time.

It’s not an accounting program, and it’s not trying to be.
BUS-Core exists to replace spreadsheet chaos and overpriced SaaS platforms that bleed your margins. It’s your own local workshop system—clean, transparent, and yours.

## Key Features

- Zero-License: 100% free and open-source (AGPLv3). No “Pro” tiers, no locked features, no tracking.
- Precision Inventory: Integer-based metric tracking with FIFO batch valuation and accurate stock costing.
- Manufacturing Engine: Recipe-based builds with automatic cost rollups, shortage detection, and atomic commits.
- Ledger & Audit Trail: Full movement history—purchases, production, sales, loss, and adjustments.
- Local & Private: Runs on a local SQLite database with optional AES-GCM encrypted backups.
- Cross-Platform: Works on Windows (primary), Linux, and macOS.


## Getting Started

### Prerequisites
* Windows (Primary support), Linux, or macOS soon tm

### Installation

1.  Download the File.
2.  Double click to run the exe.
3.  No install, no extras, I am waiting for Code signing cert so Virus protection may prompt on download.
    

**Note for Windows Users:** The application runs in the **System Tray**. If the browser does not open automatically, or if you close the window, double-click the tray icon to access the dashboard.

## Dev Mode

you must set env var to dev. 

  * **Console Access:** Keeps the terminal window open (hidden by default in production).
  * **Debug Endpoints:** Enables access to protected `/dev` API routes.
  * **Smoke Tests:** Validate system integrity using `scripts/smoke.ps1`.
  * scripts avalable with source code

## Architecture

See [docs/SOT.md](docs/SOT.md) for the Source of Truth and architecture details.



Interface Gallery

| Dashboard | Inventory Management |
| :---: | :---: |
| <img src="screenshots/Home.jpg" width="100%"> | <img src="screenshots/Invintory.jpg" width="100%"> |

| Manufacturing | Recipe Engine |
| :---: | :---: |
| <img src="screenshots/Manufacturing.jpg" width="100%"> | <img src="screenshots/Recipe.jpg" width="100%"> |

| System Logs | Application Settings |
| :---: | :---: |
| <img src="screenshots/Logs.jpg" width="100%"> | <img src="screenshots/Settings.jpg" width="100%"> |

```

## Run with Docker

### Quick start (Docker Compose)
```bash
docker compose build
docker compose up -d
# open http://localhost:8765
```

One-liner without Compose
```bash
docker build -t bus-core .
docker run -d --name bus-core -p 8765:8765 -e BUS_DB=/data/app.db -v bus_data:/data bus-core
```

Health & UI
```bash
curl http://localhost:8765/health
# UI:
# http://localhost:8765/ui/shell.html#/home
```

Stop / Remove
```bash
docker compose down
# or:
docker rm -f bus-core
```
