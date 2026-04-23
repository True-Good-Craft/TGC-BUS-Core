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

from fastapi import HTTPException, Request, status


def _calc_default_allow_writes() -> bool:
    """Default to enabling writes unless explicitly read-only."""

    allow = os.getenv("ALLOW_WRITES", "1").lower() not in ("0", "false", "no")
    ro = os.getenv("READ_ONLY", "0").lower() in ("1", "true", "yes")
    return bool(allow and not ro)


def writes_enabled(request: Request) -> bool:
    """Return the current write-enabled flag, stored on app state."""

    state = getattr(request.app, "state", None)
    if state is None:
        return _calc_default_allow_writes()
    if not hasattr(state, "allow_writes") or state.allow_writes is None:
        state.allow_writes = _calc_default_allow_writes()
    return bool(state.allow_writes)


def require_write_access(request: Request):
    """Guard dependency that blocks requests when writes are disabled."""

    if not writes_enabled(request):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "writes_disabled",
                "hint": "Set dev.writes_enabled=true in config or unset READ_ONLY env var, then restart.",
            },
        )
