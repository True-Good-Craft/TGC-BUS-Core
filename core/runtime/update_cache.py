# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Mapping

from core.appdata.paths import update_cache_root
from core.config.update_policy import validate_update_channel
from core.version import VERSION as CURRENT_VERSION

STATE_SCHEMA = 1
STATE_FILE_NAME = "state.json"
MANIFESTS_DIR_NAME = "manifests"
DOWNLOADS_DIR_NAME = "downloads"
VERSIONS_DIR_NAME = "versions"
SEMVER_PATTERN = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


class UpdateCacheStateError(ValueError):
    """Raised when update cache state fails closed validation."""


def cache_root() -> Path:
    return update_cache_root()


def manifests_dir(root: Path | None = None) -> Path:
    return (root or cache_root()) / MANIFESTS_DIR_NAME


def downloads_dir(root: Path | None = None) -> Path:
    return (root or cache_root()) / DOWNLOADS_DIR_NAME


def versions_dir(root: Path | None = None) -> Path:
    return (root or cache_root()) / VERSIONS_DIR_NAME


def state_path(root: Path | None = None) -> Path:
    return (root or cache_root()) / STATE_FILE_NAME


def ensure_cache_dirs(root: Path | None = None) -> Path:
    resolved_root = root or cache_root()
    for path in (
        resolved_root,
        manifests_dir(resolved_root),
        downloads_dir(resolved_root),
        versions_dir(resolved_root),
    ):
        path.mkdir(parents=True, exist_ok=True)
    return resolved_root


def default_state(active_version: str = CURRENT_VERSION) -> dict[str, Any]:
    return {
        "schema": STATE_SCHEMA,
        "active_version": active_version,
        "hash_verified": None,
        "extracted": None,
        "exe_verified": None,
        "verified_ready": None,
        "verified_ready_versions": {},
        "handoff": {
            "last_attempted_version": None,
            "attempt_count": 0,
            "last_result": None,
        },
    }


def read_state(root: Path | None = None, *, active_version: str = CURRENT_VERSION) -> dict[str, Any]:
    path = state_path(root)
    if not path.exists():
        return default_state(active_version)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return validate_state(payload, root=root, active_version=active_version)
    except Exception:
        return default_state(active_version)


def write_state(state: dict[str, Any], root: Path | None = None, *, active_version: str = CURRENT_VERSION) -> dict[str, Any]:
    resolved_root = ensure_cache_dirs(root)
    validated = validate_state(state, root=resolved_root, active_version=active_version)
    path = state_path(resolved_root)
    tmp = path.with_name(f"{path.name}.tmp.{os.getpid()}")
    tmp.write_text(json.dumps(validated, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)
    return validated


def validate_state(state: Any, root: Path | None = None, *, active_version: str = CURRENT_VERSION) -> dict[str, Any]:
    if not isinstance(state, dict):
        raise UpdateCacheStateError("update cache state must be an object")

    schema = state.get("schema")
    if schema != STATE_SCHEMA:
        raise UpdateCacheStateError("unsupported update cache state schema")

    stored_active = state.get("active_version")
    if not isinstance(stored_active, str) or not _is_semver(stored_active):
        raise UpdateCacheStateError("active_version must be strict SemVer")

    effective_active = active_version if _is_semver(active_version) else stored_active
    hash_verified = _validate_hash_verified(state.get("hash_verified"), root or cache_root(), effective_active)
    extracted = _validate_extracted(state.get("extracted"), root or cache_root(), effective_active)
    exe_verified = _validate_exe_verified(state.get("exe_verified"), root or cache_root(), effective_active)
    verified_ready = _validate_verified_ready(state.get("verified_ready"), root or cache_root(), effective_active)
    verified_ready_versions = _validate_verified_ready_versions(
        state.get("verified_ready_versions"),
        root or cache_root(),
        effective_active,
    )
    if verified_ready is not None:
        verified_ready_versions = _with_verified_ready_record(verified_ready_versions, verified_ready)
    handoff = _validate_handoff(state.get("handoff"))

    return {
        "schema": STATE_SCHEMA,
        "active_version": stored_active,
        "hash_verified": hash_verified,
        "extracted": extracted,
        "exe_verified": exe_verified,
        "verified_ready": verified_ready,
        "verified_ready_versions": verified_ready_versions,
        "handoff": handoff,
    }


def iter_verified_ready_records(state: Mapping[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    by_version = state.get("verified_ready_versions") if isinstance(state, Mapping) else None
    if isinstance(by_version, Mapping):
        for sha_map in by_version.values():
            if not isinstance(sha_map, Mapping):
                continue
            for record in sha_map.values():
                if not isinstance(record, dict):
                    continue
                key = _verified_ready_key(record)
                if key is None or key in seen:
                    continue
                records.append(record)
                seen.add(key)

    legacy = state.get("verified_ready") if isinstance(state, Mapping) else None
    if isinstance(legacy, dict):
        key = _verified_ready_key(legacy)
        if key is not None and key not in seen:
            records.append(legacy)

    return records


def find_verified_ready(state: Mapping[str, Any], *, version: str, sha256: str) -> dict[str, Any] | None:
    normalized_sha = sha256.lower()
    by_version = state.get("verified_ready_versions") if isinstance(state, Mapping) else None
    if isinstance(by_version, Mapping):
        sha_map = by_version.get(version)
        if isinstance(sha_map, Mapping):
            record = sha_map.get(normalized_sha)
            if isinstance(record, dict):
                return record

    legacy = state.get("verified_ready") if isinstance(state, Mapping) else None
    if isinstance(legacy, dict) and legacy.get("version") == version and str(legacy.get("sha256", "")).lower() == normalized_sha:
        return legacy
    return None


def _validate_hash_verified(value: Any, root: Path, active_version: str) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise UpdateCacheStateError("hash_verified must be null or an object")

    version = value.get("version")
    if not isinstance(version, str) or not _is_semver(version):
        raise UpdateCacheStateError("hash_verified.version must be strict SemVer")

    channel = validate_update_channel(value.get("channel"))

    artifact_path = value.get("artifact_path")
    if not isinstance(artifact_path, str) or not artifact_path.strip():
        raise UpdateCacheStateError("hash_verified.artifact_path must be a non-empty string")
    normalized_artifact = _normalize_confined_path(Path(artifact_path), downloads_dir(root))

    sha256 = value.get("sha256")
    if not isinstance(sha256, str) or not re.fullmatch(r"[A-Fa-f0-9]{64}", sha256):
        raise UpdateCacheStateError("hash_verified.sha256 must be 64 hex characters")

    size_bytes = value.get("size_bytes")
    if type(size_bytes) is not int or size_bytes <= 0:
        raise UpdateCacheStateError("hash_verified.size_bytes must be a positive integer")

    downloaded = value.get("downloaded")
    if downloaded is not True:
        raise UpdateCacheStateError("hash_verified.downloaded must be true")

    hash_verified = value.get("hash_verified")
    if hash_verified is not True:
        raise UpdateCacheStateError("hash_verified.hash_verified must be true")

    downloaded_at = value.get("downloaded_at")
    if not isinstance(downloaded_at, str) or not downloaded_at.strip():
        raise UpdateCacheStateError("hash_verified.downloaded_at must be a non-empty string")

    verified_at = value.get("verified_at")
    if not isinstance(verified_at, str) or not verified_at.strip():
        raise UpdateCacheStateError("hash_verified.verified_at must be a non-empty string")

    return {
        "version": version,
        "channel": channel,
        "artifact_path": str(normalized_artifact),
        "sha256": sha256.lower(),
        "size_bytes": size_bytes,
        "downloaded": True,
        "hash_verified": True,
        "downloaded_at": downloaded_at,
        "verified_at": verified_at,
    }


def _validate_verified_ready(value: Any, root: Path, active_version: str) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise UpdateCacheStateError("verified_ready must be null or an object")

    version = value.get("version")
    if not isinstance(version, str) or not _is_semver(version):
        raise UpdateCacheStateError("verified_ready.version must be strict SemVer")
    channel = validate_update_channel(value.get("channel"))

    artifact_path = value.get("artifact_path")
    if not isinstance(artifact_path, str) or not artifact_path.strip():
        raise UpdateCacheStateError("verified_ready.artifact_path must be a non-empty string")
    normalized_artifact = _normalize_confined_path(Path(artifact_path), downloads_dir(root))

    extracted_dir = value.get("extracted_dir")
    if not isinstance(extracted_dir, str) or not extracted_dir.strip():
        raise UpdateCacheStateError("verified_ready.extracted_dir must be a non-empty string")
    normalized_dir = _normalize_version_dir(Path(extracted_dir), versions_dir(root), version)

    if value.get("verified") is not True:
        raise UpdateCacheStateError("verified_ready.verified must be true")

    verified_at = value.get("verified_at")
    if not isinstance(verified_at, str) or not verified_at.strip():
        raise UpdateCacheStateError("verified_ready.verified_at must be a non-empty string")

    ready_at = value.get("ready_at")
    if not isinstance(ready_at, str) or not ready_at.strip():
        raise UpdateCacheStateError("verified_ready.ready_at must be a non-empty string")

    exe_path = value.get("exe_path")
    if not isinstance(exe_path, str) or not exe_path.strip():
        raise UpdateCacheStateError("verified_ready.exe_path must be a non-empty string")

    normalized_exe = _normalize_exe_path(Path(exe_path), normalized_dir)

    sha256 = value.get("sha256")
    if not isinstance(sha256, str) or not re.fullmatch(r"[A-Fa-f0-9]{64}", sha256):
        raise UpdateCacheStateError("verified_ready.sha256 must be 64 hex characters")

    size_bytes = value.get("size_bytes")
    if size_bytes is not None and (type(size_bytes) is not int or size_bytes <= 0):
        raise UpdateCacheStateError("verified_ready.size_bytes must be null or a positive integer")

    publisher = value.get("publisher")
    if not isinstance(publisher, str) or not publisher.strip():
        raise UpdateCacheStateError("verified_ready.publisher must be a non-empty string")

    signer_subject = value.get("signer_subject")
    if not isinstance(signer_subject, str) or not signer_subject.strip():
        raise UpdateCacheStateError("verified_ready.signer_subject must be a non-empty string")

    signer_thumbprint = value.get("signer_thumbprint")
    if signer_thumbprint is not None:
        if not isinstance(signer_thumbprint, str) or not re.fullmatch(r"[A-Fa-f0-9]{40}", signer_thumbprint):
            raise UpdateCacheStateError("verified_ready.signer_thumbprint must be null or 40 hex characters")
        signer_thumbprint = signer_thumbprint.lower()

    return {
        "version": version,
        "channel": channel,
        "artifact_path": str(normalized_artifact),
        "extracted_dir": str(normalized_dir),
        "exe_path": str(normalized_exe),
        "sha256": sha256.lower(),
        "size_bytes": size_bytes,
        "publisher": publisher.strip(),
        "signer_subject": signer_subject.strip(),
        "signer_thumbprint": signer_thumbprint,
        "verified": True,
        "verified_at": verified_at,
        "ready_at": ready_at,
    }


def _validate_verified_ready_versions(value: Any, root: Path, active_version: str) -> dict[str, dict[str, dict[str, Any]]]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise UpdateCacheStateError("verified_ready_versions must be an object")

    records: dict[str, dict[str, dict[str, Any]]] = {}
    for version, sha_map in value.items():
        if not isinstance(version, str) or not _is_semver(version):
            raise UpdateCacheStateError("verified_ready_versions keys must be strict SemVer")
        if not isinstance(sha_map, dict):
            raise UpdateCacheStateError("verified_ready_versions version entries must be objects")
        for sha256, record in sha_map.items():
            if not isinstance(sha256, str) or not re.fullmatch(r"[A-Fa-f0-9]{64}", sha256):
                raise UpdateCacheStateError("verified_ready_versions sha256 keys must be 64 hex characters")
            validated = _validate_verified_ready(record, root, active_version)
            if validated is None:
                raise UpdateCacheStateError("verified_ready_versions records must be objects")
            if validated["version"] != version or validated["sha256"] != sha256.lower():
                raise UpdateCacheStateError("verified_ready_versions keys must match record version and sha256")
            records.setdefault(version, {})[sha256.lower()] = validated
    return records


def _with_verified_ready_record(
    records: dict[str, dict[str, dict[str, Any]]],
    record: dict[str, Any],
) -> dict[str, dict[str, dict[str, Any]]]:
    key = _verified_ready_key(record)
    if key is None:
        return records
    version, sha256 = key
    merged = {record_version: dict(sha_map) for record_version, sha_map in records.items()}
    merged.setdefault(version, {})[sha256] = record
    return merged


def _verified_ready_key(record: Mapping[str, Any]) -> tuple[str, str] | None:
    version = record.get("version")
    sha256 = record.get("sha256")
    if not isinstance(version, str) or not isinstance(sha256, str):
        return None
    if not _is_semver(version) or not re.fullmatch(r"[A-Fa-f0-9]{64}", sha256):
        return None
    return version, sha256.lower()


def _validate_exe_verified(value: Any, root: Path, active_version: str) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise UpdateCacheStateError("exe_verified must be null or an object")

    version = value.get("version")
    if not isinstance(version, str) or not _is_semver(version):
        raise UpdateCacheStateError("exe_verified.version must be strict SemVer")

    channel = validate_update_channel(value.get("channel"))

    extracted_dir = value.get("extracted_dir")
    if not isinstance(extracted_dir, str) or not extracted_dir.strip():
        raise UpdateCacheStateError("exe_verified.extracted_dir must be a non-empty string")
    normalized_dir = _normalize_version_dir(Path(extracted_dir), versions_dir(root), version)

    exe_path = value.get("exe_path")
    if not isinstance(exe_path, str) or not exe_path.strip():
        raise UpdateCacheStateError("exe_verified.exe_path must be a non-empty string")
    normalized_exe = _normalize_exe_path(Path(exe_path), normalized_dir)

    sha256 = value.get("sha256")
    if not isinstance(sha256, str) or not re.fullmatch(r"[A-Fa-f0-9]{64}", sha256):
        raise UpdateCacheStateError("exe_verified.sha256 must be 64 hex characters")

    size_bytes = value.get("size_bytes")
    if size_bytes is not None and (type(size_bytes) is not int or size_bytes <= 0):
        raise UpdateCacheStateError("exe_verified.size_bytes must be null or a positive integer")

    publisher = value.get("publisher")
    if not isinstance(publisher, str) or not publisher.strip():
        raise UpdateCacheStateError("exe_verified.publisher must be a non-empty string")

    signer_subject = value.get("signer_subject")
    if not isinstance(signer_subject, str) or not signer_subject.strip():
        raise UpdateCacheStateError("exe_verified.signer_subject must be a non-empty string")

    signer_thumbprint = value.get("signer_thumbprint")
    if signer_thumbprint is not None:
        if not isinstance(signer_thumbprint, str) or not re.fullmatch(r"[A-Fa-f0-9]{40}", signer_thumbprint):
            raise UpdateCacheStateError("exe_verified.signer_thumbprint must be null or 40 hex characters")
        signer_thumbprint = signer_thumbprint.lower()

    if value.get("verified") is not True:
        raise UpdateCacheStateError("exe_verified.verified must be true")

    verified_at = value.get("verified_at")
    if not isinstance(verified_at, str) or not verified_at.strip():
        raise UpdateCacheStateError("exe_verified.verified_at must be a non-empty string")

    return {
        "version": version,
        "channel": channel,
        "extracted_dir": str(normalized_dir),
        "exe_path": str(normalized_exe),
        "sha256": sha256.lower(),
        "size_bytes": size_bytes,
        "publisher": publisher.strip(),
        "signer_subject": signer_subject.strip(),
        "signer_thumbprint": signer_thumbprint,
        "verified": True,
        "verified_at": verified_at,
    }


def _validate_extracted(value: Any, root: Path, active_version: str) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise UpdateCacheStateError("extracted must be null or an object")

    version = value.get("version")
    if not isinstance(version, str) or not _is_semver(version):
        raise UpdateCacheStateError("extracted.version must be strict SemVer")

    channel = validate_update_channel(value.get("channel"))

    artifact_path = value.get("artifact_path")
    if not isinstance(artifact_path, str) or not artifact_path.strip():
        raise UpdateCacheStateError("extracted.artifact_path must be a non-empty string")
    normalized_artifact = _normalize_confined_path(Path(artifact_path), downloads_dir(root))

    extracted_dir = value.get("extracted_dir")
    if not isinstance(extracted_dir, str) or not extracted_dir.strip():
        raise UpdateCacheStateError("extracted.extracted_dir must be a non-empty string")
    normalized_dir = _normalize_version_dir(Path(extracted_dir), versions_dir(root), version)

    exe_path = value.get("exe_path")
    if not isinstance(exe_path, str) or not exe_path.strip():
        raise UpdateCacheStateError("extracted.exe_path must be a non-empty string")
    normalized_exe = _normalize_exe_path(Path(exe_path), normalized_dir)

    sha256 = value.get("sha256")
    if not isinstance(sha256, str) or not re.fullmatch(r"[A-Fa-f0-9]{64}", sha256):
        raise UpdateCacheStateError("extracted.sha256 must be 64 hex characters")

    size_bytes = value.get("size_bytes")
    if size_bytes is not None and (type(size_bytes) is not int or size_bytes <= 0):
        raise UpdateCacheStateError("extracted.size_bytes must be null or a positive integer")

    extracted_at = value.get("extracted_at")
    if not isinstance(extracted_at, str) or not extracted_at.strip():
        raise UpdateCacheStateError("extracted.extracted_at must be a non-empty string")

    return {
        "version": version,
        "channel": channel,
        "artifact_path": str(normalized_artifact),
        "extracted_dir": str(normalized_dir),
        "exe_path": str(normalized_exe),
        "sha256": sha256.lower(),
        "size_bytes": size_bytes,
        "extracted_at": extracted_at,
    }


def _validate_handoff(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise UpdateCacheStateError("handoff must be an object")

    last_attempted_version = value.get("last_attempted_version")
    if last_attempted_version is not None and (
        not isinstance(last_attempted_version, str) or not _is_semver(last_attempted_version)
    ):
        raise UpdateCacheStateError("handoff.last_attempted_version must be null or strict SemVer")

    attempt_count = value.get("attempt_count")
    if type(attempt_count) is not int or attempt_count < 0:
        raise UpdateCacheStateError("handoff.attempt_count must be a non-negative integer")

    last_result = value.get("last_result")
    if last_result is not None and (not isinstance(last_result, str) or not last_result.strip()):
        raise UpdateCacheStateError("handoff.last_result must be null or a non-empty string")

    return {
        "last_attempted_version": last_attempted_version,
        "attempt_count": attempt_count,
        "last_result": last_result,
    }


def _normalize_confined_path(path: Path, allowed_root: Path) -> Path:
    if not path.is_absolute():
        raise UpdateCacheStateError("update cache paths must be absolute")

    resolved_path = path.resolve(strict=False)
    resolved_root = allowed_root.resolve(strict=False)
    try:
        resolved_path.relative_to(resolved_root)
    except ValueError as exc:
        raise UpdateCacheStateError("update cache path escapes allowed directory") from exc
    return resolved_path


def _normalize_version_dir(path: Path, versions_root: Path, version: str) -> Path:
    normalized_dir = _normalize_confined_path(path, versions_root)
    expected_dir = (versions_root / version).resolve(strict=False)
    if normalized_dir != expected_dir:
        raise UpdateCacheStateError("update cache version directory must match versions/<version>")
    return normalized_dir


def _normalize_exe_path(path: Path, allowed_root: Path) -> Path:
    normalized_path = _normalize_confined_path(path, allowed_root)
    if normalized_path.suffix.lower() != ".exe":
        raise UpdateCacheStateError("update cache executable path must end with .exe")
    return normalized_path


def _is_semver(raw: str) -> bool:
    return bool(SEMVER_PATTERN.fullmatch(raw))


def _parse_semver(raw: str) -> tuple[int, int, int]:
    match = SEMVER_PATTERN.fullmatch(raw)
    if not match:
        raise UpdateCacheStateError("version must be strict SemVer")
    return int(match.group(1)), int(match.group(2)), int(match.group(3))
