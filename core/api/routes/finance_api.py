# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from core.appdb.engine import get_session
from core.appdb.models import CashEvent, Item, ItemMovement
from core.metrics.metric import default_unit_for, uom_multiplier
from core.services.stock_mutation import perform_stock_in_base


router = APIRouter(prefix="/finance", tags=["finance"])


def round_half_up_cents(x: Decimal) -> int:
    return int(x.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _basis_uom_for_item(item: Item) -> str:
    basis_uom = item.uom or default_unit_for(item.dimension)
    if uom_multiplier(item.dimension, basis_uom) <= 0:
        basis_uom = default_unit_for(item.dimension)
    return basis_uom


def _human_qty_from_base(qty_base: int, item: Item) -> Decimal:
    basis_uom = _basis_uom_for_item(item)
    mult = uom_multiplier(item.dimension, basis_uom)
    if mult <= 0:
        raise HTTPException(status_code=400, detail="invalid_uom_multiplier")
    return Decimal(qty_base) / Decimal(mult)


def _line_cost_cents(unit_cost_cents: int, qty_base: int, item: Item) -> int:
    human_qty = _human_qty_from_base(qty_base, item)
    return round_half_up_cents(Decimal(unit_cost_cents) * human_qty)


class ExpenseIn(BaseModel):
    amount_cents: int = Field(gt=0)
    category: Optional[str] = None
    notes: Optional[str] = None
    created_at: Optional[datetime] = None


@router.post("/expense")
def finance_expense(body: ExpenseIn, db: Session = Depends(get_session)):
    ce = CashEvent(
        kind="expense",
        category=body.category,
        amount_cents=-abs(int(body.amount_cents)),
        item_id=None,
        qty_base=None,
        unit_price_cents=None,
        source_kind="expense",
        source_id=None,
        related_source_id=None,
        notes=body.notes,
        created_at=body.created_at or datetime.utcnow(),
    )
    db.add(ce)
    db.commit()
    return {"ok": True, "id": int(ce.id) if ce.id is not None else None}


class RefundIn(BaseModel):
    item_id: int
    refund_amount_cents: int = Field(gt=0)
    qty_base: int = Field(gt=0)
    restock_inventory: bool
    related_source_id: Optional[str] = None
    restock_unit_cost_cents: Optional[int] = None
    category: Optional[str] = None
    notes: Optional[str] = None
    created_at: Optional[datetime] = None


@router.post("/refund")
def finance_refund(body: RefundIn, db: Session = Depends(get_session)):
    item_id = int(body.item_id)
    qty_base = int(body.qty_base)
    refund_amount_cents = int(body.refund_amount_cents)

    if body.restock_inventory is True and (not body.related_source_id) and body.restock_unit_cost_cents is None:
        raise HTTPException(status_code=400, detail="restock_unit_cost_required_without_related_source_id")

    source_id = uuid.uuid4().hex

    # Atomicity (REFUND): cash_events insert + optional stock-in movement must be a single transaction.
    with db.begin():
        db.add(
            CashEvent(
                kind="refund",
                category=body.category,
                amount_cents=-abs(refund_amount_cents),
                item_id=item_id,
                qty_base=qty_base,
                unit_price_cents=None,
                source_kind="refund",
                source_id=source_id,
                related_source_id=(body.related_source_id or None),
                notes=body.notes,
                created_at=body.created_at or datetime.utcnow(),
            )
        )

        if body.restock_inventory is True:
            if body.related_source_id:
                # Weighted-average unit cost from original sale movements linked by related_source_id.
                rows = (
                    db.query(ItemMovement)
                    .filter(ItemMovement.item_id == item_id)
                    .filter(ItemMovement.source_id == body.related_source_id)
                    .filter(ItemMovement.qty_change < 0)
                    .all()
                )
                if not rows:
                    raise HTTPException(status_code=400, detail="related_source_id_not_found_for_item")

                total_qty = Decimal("0")
                total_cost = Decimal("0")
                for m in rows:
                    qabs = abs(int(m.qty_change))
                    total_qty += Decimal(qabs)
                    total_cost += Decimal(qabs) * Decimal(int(m.unit_cost_cents))
                if total_qty == 0:
                    raise HTTPException(status_code=400, detail="related_source_id_has_zero_qty")

                unit_cost_cents = int((total_cost / total_qty).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
            else:
                unit_cost_cents = int(body.restock_unit_cost_cents)

            perform_stock_in_base(
                db,
                item_id=str(item_id),
                qty_base=qty_base,
                unit_cost_cents=unit_cost_cents,
                ref=source_id,
                meta={"source_kind": "refund_restock", "source_id": source_id},
            )

    return {"ok": True, "source_id": source_id}


@router.get("/profit")
def finance_profit(
    from_: str = Query(..., alias="from"),
    to: str = Query(..., alias="to"),
    db: Session = Depends(get_session),
):
    # Params are YYYY-MM-DD. Bounds: [from 00:00:00, to_next_day 00:00:00) (exclusive upper).
    try:
        from_date = datetime.strptime(from_, "%Y-%m-%d").date()
        to_date = datetime.strptime(to, "%Y-%m-%d").date()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid_date_format_expected_YYYY_MM_DD")

    from_dt = datetime(from_date.year, from_date.month, from_date.day, 0, 0, 0)
    to_dt = datetime((to_date + timedelta(days=1)).year, (to_date + timedelta(days=1)).month, (to_date + timedelta(days=1)).day, 0, 0, 0)

    events = (
        db.query(CashEvent)
        .filter(CashEvent.created_at >= from_dt)
        .filter(CashEvent.created_at < to_dt)
        .all()
    )

    gross_sales_cents = 0
    returns_cents = 0
    sale_source_ids = set()

    for e in events:
        if e.kind == "sale":
            gross_sales_cents += int(e.amount_cents)
            if e.source_id:
                sale_source_ids.add(e.source_id)
        elif e.kind == "refund":
            returns_cents += int(e.amount_cents)

    net_sales_cents = gross_sales_cents + returns_cents

    cogs_cents = 0
    if sale_source_ids:
        item_cache: dict[int, Item] = {}
        moves = (
            db.query(ItemMovement)
            .filter(ItemMovement.source_id.in_(list(sale_source_ids)))
            .filter(ItemMovement.qty_change < 0)
            .all()
        )
        for m in moves:
            qty_base = abs(int(m.qty_change))
            item_id = int(m.item_id)
            item = item_cache.get(item_id)
            if item is None:
                item = db.get(Item, item_id)
                if item is None:
                    raise HTTPException(status_code=400, detail="item_not_found")
                item_cache[item_id] = item
            line_cost = _line_cost_cents(int(m.unit_cost_cents or 0), qty_base, item)
            cogs_cents += line_cost

    gross_profit_cents = net_sales_cents - cogs_cents

    return {
        "gross_sales_cents": gross_sales_cents,
        "returns_cents": returns_cents,
        "net_sales_cents": net_sales_cents,
        "cogs_cents": cogs_cents,
        "gross_profit_cents": gross_profit_cents,
        "from": from_,
        "to": to,
    }
