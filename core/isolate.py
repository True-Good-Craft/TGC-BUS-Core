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

import json, os, subprocess, sys, tempfile

_WINDOWS_HIDE = 0x08000000 if os.name == "nt" else 0

def run_isolated(plugin: str, cap: str, payload: dict, env_keys: list[str], timeout_s: int = 60):
    # Whitelist environment
    child_env = {k: os.getenv(k, "") for k in env_keys}
    # Minimal PYTHONPATH: allow project to import core/plugins
    child_env["PYTHONPATH"] = os.getcwd() + os.pathsep + child_env.get("PYTHONPATH", "")

    # Write payload to a temp file
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".json") as tf:
        tf.write(json.dumps(payload))
        payload_path = tf.name

    # Inline runner code (imports only what we need)
    code = f"""
import json, sys, time
from core.services.capabilities import resolve
from core.plugin_api import Context
from core.config import load_core_config
from core.plugin_manager import load_plugins
p = json.loads(open({payload_path!r}).read())
load_plugins()
fn = resolve({cap!r})
ctx = Context(run_id=p['run_id'], config=load_core_config(), limits=p['limits'], logger=None)
res = fn(ctx, **p['params'])
print(json.dumps({'ok':res.ok,'data':res.data,'notes':res.notes}))
"""

    cmd = [sys.executable, "-c", code]
    try:
        proc = subprocess.Popen(
            cmd,
            env=child_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            creationflags=_WINDOWS_HIDE
        )
        stdout, stderr = proc.communicate(timeout=timeout_s)
        rc = proc.returncode
    except subprocess.TimeoutExpired:
        proc.kill()
        stdout, stderr, rc = "", "timeout", -9
    finally:
        try:
            os.unlink(payload_path)
        except Exception:  # Best-effort cleanup; temp payload file may already be gone.
            pass

    return rc, stdout, stderr
