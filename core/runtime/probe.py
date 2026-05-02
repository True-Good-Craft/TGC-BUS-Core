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

import concurrent.futures
import time
from typing import Dict, List

from core.services.conn_broker import ConnectionBroker

PROBE_TIMEOUT_SEC = 5


def _probe_one(broker: ConnectionBroker, svc: str) -> dict:
    t0 = time.time()
    try:
        res = broker.probe(svc)
        if not isinstance(res, dict):
            res = {"ok": bool(res)}
        res.setdefault("elapsed_ms", int((time.time() - t0) * 1000))
        return res
    except Exception as exc:
        return {
            "ok": False,
            "detail": "probe_exception",
            "error": str(exc),
            "elapsed_ms": int((time.time() - t0) * 1000),
        }


def probe_services(broker: ConnectionBroker, services: List[str]) -> Dict[str, dict]:
    results: Dict[str, dict] = {}
    if not services:
        return results
    max_workers = min(8, max(1, len(services)))
    wall_timeout = PROBE_TIMEOUT_SEC * max(1, len(services))
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
        futs = {pool.submit(_probe_one, broker, svc): svc for svc in services}
        try:
            for fut in concurrent.futures.as_completed(futs, timeout=wall_timeout):
                svc = futs[fut]
                try:
                    results[svc] = fut.result(timeout=0)
                except concurrent.futures.TimeoutError:
                    results[svc] = {
                        "ok": False,
                        "detail": "probe_timeout",
                        "timeout_sec": PROBE_TIMEOUT_SEC,
                    }
                except Exception as exc:
                    results[svc] = {
                        "ok": False,
                        "detail": "probe_exception",
                        "error": str(exc),
                    }
        except concurrent.futures.TimeoutError:  # Expected fallback: missing result becomes probe_timeout below.
            pass
    for fut, svc in futs.items():
        if svc not in results:
            results[svc] = {
                "ok": False,
                "detail": "probe_timeout",
                "timeout_sec": PROBE_TIMEOUT_SEC,
            }
    return results
