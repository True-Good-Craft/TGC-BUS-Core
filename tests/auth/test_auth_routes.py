# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select

from core.api.routes.auth import AUTH_SESSION_COOKIE, RECOVERY_CODE_COUNT
from core.auth.permissions import OWNER_ROLE_KEY
from core.auth.sessions import hash_session_token


def _legacy_session_token(bus_client) -> str:
    return bus_client["api_http"].app.state.app_state.tokens.current()


def _legacy_client(bus_client) -> TestClient:
    client = TestClient(bus_client["api_http"].APP)
    client.headers.update({"Cookie": f"bus_session={_legacy_session_token(bus_client)}"})
    return client


def _setup_owner(client) -> dict:
    response = client.post(
        "/auth/setup-owner",
        json={
            "username": "owner",
            "password": "correct horse battery staple",
            "display_name": "Shop Owner",
            "email": "owner@example.test",
            "business_name": "Example Shop",
        },
    )
    assert response.status_code == 200, response.text
    auth_token = response.cookies.get(AUTH_SESSION_COOKIE)
    if auth_token:
        existing_cookie = client.headers.get("Cookie", "")
        if AUTH_SESSION_COOKIE not in existing_cookie:
            separator = "; " if existing_cookie else ""
            client.headers.update({"Cookie": f"{existing_cookie}{separator}{AUTH_SESSION_COOKIE}={auth_token}"})
    return response.json()


def test_auth_state_returns_unclaimed_on_fresh_db(bus_client):
    client = bus_client["client"]

    response = client.get("/auth/state")

    assert response.status_code == 200
    assert response.json() == {
        "mode": "unclaimed",
        "owner_exists": False,
        "setup_available": True,
        "login_required": False,
        "current_user": None,
    }


def test_setup_owner_succeeds_and_creates_owner_user_role_session_and_recovery_codes(bus_client):
    client = bus_client["client"]
    models = bus_client["models"]
    engine_module = bus_client["engine"]

    response = client.post(
        "/auth/setup-owner",
        json={"username": "owner", "password": "correct horse battery staple"},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["ok"] is True
    assert payload["mode"] == "claimed"
    assert payload["user"]["username"] == "owner"
    assert payload["user"]["roles"] == [OWNER_ROLE_KEY]
    assert len(payload["recovery_codes"]) == RECOVERY_CODE_COUNT
    assert len(set(payload["recovery_codes"])) == RECOVERY_CODE_COUNT
    assert response.cookies.get(AUTH_SESSION_COOKIE)

    with engine_module.SessionLocal() as db:
        users = db.execute(select(models.AuthUser)).scalars().all()
        assert len(users) == 1
        user = users[0]
        assert user.username == "owner"
        assert user.username_norm == "owner"

        roles = [
            row[0]
            for row in db.execute(
                select(models.AuthRole.key)
                .join(models.AuthUserRole, models.AuthUserRole.role_id == models.AuthRole.id)
                .where(models.AuthUserRole.user_id == user.id)
            ).all()
        ]
        assert roles == [OWNER_ROLE_KEY]

        stored_codes = db.execute(select(models.AuthRecoveryCode.code_hash)).scalars().all()
        assert len(stored_codes) == RECOVERY_CODE_COUNT
        for plain_code in payload["recovery_codes"]:
            assert plain_code not in stored_codes
            assert all(plain_code not in stored_hash for stored_hash in stored_codes)

        sessions = db.execute(select(models.AuthSession)).scalars().all()
        assert len(sessions) == 1
        assert sessions[0].session_hash == hash_session_token(response.cookies[AUTH_SESSION_COOKIE])


def test_setup_owner_second_call_fails(bus_client):
    client = bus_client["client"]
    _setup_owner(client)

    second = client.post(
        "/auth/setup-owner",
        json={"username": "second", "password": "another good password"},
    )

    assert second.status_code == 409
    assert second.json()["detail"]["error"] == "owner_setup_unavailable"


def test_login_succeeds_with_correct_credentials_and_creates_db_session(bus_client):
    setup_client = bus_client["client"]
    models = bus_client["models"]
    engine_module = bus_client["engine"]
    _setup_owner(setup_client)

    login_client = _legacy_client(bus_client)
    response = login_client.post(
        "/auth/login",
        json={"username": "OWNER", "password": "correct horse battery staple"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["ok"] is True
    assert response.json()["user"]["username"] == "owner"
    assert response.cookies.get(AUTH_SESSION_COOKIE)
    with engine_module.SessionLocal() as db:
        sessions = db.execute(select(models.AuthSession)).scalars().all()
        assert len(sessions) == 2
        assert any(session.session_hash == hash_session_token(response.cookies[AUTH_SESSION_COOKIE]) for session in sessions)


def test_login_fails_with_wrong_credentials(bus_client):
    client = bus_client["client"]
    _setup_owner(client)

    response = client.post("/auth/login", json={"username": "owner", "password": "wrong"})

    assert response.status_code == 401
    assert response.json()["detail"]["error"] == "invalid_credentials"


def test_disabled_user_cannot_login(bus_client):
    client = bus_client["client"]
    models = bus_client["models"]
    engine_module = bus_client["engine"]
    _setup_owner(client)
    with engine_module.SessionLocal() as db:
        user = db.scalar(select(models.AuthUser).where(models.AuthUser.username_norm == "owner"))
        assert user is not None
        user.is_enabled = False
        db.commit()

    response = client.post(
        "/auth/login",
        json={"username": "owner", "password": "correct horse battery staple"},
    )

    assert response.status_code == 403
    assert response.json()["detail"]["error"] == "user_disabled"


def test_logout_revokes_session(bus_client):
    client = bus_client["client"]
    models = bus_client["models"]
    engine_module = bus_client["engine"]
    _setup_owner(client)
    auth_token = client.cookies.get(AUTH_SESSION_COOKIE)
    assert auth_token

    response = client.post("/auth/logout")

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    with engine_module.SessionLocal() as db:
        session = db.scalar(select(models.AuthSession).where(models.AuthSession.session_hash == hash_session_token(auth_token)))
        assert session is not None
        assert session.revoked_at is not None


def test_auth_me_returns_current_user_with_valid_auth_session(bus_client):
    client = bus_client["client"]
    _setup_owner(client)

    response = client.get("/auth/me")

    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "claimed"
    assert payload["current_user"]["username"] == "owner"
    assert OWNER_ROLE_KEY in payload["current_user"]["roles"]
    assert "inventory.read" in payload["current_user"]["permissions"]


def test_auth_me_returns_401_in_claimed_mode_without_auth_session(bus_client):
    _setup_owner(bus_client["client"])
    legacy_only_client = _legacy_client(bus_client)

    response = legacy_only_client.get("/auth/me")

    assert response.status_code == 401
    assert response.json()["detail"]["error"] == "auth_required"


def test_auth_state_returns_claimed_with_and_without_valid_auth_session(bus_client):
    setup_client = bus_client["client"]
    _setup_owner(setup_client)

    claimed_without_auth = _legacy_client(bus_client).get("/auth/state")
    assert claimed_without_auth.status_code == 200
    assert claimed_without_auth.json() == {
        "mode": "claimed",
        "owner_exists": True,
        "setup_available": False,
        "login_required": True,
        "current_user": None,
    }

    claimed_with_auth = setup_client.get("/auth/state")
    assert claimed_with_auth.status_code == 200
    payload = claimed_with_auth.json()
    assert payload["mode"] == "claimed"
    assert payload["login_required"] is False
    assert payload["current_user"]["username"] == "owner"


def test_existing_session_token_behavior_remains_unchanged(bus_client):
    client = bus_client["client"]

    response = client.get("/session/token")

    assert response.status_code == 200
    assert response.json()["token"]
    assert response.cookies.get("bus_session") == response.json()["token"]
    assert response.cookies.get(AUTH_SESSION_COOKIE) is None


def test_existing_unclaimed_app_behavior_remains_unchanged(bus_client):
    client = bus_client["client"]

    response = client.get("/app/system/state")

    assert response.status_code == 200
    assert "status" in response.json()
