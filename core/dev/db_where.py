# Copyright (C) 2025 BUS Core Authors
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations
from fastapi import APIRouter, Depends
from sqlalchemy import text
from core.appdb.engine import DB_PATH, get_engine
from core.api.utils.devguard import require_dev

router = APIRouter(prefix="/dev", tags=["dev"], dependencies=[Depends(require_dev)])

@router.get("/db/where")
def dev_db_where():
    pragma = []
    try:
        engine = get_engine()
        with engine.connect() as conn:
            rows = conn.execute(text("PRAGMA database_list;")).all()
            pragma = [[str(c) for c in r] for r in rows]
    except Exception:
        pragma = [["error", "db_probe_failed"]]
    return {
        "engine_url": str(get_engine().url),
        "db_path": str(DB_PATH),
        "exists": DB_PATH.exists(),
        "pragma_database_list": pragma,
    }
