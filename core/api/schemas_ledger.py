# SPDX-License-Identifier: AGPL-3.0-or-later
from typing import Optional

from pydantic import BaseModel, StrictStr, model_validator

try:
    from pydantic import ConfigDict  # v2
    _ModelConfig = ConfigDict
except ImportError:  # pydantic v1 fallback
    _ModelConfig = None  # type: ignore


class StockInReq(BaseModel):
    item_id: int
    uom: StrictStr
    quantity_decimal: StrictStr
    unit_cost_decimal: StrictStr
    cost_uom: StrictStr
    vendor_id: Optional[int] = None
    notes: Optional[StrictStr] = None

    @model_validator(mode="before")
    @classmethod
    def reject_legacy_unit_cost(cls, data):
        if isinstance(data, dict) and "unit_cost_cents" in data:
            raise ValueError("legacy_unit_cost_field_not_allowed")
        return data

    if _ModelConfig:
        model_config = _ModelConfig(extra="forbid")
    else:
        class Config:  # type: ignore
            extra = "forbid"


class QtyDisplay(BaseModel):
    unit: str
    value: str


class StockInResp(BaseModel):
    batch_id: int
    qty_added_int: int
    stock_on_hand_int: int
    stock_on_hand_display: QtyDisplay
    fifo_unit_cost_display: Optional[str] = None
