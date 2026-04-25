# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from pathlib import Path

import pytest

from core.runtime import update_cache
from core.services.update_promote import UpdatePromotionError, UpdateReadyPromotionService

pytestmark = pytest.mark.unit


def _root(tmp_path: Path) -> Path:
    return tmp_path / "LocalAppData" / "BUSCore" / "updates"


def _seed_state(root: Path) -> dict:
    update_cache.ensure_cache_dirs(root)
    artifact_path = root / "downloads" / "BUS-Core-1.0.5-stable.zip"
    artifact_path.write_bytes(b"zip-bytes")
    extracted_dir = root / "versions" / "1.0.5"
    extracted_dir.mkdir(parents=True, exist_ok=True)
    exe_path = extracted_dir / "BUS-Core-1.0.5.exe"
    exe_path.write_bytes(b"exe-bytes")

    state = update_cache.read_state(root, active_version="1.0.4")
    state["hash_verified"] = {
        "version": "1.0.5",
        "channel": "stable",
        "artifact_path": str(artifact_path.resolve()),
        "sha256": "a" * 64,
        "size_bytes": 123,
        "downloaded": True,
        "hash_verified": True,
        "downloaded_at": "2026-04-25T12:00:00Z",
        "verified_at": "2026-04-25T12:00:01Z",
    }
    state["extracted"] = {
        "version": "1.0.5",
        "channel": "stable",
        "artifact_path": str(artifact_path.resolve()),
        "extracted_dir": str(extracted_dir.resolve()),
        "exe_path": str(exe_path.resolve()),
        "sha256": "a" * 64,
        "size_bytes": 123,
        "extracted_at": "2026-04-25T12:01:00Z",
    }
    state["exe_verified"] = {
        "version": "1.0.5",
        "channel": "stable",
        "extracted_dir": str(extracted_dir.resolve()),
        "exe_path": str(exe_path.resolve()),
        "sha256": "a" * 64,
        "size_bytes": 123,
        "publisher": "True Good Craft",
        "signer_subject": "CN=True Good Craft, O=True Good Craft",
        "signer_thumbprint": "55474aa9a2d562022a6590d487045e069457f985",
        "verified": True,
        "verified_at": "2026-04-25T12:02:00Z",
    }
    return update_cache.write_state(state, root, active_version="1.0.4")


def test_happy_path_promotes_to_verified_ready(tmp_path: Path):
    root = _root(tmp_path)
    state = _seed_state(root)

    promoted = UpdateReadyPromotionService().promote(state, root=root)

    stored = update_cache.read_state(root, active_version="1.0.4")
    assert promoted.version == "1.0.5"
    assert stored["verified_ready"] is not None
    assert stored["verified_ready"]["artifact_path"] == state["hash_verified"]["artifact_path"]
    assert stored["verified_ready"]["extracted_dir"] == state["extracted"]["extracted_dir"]
    assert stored["verified_ready"]["exe_path"] == state["extracted"]["exe_path"]
    assert stored["verified_ready"]["sha256"] == "a" * 64
    assert stored["verified_ready"]["publisher"] == "True Good Craft"


def test_missing_hash_verified_is_rejected(tmp_path: Path):
    root = _root(tmp_path)
    state = _seed_state(root)
    state["hash_verified"] = None

    with pytest.raises(UpdatePromotionError) as exc_info:
        UpdateReadyPromotionService().promote(state, root=root)

    assert exc_info.value.code == "missing_hash_verified"
    assert update_cache.read_state(root, active_version="1.0.4")["verified_ready"] is None


def test_missing_extracted_is_rejected(tmp_path: Path):
    root = _root(tmp_path)
    state = _seed_state(root)
    state["extracted"] = None

    with pytest.raises(UpdatePromotionError) as exc_info:
        UpdateReadyPromotionService().promote(state, root=root)

    assert exc_info.value.code == "missing_extracted"


def test_missing_exe_verified_is_rejected(tmp_path: Path):
    root = _root(tmp_path)
    state = _seed_state(root)
    state["exe_verified"] = None

    with pytest.raises(UpdatePromotionError) as exc_info:
        UpdateReadyPromotionService().promote(state, root=root)

    assert exc_info.value.code == "missing_exe_verified"


def test_mismatched_version_is_rejected(tmp_path: Path):
    root = _root(tmp_path)
    state = _seed_state(root)
    state["exe_verified"] = dict(state["exe_verified"])
    state["exe_verified"]["version"] = "1.0.6"

    with pytest.raises(UpdatePromotionError) as exc_info:
        UpdateReadyPromotionService().promote(state, root=root)

    assert exc_info.value.code == "mismatched_version"


def test_mismatched_channel_is_rejected(tmp_path: Path):
    root = _root(tmp_path)
    state = _seed_state(root)
    state["extracted"] = dict(state["extracted"])
    state["extracted"]["channel"] = "beta"

    with pytest.raises(UpdatePromotionError) as exc_info:
        UpdateReadyPromotionService().promote(state, root=root)

    assert exc_info.value.code == "mismatched_channel"


def test_mismatched_sha256_is_rejected(tmp_path: Path):
    root = _root(tmp_path)
    state = _seed_state(root)
    state["extracted"] = dict(state["extracted"])
    state["extracted"]["sha256"] = "b" * 64

    with pytest.raises(UpdatePromotionError) as exc_info:
        UpdateReadyPromotionService().promote(state, root=root)

    assert exc_info.value.code == "mismatched_sha256"


def test_artifact_outside_downloads_is_rejected(tmp_path: Path):
    root = _root(tmp_path)
    state = _seed_state(root)
    outside = tmp_path / "outside.zip"
    outside.write_bytes(b"zip-bytes")
    state["hash_verified"] = dict(state["hash_verified"])
    state["hash_verified"]["artifact_path"] = str(outside.resolve())
    state["extracted"] = dict(state["extracted"])
    state["extracted"]["artifact_path"] = str(outside.resolve())

    with pytest.raises(UpdatePromotionError) as exc_info:
        UpdateReadyPromotionService().promote(state, root=root)

    assert exc_info.value.code == "invalid_artifact_path"


def test_extracted_dir_outside_versions_is_rejected(tmp_path: Path):
    root = _root(tmp_path)
    state = _seed_state(root)
    outside_dir = tmp_path / "outside-version"
    outside_dir.mkdir(parents=True, exist_ok=True)
    state["extracted"] = dict(state["extracted"])
    state["extracted"]["extracted_dir"] = str(outside_dir.resolve())
    state["exe_verified"] = dict(state["exe_verified"])
    state["exe_verified"]["extracted_dir"] = str(outside_dir.resolve())

    with pytest.raises(UpdatePromotionError) as exc_info:
        UpdateReadyPromotionService().promote(state, root=root)

    assert exc_info.value.code == "invalid_extracted_dir"


def test_exe_path_outside_extracted_dir_is_rejected(tmp_path: Path):
    root = _root(tmp_path)
    state = _seed_state(root)
    outside_exe = tmp_path / "outside" / "BUS-Core-1.0.5.exe"
    outside_exe.parent.mkdir(parents=True, exist_ok=True)
    outside_exe.write_bytes(b"exe-bytes")
    state["extracted"] = dict(state["extracted"])
    state["extracted"]["exe_path"] = str(outside_exe.resolve())
    state["exe_verified"] = dict(state["exe_verified"])
    state["exe_verified"]["exe_path"] = str(outside_exe.resolve())

    with pytest.raises(UpdatePromotionError) as exc_info:
        UpdateReadyPromotionService().promote(state, root=root)

    assert exc_info.value.code == "invalid_exe_path"


def test_exe_verified_false_is_rejected(tmp_path: Path):
    root = _root(tmp_path)
    state = _seed_state(root)
    state["exe_verified"] = dict(state["exe_verified"])
    state["exe_verified"]["verified"] = False

    with pytest.raises(UpdatePromotionError) as exc_info:
        UpdateReadyPromotionService().promote(state, root=root)

    assert exc_info.value.code == "missing_exe_verified"


def test_missing_exe_file_is_rejected(tmp_path: Path):
    root = _root(tmp_path)
    state = _seed_state(root)
    Path(state["extracted"]["exe_path"]).unlink()

    with pytest.raises(UpdatePromotionError) as exc_info:
        UpdateReadyPromotionService().promote(state, root=root)

    assert exc_info.value.code == "invalid_exe_path"
    assert update_cache.read_state(root, active_version="1.0.4")["verified_ready"] is None


def test_failure_leaves_existing_states_unchanged(tmp_path: Path):
    root = _root(tmp_path)
    state = _seed_state(root)
    original = update_cache.read_state(root, active_version="1.0.4")
    state["extracted"] = dict(state["extracted"])
    state["extracted"]["sha256"] = "b" * 64

    with pytest.raises(UpdatePromotionError):
        UpdateReadyPromotionService().promote(state, root=root)

    stored = update_cache.read_state(root, active_version="1.0.4")
    assert stored["hash_verified"] == original["hash_verified"]
    assert stored["extracted"] == original["extracted"]
    assert stored["exe_verified"] == original["exe_verified"]
    assert stored["verified_ready"] is None