# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import uuid
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from core.appdb.engine import get_session
from core.appdb.models import CashEvent, Item, ItemMovement
from core.appdb.models_recipes import ManufacturingRun
from core.api.utils.quantity_guard import reject_legacy_qty_keys
from core.metrics.metric import default_unit_for, uom_multiplier
from core.metrics.metric import normalize_quantity_to_base_int
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


def _decimal_string(value: Decimal) -> str:
    text = format(value.normalize(), "f")
    if text in {"-0", "-0.0", "-0.00"}:
        return "0"
    return text


def _parse_window(from_: str, to: str) -> tuple[datetime, datetime]:
    try:
        from_date = datetime.strptime(from_, "%Y-%m-%d").date()
        to_date = datetime.strptime(to, "%Y-%m-%d").date()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid_date_format_expected_YYYY_MM_DD")
    from_dt = datetime(from_date.year, from_date.month, from_date.day, 0, 0, 0)
    to_next = to_date + timedelta(days=1)
    to_dt = datetime(to_next.year, to_next.month, to_next.day, 0, 0, 0)
    return from_dt, to_dt


def _parse_window_read(from_: str, to: str) -> tuple[tuple[datetime, datetime] | None, str | None]:
    try:
        from_date = datetime.strptime(from_, "%Y-%m-%d").date()
        to_date = datetime.strptime(to, "%Y-%m-%d").date()
    except Exception:
        return None, "invalid_date_format"
    if from_date > to_date:
        return None, "invalid_date_range"
    from_dt = datetime(from_date.year, from_date.month, from_date.day, 0, 0, 0)
    to_next = to_date + timedelta(days=1)
    to_dt = datetime(to_next.year, to_next.month, to_next.day, 0, 0, 0)
    return (from_dt, to_dt), None


def _parse_created_at_sort(value: object) -> datetime:
    if not value:
        return datetime.min
    text = str(value)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except Exception:
        return datetime.min
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _tx_tiebreaker(tx: dict) -> str:
    if tx.get("id") is not None:
        return str(tx.get("id"))
    if tx.get("source_id") is not None:
        return str(tx.get("source_id"))
    return ""


def _item_cache_get(db: Session, cache: dict[int, Item], item_id: int) -> Item:
    item = cache.get(item_id)
    if item is None:
        item = db.get(Item, item_id)
        if item is None:
            raise HTTPException(status_code=400, detail="item_not_found")
        cache[item_id] = item
    return item


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
    quantity_decimal: str
    uom: str
    restock_inventory: bool
    related_source_id: Optional[str] = None
    restock_unit_cost_cents: Optional[int] = None
    category: Optional[str] = None
    notes: Optional[str] = None
    created_at: Optional[datetime] = None


@router.post("/refund")
def finance_refund(raw: dict = Body(...), db: Session = Depends(get_session)):
    reject_legacy_qty_keys(raw)
    body = RefundIn(**raw)

    item_id = int(body.item_id)
    refund_amount_cents = int(body.refund_amount_cents)

    if body.restock_inventory is True and (not body.related_source_id) and body.restock_unit_cost_cents is None:
        raise HTTPException(status_code=400, detail="restock_unit_cost_required_without_related_source_id")

    source_id = uuid.uuid4().hex

    # Atomicity (REFUND): cash_events insert + optional stock-in movement must be a single transaction.
    with db.begin():
        item = db.get(Item, item_id)
        if item is None:
            raise HTTPException(status_code=404, detail="item_not_found")
        qty_base = normalize_quantity_to_base_int(
            quantity_decimal=body.quantity_decimal,
            uom=body.uom,
            dimension=item.dimension,
        )
        if qty_base <= 0:
            raise HTTPException(status_code=400, detail="quantity_decimal must be > 0")

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
    from_dt, to_dt = _parse_window(from_, to)

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


@router.get("/summary")
def finance_summary(
    from_: str = Query(..., alias="from"),
    to: str = Query(..., alias="to"),
    db: Session = Depends(get_session),
):
    window, error = _parse_window_read(from_, to)
    if error is not None:
        return JSONResponse(status_code=400, content={"detail": error})
    from_dt, to_dt = window
    item_cache: dict[int, Item] = {}

    events = (
        db.query(CashEvent)
        .filter(CashEvent.created_at >= from_dt)
        .filter(CashEvent.created_at < to_dt)
        .all()
    )

    gross_sales_cents = 0
    returns_cents = 0
    expenses_cents = 0
    sale_source_ids: set[str] = set()
    units_sold_base: dict[int, int] = {}

    for e in events:
        if e.kind == "sale":
            gross_sales_cents += int(e.amount_cents)
            if e.source_id:
                sale_source_ids.add(str(e.source_id))
        elif e.kind == "refund":
            returns_cents += int(e.amount_cents)
        elif e.kind == "expense":
            expenses_cents += abs(int(e.amount_cents))

    net_sales_cents = gross_sales_cents + returns_cents

    sold_moves_window = (
        db.query(ItemMovement)
        .filter(ItemMovement.created_at >= from_dt)
        .filter(ItemMovement.created_at < to_dt)
        .filter(ItemMovement.qty_change < 0)
        .filter(ItemMovement.source_kind == "sold")
        .all()
    )
    for move in sold_moves_window:
        item_id = int(move.item_id)
        units_sold_base[item_id] = units_sold_base.get(item_id, 0) + abs(int(move.qty_change))

    cogs_cents = 0
    if sale_source_ids:
        sale_moves = (
            db.query(ItemMovement)
            .filter(ItemMovement.source_id.in_(list(sale_source_ids)))
            .filter(ItemMovement.qty_change < 0)
            .filter(ItemMovement.source_kind == "sold")
            .all()
        )
        for move in sale_moves:
            item = _item_cache_get(db, item_cache, int(move.item_id))
            cogs_cents += _line_cost_cents(int(move.unit_cost_cents or 0), abs(int(move.qty_change)), item)

    gross_profit_cents = net_sales_cents - cogs_cents
    net_profit_cents = gross_profit_cents - expenses_cents

    runs = (
        db.query(ManufacturingRun)
        .filter(ManufacturingRun.created_at >= from_dt)
        .filter(ManufacturingRun.created_at < to_dt)
        .all()
    )

    units_produced_base: dict[int, int] = {}
    for run in runs:
        if int(run.output_qty or 0) <= 0:
            continue
        item_id = int(run.output_item_id)
        units_produced_base[item_id] = units_produced_base.get(item_id, 0) + int(run.output_qty)

    def _qty_payload(by_item_base: dict[int, int]) -> list[dict]:
        out: list[dict] = []
        for item_id in sorted(by_item_base.keys()):
            item = _item_cache_get(db, item_cache, item_id)
            basis_uom = _basis_uom_for_item(item)
            qty_decimal = _decimal_string(_human_qty_from_base(by_item_base[item_id], item))
            out.append({"item_id": item_id, "item_name": item.name, "quantity_decimal": qty_decimal, "uom": basis_uom})
        return out

    return {
        "gross_sales_cents": gross_sales_cents,
        "returns_cents": returns_cents,
        "net_sales_cents": net_sales_cents,
        "cogs_cents": cogs_cents,
        "gross_profit_cents": gross_profit_cents,
        "expenses_cents": expenses_cents,
        "net_profit_cents": net_profit_cents,
        "runs_count": len(runs),
        "units_produced": _qty_payload(units_produced_base),
        "units_sold": _qty_payload(units_sold_base),
        "from": from_,
        "to": to,
    }


@router.get("/transactions")
def finance_transactions(
    from_: str = Query(..., alias="from"),
    to: str = Query(..., alias="to"),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_session),
):
    window, error = _parse_window_read(from_, to)
    if error is not None:
        return JSONResponse(status_code=400, content={"detail": error})
    from_dt, to_dt = window
    item_cache: dict[int, Item] = {}

    events = (
        db.query(CashEvent)
        .filter(CashEvent.created_at >= from_dt)
        .filter(CashEvent.created_at < to_dt)
        .all()
    )
    sales_cash_by_source_id: dict[str, int] = {}
    sales_created_at_by_source_id: dict[str, datetime | None] = {}
    transactions: list[dict] = []

    for e in events:
        if e.kind == "sale" and e.source_id:
            source_id = str(e.source_id)
            sales_cash_by_source_id[source_id] = sales_cash_by_source_id.get(source_id, 0) + int(e.amount_cents)
            existing_dt = sales_created_at_by_source_id.get(source_id)
            current_dt = e.created_at
            if existing_dt is None:
                sales_created_at_by_source_id[source_id] = current_dt
            elif current_dt is not None and current_dt < existing_dt:
                sales_created_at_by_source_id[source_id] = current_dt
        elif e.kind in {"refund", "expense"}:
            transactions.append(
                {
                    "kind": e.kind,
                    "id": int(e.id),
                    "created_at": e.created_at.isoformat() if e.created_at else None,
                    "amount_cents": int(e.amount_cents),
                    "item_id": int(e.item_id) if e.item_id is not None else None,
                    "source_id": e.source_id,
                    "related_source_id": e.related_source_id,
                    "category": e.category,
                    "notes": e.notes,
                }
            )

    sale_source_ids = list(sales_cash_by_source_id.keys())
    sales_cogs_by_source_id: dict[str, int] = {sid: 0 for sid in sale_source_ids}
    if sale_source_ids:
        sale_moves = (
            db.query(ItemMovement)
            .filter(ItemMovement.source_id.in_(sale_source_ids))
            .filter(ItemMovement.qty_change < 0)
            .filter(ItemMovement.source_kind == "sold")
            .all()
        )
        for move in sale_moves:
            source_id = str(move.source_id)
            item = _item_cache_get(db, item_cache, int(move.item_id))
            line_cogs = _line_cost_cents(int(move.unit_cost_cents or 0), abs(int(move.qty_change)), item)
            sales_cogs_by_source_id[source_id] = sales_cogs_by_source_id.get(source_id, 0) + line_cogs

    for source_id in sale_source_ids:
        sales_amount = int(sales_cash_by_source_id.get(source_id, 0))
        cogs = int(sales_cogs_by_source_id.get(source_id, 0))
        created_at = sales_created_at_by_source_id.get(source_id)
        transactions.append(
            {
                "kind": "sale",
                "source_id": source_id,
                "created_at": created_at.isoformat() if created_at else None,
                "amount_cents": sales_amount,
                "cogs_cents": cogs,
                "gross_profit_cents": sales_amount - cogs,
            }
        )

    runs = (
        db.query(ManufacturingRun)
        .filter(ManufacturingRun.created_at >= from_dt)
        .filter(ManufacturingRun.created_at < to_dt)
        .all()
    )
    for run in runs:
        meta = {}
        if run.meta:
            try:
                meta = json.loads(run.meta)
            except Exception:
                meta = {}
        item = _item_cache_get(db, item_cache, int(run.output_item_id))
        transactions.append(
            {
                "kind": "manufacturing_run",
                "id": int(run.id),
                "created_at": run.created_at.isoformat() if run.created_at else None,
                "status": run.status,
                "output_item_id": int(run.output_item_id),
                "output_qty_decimal": _decimal_string(_human_qty_from_base(int(run.output_qty or 0), item)),
                "output_uom": _basis_uom_for_item(item),
                "cost_inputs_cents": int(meta.get("cost_inputs_cents", 0) or 0),
                "per_output_cents": int(meta.get("per_output_cents", 0) or 0),
            }
        )

    purchases = (
        db.query(ItemMovement)
        .filter(ItemMovement.created_at >= from_dt)
        .filter(ItemMovement.created_at < to_dt)
        .filter(ItemMovement.source_kind == "purchase")
        .filter(ItemMovement.qty_change > 0)
        .all()
    )
    for move in purchases:
        item = _item_cache_get(db, item_cache, int(move.item_id))
        qty_base = int(move.qty_change)
        amount_cents = _line_cost_cents(int(move.unit_cost_cents or 0), qty_base, item)
        transactions.append(
            {
                "kind": "purchase_inferred",
                "id": int(move.id),
                "created_at": move.created_at.isoformat() if move.created_at else None,
                "item_id": int(move.item_id),
                "source_id": move.source_id,
                "quantity_decimal": _decimal_string(_human_qty_from_base(qty_base, item)),
                "uom": _basis_uom_for_item(item),
                "unit_cost_cents": int(move.unit_cost_cents or 0),
                "amount_cents": amount_cents,
            }
        )

    transactions.sort(
        key=lambda tx: (_parse_created_at_sort(tx.get("created_at")), _tx_tiebreaker(tx)),
        reverse=True,
    )
    sliced = transactions[: int(limit)]
    return {
        "from": from_,
        "to": to,
        "limit": int(limit),
        "count": int(len(sliced)),
        "transactions": sliced,
    }
