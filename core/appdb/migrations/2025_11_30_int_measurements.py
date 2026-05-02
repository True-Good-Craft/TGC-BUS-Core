# Copyright (C) 2025 BUS Core Authors
# SPDX-License-Identifier: AGPL-3.0-or-later

from contextlib import contextmanager
from typing import Set
import sqlite3, os, time

from core.appdb.paths import resolve_db_path

DB_PATH = resolve_db_path()

@contextmanager
def conn():
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    try:
        yield con
    finally:
        con.commit()
        con.close()

def table_exists(cur, table: str) -> bool:
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
    return cur.fetchone() is not None

def columns(cur, table: str) -> Set[str]:
    cur.execute(f"PRAGMA table_info({table})")
    return {row[1] for row in cur.fetchall()}

def apply():
    with conn() as con:
        cur = con.cursor()

        # Ensure base items table exists (with legacy cols for backfill)
        if not table_exists(cur, "items"):
            cur.execute(
                """
                CREATE TABLE items (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    uom TEXT NOT NULL DEFAULT 'ea',
                    qty_stored INTEGER NOT NULL DEFAULT 0,
                    qty REAL NULL,   -- legacy (read-only)
                    unit TEXT NULL   -- legacy (read-only)
                )
                """
            )

        # Add canonical columns if missing (idempotent)
        item_cols = columns(cur, "items")
        if "uom" not in item_cols:
            cur.execute("ALTER TABLE items ADD COLUMN uom TEXT NOT NULL DEFAULT 'ea'")
        if "qty_stored" not in item_cols:
            cur.execute("ALTER TABLE items ADD COLUMN qty_stored INTEGER NOT NULL DEFAULT 0")

        # Backfill from legacy qty/unit when present
        item_cols = columns(cur, "items")
        if "qty" in item_cols:
            try:
                cur.execute("SELECT id, qty, unit FROM items")
                for _id, qty, unit in cur.fetchall():
                    if qty is None:
                        continue
                    uom = (unit or 'ea')
                    if uom not in ('ea','g','mm','mm2','mm3'):
                        uom = 'ea'
                    stored = int(round(qty)) if uom == 'ea' else int(round(qty * 100))
                    cur.execute("UPDATE items SET uom=?, qty_stored=? WHERE id=?", (uom, stored, _id))
            except sqlite3.OperationalError:  # Compatibility fallback: legacy qty columns may be absent.
                pass

        # Manufacturing schema
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS recipes (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                notes TEXT
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS recipe_items (
                id INTEGER PRIMARY KEY,
                recipe_id INTEGER NOT NULL,
                item_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                qty_stored INTEGER NOT NULL,
                FOREIGN KEY(recipe_id) REFERENCES recipes(id) ON DELETE CASCADE,
                FOREIGN KEY(item_id) REFERENCES items(id)
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS ix_recipe_items_recipe_id ON recipe_items(recipe_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS ix_items_uom ON items(uom)")

if __name__ == "__main__":
    apply()
    print(f"Migration 2025_11_30_int_measurements applied to {DB_PATH} at {time.strftime('%Y-%m-%d %H:%M:%S')}")
