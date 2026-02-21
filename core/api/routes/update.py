# Copyright (C) 2025 BUS Core Authors
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

from fastapi import APIRouter

from core.config.manager import load_config
from core.services.update_service import UpdateService
from core.version import VERSION

router = APIRouter()


@router.get("/update/check")
async def check_update() -> dict:
    config = load_config().model_dump()
    service = UpdateService(config=config, version=VERSION)
    return await service.check()
