# Copyright (C) 2025 BUS Core Authors
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Callable, Mapping

import httpx

from core.config.update_policy import (
    DEFAULT_UPDATE_CHANNEL,
    UpdatePolicyError,
    validate_update_channel,
    validate_update_manifest_url,
)
from core.version import VERSION as CURRENT_VERSION

REQUEST_TIMEOUT_SECONDS = 4.0
MAX_MANIFEST_BYTES = 65_536
SEMVER_PATTERN = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
SHA256_PATTERN = re.compile(r"^[A-Fa-f0-9]{64}$")
ARTIFACT_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+/-]{0,63}$")
ARTIFACT_METADATA_KEYS = (
    "type",
    "kind",
    "platform",
    "artifact_type",
    "artifact_kind",
    "artifact_platform",
)


class UpdateCheckError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class UpdateResult:
    current_version: str
    latest_version: str | None
    update_available: bool
    download_url: str | None
    error_code: str | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class ManifestRelease:
    """Validated manifest-provided metadata. These values are declared, not verified."""

    version: str
    channel: str
    download_url: str
    declared_sha256: str | None = None
    declared_size_bytes: int | None = None
    release_notes_url: str | None = None
    artifact_type: str | None = None
    artifact_kind: str | None = None
    platform: str | None = None
    signature_url: str | None = None
    publisher: str | None = None
    signer: str | None = None


class UpdateService:
    def __init__(
        self,
        fetch_manifest: Callable[[str, float], Any] | None = None,
        *,
        trusted_manifest_public_keys: Mapping[str, Any] | None = None,
        require_signed_manifest: bool = False,
    ) -> None:
        self._fetch_manifest = fetch_manifest or self._http_fetch_manifest
        self._trusted_manifest_public_keys = trusted_manifest_public_keys or {}
        self._require_signed_manifest = require_signed_manifest

    def check(self, *, manifest_url: str, channel: str) -> UpdateResult:
        if not _is_semver(CURRENT_VERSION):
            return self._error_result("invalid_current_version", "Current version is not strict SemVer.")

        try:
            _validate_manifest_url(manifest_url)
            selected_channel = _validate_update_channel(channel)
            manifest = self._fetch_manifest(manifest_url, REQUEST_TIMEOUT_SECONDS)
            manifest = self._unwrap_manifest(manifest)
            release = _resolve_manifest_release(manifest, selected_channel)

            latest_version = release.version
            if not _is_semver(latest_version):
                raise UpdateCheckError("invalid_manifest_version", "Manifest version must be strict SemVer.")

            update_available = _parse_semver(latest_version) > _parse_semver(CURRENT_VERSION)

            return UpdateResult(
                current_version=CURRENT_VERSION,
                latest_version=latest_version,
                update_available=update_available,
                download_url=release.download_url if update_available else None,
            )
        except UpdateCheckError as exc:
            return self._error_result(exc.code, exc.message)
        except _timeout_exception_class():
            return self._error_result("timeout", "Update manifest request timed out.")
        except _http_error_class():
            return self._error_result("network_error", "Failed to fetch update manifest.")
        except Exception:
            return self._error_result("update_check_failed", "Update check failed.")

    def _unwrap_manifest(self, manifest: Any) -> Any:
        if not self._require_signed_manifest and not _looks_like_signed_manifest(manifest):
            return manifest

        from core.runtime.manifest_trust import ManifestTrustError, unwrap_manifest

        try:
            return unwrap_manifest(
                manifest,
                trusted_public_keys=self._trusted_manifest_public_keys,
                require_signature=self._require_signed_manifest,
            )
        except ManifestTrustError as exc:
            raise UpdateCheckError(exc.code, exc.message) from exc

    @staticmethod
    def _http_fetch_manifest(url: str, timeout_s: float) -> Any:
        timeout_config = _build_timeout(timeout_s)
        client_cls = getattr(httpx, "Client", None)
        if callable(client_cls):
            try:
                with client_cls(timeout=timeout_config, follow_redirects=False) as client:
                    stream_method = getattr(client, "stream", None)
                    if callable(stream_method):
                        with stream_method("GET", url) as response:
                            return _read_manifest_response(response)
            except TypeError:
                pass

        stream_fn = getattr(httpx, "stream", None)
        if not callable(stream_fn):
            raise UpdateCheckError("network_error", "Failed to fetch update manifest.")

        with stream_fn("GET", url, timeout=timeout_config, follow_redirects=False) as response:
            return _read_manifest_response(response)

    @staticmethod
    def _error_result(code: str, message: str) -> UpdateResult:
        return UpdateResult(
            current_version=CURRENT_VERSION,
            latest_version=None,
            update_available=False,
            download_url=None,
            error_code=code,
            error_message=message,
        )


def _build_timeout(timeout_s: float) -> Any:
    timeout_cls = getattr(httpx, "Timeout", None)
    if callable(timeout_cls):
        return timeout_cls(timeout_s)
    return timeout_s


def _header_value(response: Any, name: str) -> str | None:
    headers = getattr(response, "headers", None)
    if headers is None:
        return None
    get_method = getattr(headers, "get", None)
    if callable(get_method):
        value = get_method(name)
        if value is None:
            value = get_method(name.lower())
        return value
    if isinstance(headers, dict):
        value = headers.get(name)
        if value is None:
            value = headers.get(name.lower())
        return value
    if isinstance(headers, list):
        for item in headers:
            if isinstance(item, tuple) and len(item) == 2 and str(item[0]).lower() == name.lower():
                return str(item[1])
    return None


def _timeout_exception_class() -> tuple[type[BaseException], ...]:
    timeout_exception = getattr(httpx, "TimeoutException", TimeoutError)
    return (timeout_exception, TimeoutError)


def _http_error_class() -> tuple[type[BaseException], ...]:
    http_error = getattr(httpx, "HTTPError", None)
    return (http_error,) if isinstance(http_error, type) else tuple()


def _read_manifest_response(response: Any) -> Any:
    status_code = int(getattr(response, "status_code", 0))
    if 300 <= status_code < 400:
        raise UpdateCheckError("network_error", "Failed to fetch update manifest.")

    raise_for_status = getattr(response, "raise_for_status", None)
    if callable(raise_for_status):
        raise_for_status()
    elif status_code >= 400:
        raise UpdateCheckError("network_error", "Failed to fetch update manifest.")

    content_type = _header_value(response, "content-type")
    if content_type and "application/json" not in content_type.lower():
        raise UpdateCheckError("invalid_manifest", "Manifest must be JSON.")

    content_length = _header_value(response, "content-length")
    if content_length is not None:
        try:
            if int(content_length) > MAX_MANIFEST_BYTES:
                raise UpdateCheckError("manifest_too_large", "Manifest exceeds maximum size.")
        except ValueError:
            pass

    total_bytes = 0
    buffer = bytearray()
    for chunk in response.iter_bytes():
        total_bytes += len(chunk)
        if total_bytes > MAX_MANIFEST_BYTES:
            raise UpdateCheckError("manifest_too_large", "Manifest exceeds maximum size.")
        buffer.extend(chunk)

    try:
        return json.loads(bytes(buffer).decode("utf-8"))
    except Exception:
        raise UpdateCheckError("invalid_manifest", "Manifest must be valid JSON.")


def _validate_manifest_url(manifest_url: str) -> None:
    try:
        validate_update_manifest_url(manifest_url)
    except UpdatePolicyError as exc:
        raise UpdateCheckError(exc.code, exc.message) from exc


def _validate_update_channel(channel: str) -> str:
    try:
        return validate_update_channel(channel)
    except UpdatePolicyError as exc:
        raise UpdateCheckError(exc.code, exc.message) from exc


def _resolve_manifest_release(manifest: Any, channel: str) -> ManifestRelease:
    if not isinstance(manifest, dict):
        raise UpdateCheckError("invalid_manifest", "Manifest must be an object.")

    channels = manifest.get("channels")
    if "channels" in manifest and not isinstance(channels, dict):
        raise UpdateCheckError("invalid_manifest", "Manifest channels must be an object.")

    if channel != DEFAULT_UPDATE_CHANNEL:
        if isinstance(channels, dict):
            selected = channels.get(channel)
            if isinstance(selected, dict):
                _validate_entry_channel(selected, channel, channel_key_matched=True)
                selected_release = _normalize_manifest_release(selected, channel)
                if selected_release is not None:
                    return selected_release
                raise UpdateCheckError("invalid_manifest", "Manifest release entry is invalid.")

        selected = manifest.get(channel)
        if isinstance(selected, dict):
            _validate_entry_channel(selected, channel, channel_key_matched=True)
            selected_release = _normalize_manifest_release(selected, channel)
            if selected_release is not None:
                return selected_release
            raise UpdateCheckError("invalid_manifest", "Manifest release entry is invalid.")

        if _manifest_has_release_shape(manifest):
            _validate_entry_channel(manifest, channel, channel_key_matched=False)
            return _normalize_manifest_release(manifest, channel)

        raise UpdateCheckError("channel_not_found", "Requested update channel not found.")

    if _manifest_has_release_shape(manifest):
        _validate_entry_channel(manifest, channel, channel_key_matched=False)
        return _normalize_manifest_release(manifest, channel)

    if isinstance(channels, dict):
        selected = channels.get(channel)
        if isinstance(selected, dict):
            _validate_entry_channel(selected, channel, channel_key_matched=True)
            selected_release = _normalize_manifest_release(selected, channel)
            if selected_release is not None:
                return selected_release
            raise UpdateCheckError("invalid_manifest", "Manifest release entry is invalid.")

    selected = manifest.get(channel)
    if isinstance(selected, dict):
        _validate_entry_channel(selected, channel, channel_key_matched=True)
        selected_release = _normalize_manifest_release(selected, channel)
        if selected_release is not None:
            return selected_release
        raise UpdateCheckError("invalid_manifest", "Manifest release entry is invalid.")

    raise UpdateCheckError("channel_not_found", "Requested update channel not found.")


def _looks_like_signed_manifest(manifest: Any) -> bool:
    return isinstance(manifest, dict) and "signature" in manifest


def _resolve_manifest_entry(manifest: Any, channel: str) -> dict[str, Any]:
    release = _resolve_manifest_release(manifest, channel)
    return {"version": release.version, "download_url": release.download_url}


def _manifest_has_release_shape(manifest_obj: dict[str, Any]) -> bool:
    return "version" in manifest_obj or "latest" in manifest_obj


def _validate_entry_channel(manifest_obj: dict[str, Any], requested_channel: str, *, channel_key_matched: bool) -> None:
    manifest_channel = manifest_obj.get("channel")
    if manifest_channel is None:
        # Current Lighthouse publishes the stable lane as a channel-less manifest.
        # Non-stable direct manifests need explicit channel metadata; entries
        # selected from a matching channels[channel] key already carry lane intent.
        if requested_channel != DEFAULT_UPDATE_CHANNEL and not channel_key_matched:
            raise UpdateCheckError("channel_not_found", "Requested update channel not found.")
        return

    try:
        actual_channel = validate_update_channel(manifest_channel)
    except UpdatePolicyError as exc:
        raise UpdateCheckError(exc.code, exc.message) from exc

    if actual_channel != requested_channel:
        raise UpdateCheckError("channel_mismatch", "Manifest channel does not match configured update channel.")


def _normalize_manifest_release(
    manifest_obj: dict[str, Any],
    channel: str,
    *,
    validate_metadata: bool = True,
) -> ManifestRelease | None:
    if "version" in manifest_obj:
        return _build_direct_release(manifest_obj, channel, validate_metadata=validate_metadata)

    if "latest" not in manifest_obj:
        return None

    latest_obj = manifest_obj.get("latest")
    if not isinstance(latest_obj, dict):
        raise UpdateCheckError("invalid_manifest", "Manifest latest must be an object.")

    version = latest_obj.get("version")
    if not isinstance(version, str):
        raise UpdateCheckError("invalid_manifest", "Manifest latest.version is required and must be a string.")
    if not _is_semver(version):
        raise UpdateCheckError("invalid_manifest_version", "Manifest version must be strict SemVer.")

    download = latest_obj.get("download")
    if not isinstance(download, dict):
        raise UpdateCheckError("invalid_manifest", "Manifest latest.download is required and must be an object.")

    download_url = download.get("url")
    if not isinstance(download_url, str):
        raise UpdateCheckError("invalid_manifest", "Manifest latest.download.url is required and must be a string.")

    return _build_canonical_release(latest_obj, download, channel, validate_metadata=validate_metadata)


def _build_direct_release(entry: dict[str, Any], channel: str, *, validate_metadata: bool) -> ManifestRelease:
    version = entry.get("version")
    if not isinstance(version, str):
        raise UpdateCheckError("missing_version", "Manifest version is required and must be a string.")
    if not _is_semver(version):
        raise UpdateCheckError("invalid_manifest_version", "Manifest version must be strict SemVer.")

    download_url = _validate_download_url(entry)
    if not validate_metadata:
        return ManifestRelease(version=version, channel=channel, download_url=download_url)

    _validate_direct_entry_metadata(entry)
    return ManifestRelease(
        version=version,
        channel=channel,
        download_url=download_url,
        declared_sha256=_optional_sha256(*_metadata_lookup((entry,), ("sha256",))),
        declared_size_bytes=_optional_size_bytes(*_metadata_lookup((entry,), ("size_bytes",))),
        release_notes_url=_optional_release_notes_url(*_metadata_lookup((entry,), ("release_notes_url",))),
        artifact_type=_metadata_token((entry,), ("artifact_type", "type")),
        artifact_kind=_metadata_token((entry,), ("artifact_kind", "kind")),
        platform=_metadata_token((entry,), ("artifact_platform", "platform")),
        signature_url=_optional_signature_url(*_metadata_lookup((entry,), ("signature_url",))),
        publisher=_optional_text_metadata(*_metadata_lookup((entry,), ("publisher",)), field_name="publisher"),
        signer=_optional_text_metadata(*_metadata_lookup((entry,), ("signer",)), field_name="signer"),
    )


def _build_canonical_release(
    latest_obj: dict[str, Any],
    download_obj: dict[str, Any],
    channel: str,
    *,
    validate_metadata: bool,
) -> ManifestRelease:
    version = latest_obj.get("version")
    if not isinstance(version, str):
        raise UpdateCheckError("invalid_manifest", "Manifest latest.version is required and must be a string.")
    if not _is_semver(version):
        raise UpdateCheckError("invalid_manifest_version", "Manifest version must be strict SemVer.")

    download_url = _validate_download_url({"download_url": download_obj.get("url")})
    if not validate_metadata:
        return ManifestRelease(version=version, channel=channel, download_url=download_url)

    _validate_canonical_entry_metadata(latest_obj, download_obj)
    return ManifestRelease(
        version=version,
        channel=channel,
        download_url=download_url,
        declared_sha256=_optional_sha256(*_metadata_lookup((download_obj, latest_obj), ("sha256",))),
        declared_size_bytes=_optional_size_bytes(*_metadata_lookup((download_obj, latest_obj), ("size_bytes",))),
        release_notes_url=_optional_release_notes_url(*_metadata_lookup((latest_obj,), ("release_notes_url",))),
        artifact_type=_metadata_token((download_obj, latest_obj), ("artifact_type", "type")),
        artifact_kind=_metadata_token((download_obj, latest_obj), ("artifact_kind", "kind")),
        platform=_metadata_token((download_obj, latest_obj), ("artifact_platform", "platform")),
        signature_url=_optional_signature_url(*_metadata_lookup((download_obj, latest_obj), ("signature_url",))),
        publisher=_optional_text_metadata(
            *_metadata_lookup((download_obj, latest_obj), ("publisher",)),
            field_name="publisher",
        ),
        signer=_optional_text_metadata(
            *_metadata_lookup((download_obj, latest_obj), ("signer",)),
            field_name="signer",
        ),
    )


def _validate_direct_entry_metadata(entry: dict[str, Any]) -> None:
    _validate_optional_sha256(entry.get("sha256"), present="sha256" in entry)
    _validate_optional_size_bytes(entry.get("size_bytes"), present="size_bytes" in entry)
    _validate_optional_release_notes_url(entry.get("release_notes_url"), present="release_notes_url" in entry)
    _validate_optional_signature_url(entry.get("signature_url"), present="signature_url" in entry)
    _validate_optional_text_metadata(entry.get("publisher"), present="publisher" in entry, field_name="publisher")
    _validate_optional_text_metadata(entry.get("signer"), present="signer" in entry, field_name="signer")
    _validate_artifact_metadata_fields(entry)


def _validate_canonical_entry_metadata(latest_obj: dict[str, Any], download_obj: dict[str, Any]) -> None:
    _validate_optional_sha256(latest_obj.get("sha256"), present="sha256" in latest_obj)
    _validate_optional_sha256(download_obj.get("sha256"), present="sha256" in download_obj)
    _validate_optional_size_bytes(latest_obj.get("size_bytes"), present="size_bytes" in latest_obj)
    _validate_optional_size_bytes(download_obj.get("size_bytes"), present="size_bytes" in download_obj)
    _validate_optional_release_notes_url(
        latest_obj.get("release_notes_url"),
        present="release_notes_url" in latest_obj,
    )
    _validate_optional_signature_url(latest_obj.get("signature_url"), present="signature_url" in latest_obj)
    _validate_optional_signature_url(download_obj.get("signature_url"), present="signature_url" in download_obj)
    _validate_optional_text_metadata(latest_obj.get("publisher"), present="publisher" in latest_obj, field_name="publisher")
    _validate_optional_text_metadata(download_obj.get("publisher"), present="publisher" in download_obj, field_name="publisher")
    _validate_optional_text_metadata(latest_obj.get("signer"), present="signer" in latest_obj, field_name="signer")
    _validate_optional_text_metadata(download_obj.get("signer"), present="signer" in download_obj, field_name="signer")
    _validate_artifact_metadata_fields(latest_obj)
    _validate_artifact_metadata_fields(download_obj)


def _metadata_lookup(containers: tuple[dict[str, Any], ...], keys: tuple[str, ...]) -> tuple[Any, bool]:
    for container in containers:
        for key in keys:
            if key in container:
                return container.get(key), True
    return None, False


def _metadata_token(containers: tuple[dict[str, Any], ...], keys: tuple[str, ...]) -> str | None:
    value, present = _metadata_lookup(containers, keys)
    if not present:
        return None
    return _artifact_token(value)


def _validate_optional_sha256(value: Any, *, present: bool) -> None:
    _optional_sha256(value, present)


def _optional_sha256(value: Any, present: bool) -> str | None:
    if not present:
        return None
    if not isinstance(value, str) or not SHA256_PATTERN.fullmatch(value):
        raise UpdateCheckError("invalid_manifest_sha256", "Manifest sha256 must be 64 hex characters.")
    return value


def _validate_optional_size_bytes(value: Any, *, present: bool) -> None:
    _optional_size_bytes(value, present)


def _optional_size_bytes(value: Any, present: bool) -> int | None:
    if not present:
        return None
    if type(value) is not int or value <= 0:
        raise UpdateCheckError("invalid_manifest_size", "Manifest size_bytes must be a positive integer.")
    return value


def _validate_optional_release_notes_url(value: Any, *, present: bool) -> None:
    _optional_release_notes_url(value, present)


def _optional_release_notes_url(value: Any, present: bool) -> str | None:
    if not present:
        return None
    if not isinstance(value, str) or not value.strip():
        raise UpdateCheckError("invalid_release_notes_url", "Manifest release_notes_url is invalid.")

    try:
        parsed = httpx.URL(value.strip())
    except Exception:
        raise UpdateCheckError("invalid_release_notes_url", "Manifest release_notes_url is invalid.")
    if parsed.scheme not in {"http", "https"} or not parsed.host:
        raise UpdateCheckError("invalid_release_notes_url", "Manifest release_notes_url is invalid.")
    return value.strip()


def _validate_optional_signature_url(value: Any, *, present: bool) -> None:
    _optional_signature_url(value, present)


def _optional_signature_url(value: Any, present: bool) -> str | None:
    if not present:
        return None
    if not isinstance(value, str) or not value.strip():
        raise UpdateCheckError("invalid_signature_url", "Manifest signature_url is invalid.")
    try:
        return validate_update_manifest_url(value.strip())
    except UpdatePolicyError as exc:
        raise UpdateCheckError("invalid_signature_url", exc.message) from exc


def _validate_optional_text_metadata(value: Any, *, present: bool, field_name: str) -> None:
    _optional_text_metadata(value, present, field_name=field_name)


def _optional_text_metadata(value: Any, present: bool, *, field_name: str) -> str | None:
    if not present:
        return None
    if not isinstance(value, str) or not value.strip() or value.strip() != value or len(value) > 128:
        raise UpdateCheckError("invalid_artifact_metadata", f"Manifest {field_name} must be a non-empty string.")
    if any(ord(char) < 32 for char in value):
        raise UpdateCheckError("invalid_artifact_metadata", f"Manifest {field_name} must be a non-empty string.")
    return value


def _validate_artifact_metadata_fields(container: dict[str, Any]) -> None:
    for key in ARTIFACT_METADATA_KEYS:
        if key not in container:
            continue
        _artifact_token(container.get(key))


def _artifact_token(value: Any) -> str:
    stripped = value.strip() if isinstance(value, str) else ""
    if not isinstance(value, str) or stripped != value or not ARTIFACT_TOKEN_PATTERN.fullmatch(value):
        raise UpdateCheckError(
            "invalid_artifact_metadata",
            "Manifest artifact metadata fields must be non-empty token strings.",
        )
    return value


def _validate_download_url(entry: dict[str, Any]) -> str:
    if "download_url" not in entry:
        raise UpdateCheckError("invalid_manifest", "Manifest download_url is required.")
    download_url = entry.get("download_url")
    if not isinstance(download_url, str) or not download_url.strip():
        raise UpdateCheckError("invalid_download_url", "Manifest download_url must be a string when present.")
    try:
        return validate_update_manifest_url(download_url.strip())
    except UpdatePolicyError as exc:
        raise UpdateCheckError("invalid_download_url", exc.message) from exc


def _is_semver(raw: str) -> bool:
    return bool(SEMVER_PATTERN.match(raw))


def _parse_semver(raw: str) -> tuple[int, int, int]:
    match = SEMVER_PATTERN.match(raw)
    if not match:
        raise UpdateCheckError("invalid_version", "Version must be strict SemVer.")
    return int(match.group(1)), int(match.group(2)), int(match.group(3))
