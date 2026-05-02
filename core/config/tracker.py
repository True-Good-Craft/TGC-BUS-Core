# SPDX-License-Identifier: AGPL-3.0-or-later
# TGC BUS Core (Business Utility System Core)
# Copyright (C) 2025 True Good Craft
#
# This file is part of TGC BUS Core.
#
# TGC BUS Core is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# TGC BUS Core is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with TGC BUS Core.  If not, see <https://www.gnu.org/licenses/>.

from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Dict, List, Tuple

from core.config.paths import APP_DIR


def _root() -> Path:
    return Path(__file__).resolve().parents[2]  # repo root


def _data_dir() -> Path:
    return _root() / "data"


def _logs_dir() -> Path:
    return _root() / "logs"


def _state_dir() -> Path:
    if os.name == "nt":
        return APP_DIR
    return Path.home() / ".tgc"


def _manifest_path() -> Path:
    return _state_dir() / "state" / "system_manifest.json"


def _session_token_path() -> Path:
    return _data_dir() / "session_token.txt"


def _secrets_dir() -> Path:
    return _state_dir() / "secrets"


def _secrets_files() -> List[Path]:
    out = []
    p = _secrets_dir()
    if (p / "secrets.json.enc").exists():
        out.append(p / "secrets.json.enc")
    if (p / "master.key").exists():
        out.append(p / "master.key")
    return out


def _plugins_root() -> Path:
    return _root() / "plugins"


def discover_plugin_settings() -> List[Tuple[str, Path]]:
    out: List[Tuple[str, Path]] = []
    pr = _plugins_root()
    if not pr.exists():
        return out
    for d in pr.iterdir():
        if not d.is_dir() or d.name.startswith("_"):
            continue
        for candidate in ("settings.json", "settings.yaml", "settings.yml"):
            f = d / candidate
            if f.exists():
                out.append((d.name, f))
    return out


def _file_info(p: Path) -> Dict:
    try:
        s = p.stat()
        ro = not os.access(p, os.W_OK) or bool(s.st_mode & stat.S_IREAD and not s.st_mode & stat.S_IWRITE)
        return {"exists": True, "bytes": s.st_size, "readonly": ro}
    except FileNotFoundError:
        return {"exists": False, "bytes": 0, "readonly": False}


def snapshot() -> Dict:
    settings = {pid: str(path) for pid, path in discover_plugin_settings()}
    return {
        "paths": {
            "manifest": str(_manifest_path()),
            "session_token": str(_session_token_path()),
            "secrets_dir": str(_secrets_dir()),
            "logs_dir": str(_logs_dir()),
            "data_dir": str(_data_dir()),
            "plugins_root": str(_plugins_root()),
            "plugin_settings": settings,
        },
        "files": {
            "manifest": _file_info(_manifest_path()),
            "session_token": _file_info(_session_token_path()),
            **{f"secrets/{p.name}": _file_info(p) for p in _secrets_files()},
            **{f"settings/{pid}": _file_info(path) for pid, path in discover_plugin_settings()},
        },
    }


def clear_secrets() -> Dict:
    removed = []
    for p in _secrets_files():
        try:
            p.unlink(missing_ok=True)
            removed.append(str(p))
        except Exception:
            pass
    return {"removed": removed}


def clear_saved_data(keep_settings: bool = True) -> Dict:
    removed = []
    try:
        _session_token_path().unlink(missing_ok=True)
        removed.append(str(_session_token_path()))
    except Exception:
        pass
    ld = _logs_dir()
    if ld.exists():
        for f in ld.glob("*"):
            try:
                f.unlink()
                removed.append(str(f))
            except Exception:
                pass
    dd = _data_dir()
    if dd.exists():
        for f in dd.glob("*"):
            try:
                f.unlink()
                removed.append(str(f))
            except Exception:
                pass
    return {"removed": removed}


def set_settings_readonly(pid: str, ro: bool = True) -> Dict:
    for plug, path in discover_plugin_settings():
        if plug == pid:
            try:
                mode = path.stat().st_mode
                path.chmod((mode & ~stat.S_IWRITE) if ro else (mode | stat.S_IWRITE))
                return {"ok": True, "path": str(path), "readonly": ro}
            except Exception as e:
                return {"ok": False, "path": str(path), "error": str(e)}
    return {"ok": False, "error": "settings_not_found"}
