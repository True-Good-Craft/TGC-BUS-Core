# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from core.appdb.engine import get_session
from core.api.quantity_contract import normalize_quantity_to_base_int
from core.api.cost_contract import normalize_cost_to_base_cents
from core.appdb.ledger import add_batch
from core.appdb.models import CashEvent, ItemMovement
from core.services.finance_service import process_refund, record_expense
from core.api.read_models import get_finance_summary


router = APIRouter(prefix="/finance", tags=["finance"])


class ExpenseIn(BaseModel):
    amount_cents: int = Field(gt=0)
    category: Optional[str] = None
    notes: Optional[str] = None
    created_at: Optional[datetime] = None


@router.post("/expense")
def finance_expense(body: ExpenseIn, db: Session = Depends(get_session)):
    ce = record_expense(
        db,
        amount_cents=int(body.amount_cents),
        category=body.category,
        notes=body.notes,
        created_at=body.created_at,
    )
    db.commit()
    return {"ok": True, "id": int(ce.id) if ce.id is not None else None}


class RefundIn(BaseModel):
    item_id: int
    refund_amount_cents: int = Field(gt=0)
    quantity_decimal: str = Field(min_length=1)
    uom: str = Field(min_length=1)
    restock_inventory: bool
    related_source_id: Optional[str] = None
    restock_unit_cost_decimal: Optional[str] = None
    restock_cost_uom: Optional[str] = None
    category: Optional[str] = None
    notes: Optional[str] = None
    created_at: Optional[datetime] = None

    @model_validator(mode="before")
    @classmethod
    def reject_legacy_qty_base(cls, data):
        if isinstance(data, dict) and "qty_base" in data:
            raise ValueError("legacy_qty_field_not_allowed")
        if isinstance(data, dict) and "restock_unit_cost_cents" in data:
            raise ValueError("legacy_unit_cost_field_not_allowed")
        return data


@router.post("/refund")
def finance_refund(body: RefundIn, db: Session = Depends(get_session)):
    source_id = process_refund(
        db,
        item_id=int(body.item_id),
        refund_amount_cents=int(body.refund_amount_cents),
        quantity_decimal=body.quantity_decimal,
        uom=body.uom,
        restock_inventory=bool(body.restock_inventory),
        related_source_id=body.related_source_id,
        restock_unit_cost_decimal=body.restock_unit_cost_decimal,
        restock_cost_uom=body.restock_cost_uom,
        category=body.category,
        notes=body.notes,
        created_at=body.created_at,
        normalize_quantity_fn=normalize_quantity_to_base_int,
        normalize_cost_fn=normalize_cost_to_base_cents,
        add_batch_fn=add_batch,
    )
    db.commit()
    return {"ok": True, "source_id": source_id}



def _parse_iso8601(ts: str) -> datetime:
    parsed = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _to_utc_z(dt: datetime) -> str:
    return dt.replace(microsecond=0, tzinfo=timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _resolve_profit_window(db: Session, start: str | None, end: str | None, range_: str | None):
    now = datetime.utcnow()

    if start and end:
        return _parse_iso8601(start), _parse_iso8601(end)

    if range_:
        key = str(range_).strip().lower()
        if key == "7d":
            return now - timedelta(days=7), now
        if key == "30d":
            return now - timedelta(days=30), now
        if key == "90d":
            return now - timedelta(days=90), now
        if key == "ytd":
            return datetime(now.year, 1, 1, 0, 0, 0), now
        if key == "all":
            earliest = db.query(CashEvent.created_at).order_by(CashEvent.created_at.asc()).first()
            if earliest and earliest[0]:
                return earliest[0], now
            return now - timedelta(days=30), now
        raise HTTPException(status_code=400, detail="invalid_range")

    return now - timedelta(days=30), now


@router.get("/profit")
def finance_profit(
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
    range_: str | None = Query(default=None, alias="range"),
    from_: str | None = Query(default=None, alias="from"),
    to: str | None = Query(default=None, alias="to"),
    db: Session = Depends(get_session),
):
    if (start is None and end is None) and (from_ is not None and to is not None):
        try:
            from_date = datetime.strptime(from_, "%Y-%m-%d").date()
            to_date = datetime.strptime(to, "%Y-%m-%d").date()
        except Exception:
            raise HTTPException(status_code=400, detail="invalid_date_format_expected_YYYY_MM_DD")
        start_dt = datetime(from_date.year, from_date.month, from_date.day, 0, 0, 0)
        end_dt = datetime((to_date + timedelta(days=1)).year, (to_date + timedelta(days=1)).month, (to_date + timedelta(days=1)).day, 0, 0, 0)
    else:
        try:
            start_dt, end_dt = _resolve_profit_window(db, start=start, end=end, range_=range_)
        except ValueError:
            raise HTTPException(status_code=400, detail="invalid_iso8601_datetime")

    summary = get_finance_summary(db, start_dt=start_dt, end_dt=end_dt)

    return {
        "window": {
            "start": _to_utc_z(start_dt),
            "end": _to_utc_z(end_dt),
        },
        "gross_revenue_cents": summary.gross_revenue_cents,
        "refunds_cents": summary.refunds_cents,
        "net_revenue_cents": summary.net_revenue_cents,
        "cogs_cents": summary.cogs_cents,
        "gross_profit_cents": summary.gross_profit_cents,
        "margin_percent": summary.margin_percent,
        "math": {
            "formula": "Net Revenue (Gross - Refunds) - COGS = Gross Profit",
        },
    }


@router.get("/cash-event/{source_id}")
def finance_cash_event_trace(source_id: str, db: Session = Depends(get_session)):
    event = db.query(CashEvent).filter(CashEvent.source_id == source_id).first()
    if event is None:
        raise HTTPException(status_code=404, detail="cash_event_not_found")

    linked_movements = (
        db.query(ItemMovement)
        .filter(ItemMovement.source_id == event.source_id)
        .order_by(ItemMovement.created_at.asc(), ItemMovement.id.asc())
        .all()
    )

    computed_cogs_cents = 0
    if event.kind == "sale":
        computed_cogs_cents = sum(
            abs(int(m.qty_change)) * int(m.unit_cost_cents or 0)
            for m in linked_movements
            if int(m.qty_change) < 0
        )
    net_profit_cents = int(event.amount_cents) - int(computed_cogs_cents) if event.kind == "sale" else int(event.amount_cents)

    return {
        "cash_event": {
            "id": int(event.id),
            "kind": str(event.kind),
            "amount_cents": int(event.amount_cents),
            "source_id": str(event.source_id) if event.source_id is not None else "",
            "created_at": _to_utc_z(event.created_at),
        },
        "linked_movements": [
            {
                "id": int(m.id),
                "item_id": int(m.item_id),
                "qty_change": int(m.qty_change),
                "unit_cost_cents": int(m.unit_cost_cents or 0),
                "source_id": str(m.source_id) if m.source_id is not None else "",
                "created_at": _to_utc_z(m.created_at),
            }
            for m in linked_movements
        ],
        "computed_cogs_cents": int(computed_cogs_cents),
        "net_profit_cents": int(net_profit_cents),
    }
