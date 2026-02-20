# Copyright (C) 2025 BUS Core Authors
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

from core.services import update_service


def test_update_check_disabled_no_http(bus_client, monkeypatch):
    client = bus_client["client"]
    called = {"value": False}

    def _urlopen(*args, **kwargs):
        called["value"] = True
        raise AssertionError("urlopen should not be called")

    monkeypatch.setattr(update_service, "urlopen", _urlopen)

    client.request("PATCH", "/app/config", json={"updates": {"enabled": False}})
    res = client.get("/app/update/check")

    assert res.status_code == 200
    assert res.json()["enabled"] is False
    assert called["value"] is False


def test_patch_config_updates_section(bus_client):
    client = bus_client["client"]

    res = client.request(
        "PATCH",
        "/app/config",
        json={"updates": {"enabled": True, "check_on_startup": False, "channel": "stable"}},
    )

    assert res.status_code == 200

    cfg = client.get("/app/config")
    assert cfg.status_code == 200
    payload = cfg.json()
    assert payload["updates"]["enabled"] is True
    assert payload["updates"]["check_on_startup"] is False
    assert payload["updates"]["channel"] == "stable"
