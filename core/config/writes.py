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

from typing import Any, Dict, Optional

from fastapi import Request

from core.api.security import _calc_default_allow_writes, require_write_access, writes_enabled
from core.config.manager import get_dev_writes_enabled, set_dev_writes_enabled

WRITE_BLOCK_MSG = "Local writes disabled. Enable in Settings."


def get_writes_enabled(request: Optional[Request] = None) -> bool:
    if request is not None:
        return writes_enabled(request)
    persisted = get_dev_writes_enabled()
    if persisted is not None:
        return persisted
    return _calc_default_allow_writes()


def set_writes_enabled(enabled: bool, request: Optional[Request] = None) -> Dict[str, Any]:
    set_dev_writes_enabled(bool(enabled))
    if request is not None and getattr(request, "app", None) is not None:
        request.app.state.allow_writes = bool(enabled)
    return {"enabled": bool(enabled)}


def require_writes(request: Request):
    require_write_access(request)

