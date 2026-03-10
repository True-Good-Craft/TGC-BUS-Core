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
from typing import Any, Dict

from core.appdb.paths import app_db_path


__all__ = ["load_core_config"]


def load_core_config() -> Dict[str, Any]:
    """Legacy back-compat shim for plugin/test harness context, not app-runtime config."""
    path = app_db_path().parent / "core_config.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}

