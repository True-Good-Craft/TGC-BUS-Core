# Copyright (C) 2025 BUS Core Authors
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

import ipaddress
import json
import re
from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import urlparse

import httpx

from core.version import VERSION as CURRENT_VERSION

REQUEST_TIMEOUT_SECONDS = 4.0
MAX_MANIFEST_BYTES = 65_536
SEMVER_PATTERN = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


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


class UpdateService:
    def __init__(
        self,
        fetch_manifest: Callable[[str, float], Any] | None = None,
    ) -> None:
        self._fetch_manifest = fetch_manifest or self._http_fetch_manifest

    def check(self, *, manifest_url: str, channel: str) -> UpdateResult:
        if not _is_semver(CURRENT_VERSION):
            return self._error_result("invalid_current_version", "Current version is not strict SemVer.")

        try:
            _validate_manifest_url(manifest_url)
            manifest = self._fetch_manifest(manifest_url, REQUEST_TIMEOUT_SECONDS)
            entry = _resolve_manifest_entry(manifest, channel)

            latest_version = entry.get("version")
            if not isinstance(latest_version, str):
                raise UpdateCheckError("missing_version", "Manifest version is required and must be a string.")
            if not _is_semver(latest_version):
                raise UpdateCheckError("invalid_manifest_version", "Manifest version must be strict SemVer.")

            download_url = _validate_download_url(entry)
            update_available = _parse_semver(latest_version) > _parse_semver(CURRENT_VERSION)

            return UpdateResult(
                current_version=CURRENT_VERSION,
                latest_version=latest_version,
                update_available=update_available,
                download_url=download_url if update_available else None,
            )
        except UpdateCheckError as exc:
            return self._error_result(exc.code, exc.message)
        except _timeout_exception_class():
            return self._error_result("timeout", "Update manifest request timed out.")
        except _http_error_class():
            return self._error_result("network_error", "Failed to fetch update manifest.")
        except Exception:
            return self._error_result("update_check_failed", "Update check failed.")

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
    if not isinstance(manifest_url, str) or not manifest_url.strip():
        raise UpdateCheckError("invalid_manifest_url", "Manifest URL is invalid.")

    parsed = urlparse(manifest_url.strip())
    if parsed.scheme not in {"http", "https"}:
        raise UpdateCheckError("invalid_manifest_url", "Manifest URL is invalid.")

    host = parsed.hostname
    if not host:
        raise UpdateCheckError("invalid_manifest_url", "Manifest URL is invalid.")

    lowered = host.lower()
    if lowered in {"localhost", "localhost."}:
        raise UpdateCheckError("manifest_url_not_allowed", "Manifest URL is not allowed.")

    try:
        ip = ipaddress.ip_address(lowered)
    except ValueError:
        ip = None

    if ip is None:
        return

    if ip.is_private or ip.is_loopback or ip.is_unspecified or ip.is_link_local:
        raise UpdateCheckError("manifest_url_not_allowed", "Manifest URL is not allowed.")


def _resolve_manifest_entry(manifest: Any, channel: str) -> dict[str, Any]:
    if not isinstance(manifest, dict):
        raise UpdateCheckError("invalid_manifest", "Manifest must be an object.")

    direct_entry = _normalize_manifest_entry(manifest)
    if direct_entry is not None:
        return direct_entry

    channels = manifest.get("channels")
    if isinstance(channels, dict):
        selected = channels.get(channel)
        if isinstance(selected, dict):
            selected_entry = _normalize_manifest_entry(selected)
            if selected_entry is not None:
                return selected_entry
            return selected
        raise UpdateCheckError("channel_not_found", "Requested update channel not found.")

    selected = manifest.get(channel)
    if isinstance(selected, dict):
        selected_entry = _normalize_manifest_entry(selected)
        if selected_entry is not None:
            return selected_entry
        return selected

    raise UpdateCheckError("channel_not_found", "Requested update channel not found.")


def _normalize_manifest_entry(manifest_obj: dict[str, Any]) -> dict[str, Any] | None:
    if "version" in manifest_obj:
        return manifest_obj

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

    return {
        "version": version,
        "download_url": download_url,
    }


def _validate_download_url(entry: dict[str, Any]) -> str | None:
    if "download_url" not in entry:
        return None
    download_url = entry.get("download_url")
    if download_url is None:
        return None
    if not isinstance(download_url, str):
        raise UpdateCheckError("invalid_download_url", "Manifest download_url must be a string when present.")
    return download_url


def _is_semver(raw: str) -> bool:
    return bool(SEMVER_PATTERN.match(raw))


def _parse_semver(raw: str) -> tuple[int, int, int]:
    match = SEMVER_PATTERN.match(raw)
    if not match:
        raise UpdateCheckError("invalid_version", "Version must be strict SemVer.")
    return int(match.group(1)), int(match.group(2)), int(match.group(3))
