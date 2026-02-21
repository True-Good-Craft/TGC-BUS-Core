# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from dataclasses import asdict, dataclass

from sqlalchemy import func
from sqlalchemy.orm import Session

from core.appdb.models import CashEvent, ItemBatch, ItemMovement


@dataclass(frozen=True)
class IntegrityReport:
    ok: bool
    issues: list[dict]

    def to_dict(self) -> dict:
        return asdict(self)


def validate_inventory_integrity(session: Session) -> IntegrityReport:
    issues: list[dict] = []

    bad_batches = session.query(ItemBatch.id).filter(ItemBatch.qty_remaining < 0).all()
    for (batch_id,) in bad_batches:
        issues.append({"code": "batch_negative_qty_remaining", "batch_id": int(batch_id)})

    orphan_movements = (
        session.query(ItemMovement.id, ItemMovement.batch_id)
        .outerjoin(ItemBatch, ItemMovement.batch_id == ItemBatch.id)
        .filter(ItemMovement.batch_id.isnot(None))
        .filter(ItemBatch.id.is_(None))
        .all()
    )
    for movement_id, batch_id in orphan_movements:
        issues.append(
            {
                "code": "movement_references_missing_batch",
                "movement_id": int(movement_id),
                "batch_id": int(batch_id),
            }
        )

    null_cost_neg_moves = (
        session.query(ItemMovement.id)
        .filter(ItemMovement.qty_change < 0)
        .filter(ItemMovement.unit_cost_cents.is_(None))
        .all()
    )
    for (movement_id,) in null_cost_neg_moves:
        issues.append({"code": "negative_movement_null_unit_cost", "movement_id": int(movement_id)})

    neg_cost_batches = (
        session.query(ItemBatch.id)
        .filter((ItemBatch.qty_initial * func.coalesce(ItemBatch.unit_cost_cents, 0)) < 0)
        .all()
    )
    for (batch_id,) in neg_cost_batches:
        issues.append({"code": "batch_negative_aggregate_cost", "batch_id": int(batch_id)})

    return IntegrityReport(ok=len(issues) == 0, issues=issues)


def validate_finance_integrity(session: Session) -> IntegrityReport:
    issues: list[dict] = []

    sales = session.query(CashEvent).filter(CashEvent.kind == "sale").all()

    for sale in sales:
        linked = (
            session.query(ItemMovement)
            .filter(ItemMovement.source_id == sale.source_id)
            .all()
        )

        linked_negative = [m for m in linked if int(m.qty_change) < 0]
        if not linked_negative:
            issues.append(
                {
                    "code": "sale_missing_negative_movements",
                    "cash_event_id": int(sale.id),
                    "source_id": str(sale.source_id) if sale.source_id is not None else "",
                }
            )
            continue

        for m in linked:
            if int(m.qty_change) >= 0:
                issues.append(
                    {
                        "code": "sale_linked_non_negative_movement",
                        "cash_event_id": int(sale.id),
                        "movement_id": int(m.id),
                    }
                )

        cogs_cents = sum(abs(int(m.qty_change)) * int(m.unit_cost_cents or 0) for m in linked_negative)
        if cogs_cents > int(sale.amount_cents):
            issues.append(
                {
                    "code": "sale_cogs_exceeds_sale_amount",
                    "cash_event_id": int(sale.id),
                    "sale_amount_cents": int(sale.amount_cents),
                    "cogs_cents": int(cogs_cents),
                }
            )

    refunds = session.query(CashEvent).filter(CashEvent.kind == "refund").all()
    for refund in refunds:
        refund_neg_linked = (
            session.query(ItemMovement.id)
            .filter(ItemMovement.source_id == refund.source_id)
            .filter(ItemMovement.qty_change < 0)
            .all()
        )
        for (movement_id,) in refund_neg_linked:
            issues.append(
                {
                    "code": "refund_linked_negative_movement_not_cogs",
                    "cash_event_id": int(refund.id),
                    "movement_id": int(movement_id),
                }
            )

    return IntegrityReport(ok=len(issues) == 0, issues=issues)
