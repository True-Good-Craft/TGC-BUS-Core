# Copyright (C) 2025 BUS Core Authors
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

from fastapi import APIRouter

from core.config.manager import load_config
from core.services.update import UpdateResult, UpdateService
from core.version import VERSION as CURRENT_VERSION

router = APIRouter()


def get_update_service() -> UpdateService:
    return UpdateService()


def _result_payload(result: UpdateResult) -> dict[str, object | None]:
    return {
        "current_version": result.current_version,
        "latest_version": result.latest_version,
        "update_available": result.update_available,
        "download_url": result.download_url,
        "error_code": result.error_code,
        "error_message": result.error_message,
    }


@router.get("/update/check")
def check_for_updates() -> dict[str, object | None]:
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
