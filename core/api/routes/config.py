# Copyright (C) 2025 BUS Core Authors
# SPDX-License-Identifier: AGPL-3.0-or-later

from fastapi import APIRouter, Depends, Body, Request
from typing import Dict, Any

from core.config.writes import require_writes
from core.config.manager import load_config, save_config

router = APIRouter()

@router.get("/config")
def get_config() -> Dict[str, Any]:
    return load_config().model_dump()

@router.post("/config")
def update_config(
    request: Request,
    payload: Dict[str, Any] = Body(...),
    _writes: None = Depends(require_writes)
) -> Dict[str, Any]:
    save_config(payload)
    # If the caller explicitly changed dev.writes_enabled, reflect it in the
    # runtime mirror immediately so a restart is not required for this field.
    dev_payload = payload.get("dev")
    if isinstance(dev_payload, dict) and "writes_enabled" in dev_payload:
        request.app.state.allow_writes = bool(dev_payload["writes_enabled"])
        return {"ok": True, "restart_required": False}
    return {"ok": True, "restart_required": True}
