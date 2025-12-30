# Copyright (C) 2025 BUS Core Authors
# SPDX-License-Identifier: AGPL-3.0-or-later

# core/api/schemas_measure.py
from pydantic import BaseModel, Field, field_validator
from typing import Literal

from core.metrics import metric

Dimension = Literal["length", "area", "volume", "weight", "count"]

UOM = Literal[
    "mm",
    "cm",
    "m",
    "mm2",
    "cm2",
    "m2",
    "mm3",
    "cm3",
    "ml",
    "l",
    "m3",
    "mg",
    "g",
    "kg",
    "mc",
    "ea",
]


class QuantityStored(BaseModel):
    dimension: Dimension
    uom: UOM
    qty_stored: int = Field(
        ..., description="Canonical stored quantity (metric ×100 for g/mm/mm2/mm3, plain int for ea)"
    )

    @field_validator("uom")
    @classmethod
    def _validate_dimension_uom(cls, uom: UOM, info):
        dimension = info.data.get("dimension")
        if metric.uom_multiplier(dimension, uom) == 0:
            raise ValueError(f"Unsupported uom '{uom}' for dimension '{dimension}'")
        return uom
