# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import json
from pathlib import Path
import os

__doc__ = r"""
Windows AppData conventions (SoT):
  Base: %LOCALAPPDATA%\BUSCore
  DB defaults (Windows):
    demo -> %LOCALAPPDATA%\BUSCore\app\app_demo.db
    prod -> %LOCALAPPDATA%\BUSCore\app\app.db
  On non-Windows dev shells, use ~/.buscore/app/app.db
  (raw string to avoid Windows backslash escape warnings)
"""

BUS_MODE_CONFIG_NAME = "bus_mode.json"
BUS_MODE_FLAG_NAME = "bus_mode.flag"


def _is_windows() -> bool:
    return os.name == "nt"


def _localappdata() -> Path:
    lad = os.environ.get("LOCALAPPDATA")
    if lad:
        return Path(lad)
    # Fallback (non-Windows dev shells)
    return Path.home() / ".buscore"


def buscore_root() -> Path:
    return _localappdata() / "BUSCore"


def app_root() -> Path:
    return buscore_root() / "app"


def config_path() -> Path:
    return buscore_root() / "config.json"


def reader_settings_path() -> Path:
    return buscore_root() / "settings_reader.json"


def exports_dir() -> Path:
    return buscore_root() / "exports"


def secrets_dir() -> Path:
    return buscore_root() / "secrets"


def state_dir() -> Path:
    return buscore_root() / "state"


def update_cache_root() -> Path:
    return buscore_root() / "updates"


def app_db_default() -> Path:
    if _is_windows():
        return app_root() / "app.db"
    # non-Windows dev fallback target
    return Path.home() / ".buscore" / "app" / "app.db"


def app_demo_db_default() -> Path:
    if _is_windows():
        return app_root() / "app_demo.db"
    return Path.home() / ".buscore" / "app" / "app_demo.db"


def app_db_design_target() -> Path:
    # Alias for clarity when other modules want the design-target location
    return app_db_default()


def _normalize_bus_mode(value: str | None) -> str | None:
    if value is None:
        return None
    mode = value.strip().lower()
    if mode in {"demo", "prod"}:
        return mode
    return None


def bus_mode_config_path() -> Path:
    return app_root() / BUS_MODE_CONFIG_NAME


def bus_mode_flag_path() -> Path:
    return app_root() / BUS_MODE_FLAG_NAME


def _read_bus_mode_from_config() -> str | None:
    path = bus_mode_config_path()
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if isinstance(payload, dict):
        return _normalize_bus_mode(str(payload.get("BUS_MODE") or payload.get("bus_mode") or ""))
    return None


def _read_bus_mode_from_flag() -> str | None:
    path = bus_mode_flag_path()
    if not path.exists():
        return None
    try:
        return _normalize_bus_mode(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def resolve_bus_mode() -> str:
    """
    Runtime mode resolution priority:
      1) mode config file
      2) BUS_MODE env var
      3) local mode flag file
      4) default (fresh install): demo

    If BUS_DB is explicitly set and no BUS_MODE source exists, default to prod
    so explicit test/dev path overrides keep legacy behavior.
    """
    mode = _read_bus_mode_from_config()
    if mode:
        return mode
    mode = _normalize_bus_mode(os.environ.get("BUS_MODE"))
    if mode:
        return mode
    mode = _read_bus_mode_from_flag()
    if mode:
        return mode
    if os.environ.get("BUS_DB"):
        return "prod"
    return "demo"


def set_bus_mode(mode: str) -> str:
    normalized = _normalize_bus_mode(mode)
    if normalized is None:
        raise ValueError("invalid_bus_mode")
    ensure_roots()
    path = bus_mode_config_path()
    payload = {"BUS_MODE": normalized}
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(path)
    return normalized


def db_path_for_mode(mode: str) -> Path:
    normalized = _normalize_bus_mode(mode)
    if normalized is None:
        raise ValueError("invalid_bus_mode")
    return app_demo_db_default() if normalized == "demo" else app_db_default()


def ensure_roots() -> None:
    for p in (buscore_root(), app_root(), exports_dir(), secrets_dir(), state_dir()):
        p.mkdir(parents=True, exist_ok=True)


def resolve_db_path() -> str:
    r"""
    New SoT (Windows): runtime DB lives in %LOCALAPPDATA%\BUSCore\app\app_demo.db
    (demo mode) or %LOCALAPPDATA%\BUSCore\app\app.db (prod mode).
    If BUS_DB is set, use it exactly.
    On non-Windows dev shells, fallback to ~/.buscore/app/app.db as default.
    """
    env_db = os.environ.get("BUS_DB")
    if env_db:
        return str(Path(env_db).resolve())
    ensure_roots()
    mode = resolve_bus_mode()
    return str(db_path_for_mode(mode).resolve())


# Legacy repo path helper (for one-time migration only)
def legacy_repo_db() -> Path:
    return (Path.cwd() / "data" / "app.db").resolve()
