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

import json
import os
import pathlib
from typing import Any, Dict, List

_CFG_DIR = pathlib.Path(os.environ.get("LOCALAPPDATA", ".")) / "BUSCore"
_CFG_DIR.mkdir(parents=True, exist_ok=True)
_CFG_FILE = _CFG_DIR / "settings_reader.json"

_STATE: Dict[str, Any] = {
    "enabled": {"drive": True, "local": True, "notion": False, "smb": False},
    "local_roots": [],
    "drive_includes": {
        "include_my_drive": False,
        "my_drive_root_id": "",
        "include_shared_drives": False,
    },
}


def _load_file() -> Dict[str, Any]:
    if _CFG_FILE.exists():
        try:
            return json.loads(_CFG_FILE.read_text(encoding="utf-8"))
        except Exception:  # Compatibility fallback: missing/corrupt reader config uses defaults.
            pass
    return dict(_STATE)


def load_settings() -> Dict[str, Any]:
    global _STATE
    _STATE = _load_file()
    return dict(_STATE)


def save_settings(s: Dict[str, Any]) -> None:
    global _STATE
    _STATE = dict(_STATE | s)
    _CFG_FILE.write_text(json.dumps(_STATE, indent=2), encoding="utf-8")


def get_allowed_local_roots() -> List[str]:
    return list(_STATE.get("local_roots", []))


def set_allowed_local_roots(roots: List[str]) -> None:
    s = dict(_STATE)
    s["local_roots"] = list(roots or [])
    save_settings(s)


# Initialize at import
load_settings()
