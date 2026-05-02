# SPDX-License-Identifier: AGPL-3.0-or-later
# TGC BUS Core (Business Utility System Core)
# Copyright (C) 2025 True Good Craft
#
# This file is part of TGC BUS Core.
#
# TGC BUS Core is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# TGC BUS Core is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with TGC BUS Core.  If not, see <https://www.gnu.org/licenses/>.

import json
import sqlite3
from typing import Optional

from core.config.paths import APP_DIR

from .model import Plan

DB_FILE = APP_DIR / "plans.db"


def _init():
    con = sqlite3.connect(DB_FILE)
    cur = con.cursor()
    cur.execute(
        """
    CREATE TABLE IF NOT EXISTS plans(
      id TEXT PRIMARY KEY,
      created_at TEXT NOT NULL,
      source TEXT NOT NULL,
      title TEXT NOT NULL,
      note TEXT,
      status TEXT NOT NULL,
      stats_json TEXT NOT NULL,
      actions_json TEXT NOT NULL
    )"""
    )
    con.commit()
    con.close()


_init()


def save_plan(plan: Plan) -> None:
    con = sqlite3.connect(DB_FILE)
    cur = con.cursor()
    cur.execute(
        """
      INSERT OR REPLACE INTO plans(id, created_at, source, title, note, status, stats_json, actions_json)
      VALUES(?,?,?,?,?,?,?,?)
    """,
        (
            plan.id,
            plan.created_at.isoformat(),
            plan.source,
            plan.title,
            plan.note or "",
            plan.status.value,
            json.dumps(plan.stats),
            json.dumps([a.model_dump() for a in plan.actions]),
        ),
    )
    con.commit()
    con.close()


def get_plan(plan_id: str) -> Optional[Plan]:
    con = sqlite3.connect(DB_FILE)
    cur = con.cursor()
    row = cur.execute(
        "SELECT id, created_at, source, title, note, status, stats_json, actions_json FROM plans WHERE id=?",
        (plan_id,),
    ).fetchone()
    con.close()
    if not row:
        return None
    import datetime
    import json as _json

    from .model import Action as _Action
    from .model import Plan as _Plan
    from .model import PlanStatus as _PS

    actions = [_Action(**d) for d in _json.loads(row[7])]
    return _Plan(
        id=row[0],
        created_at=datetime.datetime.fromisoformat(row[1]),
        source=row[2],
        title=row[3],
        note=row[4] or None,
        status=_PS(row[5]),
        stats=_json.loads(row[6]),
        actions=actions,
    )


def list_plans(limit: int = 100, offset: int = 0):
    con = sqlite3.connect(DB_FILE)
    cur = con.cursor()
    rows = cur.execute(
        "SELECT id, created_at, source, title, note, status FROM plans ORDER BY created_at DESC LIMIT ? OFFSET ?",
        (limit, offset),
    ).fetchall()
    con.close()
    return [
        {"id": r[0], "created_at": r[1], "source": r[2], "title": r[3], "note": r[4], "status": r[5]}
        for r in rows
    ]
