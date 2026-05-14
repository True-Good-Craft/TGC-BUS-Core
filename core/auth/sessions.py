# SPDX-License-Identifier: AGPL-3.0-or-later
"""Session token helpers for future DB-backed auth sessions."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Any

SESSION_HASH_SCHEME = "sha256-v1"
AUTH_SESSION_IDLE_TIMEOUT_MINUTES = 720
AUTH_SESSION_MAX_AGE_DAYS = 30
AUTH_SESSION_TOUCH_INTERVAL_MINUTES = 5


def generate_session_token() -> str:
    return secrets.token_urlsafe(32)


def hash_session_token(token: str) -> str:
    if not isinstance(token, str) or not token:
        raise ValueError("session_token_required")
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    return f"{SESSION_HASH_SCHEME}${digest}"


def session_is_valid(auth_session: Any, now: datetime) -> bool:
    if auth_session is None or auth_session.revoked_at is not None:
        return False
    if auth_session.expires_at is None or auth_session.expires_at <= now:
        return False
    if auth_session.created_at is not None and auth_session.created_at <= now - timedelta(days=AUTH_SESSION_MAX_AGE_DAYS):
        return False
    last_seen = auth_session.last_seen_at or auth_session.created_at
    if last_seen is not None and last_seen <= now - timedelta(minutes=AUTH_SESSION_IDLE_TIMEOUT_MINUTES):
        return False
    return True


def session_should_touch(auth_session: Any, now: datetime) -> bool:
    last_seen = auth_session.last_seen_at
    if last_seen is None:
        return True
    return last_seen <= now - timedelta(minutes=AUTH_SESSION_TOUCH_INTERVAL_MINUTES)


__all__ = [
    "AUTH_SESSION_IDLE_TIMEOUT_MINUTES",
    "AUTH_SESSION_MAX_AGE_DAYS",
    "AUTH_SESSION_TOUCH_INTERVAL_MINUTES",
    "SESSION_HASH_SCHEME",
    "generate_session_token",
    "hash_session_token",
    "session_is_valid",
    "session_should_touch",
]
