# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from io import StringIO
from typing import Iterator

from sqlalchemy import and_, exists, or_
from sqlalchemy.orm import Session

from core.appdb.models import CashEvent, Item, ItemMovement
from core.metrics.metric import default_unit_for, uom_multiplier

DEFAULT_EXPORT_CURRENCY = "CAD"
SUPPORTED_EXPORT_PROFILES = {"generic"}

FINANCE_EXPORT_COLUMNS = [
    "date",
    "bus_event_id",
    "kind",
    "source_kind",
    "source_id",
    "description",
    "amount_cents",
    "amount",
    "currency",
    "category",
    "suggested_account",
    "item_id",
    "item_name",
    "quantity_decimal",
    "uom",
    "unit_amount_cents",
    "notes",
]


class InvalidExportDate(ValueError):
    pass


@dataclass(frozen=True)
class ExportWindow:
    from_dt: datetime | None
    to_dt: datetime | None
    from_segment: str
    to_segment: str


def parse_export_window(from_value: str | None, to_value: str | None) -> ExportWindow:
    def parse_date(value: str | None) -> datetime | None:
        if value is None or value == "":
            return None
        try:
            parsed = datetime.strptime(value, "%Y-%m-%d")
        except ValueError as exc:
            raise InvalidExportDate("invalid_date") from exc
        return datetime(parsed.year, parsed.month, parsed.day, 0, 0, 0)

    from_dt = parse_date(from_value)
    to_start = parse_date(to_value)
    if from_dt is not None and to_start is not None and from_dt > to_start:
        raise InvalidExportDate("invalid_date")
    to_dt = to_start + timedelta(days=1) if to_start is not None else None
    return ExportWindow(
        from_dt=from_dt,
        to_dt=to_dt,
        from_segment=from_value or "all",
        to_segment=to_value or "all",
    )


def finance_export_filename(profile: str, window: ExportWindow) -> str:
    return f"BUS-Core-Finance-Export-{profile}-{window.from_segment}-to-{window.to_segment}.csv"


def _amount_decimal_string(amount_cents: int) -> str:
    amount = (Decimal(int(amount_cents)) / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"{amount:.2f}"


def _decimal_string(value: Decimal) -> str:
    text = format(value.normalize(), "f")
    if text in {"-0", "-0.0", "-0.00"}:
        return "0"
    return text


def _basis_uom_for_item(item: Item) -> str:
    basis_uom = item.uom or default_unit_for(item.dimension)
    if uom_multiplier(item.dimension, basis_uom) <= 0:
        basis_uom = default_unit_for(item.dimension)
    return basis_uom


def _human_qty_from_base(qty_base: int, item: Item) -> Decimal:
    basis_uom = _basis_uom_for_item(item)
    multiplier = uom_multiplier(item.dimension, basis_uom)
    if multiplier <= 0:
        raise ValueError("invalid_uom_multiplier")
    return Decimal(int(qty_base)) / Decimal(multiplier)


def _line_cost_cents(unit_cost_cents: int, qty_base: int, item: Item) -> int:
    human_qty = _human_qty_from_base(qty_base, item)
    return int((Decimal(int(unit_cost_cents)) * human_qty).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _date_string(value: datetime | None) -> str:
    if value is None:
        return ""
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return value.date().isoformat()


def _safe_text(value: object) -> str:
    return "" if value is None else str(value)


def _suggested_account(kind: str) -> str:
    return {
        "purchase": "Materials",
        "purchase_inferred": "Materials",
        "expense": "Expense",
        "sale": "Sales",
        "refund": "Refunds",
        "cogs": "Cost of Goods Sold",
    }.get(kind, "")


def _cash_event_kind(event: CashEvent) -> str:
    if event.kind == "expense" and event.source_kind == "purchase":
        return "purchase"
    return str(event.kind)


def _description(kind: str, item_name: str) -> str:
    labels = {
        "purchase": "Purchase",
        "purchase_inferred": "Legacy purchase",
        "expense": "Expense",
        "sale": "Sale",
        "refund": "Refund",
    }
    label = labels.get(kind, kind)
    return f"{label}: {item_name}" if item_name else label


def _empty_row() -> dict[str, str]:
    return {column: "" for column in FINANCE_EXPORT_COLUMNS}


def _cash_event_row(event: CashEvent, item: Item | None) -> dict[str, str]:
    kind = _cash_event_kind(event)
    amount_cents = int(event.amount_cents)
    item_name = _safe_text(item.name) if item is not None else ""
    row = _empty_row()
    row.update(
        {
            "date": _date_string(event.created_at),
            "bus_event_id": f"cash_event:{int(event.id)}",
            "kind": kind,
            "source_kind": _safe_text(event.source_kind),
            "source_id": _safe_text(event.source_id),
            "description": _description(kind, item_name),
            "amount_cents": str(amount_cents),
            "amount": _amount_decimal_string(amount_cents),
            "currency": DEFAULT_EXPORT_CURRENCY,
            "category": _safe_text(event.category),
            "suggested_account": _suggested_account(kind),
            "item_id": str(int(event.item_id)) if event.item_id is not None else "",
            "item_name": item_name,
            "unit_amount_cents": str(int(event.unit_price_cents)) if event.unit_price_cents is not None else "",
            "notes": _safe_text(event.notes),
        }
    )
    if event.qty_base is not None and item is not None:
        row["quantity_decimal"] = _decimal_string(_human_qty_from_base(int(event.qty_base), item))
        row["uom"] = _basis_uom_for_item(item)
    return row


def _legacy_purchase_row(move: ItemMovement, item: Item) -> dict[str, str]:
    qty_base = int(move.qty_change)
    amount_cents = _line_cost_cents(int(move.unit_cost_cents or 0), qty_base, item)
    item_name = _safe_text(item.name)
    row = _empty_row()
    row.update(
        {
            "date": _date_string(move.created_at),
            "bus_event_id": f"movement:{int(move.id)}",
            "kind": "purchase_inferred",
            "source_kind": _safe_text(move.source_kind),
            "source_id": _safe_text(move.source_id),
            "description": _description("purchase_inferred", item_name),
            "amount_cents": str(amount_cents),
            "amount": _amount_decimal_string(amount_cents),
            "currency": DEFAULT_EXPORT_CURRENCY,
            "suggested_account": _suggested_account("purchase_inferred"),
            "item_id": str(int(move.item_id)),
            "item_name": item_name,
            "quantity_decimal": _decimal_string(_human_qty_from_base(qty_base, item)),
            "uom": _basis_uom_for_item(item),
            "unit_amount_cents": str(int(move.unit_cost_cents or 0)),
        }
    )
    return row


def _apply_cash_event_window(query, window: ExportWindow):
    if window.from_dt is not None:
        query = query.filter(CashEvent.created_at >= window.from_dt)
    if window.to_dt is not None:
        query = query.filter(CashEvent.created_at < window.to_dt)
    return query


def _apply_movement_window(query, window: ExportWindow):
    if window.from_dt is not None:
        query = query.filter(ItemMovement.created_at >= window.from_dt)
    if window.to_dt is not None:
        query = query.filter(ItemMovement.created_at < window.to_dt)
    return query


def iter_finance_export_rows(db: Session, window: ExportWindow) -> Iterator[dict[str, str]]:
    cash_events = _apply_cash_event_window(
        db.query(CashEvent, Item).outerjoin(Item, CashEvent.item_id == Item.id),
        window,
    ).order_by(CashEvent.created_at.asc(), CashEvent.id.asc())
    for event, item in cash_events.yield_per(100):
        yield _cash_event_row(event, item)

    legacy_purchases = _apply_movement_window(
        db.query(ItemMovement, Item)
        .join(Item, ItemMovement.item_id == Item.id)
        .filter(ItemMovement.source_kind == "purchase")
        .filter(ItemMovement.qty_change > 0)
        .filter(
            or_(
                ItemMovement.source_id.is_(None),
                ~exists().where(
                    and_(
                        CashEvent.source_id == ItemMovement.source_id,
                        CashEvent.source_kind == "purchase",
                        CashEvent.kind == "expense",
                    )
                ),
            )
        ),
        window,
    ).order_by(ItemMovement.created_at.asc(), ItemMovement.id.asc())
    for move, item in legacy_purchases.yield_per(100):
        yield _legacy_purchase_row(move, item)


def stream_finance_export_csv(db: Session, window: ExportWindow) -> Iterator[str]:
    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=FINANCE_EXPORT_COLUMNS, lineterminator="\n")
    writer.writeheader()
    yield buffer.getvalue()
    buffer.seek(0)
    buffer.truncate(0)

    for row in iter_finance_export_rows(db, window):
        writer.writerow(row)
        yield buffer.getvalue()
        buffer.seek(0)
        buffer.truncate(0)
