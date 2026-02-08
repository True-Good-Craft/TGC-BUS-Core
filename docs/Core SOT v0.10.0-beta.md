# TGC BUS Core — Source of Truth

**Version:** v0.10.0-beta  
**Updated:** 2025-12-14  
**Status:** Beta

> **Authority:** Code is truth. Where this document and code disagree, update this document.

---

## 1. Identity & Naming

| Field | Value |
|-------|-------|
| Company | True Good Craft (TGC) |
| Acronym | Business Utility System |
| Product | TGC BUS Core |
| Short Form | BUS Core |

---

## 2. Purpose & Scope

**Audience:** Small/micro shops (makers, 1–10 person teams), local-first, anti-SaaS owners.

**Primary Value:** Keep inventory, contacts, manufacturing, and critical data on the owner's machine.

**Core Principles:**
- **Local-first:** Runs on a single machine with local files and DB.
- **Open-core:** AGPL license.
- **No forced cloud:** No mandatory SaaS or telemetry.
- **Local-only analytics:** All analytics computed from local DB only.
- **Single-operator friendly:** If one person runs the shop, one person manages the system.

---

## 3. Architecture

### 3.1 Stack

| Component | Technology |
|-----------|------------|
| Backend | Python / FastAPI (`core.api.http:create_app`) |
| Database | SQLite via SQLAlchemy ORM |
| UI | Single-page shell (`core/ui/shell.html`) + modular JS cards |
| Server | Uvicorn at `127.0.0.1:8765` |

### 3.2 Entry Points

| Script | Purpose |
|--------|---------|
| `scripts/launch.ps1` | Canonical launcher (creates venv, installs deps, starts server) |
| `scripts/smoke.ps1` | Canonical smoke test harness |

### 3.3 Windows Paths

| Resource | Path |
|----------|------|
| Database | `%LOCALAPPDATA%\BUSCore\app\app.db` (default) |
| Config | `%LOCALAPPDATA%\BUSCore\config.json` |
| Exports | `%LOCALAPPDATA%\BUSCore\exports` |
| Journals | `%LOCALAPPDATA%\BUSCore\app\data\journals\` |
| Reader Settings | `%LOCALAPPDATA%\BUSCore\settings_reader.json` |

**Override:** Set `BUS_DB` environment variable to use a custom DB path.

**Migration:** On first run, if `data/app.db` exists in repo and AppData DB does not, Core copies repo DB to AppData.

---

## 4. Domain Model

### 4.1 Vendors / Contacts

Single `vendors` table for people and organizations.

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER | Primary key |
| `name` | STRING | Required, unique |
| `role` | STRING | `vendor`, `contact`, or `both` |
| `kind` | STRING | `org` or `person` |
| `organization_id` | INTEGER | FK → `vendors.id` (nullable) |
| `meta` | JSON | Structured data (`email`, `phone`) |
| `created_at` | TIMESTAMP | Creation time |

**Contacts API:** `/app/contacts` facades onto `vendors`. Duplicate name POST merges with `role='both'`.

### 4.2 Items

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER | Primary key |
| `name` | STRING | Required |
| `sku` | STRING | Nullable |
| `vendor_id` | INTEGER | FK → `vendors.id` (nullable) |
| `dimension` | STRING | Required: `length`, `area`, `volume`, `weight`, `count` |
| `quantity_int` | INTEGER | On-hand in base units |
| `uom` | STRING | Unit of measure code |
| `price` | FLOAT | Current unit price |
| `item_type` | STRING | `product`, `material`, `component` |
| `notes` | TEXT | Nullable |
| `created_at` | TIMESTAMP | Creation time |

**Base Units:**
- Length: mm
- Area: mm²
- Volume: mm³ (ml = cm³)
- Weight: mg
- Count: milli-units (1 ea = 1000 base)

### 4.3 Ledger — Batches & Movements

#### item_batches

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER | Primary key |
| `item_id` | INTEGER | FK → `items.id` |
| `qty_remaining` | INTEGER | Remaining quantity in base units |
| `unit_cost_cents` | INTEGER | Cost per unit in cents |
| `created_at` | TIMESTAMP | FIFO ordering anchor |

#### item_movements

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER | Primary key |
| `item_id` | INTEGER | FK → `items.id` |
| `batch_id` | INTEGER | FK → `item_batches.id` (nullable) |
| `qty_change` | INTEGER | Positive = in, negative = out |
| `unit_cost_cents` | INTEGER | Cost per unit in cents |
| `source_kind` | STRING | `purchase`, `consume`, `manufacturing`, `adjustment`, `sold`, `loss`, `theft`, `other` |
| `source_id` | STRING | Upstream entity reference |
| `is_oversold` | INTEGER | 0 or 1 flag |
| `created_at` | TIMESTAMP | Movement time |

**FIFO Invariants:**
- Purchases create a batch + positive movement.
- Consumes create negative movements from oldest batch first.
- Valuation = Σ(qty_remaining × unit_cost_cents) across open batches.
- Active batch = `qty_remaining > 0`.

### 4.4 Manufacturing — Recipes & Runs

#### recipes

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER | Primary key |
| `name` | STRING | Required |
| `code` | STRING | Nullable, unique when non-null (reserved) |
| `output_item_id` | INTEGER | FK → `items.id` |
| `notes` | TEXT | Nullable |
| `archived` | BOOLEAN | Default false |
| `created_at` | TIMESTAMP | Creation time |
| `updated_at` | TIMESTAMP | Last update |

#### recipe_items

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER | Primary key |
| `recipe_id` | INTEGER | FK → `recipes.id` |
| `item_id` | INTEGER | FK → `items.id` |
| `qty_required` | INTEGER | Required quantity in base units |
| `optional` | BOOLEAN | Default false |
| `created_at` | TIMESTAMP | Creation time |

#### manufacturing_runs

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER | Primary key |
| `recipe_id` | INTEGER | FK → `recipes.id` (nullable for ad-hoc) |
| `output_item_id` | INTEGER | FK → `items.id` |
| `output_qty` | INTEGER | Produced quantity in base units |
| `status` | STRING | `pending`, `completed`, `failed_insufficient_stock`, `failed_error` |
| `created_at` | TIMESTAMP | Creation time |
| `executed_at` | TIMESTAMP | Execution time (nullable) |
| `notes` | TEXT | Nullable |
| `meta` | JSON | Nullable |

**Manufacturing Invariants:**
- Runs never oversell (`is_oversold=0` always).
- Insufficient stock → HTTP 400, no movements, `status=failed_insufficient_stock`.
- All component consumes and output creation are atomic (single transaction).
- Output unit cost = total consumed cost / output qty (round half-up).
- Optional components never block runs; skipped if insufficient.

**Capacity Calculation:**
```
capacity_per_component = floor(on_hand / qty_required)
recipe_capacity = min(capacity_per_component) across required components
```

---

## 5. API Endpoints

### 5.1 Session & Health

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/session/token` | Returns session token, sets cookie |
| GET | `/health` | Returns `{ "ok": true, "version": "<VERSION>" }` |
| GET | `/health/detailed` | Diagnostics (404 unless `BUS_DEV=1`) |
| GET | `/openapi.json` | API schema (public) |

### 5.2 Items

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/app/items` | List all items |
| GET | `/app/items/{id}` | Get item detail |
| POST | `/app/items` | Create item |
| PUT | `/app/items/{id}` | Update item |
| DELETE | `/app/items/{id}` | Delete item |

### 5.3 Ledger

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/app/purchase` | Stock-in (creates batch + movement) |
| POST | `/app/consume` | FIFO consume |
| POST | `/app/ledger/adjust` | Positive/negative adjustment |
| POST | `/app/stock/out` | Remove stock with reason (`sold`, `loss`, `theft`, `other`) |
| GET | `/app/ledger/movements` | Recent movements |
| GET | `/app/logs` | Ledger-based history (cursor pagination via `cursor_id`) |

### 5.4 Vendors / Contacts

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/app/vendors` | List vendors |
| POST | `/app/vendors` | Create vendor |
| PUT | `/app/vendors/{id}` | Update vendor |
| DELETE | `/app/vendors/{id}` | Delete vendor |
| GET | `/app/contacts` | List contacts (facades vendors) |
| POST | `/app/contacts` | Create/merge contact |
| PUT | `/app/contacts/{id}` | Update contact |
| DELETE | `/app/contacts/{id}` | Delete contact |

### 5.5 Recipes

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/app/recipes` | List recipes |
| GET | `/app/recipes/{id}` | Get recipe detail |
| POST | `/app/recipes` | Create recipe |
| PUT | `/app/recipes/{id}` | Full document update |
| DELETE | `/app/recipes/{id}` | Delete recipe |

### 5.6 Manufacturing

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/app/manufacturing/run` | Execute single production run |
| GET | `/app/manufacturing/runs` | List runs |
| GET | `/app/manufacturing/runs/{id}` | Get run detail |

### 5.7 Backup & Restore

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/app/export-db` | Export encrypted backup |
| POST | `/app/db/import/preview` | Preview restore (validate, return counts) |
| POST | `/app/db/import/commit` | Commit restore (atomic replace) |

### 5.8 Config

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/app/config` | Get current config |
| POST | `/app/config` | Update config (returns `restart_required`) |
| GET | `/app/business_profile` | Get business profile |
| POST | `/app/business_profile` | Update business profile |

### 5.9 Dev Endpoints (BUS_DEV=1 only)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/dev/*` | Various diagnostics (404 in production) |

---

## 6. UI Routes

### 6.1 Canonical Routes

| Route | Screen |
|-------|--------|
| `#/home` | Dashboard |
| `#/inventory` | Items list |
| `#/inventory/<id>` | Item detail |
| `#/contacts` | Vendors/contacts list |
| `#/contacts/<id>` | Contact detail |
| `#/recipes` | Recipes list |
| `#/recipes/<id>` | Recipe detail |
| `#/runs` | Manufacturing runs |
| `#/runs/<id>` | Run detail |
| `#/import` | Import/export & backup |
| `#/settings` | Settings |

### 6.2 Aliases

| Alias | Target |
|-------|--------|
| `#/dashboard` | `#/home` |
| `#/items` | `#/inventory` |
| `#/vendors` | `#/contacts` |

### 6.3 Sidebar Navigation

1. Dashboard → `#/home`
2. Items → `#/inventory`
3. Vendors → `#/contacts`
4. Manufacturing → Recipes → `#/recipes`
5. Manufacturing → Runs → `#/runs`
6. Files / Import & Export → `#/import`
7. Settings → `#/settings`

### 6.4 Inventory UI

**Table Columns:** Name | Quantity | Price | Vendor | Location

- Quantity shows sum of active batches in item's display unit.
- Price shows FIFO price (oldest batch unit cost).
- Row click expands inline detail panel with batches and edit/delete actions.
- Add/Edit uses Shallow/Deep pattern (Name, Qty, Price, Location visible; SKU, Vendor, Type, Notes expandable).

### 6.5 Manufacturing UI

- **Recipes page:** Master-detail for recipe definition.
- **Manufacturing page:** Run production (select recipe, confirm, execute).
- **Recent Runs panel:** Shows last 30 days (Recipe | Date | Time).
- Single-run execution (no multiplier input).

### 6.6 Error Handling

- Non-2xx responses always surface visible errors.
- HTTP 400: Keep dialog open, show field errors.
- HTTP 5xx/timeout: Show persistent error banner.
- Error format: `{ "detail": "message" }` or `{ "detail": [...] }`.

---

## 7. Data & Journals

### 7.1 Authority

- **DB is single source of truth** for all state.
- Journals are receipts, never read to compute values.

### 7.2 Journal Files

| File | Contents |
|------|----------|
| `inventory.jsonl` | Purchases, consumes, adjustments, stock-out |
| `manufacturing.jsonl` | Manufacturing runs |
| `bulk_import.jsonl` | Bulk import operations |
| `plugin_audit.jsonl` | Plugin actions |

### 7.3 Write Order

1. Apply DB changes in transaction.
2. If commit succeeds, append journal line.
3. If commit fails, no journal written.

### 7.4 Adjustments

**Positive (found stock):**
- New batch with `unit_cost_cents=0`.
- Positive movement with `source_kind=adjustment`.

**Negative (lost/damaged):**
- FIFO consume from oldest batches.
- HTTP 400 if insufficient stock.
- Records actual batch costs consumed.

---

## 8. Backup & Restore

### 8.1 Export

- Encrypts `app.db` using AES-GCM with user password.
- Key derived via KDF (PBKDF2/Argon2id).
- Writes to `%LOCALAPPDATA%\BUSCore\exports`.

### 8.2 Restore

**Preview:** Decrypts, validates schema, returns metadata.

**Commit Sequence:**
1. Acquire restore lock, enter maintenance mode.
2. Decrypt backup to temp file.
3. WAL checkpoint current DB.
4. Stop indexer, dispose engine, GC handles.
5. Atomic `os.replace` with retry.
6. Archive journals (`*.jsonl` → `*.pre-restore-<timestamp>`).
7. Recreate empty journal files.
8. Return `{ ok: true, restart_required: true }`.

**Schema Compatibility:** Refuses backups with incompatible schema version.

---

## 9. Config

### 9.1 Schema

```json
{
  "launcher": {
    "auto_start_in_tray": false,
    "close_to_tray": false
  },
  "ui": {
    "theme": "system"
  },
  "backup": {
    "default_directory": "%LOCALAPPDATA%\\BUSCore\\exports"
  },
  "dev": {
    "writes_enabled": false
  }
}
```

### 9.2 Launcher Behavior (Windows)

**Production Mode (default):**
- Hides console window.
- Runs uvicorn in daemon thread.
- Shows system tray icon.
- Opens browser to `/ui/shell.html#/home`.

**Dev Mode (`BUS_DEV=1` or `--dev`):**
- Console visible.
- Uvicorn blocking mode.
- No system tray.

**Tray Menu:**
- Open Dashboard
- Show Console
- Quit BUS Core

**Close Behavior:**
- `close_to_tray=true` → Hide to tray.
- `close_to_tray=false` → Full quit.

---

## 10. Testing & Smoke

### 10.1 Authentication

- Cookie-based session via `GET /session/token`.
- All protected routes require valid session cookie.

### 10.2 Smoke Stages

1. Session + health checks
2. Item CRUD
3. Contacts/Vendors CRUD
4. FIFO stock-in (two cost layers)
5. FIFO consume (cross-layer)
6. Recipe creation
7. Manufacturing run (success)
8. Manufacturing run (failure - insufficient stock)
9. Adjustments (positive/negative)
10. Backup export/restore
11. Integrity checks (no negative qty, no unexpected oversold)
12. Cleanup

### 10.3 Success Criteria

- Exit code 0 = all pass.
- Exit code 1 = any failure.
- All CRUD returns HTTP 200.
- Manufacturing insufficient stock returns HTTP 400 with `shortages`.

---

## 11. Dev Mode & Security

### 11.1 Dev Flag

- `BUS_DEV` environment variable.
- Only `BUS_DEV="1"` enables dev mode.
- Any other value or unset = production.

### 11.2 Production Behavior

- `/dev/*` routes return 404.
- `/health/detailed` returns 404.
- Error responses sanitized (no stack traces).

### 11.3 Dev Behavior

- `/dev/*` routes accessible (require auth).
- Full exception details.
- `/health/detailed` available.

---

## 12. Repository & Legal

- **License:** AGPL-3.0 with SPDX headers.
- **Brand Assets:** `Flat-Dark.png`, `Glow-Hero.png` (root, tracked, no LFS).
- **Favicon:** `ui/favicon.svg` (canonical source).

---

## Changelog

### v0.10.0-beta — 2025-12-14

- Consolidated from v0.8.8 with all session deltas integrated.
- Removed speculative content and "unknowns" sections.
- Removed historical delta blocks (facts incorporated).
- Quantities standardized to INTEGER base units with dimension system.
- FIFO ledger is sole authority for stock and valuation.
- Manufacturing single-run UI (no multiplier).
- Logs page reads from ledger movements (not journals).
- Stock-out endpoint with reason codes.
- Cookie-only authentication (header tokens removed).
- Production mode launcher with hidden console and system tray.
- Encrypted backup/restore with journal archiving.

---

**End of Source of Truth.**
