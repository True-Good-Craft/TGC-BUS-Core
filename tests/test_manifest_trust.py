# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import base64
from copy import deepcopy

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from core.runtime.manifest_trust import (
    ManifestTrustError,
    canonicalize_manifest_payload,
    is_signed_manifest,
    unwrap_manifest,
    verify_embedded_manifest_signature,
    verify_manifest_envelope,
)

pytestmark = pytest.mark.unit

KEY_ID = "test-manifest-key"


def _payload() -> dict:
    return {
        "latest": {
            "version": "1.0.5",
            "download": {
                "url": "https://example.test/TGC-BUS-Core-1.0.5.zip",
                "sha256": "a" * 64,
            },
        },
        "channels": {"stable": {"latest": {"version": "1.0.5"}}},
    }


def _keypair():
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    public_bytes = public_key.public_bytes(encoding=Encoding.Raw, format=PublicFormat.Raw)
    return private_key, public_bytes


def _signed_envelope(payload: dict | None = None):
    private_key, public_bytes = _keypair()
    manifest_payload = payload or _payload()
    signature = private_key.sign(canonicalize_manifest_payload(manifest_payload))
    return (
        {
            "payload": manifest_payload,
            "signature": {
                "alg": "Ed25519",
                "key_id": KEY_ID,
                "sig": base64.b64encode(signature).decode("ascii"),
            },
        },
        {KEY_ID: public_bytes},
    )


def _embedded_payload() -> dict:
    return {
        "latest": {
            "version": "1.0.5",
            "download": {
                "url": "https://example.test/TGC-BUS-Core-1.0.5.zip",
                "sha256": "a" * 64,
            },
        },
        "channels": {
            "stable": {
                "version": "1.0.5",
                "download": {
                    "url": "https://example.test/TGC-BUS-Core-1.0.5.zip",
                    "sha256": "a" * 64,
                },
            }
        },
    }


def _signed_embedded_manifest(payload: dict | None = None):
    private_key, public_bytes = _keypair()
    manifest = payload or _embedded_payload()
    signature = private_key.sign(canonicalize_manifest_payload(manifest))
    signed_manifest = dict(manifest)
    signed_manifest["signature"] = {
        "alg": "Ed25519",
        "key_id": KEY_ID,
        "sig": base64.b64encode(signature).decode("ascii"),
    }
    return signed_manifest, {KEY_ID: public_bytes}


def test_valid_signed_envelope_verifies_and_returns_payload():
    envelope, trusted_keys = _signed_envelope()

    assert is_signed_manifest(envelope) is True
    assert verify_manifest_envelope(envelope, trusted_public_keys=trusted_keys) == envelope["payload"]


def test_valid_embedded_signed_manifest_verifies_and_returns_manifest_without_signature():
    manifest, trusted_keys = _signed_embedded_manifest()

    verified = verify_embedded_manifest_signature(manifest, trusted_public_keys=trusted_keys)

    assert is_signed_manifest(manifest) is True
    assert "signature" not in verified
    assert verified == _embedded_payload()


def test_embedded_verification_does_not_mutate_original_manifest():
    manifest, trusted_keys = _signed_embedded_manifest()
    original = deepcopy(manifest)

    verify_embedded_manifest_signature(manifest, trusted_public_keys=trusted_keys)

    assert manifest == original


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("latest", "version"), "1.0.6"),
        (("latest", "download", "url"), "https://example.test/evil.zip"),
        (("latest", "download", "sha256"), "b" * 64),
        (("channels", "stable", "version"), "1.0.6"),
    ],
)
def test_tampered_embedded_signed_manifest_fields_fail(path: tuple[str, ...], value: str):
    manifest, trusted_keys = _signed_embedded_manifest()
    cursor = manifest
    for key in path[:-1]:
        cursor = cursor[key]
    cursor[path[-1]] = value

    with pytest.raises(ManifestTrustError) as exc_info:
        verify_embedded_manifest_signature(manifest, trusted_public_keys=trusted_keys)

    assert exc_info.value.code == "bad_signature"


def test_embedded_signed_manifest_unknown_key_id_fails():
    manifest, trusted_keys = _signed_embedded_manifest()
    manifest["signature"]["key_id"] = "unknown"

    with pytest.raises(ManifestTrustError) as exc_info:
        verify_embedded_manifest_signature(manifest, trusted_public_keys=trusted_keys)

    assert exc_info.value.code == "unknown_key_id"


def test_embedded_signed_manifest_unsupported_alg_fails():
    manifest, trusted_keys = _signed_embedded_manifest()
    manifest["signature"]["alg"] = "RS256"

    with pytest.raises(ManifestTrustError) as exc_info:
        verify_embedded_manifest_signature(manifest, trusted_public_keys=trusted_keys)

    assert exc_info.value.code == "unsupported_alg"


def test_embedded_signed_manifest_malformed_base64_fails():
    manifest, trusted_keys = _signed_embedded_manifest()
    manifest["signature"]["sig"] = "not base64 !"

    with pytest.raises(ManifestTrustError) as exc_info:
        verify_embedded_manifest_signature(manifest, trusted_public_keys=trusted_keys)

    assert exc_info.value.code == "invalid_signature"


def test_tampered_payload_fails():
    envelope, trusted_keys = _signed_envelope()
    envelope["payload"]["latest"]["version"] = "9.9.9"

    with pytest.raises(ManifestTrustError) as exc_info:
        verify_manifest_envelope(envelope, trusted_public_keys=trusted_keys)

    assert exc_info.value.code == "bad_signature"


def test_tampered_signature_fails():
    envelope, trusted_keys = _signed_envelope()
    envelope["signature"]["sig"] = base64.b64encode(b"0" * 64).decode("ascii")

    with pytest.raises(ManifestTrustError) as exc_info:
        verify_manifest_envelope(envelope, trusted_public_keys=trusted_keys)

    assert exc_info.value.code == "bad_signature"


def test_unknown_key_id_fails():
    envelope, trusted_keys = _signed_envelope()
    envelope["signature"]["key_id"] = "unknown"

    with pytest.raises(ManifestTrustError) as exc_info:
        verify_manifest_envelope(envelope, trusted_public_keys=trusted_keys)

    assert exc_info.value.code == "unknown_key_id"


def test_unsupported_alg_fails():
    envelope, trusted_keys = _signed_envelope()
    envelope["signature"]["alg"] = "RS256"

    with pytest.raises(ManifestTrustError) as exc_info:
        verify_manifest_envelope(envelope, trusted_public_keys=trusted_keys)

    assert exc_info.value.code == "unsupported_alg"


def test_malformed_base64_fails():
    envelope, trusted_keys = _signed_envelope()
    envelope["signature"]["sig"] = "not base64 !"

    with pytest.raises(ManifestTrustError) as exc_info:
        verify_manifest_envelope(envelope, trusted_public_keys=trusted_keys)

    assert exc_info.value.code == "invalid_signature"


def test_unsigned_manifest_remains_available_when_enforcement_is_off():
    payload = _payload()

    assert is_signed_manifest(payload) is False
    assert unwrap_manifest(payload, trusted_public_keys={}, require_signature=False) is payload


def test_enforcement_on_rejects_unsigned_manifest():
    with pytest.raises(ManifestTrustError) as exc_info:
        unwrap_manifest(_payload(), trusted_public_keys={}, require_signature=True)

    assert exc_info.value.code == "missing_signature"


def test_canonicalization_is_stable_for_key_ordering():
    payload = {"b": 2, "a": {"d": 4, "c": 3}}
    reordered = {"a": {"c": 3, "d": 4}, "b": 2}

    assert canonicalize_manifest_payload(payload) == canonicalize_manifest_payload(reordered)


def test_verification_does_not_mutate_payload():
    envelope, trusted_keys = _signed_envelope()
    original = deepcopy(envelope["payload"])

    verify_manifest_envelope(envelope, trusted_public_keys=trusted_keys)

    assert envelope["payload"] == original
