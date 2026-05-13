from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc
from sqlalchemy.orm import Session

from core.appdb.engine import get_session
from core.appdb.models import Item, ItemMovement
from core.auth.dependencies import require_permission
from core.auth.permissions import PERMISSION_LOGS_READ
from tgc.security import require_token_ctx

router = APIRouter(prefix="/app", tags=["logs"])
public_router = APIRouter(prefix="/app", tags=["logs"])


def _to_iso(dt: datetime | None) -> str:
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()
    return datetime.now(timezone.utc).isoformat()


@router.get("/logs", operation_id="list_app_logs")
@public_router.get("/logs", operation_id="list_public_app_logs")
def list_logs(
    limit: int = Query(200, ge=10, le=1000),
    cursor_id: int | None = Query(None, description="Return rows with id < cursor_id"),
    item_id: int | None = None,
    db: Session = Depends(get_session),
    _permission=Depends(require_permission(PERMISSION_LOGS_READ)),
    _token: None = Depends(require_token_ctx),
):
    """Return stock-change events from the ledger (item_movements), newest first."""

    q = db.query(ItemMovement, Item).outerjoin(Item, Item.id == ItemMovement.item_id)

    if item_id is not None:
        q = q.filter(ItemMovement.item_id == int(item_id))
    if cursor_id is not None:
        q = q.filter(ItemMovement.id < int(cursor_id))

    rows = q.order_by(desc(ItemMovement.id)).limit(int(limit)).all()

    events = []
    for mov, it in rows:
        events.append(
            {
                "id": int(mov.id),
                "ts": _to_iso(getattr(mov, "created_at", None)),
                "domain": "inventory",
                "kind": mov.source_kind or "movement",
                "item_id": int(mov.item_id),
                "item_name": getattr(it, "name", None),
                "qty_change": int(mov.qty_change),
                "unit_cost_cents": int(mov.unit_cost_cents or 0),
                "batch_id": int(mov.batch_id) if mov.batch_id is not None else None,
                "is_oversold": bool(mov.is_oversold),
            }
        )

    next_cursor_id = events[-1]["id"] if len(events) == int(limit) else None
    return {"events": events, "next_cursor_id": next_cursor_id}
