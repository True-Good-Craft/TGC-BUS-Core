# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from core.api.read_models import get_finance_summary, get_inventory_value, get_units_produced
from core.appdb.engine import get_session


router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def _parse_iso8601(ts: str) -> datetime:
    parsed = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _to_utc_z(dt: datetime) -> str:
    return dt.replace(microsecond=0, tzinfo=timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


@router.get("/summary")
def dashboard_summary(
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
    db: Session = Depends(get_session),
):
    try:
        end_dt = _parse_iso8601(end) if end else datetime.utcnow()
        start_dt = _parse_iso8601(start) if start else (end_dt - timedelta(days=30))
    except Exception:
        raise HTTPException(status_code=400, detail="invalid_iso8601_datetime")

    finance = get_finance_summary(db, start_dt=start_dt, end_dt=end_dt)

    return {
        "window": {
            "start": _to_utc_z(start_dt),
            "end": _to_utc_z(end_dt),
        },
        "inventory_value_cents": get_inventory_value(db),
        "units_produced": get_units_produced(db, start_dt=start_dt, end_dt=end_dt),
        "gross_revenue_cents": finance.gross_revenue_cents,
        "refunds_cents": finance.refunds_cents,
        "net_revenue_cents": finance.net_revenue_cents,
        "cogs_cents": finance.cogs_cents,
        "gross_profit_cents": finance.gross_profit_cents,
        "margin_percent": finance.margin_percent,
    }
