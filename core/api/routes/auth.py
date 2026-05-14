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
    AuthRecoveryAttempt,
    AuthRole,
    AuthRolePermission,
    AuthSession,
    AuthUser,
    AuthUserRole,
)
from core.auth.audit import create_audit_event
from core.auth.dependencies import AuthUserContext, require_permission
from core.auth.passwords import SCRYPT_SCHEME, hash_password, validate_password_policy, verify_password
from core.auth.permissions import OWNER_ROLE_KEY, PERMISSION_USERS_MANAGE, default_role_bundles
from core.auth.sessions import (
    AUTH_SESSION_MAX_AGE_DAYS,
    generate_session_token,
    hash_session_token,
    session_is_valid,
    session_should_touch,
)
from core.auth.store import count_auth_users, normalize_username

router = APIRouter(prefix="/auth", tags=["auth"])

AUTH_SESSION_COOKIE = "bus_auth_session"
AUTH_SESSION_DAYS = AUTH_SESSION_MAX_AGE_DAYS
RECOVERY_CODE_COUNT = 10
RECOVERY_RATE_LIMIT_MAX_FAILURES = 5
RECOVERY_RATE_LIMIT_WINDOW_MINUTES = 15
RECOVERY_GENERIC_ERROR = {"error": "recovery_failed"}


class SetupOwnerRequest(BaseModel):
    username: str
    password: str
    display_name: str | None = None
    email: str | None = None
    business_name: str | None = None


class LoginRequest(BaseModel):
    username: str
    password: str


class RecoverRequest(BaseModel):
    username: str
    recovery_code: str
    new_password: str


class RegenerateRecoveryCodesRequest(BaseModel):
    user_id: int | None = None


def _utcnow() -> datetime:
    return datetime.utcnow()


def _safe_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _require_valid_password(password: str) -> None:
    try:
        validate_password_policy(password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": str(exc)}) from exc


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


def _normalize_recovery_code(code: str) -> str:
    return str(code or "").strip().upper()


def _hash_recovery_code(code: str) -> str:
    digest = hashlib.sha256(_normalize_recovery_code(code).encode("utf-8")).hexdigest()
    return f"recovery-sha256-v1${digest}"


def _client_key(request: Request) -> str:
    host = request.client.host if request.client else "unknown"
    user_agent_hash = _hash_user_agent(request) or "no-agent"
    return "sha256-v1$" + hashlib.sha256(f"{host}|{user_agent_hash}".encode("utf-8")).hexdigest()


def _rate_limit_row(db: Session, username_norm: str, client_key: str) -> AuthRecoveryAttempt:
    row = db.scalar(
        select(AuthRecoveryAttempt).where(
            AuthRecoveryAttempt.username_norm == username_norm,
            AuthRecoveryAttempt.client_key == client_key,
        )
    )
    if row is None:
        row = AuthRecoveryAttempt(username_norm=username_norm, client_key=client_key)
        db.add(row)
        db.flush()
    return row


def _recovery_locked(row: AuthRecoveryAttempt, now: datetime) -> bool:
    return row.locked_until is not None and row.locked_until > now


def _record_recovery_failure(db: Session, username_norm: str, client_key: str, now: datetime) -> None:
    row = _rate_limit_row(db, username_norm, client_key)
    window_start = now - timedelta(minutes=RECOVERY_RATE_LIMIT_WINDOW_MINUTES)
    if row.first_failed_at is None or row.first_failed_at < window_start:
        row.first_failed_at = now
        row.failed_count = 0
        row.locked_until = None
    row.failed_count = int(row.failed_count or 0) + 1
    if row.failed_count >= RECOVERY_RATE_LIMIT_MAX_FAILURES:
        row.locked_until = now + timedelta(minutes=RECOVERY_RATE_LIMIT_WINDOW_MINUTES)


def _clear_recovery_failures(db: Session, username_norm: str, client_key: str) -> None:
    row = db.scalar(
        select(AuthRecoveryAttempt).where(
            AuthRecoveryAttempt.username_norm == username_norm,
            AuthRecoveryAttempt.client_key == client_key,
        )
    )
    if row is None:
        return
    row.failed_count = 0
    row.first_failed_at = None
    row.locked_until = None


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
    auth_session = db.scalar(select(AuthSession).where(AuthSession.session_hash == session_hash))
    if not session_is_valid(auth_session, now):
        return None, None
    user = db.get(AuthUser, auth_session.user_id)
    if user is None or not bool(user.is_enabled):
        return None, None
    if session_should_touch(auth_session, now):
        auth_session.last_seen_at = now
    return auth_session, user


def _create_session(db: Session, user: AuthUser, request: Request) -> tuple[str, AuthSession]:
    token = generate_session_token()
    auth_session = AuthSession(
        session_hash=hash_session_token(token),
        user_id=int(user.id),
        created_at=_utcnow(),
        expires_at=_utcnow() + timedelta(days=AUTH_SESSION_MAX_AGE_DAYS),
        last_seen_at=_utcnow(),
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

    auth_session, user = _current_session(db, request)
    if auth_session is not None:
        db.commit()
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


def _recovery_username_key(username: str) -> tuple[str, bool]:
    try:
        return normalize_username(username), True
    except ValueError:
        digest = hashlib.sha256(str(username or "").strip().casefold().encode("utf-8")).hexdigest()
        return f"invalid${digest}", False


def _revoke_user_sessions(db: Session, user_id: int) -> int:
    now = _utcnow()
    sessions = db.execute(
        select(AuthSession).where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
    ).scalars().all()
    for auth_session in sessions:
        auth_session.revoked_at = now
    return len(sessions)


def _new_recovery_codes(db: Session, user_id: int) -> list[str]:
    recovery_codes = [_recovery_code() for _ in range(RECOVERY_CODE_COUNT)]
    for code in recovery_codes:
        db.add(AuthRecoveryCode(user_id=user_id, code_hash=_hash_recovery_code(code)))
    return recovery_codes


def _claimed_actor_id(actor: AuthUserContext) -> int:
    if actor.mode != "claimed" or actor.user_id is None:
        raise HTTPException(status_code=409, detail={"error": "claimed_mode_required"})
    return int(actor.user_id)


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
    _require_valid_password(payload.password)

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


@router.post("/recover")
def recover(
    payload: RecoverRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_session),
) -> dict[str, Any]:
    if count_auth_users(db) == 0:
        raise HTTPException(status_code=409, detail={"error": "claimed_mode_required"})
    username_norm, username_valid = _recovery_username_key(payload.username)
    client_key = _client_key(request)
    now = _utcnow()
    rate_row = _rate_limit_row(db, username_norm, client_key)
    if _recovery_locked(rate_row, now):
        db.commit()
        raise HTTPException(status_code=401, detail=RECOVERY_GENERIC_ERROR)
    _require_valid_password(payload.new_password)

    user = db.scalar(select(AuthUser).where(AuthUser.username_norm == username_norm)) if username_valid else None
    recovery = None
    if user is not None and bool(user.is_enabled):
        recovery = db.scalar(
            select(AuthRecoveryCode).where(
                AuthRecoveryCode.user_id == int(user.id),
                AuthRecoveryCode.code_hash == _hash_recovery_code(payload.recovery_code),
                AuthRecoveryCode.used_at.is_(None),
            )
        )
    if user is None or not bool(getattr(user, "is_enabled", False)) or recovery is None:
        _record_recovery_failure(db, username_norm, client_key, now)
        db.commit()
        raise HTTPException(status_code=401, detail=RECOVERY_GENERIC_ERROR)

    recovery.used_at = now
    user.password_hash = hash_password(payload.new_password)
    user.password_scheme = SCRYPT_SCHEME
    user.must_change_password = False
    revoked_count = _revoke_user_sessions(db, int(user.id))
    _clear_recovery_failures(db, username_norm, client_key)
    create_audit_event(
        db,
        action="auth.recovery_used",
        actor_user_id=int(user.id),
        target_type="user",
        target_id=str(user.id),
        request_id=getattr(request.state, "req_id", None),
        detail={"revoked_sessions": revoked_count},
    )
    db.commit()
    _clear_auth_cookie(response, request)
    return {"ok": True, "login_required": True}


@router.post("/recovery-codes/regenerate")
def regenerate_recovery_codes(
    payload: RegenerateRecoveryCodesRequest,
    request: Request,
    db: Session = Depends(get_session),
    actor: AuthUserContext = Depends(require_permission(PERMISSION_USERS_MANAGE)),
) -> dict[str, Any]:
    if count_auth_users(db) == 0:
        raise HTTPException(status_code=409, detail={"error": "claimed_mode_required"})
    actor_user_id = _claimed_actor_id(actor)
    target_user_id = int(payload.user_id) if payload.user_id is not None else actor_user_id
    user = db.get(AuthUser, target_user_id)
    if user is None:
        raise HTTPException(status_code=404, detail={"error": "user_not_found"})
    now = _utcnow()
    old_codes = db.execute(
        select(AuthRecoveryCode).where(
            AuthRecoveryCode.user_id == target_user_id,
            AuthRecoveryCode.used_at.is_(None),
        )
    ).scalars().all()
    for code in old_codes:
        code.used_at = now
    recovery_codes = _new_recovery_codes(db, target_user_id)
    create_audit_event(
        db,
        action="auth.recovery_codes_regenerated",
        actor_user_id=actor_user_id,
        target_type="user",
        target_id=str(target_user_id),
        request_id=getattr(request.state, "req_id", None),
        detail={"invalidated_unused": len(old_codes), "generated": RECOVERY_CODE_COUNT},
    )
    db.commit()
    return {"ok": True, "user_id": target_user_id, "recovery_codes": recovery_codes}


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
    auth_session, user = _current_session(db, request)
    if user is None:
        raise HTTPException(status_code=401, detail={"error": "auth_required"})
    if auth_session is not None:
        db.commit()
    return {
        "mode": "claimed",
        "current_user": _user_payload(db, user),
    }


__all__ = [
    "AUTH_SESSION_COOKIE",
    "RECOVERY_CODE_COUNT",
    "router",
]
