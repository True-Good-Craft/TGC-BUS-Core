# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

from core.api import http
import tgc.security as tgc_security



def make_request(
    path: str = "/app/system/state",
    cookies: dict[str, str] | None = None,
    app=None,
) -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "headers": [],
    }
    if app is not None:
        scope["app"] = app
    if cookies:
        cookie_header = "; ".join(f"{k}={v}" for k, v in cookies.items())
        scope["headers"].append((b"cookie", cookie_header.encode("latin-1")))
    return Request(scope)



def test_tgc_security_wrapper_delegates_to_canonical_validator(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[Request] = []

    def _fake_require_token_ctx(request: Request):
        calls.append(request)
        return {"token": "delegated"}

    monkeypatch.setattr(http, "require_token_ctx", _fake_require_token_ctx)
    req = make_request(cookies={"bus_session": "delegated"}, app=http.app)

    result = asyncio.run(tgc_security.require_token_ctx(req))

    assert result is None
    assert calls == [req]



def test_validate_session_token_prefers_runtime_token_over_stale_mirror(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime_token = "runtime-token"
    stale_token = "stale-token"

    monkeypatch.setattr(http.app.state.app_state.tokens._rec, "token", runtime_token)
    monkeypatch.setattr(http, "SESSION_TOKEN", stale_token)
    monkeypatch.setattr(
        http,
        "_load_or_create_token",
        lambda: pytest.fail("validate_session_token should not fall back when AppState token exists"),
    )

    assert http.validate_session_token(runtime_token) is True
    assert http.validate_session_token(stale_token) is False



def test_extract_token_honors_configured_cookie_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(http.app.state.app_state.settings, "session_cookie_name", "custom_session")

    custom_req = make_request(cookies={"custom_session": "custom-token"}, app=http.app)
    default_req = make_request(cookies={"bus_session": "default-token"}, app=http.app)

    assert http._extract_token(custom_req) == "custom-token"
    assert http._extract_token(default_req) == "default-token"



def test_auth_authority_routes_share_same_session_contract(bus_client) -> None:
    client = bus_client["client"]
    api_http = bus_client["api_http"]

    wrapper_resp = client.get("/app/system/state")
    canonical_resp = client.get("/oauth/google/status")

    assert wrapper_resp.status_code == 200
    assert canonical_resp.status_code == 200

    with TestClient(api_http.APP) as anon_client:
        anon_wrapper = anon_client.get("/app/system/state")
        anon_canonical = anon_client.get("/oauth/google/status")

    assert anon_wrapper.status_code == 401
    assert anon_canonical.status_code == 401



def test_auth_authority_drift_guards_cover_code_and_docs() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    tgc_security_source = (repo_root / "tgc" / "security.py").read_text(encoding="utf-8")
    http_source = (repo_root / "core" / "api" / "http.py").read_text(encoding="utf-8")
    system_map = (repo_root / "01_SYSTEM_MAP.md").read_text(encoding="utf-8")
    data_map = (repo_root / "03_DATA_CONFIG_AND_STATE_MODEL.md").read_text(encoding="utf-8")
    security_map = (repo_root / "04_SECURITY_TRUST_AND_OPERATIONS.md").read_text(encoding="utf-8")
    sot = (repo_root / "SOT.md").read_text(encoding="utf-8")

    assert "tokens.check(" not in tgc_security_source
    assert "Compatibility wrapper" in tgc_security_source
    assert "def _expected_session_token()" in http_source

    for doc in (system_map, data_map, security_map, sot):
        assert "tgc.security.require_token_ctx" in doc
        assert "compatibility wrapper" in doc
        assert "core.api.http" in doc
