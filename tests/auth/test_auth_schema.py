# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from sqlalchemy import text

from core.auth.passwords import SCRYPT_SCHEME, hash_password
from core.auth.permissions import OWNER_ROLE_KEY
from core.auth.store import get_auth_state, normalize_username


AUTH_TABLES = {
    "auth_users",
    "auth_roles",
    "auth_user_roles",
    "auth_role_permissions",
    "auth_sessions",
    "auth_recovery_codes",
    "auth_audit_events",
}


def _run_startup_schema(bus_client) -> None:
    bus_client["api_http"].startup_migrations()


def test_auth_tables_materialize_without_default_users(bus_client):
    engine_module = bus_client["engine"]
    _run_startup_schema(bus_client)

    with engine_module.SessionLocal() as db:
        rows = db.execute(text("SELECT name FROM sqlite_master WHERE type='table'")).fetchall()
        table_names = {str(row[0]) for row in rows}
        user_count = db.execute(text("SELECT COUNT(*) FROM auth_users")).scalar_one()

    assert AUTH_TABLES.issubset(table_names)
    assert user_count == 0


def test_auth_state_reports_unclaimed_before_users(bus_client):
    engine_module = bus_client["engine"]
    _run_startup_schema(bus_client)

    with engine_module.SessionLocal() as db:
        state = get_auth_state(db)

    assert state.user_count == 0
    assert state.is_claimed is False
    assert state.enabled_owner_exists is False


def test_auth_state_reports_claimed_and_owner_after_owner_insert(bus_client):
    engine_module = bus_client["engine"]
    models = bus_client["models"]
    _run_startup_schema(bus_client)

    with engine_module.SessionLocal() as db:
        owner_role = models.AuthRole(key=OWNER_ROLE_KEY, name="Owner", is_system=True)
        owner_user = models.AuthUser(
            username="Owner",
            username_norm=normalize_username("Owner"),
            display_name="Owner",
            password_hash=hash_password("correct horse battery staple"),
            password_scheme=SCRYPT_SCHEME,
        )
        db.add_all([owner_role, owner_user])
        db.flush()
        db.add(models.AuthUserRole(user_id=owner_user.id, role_id=owner_role.id))
        db.commit()

        state = get_auth_state(db)

    assert state.user_count == 1
    assert state.is_claimed is True
    assert state.enabled_owner_exists is True
