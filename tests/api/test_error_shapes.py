# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import pytest

pytestmark = pytest.mark.api


def test_array_payload_sanitized(bus_client):
    resp = bus_client["client"].post("/app/manufacturing/run", json=[])

    assert resp.status_code == 400
    assert resp.json()["detail"]["error"] == "bad_request"


def test_invalid_type_sanitized(bus_client):
    resp = bus_client["client"].post("/app/manufacturing/run", json="oops")

    assert resp.status_code == 400
    assert "error" in resp.json().get("detail", {})


def test_validation_error_envelope(bus_client):
    resp = bus_client["client"].post("/app/manufacturing/run")

    body = resp.json()
    assert resp.status_code == 400
    assert body["detail"]["error"] == "validation_error"
    assert body["detail"].get("fields")
