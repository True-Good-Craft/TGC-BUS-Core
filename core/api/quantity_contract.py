# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from fastapi import HTTPException

from core.metrics.metric import UNIT_MULTIPLIER, _norm_dimension, _norm_unit


def normalize_quantity_to_base_int(dimension: str, uom: str, quantity_decimal: str | Decimal) -> int:
    dim = _norm_dimension(dimension)
    normalized_uom = _norm_unit(uom)
    units_for_dim = UNIT_MULTIPLIER.get(dim, {})
    multiplier = units_for_dim.get(normalized_uom)
    if multiplier is None:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "bad_request",
                "message": "unsupported_uom",
                "fields": {
                    "dimension": dimension,
                    "uom": uom,
                    "normalized_uom": normalized_uom,
                },
            },
        )

    try:
        if isinstance(quantity_decimal, Decimal):
            qty_dec = quantity_decimal
        else:
            cleaned = str(quantity_decimal or "").strip().replace(",", "")
            if cleaned in ("", ".", "-.", "+."):
                raise InvalidOperation()
            if cleaned.startswith("."):
                cleaned = "0" + cleaned
            qty_dec = Decimal(cleaned)
    except (InvalidOperation, TypeError):
        raise HTTPException(
            status_code=400,
            detail={
                "error": "bad_request",
                "message": "invalid_quantity",
                "fields": {
                    "dimension": dimension,
                    "uom": uom,
                    "normalized_uom": normalized_uom,
                    "quantity_decimal": str(quantity_decimal),
                },
            },
        )

    qty_base = qty_dec * Decimal(multiplier)
    if qty_base != qty_base.to_integral_value():
        raise HTTPException(
            status_code=400,
            detail={
                "error": "bad_request",
                "message": "fractional_base_quantity_not_allowed",
                "fields": {
                    "dimension": dimension,
                    "uom": uom,
                    "normalized_uom": normalized_uom,
                    "quantity_decimal": str(qty_dec),
                },
            },
        )

    qty_int = int(qty_base)
    if qty_int <= 0:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "bad_request",
                "message": "invalid_quantity",
                "fields": {
                    "dimension": dimension,
                    "uom": uom,
                    "normalized_uom": normalized_uom,
                    "quantity_decimal": str(qty_dec),
                },
            },
        )

    return qty_int

