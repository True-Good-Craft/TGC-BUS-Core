# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import base64

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from core.runtime.manifest_keys import (
    ManifestPublicKeyPolicy,
    PRODUCTION_MANIFEST_PUBLIC_KEY_B64,
    PRODUCTION_MANIFEST_PUBLIC_KEY_ID,
    PRODUCTION_MANIFEST_PUBLIC_KEYS,
    active_manifest_public_keys,
    production_manifest_key_policies,
)
from core.runtime.manifest_trust import canonicalize_manifest_payload
from core.services.update import UpdateService

pytestmark = pytest.mark.unit


def _public_key_bytes() -> bytes:
    return Ed25519PrivateKey.generate().public_key().public_bytes(encoding=Encoding.Raw, format=PublicFormat.Raw)


def _signed_envelope(payload: dict, *, key_id: str):
    private_key = Ed25519PrivateKey.generate()
    public_bytes = private_key.public_key().public_bytes(encoding=Encoding.Raw, format=PublicFormat.Raw)
    signature = private_key.sign(canonicalize_manifest_payload(payload))
    return (
        {
            "payload": payload,
            "signature": {
                "alg": "Ed25519",
                "key_id": key_id,
                "sig": base64.b64encode(signature).decode("ascii"),
            },
        },
        public_bytes,
    )


def test_production_key_policy_contains_pinned_release_key():
    assert production_manifest_key_policies() == PRODUCTION_MANIFEST_PUBLIC_KEYS
    assert len(PRODUCTION_MANIFEST_PUBLIC_KEYS) == 1

    policy = PRODUCTION_MANIFEST_PUBLIC_KEYS[0]
    assert policy.key_id == PRODUCTION_MANIFEST_PUBLIC_KEY_ID
    assert base64.b64encode(policy.public_key).decode("ascii") == PRODUCTION_MANIFEST_PUBLIC_KEY_B64
    assert active_manifest_public_keys() == {policy.key_id: policy.public_key}
    assert len(policy.public_key) == 32


def test_trusted_key_policy_shape_and_active_filter():
    active_key = _public_key_bytes()
    policies = (
        ManifestPublicKeyPolicy(key_id="active", public_key=active_key),
        ManifestPublicKeyPolicy(key_id="deprecated", public_key=_public_key_bytes(), status="deprecated"),
        ManifestPublicKeyPolicy(key_id="revoked", public_key=_public_key_bytes(), status="revoked"),
        ManifestPublicKeyPolicy(key_id="wrong-alg", public_key=_public_key_bytes(), algorithm="RS256"),
    )

    assert active_manifest_public_keys(policies) == {"active": active_key}


def test_empty_production_key_map_does_not_break_unsigned_update_checks():
    service = UpdateService(
        fetch_manifest=lambda _url, _timeout: {
            "version": "9.9.9",
            "download_url": "https://example.test/unsigned.zip",
        },
        trusted_manifest_public_keys=active_manifest_public_keys(),
    )

    result = service.check(manifest_url="https://example.test/manifest.json", channel="stable")

    assert result.error_code is None
    assert result.update_available is True
    assert result.download_url == "https://example.test/unsigned.zip"


def test_update_service_consumes_manifest_key_policy_map():
    payload = {
        "version": "9.9.9",
        "download_url": "https://example.test/signed.zip",
    }
    envelope, public_key = _signed_envelope(payload, key_id="test-key")
    trusted_keys = active_manifest_public_keys(
        (ManifestPublicKeyPolicy(key_id="test-key", public_key=public_key),)
    )
    service = UpdateService(fetch_manifest=lambda _url, _timeout: envelope, trusted_manifest_public_keys=trusted_keys)

    result = service.check(manifest_url="https://example.test/manifest.json", channel="stable")

    assert result.error_code is None
    assert result.update_available is True
    assert result.download_url == "https://example.test/signed.zip"


def test_deprecated_policy_key_does_not_verify_signed_manifest():
    payload = {
        "version": "9.9.9",
        "download_url": "https://example.test/signed.zip",
    }
    envelope, public_key = _signed_envelope(payload, key_id="old-key")
    trusted_keys = active_manifest_public_keys(
        (ManifestPublicKeyPolicy(key_id="old-key", public_key=public_key, status="deprecated"),)
    )
    service = UpdateService(fetch_manifest=lambda _url, _timeout: envelope, trusted_manifest_public_keys=trusted_keys)

    result = service.check(manifest_url="https://example.test/manifest.json", channel="stable")

    assert result.error_code == "unknown_key_id"
    assert result.update_available is False
