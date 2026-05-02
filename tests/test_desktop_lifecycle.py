# Copyright (C) 2025 BUS Core Authors
# SPDX-License-Identifier: AGPL-3.0-or-later

import pytest
from fastapi.testclient import TestClient
from core.api.http import app, build_app

@pytest.fixture
def client():
    # Setup
    build_app()
    app.state.allow_writes = True
    return TestClient(app)

def test_config_lifecycle(client):
    # 1. Get Token
    resp = client.get("/session/token")
    assert resp.status_code == 200, "Failed to get token"

    token = resp.json()["token"]
    # Manually inject cookie header
    headers = {"Cookie": f"bus_session={token}"}

    # 2. GET config
    resp = client.get("/app/config", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "launcher" in data
    assert "ui" in data
    assert data["ui"]["theme"] in ["system", "light", "dark"]

    # 3. POST config
    # Ensure writes enabled
    app.state.allow_writes = True

    new_theme = "light"
    # Toggle to make sure we change it
    if data["ui"]["theme"] == "light":
        new_theme = "dark"

    payload = {"ui": {"theme": new_theme}}
    resp = client.post("/app/config", json=payload, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["restart_required"] is True

    # 4. Verify persistence via API
    resp = client.get("/app/config", headers=headers)
    assert resp.json()["ui"]["theme"] == new_theme

    # 5. Verify persistence via manager directly
    from core.config.manager import load_config
    c = load_config()
    assert c.ui.theme == new_theme

    # Restore default
    client.post("/app/config", json={"ui": {"theme": "system"}}, headers=headers)
