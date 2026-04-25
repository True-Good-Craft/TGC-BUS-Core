# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path

import pytest

from core.runtime import update_cache
from core.services.update_extract import ArtifactExtractError, UpdateArtifactExtractService

pytestmark = pytest.mark.unit


def _root(tmp_path: Path) -> Path:
    return tmp_path / "LocalAppData" / "BUSCore" / "updates"


def _downloads_root(tmp_path: Path) -> Path:
    root = _root(tmp_path)
    update_cache.ensure_cache_dirs(root)
    return update_cache.downloads_dir(root)


def _artifact_record(tmp_path: Path, artifact_path: Path, *, version: str = "1.0.5") -> dict:
    payload = artifact_path.read_bytes()
    return {
        "version": version,
        "channel": "stable",
        "artifact_path": str(artifact_path.resolve(strict=False)),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "size_bytes": len(payload),
        "downloaded": True,
        "hash_verified": True,
        "downloaded_at": "2026-04-25T12:00:00Z",
        "verified_at": "2026-04-25T12:00:00Z",
    }


def _write_zip(path: Path, members: list[tuple[str, bytes]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in members:
            archive.writestr(name, payload)


def test_valid_zip_extracts_to_versions_dir_and_records_extracted_state(tmp_path: Path):
    downloads_root = _downloads_root(tmp_path)
    artifact_path = downloads_root / "BUS-Core-1.0.5-stable.zip"
    _write_zip(
        artifact_path,
        [
            ("BUS-Core-1.0.5.exe", b"exe-bytes"),
            ("assets/readme.txt", b"notes"),
        ],
    )

    root = _root(tmp_path)
    state = update_cache.read_state(root, active_version="1.0.4")
    state["hash_verified"] = _artifact_record(tmp_path, artifact_path)
    update_cache.write_state(state, root, active_version="1.0.4")

    extracted = UpdateArtifactExtractService().extract(state["hash_verified"], root=root)

    extracted_dir = Path(extracted.extracted_dir)
    exe_path = Path(extracted.exe_path)
    assert extracted_dir == (update_cache.versions_dir(root) / "1.0.5").resolve()
    assert exe_path == (extracted_dir / "BUS-Core-1.0.5.exe").resolve()
    assert exe_path.read_bytes() == b"exe-bytes"
    assert artifact_path.exists()

    stored_state = update_cache.read_state(root, active_version="1.0.4")
    assert stored_state["hash_verified"]["artifact_path"] == str(artifact_path.resolve())
    assert stored_state["extracted"]["extracted_dir"] == str(extracted_dir)
    assert stored_state["extracted"]["exe_path"] == str(exe_path)
    assert stored_state["verified_ready"] is None


def test_zip_slip_entry_is_rejected_and_temp_dir_is_cleaned(tmp_path: Path):
    downloads_root = _downloads_root(tmp_path)
    artifact_path = downloads_root / "BUS-Core-1.0.5-stable.zip"
    _write_zip(
        artifact_path,
        [
            ("../escape.exe", b"bad"),
            ("BUS-Core-1.0.5.exe", b"good"),
        ],
    )

    root = _root(tmp_path)
    record = _artifact_record(tmp_path, artifact_path)

    with pytest.raises(ArtifactExtractError) as exc_info:
        UpdateArtifactExtractService().extract(record, root=root)

    assert exc_info.value.code == "unsafe_zip_entry"
    assert not (update_cache.versions_dir(root) / "1.0.5").exists()
    assert list(update_cache.versions_dir(root).glob(".extracting-*")) == []


def test_absolute_zip_entry_is_rejected(tmp_path: Path):
    downloads_root = _downloads_root(tmp_path)
    artifact_path = downloads_root / "BUS-Core-1.0.5-stable.zip"
    _write_zip(artifact_path, [("/absolute/evil.exe", b"bad")])

    with pytest.raises(ArtifactExtractError) as exc_info:
        UpdateArtifactExtractService().extract(_artifact_record(tmp_path, artifact_path), root=_root(tmp_path))

    assert exc_info.value.code == "unsafe_zip_entry"
    assert not (update_cache.versions_dir(_root(tmp_path)) / "1.0.5").exists()


def test_source_outside_downloads_is_rejected(tmp_path: Path):
    outside_path = tmp_path / "outside.zip"
    _write_zip(outside_path, [("BUS-Core-1.0.5.exe", b"exe-bytes")])

    with pytest.raises(ArtifactExtractError) as exc_info:
        UpdateArtifactExtractService().extract(_artifact_record(tmp_path, outside_path), root=_root(tmp_path))

    assert exc_info.value.code == "invalid_artifact_path"


def test_zero_exe_is_rejected(tmp_path: Path):
    downloads_root = _downloads_root(tmp_path)
    artifact_path = downloads_root / "BUS-Core-1.0.5-stable.zip"
    _write_zip(artifact_path, [("notes.txt", b"not executable")])

    with pytest.raises(ArtifactExtractError) as exc_info:
        UpdateArtifactExtractService().extract(_artifact_record(tmp_path, artifact_path), root=_root(tmp_path))

    assert exc_info.value.code == "missing_exe"
    assert not (update_cache.versions_dir(_root(tmp_path)) / "1.0.5").exists()


def test_multiple_exes_are_rejected(tmp_path: Path):
    downloads_root = _downloads_root(tmp_path)
    artifact_path = downloads_root / "BUS-Core-1.0.5-stable.zip"
    _write_zip(
        artifact_path,
        [
            ("BUS-Core-1.0.5.exe", b"one"),
            ("tools/helper.exe", b"two"),
        ],
    )

    with pytest.raises(ArtifactExtractError) as exc_info:
        UpdateArtifactExtractService().extract(_artifact_record(tmp_path, artifact_path), root=_root(tmp_path))

    assert exc_info.value.code == "multiple_exes"
    assert list(update_cache.versions_dir(_root(tmp_path)).glob(".extracting-*")) == []


def test_original_artifact_remains_in_downloads_after_success(tmp_path: Path):
    downloads_root = _downloads_root(tmp_path)
    artifact_path = downloads_root / "BUS-Core-1.0.5-stable.zip"
    _write_zip(artifact_path, [("BUS-Core-1.0.5.exe", b"exe-bytes")])

    UpdateArtifactExtractService().extract(_artifact_record(tmp_path, artifact_path), root=_root(tmp_path))

    assert artifact_path.exists()
    assert artifact_path.parent == downloads_root.resolve()