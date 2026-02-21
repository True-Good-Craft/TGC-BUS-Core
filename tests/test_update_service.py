# Copyright (C) 2025 BUS Core Authors
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

import asyncio
import json

import requests

from core.services import update_service
from core.services.update_service import UpdateService, parse_semver


class _MockResponse:
    """Mock response object compatible with requests.Response API."""
    def __init__(self, payload: dict):
        self._payload = payload
        self.status_code = 200

    def json(self) -> dict:
        return self._payload

    def raise_for_status(self) -> None:
        """No-op for successful responses."""
        pass


def test_parse_semver_strict():
    assert parse_semver("0.11.0") == (0, 11, 0)
    for bad in ("0.11", "v0.11.0", "0.11.0-beta", "a.b.c"):
        try:
            parse_semver(bad)
            raise AssertionError("expected ValueError")
        except ValueError:
            pass


def test_check_disabled_skips_http(monkeypatch):
    called = {"value": False}

    def _mock_get(*args, **kwargs):
        called["value"] = True
        raise AssertionError("requests.get should not be called")

    monkeypatch.setattr("requests.get", _mock_get)
    svc = UpdateService(config={"updates": {"enabled": False}}, version="0.11.0")

    result = asyncio.run(svc.check())

    assert result == {"enabled": False, "current_version": "0.11.0"}
    assert called["value"] is False


def test_check_enabled_manifest_ok(monkeypatch):
    def _mock_get(*args, **kwargs):
        return _MockResponse(
            {
                "min_supported": "0.10.0",
                "latest": {
                    "version": "0.11.1",
                    "release_notes_url": "https://example.com/notes",
                    "download": {
                        "url": "https://example.com/core.exe",
                        "sha256": "abc123",
                        "size_bytes": 123,
                    },
                },
            }
        )

    monkeypatch.setattr("requests.get", _mock_get)
    svc = UpdateService(config={"updates": {"enabled": True, "manifest_url": "https://example.com/m.json"}}, version="0.11.0")

    result = asyncio.run(svc.check())

    assert result["enabled"] is True
    assert result["is_update_available"] is True
    assert result["is_supported"] is True
    assert result["latest_version"] == "0.11.1"
    assert result["error"] is None


def test_manifest_invalid_schema(monkeypatch):
    def _mock_get(*args, **kwargs):
        return _MockResponse({"latest": {"version": "0.11.1"}})

    monkeypatch.setattr("requests.get", _mock_get)
    svc = UpdateService(config={"updates": {"enabled": True}}, version="0.11.0")

    result = asyncio.run(svc.check())

    assert result["error"]["code"] == "MANIFEST_INVALID_SCHEMA"


def test_invalid_latest_semver_maps_invalid_schema(monkeypatch):
    def _mock_get(*args, **kwargs):
        return _MockResponse(
            {
                "latest": {
                    "version": "v0.11.2",
                    "download": {
                        "url": "https://example.com/core.exe",
                        "sha256": "abc123",
                    },
                },
            }
        )

    monkeypatch.setattr("requests.get", _mock_get)
    svc = UpdateService(config={"updates": {"enabled": True}}, version="0.11.0")

    result = asyncio.run(svc.check())

    assert result["error"]["code"] == "MANIFEST_INVALID_SCHEMA"


def test_invalid_min_supported_maps_invalid_schema(monkeypatch):
    def _mock_get(*args, **kwargs):
        return _MockResponse(
            {
                "min_supported": "invalid",
                "latest": {
                    "version": "0.11.2",
                    "download": {
                        "url": "https://example.com/core.exe",
                        "sha256": "abc123",
                    },
                },
            }
        )

    monkeypatch.setattr("requests.get", _mock_get)
    svc = UpdateService(config={"updates": {"enabled": True}}, version="0.11.0")

    result = asyncio.run(svc.check())

    assert result["error"]["code"] == "MANIFEST_INVALID_SCHEMA"


def test_min_supported_false(monkeypatch):
    def _mock_get(*args, **kwargs):
        return _MockResponse(
            {
                "min_supported": "0.11.1",
                "latest": {
                    "version": "0.11.2",
                    "download": {
                        "url": "https://example.com/core.exe",
                        "sha256": "abc123",
                    },
                },
            }
        )

    monkeypatch.setattr("requests.get", _mock_get)
    svc = UpdateService(config={"updates": {"enabled": True}}, version="0.11.0")

    result = asyncio.run(svc.check())

    assert result["is_supported"] is False


def test_urlerror_maps_unreachable(monkeypatch):
    def _mock_get(*args, **kwargs):
        raise requests.RequestException("offline")

    monkeypatch.setattr("requests.get", _mock_get)
    svc = UpdateService(config={"updates": {"enabled": True}}, version="0.11.0")

    result = asyncio.run(svc.check())

    assert result["error"]["code"] == "MANIFEST_UNREACHABLE"


def test_generic_exception_maps_unreachable(monkeypatch):
    def _fetch_manifest(*args, **kwargs):
        return {
            "latest": {
                "version": "0.11.1",
                "download": {
                    "url": "https://example.com/core.exe",
                    "sha256": "abc123",
                },
            }
        }

    def _normalize(*args, **kwargs):
        raise Exception("boom")

    monkeypatch.setattr(UpdateService, "_fetch_manifest", _fetch_manifest)
    monkeypatch.setattr(UpdateService, "_normalize", _normalize)

    svc = UpdateService(config={"updates": {"enabled": True}}, version="0.11.0")
    result = asyncio.run(svc.check())

    assert result["error"]["code"] == "MANIFEST_UNREACHABLE"
    assert result["error"]["message"] == "unexpected error during update check"
