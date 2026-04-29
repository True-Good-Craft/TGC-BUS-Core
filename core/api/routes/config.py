# Copyright (C) 2025 BUS Core Authors
# SPDX-License-Identifier: AGPL-3.0-or-later

from typing import Dict, Any

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from pydantic import ValidationError

from core.config.writes import require_writes
from core.config.manager import load_config, save_config
from core.config.update_policy import UpdatePolicyError
from tgc.security import require_token_ctx

router = APIRouter()


@router.get("/config")
def get_config(_token: None = Depends(require_token_ctx)) -> Dict[str, Any]:
    return load_config().model_dump()


@router.post("/config")
def update_config(
    request: Request,
    payload: Dict[str, Any] = Body(...),
    _token: None = Depends(require_token_ctx),
    _writes: None = Depends(require_writes),
) -> Dict[str, Any]:
    try:
        save_config(payload)
    except UpdatePolicyError as exc:
        raise HTTPException(status_code=400, detail={"code": exc.code, "message": exc.message}) from exc
    except (ValueError, ValidationError) as exc:
        raise HTTPException(status_code=400, detail={"code": "invalid_config", "message": str(exc)}) from exc
    # If the caller explicitly changed dev.writes_enabled, reflect it in the
    # runtime mirror immediately so a restart is not required for this field.
    dev_payload = payload.get("dev")
    if isinstance(dev_payload, dict) and "writes_enabled" in dev_payload:
        request.app.state.allow_writes = bool(dev_payload["writes_enabled"])
        return {"ok": True, "restart_required": False}
    return {"ok": True, "restart_required": True}
