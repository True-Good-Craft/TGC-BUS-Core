# SPDX-License-Identifier: AGPL-3.0-or-later
"""Password hashing helpers for future DB-backed auth."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

SCRYPT_SCHEME = "scrypt-v1"
SCRYPT_N = 16384
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_DKLEN = 32
SALT_BYTES = 16


def _b64encode(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _b64decode(value: str) -> bytes:
    return base64.b64decode(value.encode("ascii"), validate=True)


def hash_password(password: str) -> str:
    if not isinstance(password, str) or not password:
        raise ValueError("password_required")
    salt = secrets.token_bytes(SALT_BYTES)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        dklen=SCRYPT_DKLEN,
    )
    return (
        f"{SCRYPT_SCHEME}$n={SCRYPT_N}$r={SCRYPT_R}$p={SCRYPT_P}"
        f"$salt={_b64encode(salt)}$hash={_b64encode(digest)}"
    )


def password_scheme(encoded_hash: str) -> str:
    return encoded_hash.split("$", 1)[0]


def _parse_scrypt_hash(encoded_hash: str) -> tuple[int, int, int, bytes, bytes] | None:
    parts = encoded_hash.split("$")
    if len(parts) != 6 or parts[0] != SCRYPT_SCHEME:
        return None
    values: dict[str, str] = {}
    for part in parts[1:]:
        if "=" not in part:
            return None
        key, value = part.split("=", 1)
        values[key] = value
    try:
        n = int(values["n"])
        r = int(values["r"])
        p = int(values["p"])
        salt = _b64decode(values["salt"])
        expected = _b64decode(values["hash"])
    except (KeyError, TypeError, ValueError):
        return None
    if n <= 1 or r <= 0 or p <= 0 or not salt or not expected:
        return None
    return n, r, p, salt, expected


def verify_password(password: str, encoded_hash: str) -> bool:
    if not isinstance(password, str) or not isinstance(encoded_hash, str):
        return False
    parsed = _parse_scrypt_hash(encoded_hash)
    if parsed is None:
        return False
    n, r, p, salt, expected = parsed
    try:
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=n,
            r=r,
            p=p,
            dklen=len(expected),
        )
    except (TypeError, ValueError):
        return False
    return hmac.compare_digest(actual, expected)


__all__ = [
    "SCRYPT_SCHEME",
    "hash_password",
    "password_scheme",
    "verify_password",
]
