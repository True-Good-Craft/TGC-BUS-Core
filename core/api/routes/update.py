# Copyright (C) 2025 BUS Core Authors
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

from fastapi import APIRouter, Depends

from core.config.writes import require_writes
from core.config.manager import load_config
from core.runtime.manifest_keys import active_manifest_public_keys
from core.services.update import UpdateResult, UpdateService
from core.services.update_stage import UpdateStageResult, UpdateStageService
from core.version import VERSION as CURRENT_VERSION
from tgc.security import require_token_ctx

router = APIRouter()


def get_update_service() -> UpdateService:
    return UpdateService(trusted_manifest_public_keys=active_manifest_public_keys())


def get_update_stage_service() -> UpdateStageService:
    return UpdateStageService(update_service=get_update_service())


def _result_payload(result: UpdateResult) -> dict[str, object | None]:
    return {
        "current_version": result.current_version,
        "latest_version": result.latest_version,
        "update_available": result.update_available,
        "download_url": result.download_url,
        "error_code": result.error_code,
        "error_message": result.error_message,
    }


def _stage_payload(result: UpdateStageResult) -> dict[str, object | None]:
    return {
        "ok": result.ok,
        "status": result.status,
        "current_version": result.current_version,
        "latest_version": result.latest_version,
        "exe_path": result.exe_path,
        "restart_available": result.restart_available,
        "error_code": result.error_code,
        "error_message": result.error_message,
    }


@router.get("/update/check")
def check_for_updates(_token: None = Depends(require_token_ctx)) -> dict[str, object | None]:
    try:
        cfg = load_config().updates
        result = get_update_service().check(
            manifest_url=cfg.manifest_url,
            channel=cfg.channel,
        )
        return _result_payload(result)
    except Exception:
        return _result_payload(
            UpdateResult(
                current_version=CURRENT_VERSION,
                latest_version=None,
                update_available=False,
                download_url=None,
                error_code="update_check_failed",
                error_message="Update check failed.",
            )
        )


@router.post("/update/stage")
def stage_update(
    _token: None = Depends(require_token_ctx),
    _writes: None = Depends(require_writes),
) -> dict[str, object | None]:
    try:
        return _stage_payload(get_update_stage_service().stage_from_config())
    except Exception:
        return _stage_payload(
            UpdateStageResult(
                ok=False,
                status="failed",
                current_version=CURRENT_VERSION,
                latest_version=None,
                exe_path=None,
                restart_available=False,
                error_code="update_stage_failed",
                error_message="Update staging failed.",
            )
        )
