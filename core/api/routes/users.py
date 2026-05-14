"""Claimed-mode user, role, session, and audit management routes."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.appdb.engine import get_session
from core.appdb.models import (
    AuthAuditEvent,
    AuthRole,
    AuthRolePermission,
    AuthSession,
    AuthUser,
    AuthUserRole,
)
from core.auth.audit import create_audit_event
from core.auth.dependencies import AuthUserContext, require_permission
from core.auth.management import AuthInvariantError, assert_not_last_enabled_owner, ensure_system_roles
from core.auth.passwords import SCRYPT_SCHEME, hash_password, validate_password_policy
from core.auth.permissions import (
    PERMISSION_AUDIT_READ,
    PERMISSION_SESSIONS_MANAGE,
    PERMISSION_USERS_MANAGE,
    PERMISSION_USERS_READ,
    VIEWER_ROLE_KEY,
)
from core.auth.store import normalize_username
from core.config.writes import require_writes
from tgc.security import require_token_ctx

router = APIRouter(tags=["users"])


class UserCreateRequest(BaseModel):
    username: str
    password: str
    display_name: str | None = None
    email: str | None = None
    roles: list[str] = Field(default_factory=list)
    must_change_password: bool = True


class UserUpdateRequest(BaseModel):
    display_name: str | None = None
    email: str | None = None
    is_enabled: bool | None = None
    must_change_password: bool | None = None


class PasswordResetRequest(BaseModel):
    new_password: str
    must_change_password: bool = True
    revoke_sessions: bool = True


class UserRolesRequest(BaseModel):
    roles: list[str]


def _utcnow() -> datetime:
    return datetime.utcnow()


def _claimed_actor(user: AuthUserContext) -> int:
    if user.mode != "claimed" or user.user_id is None:
        raise HTTPException(status_code=409, detail={"error": "claimed_mode_required"})
    return int(user.user_id)


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


def _fields_set(model: BaseModel) -> set[str]:
    if hasattr(model, "model_fields_set"):
        return set(model.model_fields_set)
    return set(getattr(model, "__fields_set__", set()))


def _require_user(db: Session, user_id: int) -> AuthUser:
    user = db.get(AuthUser, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail={"error": "user_not_found"})
    return user


def _role_keys_for_user(db: Session, user_id: int) -> list[str]:
    return sorted(
        str(row[0])
        for row in db.execute(
            select(AuthRole.key)
            .join(AuthUserRole, AuthUserRole.role_id == AuthRole.id)
            .where(AuthUserRole.user_id == user_id)
        ).all()
    )


def _permissions_for_role(db: Session, role_id: int) -> list[str]:
    return sorted(
        str(row[0])
        for row in db.execute(
            select(AuthRolePermission.permission).where(AuthRolePermission.role_id == role_id)
        ).all()
    )


def _user_payload(db: Session, user: AuthUser) -> dict[str, Any]:
    return {
        "id": int(user.id),
        "username": str(user.username),
        "display_name": user.display_name,
        "email": user.email,
        "is_enabled": bool(user.is_enabled),
        "must_change_password": bool(user.must_change_password),
        "roles": _role_keys_for_user(db, int(user.id)),
        "created_at": user.created_at,
        "updated_at": user.updated_at,
        "last_login_at": user.last_login_at,
    }


def _requested_roles(db: Session, role_keys: list[str]) -> list[AuthRole]:
    ensure_system_roles(db)
    normalized_keys = [key.strip().casefold() for key in role_keys if key.strip()]
    if not normalized_keys:
        normalized_keys = [VIEWER_ROLE_KEY]
    roles = db.execute(select(AuthRole).where(AuthRole.key.in_(normalized_keys))).scalars().all()
    by_key = {str(role.key): role for role in roles}
    missing = sorted(set(normalized_keys) - set(by_key))
    if missing:
        raise HTTPException(status_code=400, detail={"error": "unknown_role", "roles": missing})
    return [by_key[key] for key in sorted(set(normalized_keys))]


def _replace_user_roles(db: Session, user: AuthUser, roles: list[AuthRole]) -> None:
    current_roles = set(_role_keys_for_user(db, int(user.id)))
    next_roles = {str(role.key) for role in roles}
    if "owner" in current_roles and "owner" not in next_roles:
        try:
            assert_not_last_enabled_owner(db, int(user.id), "remove_owner_role")
        except AuthInvariantError as exc:
            raise HTTPException(status_code=409, detail={"error": "last_enabled_owner"}) from exc
    db.query(AuthUserRole).filter(AuthUserRole.user_id == int(user.id)).delete(synchronize_session=False)
    for role in roles:
        db.add(AuthUserRole(user_id=int(user.id), role_id=int(role.id)))


def _revoke_active_sessions(db: Session, user_id: int) -> int:
    now = _utcnow()
    sessions = db.execute(
        select(AuthSession).where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
    ).scalars().all()
    for auth_session in sessions:
        auth_session.revoked_at = now
    return len(sessions)


def _audit(
    db: Session,
    request: Request,
    *,
    action: str,
    actor_user_id: int,
    target_type: str,
    target_id: str,
    detail: dict[str, Any] | None = None,
) -> None:
    create_audit_event(
        db,
        action=action,
        actor_user_id=actor_user_id,
        target_type=target_type,
        target_id=target_id,
        request_id=getattr(request.state, "req_id", None),
        detail=detail,
    )


def _safe_audit_detail(detail_json: str | None) -> dict[str, Any] | None:
    if not detail_json:
        return None
    try:
        detail = json.loads(detail_json)
    except json.JSONDecodeError:
        return None
    if not isinstance(detail, dict):
        return None
    blocked = ("password", "hash", "token", "secret", "recovery", "code")
    return {str(key): value for key, value in detail.items() if not any(part in str(key).casefold() for part in blocked)}


@router.get("/users")
def list_users(
    db: Session = Depends(get_session),
    actor: AuthUserContext = Depends(require_permission(PERMISSION_USERS_READ)),
    _token: None = Depends(require_token_ctx),
) -> dict[str, Any]:
    _claimed_actor(actor)
    users = db.execute(select(AuthUser).order_by(AuthUser.id.asc())).scalars().all()
    return {"users": [_user_payload(db, user) for user in users]}


@router.post("/users")
def create_user(
    payload: UserCreateRequest,
    request: Request,
    db: Session = Depends(get_session),
    actor: AuthUserContext = Depends(require_permission(PERMISSION_USERS_MANAGE)),
    _token: None = Depends(require_token_ctx),
    _writes: None = Depends(require_writes),
) -> dict[str, Any]:
    actor_user_id = _claimed_actor(actor)
    try:
        username_norm = normalize_username(payload.username)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": "username_required"}) from exc
    if db.scalar(select(AuthUser.id).where(AuthUser.username_norm == username_norm)) is not None:
        raise HTTPException(status_code=409, detail={"error": "username_exists"})
    _require_valid_password(payload.password)

    roles = _requested_roles(db, payload.roles)
    user = AuthUser(
        username=payload.username.strip(),
        username_norm=username_norm,
        display_name=_safe_text(payload.display_name),
        email=_safe_text(payload.email),
        password_hash=hash_password(payload.password),
        password_scheme=SCRYPT_SCHEME,
        is_enabled=True,
        must_change_password=bool(payload.must_change_password),
    )
    db.add(user)
    db.flush()
    for role in roles:
        db.add(AuthUserRole(user_id=int(user.id), role_id=int(role.id)))
    _audit(
        db,
        request,
        action="user.created",
        actor_user_id=actor_user_id,
        target_type="user",
        target_id=str(user.id),
        detail={"username_norm": username_norm, "roles": [str(role.key) for role in roles]},
    )
    db.commit()
    db.refresh(user)
    return {"ok": True, "user": _user_payload(db, user)}


@router.get("/users/{user_id}")
def get_user(
    user_id: int,
    db: Session = Depends(get_session),
    actor: AuthUserContext = Depends(require_permission(PERMISSION_USERS_READ)),
    _token: None = Depends(require_token_ctx),
) -> dict[str, Any]:
    _claimed_actor(actor)
    return {"user": _user_payload(db, _require_user(db, user_id))}


@router.patch("/users/{user_id}")
def update_user(
    user_id: int,
    payload: UserUpdateRequest,
    request: Request,
    db: Session = Depends(get_session),
    actor: AuthUserContext = Depends(require_permission(PERMISSION_USERS_MANAGE)),
    _token: None = Depends(require_token_ctx),
    _writes: None = Depends(require_writes),
) -> dict[str, Any]:
    actor_user_id = _claimed_actor(actor)
    user = _require_user(db, user_id)
    changed: list[str] = []
    fields_set = _fields_set(payload)
    if "display_name" in fields_set:
        user.display_name = _safe_text(payload.display_name)
        changed.append("display_name")
    if "email" in fields_set:
        user.email = _safe_text(payload.email)
        changed.append("email")
    if "must_change_password" in fields_set:
        user.must_change_password = bool(payload.must_change_password)
        changed.append("must_change_password")
    if "is_enabled" in fields_set and bool(payload.is_enabled) != bool(user.is_enabled):
        if not bool(payload.is_enabled):
            try:
                assert_not_last_enabled_owner(db, user_id, "disable")
            except AuthInvariantError as exc:
                raise HTTPException(status_code=409, detail={"error": "last_enabled_owner"}) from exc
            _revoke_active_sessions(db, user_id)
        user.is_enabled = bool(payload.is_enabled)
        changed.append("is_enabled")
    _audit(
        db,
        request,
        action="user.updated",
        actor_user_id=actor_user_id,
        target_type="user",
        target_id=str(user.id),
        detail={"fields": changed},
    )
    db.commit()
    db.refresh(user)
    return {"ok": True, "user": _user_payload(db, user)}


@router.post("/users/{user_id}/disable")
def disable_user(
    user_id: int,
    request: Request,
    db: Session = Depends(get_session),
    actor: AuthUserContext = Depends(require_permission(PERMISSION_USERS_MANAGE)),
    _token: None = Depends(require_token_ctx),
    _writes: None = Depends(require_writes),
) -> dict[str, Any]:
    actor_user_id = _claimed_actor(actor)
    user = _require_user(db, user_id)
    try:
        assert_not_last_enabled_owner(db, user_id, "disable")
    except AuthInvariantError as exc:
        raise HTTPException(status_code=409, detail={"error": "last_enabled_owner"}) from exc
    user.is_enabled = False
    revoked_count = _revoke_active_sessions(db, user_id)
    _audit(
        db,
        request,
        action="user.disabled",
        actor_user_id=actor_user_id,
        target_type="user",
        target_id=str(user.id),
        detail={"revoked_sessions": revoked_count},
    )
    db.commit()
    db.refresh(user)
    return {"ok": True, "user": _user_payload(db, user), "revoked_sessions": revoked_count}


@router.post("/users/{user_id}/enable")
def enable_user(
    user_id: int,
    request: Request,
    db: Session = Depends(get_session),
    actor: AuthUserContext = Depends(require_permission(PERMISSION_USERS_MANAGE)),
    _token: None = Depends(require_token_ctx),
    _writes: None = Depends(require_writes),
) -> dict[str, Any]:
    actor_user_id = _claimed_actor(actor)
    user = _require_user(db, user_id)
    user.is_enabled = True
    _audit(
        db,
        request,
        action="user.enabled",
        actor_user_id=actor_user_id,
        target_type="user",
        target_id=str(user.id),
    )
    db.commit()
    db.refresh(user)
    return {"ok": True, "user": _user_payload(db, user)}


@router.post("/users/{user_id}/reset-password")
def reset_user_password(
    user_id: int,
    payload: PasswordResetRequest,
    request: Request,
    db: Session = Depends(get_session),
    actor: AuthUserContext = Depends(require_permission(PERMISSION_USERS_MANAGE)),
    _token: None = Depends(require_token_ctx),
    _writes: None = Depends(require_writes),
) -> dict[str, Any]:
    actor_user_id = _claimed_actor(actor)
    user = _require_user(db, user_id)
    _require_valid_password(payload.new_password)
    user.password_hash = hash_password(payload.new_password)
    user.password_scheme = SCRYPT_SCHEME
    user.must_change_password = bool(payload.must_change_password)
    revoked_count = _revoke_active_sessions(db, user_id) if payload.revoke_sessions else 0
    _audit(
        db,
        request,
        action="user.password_reset",
        actor_user_id=actor_user_id,
        target_type="user",
        target_id=str(user.id),
        detail={"revoke_sessions": bool(payload.revoke_sessions), "revoked_sessions": revoked_count},
    )
    db.commit()
    return {"ok": True, "user": _user_payload(db, user), "revoked_sessions": revoked_count}


@router.get("/roles")
def list_roles(
    db: Session = Depends(get_session),
    actor: AuthUserContext = Depends(require_permission(PERMISSION_USERS_READ)),
    _token: None = Depends(require_token_ctx),
) -> dict[str, Any]:
    _claimed_actor(actor)
    ensure_system_roles(db)
    roles = db.execute(select(AuthRole).order_by(AuthRole.key.asc())).scalars().all()
    return {
        "roles": [
            {
                "key": str(role.key),
                "name": str(role.name),
                "permissions": _permissions_for_role(db, int(role.id)),
            }
            for role in roles
        ]
    }


@router.patch("/users/{user_id}/roles")
def update_user_roles(
    user_id: int,
    payload: UserRolesRequest,
    request: Request,
    db: Session = Depends(get_session),
    actor: AuthUserContext = Depends(require_permission(PERMISSION_USERS_MANAGE)),
    _token: None = Depends(require_token_ctx),
    _writes: None = Depends(require_writes),
) -> dict[str, Any]:
    actor_user_id = _claimed_actor(actor)
    user = _require_user(db, user_id)
    roles = _requested_roles(db, payload.roles)
    previous_roles = _role_keys_for_user(db, user_id)
    _replace_user_roles(db, user, roles)
    next_roles = [str(role.key) for role in roles]
    _audit(
        db,
        request,
        action="user.roles_changed",
        actor_user_id=actor_user_id,
        target_type="user",
        target_id=str(user.id),
        detail={"previous_roles": previous_roles, "roles": next_roles},
    )
    db.commit()
    return {"ok": True, "user": _user_payload(db, user)}


@router.get("/sessions")
def list_sessions(
    db: Session = Depends(get_session),
    actor: AuthUserContext = Depends(require_permission(PERMISSION_SESSIONS_MANAGE)),
    _token: None = Depends(require_token_ctx),
    limit: int = Query(100, ge=1, le=500),
) -> dict[str, Any]:
    _claimed_actor(actor)
    rows = db.execute(
        select(AuthSession, AuthUser)
        .join(AuthUser, AuthUser.id == AuthSession.user_id)
        .order_by(AuthSession.created_at.desc(), AuthSession.id.desc())
        .limit(limit)
    ).all()
    return {
        "sessions": [
            {
                "id": int(auth_session.id),
                "user_id": int(auth_session.user_id),
                "username": str(user.username),
                "created_at": auth_session.created_at,
                "expires_at": auth_session.expires_at,
                "last_seen_at": auth_session.last_seen_at,
                "revoked_at": auth_session.revoked_at,
            }
            for auth_session, user in rows
        ]
    }


@router.post("/sessions/{session_id}/revoke")
def revoke_session(
    session_id: int,
    request: Request,
    db: Session = Depends(get_session),
    actor: AuthUserContext = Depends(require_permission(PERMISSION_SESSIONS_MANAGE)),
    _token: None = Depends(require_token_ctx),
    _writes: None = Depends(require_writes),
) -> dict[str, Any]:
    actor_user_id = _claimed_actor(actor)
    auth_session = db.get(AuthSession, session_id)
    if auth_session is None:
        raise HTTPException(status_code=404, detail={"error": "session_not_found"})
    already_revoked = auth_session.revoked_at is not None
    if not already_revoked:
        auth_session.revoked_at = _utcnow()
    _audit(
        db,
        request,
        action="session.revoked",
        actor_user_id=actor_user_id,
        target_type="session",
        target_id=str(auth_session.id),
        detail={"already_revoked": already_revoked, "user_id": int(auth_session.user_id)},
    )
    db.commit()
    return {"ok": True, "session": {"id": int(auth_session.id), "revoked_at": auth_session.revoked_at}}


@router.get("/audit")
def list_audit_events(
    db: Session = Depends(get_session),
    actor: AuthUserContext = Depends(require_permission(PERMISSION_AUDIT_READ)),
    _token: None = Depends(require_token_ctx),
    limit: int = Query(100, ge=1, le=500),
    action: str | None = None,
    actor_user_id: int | None = None,
    target_type: str | None = None,
) -> dict[str, Any]:
    _claimed_actor(actor)
    stmt = select(AuthAuditEvent)
    if action:
        stmt = stmt.where(AuthAuditEvent.action == action)
    if actor_user_id is not None:
        stmt = stmt.where(AuthAuditEvent.actor_user_id == actor_user_id)
    if target_type:
        stmt = stmt.where(AuthAuditEvent.target_type == target_type)
    stmt = stmt.order_by(AuthAuditEvent.created_at.desc(), AuthAuditEvent.id.desc()).limit(limit)
    events = db.execute(stmt).scalars().all()
    return {
        "events": [
            {
                "id": int(event.id),
                "actor_user_id": event.actor_user_id,
                "action": str(event.action),
                "target_type": event.target_type,
                "target_id": event.target_id,
                "request_id": event.request_id,
                "detail": _safe_audit_detail(event.detail_json),
                "created_at": event.created_at,
            }
            for event in events
        ]
    }


__all__ = ["router"]
