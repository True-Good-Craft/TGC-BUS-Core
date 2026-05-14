from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select

from core.api.routes.auth import AUTH_SESSION_COOKIE
from core.auth.passwords import SCRYPT_SCHEME, hash_password, verify_password
from core.auth.permissions import (
    OPERATOR_ROLE_KEY,
    OWNER_ROLE_KEY,
    PERMISSION_AUDIT_READ,
    PERMISSION_SESSIONS_MANAGE,
    PERMISSION_USERS_MANAGE,
    PERMISSION_USERS_READ,
    VIEWER_ROLE_KEY,
)
from core.auth.sessions import hash_session_token
from core.auth.store import normalize_username


OWNER_PASSWORD = "correct horse battery staple"


def _anonymous_client(bus_client) -> TestClient:
    return TestClient(bus_client["api_http"].APP)


def _setup_owner(client: TestClient) -> int:
    response = client.post("/auth/setup-owner", json={"username": "owner", "password": OWNER_PASSWORD})
    assert response.status_code == 200, response.text
    token = response.cookies.get(AUTH_SESSION_COOKIE)
    assert token
    existing_cookie = client.headers.get("Cookie", "")
    if AUTH_SESSION_COOKIE not in existing_cookie:
        separator = "; " if existing_cookie else ""
        client.headers.update({"Cookie": f"{existing_cookie}{separator}{AUTH_SESSION_COOKIE}={token}"})
    return int(response.json()["user"]["id"])


def _login(bus_client, username: str, password: str) -> TestClient:
    client = _anonymous_client(bus_client)
    response = client.post("/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    token = response.cookies.get(AUTH_SESSION_COOKIE)
    assert token
    client.headers.update({"Cookie": f"{AUTH_SESSION_COOKIE}={token}"})
    return client


def _auth_token(client: TestClient) -> str:
    token = client.cookies.get(AUTH_SESSION_COOKIE)
    if token:
        return str(token)
    cookie_header = client.headers.get("Cookie", "")
    for part in cookie_header.split(";"):
        name, _, value = part.strip().partition("=")
        if name == AUTH_SESSION_COOKIE and value:
            return value
    raise AssertionError("missing auth token")


def _create_user(
    client: TestClient,
    username: str,
    password: str = "temporary-password",
    roles: list[str] | None = None,
) -> dict:
    response = client.post(
        "/app/users",
        json={
            "username": username,
            "password": password,
            "display_name": f"Display {username}",
            "email": f"{username}@example.test",
            "roles": roles or [VIEWER_ROLE_KEY],
            "must_change_password": True,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["user"]


def _db_user(bus_client, username: str):
    models = bus_client["models"]
    engine_module = bus_client["engine"]
    with engine_module.SessionLocal() as db:
        user = db.scalar(select(models.AuthUser).where(models.AuthUser.username_norm == normalize_username(username)))
        assert user is not None
        return {
            "id": int(user.id),
            "password_hash": str(user.password_hash),
            "password_scheme": str(user.password_scheme),
            "is_enabled": bool(user.is_enabled),
        }


def _create_role_with_permissions(bus_client, key: str, permissions: list[str]) -> None:
    models = bus_client["models"]
    engine_module = bus_client["engine"]
    with engine_module.SessionLocal() as db:
        role = db.scalar(select(models.AuthRole).where(models.AuthRole.key == key))
        if role is None:
            role = models.AuthRole(key=key, name=key.replace("_", " ").title(), is_system=False)
            db.add(role)
            db.flush()
        for permission in permissions:
            exists = db.scalar(
                select(models.AuthRolePermission.id).where(
                    models.AuthRolePermission.role_id == role.id,
                    models.AuthRolePermission.permission == permission,
                )
            )
            if exists is None:
                db.add(models.AuthRolePermission(role_id=int(role.id), permission=permission))
        db.commit()


def _create_db_user_with_role(bus_client, username: str, role_key: str, password: str = "temporary-password") -> None:
    models = bus_client["models"]
    engine_module = bus_client["engine"]
    with engine_module.SessionLocal() as db:
        role = db.scalar(select(models.AuthRole).where(models.AuthRole.key == role_key))
        assert role is not None
        user = models.AuthUser(
            username=username,
            username_norm=normalize_username(username),
            password_hash=hash_password(password),
            password_scheme=SCRYPT_SCHEME,
            is_enabled=True,
            must_change_password=False,
        )
        db.add(user)
        db.flush()
        db.add(models.AuthUserRole(user_id=int(user.id), role_id=int(role.id)))
        db.commit()


def test_owner_can_list_users_and_create_child_user_with_hashed_password(bus_client):
    client = bus_client["client"]
    _setup_owner(client)

    list_response = client.get("/app/users")
    assert list_response.status_code == 200, list_response.text
    assert [user["username"] for user in list_response.json()["users"]] == ["owner"]

    created = _create_user(client, "operator1")
    assert created["username"] == "operator1"
    assert created["roles"] == [VIEWER_ROLE_KEY]
    assert "password" not in created
    assert "password_hash" not in created

    stored = _db_user(bus_client, "operator1")
    assert stored["password_hash"] != "temporary-password"
    assert stored["password_scheme"] == SCRYPT_SCHEME
    assert verify_password("temporary-password", stored["password_hash"])

    duplicate = client.post("/app/users", json={"username": " OPERATOR1 ", "password": "another", "roles": []})
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"]["error"] == "username_exists"

    short = client.post("/app/users", json={"username": "short-pass", "password": "short", "roles": []})
    assert short.status_code == 400
    assert short.json()["detail"]["error"] == "password_too_short"


def test_owner_can_access_security_management_routes(bus_client):
    client = bus_client["client"]
    _setup_owner(client)

    assert client.get("/app/users").status_code == 200
    assert client.get("/app/roles").status_code == 200
    assert client.get("/app/sessions").status_code == 200
    assert client.get("/app/audit").status_code == 200


def test_viewer_and_operator_cannot_manage_users(bus_client):
    owner_client = bus_client["client"]
    _setup_owner(owner_client)
    _create_user(owner_client, "viewer", roles=[VIEWER_ROLE_KEY])
    _create_user(owner_client, "operator", roles=[OPERATOR_ROLE_KEY])

    for username in ["viewer", "operator"]:
        client = _login(bus_client, username, "temporary-password")
        response = client.post("/app/users", json={"username": "blocked", "password": "temporary-password"})
        assert response.status_code == 403, f"{username}: {response.text}"
        assert response.json()["detail"]["error"] == "permission_denied"


def test_security_management_permissions_are_independent(bus_client):
    owner_client = bus_client["client"]
    _setup_owner(owner_client)
    _create_user(owner_client, "viewer", roles=[VIEWER_ROLE_KEY])

    viewer = _login(bus_client, "viewer", "temporary-password")
    for method, path, payload in [
        ("get", "/app/audit", None),
        ("get", "/app/sessions", None),
        ("post", "/app/sessions/1/revoke", {}),
        ("patch", "/app/users/1/roles", {"roles": [VIEWER_ROLE_KEY]}),
    ]:
        kwargs = {"json": payload} if payload is not None else {}
        response = getattr(viewer, method)(path, **kwargs)
        assert response.status_code == 403, f"{method.upper()} {path}: {response.text}"
        assert response.json()["detail"]["error"] == "permission_denied"

    _create_role_with_permissions(bus_client, "user_reader", [PERMISSION_USERS_READ])
    _create_db_user_with_role(bus_client, "user-reader", "user_reader")
    reader = _login(bus_client, "user-reader", "temporary-password")
    assert reader.get("/app/users").status_code == 200
    role_change = reader.patch("/app/users/1/roles", json={"roles": [VIEWER_ROLE_KEY]})
    assert role_change.status_code == 403

    _create_role_with_permissions(bus_client, "session_manager", [PERMISSION_SESSIONS_MANAGE])
    _create_db_user_with_role(bus_client, "session-manager", "session_manager")
    session_manager = _login(bus_client, "session-manager", "temporary-password")
    assert session_manager.get("/app/sessions").status_code == 200
    assert session_manager.get("/app/audit").status_code == 403


def test_user_with_users_manage_can_create_and_update_users(bus_client):
    owner_client = bus_client["client"]
    _setup_owner(owner_client)
    _create_role_with_permissions(bus_client, "user_admin", [PERMISSION_USERS_MANAGE])
    _create_db_user_with_role(bus_client, "manager", "user_admin")
    manager_client = _login(bus_client, "manager", "temporary-password")

    created = _create_user(manager_client, "managed-child")
    update = manager_client.patch(
        f"/app/users/{created['id']}",
        json={"display_name": "Managed Child", "email": "managed@example.test", "must_change_password": False},
    )

    assert update.status_code == 200, update.text
    payload = update.json()["user"]
    assert payload["display_name"] == "Managed Child"
    assert payload["email"] == "managed@example.test"
    assert payload["must_change_password"] is False


def test_owner_can_disable_enable_and_assign_roles_to_child_user(bus_client):
    client = bus_client["client"]
    _setup_owner(client)
    child = _create_user(client, "child", roles=[VIEWER_ROLE_KEY])
    child_client = _login(bus_client, "child", "temporary-password")
    child_token = _auth_token(child_client)

    roles = client.patch(f"/app/users/{child['id']}/roles", json={"roles": [OPERATOR_ROLE_KEY, VIEWER_ROLE_KEY]})
    assert roles.status_code == 200, roles.text
    assert roles.json()["user"]["roles"] == [OPERATOR_ROLE_KEY, VIEWER_ROLE_KEY]

    disable = client.post(f"/app/users/{child['id']}/disable")
    assert disable.status_code == 200, disable.text
    assert disable.json()["user"]["is_enabled"] is False
    assert disable.json()["revoked_sessions"] >= 1

    models = bus_client["models"]
    engine_module = bus_client["engine"]
    with engine_module.SessionLocal() as db:
        session = db.scalar(select(models.AuthSession).where(models.AuthSession.session_hash == hash_session_token(child_token)))
        assert session is not None
        assert session.revoked_at is not None

    enable = client.post(f"/app/users/{child['id']}/enable")
    assert enable.status_code == 200, enable.text
    assert enable.json()["user"]["is_enabled"] is True


def test_owner_invariant_prevents_disabling_or_stripping_last_owner(bus_client):
    client = bus_client["client"]
    owner_id = _setup_owner(client)

    disable = client.post(f"/app/users/{owner_id}/disable")
    assert disable.status_code == 409
    assert disable.json()["detail"]["error"] == "last_enabled_owner"

    strip = client.patch(f"/app/users/{owner_id}/roles", json={"roles": [VIEWER_ROLE_KEY]})
    assert strip.status_code == 409
    assert strip.json()["detail"]["error"] == "last_enabled_owner"


def test_two_owner_invariant_allows_one_owner_to_be_disabled_or_stripped(bus_client):
    client = bus_client["client"]
    _setup_owner(client)
    second_owner = _create_user(client, "second-owner", roles=[OWNER_ROLE_KEY])

    disable = client.post(f"/app/users/{second_owner['id']}/disable")
    assert disable.status_code == 200, disable.text

    enable = client.post(f"/app/users/{second_owner['id']}/enable")
    assert enable.status_code == 200, enable.text

    strip = client.patch(f"/app/users/{second_owner['id']}/roles", json={"roles": [VIEWER_ROLE_KEY]})
    assert strip.status_code == 200, strip.text
    assert strip.json()["user"]["roles"] == [VIEWER_ROLE_KEY]


def test_password_reset_changes_credentials_and_revokes_sessions(bus_client):
    client = bus_client["client"]
    _setup_owner(client)
    child = _create_user(client, "reset-me", password="old-password", roles=[VIEWER_ROLE_KEY])
    child_client = _login(bus_client, "reset-me", "old-password")

    reset = client.post(
        f"/app/users/{child['id']}/reset-password",
        json={"new_password": "new-password", "must_change_password": True, "revoke_sessions": True},
    )
    assert reset.status_code == 200, reset.text
    assert reset.json()["revoked_sessions"] >= 1
    assert "new-password" not in reset.text
    assert "password_hash" not in reset.text

    old_session = child_client.get("/app/items")
    assert old_session.status_code == 401

    old_login = _anonymous_client(bus_client).post("/auth/login", json={"username": "reset-me", "password": "old-password"})
    assert old_login.status_code == 401

    new_login = _anonymous_client(bus_client).post("/auth/login", json={"username": "reset-me", "password": "new-password"})
    assert new_login.status_code == 200, new_login.text

    short_reset = client.post(f"/app/users/{child['id']}/reset-password", json={"new_password": "short"})
    assert short_reset.status_code == 400
    assert short_reset.json()["detail"]["error"] == "password_too_short"


def test_last_owner_password_reset_requires_valid_new_password_and_remains_recoverable(bus_client):
    client = bus_client["client"]
    owner_id = _setup_owner(client)

    short = client.post(f"/app/users/{owner_id}/reset-password", json={"new_password": "short"})
    assert short.status_code == 400
    assert short.json()["detail"]["error"] == "password_too_short"

    reset = client.post(
        f"/app/users/{owner_id}/reset-password",
        json={"new_password": "new-owner-password", "revoke_sessions": True},
    )
    assert reset.status_code == 200, reset.text
    assert reset.json()["revoked_sessions"] >= 1

    old_session = client.get("/app/users")
    assert old_session.status_code == 401
    new_login = _anonymous_client(bus_client).post(
        "/auth/login",
        json={"username": "owner", "password": "new-owner-password"},
    )
    assert new_login.status_code == 200, new_login.text


def test_sessions_list_redacts_hashes_and_revoke_is_safe(bus_client):
    client = bus_client["client"]
    _setup_owner(client)
    _create_user(client, "session-user", roles=[VIEWER_ROLE_KEY])
    _login(bus_client, "session-user", "temporary-password")

    sessions = client.get("/app/sessions")
    assert sessions.status_code == 200, sessions.text
    rows = sessions.json()["sessions"]
    assert rows
    assert all("session_hash" not in row and "session_token" not in row and "token" not in row for row in rows)
    target = next(row for row in rows if row["username"] == "session-user")

    first = client.post(f"/app/sessions/{target['id']}/revoke")
    second = client.post(f"/app/sessions/{target['id']}/revoke")
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["session"]["revoked_at"] is not None
    assert second.json()["session"]["revoked_at"] is not None


def test_audit_list_and_required_management_events(bus_client):
    client = bus_client["client"]
    _setup_owner(client)
    child = _create_user(client, "audit-child", roles=[VIEWER_ROLE_KEY])
    client.patch(f"/app/users/{child['id']}", json={"display_name": "Audit Child"})
    client.post(f"/app/users/{child['id']}/disable")
    client.post(f"/app/users/{child['id']}/enable")
    client.post(f"/app/users/{child['id']}/reset-password", json={"new_password": "audit-new-password"})
    client.patch(f"/app/users/{child['id']}/roles", json={"roles": [OPERATOR_ROLE_KEY, VIEWER_ROLE_KEY]})
    _login(bus_client, "audit-child", "audit-new-password")
    session_id = next(row["id"] for row in client.get("/app/sessions").json()["sessions"] if row["username"] == "audit-child")
    client.post(f"/app/sessions/{session_id}/revoke")

    audit = client.get("/app/audit", params={"limit": 100})
    assert audit.status_code == 200, audit.text
    actions = {event["action"] for event in audit.json()["events"]}
    assert {
        "user.created",
        "user.updated",
        "user.disabled",
        "user.enabled",
        "user.password_reset",
        "user.roles_changed",
        "session.revoked",
    }.issubset(actions)
    assert "audit-new-password" not in audit.text
    assert "password_hash" not in audit.text
    assert "session_hash" not in audit.text
    assert "recovery" not in audit.text

    _create_role_with_permissions(bus_client, "auditor", [PERMISSION_AUDIT_READ])
    _create_db_user_with_role(bus_client, "auditor", "auditor")
    auditor = _login(bus_client, "auditor", "temporary-password")
    auditor_response = auditor.get("/app/audit", params={"action": "user.created"})
    assert auditor_response.status_code == 200, auditor_response.text
    assert all(event["action"] == "user.created" for event in auditor_response.json()["events"])


def test_roles_endpoint_and_unclaimed_legacy_behavior(bus_client):
    unclaimed = _anonymous_client(bus_client)
    token_response = unclaimed.get("/session/token")
    assert token_response.status_code == 200
    app_response = unclaimed.get("/app/items", headers={"Cookie": f"bus_session={token_response.json()['token']}"})
    assert app_response.status_code == 200

    client = bus_client["client"]
    _setup_owner(client)
    roles = client.get("/app/roles")
    assert roles.status_code == 200, roles.text
    role_map = {role["key"]: role for role in roles.json()["roles"]}
    assert "owner" in role_map
    assert "users.manage" in role_map["owner"]["permissions"]
