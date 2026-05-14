# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from core.runtime.manifest_trust import canonicalize_manifest_payload
from core.services.update import ManifestRelease, UpdateCheckError, UpdateService
from core.services.update_artifact import ArtifactDownloadError
from core.services.update_exe_trust import ExecutableTrustError
from core.services.update_extract import ExtractedArtifact
from core.services.update_extract import ArtifactExtractError
from core.services.update_promote import UpdatePromotionError
from core.services.update_stage import UpdateStageService
from core.version import VERSION as CURRENT_VERSION

pytestmark = pytest.mark.unit

FUTURE_VERSION = "9.9.9"
TEST_KEY_ID = "test-stage-manifest-key"


class _UpdateSvc:
    def __init__(self, release: ManifestRelease | None = None, exc: Exception | None = None, calls: list[str] | None = None) -> None:
        self.release = release
        self.exc = exc
        self.calls = calls

    def select_release(self, *, manifest_url: str, channel: str) -> ManifestRelease:
        if self.calls is not None:
            self.calls.append("check")
        if self.exc is not None:
            raise self.exc
        assert self.release is not None
        return self.release


class _ArtifactSvc:
    def __init__(self, calls: list[str], exc: Exception | None = None) -> None:
        self.calls = calls
        self.exc = exc

    def download_and_verify(self, release, *, root=None):
        self.calls.append("download")
        if self.exc is not None:
            raise self.exc
        return {
            "version": release.version,
            "channel": release.channel,
            "artifact_path": str(Path(root) / "downloads" / f"BUS-Core-{release.version}.zip"),
            "sha256": release.declared_sha256,
            "size_bytes": release.declared_size_bytes,
            "downloaded": True,
            "hash_verified": True,
        }


class _ExtractSvc:
    def __init__(self, calls: list[str], exc: Exception | None = None) -> None:
        self.calls = calls
        self.exc = exc

    def extract(self, downloaded, *, root=None):
        self.calls.append("extract")
        if self.exc is not None:
            raise self.exc
        version = downloaded["version"]
        return {
            "version": version,
            "channel": downloaded["channel"],
            "artifact_path": downloaded["artifact_path"],
            "extracted_dir": str(Path(root) / "versions" / version),
            "exe_path": str(Path(root) / "versions" / version / "BUS-Core.exe"),
            "sha256": downloaded["sha256"],
            "size_bytes": downloaded["size_bytes"],
        }


class _ExeSvc:
    def __init__(self, calls: list[str], exc: Exception | None = None, seen: list[object] | None = None) -> None:
        self.calls = calls
        self.exc = exc
        self.seen = seen

    def verify(self, extracted, *, root=None):
        self.calls.append("verify")
        if self.seen is not None:
            self.seen.append(extracted)
        if self.exc is not None:
            raise self.exc
        return extracted


class _PromoteSvc:
    def __init__(self, calls: list[str], exc: Exception | None = None) -> None:
        self.calls = calls
        self.exc = exc

    def promote(self, state, *, root=None):
        self.calls.append("promote")
        if self.exc is not None:
            raise self.exc

        class _Promoted:
            exe_path = str(Path(root) / "versions" / FUTURE_VERSION / "BUS-Core.exe")

        return _Promoted()


def _ready_record(root: Path, *, version: str, sha256: str) -> dict[str, object]:
    artifact_path = root / "downloads" / f"BUS-Core-{version}-stable.zip"
    extracted_dir = root / "versions" / version
    exe_path = extracted_dir / "BUS-Core.exe"
    return {
        "version": version,
        "channel": "stable",
        "artifact_path": str(artifact_path.resolve(strict=False)),
        "extracted_dir": str(extracted_dir.resolve(strict=False)),
        "exe_path": str(exe_path.resolve(strict=False)),
        "sha256": sha256,
        "size_bytes": 123,
        "publisher": "True Good Craft",
        "signer_subject": "CN=True Good Craft, O=True Good Craft",
        "signer_thumbprint": "55474aa9a2d562022a6590d487045e069457f985",
        "verified": True,
        "verified_at": "2026-05-13T12:00:00Z",
        "ready_at": "2026-05-13T12:00:00Z",
    }


def _release(*, version: str = FUTURE_VERSION, declared_sha256: str | None = "a" * 64) -> ManifestRelease:
    return ManifestRelease(
        version=version,
        channel="stable",
        download_url="https://example.test/BUS-Core.zip",
        declared_sha256=declared_sha256,
        declared_size_bytes=123,
    )


def _manifest_payload(*, version: str = FUTURE_VERSION, sha256: str = "a" * 64) -> dict[str, Any]:
    return {
        "latest": {
            "version": version,
            "download": {
                "url": "https://example.test/BUS-Core.zip",
                "sha256": sha256,
                "size_bytes": 123,
            },
        }
    }


def _signed_embedded_manifest(
    payload: dict[str, Any],
    *,
    key_id: str = TEST_KEY_ID,
) -> tuple[dict[str, Any], dict[str, bytes]]:
    private_key = Ed25519PrivateKey.generate()
    public_bytes = private_key.public_key().public_bytes(encoding=Encoding.Raw, format=PublicFormat.Raw)
    signature = private_key.sign(canonicalize_manifest_payload(payload))
    manifest = dict(payload)
    manifest["signature"] = {
        "alg": "Ed25519",
        "key_id": key_id,
        "sig": base64.b64encode(signature).decode("ascii"),
    }
    return manifest, {key_id: public_bytes}


def _stage_service_for_manifest(
    manifest: dict[str, Any],
    *,
    trusted_keys: dict[str, bytes] | None = None,
    require_signed_manifest: bool = True,
    calls: list[str] | None = None,
) -> UpdateStageService:
    pipeline_calls = calls if calls is not None else []
    return UpdateStageService(
        update_service=UpdateService(
            fetch_manifest=lambda _url, _timeout: manifest,
            trusted_manifest_public_keys=trusted_keys or {},
            require_signed_manifest=require_signed_manifest,
        ),
        artifact_service=_ArtifactSvc(pipeline_calls),
        extract_service=_ExtractSvc(pipeline_calls),
        exe_trust_service=_ExeSvc(pipeline_calls),
        promote_service=_PromoteSvc(pipeline_calls),
    )


def _patch_empty_update_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("core.services.update_stage.update_cache.ensure_cache_dirs", lambda root=None: root or tmp_path)
    monkeypatch.setattr(
        "core.services.update_stage.update_cache.read_state",
        lambda *_args, **_kwargs: {
            "hash_verified": {},
            "extracted": {},
            "exe_verified": {},
            "verified_ready": None,
        },
    )


def test_stage_success_calls_pipeline_in_order(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    calls: list[str] = []
    service = UpdateStageService(
        update_service=_UpdateSvc(_release(), calls=calls),
        artifact_service=_ArtifactSvc(calls),
        extract_service=_ExtractSvc(calls),
        exe_trust_service=_ExeSvc(calls),
        promote_service=_PromoteSvc(calls),
    )

    monkeypatch.setattr("core.services.update_stage.update_cache.read_state", lambda *_args, **_kwargs: {
        "hash_verified": {},
        "extracted": {},
        "exe_verified": {},
        "verified_ready": None,
    })
    monkeypatch.setattr("core.services.update_stage.update_cache.ensure_cache_dirs", lambda root=None: root or tmp_path)

    result = service.stage(manifest_url="https://example.test/manifest.json", channel="stable", root=tmp_path)

    assert result.ok is True
    assert result.status == "verified_ready"
    assert result.restart_available is True
    assert calls == ["check", "download", "extract", "verify", "promote"]


def test_stage_returns_update_not_available_for_equal_version(tmp_path: Path):
    service = UpdateStageService(update_service=_UpdateSvc(_release(version=CURRENT_VERSION)))

    result = service.stage(manifest_url="https://example.test/manifest.json", channel="stable", root=tmp_path)

    assert result.ok is False
    assert result.error_code == "update_not_available"


def test_stage_missing_sha256_fails_before_download(tmp_path: Path):
    calls: list[str] = []
    service = UpdateStageService(
        update_service=_UpdateSvc(_release(declared_sha256=None)),
        artifact_service=_ArtifactSvc(calls),
    )

    result = service.stage(manifest_url="https://example.test/manifest.json", channel="stable", root=tmp_path)

    assert result.ok is False
    assert result.error_code == "missing_declared_sha256"
    assert calls == []


def test_stage_download_failure_maps_error(tmp_path: Path):
    calls: list[str] = []
    service = UpdateStageService(
        update_service=_UpdateSvc(_release()),
        artifact_service=_ArtifactSvc(calls, ArtifactDownloadError("artifact_hash_mismatch", "hash mismatch")),
    )

    result = service.stage(manifest_url="https://example.test/manifest.json", channel="stable", root=tmp_path)

    assert result.ok is False
    assert result.error_code == "artifact_hash_mismatch"


def test_stage_extract_failure_maps_error(tmp_path: Path):
    calls: list[str] = []
    service = UpdateStageService(
        update_service=_UpdateSvc(_release()),
        artifact_service=_ArtifactSvc(calls),
        extract_service=_ExtractSvc(calls, ArtifactExtractError("invalid_zip", "bad zip")),
    )

    result = service.stage(manifest_url="https://example.test/manifest.json", channel="stable", root=tmp_path)

    assert result.ok is False
    assert result.error_code == "invalid_zip"


def test_stage_exe_verify_failure_maps_error(tmp_path: Path):
    calls: list[str] = []
    service = UpdateStageService(
        update_service=_UpdateSvc(_release()),
        artifact_service=_ArtifactSvc(calls),
        extract_service=_ExtractSvc(calls),
        exe_trust_service=_ExeSvc(calls, ExecutableTrustError("wrong_publisher", "bad signer")),
    )

    result = service.stage(manifest_url="https://example.test/manifest.json", channel="stable", root=tmp_path)

    assert result.ok is False
    assert result.error_code == "wrong_publisher"


def test_stage_promote_failure_maps_error(tmp_path: Path):
    calls: list[str] = []
    service = UpdateStageService(
        update_service=_UpdateSvc(_release()),
        artifact_service=_ArtifactSvc(calls),
        extract_service=_ExtractSvc(calls),
        exe_trust_service=_ExeSvc(calls),
        promote_service=_PromoteSvc(calls, UpdatePromotionError("mismatched_version", "mismatch")),
    )

    result = service.stage(manifest_url="https://example.test/manifest.json", channel="stable", root=tmp_path)

    assert result.ok is False
    assert result.error_code == "mismatched_version"


def test_stage_idempotent_when_verified_ready_already_present(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    calls: list[str] = []
    service = UpdateStageService(
        update_service=_UpdateSvc(_release(version=FUTURE_VERSION)),
        artifact_service=_ArtifactSvc(calls),
    )
    exe_path = tmp_path / "versions" / FUTURE_VERSION / "BUS-Core.exe"
    exe_path.parent.mkdir(parents=True, exist_ok=True)
    exe_path.write_bytes(b"exe")
    ready = _ready_record(tmp_path, version=FUTURE_VERSION, sha256="a" * 64)

    monkeypatch.setattr("core.services.update_stage.update_cache.ensure_cache_dirs", lambda root=None: root or tmp_path)
    monkeypatch.setattr(
        "core.services.update_stage.update_cache.read_state",
        lambda *_args, **_kwargs: {
            "verified_ready": ready,
            "verified_ready_versions": {FUTURE_VERSION: {"a" * 64: ready}},
        },
    )

    result = service.stage(manifest_url="https://example.test/manifest.json", channel="stable", root=tmp_path)

    assert result.ok is True
    assert result.status == "already_ready"
    assert calls == []


def test_stage_ignores_older_verified_ready_and_restages_exact_latest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from core.runtime import update_cache
    from core.services.update_promote import UpdateReadyPromotionService

    calls: list[str] = []
    old_version = "1.1.1"
    latest_version = "1.2.0"
    old_sha = "1" * 64
    latest_sha = "2" * 64
    root = tmp_path / "updates"
    update_cache.ensure_cache_dirs(root)

    old_artifact = update_cache.downloads_dir(root) / f"BUS-Core-{old_version}-stable.zip"
    old_artifact.write_bytes(b"old zip")
    old_dir = update_cache.versions_dir(root) / old_version
    old_dir.mkdir(parents=True, exist_ok=True)
    old_exe = old_dir / "BUS-Core.exe"
    old_exe.write_bytes(b"old exe")
    old_ready = _ready_record(root, version=old_version, sha256=old_sha)
    state = update_cache.read_state(root, active_version=old_version)
    state["verified_ready"] = old_ready
    state["verified_ready_versions"] = {old_version: {old_sha: old_ready}}
    update_cache.write_state(state, root, active_version=old_version)

    class _WritingArtifactSvc(_ArtifactSvc):
        def download_and_verify(self, release, *, root=None):
            self.calls.append("download")
            target_root = Path(root)
            artifact_path = update_cache.downloads_dir(target_root) / f"BUS-Core-{release.version}-stable.zip"
            artifact_path.write_bytes(b"new zip")
            state = update_cache.read_state(target_root, active_version=old_version)
            state["hash_verified"] = {
                "version": release.version,
                "channel": release.channel,
                "artifact_path": str(artifact_path.resolve()),
                "sha256": release.declared_sha256,
                "size_bytes": release.declared_size_bytes,
                "downloaded": True,
                "hash_verified": True,
                "downloaded_at": "2026-05-13T12:01:00Z",
                "verified_at": "2026-05-13T12:01:00Z",
            }
            update_cache.write_state(state, target_root, active_version=old_version)
            return state["hash_verified"]

    class _WritingExtractSvc(_ExtractSvc):
        def extract(self, downloaded, *, root=None):
            self.calls.append("extract")
            target_root = Path(root)
            extracted_dir = update_cache.versions_dir(target_root) / downloaded["version"]
            extracted_dir.mkdir(parents=True, exist_ok=False)
            exe_path = extracted_dir / "BUS-Core.exe"
            exe_path.write_bytes(b"new exe")
            state = update_cache.read_state(target_root, active_version=old_version)
            state["extracted"] = {
                "version": downloaded["version"],
                "channel": downloaded["channel"],
                "artifact_path": downloaded["artifact_path"],
                "extracted_dir": str(extracted_dir.resolve()),
                "exe_path": str(exe_path.resolve()),
                "sha256": downloaded["sha256"],
                "size_bytes": downloaded["size_bytes"],
                "extracted_at": "2026-05-13T12:02:00Z",
            }
            update_cache.write_state(state, target_root, active_version=old_version)
            return state["extracted"]

    class _WritingExeSvc(_ExeSvc):
        def verify(self, extracted, *, root=None):
            self.calls.append("verify")
            target_root = Path(root)
            state = update_cache.read_state(target_root, active_version=old_version)
            state["exe_verified"] = {
                "version": extracted["version"],
                "channel": extracted["channel"],
                "extracted_dir": extracted["extracted_dir"],
                "exe_path": extracted["exe_path"],
                "sha256": extracted["sha256"],
                "size_bytes": extracted["size_bytes"],
                "publisher": "True Good Craft",
                "signer_subject": "CN=True Good Craft, O=True Good Craft",
                "signer_thumbprint": "55474aa9a2d562022a6590d487045e069457f985",
                "verified": True,
                "verified_at": "2026-05-13T12:03:00Z",
            }
            update_cache.write_state(state, target_root, active_version=old_version)
            return state["exe_verified"]

    monkeypatch.setattr("core.services.update_stage.CURRENT_VERSION", old_version)
    monkeypatch.setattr("core.services.update_promote.CURRENT_VERSION", old_version)
    service = UpdateStageService(
        update_service=_UpdateSvc(_release(version=latest_version, declared_sha256=latest_sha), calls=calls),
        artifact_service=_WritingArtifactSvc(calls),
        extract_service=_WritingExtractSvc(calls),
        exe_trust_service=_WritingExeSvc(calls),
        promote_service=UpdateReadyPromotionService(),
    )

    staged = service.stage(manifest_url="https://example.test/manifest.json", channel="stable", root=root)
    stored = update_cache.read_state(root, active_version=old_version)

    assert staged.ok is True
    assert staged.status == "verified_ready"
    assert calls == ["check", "download", "extract", "verify"]
    assert stored["verified_ready_versions"][old_version][old_sha]["exe_path"] == str(old_exe.resolve())
    assert stored["verified_ready_versions"][latest_version][latest_sha]["exe_path"].endswith("BUS-Core.exe")
    assert old_exe.exists()

    restaged = service.stage(manifest_url="https://example.test/manifest.json", channel="stable", root=root)

    assert restaged.ok is True
    assert restaged.status == "already_ready"
    assert calls == ["check", "download", "extract", "verify", "check"]


def test_stage_update_check_error_maps_code(tmp_path: Path):
    service = UpdateStageService(
        update_service=_UpdateSvc(exc=UpdateCheckError("invalid_manifest", "bad manifest")),
    )

    result = service.stage(manifest_url="https://example.test/manifest.json", channel="stable", root=tmp_path)

    assert result.ok is False
    assert result.error_code == "invalid_manifest"


def test_stage_passes_extracted_dataclass_metadata_to_exe_verify(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    calls: list[str] = []
    seen: list[object] = []

    class _ExtractDataclassSvc(_ExtractSvc):
        def extract(self, downloaded, *, root=None):
            self.calls.append("extract")
            version = downloaded["version"]
            return ExtractedArtifact(
                version=version,
                channel=downloaded["channel"],
                artifact_path=downloaded["artifact_path"],
                extracted_dir=str(Path(root) / "versions" / version),
                exe_path=str(Path(root) / "versions" / version / "BUS-Core.exe"),
                sha256=downloaded["sha256"],
                size_bytes=downloaded["size_bytes"],
                extracted_at="2026-04-25T12:00:00Z",
            )

    service = UpdateStageService(
        update_service=_UpdateSvc(_release(), calls=calls),
        artifact_service=_ArtifactSvc(calls),
        extract_service=_ExtractDataclassSvc(calls),
        exe_trust_service=_ExeSvc(calls, seen=seen),
        promote_service=_PromoteSvc(calls),
    )

    monkeypatch.setattr("core.services.update_stage.update_cache.ensure_cache_dirs", lambda root=None: root or tmp_path)
    monkeypatch.setattr(
        "core.services.update_stage.update_cache.read_state",
        lambda *_args, **_kwargs: {
            "hash_verified": {},
            "extracted": {},
            "exe_verified": {},
            "verified_ready": None,
        },
    )

    result = service.stage(manifest_url="https://example.test/manifest.json", channel="stable", root=tmp_path)

    assert result.ok is True
    assert len(seen) == 1
    handed = seen[0]
    assert isinstance(handed, dict)
    assert handed["version"] == FUTURE_VERSION
    assert handed["channel"] == "stable"
    assert handed["artifact_path"].endswith(f"BUS-Core-{FUTURE_VERSION}.zip")
    assert handed["exe_path"].endswith("BUS-Core.exe")


def test_stage_missing_extracted_metadata_fails_clearly(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    calls: list[str] = []

    class _BrokenExtractSvc(_ExtractSvc):
        def extract(self, downloaded, *, root=None):
            self.calls.append("extract")
            return {"version": downloaded["version"], "channel": downloaded["channel"]}

    service = UpdateStageService(
        update_service=_UpdateSvc(_release(), calls=calls),
        artifact_service=_ArtifactSvc(calls),
        extract_service=_BrokenExtractSvc(calls),
        exe_trust_service=_ExeSvc(calls),
        promote_service=_PromoteSvc(calls),
    )

    monkeypatch.setattr("core.services.update_stage.update_cache.ensure_cache_dirs", lambda root=None: root or tmp_path)
    monkeypatch.setattr(
        "core.services.update_stage.update_cache.read_state",
        lambda *_args, **_kwargs: {
            "hash_verified": {},
            "extracted": None,
            "exe_verified": None,
            "verified_ready": None,
        },
    )

    result = service.stage(manifest_url="https://example.test/manifest.json", channel="stable", root=tmp_path)

    assert result.ok is False
    assert result.error_code == "missing_extracted_metadata"
    assert "verify" not in calls
    assert "promote" not in calls


def test_update_stage_rejects_unsigned_manifest_by_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    calls: list[str] = []
    service = _stage_service_for_manifest(_manifest_payload(), calls=calls)

    _patch_empty_update_cache(tmp_path, monkeypatch)
    result = service.stage(manifest_url="https://example.test/manifest.json", channel="stable", root=tmp_path)

    assert result.ok is False
    assert result.error_code == "missing_signature"
    assert calls == []


def test_update_stage_accepts_trusted_signed_manifest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    calls: list[str] = []
    manifest, trusted_keys = _signed_embedded_manifest(_manifest_payload())
    service = _stage_service_for_manifest(manifest, trusted_keys=trusted_keys, calls=calls)

    _patch_empty_update_cache(tmp_path, monkeypatch)
    result = service.stage(manifest_url="https://example.test/manifest.json", channel="stable", root=tmp_path)

    assert result.ok is True
    assert result.status == "verified_ready"
    assert result.error_code is None
    assert calls == ["download", "extract", "verify", "promote"]


def test_update_stage_rejects_bad_manifest_signature(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    calls: list[str] = []
    manifest, trusted_keys = _signed_embedded_manifest(_manifest_payload())
    manifest["latest"]["download"]["url"] = "https://example.test/tampered.zip"
    service = _stage_service_for_manifest(manifest, trusted_keys=trusted_keys, calls=calls)

    _patch_empty_update_cache(tmp_path, monkeypatch)
    result = service.stage(manifest_url="https://example.test/manifest.json", channel="stable", root=tmp_path)

    assert result.ok is False
    assert result.error_code == "bad_signature"
    assert calls == []


def test_update_stage_rejects_unknown_manifest_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    calls: list[str] = []
    manifest, _trusted_keys = _signed_embedded_manifest(_manifest_payload(), key_id="unknown-key")
    service = _stage_service_for_manifest(manifest, trusted_keys={}, calls=calls)

    _patch_empty_update_cache(tmp_path, monkeypatch)
    result = service.stage(manifest_url="https://example.test/manifest.json", channel="stable", root=tmp_path)

    assert result.ok is False
    assert result.error_code == "unknown_key_id"
    assert calls == []


def test_update_check_behavior_unchanged():
    service = UpdateService(fetch_manifest=lambda _url, _timeout: _manifest_payload())

    result = service.check(manifest_url="https://example.test/manifest.json", channel="stable")

    assert result.error_code is None
    assert result.update_available is True
    assert result.download_url == "https://example.test/BUS-Core.zip"


def test_update_stage_unsigned_manifest_compatibility_requires_explicit_opt_out(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    calls: list[str] = []
    service = _stage_service_for_manifest(
        _manifest_payload(),
        require_signed_manifest=False,
        calls=calls,
    )

    _patch_empty_update_cache(tmp_path, monkeypatch)
    result = service.stage(manifest_url="https://example.test/manifest.json", channel="stable", root=tmp_path)

    assert result.ok is True
    assert calls == ["download", "extract", "verify", "promote"]
