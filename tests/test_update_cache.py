# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.runtime import update_cache

pytestmark = pytest.mark.unit


def _root(tmp_path: Path) -> Path:
    return tmp_path / "LocalAppData" / "BUSCore" / "updates"


def _valid_state(root: Path) -> dict:
    return {
        "schema": 1,
        "active_version": "1.0.4",
        "verified_ready": {
            "version": "1.0.5",
            "channel": "stable",
            "exe_path": str(root / "versions" / "1.0.5" / "BUS-Core.exe"),
            "verified": True,
            "verified_at": "2026-04-24T12:00:00Z",
        },
        "handoff": {
            "last_attempted_version": None,
            "attempt_count": 0,
            "last_result": None,
        },
    }


def test_cache_root_uses_buscore_local_appdata(tmp_path, monkeypatch):
    local_appdata = tmp_path / "LocalAppData"
    monkeypatch.setenv("LOCALAPPDATA", str(local_appdata))

    assert update_cache.cache_root() == local_appdata / "BUSCore" / "updates"


def test_missing_state_returns_default_empty_state(tmp_path):
    state = update_cache.read_state(_root(tmp_path), active_version="1.0.4")

    assert state == update_cache.default_state("1.0.4")


def test_ensure_cache_dirs_creates_expected_directories(tmp_path):
    root = _root(tmp_path)

    update_cache.ensure_cache_dirs(root)

    assert root.is_dir()
    assert (root / "manifests").is_dir()
    assert (root / "downloads").is_dir()
    assert (root / "versions").is_dir()


def test_valid_state_round_trips(tmp_path):
    root = _root(tmp_path)
    state = _valid_state(root)

    written = update_cache.write_state(state, root, active_version="1.0.4")
    read_back = update_cache.read_state(root, active_version="1.0.4")

    assert read_back == written
    assert read_back["verified_ready"]["exe_path"] == str((root / "versions" / "1.0.5" / "BUS-Core.exe").resolve())


def test_malformed_state_is_handled_safely(tmp_path):
    root = _root(tmp_path)
    update_cache.ensure_cache_dirs(root)
    (root / "state.json").write_text("{not json", encoding="utf-8")

    assert update_cache.read_state(root, active_version="1.0.4") == update_cache.default_state("1.0.4")


def test_exe_path_outside_update_cache_is_rejected(tmp_path):
    root = _root(tmp_path)
    state = _valid_state(root)
    state["verified_ready"]["exe_path"] = str(tmp_path / "outside" / "BUS-Core.exe")

    with pytest.raises(update_cache.UpdateCacheStateError):
        update_cache.validate_state(state, root=root, active_version="1.0.4")


def test_traversal_exe_path_is_rejected(tmp_path):
    root = _root(tmp_path)
    state = _valid_state(root)
    state["verified_ready"]["exe_path"] = str(root / "versions" / "1.0.5" / ".." / ".." / "escape.exe")

    with pytest.raises(update_cache.UpdateCacheStateError):
        update_cache.validate_state(state, root=root, active_version="1.0.4")


def test_verified_ready_version_lower_or_equal_to_active_is_rejected(tmp_path):
    root = _root(tmp_path)
    state = _valid_state(root)
    state["verified_ready"]["version"] = "1.0.4"

    with pytest.raises(update_cache.UpdateCacheStateError):
        update_cache.validate_state(state, root=root, active_version="1.0.4")


def test_atomic_write_leaves_valid_json(tmp_path):
    root = _root(tmp_path)

    update_cache.write_state(_valid_state(root), root, active_version="1.0.4")

    payload = json.loads((root / "state.json").read_text(encoding="utf-8"))
    assert payload["schema"] == 1
    assert payload["verified_ready"]["version"] == "1.0.5"


def test_hash_verified_round_trips_and_normalizes_download_path(tmp_path):
    root = _root(tmp_path)
    state = _valid_state(root)
    state["hash_verified"] = {
        "version": "1.0.5",
        "channel": "stable",
        "artifact_path": str(root / "downloads" / "BUS-Core-1.0.5-stable.zip"),
        "sha256": "A" * 64,
        "size_bytes": 123,
        "downloaded": True,
        "hash_verified": True,
        "downloaded_at": "2026-04-25T12:00:00Z",
        "verified_at": "2026-04-25T12:00:00Z",
    }

    written = update_cache.write_state(state, root, active_version="1.0.4")

    assert written["hash_verified"]["artifact_path"] == str((root / "downloads" / "BUS-Core-1.0.5-stable.zip").resolve())
    assert written["hash_verified"]["sha256"] == "a" * 64
    assert written["verified_ready"]["version"] == "1.0.5"


def test_hash_verified_rejects_path_outside_downloads_dir(tmp_path):
    root = _root(tmp_path)
    state = _valid_state(root)
    state["hash_verified"] = {
        "version": "1.0.5",
        "channel": "stable",
        "artifact_path": str(root / "versions" / "1.0.5" / "BUS-Core.exe"),
        "sha256": "a" * 64,
        "size_bytes": 123,
        "downloaded": True,
        "hash_verified": True,
        "downloaded_at": "2026-04-25T12:00:00Z",
        "verified_at": "2026-04-25T12:00:00Z",
    }

    with pytest.raises(update_cache.UpdateCacheStateError):
        update_cache.validate_state(state, root=root, active_version="1.0.4")
