# SPDX-License-Identifier: AGPL-3.0-or-later
import json
import logging
import os
import sqlite3
import sys
from decimal import Decimal, InvalidOperation
from datetime import datetime
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import asc, func
from sqlalchemy.orm import Session

from core.api.utils.devguard import require_dev
from core.api.utils.quantity_guard import reject_legacy_qty_keys
from core.appdb.engine import get_session
from core.appdb.ledger import InsufficientStock
from core.appdb.models import Item, ItemBatch, ItemMovement
from core.appdb.paths import resolve_db_path
from core.metrics.metric import UNIT_MULTIPLIER, _norm_unit, default_unit_for, from_base, normalize_quantity_to_base_int
from core.services.stock_mutation import perform_purchase_base, perform_stock_in_base, perform_stock_out_base

router = APIRouter(prefix="/ledger", tags=["ledger"])
public_router = APIRouter(tags=["ledger"])
DB_PATH = resolve_db_path()
logger = logging.getLogger(__name__)


def _journals_dir() -> Path:
    root = os.environ.get("LOCALAPPDATA")
    if not root:
        root = os.path.expanduser("~/.local/share")
    d = Path(root) / "BUSCore" / "app" / "data" / "journals"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _has_items_qty_stored() -> bool:
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
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
    qty: int = Field(gt=0)
    unit_cost_cents: int = Field(ge=0)
    source_kind: str = "purchase"
    source_id: Optional[str] = None


class PurchaseCanonicalIn(BaseModel):
    item_id: int
    quantity_decimal: str
    uom: str
    unit_cost_cents: int = Field(ge=0)
    source_id: Optional[str] = None


class ConsumeIn(BaseModel):
    item_id: int
    qty: int = Field(gt=0)
    source_kind: str = "consume"
    source_id: Optional[str] = None


class StockOutIn(BaseModel):
    item_id: int
    qty: int = Field(gt=0)
    reason: Literal["sold", "loss", "theft", "other"] = "sold"
    note: Optional[str] = None
    record_cash_event: bool = True
    sell_unit_price_cents: Optional[int] = None


class StockOutCanonicalIn(BaseModel):
    item_id: int
    quantity_decimal: str
    uom: str
    reason: Literal["sold", "loss", "theft", "other"] = "sold"
    note: Optional[str] = None
    record_cash_event: bool = True
    sell_unit_price_cents: Optional[int] = None


class StockInCanonicalIn(BaseModel):
    item_id: int
    quantity_decimal: str
    uom: str
    unit_cost_cents: int | None = Field(default=0, ge=0)
    source_id: str | None = None


class AdjustmentInput(BaseModel):
    item_id: int
    qty_change: int = Field(...)
    note: str | None = None

    @field_validator("qty_change")
    @classmethod
    def qty_change_non_zero(cls, value: int) -> int:
        if value == 0:
            raise ValueError("qty_change must not be 0")
        return value


def _default_uom_for_item(db: Session, item_id: int) -> str:
    item = db.get(Item, int(item_id))
    if not item:
        raise HTTPException(status_code=404, detail="item_not_found")
    return default_unit_for(item.dimension)

def _to_base_qty_for_item(db: Session, item_id: int, quantity_decimal: str, uom: str) -> int:
    item = db.get(Item, int(item_id))
    if not item:
        raise HTTPException(status_code=404, detail="item_not_found")
    try:
        return normalize_quantity_to_base_int(quantity_decimal=quantity_decimal, uom=uom, dimension=item.dimension)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"invalid_quantity:{exc}")


@public_router.post("/purchase")
def canonical_purchase(raw: dict = Body(...), db: Session = Depends(get_session)):
    reject_legacy_qty_keys(raw)
    body = PurchaseCanonicalIn(**raw)
    qty_base = _to_base_qty_for_item(db, body.item_id, body.quantity_decimal, body.uom)
    try:
        result = perform_purchase_base(
            db,
            vendor_id="",
            lines=[
                {
                    "item_id": int(body.item_id),
                    "qty_base": int(qty_base),
                    "unit_cost_cents": int(body.unit_cost_cents),
                    "source_kind": "purchase",
                    "source_id": body.source_id,
                }
            ],
        )
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise


@router.post("/purchase")
def purchase_wrapper(raw: dict = Body(...), db: Session = Depends(get_session)):
    payload = dict(raw)
    qty = payload.pop("qty", None)
    if qty is not None:
        payload["quantity_decimal"] = str(qty)
    if "uom" not in payload:
        payload["uom"] = _default_uom_for_item(db, int(payload["item_id"]))
    body = canonical_purchase(payload, db)
    return JSONResponse(content=body, headers={"X-BUS-Deprecation": "/app/purchase"})


@router.post("/consume")
@public_router.post("/consume")
def consume(body: ConsumeIn, db: Session = Depends(get_session)):
    try:
        result = perform_stock_out_base(
            db,
            item_id=str(body.item_id),
            qty_base=int(body.qty),
            ref=body.source_id,
            meta={"reason": body.source_kind, "note": body.source_id, "record_cash_event": False},
        )
        db.commit()
        lines = [{"batch_id": l["batch_id"], "qty": -int(l["qty_change"]), "unit_cost_cents": l["unit_cost_cents"]} for l in result["lines"]]
        return {"ok": True, "lines": lines}
    except Exception as e:
        db.rollback()
        if hasattr(e, "shortages"):
            raise HTTPException(status_code=400, detail={"shortages": getattr(e, "shortages")})
        raise


@router.post("/adjust")
@public_router.post("/adjust")
def adjust_stock(body: AdjustmentInput, db: Session = Depends(get_session)):
    try:
        if body.qty_change > 0:
            perform_stock_in_base(
                db,
                item_id=str(body.item_id),
                qty_base=int(body.qty_change),
                unit_cost_cents=0,
                ref=body.note,
                meta={"source_kind": "adjustment", "source_id": body.note},
            )
            db.commit()
            return {"ok": True}
        result = perform_stock_out_base(
            db,
            item_id=str(body.item_id),
            qty_base=-int(body.qty_change),
            ref=body.note,
            meta={"reason": "adjustment", "note": body.note, "record_cash_event": False},
        )
        db.commit()
        return {"ok": bool(result.get("ok"))}
    except Exception as e:
        db.rollback()
        if hasattr(e, "shortages"):
            raise HTTPException(status_code=400, detail={"shortages": getattr(e, "shortages")})
        raise


@public_router.post("/stock/out")
def canonical_stock_out(raw: dict = Body(...), db: Session = Depends(get_session)):
    reject_legacy_qty_keys(raw)
    body = StockOutCanonicalIn(**raw)
    qty_base = _to_base_qty_for_item(db, body.item_id, body.quantity_decimal, body.uom)
    try:
        result = perform_stock_out_base(
            db,
            item_id=str(body.item_id),
            qty_base=qty_base,
            ref=body.note,
            meta={
                "reason": body.reason,
                "note": body.note,
                "record_cash_event": body.record_cash_event,
                "sell_unit_price_cents": body.sell_unit_price_cents,
            },
        )
        db.commit()
        return result
    except LookupError:
        db.rollback()
        raise HTTPException(status_code=404, detail="item_not_found")
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as e:
        db.rollback()
        if hasattr(e, "shortages"):
            raise HTTPException(status_code=400, detail={"shortages": getattr(e, "shortages")})
        raise


@router.post("/stock/out")
def stock_out_wrapper(raw: dict = Body(...), db: Session = Depends(get_session)):
    payload = dict(raw)
    qty = payload.pop("qty", None)
    if qty is not None:
        payload["quantity_decimal"] = str(qty)
    if "uom" not in payload:
        payload["uom"] = _default_uom_for_item(db, int(payload["item_id"]))
    body = canonical_stock_out(payload, db)
    return JSONResponse(content=body, headers={"X-BUS-Deprecation": "/app/stock/out"})


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


def _decimal_string(value: Decimal) -> str:
    text = format(value.normalize(), "f")
    if text in {"-0", "-0.0", "-0.00"}:
        return "0"
    return text


@public_router.get("/ledger/history")
def canonical_history(
    item_id: Optional[int] = None,
    limit: int = 100,
    include_base: bool = Query(False),
    db: Session = Depends(get_session),
):
    q = db.query(ItemMovement)
    if item_id is not None:
        q = q.filter(ItemMovement.item_id == int(item_id))
    rows = q.order_by(ItemMovement.id.desc()).limit(int(limit)).all()

    expose_base = bool(include_base) or os.environ.get("BUS_DEV") == "1"
    item_cache: dict[int, Item | None] = {}
    movements = []
    for m in rows:
        item = item_cache.get(int(m.item_id))
        if int(m.item_id) not in item_cache:
            item = db.get(Item, int(m.item_id))
            item_cache[int(m.item_id)] = item
        if item:
            uom = _norm_unit(item.uom or default_unit_for(item.dimension))
            if not UNIT_MULTIPLIER.get(item.dimension, {}).get(uom):
                uom = default_unit_for(item.dimension)
            qty_decimal = from_base(abs(int(m.qty_change)), uom, item.dimension)
        else:
            uom = 'mc'
            qty_decimal = Decimal(abs(int(m.qty_change)))

        signed_qty = -qty_decimal if int(m.qty_change) < 0 else qty_decimal
        entry = {
            "id": int(m.id),
            "item_id": int(m.item_id),
            "batch_id": int(m.batch_id) if m.batch_id is not None else None,
            "quantity_decimal": _decimal_string(signed_qty),
            "uom": uom,
            "unit_cost_cents": int(m.unit_cost_cents or 0),
            "source_kind": m.source_kind,
            "source_id": m.source_id,
            "is_oversold": bool(m.is_oversold),
            "created_at": getattr(m.created_at, "isoformat", lambda: None)(),
        }
        if expose_base:
            entry["qty_change"] = int(m.qty_change)
        movements.append(entry)

    return {"movements": movements}


@router.get("/movements")
@public_router.get("/movements")
def movements_wrapper(item_id: Optional[int] = None, limit: int = 100, db: Session = Depends(get_session)):
    body = canonical_history(item_id=item_id, limit=limit, db=db)
    return JSONResponse(content=body, headers={"X-BUS-Deprecation": "/app/ledger/history"})


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


@public_router.post("/stock/in")
def canonical_stock_in(raw: dict = Body(...), db: Session = Depends(get_session)):
    reject_legacy_qty_keys(raw)
    body = StockInCanonicalIn(**raw)
    qty_base = _to_base_qty_for_item(db, body.item_id, body.quantity_decimal, body.uom)
    try:
        result = perform_stock_in_base(
            db,
            item_id=str(body.item_id),
            qty_base=qty_base,
            unit_cost_cents=body.unit_cost_cents,
            ref=body.source_id,
            meta={"source_kind": "stock_in", "source_id": body.source_id},
        )
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise


@router.post("/stock_in")
@public_router.post("/stock_in")
def stock_in_wrapper(raw: dict = Body(...), db: Session = Depends(get_session)):
    payload = dict(raw)
    if "qty" in payload:
        payload["quantity_decimal"] = str(payload.pop("qty"))
    if "uom" not in payload:
        payload["uom"] = _default_uom_for_item(db, int(payload["item_id"]))
    body = canonical_stock_in(payload, db)
    return JSONResponse(content=body, headers={"X-BUS-Deprecation": "/app/stock/in"})


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
        return None
    return f"{_cents_to_display(int(cents))} / {unit}"


if sys.version_info < (3, 11):
    pass

__all__ = ["router", "public_router"]
