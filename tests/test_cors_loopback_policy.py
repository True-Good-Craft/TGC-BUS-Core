# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.cors import CORSMiddleware

REPO_ROOT = Path(__file__).resolve().parents[1]
HTTP_SOURCE = REPO_ROOT / "core/api/http.py"


def _cors_settings() -> dict[str, Any]:
    tree = ast.parse(HTTP_SOURCE.read_text(encoding="utf-8"), filename=str(HTTP_SOURCE))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not node.args:
            continue
        middleware_arg = node.args[0]
        if not isinstance(middleware_arg, ast.Name) or middleware_arg.id != "CORSMiddleware":
            continue
        settings: dict[str, Any] = {}
        for keyword in node.keywords:
            if keyword.arg is not None:
                settings[keyword.arg] = ast.literal_eval(keyword.value)
        return settings
    raise AssertionError("core/api/http.py must configure CORSMiddleware explicitly")


def _cors_test_client() -> TestClient:
    app = FastAPI()
    app.add_middleware(CORSMiddleware, **_cors_settings())

    @app.get("/health")
    def health() -> dict[str, bool]:
        return {"ok": True}

    return TestClient(app)


def test_default_cors_config_is_loopback_only_and_not_wildcard() -> None:
    settings = _cors_settings()

    assert settings["allow_origins"] == [
        "http://127.0.0.1:8765",
        "http://localhost:8765",
    ]
    assert "*" not in settings["allow_origins"]
    assert "*" not in settings["allow_methods"]
    assert settings.get("allow_credentials", False) is False


def test_allowed_loopback_origin_receives_cors_allow_origin() -> None:
    client = _cors_test_client()
    origin = "http://127.0.0.1:8765"

    response = client.options(
        "/health",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin


def test_untrusted_origin_does_not_receive_permissive_cors_headers() -> None:
    client = _cors_test_client()
    origin = "http://evil.example"

    response = client.options(
        "/health",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.headers.get("access-control-allow-origin") not in {origin, "*"}


def test_same_origin_api_call_without_origin_header_is_unaffected() -> None:
    client = _cors_test_client()

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert "access-control-allow-origin" not in response.headers
