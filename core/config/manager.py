# Copyright (C) 2025 BUS Core Authors
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Literal

from pydantic import BaseModel, Field

from core.appdata.paths import app_root, config_path, exports_dir


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
    # Canonical update gateway served by Lighthouse.
    manifest_url: str = "https://lighthouse.buscore.ca/update/check"
    check_on_startup: bool = True


class Config(BaseModel):
    launcher: LauncherConfig = Field(default_factory=LauncherConfig)
    ui: UIConfig = Field(default_factory=UIConfig)
    backup: BackupConfig = Field(default_factory=BackupConfig)
    dev: DevConfig = Field(default_factory=DevConfig)
    updates: UpdatesConfig = Field(default_factory=UpdatesConfig)


_PUBLIC_SECTIONS = ("launcher", "ui", "backup", "dev", "updates")


def _legacy_config_path() -> Path:
    return app_root() / "config.json"


def _read_json_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _write_json_file(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp_path.replace(path)


def _has_nested(data: dict[str, Any], *keys: str) -> bool:
    current: Any = data
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return False
        current = current[key]
    return True


def _get_nested(data: dict[str, Any], *keys: str) -> Any:
    current: Any = data
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _set_nested(data: dict[str, Any], value: Any, *keys: str) -> None:
    current = data
    for key in keys[:-1]:
        child = current.get(key)
        if not isinstance(child, dict):
            child = {}
            current[key] = child
        current = child
    current[keys[-1]] = value


def _load_canonical_config_dict() -> dict[str, Any]:
    return _read_json_file(config_path())


def _load_legacy_compat_dict() -> dict[str, Any]:
    return _read_json_file(_legacy_config_path())


def _extract_public_config(raw: dict[str, Any]) -> dict[str, Any]:
    public: dict[str, Any] = {}
    for section in _PUBLIC_SECTIONS:
        value = raw.get(section)
        if isinstance(value, dict):
            public[section] = dict(value)
    return public


def _merged_public_config_dict() -> dict[str, Any]:
    raw = _load_canonical_config_dict()
    public = _extract_public_config(raw)
    legacy = _load_legacy_compat_dict()

    if not _has_nested(raw, "dev", "writes_enabled") and "writes_enabled" in legacy:
        public.setdefault("dev", {})
        public["dev"]["writes_enabled"] = bool(legacy.get("writes_enabled"))

    return public


def load_config() -> Config:
    return Config(**_merged_public_config_dict())


def get_dev_writes_enabled() -> bool | None:
    raw = _load_canonical_config_dict()
    if _has_nested(raw, "dev", "writes_enabled"):
        return bool(_get_nested(raw, "dev", "writes_enabled"))

    legacy = _load_legacy_compat_dict()
    if "writes_enabled" in legacy:
        return bool(legacy.get("writes_enabled"))
    return None


def set_dev_writes_enabled(enabled: bool) -> None:
    raw = _load_canonical_config_dict()
    _set_nested(raw, bool(enabled), "dev", "writes_enabled")
    _write_json_file(config_path(), raw)


def load_policy_config() -> dict[str, Any]:
    raw = _load_canonical_config_dict()
    out: dict[str, Any] = {}

    if _has_nested(raw, "policy", "role"):
        out["role"] = _get_nested(raw, "policy", "role")
    if _has_nested(raw, "policy", "plan_only"):
        out["plan_only"] = bool(_get_nested(raw, "policy", "plan_only"))

    if "role" in out and "plan_only" in out:
        return out

    legacy = _load_legacy_compat_dict()
    if "role" not in out and "role" in legacy:
        out["role"] = legacy.get("role")
    if "plan_only" not in out and "plan_only" in legacy:
        out["plan_only"] = bool(legacy.get("plan_only"))
    return out


def save_policy_config(*, role: str, plan_only: bool) -> None:
    raw = _load_canonical_config_dict()
    _set_nested(raw, role, "policy", "role")
    _set_nested(raw, bool(plan_only), "policy", "plan_only")
    _write_json_file(config_path(), raw)


def save_config(data: Dict[str, Any]) -> None:
    """
    Updates the configuration with the provided data.
    Performs a deep merge with existing config to support partial updates.
    """
    raw = _load_canonical_config_dict()
    current_dump = Config(**_extract_public_config(raw)).model_dump()

    for section, values in data.items():
        if section in current_dump and isinstance(values, dict):
            current_dump[section].update(values)

    new_config = Config(**current_dump)

    new_raw = dict(raw)
    public_dump = new_config.model_dump()
    for section in _PUBLIC_SECTIONS:
        new_raw[section] = public_dump[section]

    _write_json_file(config_path(), new_raw)

