# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import hashlib
import os
import re
import shutil
import stat
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from core.config.update_policy import validate_update_channel
from core.runtime import update_cache
from core.services.update_artifact import DownloadedArtifact
from core.version import VERSION as CURRENT_VERSION

MAX_ZIP_ENTRY_COUNT = 256
MAX_UNCOMPRESSED_BYTES = 512 * 1024 * 1024
WINDOWS_ABSOLUTE_PATH_PATTERN = re.compile(r"^[A-Za-z]:[/\\]")


class ArtifactExtractError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class HashVerifiedArtifact:
    version: str
    channel: str
    artifact_path: str
    sha256: str
    size_bytes: int | None


@dataclass(frozen=True)
class ExtractedArtifact:
    version: str
    channel: str
    artifact_path: str
    extracted_dir: str
    exe_path: str
    sha256: str
    size_bytes: int | None
    extracted_at: str


class UpdateArtifactExtractService:
    def extract(
        self,
        artifact: Mapping[str, Any] | DownloadedArtifact,
        *,
        root: Path | None = None,
    ) -> ExtractedArtifact:
        validated = _coerce_hash_verified_artifact(artifact)
        target_root = update_cache.ensure_cache_dirs(root)
        downloads_root = update_cache.downloads_dir(target_root)
        versions_root = update_cache.versions_dir(target_root)

        artifact_path = Path(validated.artifact_path)
        _ensure_file_within_root(artifact_path, downloads_root)
        _verify_artifact_integrity(artifact_path, validated.sha256, validated.size_bytes)

        final_dir = (versions_root / validated.version).resolve(strict=False)
        _ensure_path_within_root(final_dir, versions_root, code="invalid_destination", message="Version extraction path escapes update cache versions directory.")
        if final_dir.exists():
            raise ArtifactExtractError("destination_exists", "Version extraction directory already exists.")

        temp_dir = (versions_root / f".extracting-{validated.version}-{os.getpid()}").resolve(strict=False)
        _ensure_path_within_root(temp_dir, versions_root, code="invalid_destination", message="Temporary extraction path escapes update cache versions directory.")
        _cleanup_dir(temp_dir)
        temp_dir.mkdir(parents=True, exist_ok=False)

        moved_to_final = False
        try:
            with zipfile.ZipFile(artifact_path) as archive:
                _extract_archive_safely(archive, temp_dir)

            extracted_exe = _select_exe_candidate(temp_dir, validated.version)
            temp_dir.replace(final_dir)
            moved_to_final = True

            final_exe = final_dir / extracted_exe.relative_to(temp_dir)
            timestamp = _utc_now_iso()
            state = update_cache.read_state(target_root, active_version=CURRENT_VERSION)
            state["extracted"] = {
                "version": validated.version,
                "channel": validated.channel,
                "artifact_path": str(artifact_path.resolve(strict=False)),
                "extracted_dir": str(final_dir),
                "exe_path": str(final_exe.resolve(strict=False)),
                "sha256": validated.sha256,
                "size_bytes": validated.size_bytes,
                "extracted_at": timestamp,
            }
            update_cache.write_state(state, target_root, active_version=CURRENT_VERSION)
            return ExtractedArtifact(
                version=validated.version,
                channel=validated.channel,
                artifact_path=str(artifact_path.resolve(strict=False)),
                extracted_dir=str(final_dir),
                exe_path=str(final_exe.resolve(strict=False)),
                sha256=validated.sha256,
                size_bytes=validated.size_bytes,
                extracted_at=timestamp,
            )
        except ArtifactExtractError:
            if moved_to_final:
                _cleanup_dir(final_dir)
            else:
                _cleanup_dir(temp_dir)
            raise
        except zipfile.BadZipFile as exc:
            if moved_to_final:
                _cleanup_dir(final_dir)
            else:
                _cleanup_dir(temp_dir)
            raise ArtifactExtractError("invalid_zip", "Artifact ZIP is malformed or unreadable.") from exc
        except Exception as exc:
            if moved_to_final:
                _cleanup_dir(final_dir)
            else:
                _cleanup_dir(temp_dir)
            raise ArtifactExtractError("artifact_extract_failed", "Artifact extraction failed.") from exc


def _coerce_hash_verified_artifact(artifact: Mapping[str, Any] | DownloadedArtifact) -> HashVerifiedArtifact:
    if isinstance(artifact, DownloadedArtifact):
        return HashVerifiedArtifact(
            version=artifact.version,
            channel=validate_update_channel(artifact.channel),
            artifact_path=str(Path(artifact.artifact_path)),
            sha256=_validate_sha256(artifact.sha256),
            size_bytes=_validate_size_bytes(artifact.size_bytes),
        )

    if not isinstance(artifact, Mapping):
        raise ArtifactExtractError("invalid_artifact_state", "Artifact extraction requires hash-verified update metadata.")

    if artifact.get("downloaded") is not True:
        raise ArtifactExtractError("invalid_artifact_state", "Artifact must already be marked downloaded.")
    if artifact.get("hash_verified") is not True:
        raise ArtifactExtractError("invalid_artifact_state", "Artifact must already be hash verified.")

    version = artifact.get("version")
    if not isinstance(version, str) or not update_cache.SEMVER_PATTERN.fullmatch(version):
        raise ArtifactExtractError("invalid_artifact_state", "Artifact version must be strict SemVer.")

    artifact_path = artifact.get("artifact_path")
    if not isinstance(artifact_path, str) or not artifact_path.strip():
        raise ArtifactExtractError("invalid_artifact_state", "Artifact path must be a non-empty string.")

    return HashVerifiedArtifact(
        version=version,
        channel=validate_update_channel(artifact.get("channel")),
        artifact_path=artifact_path,
        sha256=_validate_sha256(artifact.get("sha256")),
        size_bytes=_validate_size_bytes(artifact.get("size_bytes")),
    )


def _validate_sha256(value: Any) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Fa-f0-9]{64}", value):
        raise ArtifactExtractError("invalid_artifact_state", "Artifact sha256 must be 64 hex characters.")
    return value.lower()


def _validate_size_bytes(value: Any) -> int | None:
    if value is None:
        return None
    if type(value) is not int or value <= 0:
        raise ArtifactExtractError("invalid_artifact_state", "Artifact size_bytes must be a positive integer when provided.")
    return value


def _verify_artifact_integrity(path: Path, expected_sha256: str, expected_size: int | None) -> None:
    actual_path = path.resolve(strict=False)
    if not actual_path.exists() or not actual_path.is_file():
        raise ArtifactExtractError("missing_artifact", "Artifact ZIP does not exist.")

    actual_size = actual_path.stat().st_size
    if expected_size is not None and actual_size != expected_size:
        raise ArtifactExtractError("artifact_size_mismatch", "Artifact ZIP size does not match hash-verified metadata.")

    hasher = hashlib.sha256()
    with actual_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65_536), b""):
            hasher.update(chunk)
    if hasher.hexdigest().lower() != expected_sha256:
        raise ArtifactExtractError("artifact_hash_mismatch", "Artifact ZIP hash does not match hash-verified metadata.")


def _extract_archive_safely(archive: zipfile.ZipFile, temp_dir: Path) -> None:
    infos = archive.infolist()
    if not infos:
        raise ArtifactExtractError("empty_zip", "Artifact ZIP is empty.")
    if len(infos) > MAX_ZIP_ENTRY_COUNT:
        raise ArtifactExtractError("too_many_entries", "Artifact ZIP contains too many entries.")

    total_uncompressed = 0
    extracted_files = 0
    for info in infos:
        destination = _validated_zip_destination(info, temp_dir)
        total_uncompressed += info.file_size
        if total_uncompressed > MAX_UNCOMPRESSED_BYTES:
            raise ArtifactExtractError("zip_too_large", "Artifact ZIP expands beyond the allowed size limit.")

        if info.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
            continue

        extracted_files += 1
        destination.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(info, "r") as source, destination.open("wb") as target:
            shutil.copyfileobj(source, target)

    if extracted_files == 0:
        raise ArtifactExtractError("empty_zip", "Artifact ZIP does not contain any files.")


def _validated_zip_destination(info: zipfile.ZipInfo, temp_dir: Path) -> Path:
    normalized_name = info.filename.replace("\\", "/")
    if not normalized_name or normalized_name.startswith("/") or WINDOWS_ABSOLUTE_PATH_PATTERN.match(normalized_name):
        raise ArtifactExtractError("unsafe_zip_entry", "Artifact ZIP contains an absolute path entry.")

    parts = PurePosixPath(normalized_name).parts
    if not parts:
        raise ArtifactExtractError("unsafe_zip_entry", "Artifact ZIP contains an invalid entry.")
    for part in parts:
        if part in {"", ".", ".."}:
            raise ArtifactExtractError("unsafe_zip_entry", "Artifact ZIP contains path traversal entries.")
        if ":" in part or any(ord(ch) < 32 for ch in part):
            raise ArtifactExtractError("unsafe_zip_entry", "Artifact ZIP contains unsafe entry names.")

    unix_mode = (info.external_attr >> 16) & 0xFFFF
    if stat.S_ISLNK(unix_mode):
        raise ArtifactExtractError("unsafe_zip_entry", "Artifact ZIP contains symlink entries.")

    destination = (temp_dir / Path(*parts)).resolve(strict=False)
    _ensure_path_within_root(
        destination,
        temp_dir,
        code="unsafe_zip_entry",
        message="Artifact ZIP entry escapes the extraction directory.",
    )
    return destination


def _select_exe_candidate(temp_dir: Path, version: str) -> Path:
    candidates = sorted(path for path in temp_dir.rglob("*") if path.is_file() and path.suffix.lower() == ".exe")
    if not candidates:
        raise ArtifactExtractError("missing_exe", "Artifact ZIP must contain exactly one BUS Core executable.")
    if len(candidates) > 1:
        raise ArtifactExtractError("multiple_exes", "Artifact ZIP contains multiple executable candidates.")

    candidate = candidates[0]
    expected_name = f"BUS-Core-{version}.exe"
    if candidate.name == expected_name:
        return candidate
    return candidate


def _ensure_file_within_root(path: Path, root: Path) -> None:
    if not path.is_absolute():
        raise ArtifactExtractError("invalid_artifact_path", "Artifact path must be absolute.")
    _ensure_path_within_root(
        path.resolve(strict=False),
        root,
        code="invalid_artifact_path",
        message="Artifact path must stay inside update cache downloads directory.",
    )


def _ensure_path_within_root(path: Path, root: Path, *, code: str, message: str) -> None:
    resolved_root = root.resolve(strict=False)
    resolved_path = path.resolve(strict=False)
    try:
        resolved_path.relative_to(resolved_root)
    except ValueError as exc:
        raise ArtifactExtractError(code, message) from exc


def _cleanup_dir(path: Path) -> None:
    try:
        shutil.rmtree(path, ignore_errors=True)
    except Exception:
        pass


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")