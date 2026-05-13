# SPDX-License-Identifier: AGPL-3.0-or-later
"""DB-backed auth and user-account models."""

from __future__ import annotations

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func as sa_func

from core.appdb.models import Base


class AuthUser(Base):
    __tablename__ = "auth_users"

    id = Column(Integer, primary_key=True)
    username = Column(String, nullable=False, unique=True)
    username_norm = Column(String, nullable=False, unique=True, index=True)
    display_name = Column(String, nullable=True)
    email = Column(String, nullable=True)
    password_hash = Column(Text, nullable=False)
    password_scheme = Column(String, nullable=False)
    is_enabled = Column(Boolean, nullable=False, default=True, server_default="1")
    must_change_password = Column(Boolean, nullable=False, default=False, server_default="0")
    created_at = Column(DateTime, nullable=False, server_default=sa_func.now())
    updated_at = Column(
        DateTime,
        nullable=False,
        server_default=sa_func.now(),
        onupdate=sa_func.now(),
    )
    last_login_at = Column(DateTime, nullable=True)

    roles = relationship("AuthUserRole", back_populates="user", cascade="all, delete-orphan")
    sessions = relationship("AuthSession", back_populates="user", cascade="all, delete-orphan")
    recovery_codes = relationship(
        "AuthRecoveryCode",
        back_populates="user",
        cascade="all, delete-orphan",
    )


class AuthRole(Base):
    __tablename__ = "auth_roles"

    id = Column(Integer, primary_key=True)
    key = Column(String, nullable=False, unique=True, index=True)
    name = Column(String, nullable=False)
    is_system = Column(Boolean, nullable=False, default=True, server_default="1")
    created_at = Column(DateTime, nullable=False, server_default=sa_func.now())

    users = relationship("AuthUserRole", back_populates="role", cascade="all, delete-orphan")
    permissions = relationship(
        "AuthRolePermission",
        back_populates="role",
        cascade="all, delete-orphan",
    )


class AuthUserRole(Base):
    __tablename__ = "auth_user_roles"
    __table_args__ = (UniqueConstraint("user_id", "role_id", name="uq_auth_user_roles_user_role"),)

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("auth_users.id"), nullable=False, index=True)
    role_id = Column(Integer, ForeignKey("auth_roles.id"), nullable=False, index=True)

    user = relationship("AuthUser", back_populates="roles")
    role = relationship("AuthRole", back_populates="users")


class AuthRolePermission(Base):
    __tablename__ = "auth_role_permissions"
    __table_args__ = (
        UniqueConstraint("role_id", "permission", name="uq_auth_role_permissions_role_permission"),
    )

    id = Column(Integer, primary_key=True)
    role_id = Column(Integer, ForeignKey("auth_roles.id"), nullable=False, index=True)
    permission = Column(String, nullable=False)

    role = relationship("AuthRole", back_populates="permissions")


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    id = Column(Integer, primary_key=True)
    session_hash = Column(String, nullable=False, unique=True, index=True)
    user_id = Column(Integer, ForeignKey("auth_users.id"), nullable=False, index=True)
    created_at = Column(DateTime, nullable=False, server_default=sa_func.now())
    expires_at = Column(DateTime, nullable=False)
    last_seen_at = Column(DateTime, nullable=True)
    revoked_at = Column(DateTime, nullable=True)
    user_agent_hash = Column(String, nullable=True)

    user = relationship("AuthUser", back_populates="sessions")


class AuthRecoveryCode(Base):
    __tablename__ = "auth_recovery_codes"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("auth_users.id"), nullable=False, index=True)
    code_hash = Column(String, nullable=False, unique=True, index=True)
    created_at = Column(DateTime, nullable=False, server_default=sa_func.now())
    used_at = Column(DateTime, nullable=True)

    user = relationship("AuthUser", back_populates="recovery_codes")


class AuthAuditEvent(Base):
    __tablename__ = "auth_audit_events"

    id = Column(Integer, primary_key=True)
    actor_user_id = Column(Integer, ForeignKey("auth_users.id"), nullable=True, index=True)
    action = Column(String, nullable=False, index=True)
    target_type = Column(String, nullable=True)
    target_id = Column(String, nullable=True)
    request_id = Column(String, nullable=True)
    detail_json = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=sa_func.now())

    actor = relationship("AuthUser")


__all__ = [
    "AuthAuditEvent",
    "AuthRecoveryCode",
    "AuthRole",
    "AuthRolePermission",
    "AuthSession",
    "AuthUser",
    "AuthUserRole",
]
