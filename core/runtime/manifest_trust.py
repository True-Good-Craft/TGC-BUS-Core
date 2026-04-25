# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import base64
import binascii
import json
from typing import Any, Mapping

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

SIGNATURE_ALG = "Ed25519"


class ManifestTrustError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def is_signed_manifest(manifest: Any) -> bool:
    return isinstance(manifest, dict) and "signature" in manifest


def canonicalize_manifest_payload(payload: Any) -> bytes:
    try:
        return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ManifestTrustError("invalid_payload", "Manifest payload is not canonical JSON.") from exc


def verify_manifest_envelope(
    envelope: Any,
    *,
    trusted_public_keys: Mapping[str, Ed25519PublicKey | bytes],
) -> dict[str, Any]:
    if not _is_signature_envelope(envelope):
        raise ManifestTrustError("missing_signature", "Signed manifest envelope is required.")

    payload = envelope.get("payload")
    if not isinstance(payload, dict):
        raise ManifestTrustError("invalid_payload", "Manifest payload must be an object.")

    signature = envelope.get("signature")
    _verify_signature_metadata(
        signature,
        trusted_public_keys=trusted_public_keys,
        signed_payload=canonicalize_manifest_payload(payload),
    )

    return payload


def verify_embedded_manifest_signature(
    manifest: Any,
    *,
    trusted_public_keys: Mapping[str, Ed25519PublicKey | bytes],
) -> dict[str, Any]:
    if not _is_embedded_signed_manifest(manifest):
        raise ManifestTrustError("missing_signature", "Embedded manifest signature is required.")

    unsigned_manifest = dict(manifest)
    signature = unsigned_manifest.pop("signature")
    _verify_signature_metadata(
        signature,
        trusted_public_keys=trusted_public_keys,
        signed_payload=canonicalize_manifest_payload(unsigned_manifest),
    )
    return unsigned_manifest


def unwrap_manifest(
    manifest: Any,
    *,
    trusted_public_keys: Mapping[str, Ed25519PublicKey | bytes],
    require_signature: bool = False,
) -> Any:
    if _is_signature_envelope(manifest):
        return verify_manifest_envelope(manifest, trusted_public_keys=trusted_public_keys)
    if _is_embedded_signed_manifest(manifest):
        return verify_embedded_manifest_signature(manifest, trusted_public_keys=trusted_public_keys)
    if require_signature:
        raise ManifestTrustError("missing_signature", "Signed manifest envelope is required.")
    return manifest


def _is_signature_envelope(manifest: Any) -> bool:
    return isinstance(manifest, dict) and "payload" in manifest and "signature" in manifest


def _is_embedded_signed_manifest(manifest: Any) -> bool:
    return isinstance(manifest, dict) and "signature" in manifest and "payload" not in manifest


def _verify_signature_metadata(
    signature: Any,
    *,
    trusted_public_keys: Mapping[str, Ed25519PublicKey | bytes],
    signed_payload: bytes,
) -> None:
    if not isinstance(signature, dict):
        raise ManifestTrustError("invalid_signature", "Manifest signature metadata must be an object.")

    alg = signature.get("alg")
    if alg != SIGNATURE_ALG:
        raise ManifestTrustError("unsupported_alg", "Manifest signature algorithm is not supported.")

    key_id = signature.get("key_id")
    if not isinstance(key_id, str) or not key_id:
        raise ManifestTrustError("unknown_key_id", "Manifest signature key_id is not trusted.")

    public_key = trusted_public_keys.get(key_id)
    if public_key is None:
        raise ManifestTrustError("unknown_key_id", "Manifest signature key_id is not trusted.")

    sig = signature.get("sig")
    if not isinstance(sig, str) or not sig:
        raise ManifestTrustError("invalid_signature", "Manifest signature must be base64.")

    try:
        signature_bytes = base64.b64decode(sig.encode("ascii"), validate=True)
    except (UnicodeEncodeError, binascii.Error) as exc:
        raise ManifestTrustError("invalid_signature", "Manifest signature must be base64.") from exc

    verifier = _load_ed25519_public_key(public_key)
    try:
        verifier.verify(signature_bytes, signed_payload)
    except InvalidSignature as exc:
        raise ManifestTrustError("bad_signature", "Manifest signature verification failed.") from exc


def _load_ed25519_public_key(public_key: Ed25519PublicKey | bytes) -> Ed25519PublicKey:
    if isinstance(public_key, Ed25519PublicKey):
        return public_key
    if isinstance(public_key, bytes):
        try:
            return Ed25519PublicKey.from_public_bytes(public_key)
        except ValueError as exc:
            raise ManifestTrustError("invalid_public_key", "Trusted manifest public key is invalid.") from exc
    raise ManifestTrustError("invalid_public_key", "Trusted manifest public key is invalid.")
