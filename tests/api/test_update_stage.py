# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import pytest

from core.services.update_stage import UpdateStageResult

pytestmark = pytest.mark.api


EXPECTED_STAGE_KEYS = {
    "ok",
    "status",
    "current_version",
    "latest_version",
    "exe_path",
    "restart_available",
    "error_code",
    "error_message",
}


def test_update_check_contract_unchanged(bus_client):
    response = bus_client["client"].get("/app/update/check")

    assert response.status_code == 200
    assert set(response.json().keys()) == {
        "current_version",
        "latest_version",
        "update_available",
        "download_url",
        "error_code",
        "error_message",
    }


def test_update_stage_endpoint_returns_update_not_available(bus_client, monkeypatch: pytest.MonkeyPatch):
    from core.api.routes import update as update_routes

    monkeypatch.setattr(
        update_routes,
        "get_update_stage_service",
        lambda: type(
            "Svc",
            (),
            {
                "stage_from_config": staticmethod(
                    lambda: UpdateStageResult(
                        ok=False,
                        status="failed",
                        current_version="1.0.4",
                        latest_version="1.0.4",
                        exe_path=None,
                        restart_available=False,
                        error_code="update_not_available",
                        error_message="No newer version is available.",
                    )
                )
            },
        )(),
    )

    response = bus_client["client"].post("/app/update/stage", json={})

    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == EXPECTED_STAGE_KEYS
    assert body["ok"] is False
    assert body["error_code"] == "update_not_available"


def test_update_stage_requires_auth_session(bus_client):
    client = bus_client["client"]
    client.headers.pop("Cookie", None)

    response = client.post("/app/update/stage", json={})

    assert response.status_code == 401


def test_update_stage_requires_writes_enabled(bus_client):
    api_http = bus_client["api_http"]
    api_http.app.state.allow_writes = False

    response = bus_client["client"].post("/app/update/stage", json={})

    assert response.status_code == 403
    body = response.json()
    assert body.get("detail", {}).get("error") == "writes_disabled"


def test_update_stage_success_payload(bus_client, monkeypatch: pytest.MonkeyPatch):
    from core.api.routes import update as update_routes

    monkeypatch.setattr(
        update_routes,
        "get_update_stage_service",
        lambda: type(
            "Svc",
            (),
            {
                "stage_from_config": staticmethod(
                    lambda: UpdateStageResult(
                        ok=True,
                        status="verified_ready",
                        current_version="1.0.4",
                        latest_version="1.0.5",
                        exe_path="C:/cache/versions/1.0.5/BUS-Core.exe",
                        restart_available=True,
                        error_code=None,
                        error_message=None,
                    )
                )
            },
        )(),
    )

    response = bus_client["client"].post("/app/update/stage", json={})

    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == EXPECTED_STAGE_KEYS
    assert body["ok"] is True
    assert body["status"] == "verified_ready"
    assert body["restart_available"] is True
