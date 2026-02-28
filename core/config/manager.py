# Copyright (C) 2025 BUS Core Authors
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations
import json
import os
from pathlib import Path
from typing import Literal, Dict, Any

from pydantic import BaseModel, Field

from core.appdata.paths import config_path, exports_dir

class LauncherConfig(BaseModel):
    auto_start_in_tray: bool = False
    close_to_tray: bool = False

class UIConfig(BaseModel):
    theme: Literal["system", "light", "dark"] = "system"

class BackupConfig(BaseModel):
    default_directory: str = Field(default_factory=lambda: str(exports_dir()))

class DevConfig(BaseModel):
    writes_enabled: bool = False


class UpdatesConfig(BaseModel):
    enabled: bool = False
    channel: str = "stable"
    manifest_url: str = "https://updates.truegoodcraft.com/bus-core/manifest.json"
    check_on_startup: bool = True

class Config(BaseModel):
    launcher: LauncherConfig = Field(default_factory=LauncherConfig)
    ui: UIConfig = Field(default_factory=UIConfig)
    backup: BackupConfig = Field(default_factory=BackupConfig)
    dev: DevConfig = Field(default_factory=DevConfig)
    updates: UpdatesConfig = Field(default_factory=UpdatesConfig)

def load_config() -> Config:
    path = config_path()
    if not path.exists():
        return Config()
    try:
        text = path.read_text(encoding="utf-8")
        data = json.loads(text)
        return Config(**data)
    except Exception:
        # Fallback to default if corrupted or parse error
        return Config()

def save_config(data: Dict[str, Any]) -> None:
    """
    Updates the configuration with the provided data.
    Performs a deep merge with existing config to support partial updates.
    """
    current_config = load_config()
    current_dump = current_config.model_dump()

    # Simple deep merge for known sections
    for section, values in data.items():
        if section in current_dump and isinstance(values, dict):
            # We filter unknown keys inside the section using Pydantic later,
            # but for merging, we just update the dict.
            current_dump[section].update(values)
        # We ignore top-level keys that are not in the model (like unknown sections)

    # Re-validate with Pydantic
    # This ensures that we only save valid keys according to the schema
    new_config = Config(**current_dump)

    # Atomic write
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".tmp")
    tmp_path.write_text(new_config.model_dump_json(indent=2), encoding="utf-8")

    # Atomic replace
    tmp_path.replace(path)
