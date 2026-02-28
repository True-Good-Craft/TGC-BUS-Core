# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from typing import Dict, List

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import text
from sqlalchemy.orm import Session

from core.appdb.engine import get_session
from core.appdb.models import CashEvent, Item, ItemMovement, Vendor
from core.appdb.models_recipes import ManufacturingRun, Recipe
from tgc.security import require_token_ctx

router = APIRouter(prefix="/system", tags=["system"])

COUNT_KEYS = (
    "items",
    "vendors",
    "recipes",
    "movements",
    "cash_events",
    "manufacturing_runs",
)


@router.get("/state")
def get_system_state(
    request: Request,
    db: Session = Depends(get_session),
    _token: str = Depends(require_token_ctx),
) -> Dict[str, object]:
    count_queries = {
        "items": lambda: db.query(Item).count(),
        "vendors": lambda: db.query(Vendor).count(),
        "recipes": lambda: db.query(Recipe).count(),
        "movements": lambda: db.query(ItemMovement).count(),
        "cash_events": lambda: db.query(CashEvent).count(),
        "manufacturing_runs": lambda: db.query(ManufacturingRun).count(),
    }
    try:
        counts = {key: int(count_queries[key]()) for key in COUNT_KEYS}
        version = request.app.version if getattr(request.app, "version", None) else "unknown"
        schema_version = "baseline"
        table_row = db.execute(
            text(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name IN ('alembic_version','schema_migrations') "
                "ORDER BY CASE name WHEN 'alembic_version' THEN 0 ELSE 1 END LIMIT 1"
            )
        ).fetchone()
        if table_row:
            table_name = str(table_row[0])
            if table_name == "alembic_version":
                ver_row = db.execute(text("SELECT version_num FROM alembic_version LIMIT 1")).fetchone()
                if ver_row and ver_row[0] is not None:
                    schema_version = str(ver_row[0])
            elif table_name == "schema_migrations":
                ver_row = db.execute(text("SELECT version FROM schema_migrations ORDER BY version DESC LIMIT 1")).fetchone()
                if ver_row and ver_row[0] is not None:
                    schema_version = str(ver_row[0])
    except Exception as exc:
        raise HTTPException(status_code=500, detail="system_state_unavailable") from exc

    is_first_run = all(int(counts[key]) == 0 for key in COUNT_KEYS)
    basis: List[str] = [key for key in COUNT_KEYS if int(counts[key]) > 0]
    status = "ready"
    if is_first_run:
        status = "empty"
    elif str(schema_version) == "baseline":
        status = "needs_migration"

    return {
        "is_first_run": is_first_run,
        "counts": counts,
        "demo_allowed": is_first_run,
        "basis": basis,
        "build": {
            "version": str(version),
            "schema_version": str(schema_version),
        },
        "status": status,
    }
