# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from core.api.cost_contract import normalize_cost_to_base_cents
from core.api.quantity_contract import normalize_quantity_to_base_int
from core.appdb.ledger import add_batch
from core.appdb.models import CashEvent, Item, ItemMovement


def record_expense(
    db: Session,
    *,
    amount_cents: int,
    category: Optional[str] = None,
    notes: Optional[str] = None,
    created_at: Optional[datetime] = None,
) -> CashEvent:
    ce = CashEvent(
        kind="expense",
        category=category,
        amount_cents=-abs(int(amount_cents)),
        item_id=None,
        qty_base=None,
        unit_price_cents=None,
        source_kind="expense",
        source_id=None,
        related_source_id=None,
        notes=notes,
        created_at=created_at or datetime.utcnow(),
    )
    db.add(ce)
    db.flush()
    return ce


def process_refund(
    db: Session,
    *,
    item_id: int,
    refund_amount_cents: int,
    quantity_decimal: str,
    uom: str,
    restock_inventory: bool,
    related_source_id: Optional[str] = None,
    restock_unit_cost_decimal: Optional[str] = None,
    restock_cost_uom: Optional[str] = None,
    category: Optional[str] = None,
    notes: Optional[str] = None,
    created_at: Optional[datetime] = None,
    normalize_quantity_fn=normalize_quantity_to_base_int,
    normalize_cost_fn=normalize_cost_to_base_cents,
    add_batch_fn=add_batch,
) -> str:
    item = db.get(Item, int(item_id))
    if not item:
        raise HTTPException(status_code=404, detail="item_not_found")

    qty_base = normalize_quantity_fn(item.dimension, uom, quantity_decimal)

    if restock_inventory and (not related_source_id) and (
        restock_unit_cost_decimal is None or not restock_cost_uom
    ):
        raise HTTPException(
            status_code=400,
            detail="restock_unit_cost_required_without_related_source_id",
        )

    source_id = uuid.uuid4().hex
    db.add(
        CashEvent(
            kind="refund",
            category=category,
            amount_cents=-abs(int(refund_amount_cents)),
            item_id=int(item_id),
            qty_base=qty_base,
            unit_price_cents=None,
            source_kind="refund",
            source_id=source_id,
            related_source_id=related_source_id or None,
            notes=notes,
            created_at=created_at or datetime.utcnow(),
        )
    )

    if restock_inventory:
        if related_source_id:
            rows = (
                db.query(ItemMovement)
                .filter(ItemMovement.item_id == int(item_id))
                .filter(ItemMovement.source_id == related_source_id)
                .filter(ItemMovement.qty_change < 0)
                .all()
            )
            if not rows:
                raise HTTPException(status_code=400, detail="related_source_id_not_found_for_item")

            total_qty = Decimal("0")
            total_cost = Decimal("0")
            for movement in rows:
                quantity_abs = abs(int(movement.qty_change))
                total_qty += Decimal(quantity_abs)
                total_cost += Decimal(quantity_abs) * Decimal(int(movement.unit_cost_cents))

            if total_qty == 0:
                raise HTTPException(status_code=400, detail="related_source_id_has_zero_qty")

            unit_cost_cents = int(
                (total_cost / total_qty).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
            )
        else:
            unit_cost_cents = normalize_cost_fn(
                item.dimension,
                str(restock_cost_uom),
                str(restock_unit_cost_decimal),
            )

        add_batch_fn(
            db,
            item_id=int(item_id),
            qty=qty_base,
            unit_cost_cents=int(unit_cost_cents),
            source_kind="refund_restock",
            source_id=source_id,
        )

    return source_id
