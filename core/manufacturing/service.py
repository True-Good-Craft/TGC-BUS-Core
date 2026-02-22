# SPDX-License-Identifier: AGPL-3.0-or-later
"""Shared manufacturing service utilities."""

from __future__ import annotations

import json
from contextlib import wraps
from datetime import datetime
from typing import Callable, Dict, List, Tuple

from fastapi import HTTPException
from sqlalchemy.orm import Session

from core.api.schemas.manufacturing import (
    AdhocRunRequest,
    ManufacturingRunRequest,
    RecipeRunRequest,
)
from core.api.quantity_contract import normalize_quantity_to_base_int
from core.metrics.metric import default_unit_for
from core.appdb.ledger import InsufficientStock, on_hand_qty
from core.appdb.models import Item, ItemBatch, ItemMovement
from core.appdb.models_recipes import Recipe, RecipeItem
from core.money import round_half_up_cents


def transactional(func: Callable):
    @wraps(func)
    def wrapper(session: Session, *args, **kwargs):
        on_before_commit = kwargs.pop("on_before_commit", None)
        try:
            result = func(session, *args, **kwargs)
            if on_before_commit:
                on_before_commit(result)
            session.commit()
            return result
        except HTTPException:
            session.rollback()
            raise
        except Exception:
            session.rollback()
            raise

    return wrapper


class fifo:
    @staticmethod
    def allocate(session: Session, item_id: int, qty: float) -> List[dict]:
        qty_int = int(qty)
        if qty_int <= 0:
            return []

        batches = (
            session.query(ItemBatch)
            .filter(ItemBatch.item_id == item_id, ItemBatch.qty_remaining > 0)
            .order_by(ItemBatch.created_at, ItemBatch.id)
            .with_for_update()
            .all()
        )
        available = sum(int(b.qty_remaining) for b in batches)
        if available < qty_int:
            raise InsufficientStock(
                [
                    {
                        "item_id": item_id,
                        "required": qty,
                        "on_hand": available,
                        "missing": qty - available,
                    }
                ]
            )

        allocations: List[dict] = []
        remaining = qty_int
        for batch in batches:
            if remaining <= 0:
                break
            take = min(int(batch.qty_remaining), int(remaining))
            if take <= 0:
                continue
            batch.qty_remaining = int(batch.qty_remaining) - take
            remaining -= take
            allocations.append(
                {
                    "item_id": item_id,
                    "batch_id": batch.id,
                    "qty": take,
                    "unit_cost_cents": batch.unit_cost_cents,
                }
            )

        return allocations


def format_shortages(shortages: List[dict]) -> List[dict]:
    formatted = []
    for shortage in shortages:
        formatted.append(
            {
                "item_id": shortage.get("item_id"),
                "required": int(shortage.get("required", 0)),
                "available": int(shortage.get("available", shortage.get("on_hand", 0))),
            }
        )
    return formatted


def validate_run(
    session: Session, body: ManufacturingRunRequest
) -> Tuple[int, list[dict], float, list[dict]]:
    """Validate a manufacturing run request before any writes occur.

    Returns a tuple of (output_item_id, required_components, scale_k, shortages).
    Shortages are returned formatted but do not raise; caller decides how to respond.
    """
    if isinstance(body, RecipeRunRequest):
        recipe = session.get(Recipe, body.recipe_id)
        if not recipe:
            raise HTTPException(status_code=404, detail="Recipe not found")
        if not recipe.output_item_id:
            raise HTTPException(status_code=400, detail="Recipe has no output_item_id")

        output_item_id = recipe.output_item_id
        k = body.output_qty / (recipe.output_qty or 1.0)
        required = []
        raw_required_qtys: List[float] = []
        for it in (
            session.query(RecipeItem)
            .filter(RecipeItem.recipe_id == recipe.id)
            .order_by(RecipeItem.sort_order)
            .all()
        ):
            item = session.get(Item, it.item_id)
            if not item:
                raise HTTPException(status_code=404, detail=f"Item {it.item_id} not found")
            base_uom = default_unit_for(item.dimension)
            qty_base = normalize_quantity_to_base_int(
                item.dimension,
                base_uom,
                float(it.qty_required) * k,
            )
            original_requested_qty = float(it.qty_required) * k
            if (float(original_requested_qty) > 0) and qty_base <= 0:
                raise HTTPException(
                    status_code=400,
                    detail="invalid_normalized_quantity",
                )
            required.append(
                {
                    "item_id": it.item_id,
                    "qty_base": qty_base,
                    "is_optional": bool(it.is_optional),
                }
            )
            raw_required_qtys.append(original_requested_qty)
    elif isinstance(body, AdhocRunRequest):
        output_item_id = body.output_item_id
        k = 1.0
        required = []
        raw_required_qtys: List[float] = []
        for c in body.components:
            item = session.get(Item, c.item_id)
            if not item:
                raise HTTPException(status_code=404, detail=f"Item {c.item_id} not found")
            base_uom = default_unit_for(item.dimension)
            qty_base = normalize_quantity_to_base_int(item.dimension, base_uom, c.qty_required)
            original_requested_qty = float(c.qty_required)
            if (float(original_requested_qty) > 0) and qty_base <= 0:
                raise HTTPException(
                    status_code=400,
                    detail="invalid_normalized_quantity",
                )
            required.append(
                {
                    "item_id": c.item_id,
                    "qty_base": qty_base,
                    "is_optional": bool(c.is_optional),
                }
            )
            raw_required_qtys.append(original_requested_qty)
    else:  # pragma: no cover - defensive
        raise HTTPException(status_code=400, detail="invalid payload")

    shortages: List[dict] = []
    for idx, r in enumerate(required):
        if r["is_optional"]:
            continue
        on_hand = on_hand_qty(session, r["item_id"])
        shortage_amount = max(r["qty_base"] - on_hand, 0)
        print(
            ">>> VALIDATE_RUN DEBUG "
            f"item_id={r['item_id']} "
            f"raw_required_qty={raw_required_qtys[idx]} "
            f"qty_base={r['qty_base']} "
            f"on_hand_qty={on_hand} "
            f"shortage_amount={shortage_amount}"
        )
        if on_hand < r["qty_base"]:
            shortages.append(
                {"item_id": r["item_id"], "required": r["qty_base"], "available": on_hand}
            )

    formatted_shortages = format_shortages(shortages)

    return output_item_id, required, k, formatted_shortages


@transactional
def execute_run_txn(
    session: Session,
    body: ManufacturingRunRequest,
    output_item_id: int,
    required: list[dict],
    k: float,
):
    from core.appdb.models_recipes import ManufacturingRun

    mfg_run = ManufacturingRun(
        recipe_id=getattr(body, "recipe_id", None),
        output_item_id=output_item_id,
        output_qty=0,
        status="created",
        notes=getattr(body, "notes", None),
    )
    session.add(mfg_run)
    session.flush()

    output_item = session.get(Item, output_item_id)
    if not output_item:
        raise HTTPException(status_code=404, detail=f"Item {output_item_id} not found")
    output_base_uom = default_unit_for(output_item.dimension)
    output_qty_base = normalize_quantity_to_base_int(
        output_item.dimension,
        output_base_uom,
        body.output_qty,
    )
    mfg_run.output_qty = output_qty_base

    allocations: List[dict] = []
    consumed_per_item: dict[int, int] = {}
    movement_rows: List[ItemMovement] = []
    for r in required:
        required_base = r["qty_base"]
        if required_base <= 0:
            continue
        if r["is_optional"]:
            if on_hand_qty(session, r["item_id"]) < required_base:
                continue
        slices = fifo.allocate(session, r["item_id"], required_base)
        for alloc in slices:
            allocations.append(alloc)
            consumed_per_item[alloc["item_id"]] = consumed_per_item.get(alloc["item_id"], 0) + alloc[
                "qty"
            ]
    cost_inputs_cents = 0
    for alloc in allocations:
        mv = ItemMovement(
            item_id=alloc["item_id"],
            batch_id=alloc["batch_id"],
            qty_change=-alloc["qty"],
            unit_cost_cents=alloc["unit_cost_cents"],
            source_kind="manufacturing",
            source_id=mfg_run.id,
            is_oversold=False,
        )
        session.add(mv)
        movement_rows.append(mv)
        unit_cost = int(alloc["unit_cost_cents"] or 0)
        cost_inputs_cents += int(alloc["qty"]) * unit_cost

    per_output_cents = round_half_up_cents(cost_inputs_cents / max(float(output_qty_base or 0), 1e-9))
    output_batch = ItemBatch(
        item_id=output_item_id,
        qty_initial=output_qty_base,
        qty_remaining=output_qty_base,
        unit_cost_cents=per_output_cents,
        source_kind="manufacturing",
        source_id=mfg_run.id,
        is_oversold=False,
    )
    session.add(output_batch)
    session.flush()

    try:
        from core.logging import log

        log.info(
            "mfg:cost",
            extra={
                "inputs_cents": cost_inputs_cents,
                "out_qty_base": output_qty_base,
                "per_out_cents": per_output_cents,
            },
        )
    except Exception:
        pass

    output_mv = ItemMovement(
        item_id=output_item_id,
        batch_id=output_batch.id,
        qty_change=output_qty_base,
        unit_cost_cents=per_output_cents,
        source_kind="manufacturing",
        source_id=mfg_run.id,
        is_oversold=False,
    )
    session.add(output_mv)
    movement_rows.append(output_mv)

    for item_id, qty in consumed_per_item.items():
        item = session.get(Item, item_id)
        if item:
            item.qty_stored = (item.qty_stored or 0) - qty

    if output_item:
        output_item.qty_stored = (output_item.qty_stored or 0) + output_qty_base

    mfg_run.status = "completed"
    mfg_run.executed_at = datetime.utcnow()
    mfg_run.meta = json.dumps(
        {
            "k": k,
            "cost_inputs_cents": cost_inputs_cents,
            "per_output_cents": per_output_cents,
            "allocations": allocations,
            "output_batch_id": output_batch.id,
        }
    )

    journal_entry = {
        "run_id": mfg_run.id,
        "recipe_id": getattr(body, "recipe_id", None),
        "output_item_id": output_item_id,
        "output_qty": output_qty_base,
        "allocations": allocations,
        "output_batch_id": output_batch.id,
        "per_output_cents": per_output_cents,
        "cost_inputs_cents": cost_inputs_cents,
    }

    session.flush()

    return {
        "run": mfg_run,
        "journal_entry": journal_entry,
        "output_unit_cost_cents": per_output_cents,
        "movement_rows": movement_rows,
    }


__all__ = ["execute_run_txn", "fifo", "format_shortages", "validate_run"]
