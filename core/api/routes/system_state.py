# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from pathlib import Path
from typing import Dict, List

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import text
from sqlalchemy.orm import Session

from core.appdata.paths import db_path_for_mode, resolve_bus_mode, set_bus_mode
from core.appdb.engine import dispose_engine, get_engine, get_session
from core.appdb.migrate import ensure_vendors_flags
from core.appdb.models import Base, CashEvent, Item, ItemMovement, Vendor
from core.appdb.models_recipes import ManufacturingRun, Recipe
from core.auth.dependencies import require_permission
from core.auth.permissions import PERMISSION_SYSTEM_ADMIN, PERMISSION_SYSTEM_READ
from core.config.writes import require_writes
from core.version import INTERNAL_VERSION
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
    _permission=Depends(require_permission(PERMISSION_SYSTEM_READ)),
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
        raise HTTPException(
            status_code=500,
            detail={"error": "bad_request", "message": "system_state_unavailable"},
        ) from exc

    bus_mode = resolve_bus_mode()
    demo_mode = bus_mode == "demo"
    is_first_run = all(int(counts[key]) == 0 for key in COUNT_KEYS)
    basis: List[str] = [key for key in COUNT_KEYS if int(counts[key]) > 0]
    status = "ready"
    if is_first_run:
        status = "empty"
    elif str(schema_version) == "baseline":
        status = "needs_migration"

    return {
        "bus_mode": bus_mode,
        "is_first_run": is_first_run,
        "counts": counts,
        "demo_allowed": demo_mode,
        "basis": basis,
        "build": {
            "version": str(version),
            "internal_version": str(INTERNAL_VERSION),
            "schema_version": str(schema_version),
        },
        "status": status,
    }


@router.post("/start-fresh")
def start_fresh_shop(
    _permission=Depends(require_permission(PERMISSION_SYSTEM_ADMIN)),
    _token: str = Depends(require_token_ctx),
    _writes: None = Depends(require_writes),
) -> Dict[str, object]:
    try:
        set_bus_mode("prod")
        prod_db = db_path_for_mode("prod")

        dispose_engine()

        for suffix in ("", "-wal", "-shm", "-journal"):
            candidate = Path(f"{prod_db}{suffix}")
            candidate.unlink(missing_ok=True)

        engine = get_engine()
        Base.metadata.create_all(bind=engine)
        ensure_vendors_flags(engine)
        dispose_engine()
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={"error": "bad_request", "message": "start_fresh_failed"},
        ) from exc

    return {
        "ok": True,
        "restart_required": True,
    }


