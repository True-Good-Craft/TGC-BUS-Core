# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from core.appdb.engine import get_session
from core.demo.avoarrow_factory import EMPTY_GUARD_ERROR, load_demo_factory

router = APIRouter(tags=["demo"])


@router.post("/demo/load")
def load_demo(db: Session = Depends(get_session)):
    try:
        return load_demo_factory(db)
    except ValueError as exc:
        if str(exc) == EMPTY_GUARD_ERROR:
            raise HTTPException(status_code=400, detail=str(exc))
        raise
