# Copyright (C) 2025 BUS Core Authors
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

import asyncio
import json
from urllib.error import URLError

from core.services import update_service
from core.services.update_service import UpdateService, parse_semver


class _Resp:
    def __init__(self, payload: dict):
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return None


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

    def _urlopen(*args, **kwargs):
        called["value"] = True
        raise AssertionError("should not be called")

    monkeypatch.setattr(update_service, "urlopen", _urlopen)
    svc = UpdateService(config={"updates": {"enabled": False}}, version="0.11.0")

    result = asyncio.run(svc.check())

    assert result == {"enabled": False, "current_version": "0.11.0"}
    assert called["value"] is False


def test_check_enabled_manifest_ok(monkeypatch):
    def _urlopen(*args, **kwargs):
        return _Resp(
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

    monkeypatch.setattr(update_service, "urlopen", _urlopen)
    svc = UpdateService(config={"updates": {"enabled": True, "manifest_url": "https://example.com/m.json"}}, version="0.11.0")

    result = asyncio.run(svc.check())

    assert result["enabled"] is True
    assert result["is_update_available"] is True
    assert result["is_supported"] is True
    assert result["latest_version"] == "0.11.1"
    assert result["error"] is None


def test_manifest_invalid_schema(monkeypatch):
    def _urlopen(*args, **kwargs):
        return _Resp({"latest": {"version": "0.11.1"}})

    monkeypatch.setattr(update_service, "urlopen", _urlopen)
    svc = UpdateService(config={"updates": {"enabled": True}}, version="0.11.0")

    result = asyncio.run(svc.check())

    assert result["error"]["code"] == "MANIFEST_INVALID_SCHEMA"


def test_invalid_latest_semver_maps_invalid_schema(monkeypatch):
    def _urlopen(*args, **kwargs):
        return _Resp(
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

    monkeypatch.setattr(update_service, "urlopen", _urlopen)
    svc = UpdateService(config={"updates": {"enabled": True}}, version="0.11.0")

    result = asyncio.run(svc.check())

    assert result["error"]["code"] == "MANIFEST_INVALID_SCHEMA"


def test_invalid_min_supported_maps_invalid_schema(monkeypatch):
    def _urlopen(*args, **kwargs):
        return _Resp(
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

    monkeypatch.setattr(update_service, "urlopen", _urlopen)
    svc = UpdateService(config={"updates": {"enabled": True}}, version="0.11.0")

    result = asyncio.run(svc.check())

    assert result["error"]["code"] == "MANIFEST_INVALID_SCHEMA"


def test_min_supported_false(monkeypatch):
    def _urlopen(*args, **kwargs):
        return _Resp(
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

    monkeypatch.setattr(update_service, "urlopen", _urlopen)
    svc = UpdateService(config={"updates": {"enabled": True}}, version="0.11.0")

    result = asyncio.run(svc.check())

    assert result["is_supported"] is False


def test_urlerror_maps_unreachable(monkeypatch):
    def _urlopen(*args, **kwargs):
        raise URLError("offline")

    monkeypatch.setattr(update_service, "urlopen", _urlopen)
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
