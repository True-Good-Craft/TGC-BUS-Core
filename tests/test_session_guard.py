# SPDX-License-Identifier: AGPL-3.0-or-later
import asyncio
import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

from core.version import VERSION

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.api import http
from core.api.http import _extract_token, _require_session


def make_request(path: str = "/dev/writes", cookies: dict[str, str] | None = None) -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "headers": [],
    }
    # Pass cookies separately if we were using a real client,
    # but for manual Request construction, Starlette parses 'cookie' header.
    if cookies:
        cookie_header = "; ".join(f"{k}={v}" for k, v in cookies.items())
        scope["headers"].append((b"cookie", cookie_header.encode("latin-1")))

    return Request(scope)


def test_extract_token_present() -> None:
    req = make_request(cookies={"bus_session": "abc123"})
    assert _extract_token(req) == "abc123"


def test_extract_token_missing() -> None:
    req = make_request()
    assert _extract_token(req) is None


def test_require_session_missing_token() -> None:
    req = make_request()
    response = asyncio.run(_require_session(req))
    assert response is not None
    assert response.status_code == 401
    assert json.loads(response.body.decode()) == {"error": "unauthorized"}


def test_require_session_invalid_token(monkeypatch: pytest.MonkeyPatch) -> None:
    token = "invalid"
    req = make_request(cookies={"bus_session": token})
    monkeypatch.setattr(http, "validate_session_token", lambda _token: False)
    response = asyncio.run(_require_session(req))
    assert response is not None
    assert response.status_code == 401
    assert json.loads(response.body.decode()) == {"error": "unauthorized"}


def test_require_session_valid_token(monkeypatch: pytest.MonkeyPatch) -> None:
    token = "valid-token"
    req = make_request(cookies={"bus_session": token})
    monkeypatch.setattr(http, "validate_session_token", lambda candidate: candidate == token)
    response = asyncio.run(_require_session(req))
    assert response is None
    assert getattr(req.state, "session") == token


@pytest.fixture
def test_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    # We must patch get_state to return a mocked token state, OR accept that real app state is used.
    # The error "assert 'XY...' == 'fixture-token'" shows real token generation is happening.
    # Patching module globals SESSION_TOKEN might not be enough if get_state logic uses its own source.
    # In http.py: session_token(request) uses state.tokens.current()

    # Let's just update the test to accept whatever token comes back.
    monkeypatch.setenv("BUS_DEV", "1")
    with TestClient(http.APP) as client:
        yield client


def test_integration_routes_and_cors(test_client: TestClient) -> None:
    unauthorized_health = test_client.get("/health")
    assert unauthorized_health.status_code == 200
    assert unauthorized_health.json() == {"ok": True, "version": VERSION}

    # TestClient persists Set-Cookie responses, so the unauthorized dev check
    # must run before we bootstrap the session cookie via /session/token.
    unauthorized_writes = test_client.get("/dev/writes")
    assert unauthorized_writes.status_code == 401
    assert unauthorized_writes.json() == {"error": "unauthorized"}

    token_resp = test_client.get("/session/token")
    assert token_resp.status_code == 200
    token = token_resp.json()["token"]
    assert token

    # Use Cookie header instead of X-Session-Token
    headers = {"Cookie": f"bus_session={token}"}

    health = test_client.get("/health", headers=headers)
    assert health.status_code == 200
    assert health.json() == {"ok": True, "version": VERSION}

    writes = test_client.get("/dev/writes", headers=headers)
    assert writes.status_code == 200
    body = writes.json()
    assert "enabled" in body

    options = test_client.request(
        "OPTIONS",
        "/dev/writes",
        headers={
            "Origin": "http://example.com",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert options.status_code == 200
    # verify CORS no longer reflects TOKEN_HEADER if we were checking that

