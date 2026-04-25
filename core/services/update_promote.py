# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from core.runtime import update_cache
from core.version import VERSION as CURRENT_VERSION


class UpdatePromotionError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class VerifiedReadyArtifact:
    version: str
    channel: str
    artifact_path: str
    extracted_dir: str
    exe_path: str
    sha256: str
    size_bytes: int | None
    publisher: str
    signer_subject: str
    signer_thumbprint: str | None
    verified_at: str
    ready_at: str


class UpdateReadyPromotionService:
    def promote(self, state: Mapping[str, Any], *, root: Path | None = None) -> VerifiedReadyArtifact:
        if not isinstance(state, Mapping):
            raise UpdatePromotionError("invalid_state", "Update promotion requires cache state.")

        target_root = update_cache.ensure_cache_dirs(root)
        hash_verified = _require_record(state.get("hash_verified"), "hash_verified")
        extracted = _require_record(state.get("extracted"), "extracted")
        exe_verified = _require_record(state.get("exe_verified"), "exe_verified")

        version = _require_matching_text(hash_verified, extracted, exe_verified, key="version", code="mismatched_version")
        channel = _require_matching_text(hash_verified, extracted, exe_verified, key="channel", code="mismatched_channel")
        sha256 = _require_matching_text(hash_verified, extracted, exe_verified, key="sha256", code="mismatched_sha256")
        artifact_path = _require_matching_text(hash_verified, extracted, key="artifact_path", code="mismatched_artifact_path")
        extracted_dir = _require_matching_text(extracted, exe_verified, key="extracted_dir", code="mismatched_extracted_dir")
        exe_path = _require_matching_text(extracted, exe_verified, key="exe_path", code="mismatched_exe_path")

        hash_size = _optional_positive_int(hash_verified.get("size_bytes"), code="invalid_hash_verified")
        extracted_size = _optional_positive_int(extracted.get("size_bytes"), code="invalid_extracted")
        exe_size = _optional_positive_int(exe_verified.get("size_bytes"), code="invalid_exe_verified")
        size_bytes = _require_matching_optional_int(hash_size, extracted_size, exe_size, code="mismatched_size_bytes")

        if hash_verified.get("downloaded") is not True or hash_verified.get("hash_verified") is not True:
            raise UpdatePromotionError("missing_hash_verified", "Hash-verified update state is incomplete.")
        if exe_verified.get("verified") is not True:
            raise UpdatePromotionError("missing_exe_verified", "Executable verification state is incomplete.")

        downloads_root = update_cache.downloads_dir(target_root)
        versions_root = update_cache.versions_dir(target_root)
        normalized_artifact = _ensure_existing_file_within_root(Path(artifact_path), downloads_root, code="invalid_artifact_path")
        normalized_dir = _ensure_existing_version_dir(Path(extracted_dir), versions_root, version)
        normalized_exe = _ensure_existing_file_within_root(Path(exe_path), normalized_dir, code="invalid_exe_path")

        publisher = _require_non_empty_text(exe_verified.get("publisher"), code="invalid_exe_verified")
        signer_subject = _require_non_empty_text(exe_verified.get("signer_subject"), code="invalid_exe_verified")
        signer_thumbprint = exe_verified.get("signer_thumbprint")
        if signer_thumbprint is not None:
            signer_thumbprint = _require_non_empty_text(signer_thumbprint, code="invalid_exe_verified").lower()

        verified_at = _require_non_empty_text(exe_verified.get("verified_at"), code="invalid_exe_verified")
        ready_at = verified_at

        mutable_state = dict(state)
        mutable_state["verified_ready"] = {
            "version": version,
            "channel": channel,
            "artifact_path": str(normalized_artifact),
            "extracted_dir": str(normalized_dir),
            "exe_path": str(normalized_exe),
            "sha256": sha256,
            "size_bytes": size_bytes,
            "publisher": publisher,
            "signer_subject": signer_subject,
            "signer_thumbprint": signer_thumbprint,
            "verified": True,
            "verified_at": verified_at,
            "ready_at": ready_at,
        }
        update_cache.write_state(mutable_state, target_root, active_version=CURRENT_VERSION)
        return VerifiedReadyArtifact(
            version=version,
            channel=channel,
            artifact_path=str(normalized_artifact),
            extracted_dir=str(normalized_dir),
            exe_path=str(normalized_exe),
            sha256=sha256,
            size_bytes=size_bytes,
            publisher=publisher,
            signer_subject=signer_subject,
            signer_thumbprint=signer_thumbprint,
            verified_at=verified_at,
            ready_at=ready_at,
        )


def _require_record(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise UpdatePromotionError(f"missing_{name}", f"{name} state is required for verified_ready promotion.")
    return value


def _require_matching_text(*records: Mapping[str, Any], key: str, code: str) -> str:
    values = [_require_non_empty_text(record.get(key), code=code) for record in records]
    normalized = [value.lower() if key == "sha256" else value for value in values]
    if any(value != normalized[0] for value in normalized[1:]):
        raise UpdatePromotionError(code, f"{key} must match across update stages.")
    return normalized[0] if key == "sha256" else values[0]


def _require_matching_optional_int(*values: int | None, code: str) -> int | None:
    present = [value for value in values if value is not None]
    if not present:
        return None
    if any(value != present[0] for value in present[1:]):
        raise UpdatePromotionError(code, "size_bytes must match across update stages.")
    return present[0]


def _optional_positive_int(value: Any, *, code: str) -> int | None:
    if value is None:
        return None
    if type(value) is not int or value <= 0:
        raise UpdatePromotionError(code, "size_bytes must be null or a positive integer.")
    return value


def _require_non_empty_text(value: Any, *, code: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise UpdatePromotionError(code, "Required state field is missing.")
    return value.strip()


def _ensure_existing_file_within_root(path: Path, allowed_root: Path, *, code: str) -> Path:
    try:
        normalized = update_cache._normalize_confined_path(path, allowed_root)
    except update_cache.UpdateCacheStateError as exc:
        raise UpdatePromotionError(code, str(exc)) from exc
    if not normalized.exists() or not normalized.is_file():
        raise UpdatePromotionError(code, "Required update artifact file is missing.")
    return normalized


def _ensure_existing_version_dir(path: Path, versions_root: Path, version: str) -> Path:
    try:
        normalized = update_cache._normalize_version_dir(path, versions_root, version)
    except update_cache.UpdateCacheStateError as exc:
        raise UpdatePromotionError("invalid_extracted_dir", str(exc)) from exc
    if not normalized.exists() or not normalized.is_dir():
        raise UpdatePromotionError("invalid_extracted_dir", "Required extracted version directory is missing.")
    return normalized