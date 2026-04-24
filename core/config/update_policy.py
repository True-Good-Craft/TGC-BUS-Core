# Copyright (C) 2025 BUS Core Authors
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

import ipaddress
import os
from urllib.parse import urlparse

DEFAULT_UPDATE_CHANNEL = "stable"
ALLOWED_UPDATE_CHANNELS = (
    "stable",
    "test",
    "partner-3dque",
    "lts-1.1",
    "security-hotfix",
)
DEFAULT_UPDATE_MANIFEST_URL = "https://lighthouse.buscore.ca/update/check"

_ALLOWED_UPDATE_CHANNELS = set(ALLOWED_UPDATE_CHANNELS)


class UpdatePolicyError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def dev_update_manifest_urls_allowed() -> bool:
    return (
        os.getenv("BUS_DEV", "0") == "1"
        or os.getenv("BUS_ALLOW_DEV_UPDATE_MANIFEST_URLS", "0") == "1"
    )


def validate_update_channel(value: object) -> str:
    if not isinstance(value, str):
        raise UpdatePolicyError("invalid_update_channel", "Update channel is invalid.")
    channel = value.strip().lower()
    if channel not in _ALLOWED_UPDATE_CHANNELS:
        raise UpdatePolicyError("invalid_update_channel", "Update channel is invalid.")
    return channel


def validate_update_manifest_url(value: object, *, allow_dev_urls: bool | None = None) -> str:
    if allow_dev_urls is None:
        allow_dev_urls = dev_update_manifest_urls_allowed()

    if not isinstance(value, str) or not value.strip():
        raise UpdatePolicyError("invalid_manifest_url", "Manifest URL is invalid.")

    manifest_url = value.strip()
    parsed = urlparse(manifest_url)
    if parsed.scheme not in {"http", "https"}:
        raise UpdatePolicyError("invalid_manifest_url", "Manifest URL is invalid.")

    host = parsed.hostname
    if not host:
        raise UpdatePolicyError("invalid_manifest_url", "Manifest URL is invalid.")

    lowered = host.lower()
    if lowered in {"localhost", "localhost."}:
        if allow_dev_urls:
            return manifest_url
        raise UpdatePolicyError("manifest_url_not_allowed", "Manifest URL is not allowed.")

    try:
        ip = ipaddress.ip_address(lowered)
    except ValueError:
        ip = None

    if ip is not None and (ip.is_private or ip.is_loopback or ip.is_unspecified or ip.is_link_local):
        if allow_dev_urls:
            return manifest_url
        raise UpdatePolicyError("manifest_url_not_allowed", "Manifest URL is not allowed.")

    if parsed.scheme != "https" and not allow_dev_urls:
        raise UpdatePolicyError("invalid_manifest_url", "Manifest URL must use HTTPS.")

    return manifest_url
