"""Route-local auth dependencies for claimed/unclaimed mode."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from starlette.status import HTTP_401_UNAUTHORIZED, HTTP_403_FORBIDDEN

from core.appdb.engine import get_session
from core.appdb.models import (
    AuthAuditEvent,
    AuthRecoveryCode,
    AuthRole,
    AuthRolePermission,
    AuthSession,
    AuthUser,
    AuthUserRole,
)
from core.auth.permissions import ALL_PERMISSIONS, OWNER_ROLE_KEY
from core.auth.sessions import hash_session_token
from core.auth.store import count_auth_users

_AUTH_MODEL_REGISTRY_ANCHOR = (AuthAuditEvent, AuthRecoveryCode)


@dataclass(frozen=True)
class AuthUserContext:
    mode: str
    user_id: int | None
    username: str
    roles: tuple[str, ...]
    permissions: tuple[str, ...]
    session_id: int | None = None


def _utcnow() -> datetime:
    return datetime.utcnow()


def _missing_auth_tables(exc: OperationalError) -> bool:
    text_error = str(exc).lower()
    return "no such table" in text_error and "auth_users" in text_error


def _auth_user_count(db: Session) -> int:
    try:
        return count_auth_users(db)
    except OperationalError as exc:
        if _missing_auth_tables(exc):
            return 0
        raise


def _unclaimed_context() -> AuthUserContext:
    return AuthUserContext(
        mode="unclaimed",
        user_id=None,
        username="local-system",
        roles=(OWNER_ROLE_KEY,),
        permissions=ALL_PERMISSIONS,
        session_id=None,
    )


def _state_int(value: object) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _session_id_from_state(request: Request) -> int | None:
    state_session = getattr(request.state, "auth_session", None)
    if isinstance(state_session, dict):
        return _state_int(state_session.get("id"))
    return None


def _user_id_from_state(request: Request) -> int | None:
    state_user = getattr(request.state, "auth_user", None)
    if isinstance(state_user, dict):
        return _state_int(state_user.get("id"))
    return None


def _session_from_cookie(db: Session, request: Request) -> AuthSession | None:
    token = request.cookies.get("bus_auth_session")
    if not token:
        return None
    try:
        session_hash = hash_session_token(token)
    except ValueError:
        return None
    return db.scalar(select(AuthSession).where(AuthSession.session_hash == session_hash))


def _valid_session(db: Session, request: Request) -> AuthSession | None:
    session_id = _session_id_from_state(request)
    auth_session = db.get(AuthSession, session_id) if session_id is not None else _session_from_cookie(db, request)
    now = _utcnow()
    if auth_session is None or auth_session.revoked_at is not None:
        return None
    if auth_session.expires_at is None or auth_session.expires_at <= now:
        return None
    return auth_session


def _roles_and_permissions(db: Session, user_id: int) -> tuple[tuple[str, ...], tuple[str, ...]]:
    role_rows = db.execute(
        select(AuthRole.id, AuthRole.key)
        .join(AuthUserRole, AuthUserRole.role_id == AuthRole.id)
        .where(AuthUserRole.user_id == user_id)
    ).all()
    roles = tuple(sorted(str(row[1]) for row in role_rows))
    if OWNER_ROLE_KEY in roles:
        return roles, ALL_PERMISSIONS

    role_ids = [int(row[0]) for row in role_rows]
    if not role_ids:
        return roles, ()
    permissions = tuple(
        sorted(
            {
                str(row[0])
                for row in db.execute(
                    select(AuthRolePermission.permission).where(AuthRolePermission.role_id.in_(role_ids))
                ).all()
            }
        )
    )
    return roles, permissions


def _claimed_context(db: Session, request: Request) -> AuthUserContext:
    auth_session = _valid_session(db, request)
    if auth_session is None:
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail={"error": "auth_required"})

    state_user_id = _user_id_from_state(request)
    if state_user_id is not None and state_user_id != int(auth_session.user_id):
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail={"error": "auth_required"})

    user = db.get(AuthUser, int(auth_session.user_id))
    if user is None or not bool(user.is_enabled):
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail={"error": "auth_required"})

    roles, permissions = _roles_and_permissions(db, int(user.id))
    request.state.auth_mode = "claimed"
    request.state.auth_user = {
        "id": int(user.id),
        "username": str(user.username),
        "username_norm": str(user.username_norm),
    }
    request.state.auth_session = {
        "id": int(auth_session.id),
        "user_id": int(auth_session.user_id),
        "expires_at": auth_session.expires_at.isoformat() if auth_session.expires_at else None,
    }
    return AuthUserContext(
        mode="claimed",
        user_id=int(user.id),
        username=str(user.username),
        roles=roles,
        permissions=permissions,
        session_id=int(auth_session.id),
    )


def require_user(request: Request, db: Session = Depends(get_session)) -> AuthUserContext:
    if getattr(request.state, "auth_mode", None) == "unclaimed":
        return _unclaimed_context()
    user_count = _auth_user_count(db)
    if user_count == 0:
        return _unclaimed_context()
    return _claimed_context(db, request)


def require_permission(permission: str) -> Callable[[AuthUserContext], AuthUserContext]:
    def _dependency(user: AuthUserContext = Depends(require_user)) -> AuthUserContext:
        if permission not in user.permissions:
            raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail={"error": "permission_denied"})
        return user

    _dependency.__name__ = f"require_permission_{permission.replace('.', '_')}"
    return _dependency


__all__ = ["AuthUserContext", "require_permission", "require_user"]
