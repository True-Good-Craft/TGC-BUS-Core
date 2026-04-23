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

from typing import Dict, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .ids import rid_to_path, to_rid
from .roots import get_allowed_local_roots

router = APIRouter(prefix="/reader/local", tags=["reader-local"])


class PathsBody(BaseModel):
    paths: List[str]


class IdsBody(BaseModel):
    ids: List[str]


@router.post("/resolve_ids")
def resolve_ids(body: PathsBody) -> Dict[str, str]:
    roots = get_allowed_local_roots()
    out: Dict[str, str] = {}
    for path in body.paths:
        try:
            out[path] = to_rid(path, roots)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
    return out


@router.post("/resolve_paths")
def resolve_paths(body: IdsBody) -> Dict[str, str | None]:
    roots = get_allowed_local_roots()
    out: Dict[str, str | None] = {}
    for rid in body.ids:
        try:
            out[rid] = rid_to_path(rid, roots)
        except ValueError:
            out[rid] = None
    return out
