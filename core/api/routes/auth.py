# SPDX-License-Identifier: AGPL-3.0-or-later
"""DB-backed auth account lifecycle routes.

These routes introduce the future claimed-owner auth surface without changing the
legacy BUS Core runtime session guard or `/session/token` compatibility path.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.appdb.engine import get_session
from core.appdb.models import (
    AuthRecoveryCode,
    AuthRole,
    AuthRolePermission,
    AuthSession,
    AuthUser,
    AuthUserRole,
)
from core.auth.audit import create_audit_event
from core.auth.passwords import SCRYPT_SCHEME, hash_password, verify_password
from core.auth.permissions import OWNER_ROLE_KEY, default_role_bundles
from core.auth.sessions import generate_session_token, hash_session_token
from core.auth.store import count_auth_users, normalize_username

router = APIRouter(prefix="/auth", tags=["auth"])

AUTH_SESSION_COOKIE = "bus_auth_session"
AUTH_SESSION_DAYS = 30
RECOVERY_CODE_COUNT = 10


class SetupOwnerRequest(BaseModel):
    username: str
    password: str
    display_name: str | None = None
    email: str | None = None
    business_name: str | None = None


class LoginRequest(BaseModel):
    username: str
    password: str


def _utcnow() -> datetime:
    return datetime.utcnow()


def _safe_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _cookie_security(request: Request) -> tuple[str, bool]:
    state = getattr(request.app.state, "app_state", None)
    settings = getattr(state, "settings", None)
    same_site = str(getattr(settings, "same_site", "lax") or "lax").lower()
    secure_cookie = bool(getattr(settings, "secure_cookie", False))
    return same_site, secure_cookie


def _set_auth_cookie(response: Response, request: Request, token: str) -> None:
    same_site, secure_cookie = _cookie_security(request)
    response.set_cookie(
        key=AUTH_SESSION_COOKIE,
        value=token,
        httponly=True,
        samesite=same_site,
        secure=secure_cookie,
        path="/",
    )


def _clear_auth_cookie(response: Response, request: Request) -> None:
    same_site, secure_cookie = _cookie_security(request)
    response.delete_cookie(
        key=AUTH_SESSION_COOKIE,
        path="/",
        samesite=same_site,
        secure=secure_cookie,
    )


def _recovery_code() -> str:
    raw = base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")
    return "-".join(raw[index : index + 4] for index in range(0, len(raw), 4))


def _hash_recovery_code(code: str) -> str:
    digest = hashlib.sha256(code.encode("utf-8")).hexdigest()
    return f"recovery-sha256-v1${digest}"


def _seed_system_roles(db: Session) -> dict[str, AuthRole]:
    roles: dict[str, AuthRole] = {}
    for role_key, permissions in default_role_bundles().items():
        role = db.scalar(select(AuthRole).where(AuthRole.key == role_key))
        if role is None:
            role = AuthRole(key=role_key, name=role_key.replace("_", " ").title(), is_system=True)
            db.add(role)
            db.flush()
        roles[role_key] = role

        existing_permissions = {
            row[0]
            for row in db.execute(
                select(AuthRolePermission.permission).where(AuthRolePermission.role_id == role.id)
            ).all()
        }
        for permission in permissions:
            if permission not in existing_permissions:
                db.add(AuthRolePermission(role_id=role.id, permission=permission))
    db.flush()
    return roles


def _user_roles_and_permissions(db: Session, user_id: int) -> tuple[list[str], list[str]]:
    role_rows = db.execute(
        select(AuthRole.id, AuthRole.key)
        .join(AuthUserRole, AuthUserRole.role_id == AuthRole.id)
        .where(AuthUserRole.user_id == user_id)
    ).all()
    roles = sorted(str(row[1]) for row in role_rows)
    role_ids = [int(row[0]) for row in role_rows]
    if not role_ids:
        return roles, []
    permissions = sorted(
        {
            str(row[0])
            for row in db.execute(
                select(AuthRolePermission.permission).where(AuthRolePermission.role_id.in_(role_ids))
            ).all()
        }
    )
    return roles, permissions


def _user_payload(db: Session, user: AuthUser) -> dict[str, Any]:
    roles, permissions = _user_roles_and_permissions(db, int(user.id))
    return {
        "id": int(user.id),
        "username": str(user.username),
        "display_name": user.display_name,
        "roles": roles,
        "permissions": permissions,
    }


def _current_session(db: Session, request: Request) -> tuple[AuthSession | None, AuthUser | None]:
    token = request.cookies.get(AUTH_SESSION_COOKIE)
    if not token:
        return None, None
    try:
        session_hash = hash_session_token(token)
    except ValueError:
        return None, None
    now = _utcnow()
    auth_session = db.scalar(
        select(AuthSession).where(
            AuthSession.session_hash == session_hash,
            AuthSession.revoked_at.is_(None),
            AuthSession.expires_at > now,
        )
    )
    if auth_session is None:
        return None, None
    user = db.get(AuthUser, auth_session.user_id)
    if user is None or not bool(user.is_enabled):
        return None, None
    auth_session.last_seen_at = now
    return auth_session, user


def _create_session(db: Session, user: AuthUser, request: Request) -> tuple[str, AuthSession]:
    token = generate_session_token()
    auth_session = AuthSession(
        session_hash=hash_session_token(token),
        user_id=int(user.id),
        created_at=_utcnow(),
        expires_at=_utcnow() + timedelta(days=AUTH_SESSION_DAYS),
        user_agent_hash=_hash_user_agent(request),
    )
    db.add(auth_session)
    db.flush()
    return token, auth_session


def _hash_user_agent(request: Request) -> str | None:
    user_agent = request.headers.get("user-agent")
    if not user_agent:
        return None
    return "sha256-v1$" + hashlib.sha256(user_agent.encode("utf-8")).hexdigest()


def _auth_state_payload(db: Session, request: Request) -> dict[str, Any]:
    user_count = count_auth_users(db)
    if user_count == 0:
        return {
            "mode": "unclaimed",
            "owner_exists": False,
            "setup_available": True,
            "login_required": False,
            "current_user": None,
        }

    _, user = _current_session(db, request)
    return {
        "mode": "claimed",
        "owner_exists": True,
        "setup_available": False,
        "login_required": user is None,
        "current_user": _user_payload(db, user) if user is not None else None,
    }


def _audit_login_failed(db: Session, request: Request, username_norm: str | None, reason: str) -> None:
    create_audit_event(
        db,
        action="auth.login_failed",
        request_id=getattr(request.state, "req_id", None),
        detail={"username_norm": username_norm or "", "reason": reason},
    )


@router.get("/state")
def get_auth_state_route(request: Request, db: Session = Depends(get_session)) -> dict[str, Any]:
    return _auth_state_payload(db, request)


@router.post("/setup-owner")
def setup_owner(
    payload: SetupOwnerRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_session),
) -> dict[str, Any]:
    if count_auth_users(db) > 0:
        raise HTTPException(status_code=409, detail={"error": "owner_setup_unavailable"})

    try:
        username_norm = normalize_username(payload.username)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": "username_required"}) from exc
    if not payload.password or not payload.password.strip():
        raise HTTPException(status_code=400, detail={"error": "password_required"})

    roles = _seed_system_roles(db)
    owner_role = roles[OWNER_ROLE_KEY]
    password_hash = hash_password(payload.password)
    user = AuthUser(
        username=payload.username.strip(),
        username_norm=username_norm,
        display_name=_safe_text(payload.display_name),
        email=_safe_text(payload.email),
        password_hash=password_hash,
        password_scheme=SCRYPT_SCHEME,
        is_enabled=True,
        must_change_password=False,
    )
    db.add(user)
    db.flush()
    db.add(AuthUserRole(user_id=int(user.id), role_id=int(owner_role.id)))

    recovery_codes = [_recovery_code() for _ in range(RECOVERY_CODE_COUNT)]
    for code in recovery_codes:
        db.add(AuthRecoveryCode(user_id=int(user.id), code_hash=_hash_recovery_code(code)))

    session_token, _ = _create_session(db, user, request)
    user.last_login_at = _utcnow()
    create_audit_event(
        db,
        action="auth.owner_setup",
        actor_user_id=int(user.id),
        target_type="user",
        target_id=str(user.id),
        request_id=getattr(request.state, "req_id", None),
        detail={"business_name": _safe_text(payload.business_name) or ""},
    )
    db.commit()
    _set_auth_cookie(response, request, session_token)
    return {
        "ok": True,
        "mode": "claimed",
        "user": {
            "id": int(user.id),
            "username": str(user.username),
            "roles": [OWNER_ROLE_KEY],
        },
        "recovery_codes": recovery_codes,
    }


@router.post("/login")
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_session),
) -> dict[str, Any]:
    if count_auth_users(db) == 0:
        raise HTTPException(status_code=409, detail={"error": "setup_required"})
    try:
        username_norm = normalize_username(payload.username)
    except ValueError:
        username_norm = None

    user = None
    if username_norm:
        user = db.scalar(select(AuthUser).where(AuthUser.username_norm == username_norm))
    if user is None or not verify_password(payload.password, str(getattr(user, "password_hash", ""))):
        _audit_login_failed(db, request, username_norm, "invalid_credentials")
        db.commit()
        raise HTTPException(status_code=401, detail={"error": "invalid_credentials"})
    if not bool(user.is_enabled):
        _audit_login_failed(db, request, username_norm, "disabled_user")
        db.commit()
        raise HTTPException(status_code=403, detail={"error": "user_disabled"})

    session_token, _ = _create_session(db, user, request)
    user.last_login_at = _utcnow()
    create_audit_event(
        db,
        action="auth.login_success",
        actor_user_id=int(user.id),
        target_type="user",
        target_id=str(user.id),
        request_id=getattr(request.state, "req_id", None),
    )
    db.commit()
    _set_auth_cookie(response, request, session_token)
    return {"ok": True, "user": _user_payload(db, user)}


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_session)) -> dict[str, bool]:
    auth_session, user = _current_session(db, request)
    if auth_session is not None:
        auth_session.revoked_at = _utcnow()
        if user is not None:
            create_audit_event(
                db,
                action="auth.logout",
                actor_user_id=int(user.id),
                target_type="session",
                target_id=str(auth_session.id),
                request_id=getattr(request.state, "req_id", None),
            )
        db.commit()
    _clear_auth_cookie(response, request)
    return {"ok": True}


@router.get("/me")
def me(request: Request, db: Session = Depends(get_session)) -> dict[str, Any]:
    if count_auth_users(db) == 0:
        return {
            "mode": "unclaimed",
            "current_user": None,
        }
    _, user = _current_session(db, request)
    if user is None:
        raise HTTPException(status_code=401, detail={"error": "auth_required"})
    return {
        "mode": "claimed",
        "current_user": _user_payload(db, user),
    }


__all__ = [
    "AUTH_SESSION_COOKIE",
    "RECOVERY_CODE_COUNT",
    "router",
]
