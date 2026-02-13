# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import func
from sqlalchemy.orm import Session

from core.appdb.models import CashEvent, ItemBatch, ItemMovement, ManufacturingRun


@dataclass(frozen=True)
class FinanceSummary:
    gross_revenue_cents: int
    refunds_cents: int
    net_revenue_cents: int
    cogs_cents: int
    gross_profit_cents: int
    margin_percent: float


def get_inventory_value(session: Session) -> int:
    total = (
        session.query(func.sum(ItemBatch.qty_remaining * func.coalesce(ItemBatch.unit_cost_cents, 0)))
        .filter(ItemBatch.qty_remaining > 0)
        .scalar()
    )
    return int(total or 0)




def get_item_inventory_value(session: Session, item_id: int) -> int:
    total = (
        session.query(func.sum(ItemBatch.qty_remaining * func.coalesce(ItemBatch.unit_cost_cents, 0)))
        .filter(ItemBatch.item_id == int(item_id))
        .filter(ItemBatch.qty_remaining > 0)
        .scalar()
    )
    return int(total or 0)


def get_item_on_hand_quantity(session: Session, item_id: int) -> int:
    total = (
        session.query(func.sum(ItemBatch.qty_remaining))
        .filter(ItemBatch.item_id == int(item_id))
        .filter(ItemBatch.qty_remaining > 0)
        .scalar()
    )
    return int(total or 0)
def get_units_produced(session: Session, start_dt: datetime, end_dt: datetime) -> int:
    run_ts_col = ManufacturingRun.executed_at if hasattr(ManufacturingRun, "executed_at") else ManufacturingRun.created_at
    total = (
        session.query(func.sum(ManufacturingRun.output_qty))
        .filter(ManufacturingRun.status == "completed")
        .filter(run_ts_col >= start_dt)
        .filter(run_ts_col < end_dt)
        .scalar()
    )
    return int(total or 0)


def get_finance_summary(session: Session, start_dt: datetime, end_dt: datetime) -> FinanceSummary:
    gross = (
        session.query(func.sum(CashEvent.amount_cents))
        .filter(CashEvent.kind == "sale")
        .filter(CashEvent.created_at >= start_dt)
        .filter(CashEvent.created_at < end_dt)
        .scalar()
    )
    refunds_raw = (
        session.query(func.sum(CashEvent.amount_cents))
        .filter(CashEvent.kind == "refund")
        .filter(CashEvent.created_at >= start_dt)
        .filter(CashEvent.created_at < end_dt)
        .scalar()
    )
    cogs = (
        session.query(func.sum(func.abs(ItemMovement.qty_change) * func.coalesce(ItemMovement.unit_cost_cents, 0)))
        .join(CashEvent, ItemMovement.source_id == CashEvent.source_id)
        .filter(CashEvent.kind == "sale")
        .filter(CashEvent.created_at >= start_dt)
        .filter(CashEvent.created_at < end_dt)
        .filter(ItemMovement.qty_change < 0)
        .scalar()
    )

    gross_revenue_cents = int(gross or 0)
    refunds_cents = abs(int(refunds_raw or 0))
    cogs_cents = int(cogs or 0)

    net_revenue_cents = gross_revenue_cents - refunds_cents
    gross_profit_cents = net_revenue_cents - cogs_cents

    if net_revenue_cents == 0:
        margin_percent = 0.0
    else:
        margin_percent = float(
            ((Decimal(gross_profit_cents) / Decimal(net_revenue_cents)) * Decimal(100)).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        )

    return FinanceSummary(
        gross_revenue_cents=gross_revenue_cents,
        refunds_cents=refunds_cents,
        net_revenue_cents=net_revenue_cents,
        cogs_cents=cogs_cents,
        gross_profit_cents=gross_profit_cents,
        margin_percent=margin_percent,
    )
