# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

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
        "verified_ready": None,
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
    verified_ready = _validate_verified_ready(state.get("verified_ready"), root or cache_root(), effective_active)
    handoff = _validate_handoff(state.get("handoff"))

    return {
        "schema": STATE_SCHEMA,
        "active_version": stored_active,
        "hash_verified": hash_verified,
        "verified_ready": verified_ready,
        "handoff": handoff,
    }


def _validate_hash_verified(value: Any, root: Path, active_version: str) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise UpdateCacheStateError("hash_verified must be null or an object")

    version = value.get("version")
    if not isinstance(version, str) or not _is_semver(version):
        raise UpdateCacheStateError("hash_verified.version must be strict SemVer")
    if _is_semver(active_version) and _parse_semver(version) <= _parse_semver(active_version):
        raise UpdateCacheStateError("hash_verified.version must be newer than active_version")

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
    if _is_semver(active_version) and _parse_semver(version) <= _parse_semver(active_version):
        raise UpdateCacheStateError("verified_ready.version must be newer than active_version")

    channel = validate_update_channel(value.get("channel"))

    if value.get("verified") is not True:
        raise UpdateCacheStateError("verified_ready.verified must be true")

    verified_at = value.get("verified_at")
    if not isinstance(verified_at, str) or not verified_at.strip():
        raise UpdateCacheStateError("verified_ready.verified_at must be a non-empty string")

    exe_path = value.get("exe_path")
    if not isinstance(exe_path, str) or not exe_path.strip():
        raise UpdateCacheStateError("verified_ready.exe_path must be a non-empty string")

    normalized_exe = _normalize_confined_path(Path(exe_path), versions_dir(root))
    return {
        "version": version,
        "channel": channel,
        "exe_path": str(normalized_exe),
        "verified": True,
        "verified_at": verified_at,
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
        raise UpdateCacheStateError("update cache path escapes versions directory") from exc
    return resolved_path


def _is_semver(raw: str) -> bool:
    return bool(SEMVER_PATTERN.fullmatch(raw))


def _parse_semver(raw: str) -> tuple[int, int, int]:
    match = SEMVER_PATTERN.fullmatch(raw)
    if not match:
        raise UpdateCacheStateError("version must be strict SemVer")
    return int(match.group(1)), int(match.group(2)), int(match.group(3))
