# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import httpx

from core.config.update_policy import UpdatePolicyError, validate_update_manifest_url
from core.runtime import update_cache
from core.services.update import ManifestRelease
from core.version import VERSION as CURRENT_VERSION

ARTIFACT_TIMEOUT_SECONDS = 30.0
ARTIFACT_CHUNK_SIZE = 65_536
SHA256_PATTERN = re.compile(r"^[A-Fa-f0-9]{64}$")


class ArtifactDownloadError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class DownloadedArtifact:
    version: str
    channel: str
    artifact_path: str
    sha256: str
    size_bytes: int
    downloaded_at: str
    verified_at: str


class UpdateArtifactService:
    def __init__(
        self,
        fetch_artifact: Callable[[str, float], bytes] | None = None,
    ) -> None:
        self._fetch_artifact = fetch_artifact or _http_fetch_artifact

    def download_and_verify(
        self,
        release: ManifestRelease,
        *,
        root: Path | None = None,
    ) -> DownloadedArtifact:
        _validate_release_for_download(release)
        target_root = update_cache.ensure_cache_dirs(root)
        downloads_root = update_cache.downloads_dir(target_root)
        file_name = _safe_artifact_filename(release)
        final_path = (downloads_root / file_name).resolve(strict=False)
        _ensure_path_within_root(final_path, downloads_root)

        partial_path = final_path.with_name(f"{final_path.name}.part.{os.getpid()}")
        _cleanup_file(partial_path)

        expected_hash = release.declared_sha256.lower()
        expected_size = release.declared_size_bytes

        hasher = hashlib.sha256()
        total_size = 0
        try:
            with partial_path.open("wb") as handle:
                payload = self._fetch_artifact(release.download_url, ARTIFACT_TIMEOUT_SECONDS)
                for chunk in _iter_payload_chunks(payload):
                    if not chunk:
                        continue
                    total_size += len(chunk)
                    if expected_size is not None and total_size > expected_size:
                        raise ArtifactDownloadError("artifact_size_mismatch", "Downloaded artifact size does not match manifest.")
                    hasher.update(chunk)
                    handle.write(chunk)

            if expected_size is not None and total_size != expected_size:
                raise ArtifactDownloadError("artifact_size_mismatch", "Downloaded artifact size does not match manifest.")

            digest = hasher.hexdigest().lower()
            if digest != expected_hash:
                raise ArtifactDownloadError("artifact_hash_mismatch", "Downloaded artifact hash does not match manifest.")

            partial_path.replace(final_path)
            timestamp = _utc_now_iso()
            state = update_cache.read_state(target_root, active_version=CURRENT_VERSION)
            state["hash_verified"] = {
                "version": release.version,
                "channel": release.channel,
                "artifact_path": str(final_path),
                "sha256": digest,
                "size_bytes": total_size,
                "downloaded": True,
                "hash_verified": True,
                "downloaded_at": timestamp,
                "verified_at": timestamp,
            }
            update_cache.write_state(state, target_root, active_version=CURRENT_VERSION)
            return DownloadedArtifact(
                version=release.version,
                channel=release.channel,
                artifact_path=str(final_path),
                sha256=digest,
                size_bytes=total_size,
                downloaded_at=timestamp,
                verified_at=timestamp,
            )
        except ArtifactDownloadError:
            _cleanup_file(partial_path)
            raise
        except _timeout_exception_class():
            _cleanup_file(partial_path)
            raise ArtifactDownloadError("timeout", "Artifact download request timed out.")
        except _http_error_class():
            _cleanup_file(partial_path)
            raise ArtifactDownloadError("network_error", "Failed to download update artifact.")
        except Exception:
            _cleanup_file(partial_path)
            raise ArtifactDownloadError("artifact_download_failed", "Artifact download failed.")


def _validate_release_for_download(release: ManifestRelease) -> None:
    try:
        validate_update_manifest_url(release.download_url)
    except UpdatePolicyError as exc:
        raise ArtifactDownloadError("invalid_download_url", exc.message) from exc

    if not isinstance(release.declared_sha256, str) or not SHA256_PATTERN.fullmatch(release.declared_sha256):
        raise ArtifactDownloadError("missing_declared_sha256", "Manifest declared sha256 is required for artifact download.")

    if release.declared_size_bytes is not None:
        if type(release.declared_size_bytes) is not int or release.declared_size_bytes <= 0:
            raise ArtifactDownloadError("invalid_declared_size", "Manifest declared size_bytes is invalid.")


def _safe_artifact_filename(release: ManifestRelease) -> str:
    safe_channel = re.sub(r"[^A-Za-z0-9._-]", "-", release.channel).strip(".-") or "stable"
    safe_version = re.sub(r"[^0-9.]", "-", release.version).strip(".-") or "0.0.0"
    return f"BUS-Core-{safe_version}-{safe_channel}.zip"


def _ensure_path_within_root(path: Path, root: Path) -> None:
    resolved_path = path.resolve(strict=False)
    resolved_root = root.resolve(strict=False)
    try:
        resolved_path.relative_to(resolved_root)
    except ValueError as exc:
        raise ArtifactDownloadError("invalid_artifact_path", "Artifact path escapes update cache downloads directory.") from exc


def _iter_payload_chunks(payload: bytes) -> list[bytes] | Any:
    if isinstance(payload, (bytes, bytearray)):
        return [bytes(payload)]
    return payload


def _http_fetch_artifact(url: str, timeout_s: float) -> bytes:
    timeout_config = _build_timeout(timeout_s)
    client_cls = getattr(httpx, "Client", None)
    if callable(client_cls):
        try:
            with client_cls(timeout=timeout_config, follow_redirects=False) as client:
                stream_method = getattr(client, "stream", None)
                if callable(stream_method):
                    with stream_method("GET", url) as response:
                        return _read_artifact_response(response)
        except TypeError:  # Compatibility fallback: older httpx stubs may not accept Client timeout options.
            pass

    stream_fn = getattr(httpx, "stream", None)
    if not callable(stream_fn):
        raise ArtifactDownloadError("network_error", "Failed to download update artifact.")

    with stream_fn("GET", url, timeout=timeout_config, follow_redirects=False) as response:
        return _read_artifact_response(response)


def _build_timeout(timeout_s: float) -> Any:
    timeout_cls = getattr(httpx, "Timeout", None)
    if callable(timeout_cls):
        return timeout_cls(timeout_s)
    return timeout_s


def _read_artifact_response(response: Any) -> bytes:
    status_code = int(getattr(response, "status_code", 0))
    if 300 <= status_code < 400:
        raise ArtifactDownloadError("network_error", "Failed to download update artifact.")

    raise_for_status = getattr(response, "raise_for_status", None)
    if callable(raise_for_status):
        raise_for_status()
    elif status_code >= 400:
        raise ArtifactDownloadError("network_error", "Failed to download update artifact.")

    chunks: list[bytes] = []
    iter_bytes = getattr(response, "iter_bytes", None)
    if callable(iter_bytes):
        for chunk in iter_bytes():
            chunks.append(chunk)
        return b"".join(chunks)

    content = getattr(response, "content", None)
    if isinstance(content, (bytes, bytearray)):
        return bytes(content)

    raise ArtifactDownloadError("network_error", "Failed to download update artifact.")


def _timeout_exception_class() -> tuple[type[BaseException], ...]:
    timeout_exception = getattr(httpx, "TimeoutException", TimeoutError)
    return (timeout_exception, TimeoutError)


def _http_error_class() -> tuple[type[BaseException], ...]:
    http_error = getattr(httpx, "HTTPError", None)
    return (http_error,) if isinstance(http_error, type) else tuple()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _cleanup_file(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except Exception:  # Best-effort cleanup; partial artifact may already be absent.
        pass