# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from core.runtime import update_cache
from core.services.update import ManifestRelease
from core.services.update_artifact import ArtifactDownloadError, UpdateArtifactService

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def production_update_url_policy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BUS_DEV", "0")
    monkeypatch.delenv("BUS_ALLOW_DEV_UPDATE_MANIFEST_URLS", raising=False)


def _root(tmp_path: Path) -> Path:
    return tmp_path / "LocalAppData" / "BUSCore" / "updates"


def _release(
    *,
    version: str = "1.0.5",
    channel: str = "stable",
    download_url: str = "https://example.test/TGC-BUS-Core-1.0.5.zip",
    declared_sha256: str | None,
    declared_size_bytes: int | None,
) -> ManifestRelease:
    return ManifestRelease(
        version=version,
        channel=channel,
        download_url=download_url,
        declared_sha256=declared_sha256,
        declared_size_bytes=declared_size_bytes,
    )


def test_download_success_writes_final_file_and_hash_verified_state(tmp_path: Path):
    payload = b"bus-core-update-artifact"
    digest = hashlib.sha256(payload).hexdigest()
    release = _release(declared_sha256=digest, declared_size_bytes=len(payload))

    service = UpdateArtifactService(fetch_artifact=lambda _url, _timeout: [payload])
    downloaded = service.download_and_verify(release, root=_root(tmp_path))

    final_path = Path(downloaded.artifact_path)
    assert final_path.exists()
    assert final_path.read_bytes() == payload
    assert final_path.parent == update_cache.downloads_dir(_root(tmp_path)).resolve()

    state = update_cache.read_state(_root(tmp_path), active_version="1.0.4")
    assert state["hash_verified"] is not None
    assert state["hash_verified"]["hash_verified"] is True
    assert state["hash_verified"]["downloaded"] is True
    assert state["hash_verified"]["artifact_path"] == str(final_path)
    assert state["verified_ready"] is None


def test_sha256_mismatch_fails_closed_and_leaves_no_final_artifact(tmp_path: Path):
    payload = b"artifact-bytes"
    wrong_digest = "a" * 64
    release = _release(declared_sha256=wrong_digest, declared_size_bytes=len(payload))

    service = UpdateArtifactService(fetch_artifact=lambda _url, _timeout: [payload])
    with pytest.raises(ArtifactDownloadError) as exc_info:
        service.download_and_verify(release, root=_root(tmp_path))

    assert exc_info.value.code == "artifact_hash_mismatch"
    downloads_root = update_cache.downloads_dir(_root(tmp_path))
    assert list(downloads_root.glob("*.zip")) == []
    assert list(downloads_root.glob("*.part.*")) == []

    state = update_cache.read_state(_root(tmp_path), active_version="1.0.4")
    assert state["hash_verified"] is None


def test_missing_declared_sha256_fails_closed(tmp_path: Path):
    release = _release(declared_sha256=None, declared_size_bytes=10)

    service = UpdateArtifactService(fetch_artifact=lambda _url, _timeout: [b"bytes"])
    with pytest.raises(ArtifactDownloadError) as exc_info:
        service.download_and_verify(release, root=_root(tmp_path))

    assert exc_info.value.code == "missing_declared_sha256"


def test_declared_size_mismatch_fails_closed(tmp_path: Path):
    payload = b"abc123"
    digest = hashlib.sha256(payload).hexdigest()
    release = _release(declared_sha256=digest, declared_size_bytes=len(payload) + 1)

    service = UpdateArtifactService(fetch_artifact=lambda _url, _timeout: [payload])
    with pytest.raises(ArtifactDownloadError) as exc_info:
        service.download_and_verify(release, root=_root(tmp_path))

    assert exc_info.value.code == "artifact_size_mismatch"
    assert list(update_cache.downloads_dir(_root(tmp_path)).glob("*.part.*")) == []


@pytest.mark.parametrize(
    "download_url",
    [
        "http://localhost/update.zip",
        "http://127.0.0.1/update.zip",
        "https://192.168.10.15/update.zip",
        "file:///tmp/update.zip",
        "javascript:alert(1)",
    ],
)
def test_invalid_download_url_fails_closed_outside_dev(tmp_path: Path, download_url: str):
    payload = b"artifact"
    digest = hashlib.sha256(payload).hexdigest()
    release = _release(download_url=download_url, declared_sha256=digest, declared_size_bytes=len(payload))

    service = UpdateArtifactService(fetch_artifact=lambda _url, _timeout: [payload])
    with pytest.raises(ArtifactDownloadError) as exc_info:
        service.download_and_verify(release, root=_root(tmp_path))

    assert exc_info.value.code == "invalid_download_url"


def test_filename_is_derived_safely_not_from_url_path(tmp_path: Path):
    payload = b"artifact"
    digest = hashlib.sha256(payload).hexdigest()
    release = _release(
        version="1.0.5",
        channel="stable",
        download_url="https://example.test/../../evil.zip",
        declared_sha256=digest,
        declared_size_bytes=len(payload),
    )

    service = UpdateArtifactService(fetch_artifact=lambda _url, _timeout: [payload])
    downloaded = service.download_and_verify(release, root=_root(tmp_path))

    final_path = Path(downloaded.artifact_path)
    assert ".." not in final_path.name
    assert final_path.name == "BUS-Core-1.0.5-stable.zip"
    assert final_path.parent == update_cache.downloads_dir(_root(tmp_path)).resolve()


def test_partial_file_is_not_kept_when_download_fails(tmp_path: Path):
    payload = b"payload"
    wrong_digest = "b" * 64
    release = _release(declared_sha256=wrong_digest, declared_size_bytes=len(payload))

    service = UpdateArtifactService(fetch_artifact=lambda _url, _timeout: [payload])
    with pytest.raises(ArtifactDownloadError):
        service.download_and_verify(release, root=_root(tmp_path))

    downloads_root = update_cache.downloads_dir(_root(tmp_path))
    assert list(downloads_root.glob("*.part.*")) == []


def test_network_failure_leaves_no_success_state(tmp_path: Path):
    payload = b"payload"
    digest = hashlib.sha256(payload).hexdigest()
    release = _release(declared_sha256=digest, declared_size_bytes=len(payload))

    def _failing_fetch(_url: str, _timeout: float):
        raise TimeoutError("simulated timeout")

    service = UpdateArtifactService(fetch_artifact=_failing_fetch)
    with pytest.raises(ArtifactDownloadError) as exc_info:
        service.download_and_verify(release, root=_root(tmp_path))

    assert exc_info.value.code == "timeout"
    state = update_cache.read_state(_root(tmp_path), active_version="1.0.4")
    assert state["hash_verified"] is None
