# Copyright (C) 2025 BUS Core Authors
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations
import os
import sqlite3, time
from contextlib import contextmanager
from typing import Any, Dict

from core.appdb.paths import resolve_db_path

DB_PATH = resolve_db_path()

@contextmanager
def conn():
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    try:
        yield con
    finally:
        con.commit(); con.close()

def ensure_schema() -> Dict[str, Any]:
    """
    v1 baseline schema (no legacy qty/unit in DB).
    Canonical stock = items.qty_stored (+ items.uom).
    Safe to run on every startup.
    """
    created = {
        "items": False,
        "item_batches": False,
        "item_movements": False,
        "recipes": False,
        "recipe_items": False,
        "manufacturing_runs": False,
    }

    with conn() as con:
        cur = con.cursor()

        def col_exists(table: str, column: str) -> bool:
            cur.execute("PRAGMA table_info(%s)" % table)
            return any(r[1] == column for r in cur.fetchall())

        # ITEMS (no qty/unit legacy cols)
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='items'")
        if not cur.fetchone():
            cur.execute(
                """
            CREATE TABLE items (
                id INTEGER PRIMARY KEY,
                vendor_id INTEGER,
                sku TEXT,
                name TEXT NOT NULL,
                uom TEXT NOT NULL DEFAULT 'ea',          -- display unit (legacy)
                dimension TEXT NOT NULL DEFAULT 'count',
                qty_stored INTEGER NOT NULL DEFAULT 0,   -- canonical on-hand (int)
                price REAL DEFAULT 0,
                is_product BOOLEAN NOT NULL DEFAULT 0,
                is_archived BOOLEAN NOT NULL DEFAULT 0,
                notes TEXT,
                item_type TEXT,
                location TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
            )
            created["items"] = True
        else:
            for col, ddl in [
                (
                    "dimension",
                    "ALTER TABLE items ADD COLUMN dimension TEXT NOT NULL DEFAULT 'count'",
                ),
                (
                    "is_product",
                    "ALTER TABLE items ADD COLUMN is_product BOOLEAN NOT NULL DEFAULT 0",
                ),
                (
                    "is_archived",
                    "ALTER TABLE items ADD COLUMN is_archived BOOLEAN NOT NULL DEFAULT 0",
                ),
            ]:
                if not col_exists("items", col):
                    cur.execute(ddl)

        # ITEM BATCHES (cost layers)
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='item_batches'")
        if not cur.fetchone():
            cur.execute(
                """
            CREATE TABLE item_batches (
                id INTEGER PRIMARY KEY,
                item_id INTEGER NOT NULL REFERENCES items(id),
                qty_initial INTEGER NOT NULL,
                qty_remaining INTEGER NOT NULL,
                unit_cost_cents INTEGER NOT NULL,
                source_kind TEXT NOT NULL,
                source_id TEXT,
                is_oversold BOOLEAN DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
            )
            created["item_batches"] = True
        else:
            if not col_exists("item_batches", "is_oversold"):
                cur.execute("ALTER TABLE item_batches ADD COLUMN is_oversold BOOLEAN DEFAULT 0")

        # MOVEMENTS (physical ledger)
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='item_movements'")
        if not cur.fetchone():
            cur.execute(
                """
            CREATE TABLE item_movements (
                id INTEGER PRIMARY KEY,
                item_id INTEGER NOT NULL REFERENCES items(id),
                batch_id INTEGER REFERENCES item_batches(id),
                qty_change INTEGER NOT NULL,               -- +in / -out (physical)
                unit_cost_cents INTEGER DEFAULT 0,         -- snapshot
                source_kind TEXT NOT NULL,
                source_id TEXT,
                is_oversold BOOLEAN DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
            )
            created["item_movements"] = True
        else:
            if not col_exists("item_movements", "is_oversold"):
                cur.execute("ALTER TABLE item_movements ADD COLUMN is_oversold BOOLEAN DEFAULT 0")

        # RECIPES
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='recipes'")
        if not cur.fetchone():
            cur.execute(
                """
            CREATE TABLE recipes (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                code TEXT,
                output_item_id INTEGER NOT NULL,
                output_qty INTEGER NOT NULL DEFAULT 1,
                archived BOOLEAN NOT NULL DEFAULT 0,
                notes TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
                """
            )
            created["recipes"] = True
        else:
            for col, ddl in [
                ("code", "ALTER TABLE recipes ADD COLUMN code TEXT"),
                ("output_item_id", "ALTER TABLE recipes ADD COLUMN output_item_id INTEGER NOT NULL DEFAULT 0"),
                ("output_qty", "ALTER TABLE recipes ADD COLUMN output_qty INTEGER NOT NULL DEFAULT 1"),
                (
                    "archived",
                    "ALTER TABLE recipes ADD COLUMN archived BOOLEAN NOT NULL DEFAULT 0",
                ),
                ("created_at", "ALTER TABLE recipes ADD COLUMN created_at DATETIME DEFAULT CURRENT_TIMESTAMP"),
                ("updated_at", "ALTER TABLE recipes ADD COLUMN updated_at DATETIME DEFAULT CURRENT_TIMESTAMP"),
            ]:
                if not col_exists("recipes", col) and not (
                    col == "archived" and col_exists("recipes", "is_archived")
                ):
                    cur.execute(ddl)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_recipes_code ON recipes(code)")

        # RECIPE ITEMS
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='recipe_items'")
        if not cur.fetchone():
            cur.execute(
                """
            CREATE TABLE recipe_items (
                id INTEGER PRIMARY KEY,
                recipe_id INTEGER NOT NULL REFERENCES recipes(id),
                item_id INTEGER NOT NULL REFERENCES items(id),
                qty_required INTEGER NOT NULL,
                is_optional BOOLEAN NOT NULL DEFAULT 0,
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
            )
            created["recipe_items"] = True
        else:
            for col, ddl in [
                ("qty_required", "ALTER TABLE recipe_items ADD COLUMN qty_required INTEGER NOT NULL DEFAULT 0"),
                ("is_optional", "ALTER TABLE recipe_items ADD COLUMN is_optional BOOLEAN NOT NULL DEFAULT 0"),
                ("sort_order", "ALTER TABLE recipe_items ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0"),
                ("created_at", "ALTER TABLE recipe_items ADD COLUMN created_at DATETIME DEFAULT CURRENT_TIMESTAMP"),
                ("updated_at", "ALTER TABLE recipe_items ADD COLUMN updated_at DATETIME DEFAULT CURRENT_TIMESTAMP"),
            ]:
                if not col_exists("recipe_items", col):
                    cur.execute(ddl)

        # MANUFACTURING RUNS
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='manufacturing_runs'")
        if not cur.fetchone():
            cur.execute(
                """
            CREATE TABLE manufacturing_runs (
                id INTEGER PRIMARY KEY,
                recipe_id INTEGER,
                output_item_id INTEGER NOT NULL,
                output_qty INTEGER NOT NULL,
                status TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                executed_at DATETIME,
                notes TEXT,
                meta TEXT
            )
            """
            )
            created["manufacturing_runs"] = True

        # Helpful indexes (idempotent)
        cur.execute(
            "CREATE INDEX IF NOT EXISTS items_is_archived_idx ON items(is_archived)"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_item_batches_item_created ON item_batches (item_id, created_at)"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_item_batches_item_qtyrem ON item_batches (item_id, qty_remaining)"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_item_movements_item_created ON item_movements (item_id, created_at)"
        )

    return {"ok": True, "path": DB_PATH, "created": created, "ts": time.strftime("%Y-%m-%d %H:%M:%S")}

if __name__ == "__main__":
    print(ensure_schema())
