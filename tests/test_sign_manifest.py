# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import base64
import json

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, PublicFormat, NoEncryption

from core.runtime.manifest_trust import ManifestTrustError, verify_embedded_manifest_signature
from scripts import sign_manifest

pytestmark = pytest.mark.unit

KEY_ID = "test-manifest-key"


def _manifest() -> dict:
    return {
        "latest": {
            "version": "1.0.5",
            "download": {
                "url": "https://example.test/BUS-Core-1.0.5.zip",
                "sha256": "a" * 64,
            },
        },
        "history": [],
    }


def _keypair():
    private_key = Ed25519PrivateKey.generate()
    private_raw = private_key.private_bytes(
        encoding=Encoding.Raw,
        format=PrivateFormat.Raw,
        encryption_algorithm=NoEncryption(),
    )
    public_raw = private_key.public_key().public_bytes(encoding=Encoding.Raw, format=PublicFormat.Raw)
    return private_key, base64.b64encode(private_raw).decode("ascii"), public_raw


def test_generated_signed_manifest_verifies_with_matching_public_key():
    private_key, _private_raw_b64, public_raw = _keypair()

    signed = sign_manifest.sign_manifest_dict(_manifest(), key_id=KEY_ID, private_key=private_key)

    verified = verify_embedded_manifest_signature(signed, trusted_public_keys={KEY_ID: public_raw})
    assert verified == _manifest()


def test_tampering_signed_output_fails_verification():
    private_key, _private_raw_b64, public_raw = _keypair()
    signed = sign_manifest.sign_manifest_dict(_manifest(), key_id=KEY_ID, private_key=private_key)
    signed["latest"]["download"]["url"] = "https://example.test/tampered.zip"

    with pytest.raises(ManifestTrustError) as exc_info:
        verify_embedded_manifest_signature(signed, trusted_public_keys={KEY_ID: public_raw})

    assert exc_info.value.code == "bad_signature"


def test_existing_signature_is_replaced_not_signed_over():
    private_key, _private_raw_b64, public_raw = _keypair()
    manifest = _manifest()
    manifest["signature"] = {
        "alg": "Ed25519",
        "key_id": "old-key",
        "sig": "old-signature",
    }

    signed = sign_manifest.sign_manifest_dict(manifest, key_id=KEY_ID, private_key=private_key)

    assert signed["signature"]["key_id"] == KEY_ID
    assert signed["signature"]["sig"] != "old-signature"
    assert "signature" not in verify_embedded_manifest_signature(signed, trusted_public_keys={KEY_ID: public_raw})


def test_output_preserves_latest_version_and_download_url(tmp_path, monkeypatch):
    _private_key, private_raw_b64, public_raw = _keypair()
    input_path = tmp_path / "stable.json"
    output_path = tmp_path / "stable-signed.json"
    public_path = tmp_path / "manifest.pub"
    input_path.write_text(json.dumps(_manifest()), encoding="utf-8")
    public_path.write_text(base64.b64encode(public_raw).decode("ascii"), encoding="utf-8")
    monkeypatch.setenv("BUS_MANIFEST_SIGNING_PRIVATE_KEY", private_raw_b64)

    result = sign_manifest.main(
        [
            str(input_path),
            str(output_path),
            "--key-id",
            KEY_ID,
            "--public-key-file",
            str(public_path),
        ]
    )

    assert result == 0
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["latest"]["version"] == "1.0.5"
    assert payload["latest"]["download"]["url"] == "https://example.test/BUS-Core-1.0.5.zip"
    assert payload["signature"]["alg"] == "Ed25519"
    verify_embedded_manifest_signature(payload, trusted_public_keys={KEY_ID: public_raw})


def test_missing_private_key_fails_cleanly(monkeypatch):
    monkeypatch.delenv("BUS_MANIFEST_SIGNING_PRIVATE_KEY", raising=False)

    with pytest.raises(sign_manifest.ManifestSigningError, match="missing Ed25519 private key"):
        sign_manifest.load_private_key_material(env_var="BUS_MANIFEST_SIGNING_PRIVATE_KEY", file_path=None)


def test_invalid_private_key_fails_cleanly():
    with pytest.raises(sign_manifest.ManifestSigningError, match="invalid Ed25519 private key"):
        sign_manifest.load_ed25519_private_key("not base64 !")


def test_private_key_file_pem_input_is_supported(tmp_path):
    private_key = Ed25519PrivateKey.generate()
    private_pem = private_key.private_bytes(
        encoding=Encoding.PEM,
        format=PrivateFormat.PKCS8,
        encryption_algorithm=NoEncryption(),
    )
    key_path = tmp_path / "manifest-signing-key.pem"
    key_path.write_bytes(private_pem)

    loaded = sign_manifest.load_ed25519_private_key(
        sign_manifest.load_private_key_material(env_var=None, file_path=key_path)
    )

    assert isinstance(loaded, Ed25519PrivateKey)
