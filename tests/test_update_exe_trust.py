# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from core.runtime import update_cache
from core.services.update_exe_trust import ALLOWED_SIGNER_THUMBPRINTS, ExecutableTrustError, UpdateExecutableTrustService

pytestmark = pytest.mark.unit


def _root(tmp_path: Path) -> Path:
    return tmp_path / "LocalAppData" / "BUSCore" / "updates"


def _seed_extracted_state(root: Path, exe_path: Path) -> dict:
    state = update_cache.read_state(root, active_version="1.0.4")
    state["hash_verified"] = {
        "version": "1.0.5",
        "channel": "stable",
        "artifact_path": str((root / "downloads" / "BUS-Core-1.0.5-stable.zip").resolve(strict=False)),
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
        "artifact_path": str((root / "downloads" / "BUS-Core-1.0.5-stable.zip").resolve(strict=False)),
        "extracted_dir": str((root / "versions" / "1.0.5").resolve(strict=False)),
        "exe_path": str(exe_path.resolve(strict=False)),
        "sha256": "b" * 64,
        "size_bytes": 123,
        "extracted_at": "2026-04-25T12:01:00Z",
    }
    return update_cache.write_state(state, root, active_version="1.0.4")


def _write_exe(root: Path, name: str = "BUS-Core-1.0.5.exe") -> Path:
    exe_path = root / "versions" / "1.0.5" / name
    exe_path.parent.mkdir(parents=True, exist_ok=True)
    exe_path.write_bytes(b"signed-exe")
    return exe_path


def _completed_process(payload: dict[str, str], *, returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["powershell.exe"],
        returncode=returncode,
        stdout=json.dumps(payload),
        stderr="",
    )


def test_valid_signature_and_publisher_records_exe_verified(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = _root(tmp_path)
    update_cache.ensure_cache_dirs(root)
    exe_path = _write_exe(root)
    state = _seed_extracted_state(root, exe_path)

    monkeypatch.setattr("core.services.update_exe_trust._is_windows_platform", lambda: True)
    monkeypatch.setattr(
        "core.services.update_exe_trust.subprocess.run",
        lambda *args, **kwargs: _completed_process(
            {
                "status": "Valid",
                "status_message": "Signature verified.",
                "subject": "CN=True Good Craft, O=True Good Craft, C=US",
                "thumbprint": ALLOWED_SIGNER_THUMBPRINTS[0],
            }
        ),
    )

    verified = UpdateExecutableTrustService().verify(state["extracted"], root=root)

    stored_state = update_cache.read_state(root, active_version="1.0.4")
    assert verified.publisher == "True Good Craft"
    assert verified.signer_thumbprint == ALLOWED_SIGNER_THUMBPRINTS[0].lower()
    assert stored_state["exe_verified"] is not None
    assert stored_state["exe_verified"]["exe_path"] == str(exe_path.resolve())
    assert stored_state["exe_verified"]["publisher"] == "True Good Craft"
    assert stored_state["verified_ready"] is None


def test_thumbprint_normalizes_whitespace_and_case(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = _root(tmp_path)
    update_cache.ensure_cache_dirs(root)
    exe_path = _write_exe(root)
    state = _seed_extracted_state(root, exe_path)

    monkeypatch.setattr("core.services.update_exe_trust._is_windows_platform", lambda: True)
    monkeypatch.setattr(
        "core.services.update_exe_trust.subprocess.run",
        lambda *args, **kwargs: _completed_process(
            {
                "status": "Valid",
                "status_message": "Signature verified.",
                "subject": "CN=True Good Craft, O=True Good Craft, C=US",
                "thumbprint": " 55474aa9 a2d56202 2a6590d4 87045e06 9457f985 ",
            }
        ),
    )

    verified = UpdateExecutableTrustService().verify(state["extracted"], root=root)

    assert verified.signer_thumbprint == ALLOWED_SIGNER_THUMBPRINTS[0].lower()


def test_non_windows_platform_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = _root(tmp_path)
    update_cache.ensure_cache_dirs(root)
    exe_path = _write_exe(root)
    state = _seed_extracted_state(root, exe_path)

    monkeypatch.setattr("core.services.update_exe_trust._is_windows_platform", lambda: False)

    with pytest.raises(ExecutableTrustError) as exc_info:
        UpdateExecutableTrustService().verify(state["extracted"], root=root)

    assert exc_info.value.code == "unsupported_platform"
    assert update_cache.read_state(root, active_version="1.0.4")["exe_verified"] is None


def test_missing_exe_path_is_rejected(tmp_path: Path):
    with pytest.raises(ExecutableTrustError) as exc_info:
        UpdateExecutableTrustService().verify(
            {
                "version": "1.0.5",
                "channel": "stable",
                "extracted_dir": str((_root(tmp_path) / "versions" / "1.0.5").resolve(strict=False)),
                "exe_path": "",
                "sha256": "b" * 64,
                "size_bytes": 123,
            },
            root=_root(tmp_path),
        )

    assert exc_info.value.code == "invalid_exe_path"


def test_exe_path_outside_version_dir_is_rejected(tmp_path: Path):
    root = _root(tmp_path)
    update_cache.ensure_cache_dirs(root)
    outside = tmp_path / "outside" / "BUS-Core-1.0.5.exe"
    outside.parent.mkdir(parents=True, exist_ok=True)
    outside.write_bytes(b"outside")

    with pytest.raises(ExecutableTrustError) as exc_info:
        UpdateExecutableTrustService().verify(
            {
                "version": "1.0.5",
                "channel": "stable",
                "extracted_dir": str((root / "versions" / "1.0.5").resolve(strict=False)),
                "exe_path": str(outside.resolve()),
                "sha256": "b" * 64,
                "size_bytes": 123,
            },
            root=root,
        )

    assert exc_info.value.code == "invalid_exe_path"


def test_non_exe_path_is_rejected(tmp_path: Path):
    root = _root(tmp_path)
    update_cache.ensure_cache_dirs(root)
    text_path = _write_exe(root, name="BUS-Core-1.0.5.txt")

    with pytest.raises(ExecutableTrustError) as exc_info:
        UpdateExecutableTrustService().verify(
            {
                "version": "1.0.5",
                "channel": "stable",
                "extracted_dir": str((root / "versions" / "1.0.5").resolve(strict=False)),
                "exe_path": str(text_path.resolve()),
                "sha256": "b" * 64,
                "size_bytes": 123,
            },
            root=root,
        )

    assert exc_info.value.code == "invalid_exe_path"


def test_invalid_signature_status_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = _root(tmp_path)
    update_cache.ensure_cache_dirs(root)
    exe_path = _write_exe(root)
    state = _seed_extracted_state(root, exe_path)

    monkeypatch.setattr("core.services.update_exe_trust._is_windows_platform", lambda: True)
    monkeypatch.setattr(
        "core.services.update_exe_trust.subprocess.run",
        lambda *args, **kwargs: _completed_process(
            {
                "status": "NotSigned",
                "status_message": "No signature.",
                "subject": "",
                "thumbprint": "",
            }
        ),
    )

    with pytest.raises(ExecutableTrustError) as exc_info:
        UpdateExecutableTrustService().verify(state["extracted"], root=root)

    assert exc_info.value.code == "invalid_signature"


def test_wrong_publisher_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = _root(tmp_path)
    update_cache.ensure_cache_dirs(root)
    exe_path = _write_exe(root)
    state = _seed_extracted_state(root, exe_path)

    monkeypatch.setattr("core.services.update_exe_trust._is_windows_platform", lambda: True)
    monkeypatch.setattr(
        "core.services.update_exe_trust.subprocess.run",
        lambda *args, **kwargs: _completed_process(
            {
                "status": "Valid",
                "status_message": "Signature verified.",
                "subject": "CN=Other Publisher, O=Other Publisher, C=US",
                "thumbprint": ALLOWED_SIGNER_THUMBPRINTS[0],
            }
        ),
    )

    with pytest.raises(ExecutableTrustError) as exc_info:
        UpdateExecutableTrustService().verify(state["extracted"], root=root)

    assert exc_info.value.code == "wrong_publisher"


def test_wrong_thumbprint_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = _root(tmp_path)
    update_cache.ensure_cache_dirs(root)
    exe_path = _write_exe(root)
    state = _seed_extracted_state(root, exe_path)

    monkeypatch.setattr("core.services.update_exe_trust._is_windows_platform", lambda: True)
    monkeypatch.setattr(
        "core.services.update_exe_trust.subprocess.run",
        lambda *args, **kwargs: _completed_process(
            {
                "status": "Valid",
                "status_message": "Signature verified.",
                "subject": "CN=True Good Craft, O=True Good Craft, C=US",
                "thumbprint": "A" * 40,
            }
        ),
    )

    with pytest.raises(ExecutableTrustError) as exc_info:
        UpdateExecutableTrustService().verify(state["extracted"], root=root)

    assert exc_info.value.code == "untrusted_signer"


def test_missing_thumbprint_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = _root(tmp_path)
    update_cache.ensure_cache_dirs(root)
    exe_path = _write_exe(root)
    state = _seed_extracted_state(root, exe_path)

    monkeypatch.setattr("core.services.update_exe_trust._is_windows_platform", lambda: True)
    monkeypatch.setattr(
        "core.services.update_exe_trust.subprocess.run",
        lambda *args, **kwargs: _completed_process(
            {
                "status": "Valid",
                "status_message": "Signature verified.",
                "subject": "CN=True Good Craft, O=True Good Craft, C=US",
                "thumbprint": "",
            }
        ),
    )

    with pytest.raises(ExecutableTrustError) as exc_info:
        UpdateExecutableTrustService().verify(state["extracted"], root=root)

    assert exc_info.value.code == "untrusted_signer"


def test_powershell_failure_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = _root(tmp_path)
    update_cache.ensure_cache_dirs(root)
    exe_path = _write_exe(root)
    state = _seed_extracted_state(root, exe_path)

    monkeypatch.setattr("core.services.update_exe_trust._is_windows_platform", lambda: True)
    monkeypatch.setattr(
        "core.services.update_exe_trust.subprocess.run",
        lambda *args, **kwargs: _completed_process({}, returncode=1),
    )

    with pytest.raises(ExecutableTrustError) as exc_info:
        UpdateExecutableTrustService().verify(state["extracted"], root=root)

    assert exc_info.value.code == "signature_check_failed"
    assert update_cache.read_state(root, active_version="1.0.4")["exe_verified"] is None