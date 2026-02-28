# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import json
import pytest

from core.config.manager import Config, UpdatesConfig
from core.services.update import REQUEST_TIMEOUT_SECONDS, UpdateService

pytestmark = pytest.mark.api


EXPECTED_KEYS = {
    "current_version",
    "latest_version",
    "update_available",
    "download_url",
    "error_code",
    "error_message",
}


class _StreamResponse:
    def __init__(self, *, status_code: int = 200, headers: dict[str, str] | None = None, chunks: list[bytes] | None = None):
        self.status_code = status_code
        self.headers = headers or {"content-type": "application/json"}
        self._chunks = chunks or []

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError("http error")

    def iter_bytes(self):
        for chunk in self._chunks:
            yield chunk


class _StreamContext:
    def __init__(self, response: _StreamResponse):
        self._response = response

    def __enter__(self):
        return self._response

    def __exit__(self, exc_type, exc, tb):
        return False


def _set_updates(monkeypatch: pytest.MonkeyPatch, *, enabled: bool, channel: str = "stable", manifest_url: str = "https://example.test/manifest.json") -> None:
    from core.api.routes import update as update_routes

    cfg = Config(updates=UpdatesConfig(enabled=enabled, channel=channel, manifest_url=manifest_url))
    monkeypatch.setattr(update_routes, "load_config", lambda: cfg)


def _assert_contract(body: dict) -> None:
    assert set(body.keys()) == EXPECTED_KEYS


def test_update_check_works_even_when_updates_disabled(bus_client, monkeypatch: pytest.MonkeyPatch):
    from core.api.routes import update as update_routes

    _set_updates(monkeypatch, enabled=False)
    service = UpdateService(fetch_manifest=lambda _url, _timeout: {"version": "9.9.9", "download_url": "https://example.test/dl"})
    monkeypatch.setattr(update_routes, "get_update_service", lambda: service)

    response = bus_client["client"].get("/app/update/check")

    assert response.status_code == 200
    body = response.json()
    _assert_contract(body)
    assert body["error_code"] is None
    assert body["update_available"] is True
    assert body["download_url"] == "https://example.test/dl"


def test_update_check_invalid_scheme_rejected_no_network_call(bus_client, monkeypatch: pytest.MonkeyPatch):
    from core.api.routes import update as update_routes

    called = {"count": 0}

    def _fetch(_url: str, _timeout: float):
        called["count"] += 1
        return {"version": "1.0.0"}

    _set_updates(monkeypatch, enabled=True, manifest_url="file:///etc/passwd")
    monkeypatch.setattr(update_routes, "get_update_service", lambda: UpdateService(fetch_manifest=_fetch))

    response = bus_client["client"].get("/app/update/check")

    assert response.status_code == 200
    body = response.json()
    _assert_contract(body)
    assert body["error_code"] == "invalid_manifest_url"
    assert called["count"] == 0


def test_update_check_data_scheme_rejected(bus_client, monkeypatch: pytest.MonkeyPatch):
    _set_updates(monkeypatch, enabled=True, manifest_url="data:application/json,{}")

    response = bus_client["client"].get("/app/update/check")

    assert response.status_code == 200
    body = response.json()
    _assert_contract(body)
    assert body["error_code"] == "invalid_manifest_url"


def test_update_check_localhost_rejected(bus_client, monkeypatch: pytest.MonkeyPatch):
    _set_updates(monkeypatch, enabled=True, manifest_url="http://localhost/manifest.json")

    response = bus_client["client"].get("/app/update/check")

    assert response.status_code == 200
    body = response.json()
    _assert_contract(body)
    assert body["error_code"] == "manifest_url_not_allowed"


def test_update_check_private_literal_ip_rejected(bus_client, monkeypatch: pytest.MonkeyPatch):
    _set_updates(monkeypatch, enabled=True, manifest_url="http://192.168.1.10/manifest.json")

    response = bus_client["client"].get("/app/update/check")

    assert response.status_code == 200
    body = response.json()
    _assert_contract(body)
    assert body["error_code"] == "manifest_url_not_allowed"


def test_update_check_redirect_treated_as_network_error(bus_client, monkeypatch: pytest.MonkeyPatch):
    from core.services import update as update_module

    _set_updates(monkeypatch, enabled=True)

    def _fake_stream(_method, _url, **_kwargs):
        response = _StreamResponse(status_code=302, headers={"content-type": "application/json"}, chunks=[b"{}"])
        return _StreamContext(response)

    monkeypatch.setattr(update_module.httpx, "stream", _fake_stream, raising=False)

    response = bus_client["client"].get("/app/update/check")

    assert response.status_code == 200
    body = response.json()
    _assert_contract(body)
    assert body["error_code"] == "network_error"


def test_update_check_stream_over_limit_rejected(bus_client, monkeypatch: pytest.MonkeyPatch):
    from core.services import update as update_module

    _set_updates(monkeypatch, enabled=True)
    payload = b"a" * 40000

    def _fake_stream(_method, _url, **_kwargs):
        response = _StreamResponse(
            status_code=200,
            headers={"content-type": "application/json"},
            chunks=[b"{\"version\":\"1.2.3\",\"pad\":\"", payload, payload, b"\"}"],
        )
        return _StreamContext(response)

    monkeypatch.setattr(update_module.httpx, "stream", _fake_stream, raising=False)

    response = bus_client["client"].get("/app/update/check")

    body = response.json()
    _assert_contract(body)
    assert body["error_code"] == "manifest_too_large"


def test_update_check_download_url_surfaced_when_update_available(bus_client, monkeypatch: pytest.MonkeyPatch):
    from core.api.routes import update as update_routes

    _set_updates(monkeypatch, enabled=True)
    service = UpdateService(fetch_manifest=lambda _url, _timeout: {"version": "9.9.9", "download_url": "https://example.test/dl"})
    monkeypatch.setattr(update_routes, "get_update_service", lambda: service)

    response = bus_client["client"].get("/app/update/check")

    body = response.json()
    _assert_contract(body)
    assert body["update_available"] is True
    assert body["download_url"] == "https://example.test/dl"


def test_update_check_wrong_content_type_rejected(bus_client, monkeypatch: pytest.MonkeyPatch):
    from core.services import update as update_module

    _set_updates(monkeypatch, enabled=True)

    def _fake_stream(_method, _url, **_kwargs):
        response = _StreamResponse(status_code=200, headers={"content-type": "text/html"}, chunks=[b"<html></html>"])
        return _StreamContext(response)

    monkeypatch.setattr(update_module.httpx, "stream", _fake_stream, raising=False)

    response = bus_client["client"].get("/app/update/check")

    body = response.json()
    _assert_contract(body)
    assert body["error_code"] == "invalid_manifest"


def test_update_check_follow_redirects_disabled_and_timeout_configured(bus_client, monkeypatch: pytest.MonkeyPatch):
    from core.services import update as update_module

    _set_updates(monkeypatch, enabled=True)
    seen = {}

    def _fake_stream(_method, _url, **kwargs):
        seen.update(kwargs)
        body = json.dumps({"version": "0.11.0", "download_url": "https://example.test/dl"}).encode()
        response = _StreamResponse(
            status_code=200,
            headers={"content-type": "application/json", "content-length": str(len(body))},
            chunks=[body],
        )
        return _StreamContext(response)

    monkeypatch.setattr(update_module.httpx, "stream", _fake_stream, raising=False)

    response = bus_client["client"].get("/app/update/check")

    assert response.status_code == 200
    body = response.json()
    _assert_contract(body)
    assert seen.get("follow_redirects") is False
    assert "timeout" in seen


def test_update_check_injected_fetch_receives_hard_timeout(bus_client, monkeypatch: pytest.MonkeyPatch):
    from core.api.routes import update as update_routes

    _set_updates(monkeypatch, enabled=True)

    seen_timeout: list[float] = []

    def _fetch(_url: str, timeout_s: float):
        seen_timeout.append(timeout_s)
        return {"version": "0.11.0", "download_url": "https://example.test/dl"}

    service = UpdateService(fetch_manifest=_fetch)
    monkeypatch.setattr(update_routes, "get_update_service", lambda: service)

    response = bus_client["client"].get("/app/update/check")

    assert response.status_code == 200
    assert seen_timeout == [REQUEST_TIMEOUT_SECONDS]


def test_canonical_manifest_shape_update_available(bus_client, monkeypatch: pytest.MonkeyPatch):
    from core.api.routes import update as update_routes

    _set_updates(monkeypatch, enabled=True)
    service = UpdateService(
        fetch_manifest=lambda _url, _timeout: {
            "min_supported": "0.1.0",
            "latest": {
                "version": "9.9.9",
                "release_notes_url": "https://example.test/release-notes",
                "size_bytes": 12345,
                "download": {
                    "url": "https://example.test/canonical-dl",
                    "sha256": "abc123",
                    "size_bytes": 12345,
                },
            },
        }
    )
    monkeypatch.setattr(update_routes, "get_update_service", lambda: service)

    response = bus_client["client"].get("/app/update/check")

    assert response.status_code == 200
    body = response.json()
    _assert_contract(body)
    assert body["error_code"] is None
    assert body["update_available"] is True
    assert body["download_url"] == "https://example.test/canonical-dl"


def test_canonical_manifest_no_update(bus_client, monkeypatch: pytest.MonkeyPatch):
    from core.api.routes import update as update_routes
    from core.version import VERSION as CURRENT_VERSION

    _set_updates(monkeypatch, enabled=True)
    service = UpdateService(
        fetch_manifest=lambda _url, _timeout: {
            "min_supported": "0.1.0",
            "latest": {
                "version": CURRENT_VERSION,
                "download": {
                    "url": "https://example.test/canonical-dl",
                },
            },
        }
    )
    monkeypatch.setattr(update_routes, "get_update_service", lambda: service)

    response = bus_client["client"].get("/app/update/check")

    assert response.status_code == 200
    body = response.json()
    _assert_contract(body)
    assert body["error_code"] is None
    assert body["update_available"] is False
    assert body["download_url"] is None


def test_canonical_manifest_missing_download(bus_client, monkeypatch: pytest.MonkeyPatch):
    from core.api.routes import update as update_routes

    _set_updates(monkeypatch, enabled=True)
    service = UpdateService(
        fetch_manifest=lambda _url, _timeout: {
            "min_supported": "0.1.0",
            "latest": {
                "version": "9.9.9",
            },
        }
    )
    monkeypatch.setattr(update_routes, "get_update_service", lambda: service)

    response = bus_client["client"].get("/app/update/check")

    assert response.status_code == 200
    body = response.json()
    _assert_contract(body)
    assert body["error_code"] == "invalid_manifest"
