# SPDX-License-Identifier: AGPL-3.0-or-later
"""Session token helpers for future DB-backed auth sessions."""

from __future__ import annotations

import hashlib
import secrets

SESSION_HASH_SCHEME = "sha256-v1"


def generate_session_token() -> str:
    return secrets.token_urlsafe(32)


def hash_session_token(token: str) -> str:
    if not isinstance(token, str) or not token:
        raise ValueError("session_token_required")
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    return f"{SESSION_HASH_SCHEME}${digest}"


__all__ = ["SESSION_HASH_SCHEME", "generate_session_token", "hash_session_token"]
