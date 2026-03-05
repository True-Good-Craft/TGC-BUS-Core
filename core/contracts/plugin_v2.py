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
from typing import Dict, Any, Optional
from core.services.conn_broker import ConnectionBroker


class PluginV2:
    id: str = "plugin"
    name: str = "BUS Plugin"
    version: str = "0.1"
    api_version: str = "2"

    def describe(self) -> Dict[str, Any]:
        return {"services": [], "scopes": ["read_base"]}

    def register_broker(self, broker: ConnectionBroker) -> None:
        raise NotImplementedError

    def run(self, broker: ConnectionBroker, options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return {"ok": True}

    def capabilities(self) -> Dict[str, Any]:
        """Return a declarative capability manifest block."""

        return {
            "provides": [],
            "requires": [],
            "trust_tier": 1,
            "stages": ["service"],
        }

    def plan_transform(self, fn: str, payload: Dict[str, Any], *, limits: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        raise NotImplementedError("transform planning not implemented")

    def manifest(self) -> Dict[str, Any]:
        block = self.capabilities() or {}
        return {
            "id": getattr(self, "id", self.__class__.__name__),
            "version": getattr(self, "version", "0"),
            "provides": list(block.get("provides", [])),
            "requires": list(block.get("requires", [])),
            "stages": list(block.get("stages", [])),
            "trust_tier": block.get("trust_tier", 1),
        }
