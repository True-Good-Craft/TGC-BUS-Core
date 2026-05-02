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

import json
import os
import subprocess
import sys
import tempfile
import math
from typing import Any, Dict


class SandboxError(RuntimeError):
    ...


_MIN_SANDBOX_TIMEOUT_SECONDS = 0.5
_MAX_SANDBOX_TIMEOUT_SECONDS = 30.0
_MAX_SANDBOX_STDOUT_BYTES = 1024 * 1024
_MAX_SANDBOX_ERROR_DETAIL_CHARS = 4096


def _coerce_timeout(timeout: float) -> float:
    try:
        numeric_timeout = float(timeout)
    except (TypeError, ValueError) as exc:
        raise SandboxError("sandbox_invalid_timeout") from exc
    if not math.isfinite(numeric_timeout):
        raise SandboxError("sandbox_invalid_timeout")
    return min(max(numeric_timeout, _MIN_SANDBOX_TIMEOUT_SECONDS), _MAX_SANDBOX_TIMEOUT_SECONDS)


def _sandbox_command() -> list[str]:
    # Keep argv fixed so request or plugin data cannot influence executable selection
    # or command-line parsing. Dynamic operation data stays in stdin JSON only.
    return [sys.executable, "-m", "core.runtime.sandbox_runner"]


def run_transform(plugin_id: str, fn: str, payload: Dict[str, Any], *, timeout: float = 5.0) -> Dict[str, Any]:
    """Execute plugin transform in a sandboxed subprocess."""

    with tempfile.TemporaryDirectory(prefix="bus_sandbox_") as tmp:
        env = os.environ.copy()
        env["BUS_SANDBOX_DIR"] = tmp
        sandbox_payload = {
            "plugin_id": plugin_id,
            "fn": fn,
            "payload": {
                "input": payload.get("input") or {},
                "limits": payload.get("limits") or {},
            },
        }
        try:
            proc = subprocess.run(  # nosec B603 - argv is fixed by _sandbox_command()
                _sandbox_command(),
                input=json.dumps(sandbox_payload).encode("utf-8"),
                capture_output=True,
                timeout=_coerce_timeout(timeout),
                check=False,
                shell=False,
                cwd=tmp,
                env=env,
            )
        except subprocess.TimeoutExpired as exc:
            raise SandboxError(f"sandbox_timeout:{plugin_id}:{fn}") from exc
        if proc.returncode != 0:
            detail = proc.stderr.decode("utf-8", errors="ignore").strip()[:_MAX_SANDBOX_ERROR_DETAIL_CHARS]
            raise SandboxError(
                f"sandbox_error:{plugin_id}:{fn}:{proc.returncode}:{detail}",
            )
        if len(proc.stdout) > _MAX_SANDBOX_STDOUT_BYTES:
            raise SandboxError("sandbox_output_too_large")
        stdout = proc.stdout.decode("utf-8")
        try:
            result = json.loads(stdout or "{}")
        except json.JSONDecodeError as exc:
            raise SandboxError("sandbox_invalid_json") from exc
        return result
