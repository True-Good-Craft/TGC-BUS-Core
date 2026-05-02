# Copyright (C) 2025 BUS Core Authors
# SPDX-License-Identifier: AGPL-3.0-or-later

# core/appdb/migrations/2025_12_01_ledger_batches.py
from contextlib import contextmanager
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

def table_exists(cur, name: str) -> bool:
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,))
    return cur.fetchone() is not None

def create_tables():
    with conn() as con:
        cur = con.cursor()
        # item_batches
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS item_batches (
                id INTEGER PRIMARY KEY,
                item_id INTEGER NOT NULL REFERENCES items(id),
                qty_initial INTEGER NOT NULL CHECK (qty_initial >= 0),
                qty_remaining INTEGER NOT NULL CHECK (qty_remaining >= 0),
                unit_cost_cents INTEGER NOT NULL CHECK (unit_cost_cents >= 0),
                source_kind TEXT NOT NULL,
                source_id TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS ix_item_batches_item ON item_batches(item_id, created_at)")
        cur.execute("CREATE INDEX IF NOT EXISTS ix_item_batches_remaining ON item_batches(item_id, qty_remaining)")
        # item_movements
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS item_movements (
                id INTEGER PRIMARY KEY,
                item_id INTEGER NOT NULL REFERENCES items(id),
                batch_id INTEGER REFERENCES item_batches(id),
                qty_change INTEGER NOT NULL,
                unit_cost_cents INTEGER DEFAULT 0,
                source_kind TEXT NOT NULL,
                source_id TEXT,
                is_oversold BOOLEAN DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS ix_item_movements_item ON item_movements(item_id, created_at)")
        cur.execute("CREATE INDEX IF NOT EXISTS ix_item_movements_batch ON item_movements(batch_id)")
        # protect harvester idempotency (if source_id provided)
        cur.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS ux_movements_source ON item_movements(source_kind, source_id, item_id, qty_change) WHERE source_id IS NOT NULL"
        )

if __name__ == "__main__":
    create_tables()
    print(f"Ledger migration applied to {DB_PATH} at {time.strftime('%Y-%m-%d %H:%M:%S')}")

