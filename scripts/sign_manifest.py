# SPDX-License-Identifier: AGPL-3.0-or-later
"""Sign a BUS Core manifest for a local/manual release ceremony.

Private signing keys must live outside this repository. In automation, provide
the key from a GitHub Actions secret; for local use, pass an external key file.
Accepted private key encodings are unencrypted PEM PKCS8 Ed25519 text or base64
raw 32-byte Ed25519 seed material. Before production enforcement is enabled,
the matching public key must be pinned in Core. This helper only writes a signed
manifest JSON file; it does not publish, upload, or mutate release state.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import json
import sys
from pathlib import Path
from typing import Any

# Bootstrap repo root onto sys.path to allow core.* imports when run directly from shell or CI.
_REPO_ROOT = Path(__file__).parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import load_pem_private_key, load_pem_public_key

from core.runtime.manifest_trust import (
    SIGNATURE_ALG,
    canonicalize_manifest_payload,
    verify_embedded_manifest_signature,
)

DEFAULT_PRIVATE_KEY_ENV = "BUS_MANIFEST_SIGNING_PRIVATE_KEY"


class ManifestSigningError(ValueError):
    pass


def sign_manifest_dict(manifest: dict[str, Any], *, key_id: str, private_key: Ed25519PrivateKey) -> dict[str, Any]:
    unsigned_manifest = dict(manifest)
    unsigned_manifest.pop("signature", None)
    signature = private_key.sign(canonicalize_manifest_payload(unsigned_manifest))
    signed_manifest = dict(unsigned_manifest)
    signed_manifest["signature"] = {
        "alg": SIGNATURE_ALG,
        "key_id": key_id,
        "sig": base64.b64encode(signature).decode("ascii"),
    }
    return signed_manifest


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ManifestSigningError(f"failed to read manifest: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ManifestSigningError("manifest must be valid JSON") from exc
    if not isinstance(manifest, dict):
        raise ManifestSigningError("manifest must be a JSON object")
    return manifest


def write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_private_key_material(*, env_var: str | None, file_path: Path | None) -> str:
    if file_path is not None:
        try:
            return file_path.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise ManifestSigningError(f"failed to read private key file: {file_path}") from exc
    if env_var:
        import os

        value = os.environ.get(env_var)
        if value:
            return value.strip()
    raise ManifestSigningError("missing Ed25519 private key")


def load_ed25519_private_key(material: str) -> Ed25519PrivateKey:
    if not material:
        raise ManifestSigningError("missing Ed25519 private key")
    if material.startswith("-----BEGIN"):
        try:
            private_key = load_pem_private_key(material.encode("utf-8"), password=None)
        except Exception as exc:
            raise ManifestSigningError("invalid Ed25519 private key") from exc
        if isinstance(private_key, Ed25519PrivateKey):
            return private_key
        raise ManifestSigningError("private key must be Ed25519")

    try:
        private_bytes = base64.b64decode(material.encode("ascii"), validate=True)
        return Ed25519PrivateKey.from_private_bytes(private_bytes)
    except (UnicodeEncodeError, binascii.Error, ValueError) as exc:
        raise ManifestSigningError("invalid Ed25519 private key") from exc


def load_ed25519_public_key(material: str) -> Ed25519PublicKey:
    if not material:
        raise ManifestSigningError("missing Ed25519 public key")
    if material.startswith("-----BEGIN"):
        try:
            public_key = load_pem_public_key(material.encode("utf-8"))
        except Exception as exc:
            raise ManifestSigningError("invalid Ed25519 public key") from exc
        if isinstance(public_key, Ed25519PublicKey):
            return public_key
        raise ManifestSigningError("public key must be Ed25519")

    try:
        public_bytes = base64.b64decode(material.encode("ascii"), validate=True)
        return Ed25519PublicKey.from_public_bytes(public_bytes)
    except (UnicodeEncodeError, binascii.Error, ValueError) as exc:
        raise ManifestSigningError("invalid Ed25519 public key") from exc


def _read_optional_key_material(*, env_var: str | None, file_path: Path | None) -> str | None:
    if file_path is not None:
        try:
            return file_path.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise ManifestSigningError(f"failed to read public key file: {file_path}") from exc
    if env_var:
        import os

        value = os.environ.get(env_var)
        if value:
            return value.strip()
    return None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Sign a BUS Core update manifest with an embedded Ed25519 signature. "
            "Private keys must be supplied from a secret environment variable or external file; "
            "this script does not publish manifests."
        )
    )
    parser.add_argument("input", type=Path, help="Path to unsigned manifest JSON.")
    parser.add_argument("output", type=Path, help="Path to write signed manifest JSON.")
    parser.add_argument("--key-id", required=True, help="Manifest signing key ID to embed.")
    parser.add_argument(
        "--private-key-env",
        default=DEFAULT_PRIVATE_KEY_ENV,
        help=(
            "Environment variable containing Ed25519 private key material. "
            "Accepted formats: PEM PKCS8 text or base64 raw 32-byte private key."
        ),
    )
    parser.add_argument(
        "--private-key-file",
        type=Path,
        help="External file containing PEM PKCS8 or base64 raw 32-byte Ed25519 private key.",
    )
    parser.add_argument(
        "--public-key-env",
        help="Optional environment variable containing PEM or base64 raw 32-byte Ed25519 public key for verification.",
    )
    parser.add_argument(
        "--public-key-file",
        type=Path,
        help="Optional file containing PEM or base64 raw 32-byte Ed25519 public key for verification.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        manifest = load_manifest(args.input)
        private_material = load_private_key_material(env_var=args.private_key_env, file_path=args.private_key_file)
        private_key = load_ed25519_private_key(private_material)
        signed_manifest = sign_manifest_dict(manifest, key_id=args.key_id, private_key=private_key)

        public_material = _read_optional_key_material(env_var=args.public_key_env, file_path=args.public_key_file)
        if public_material is not None:
            public_key = load_ed25519_public_key(public_material)
            verify_embedded_manifest_signature(signed_manifest, trusted_public_keys={args.key_id: public_key})

        write_manifest(args.output, signed_manifest)
    except Exception as exc:
        print(f"sign_manifest: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
