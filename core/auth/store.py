# SPDX-License-Identifier: AGPL-3.0-or-later
"""Low-level auth state queries for future claimed/unclaimed mode."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.appdb.models import AuthRole, AuthUser, AuthUserRole
from core.auth.permissions import OWNER_ROLE_KEY


@dataclass(frozen=True)
class AuthState:
    user_count: int
    is_claimed: bool
    enabled_owner_exists: bool


def normalize_username(username: str) -> str:
    if not isinstance(username, str):
        raise ValueError("username_required")
    normalized = " ".join(username.strip().casefold().split())
    if not normalized:
        raise ValueError("username_required")
    return normalized


def count_auth_users(db: Session) -> int:
    return int(db.scalar(select(func.count()).select_from(AuthUser)) or 0)


def auth_users_exist(db: Session) -> bool:
    return count_auth_users(db) > 0


def enabled_owner_exists(db: Session) -> bool:
    stmt = (
        select(AuthUser.id)
        .join(AuthUserRole, AuthUserRole.user_id == AuthUser.id)
        .join(AuthRole, AuthRole.id == AuthUserRole.role_id)
        .where(AuthUser.is_enabled.is_(True), AuthRole.key == OWNER_ROLE_KEY)
        .limit(1)
    )
    return db.scalar(stmt) is not None


def get_auth_state(db: Session) -> AuthState:
    user_count = count_auth_users(db)
    return AuthState(
        user_count=user_count,
        is_claimed=user_count > 0,
        enabled_owner_exists=enabled_owner_exists(db),
    )


__all__ = [
    "AuthState",
    "auth_users_exist",
    "count_auth_users",
    "enabled_owner_exists",
    "get_auth_state",
    "normalize_username",
]
