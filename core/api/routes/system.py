# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from core.appdb.engine import get_session
from core.appdb.models import CashEvent, Item, ItemBatch, ItemMovement

router = APIRouter(tags=["system"])


@router.get("/system/state")
def get_system_state(db: Session = Depends(get_session)):
    item_count = int(db.query(func.count(Item.id)).scalar() or 0)
    batch_count = int(db.query(func.count(ItemBatch.id)).scalar() or 0)
    movement_count = int(db.query(func.count(ItemMovement.id)).scalar() or 0)
    cash_event_count = int(db.query(func.count(CashEvent.id)).scalar() or 0)

    is_empty = (
        item_count == 0
        and batch_count == 0
        and movement_count == 0
        and cash_event_count == 0
    )

    return {
        "is_empty": bool(is_empty),
        "item_count": item_count,
        "batch_count": batch_count,
        "movement_count": movement_count,
        "cash_event_count": cash_event_count,
    }
