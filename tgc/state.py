# Copyright (C) 2025 BUS Core Authors
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request

from core.runtime import CoreAlpha
from tgc.logging_setup import setup_logging
from tgc.platform_adapters import PlatformAdapter
from tgc.tokens import TokenManager
from tgc.settings import Settings


@dataclass
class AppState:
    settings: Settings
    core: Optional[CoreAlpha]
    tokens: TokenManager
    logger: logging.Logger
    platform: PlatformAdapter


def init_state(settings: Settings) -> AppState:
    # Ensure data dir exists BEFORE core runtime touches DB/files
    data_dir: Path = settings.resolve_data_dir()
    tokens = TokenManager(settings)
    logger = setup_logging(data_dir / "buscore.log")
    platform = PlatformAdapter()
    return AppState(settings=settings, core=None, tokens=tokens, logger=logger, platform=platform)


def get_state(request: Request) -> AppState:
    state = getattr(request.app.state, "app_state", None)
    if state is None:
        raise RuntimeError("AppState not initialized")
    return state


def init_app_state(app: FastAPI) -> None:
    """Idempotently attach AppState to the FastAPI instance."""

    if getattr(app.state, "app_state", None) is None:
        settings = Settings()
        app.state.app_state = init_state(settings)
