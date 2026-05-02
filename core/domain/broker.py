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

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger("tgc.broker")


class Broker:
    """
    Microkernel Registry.
    Does not import adapters. Plugins must register themselves at runtime.
    """

    _providers: Dict[str, Any] = {}

    def __init__(self) -> None:
        self.ready = True

    @classmethod
    def register_provider(cls, name: str, provider_cls: Any) -> None:
        logger.info(f"Plugin Registered: {name}")
        cls._providers[name] = provider_cls

    @classmethod
    def get_provider(cls, name: str) -> Optional[Any]:
        return cls._providers.get(name)

    @classmethod
    def service_call(cls, name: str, op: str, params: Dict[str, Any]) -> Dict[str, Any]:
        provider = cls._providers.get(name)
        if not provider:
            return {"error": "unknown_provider"}
        try:
            fn = getattr(provider, op, None)
            if callable(fn):
                return fn(**params)
            return {"error": "unknown_op"}
        except Exception:
            return {"error": "provider_error"}

    @classmethod
    def clear_provider_cache(cls, provider: str) -> None:
        p = cls._providers.get(provider)
        if p and hasattr(p, "clear_cache"):
            try:
                p.clear_cache()
            except Exception:  # Cache invalidation is best-effort; provider may not support clearing.
                pass


__all__ = ["Broker"]
