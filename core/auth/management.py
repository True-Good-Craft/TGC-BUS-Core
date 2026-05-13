"""Auth management helpers shared by user-management routes."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.appdb.models import AuthRole, AuthRolePermission, AuthUser, AuthUserRole
from core.auth.permissions import OWNER_ROLE_KEY, default_role_bundles


class AuthInvariantError(ValueError):
    pass


def ensure_system_roles(db: Session) -> dict[str, AuthRole]:
    roles: dict[str, AuthRole] = {}
    for role_key, permissions in default_role_bundles().items():
        role = db.scalar(select(AuthRole).where(AuthRole.key == role_key))
        if role is None:
            role = AuthRole(key=role_key, name=role_key.replace("_", " ").title(), is_system=True)
            db.add(role)
            db.flush()
        roles[role_key] = role

        existing_permissions = {
            str(row[0])
            for row in db.execute(
                select(AuthRolePermission.permission).where(AuthRolePermission.role_id == role.id)
            ).all()
        }
        for permission in permissions:
            if permission not in existing_permissions:
                db.add(AuthRolePermission(role_id=int(role.id), permission=permission))
    db.flush()
    return roles


def _enabled_owner_user_ids(db: Session) -> set[int]:
    return {
        int(row[0])
        for row in db.execute(
            select(AuthUser.id)
            .join(AuthUserRole, AuthUserRole.user_id == AuthUser.id)
            .join(AuthRole, AuthRole.id == AuthUserRole.role_id)
            .where(AuthUser.is_enabled.is_(True), AuthRole.key == OWNER_ROLE_KEY)
        ).all()
    }


def assert_not_last_enabled_owner(db: Session, user_id: int, proposed_change: str) -> None:
    if proposed_change not in {"disable", "delete", "remove_owner_role"}:
        return
    enabled_owner_ids = _enabled_owner_user_ids(db)
    if user_id in enabled_owner_ids and len(enabled_owner_ids) <= 1:
        raise AuthInvariantError("last_enabled_owner")


__all__ = ["AuthInvariantError", "assert_not_last_enabled_owner", "ensure_system_roles"]
