# Copyright (C) 2025 BUS Core Authors
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
Pydantic schemas and helpers for manufacturing runs.
"""
from __future__ import annotations

from typing import Any, List, Union

from fastapi import HTTPException
from pydantic import BaseModel, Field, ValidationError


class ComponentInput(BaseModel):
    item_id: int
    quantity_decimal: str | None = None
    uom: str | None = None
    qty_required: float | None = Field(default=None, gt=0)
    is_optional: bool = False


class RecipeRunRequest(BaseModel):
    recipe_id: int = Field(..., gt=0)
    # Phase 2A+: quantity_decimal/uom are authoritative.
    # output_qty is legacy-only and must not be used for validation math.
    quantity_decimal: str
    uom: str
    output_qty: float = Field(..., gt=0)
    notes: str | None = None


class AdhocRunRequest(BaseModel):
    output_item_id: int = Field(..., gt=0)
    # Phase 2A+: quantity_decimal/uom are authoritative.
    # output_qty is legacy-only and must not be used for validation math.
    quantity_decimal: str
    uom: str
    output_qty: float = Field(..., gt=0)
    components: List[ComponentInput] = Field(..., min_length=1)
    notes: str | None = None


ManufacturingRunRequest = Union[RecipeRunRequest, AdhocRunRequest]


def _ensure_quantity_fields(payload: dict) -> None:
    if payload.get("quantity_decimal") is None:
        if payload.get("output_qty") is not None:
            payload["quantity_decimal"] = str(payload["output_qty"])
        elif payload.get("quantity") is not None:
            payload["quantity_decimal"] = str(payload["quantity"])
    payload.pop("quantity", None)

    if payload.get("quantity_decimal") is None:
        raise HTTPException(status_code=400, detail="quantity_decimal_required")
    if payload.get("uom") is None:
        raise HTTPException(status_code=400, detail="uom_required")

    if payload.get("output_qty") is None:
        legacy_value = payload.pop("_legacy_output_qty_float", None)
        if legacy_value is not None:
            payload["output_qty"] = float(legacy_value)
        else:
            payload["output_qty"] = float(str(payload["quantity_decimal"]))


def _normalize_components(payload: dict) -> None:
    components = payload.get("components")
    if not isinstance(components, list):
        return
    normalized: list[dict] = []
    for component in components:
        if not isinstance(component, dict):
            normalized.append(component)
            continue
        component_payload = dict(component)
        if component_payload.get("quantity_decimal") is None and component_payload.get("qty_required") is not None:
            component_payload["quantity_decimal"] = str(component_payload["qty_required"])
        if component_payload.get("qty_required") is None and component_payload.get("quantity_decimal") is not None:
            component_payload["qty_required"] = float(str(component_payload["quantity_decimal"]))
        normalized.append(component_payload)
    payload["components"] = normalized


def parse_run_request(payload: Any) -> ManufacturingRunRequest:
    if isinstance(payload, list):
        raise HTTPException(status_code=400, detail="single run only")
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="invalid payload")

    payload = dict(payload)
    _ensure_quantity_fields(payload)
    _normalize_components(payload)

    has_recipe = payload.get("recipe_id") is not None
    has_output_item = payload.get("output_item_id") is not None
    has_components = payload.get("components") is not None

    if has_recipe and (has_output_item or has_components):
        raise HTTPException(status_code=400, detail="recipe and ad-hoc payloads are mutually exclusive")

    try:
        if has_recipe:
            return RecipeRunRequest(**payload)
        if has_output_item or has_components:
            if not payload.get("components"):
                raise HTTPException(status_code=400, detail="components required for ad-hoc run")
            return AdhocRunRequest(**payload)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=exc.errors())

    raise HTTPException(status_code=400, detail="recipe_id or output_item_id required")


__all__ = [
    "AdhocRunRequest",
    "ComponentInput",
    "ManufacturingRunRequest",
    "RecipeRunRequest",
    "parse_run_request",
]
