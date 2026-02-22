# SPDX-License-Identifier: AGPL-3.0-or-later
import json
import uuid
import logging
import os
import sqlite3
import sys
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import asc, func
from sqlalchemy.orm import Session

from core.api.utils.devguard import require_dev
from core.appdb.engine import get_session
from core.appdb.ledger import (
    InsufficientStock,
    add_batch,
    fifo_consume as sa_fifo_consume,
)
from core.appdb.models import Item, ItemBatch, ItemMovement, CashEvent
from core.appdb.paths import resolve_db_path
from core.api.schemas_ledger import QtyDisplay, StockInReq, StockInResp
from core.api.quantity_contract import normalize_quantity_to_base_int
from core.api.cost_contract import normalize_cost_to_base_cents
from core.metrics.metric import UNIT_MULTIPLIER, _norm_unit, default_unit_for, from_base
from core.journal.inventory import append_inventory

# NOTE: Primary router uses legacy "/ledger" prefix; public_router exposes routes without it
# (e.g., /app/adjust) to match current app paths.
router = APIRouter(prefix="/ledger", tags=["ledger"])
public_router = APIRouter(tags=["ledger"])
DB_PATH = resolve_db_path()
logger = logging.getLogger(__name__)


def _journals_dir() -> Path:
    root = os.environ.get("LOCALAPPDATA")
    if not root:
        # Linux/macOS fallback
        root = os.path.expanduser("~/.local/share")
    d = Path(root) / "BUSCore" / "app" / "data" / "journals"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _append_inventory_journal(entry: dict) -> None:
    try:
        entry = dict(entry)
        entry.setdefault("timestamp", datetime.utcnow().isoformat() + "Z")
        if "op" not in entry and "type" in entry:
            entry["op"] = entry["type"]
        if "qty" not in entry and "qty_change" in entry:
            entry["qty"] = entry["qty_change"]
        append_inventory(entry)
    except Exception:
        # Journaling must never block core ops.
        pass

def _has_items_qty_stored() -> bool:
    con = sqlite3.connect(DB_PATH); cur = con.cursor()
    try:
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='items'")
        if not cur.fetchone():
            return False
        cur.execute("PRAGMA table_info(items)")
        cols = {r[1] for r in cur.fetchall()}
        return "qty_stored" in cols
    finally:
        con.close()

@router.get("/health")
def health():
    if not _has_items_qty_stored():
        return {"desync": True, "problems": [{"reason": "items.qty_stored missing"}]}
    return {"desync": False, "note": "Using items.qty_stored for on-hand checks"}

class PurchaseIn(BaseModel):
    item_id: int
    quantity_decimal: str = Field(min_length=1)
    uom: str = Field(min_length=1)
    unit_cost_decimal: str = Field(min_length=1)
    cost_uom: str = Field(min_length=1)
    source_kind: str = "purchase"
    source_id: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def reject_legacy_qty(cls, data):
        if isinstance(data, dict) and "qty" in data:
            raise ValueError("legacy_qty_field_not_allowed")
        if isinstance(data, dict) and "unit_cost_cents" in data:
            raise ValueError("legacy_unit_cost_field_not_allowed")
        return data


def handle_purchase(body: PurchaseIn, db: Session):
    item = db.get(Item, int(body.item_id))
    if not item:
        raise HTTPException(status_code=404, detail="item_not_found")
    qty_base = normalize_quantity_to_base_int(item.dimension, body.uom, body.quantity_decimal)
    base_unit_cost_cents = normalize_cost_to_base_cents(item.dimension, body.cost_uom, body.unit_cost_decimal)

    batch_id = add_batch(
        db,
        int(body.item_id),
        qty_base,
        int(base_unit_cost_cents),
        body.source_kind,
        body.source_id,
    )

    if db.in_transaction():
        db.flush()
    else:
        db.commit()
    _append_inventory_journal(
        {
            "type": "purchase",
            "item_id": int(body.item_id),
            "qty_change": qty_base,
            "unit_cost_cents": int(base_unit_cost_cents),
            "source_kind": body.source_kind,
            "source_id": body.source_id,
            "batch_id": int(batch_id),
        }
    )
    return {"ok": True, "batch_id": int(batch_id)}


@router.post("/purchase")
@public_router.post("/purchase")
def purchase(body: PurchaseIn, db: Session = Depends(get_session)):
    return handle_purchase(body, db)


class ConsumeIn(BaseModel):
    item_id: int
    quantity_decimal: str = Field(min_length=1)
    uom: str = Field(min_length=1)
    source_kind: str = "consume"
    source_id: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def reject_legacy_qty(cls, data):
        if isinstance(data, dict) and "qty" in data:
            raise ValueError("legacy_qty_field_not_allowed")
        return data


class StockOutIn(BaseModel):
    item_id: int
    quantity_decimal: str = Field(min_length=1)
    uom: str = Field(min_length=1)
    reason: Literal["sold", "loss", "theft", "other"] = "sold"
    note: Optional[str] = None
    record_cash_event: bool = True
    sell_unit_price_cents: Optional[int] = None

    @model_validator(mode="before")
    @classmethod
    def reject_legacy_qty(cls, data):
        if isinstance(data, dict) and "qty" in data:
            raise ValueError("legacy_qty_field_not_allowed")
        return data


@router.post("/consume")
@public_router.post("/consume")
def consume(body: ConsumeIn, db: Session = Depends(get_session)):
    item = db.get(Item, int(body.item_id))
    if not item:
        raise HTTPException(status_code=404, detail="item_not_found")
    qty_base = normalize_quantity_to_base_int(item.dimension, body.uom, body.quantity_decimal)
    try:
        moves = sa_fifo_consume(db, int(body.item_id), qty_base, body.source_kind, body.source_id)
        db.commit()
        lines = [
            {
                "batch_id": int(m.batch_id),
                "qty": -int(m.qty_change),
                "unit_cost_cents": int(m.unit_cost_cents or 0),
            }
            for m in moves
        ]
        _append_inventory_journal(
            {
                "type": "consume",
                "item_id": int(body.item_id),
                "qty_change": -qty_base,
                "source_kind": body.source_kind,
                "source_id": body.source_id,
            }
        )
        return {"ok": True, "lines": lines}
    except InsufficientStock as e:
        raise HTTPException(status_code=400, detail={"shortages": e.shortages})


# -------------------------
# POST /app/ledger/adjust
# -------------------------
class AdjustmentInput(BaseModel):
    item_id: int
    quantity_decimal: str = Field(min_length=1)
    uom: str = Field(min_length=1)
    direction: Literal["in", "out"]
    note: str | None = None

    @model_validator(mode="before")
    @classmethod
    def reject_legacy_qty_change(cls, data):
        if isinstance(data, dict) and "qty_change" in data:
            raise ValueError("legacy_qty_field_not_allowed")
        return data

    @field_validator("direction")
    @classmethod
    def direction_valid(cls, value: str) -> str:
        if value not in {"in", "out"}:
            raise ValueError("direction must be 'in' or 'out'")
        return value


@router.post("/adjust")
@public_router.post("/adjust")
def adjust_stock(body: AdjustmentInput, db: Session = Depends(get_session)):
    """
    Positive adjustment:
      - create a new batch with qty_remaining=+N and unit_cost_cents=0 (SoT silent on costing)
      - write a matching positive movement
    Negative adjustment:
      - consume FIFO from existing batches
      - 400 if insufficient on-hand; no partials
    """
    item = db.get(Item, int(body.item_id))
    if not item:
        raise HTTPException(status_code=404, detail="item_not_found")
    qty_base = normalize_quantity_to_base_int(item.dimension, body.uom, body.quantity_decimal)

    if body.direction == "in":
        add_batch(db, int(body.item_id), qty_base, 0, "adjustment", body.note)
        db.commit()
        _append_inventory_journal(
            {
                "type": "adjustment",
                "item_id": int(body.item_id),
                "qty_change": qty_base,
                "unit_cost_cents": 0,
                "source_kind": "adjustment",
                "source_id": body.note or None,
            }
        )
        return {"ok": True}
    else:
        try:
            sa_fifo_consume(db, int(body.item_id), qty_base, "adjustment", body.note)
            db.commit()
            _append_inventory_journal(
                {
                    "type": "adjustment",
                    "item_id": int(body.item_id),
                    "qty_change": -qty_base,
                    "source_kind": "adjustment",
                    "source_id": body.note or None,
                }
            )
            return {"ok": True}
        except InsufficientStock as e:
            raise HTTPException(status_code=400, detail={"shortages": e.shortages})


def handle_stock_out(body: StockOutIn, db: Session):
    try:
        item_id = int(body.item_id)
        it = db.get(Item, item_id)
        if not it:
            raise HTTPException(status_code=404, detail="item_not_found")
        qty_base = normalize_quantity_to_base_int(it.dimension, body.uom, body.quantity_decimal)

        # Atomicity (SALE): fifo movements + cash_events insert must share a single transaction.
        if body.reason == "sold" and bool(body.record_cash_event) is True:
            if (getattr(it, "dimension", None) or "").lower() != "count":
                raise HTTPException(status_code=400, detail="sold_cash_event_count_only")

            # Determine unit price snapshot (cents)
            if body.sell_unit_price_cents is not None:
                unit_price_cents = int(body.sell_unit_price_cents)
            else:
                unit_price_cents = int(
                    (Decimal(str(getattr(it, "price", 0) or 0)) * Decimal("100")).quantize(
                        Decimal("1"), rounding=ROUND_HALF_UP
                    )
                )

            # Finance v1: count-only conversion: 1 ea = 1000 base units
            qty_each = Decimal(qty_base) / Decimal(1000)
            amount_cents = int(
                (Decimal(unit_price_cents) * qty_each).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
            )

            source_id = uuid.uuid4().hex
            # SQLAlchemy Session has autobegin; in request contexts we may already be inside a transaction.
            # Use a nested transaction (SAVEPOINT) when a transaction is active, otherwise start a new one.
            tx = db.begin_nested() if db.in_transaction() else db.begin()
            with tx:
                moves = sa_fifo_consume(db, item_id, qty_base, body.reason, source_id)
                db.add(
                    CashEvent(
                        kind="sale",
                        category=None,
                        amount_cents=amount_cents,
                        item_id=item_id,
                        qty_base=qty_base,
                        unit_price_cents=unit_price_cents,
                        source_kind="sold",
                        source_id=source_id,
                        related_source_id=None,
                        notes=body.note,
                    )
                )
        else:
            # Preserve prior behavior for non-sale or when record_cash_event is false.
            moves = sa_fifo_consume(db, item_id, qty_base, body.reason, body.note)
            db.commit()
        lines = [
            {
                "batch_id": int(m.batch_id),
                "qty_change": int(m.qty_change),
                "unit_cost_cents": int(m.unit_cost_cents),
                "source_kind": m.source_kind,
                "source_id": m.source_id,
            }
            for m in moves
        ]
        _append_inventory_journal(
            {
                "type": body.reason,
                "item_id": int(body.item_id),
                "qty_change": -qty_base,
                "unit_cost_cents": 0,
                "source_kind": body.reason,
                "source_id": body.note or None,
            }
        )
        return {"ok": True, "lines": lines}
    except InsufficientStock as e:
        raise HTTPException(status_code=400, detail={"shortages": e.shortages})


@router.post("/stock/out")
@public_router.post("/stock/out")
def stock_out(body: StockOutIn, db: Session = Depends(get_session)):
    return handle_stock_out(body, db)


@router.get("/valuation")
@public_router.get("/valuation")
def valuation(item_id: Optional[int] = None, db: Session = Depends(get_session)):
    if item_id is not None:
        total = (
            db.query(func.coalesce(func.sum(ItemBatch.qty_remaining * ItemBatch.unit_cost_cents), 0))
            .filter(ItemBatch.item_id == int(item_id))
            .scalar()
        )
        return {"item_id": int(item_id), "total_value_cents": int(total or 0)}
    rows = (
        db.query(
            ItemBatch.item_id.label("item_id"),
            func.coalesce(func.sum(ItemBatch.qty_remaining * ItemBatch.unit_cost_cents), 0).label("total"),
        )
        .group_by(ItemBatch.item_id)
        .all()
    )
    return {"totals": [{"item_id": r.item_id, "total_value_cents": int(r.total or 0)} for r in rows]}


def get_ledger_history(item_id: Optional[int], limit: int, db: Session):
    q = db.query(ItemMovement)
    if item_id is not None:
        q = q.filter(ItemMovement.item_id == int(item_id))
    rows = q.order_by(ItemMovement.id.desc()).limit(int(limit)).all()

    def to_dict(m: ItemMovement) -> dict:
        return {
            "id": int(m.id),
            "item_id": int(m.item_id),
            "batch_id": int(m.batch_id) if m.batch_id is not None else None,
            "qty_change": int(m.qty_change),
            "unit_cost_cents": int(m.unit_cost_cents or 0),
            "source_kind": m.source_kind,
            "source_id": m.source_id,
            "is_oversold": bool(m.is_oversold),
            "created_at": getattr(m.created_at, "isoformat", lambda: None)(),
        }

    return {"movements": [to_dict(m) for m in rows]}


@router.get("/history")
def ledger_history(item_id: Optional[int] = None, limit: int = 100, db: Session = Depends(get_session)):
    return get_ledger_history(item_id, limit, db)


@router.get("/movements")
@public_router.get("/movements")
def movements(response: Response, item_id: Optional[int] = None, limit: int = 100, db: Session = Depends(get_session)):
    response.headers["X-BUS-Deprecation"] = "/app/ledger/history"
    return get_ledger_history(item_id, limit, db)


@router.get("/debug/db")
def ledger_debug(item_id: int | None = None):
    require_dev()
    path = resolve_db_path()
    with sqlite3.connect(path) as con:
        cur = con.cursor()
        cur.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='items'")
        has_items = bool(cur.fetchone()[0])
        item_row = None
        items_count = None
        if has_items:
            cur.execute("SELECT COUNT(*) FROM items")
            items_count = int(cur.fetchone()[0])
            if item_id is not None:
                cur.execute("SELECT id,name,sku,uom,qty_stored FROM items WHERE id=?", (int(item_id),))
                item_row = cur.fetchone()
    return {"db_path": path, "has_items": has_items, "items_count": items_count, "item_row": item_row}


def _cents_to_display(cents: int) -> str:
    return f"${cents / 100:,.2f}"


def _fifo_unit_cost_display(db: Session, item_id: int, unit: str) -> Optional[str]:
    batch = (
        db.query(ItemBatch)
        .filter(ItemBatch.item_id == item_id, ItemBatch.qty_remaining > 0)
        .order_by(asc(ItemBatch.created_at), asc(ItemBatch.id))
        .first()
    )
    if not batch:
        return None
    cents = getattr(batch, "unit_cost_cents", None)
    if cents is None:
        try:
            unit_cost = getattr(batch, "unit_cost", None)
            cents = int(round(float(unit_cost) * 100)) if unit_cost is not None else None
        except Exception:
            cents = None
    if cents is None:
        try:
            total_cents = getattr(batch, "total_cost_cents", None)
            qty_init = getattr(batch, "qty_initial", None) or 0
            cents = int(total_cents) // int(qty_init) if total_cents is not None and qty_init else None
        except Exception:
            cents = None
    if cents is None:
        return None
    return f"{_cents_to_display(int(cents))} / {unit}"


def handle_stock_in(payload: StockInReq, db: Session):
    item = db.get(Item, payload.item_id)
    if not item:
        raise HTTPException(status_code=404, detail="item_not_found")

    uom_raw = payload.uom
    uom = _norm_unit(uom_raw)
    qty_int = normalize_quantity_to_base_int(item.dimension, uom_raw, payload.quantity_decimal)
    unit_cost_cents = normalize_cost_to_base_cents(item.dimension, payload.cost_uom, payload.unit_cost_decimal)

    batch = ItemBatch(
        item_id=item.id,
        qty_initial=qty_int,
        qty_remaining=qty_int,
        unit_cost_cents=unit_cost_cents,
        source_kind="stock_in",
        source_id=str(payload.vendor_id) if payload.vendor_id is not None else None,
        is_oversold=False,
        created_at=datetime.utcnow(),
    )
    db.add(batch)

    logger.info(
        "stock_in debug",
        extra={
            "item_id": item.id,
            "dimension": item.dimension,
            "uom": uom,
            "uom_raw": uom_raw,
            "qty_decimal": str(payload.quantity_decimal),
            "qty_int": qty_int,
            "unit_cost_decimal": payload.unit_cost_decimal,
            "unit_cost_cents": unit_cost_cents,
        },
    )

    movement = ItemMovement(
        item_id=item.id,
        batch_id=None,
        qty_change=qty_int,
        unit_cost_cents=unit_cost_cents,
        source_kind="stock_in",
        source_id=str(payload.vendor_id) if payload.vendor_id is not None else None,
        is_oversold=False,
        created_at=datetime.utcnow(),
    )
    db.add(movement)
    db.flush()
    if hasattr(movement, "batch_id"):
        movement.batch_id = batch.id

    if hasattr(item, "qty_stored"):
        item.qty_stored = int((getattr(item, "qty_stored", 0) or 0) + qty_int)

    on_hand = 0
    oldest = None
    try:
        on_hand = (
            db.query(func.coalesce(func.sum(ItemBatch.qty_remaining), 0))
            .filter(ItemBatch.item_id == item.id, ItemBatch.qty_remaining > 0)
            .scalar()
            or 0
        )

        oldest = (
            db.query(ItemBatch)
            .filter(ItemBatch.item_id == item.id, ItemBatch.qty_remaining > 0)
            .order_by(asc(ItemBatch.created_at), asc(ItemBatch.id))
            .first()
        )

        db.commit()
    except Exception:
        db.rollback()
        raise

    display_unit = item.uom or default_unit_for(getattr(item, "dimension", "count") or "count")
    if item.dimension not in UNIT_MULTIPLIER or display_unit not in UNIT_MULTIPLIER[item.dimension]:
        display_unit = default_unit_for(getattr(item, "dimension", "count") or "count")
    display_qty = from_base(int(on_hand), display_unit, item.dimension)
    fifo_disp = (
        f"{_cents_to_display(oldest.unit_cost_cents)} / {display_unit}"
        if oldest and getattr(oldest, "unit_cost_cents", None) is not None
        else None
    )

    return StockInResp(
        batch_id=batch.id,
        qty_added_int=qty_int,
        stock_on_hand_int=int(on_hand),
        stock_on_hand_display=QtyDisplay(unit=display_unit, value=str(display_qty)),
        fifo_unit_cost_display=fifo_disp,
    )


@router.post("/stock/in", response_model=StockInResp)
@public_router.post("/stock/in", response_model=StockInResp)
def stock_in_canonical(payload: StockInReq, db: Session = Depends(get_session)):
    return handle_stock_in(payload, db)


@router.post("/stock_in", response_model=StockInResp)
@public_router.post("/stock_in", response_model=StockInResp)
def stock_in(payload: StockInReq, response: Response, db: Session = Depends(get_session)):
    response.headers["X-BUS-Deprecation"] = "/app/stock/in"
    return handle_stock_in(payload, db)


__all__ = ["router", "public_router"]
