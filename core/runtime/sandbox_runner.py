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

import importlib
import json
import sys
from typing import Any, Dict

from core.contracts.plugin_v2 import PluginV2


def _load_plugin(plugin_id: str) -> PluginV2:
    module_names = [f"plugins.{plugin_id}.plugin", f"plugins.{plugin_id}"]
    last_exc: Exception | None = None
    for name in module_names:
        try:
            module = importlib.import_module(name)
        except Exception as exc:  # pragma: no cover - defensive
            last_exc = exc
            continue
        plugin_cls = getattr(module, "Plugin", None)
        if plugin_cls and issubclass(plugin_cls, PluginV2):
            return plugin_cls()
    raise RuntimeError(f"plugin_not_found:{plugin_id}:{last_exc}")


def _parse_request() -> tuple[str, str, Dict[str, Any]]:
    try:
        request = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError as exc:
        raise ValueError("sandbox_invalid_request") from exc
    if not isinstance(request, dict):
        raise ValueError("sandbox_invalid_request")

    plugin_id = request.get("plugin_id")
    fn = request.get("fn")
    payload = request.get("payload")
    if not isinstance(plugin_id, str) or not isinstance(fn, str) or not isinstance(payload, dict):
        raise ValueError("sandbox_invalid_request")
    return plugin_id, fn, payload


def main(argv: list[str] | None = None) -> int:
    del argv
    try:
        plugin_id, fn, payload = _parse_request()
    except ValueError as exc:
        sys.stderr.write(str(exc))
        return 2

    plugin = _load_plugin(plugin_id)
    input_data: Dict[str, Any] = payload.get("input") or {}
    limits = payload.get("limits") or {}
    proposal = plugin.plan_transform(fn, input_data, limits=limits)
    output = {"proposal": proposal}
    sys.stdout.write(json.dumps(output))
    return 0


if __name__ == "__main__":
    sys.exit(main())
