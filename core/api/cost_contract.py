# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from fastapi import HTTPException

from core.metrics.metric import UNIT_MULTIPLIER, _norm_dimension, _norm_unit


def normalize_cost_to_base_cents(dimension: str, cost_uom: str, unit_cost_decimal: str | Decimal) -> int:
    dim = _norm_dimension(dimension)
    normalized_uom = _norm_unit(cost_uom)
    units_for_dim = UNIT_MULTIPLIER.get(dim, {})
    multiplier = units_for_dim.get(normalized_uom)
    if multiplier is None:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "bad_request",
                "message": "unsupported_cost_uom",
                "fields": {
                    "dimension": dimension,
                    "cost_uom": cost_uom,
                    "normalized_cost_uom": normalized_uom,
                },
            },
        )

    try:
        if isinstance(unit_cost_decimal, Decimal):
            unit_cost_dec = unit_cost_decimal
        else:
            cleaned = str(unit_cost_decimal or "").strip().replace(",", "")
            if cleaned in ("", ".", "-.", "+."):
                raise InvalidOperation()
            if cleaned.startswith("."):
                cleaned = "0" + cleaned
            unit_cost_dec = Decimal(cleaned)
    except (InvalidOperation, TypeError):
        raise HTTPException(
            status_code=400,
            detail={
                "error": "bad_request",
                "message": "invalid_unit_cost",
                "fields": {
                    "dimension": dimension,
                    "cost_uom": cost_uom,
                    "normalized_cost_uom": normalized_uom,
                    "unit_cost_decimal": str(unit_cost_decimal),
                },
            },
        )

    if unit_cost_dec < 0:
        raise HTTPException(status_code=400, detail="invalid_unit_cost")

    # Deterministic rounding rule: ROUND_HALF_UP to integer cents per base unit.
    cents_per_human_unit = unit_cost_dec * Decimal("100")
    cents_per_base_unit = (cents_per_human_unit / Decimal(multiplier)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(cents_per_base_unit)
