# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from datetime import datetime
import uuid
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from sqlalchemy.orm import Session

from core.appdb.ledger import InsufficientStock, add_batch, fifo_consume
from core.appdb.models import CashEvent, Item
from core.journal.inventory import append_inventory


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
    except Exception:
        pass


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
        tx = session.begin_nested() if session.in_transaction() else session.begin()
        with tx:
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
        session.commit()

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
            "source_id": note or None,
        }
    )
    return {"ok": True, "lines": lines}


def perform_purchase_base(session: Session, vendor_id: str, lines: list[dict]) -> dict[str, Any]:
    created: list[int] = []
    for line in lines:
        qty = _require_qty_base(int(line.get("qty_base", 0)))
        item_id = int(line["item_id"])
        unit_cost = int(line.get("unit_cost_cents") or 0)
        source_kind = str(line.get("source_kind") or "purchase")
        source_id = line.get("source_id")
        batch_id = add_batch(session, item_id, qty, unit_cost, source_kind, source_id)
        created.append(int(batch_id))
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
    session.commit()
    return {"ok": True, "batch_ids": created}
