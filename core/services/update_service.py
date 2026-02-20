# Copyright (C) 2025 BUS Core Authors
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timezone
from typing import Any, Mapping
from urllib.error import URLError
from urllib.request import urlopen


MANIFEST_UNREACHABLE = "MANIFEST_UNREACHABLE"
MANIFEST_INVALID_SCHEMA = "MANIFEST_INVALID_SCHEMA"


class ManifestUnreachable(Exception):
    pass


class ManifestInvalidSchema(Exception):
    pass


_SEMVER_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


def parse_semver(value: str) -> tuple[int, int, int]:
    match = _SEMVER_RE.fullmatch(value or "")
    if not match:
        raise ValueError("invalid semver")
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


class UpdateService:
    def __init__(self, config: Mapping[str, Any], version: str):
        self._config = config or {}
        self._version = version

    async def check(self) -> dict[str, Any]:
        updates = self._config.get("updates") if isinstance(self._config, Mapping) else None
        updates = updates if isinstance(updates, Mapping) else {}

        enabled = bool(updates.get("enabled", False))
        if not enabled:
            return {
                "enabled": False,
                "current_version": self._version,
            }

        manifest_url = str(
            updates.get("manifest_url")
            or "https://buscore.ca/manifest/core/stable.json"
        )

        try:
            payload = await asyncio.to_thread(self._fetch_manifest, manifest_url)
            return self._normalize(payload)
        except ManifestInvalidSchema as exc:
            return {
                "enabled": True,
                "current_version": self._version,
                "error": {
                    "code": MANIFEST_INVALID_SCHEMA,
                    "message": str(exc),
                },
            }
        except ManifestUnreachable as exc:
            return {
                "enabled": True,
                "current_version": self._version,
                "error": {
                    "code": MANIFEST_UNREACHABLE,
                    "message": str(exc),
                },
            }
        except Exception:
            return {
                "enabled": True,
                "current_version": self._version,
                "error": {
                    "code": MANIFEST_UNREACHABLE,
                    "message": "unexpected error during update check",
                },
            }

    def _fetch_manifest(self, manifest_url: str) -> Mapping[str, Any]:
        try:
            with urlopen(manifest_url, timeout=4) as response:
                raw = response.read()
        except URLError as exc:  # includes timeout
            raise ManifestUnreachable("manifest request failed") from exc

        try:
            payload = json.loads(raw.decode("utf-8"))
        except Exception as exc:
            raise ManifestInvalidSchema("manifest JSON is invalid") from exc

        if not isinstance(payload, Mapping):
            raise ManifestInvalidSchema("manifest must be an object")

        return payload

    def _normalize(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        latest = payload.get("latest") if isinstance(payload.get("latest"), Mapping) else None
        download = latest.get("download") if latest and isinstance(latest.get("download"), Mapping) else None
        latest_version = latest.get("version") if latest else None
        download_url = download.get("url") if download else None
        sha256 = download.get("sha256") if download else None

        if not (isinstance(latest_version, str) and isinstance(download_url, str) and isinstance(sha256, str)):
            raise ManifestInvalidSchema("manifest missing required fields")

        try:
            current_tuple = parse_semver(self._version)
            latest_tuple = parse_semver(latest_version)
        except ValueError as exc:
            raise ManifestInvalidSchema("invalid version format") from exc

        min_supported = payload.get("min_supported")
        if not isinstance(min_supported, str):
            min_supported = self._version

        try:
            min_supported_tuple = parse_semver(min_supported)
        except ValueError as exc:
            raise ManifestInvalidSchema("invalid min_supported format") from exc

        return {
            "enabled": True,
            "channel": "stable",
            "current_version": self._version,
            "latest_version": latest_version,
            "is_update_available": latest_tuple > current_tuple,
            "is_supported": current_tuple >= min_supported_tuple,
            "min_supported": min_supported,
            "download_url": download_url,
            "sha256": sha256,
            "size_bytes": download.get("size_bytes") if download else None,
            "release_notes_url": latest.get("release_notes_url") if latest else None,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "error": None,
        }
