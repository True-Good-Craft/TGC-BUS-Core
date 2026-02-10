# Copyright (C) 2025 BUS Core Authors
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class QuantityDisplay(BaseModel):
    unit: str
    value: str


class BatchSummary(BaseModel):
    entered: str
    remaining_int: int
    original_int: int
    unit_cost_display: str


class ItemOut(BaseModel):
    id: int
    name: str
    sku: Optional[str] = None
    uom: str
    qty_stored: int
    qty: float
    unit: str
    price: Optional[float] = None
    is_product: bool = False
    notes: Optional[str] = None
    vendor: Optional[str] = None
    location: Optional[str] = None
    type: Optional[str] = None
    created_at: Optional[datetime] = None
    stock_on_hand_int: int
    stock_on_hand_display: QuantityDisplay
    fifo_unit_cost_cents: Optional[int] = None
    fifo_unit_cost_display: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class ItemDetailOut(ItemOut):
    batches_summary: List[BatchSummary] = []


__all__ = ["BatchSummary", "ItemOut", "ItemDetailOut", "QuantityDisplay"]
