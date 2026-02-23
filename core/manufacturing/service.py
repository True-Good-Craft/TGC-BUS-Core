# SPDX-License-Identifier: AGPL-3.0-or-later
"""Shared manufacturing service utilities."""

from __future__ import annotations

import json
from contextlib import wraps
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Callable, List, Tuple

from fastapi import HTTPException
from sqlalchemy.orm import Session

from core.api.schemas.manufacturing import (
    AdhocRunRequest,
    ManufacturingRunRequest,
    RecipeRunRequest,
)
from core.appdb.ledger import InsufficientStock, on_hand_qty
from core.appdb.models import Item, ItemBatch, ItemMovement
from core.appdb.models_recipes import Recipe, RecipeItem
from core.metrics.metric import default_unit_for, normalize_quantity_to_base_int, uom_multiplier
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
    def allocate(session: Session, item_id: int, qty: int) -> List[dict]:
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
                        "required": qty_int,
                        "on_hand": available,
                        "missing": qty_int - available,
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
    return [
        {
            "item_id": int(shortage.get("item_id")),
            "required": int(shortage.get("required", 0)),
            "available": int(shortage.get("available", shortage.get("on_hand", 0))),
        }
        for shortage in shortages
    ]


def _to_base_qty_for_item(session: Session, item_id: int, quantity_decimal: str, uom: str) -> int:
    item = session.get(Item, int(item_id))
    if item is None:
        raise HTTPException(status_code=404, detail=f"item_not_found:{item_id}")
    dimension = getattr(item, "dimension", None) or "count"
    return int(normalize_quantity_to_base_int(quantity_decimal=quantity_decimal, uom=uom, dimension=dimension))


def _scale_ratio(output_qty_base: int, recipe_output_qty_base: int) -> Decimal:
    if int(recipe_output_qty_base) <= 0:
        raise ValueError("recipe_output_qty_base_must_be_positive")
    return Decimal(int(output_qty_base)) / Decimal(int(recipe_output_qty_base))


def _basis_uom_for_item(item: Item) -> str:
    dimension = getattr(item, "dimension", None) or "count"
    item_uom = getattr(item, "uom", None)
    try:
        uom_multiplier(dimension, str(item_uom))
        return str(item_uom)
    except Exception:
        return default_unit_for(dimension)


def _human_qty_from_base(qty_base: int, dimension: str, basis_uom: str) -> Decimal:
    mult = uom_multiplier(dimension, basis_uom)
    if int(mult) <= 0:
        raise ValueError("invalid_uom_multiplier")
    return Decimal(int(qty_base)) / Decimal(int(mult))


def _cost_cents_for_base_qty(unit_cost_cents: int, qty_base: int, item: Item) -> int:
    human_qty = _human_qty_from_base(
        qty_base=qty_base,
        dimension=getattr(item, "dimension", None) or "count",
        basis_uom=_basis_uom_for_item(item),
    )
    return round_half_up_cents(Decimal(int(unit_cost_cents)) * human_qty)


def validate_run(
    session: Session, body: ManufacturingRunRequest
) -> Tuple[int, list[dict], int, list[dict]]:
    if isinstance(body, RecipeRunRequest):
        recipe = session.get(Recipe, body.recipe_id)
        if not recipe:
            raise HTTPException(status_code=404, detail="Recipe not found")
        if not recipe.output_item_id:
            raise HTTPException(status_code=400, detail="Recipe has no output_item_id")

        output_item_id = int(recipe.output_item_id)
        output_qty_base = _to_base_qty_for_item(session, output_item_id, body.quantity_decimal, body.uom)
        recipe_output_qty_base = int(recipe.output_qty or 0)
        try:
            scale = _scale_ratio(output_qty_base, recipe_output_qty_base)
        except ValueError:
            raise HTTPException(status_code=400, detail="Recipe has invalid output quantity")

        required: list[dict] = []
        for it in (
            session.query(RecipeItem)
            .filter(RecipeItem.recipe_id == recipe.id)
            .order_by(RecipeItem.sort_order)
            .all()
        ):
            required_base = int(
                (Decimal(int(it.qty_required)) * scale).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
            )
            required.append(
                {
                    "item_id": int(it.item_id),
                    "required_base": required_base,
                    "is_optional": bool(it.is_optional),
                }
            )
    elif isinstance(body, AdhocRunRequest):
        output_item_id = int(body.output_item_id)
        output_qty_base = _to_base_qty_for_item(session, output_item_id, body.quantity_decimal, body.uom)
        required = []
        for c in body.components:
            if c.quantity_decimal is None or c.uom is None:
                raise HTTPException(status_code=400, detail="adhoc_component_quantity_decimal_and_uom_required")
            required_base = _to_base_qty_for_item(session, c.item_id, c.quantity_decimal, c.uom)
            required.append(
                {
                    "item_id": int(c.item_id),
                    "required_base": int(required_base),
                    "is_optional": bool(c.is_optional),
                }
            )
    else:  # pragma: no cover
        raise HTTPException(status_code=400, detail="invalid payload")

    shortages: List[dict] = []
    for r in required:
        if r["is_optional"]:
            continue
        on_hand_base = int(on_hand_qty(session, r["item_id"]))
        required_base = int(r["required_base"])
        shortage_base = max(required_base - on_hand_base, 0)
        if shortage_base > 0:
            shortages.append({"item_id": r["item_id"], "required": required_base, "available": on_hand_base})

    return output_item_id, required, output_qty_base, format_shortages(shortages)


@transactional
def execute_run_txn(
    session: Session,
    body: ManufacturingRunRequest,
    output_item_id: int,
    required_components: list[dict],
    output_qty_base: int,
):
    from core.appdb.models_recipes import ManufacturingRun

    mfg_run = ManufacturingRun(
        recipe_id=getattr(body, "recipe_id", None),
        output_item_id=output_item_id,
        output_qty=int(output_qty_base),
        status="created",
        notes=getattr(body, "notes", None),
    )
    session.add(mfg_run)
    session.flush()

    allocations: List[dict] = []
    consumed_per_item_base: dict[int, int] = {}
    for r in required_components:
        required_base = int(r["required_base"])
        if required_base <= 0:
            continue
        if r["is_optional"]:
            if int(on_hand_qty(session, r["item_id"])) < required_base:
                continue
        slices = fifo.allocate(session, r["item_id"], required_base)
        for alloc in slices:
            allocations.append(alloc)
            consumed_per_item_base[alloc["item_id"]] = (
                consumed_per_item_base.get(alloc["item_id"], 0) + int(alloc["qty"])
            )

    cost_inputs_cents = 0
    item_cache: dict[int, Item] = {}
    for alloc in allocations:
        mv = ItemMovement(
            item_id=alloc["item_id"],
            batch_id=alloc["batch_id"],
            qty_change=-int(alloc["qty"]),
            unit_cost_cents=alloc["unit_cost_cents"],
            source_kind="manufacturing",
            source_id=mfg_run.id,
            is_oversold=False,
        )
        session.add(mv)
        alloc_item_id = int(alloc["item_id"])
        item = item_cache.get(alloc_item_id)
        if item is None:
            item = session.get(Item, alloc_item_id)
            if item is None:
                raise HTTPException(status_code=404, detail=f"item_not_found:{alloc_item_id}")
            item_cache[alloc_item_id] = item
        alloc_qty_base = int(alloc["qty"])
        unit_cost_cents = int(alloc["unit_cost_cents"] or 0)
        cost_inputs_cents += _cost_cents_for_base_qty(unit_cost_cents, alloc_qty_base, item)

    output_item = session.get(Item, output_item_id)
    if output_item is None:
        raise HTTPException(status_code=404, detail=f"item_not_found:{output_item_id}")
    output_human_qty = _human_qty_from_base(
        output_qty_base,
        getattr(output_item, "dimension", None) or "count",
        _basis_uom_for_item(output_item),
    )
    if output_human_qty <= 0:
        raise HTTPException(status_code=400, detail="invalid_output_qty")
    per_output_cents = round_half_up_cents(Decimal(cost_inputs_cents) / output_human_qty)
    output_batch = ItemBatch(
        item_id=output_item_id,
        qty_initial=int(output_qty_base),
        qty_remaining=int(output_qty_base),
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
                "out_qty_base": int(output_qty_base),
                "per_out_cents": per_output_cents,
            },
        )
    except Exception:
        pass

    session.add(
        ItemMovement(
            item_id=output_item_id,
            batch_id=output_batch.id,
            qty_change=int(output_qty_base),
            unit_cost_cents=per_output_cents,
            source_kind="manufacturing",
            source_id=mfg_run.id,
            is_oversold=False,
        )
    )

    for item_id, qty_base in consumed_per_item_base.items():
        item = session.get(Item, item_id)
        if item:
            item.qty_stored = int(item.qty_stored or 0) - int(qty_base)

    if output_item:
        output_item.qty_stored = int(output_item.qty_stored or 0) + int(output_qty_base)

    mfg_run.status = "completed"
    mfg_run.executed_at = datetime.utcnow()
    mfg_run.meta = json.dumps(
        {
            "output_qty_base": int(output_qty_base),
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
        "output_qty_base": int(output_qty_base),
        "component_allocations": [
            {
                "item_id": int(alloc["item_id"]),
                "batch_id": int(alloc["batch_id"]),
                "consumed_qty_base": int(alloc["qty"]),
                "unit_cost_cents": int(alloc["unit_cost_cents"] or 0),
            }
            for alloc in allocations
        ],
        "output_batch_id": output_batch.id,
        "per_output_cents": per_output_cents,
        "cost_inputs_cents": cost_inputs_cents,
    }

    return {
        "run": mfg_run,
        "journal_entry": journal_entry,
        "output_unit_cost_cents": per_output_cents,
    }


__all__ = ["execute_run_txn", "fifo", "format_shortages", "validate_run"]
