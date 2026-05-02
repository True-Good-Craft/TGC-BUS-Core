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

import os

from fastapi import HTTPException, Request

from core.config.writes import require_writes

from .model import Role
from .store import load_policy


def require_owner_commit(request: Request) -> None:
    # Allow if env override or UI toggle is on; otherwise block
    require_writes(request)
    # Optional strict policy (OFF unless BUS_POLICY_ENFORCE=1)
    if os.environ.get("BUS_POLICY_ENFORCE") == "1":
        p = load_policy()
        if not (p.role == Role.OWNER and p.plan_only is False):
            raise HTTPException(status_code=403, detail="Commits disabled by policy (not OWNER or plan-only).")
