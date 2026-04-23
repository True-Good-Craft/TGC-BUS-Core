# Copyright (C) 2025 BUS Core Authors
# SPDX-License-Identifier: AGPL-3.0-or-later

# core/ledger/health.py
import sqlite3
from core.appdb.paths import resolve_db_path
DB_PATH = resolve_db_path()

def _select_on_hand_column(cur) -> str | None:
    cur.execute("PRAGMA table_info(items)")
    cols = {r[1] for r in cur.fetchall()}
    if "qty" in cols:
        return "qty"
    if "qty_stored" in cols:
        return "qty_stored"
    return None


def health_summary():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    try:
        qty_col = _select_on_hand_column(cur)
        if qty_col is None:
            return {"desync": True, "problems": [{"reason": "No qty column in items"}]}

        if qty_col == "qty":
            query = """
            SELECT i.id, i.name, i.qty AS onhand,
                   IFNULL((SELECT SUM(qty_remaining) FROM item_batches b WHERE b.item_id=i.id), 0.0) AS valued_qty
            FROM items i
            """
        else:
            query = """
            SELECT i.id, i.name, i.qty_stored AS onhand,
                   IFNULL((SELECT SUM(qty_remaining) FROM item_batches b WHERE b.item_id=i.id), 0.0) AS valued_qty
            FROM items i
            """
        cur.execute(query)
        problems = []
        for iid, name, onhand, valued in cur.fetchall():
            if round(float(onhand or 0), 4) != round(float(valued or 0), 4):
                problems.append({"item_id": iid, "name": name, "items_qty": onhand, "batch_sum": valued})
        return {"desync": len(problems) > 0, "problems": problems, "using": qty_col}
    finally:
        con.close()

