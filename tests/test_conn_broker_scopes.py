# SPDX-License-Identifier: AGPL-3.0-or-later
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.services.conn_broker import ClientHandle, ConnectionBroker


def test_conn_broker_scopes():
    broker = ConnectionBroker(controller=None)

    issued_scopes: list[str] = []

    def drive_provider(scope: str) -> ClientHandle:
        issued_scopes.append(scope)
        return ClientHandle(service="drive", scope=scope, handle=object(), metadata={})

    def drive_probe(handle: ClientHandle | None):
        if handle is None:
            return {"ok": False, "detail": "no_client"}
        return {"ok": True, "scope": handle.scope}

    broker.register("drive", provider=drive_provider, probe=drive_probe)

    base = broker.get_client("drive", scope="read_base")
    crawl = broker.get_client("drive", scope="read_crawl")
    denied = broker.get_client("drive", scope="write")

    assert base and base.scope == "read_base"
    assert crawl is None
    assert denied is None
    assert issued_scopes == ["read_base"]

    probe_ok = broker.probe("drive")
    assert probe_ok["ok"] is True
    assert probe_ok["scope"] == "read_base"

    missing = broker.probe("notion")
    assert missing["ok"] is False
    assert missing["detail"] == "no_provider"
