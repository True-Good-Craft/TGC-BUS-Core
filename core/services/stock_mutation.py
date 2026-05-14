# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import logging
from datetime import datetime
import uuid
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from sqlalchemy.orm import Session

from core.appdb.ledger import add_batch, fifo_consume
from core.appdb.models import CashEvent, Item
from core.journal.inventory import append_inventory
from core.metrics.metric import default_unit_for, uom_multiplier

logger = logging.getLogger(__name__)


def _require_qty_base(qty_base: int) -> int:
    if not isinstance(qty_base, int) or qty_base <= 0:
        raise ValueError("qty_base_must_be_positive_int")
    return qty_base


def _append_inventory_journal(entry: dict[str, Any]) -> None:
    try:
        payload = dict(entry)
        payload.setdefault("timestamp", datetime.utcnow().isoformat() + "Z")
        if "op" not in payload and "type" in payload:
            payload["op"] = payload["type"]
        if "qty" not in payload and "qty_change" in payload:
            payload["qty"] = payload["qty_change"]
        append_inventory(payload)
    except Exception as exc:
        logger.warning("inventory_journal_append_failed class=%s", type(exc).__name__)


def _round_half_up_cents(value: Decimal) -> int:
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _basis_uom_for_item(item: Item) -> str:
    basis_uom = item.uom or default_unit_for(item.dimension)
    if uom_multiplier(item.dimension, basis_uom) <= 0:
        basis_uom = default_unit_for(item.dimension)
    return basis_uom


def _purchase_total_amount_cents(unit_cost_cents: int, qty_base: int, item: Item) -> int:
    basis_uom = _basis_uom_for_item(item)
    multiplier = uom_multiplier(item.dimension, basis_uom)
    if multiplier <= 0:
        raise ValueError("invalid_uom_multiplier")
    human_qty_for_cost = Decimal(int(qty_base)) / Decimal(multiplier)
    return _round_half_up_cents(Decimal(int(unit_cost_cents)) * human_qty_for_cost)


def _provided_purchase_source_ids(lines: list[dict]) -> list[str]:
    source_ids: list[str] = []
    for line in lines:
        source_id = line.get("source_id")
        if source_id is None:
            continue
        source_text = str(source_id).strip()
        if source_text and source_text not in source_ids:
            source_ids.append(source_text)
    return source_ids


def perform_stock_in_base(
    session: Session,
    item_id: str,
    qty_base: int,
    unit_cost_cents: int | None,
    ref: str | None,
    meta: dict | None,
) -> dict[str, Any]:
    qty = _require_qty_base(int(qty_base))
    unit_cost = int(unit_cost_cents or 0)
    source_kind = str((meta or {}).get("source_kind") or "stock_in")
    source_id = ref if ref is not None else (meta or {}).get("source_id")
    batch_id = add_batch(session, int(item_id), qty, unit_cost, source_kind, source_id)
    _append_inventory_journal(
        {
            "type": source_kind,
            "item_id": int(item_id),
            "qty_change": qty,
            "unit_cost_cents": unit_cost,
            "source_kind": source_kind,
            "source_id": source_id,
            "batch_id": int(batch_id) if batch_id is not None else None,
        }
    )
    return {"ok": True, "batch_id": int(batch_id) if batch_id is not None else None}


def perform_stock_out_base(
    session: Session,
    item_id: str,
    qty_base: int,
    ref: str | None,
    meta: dict | None,
) -> dict[str, Any]:
    qty = _require_qty_base(int(qty_base))
    item_int = int(item_id)
    data = dict(meta or {})
    reason = str(data.get("reason") or "sold")
    note = data.get("note")
    effective_source_id = ref

    if reason == "sold" and bool(data.get("record_cash_event", True)) is True:
        it = session.get(Item, item_int)
        if not it:
            raise LookupError("item_not_found")
        if (getattr(it, "dimension", None) or "").lower() != "count":
            raise ValueError("sold_cash_event_count_only")

        if data.get("sell_unit_price_cents") is not None:
            unit_price_cents = int(data["sell_unit_price_cents"])
        else:
            unit_price_cents = int(
                (Decimal(str(getattr(it, "price", 0) or 0)) * Decimal("100")).quantize(
                    Decimal("1"), rounding=ROUND_HALF_UP
                )
            )

        qty_each = Decimal(qty) / Decimal(1000)
        amount_cents = int((Decimal(unit_price_cents) * qty_each).quantize(Decimal("1"), rounding=ROUND_HALF_UP))

        source_id = ref or uuid.uuid4().hex
        effective_source_id = source_id
        moves = fifo_consume(session, item_int, qty, reason, source_id)
        session.add(
            CashEvent(
                kind="sale",
                category=None,
                amount_cents=amount_cents,
                item_id=item_int,
                qty_base=qty,
                unit_price_cents=unit_price_cents,
                source_kind="sold",
                source_id=source_id,
                related_source_id=None,
                notes=note,
            )
        )
    else:
        moves = fifo_consume(session, item_int, qty, reason, ref)

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
            "type": reason,
            "item_id": item_int,
            "qty_change": -qty,
            "unit_cost_cents": 0,
            "source_kind": reason,
            "source_id": effective_source_id or None,
        }
    )
    return {"ok": True, "lines": lines}


def perform_purchase_base(
    session: Session,
    vendor_id: str,
    lines: list[dict],
    *,
    category: str | None = None,
    notes: str | None = None,
    created_at: datetime | None = None,
) -> dict[str, Any]:
    created: list[int] = []
    cash_event_ids: list[int] = []
    source_ids = _provided_purchase_source_ids(lines)
    if len(source_ids) > 1:
        raise ValueError("multiple_purchase_source_ids_not_supported")
    source_id = source_ids[0] if source_ids else uuid.uuid4().hex
    effective_created_at = created_at or datetime.utcnow()

    for line in lines:
        qty = _require_qty_base(int(line.get("qty_base", 0)))
        item_id = int(line["item_id"])
        unit_cost = int(line.get("unit_cost_cents") or 0)
        source_kind = str(line.get("source_kind") or "purchase")
        item = session.get(Item, item_id)
        if item is None:
            raise LookupError("item_not_found")
        total_amount_cents = _purchase_total_amount_cents(unit_cost, qty, item)
        batch_id = add_batch(session, item_id, qty, unit_cost, source_kind, source_id)
        created.append(int(batch_id))
        cash_event = CashEvent(
            kind="expense",
            source_kind="purchase",
            source_id=source_id,
            category=category or "materials",
            amount_cents=-abs(total_amount_cents),
            item_id=item_id,
            qty_base=qty,
            unit_price_cents=unit_cost,
            related_source_id=None,
            notes=notes,
            created_at=effective_created_at,
        )
        session.add(cash_event)
        session.flush()
        if cash_event.id is not None:
            cash_event_ids.append(int(cash_event.id))
        _append_inventory_journal(
            {
                "type": "purchase",
                "item_id": item_id,
                "qty_change": qty,
                "unit_cost_cents": unit_cost,
                "source_kind": source_kind,
                "source_id": source_id,
                "batch_id": int(batch_id),
                "vendor_id": vendor_id,
            }
        )
    return {"ok": True, "source_id": source_id, "batch_ids": created, "cash_event_ids": cash_event_ids}
