# Copyright (C) 2025 BUS Core Authors
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations
import os
from pathlib import Path

from core.appdata import paths as appdata_paths
from core.appdata.paths import resolve_db_path

def app_root_dir() -> Path:
    """Root folder for BUS Core runtime data (AppData design target)."""

    root = appdata_paths.buscore_root()
    root.mkdir(parents=True, exist_ok=True)
    return root


def app_dir() -> Path:
    """Return the canonical application data directory (AppData design target)."""

    target = appdata_paths.app_root()
    target.mkdir(parents=True, exist_ok=True)
    return target


def app_db_path() -> Path:
    """Design-target database path (not the running default)."""

    local_app_data = os.getenv("LOCALAPPDATA", "").strip()
    if local_app_data:
        path = Path(local_app_data) / "BUSCore" / "app" / "app.db"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path
    path = appdata_paths.app_db_design_target()
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def ui_dir() -> Path:
    """Serve UI from the repo (core/ui). Do NOT point to AppData."""

    return Path(__file__).resolve().parents[2] / "core" / "ui"
