# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import json
from datetime import datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select

from core.api.routes.auth import AUTH_SESSION_COOKIE, RECOVERY_CODE_COUNT
from core.auth.passwords import MIN_PASSWORD_LENGTH
from core.auth.permissions import OWNER_ROLE_KEY
from core.auth.sessions import (
    AUTH_SESSION_IDLE_TIMEOUT_MINUTES,
    AUTH_SESSION_MAX_AGE_DAYS,
    AUTH_SESSION_TOUCH_INTERVAL_MINUTES,
    hash_session_token,
)


def _legacy_session_token(bus_client) -> str:
    return bus_client["api_http"].app.state.app_state.tokens.current()


def _legacy_client(bus_client) -> TestClient:
    client = TestClient(bus_client["api_http"].APP)
    client.headers.update({"Cookie": f"bus_session={_legacy_session_token(bus_client)}"})
    return client


def _anonymous_client(bus_client) -> TestClient:
    return TestClient(bus_client["api_http"].APP)


def _auth_only_client(bus_client, auth_token: str) -> TestClient:
    client = TestClient(bus_client["api_http"].APP)
    client.headers.update({"Cookie": f"{AUTH_SESSION_COOKIE}={auth_token}"})
    return client


def _auth_token_from_client(client: TestClient) -> str:
    auth_token = client.cookies.get(AUTH_SESSION_COOKIE)
    if auth_token:
        return str(auth_token)
    cookie_header = client.headers.get("Cookie", "")
    for part in cookie_header.split(";"):
        name, _, value = part.strip().partition("=")
        if name == AUTH_SESSION_COOKIE and value:
            return value
    raise AssertionError("missing auth session cookie")


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
    client = _anonymous_client(bus_client)

    response = client.get("/auth/state")

    assert response.status_code == 200
    assert response.json() == {
        "mode": "unclaimed",
        "owner_exists": False,
        "setup_available": True,
        "login_required": False,
        "current_user": None,
    }


def test_unclaimed_mode_preserves_session_token_and_legacy_app_access(bus_client):
    client = _anonymous_client(bus_client)

    token_response = client.get("/session/token")
    assert token_response.status_code == 200
    token = token_response.json()["token"]
    assert token
    assert token_response.cookies.get("bus_session") == token

    app_response = client.get("/app/system/state", headers={"Cookie": f"bus_session={token}"})
    assert app_response.status_code == 200
    assert "status" in app_response.json()


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
    set_cookie = response.headers.get("set-cookie", "").lower()
    assert f"{AUTH_SESSION_COOKIE}=" in set_cookie
    assert "httponly" in set_cookie
    assert "samesite=lax" in set_cookie

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
        assert str(response.cookies[AUTH_SESSION_COOKIE]) not in str(sessions[0].session_hash)


def test_setup_owner_rejects_short_password(bus_client):
    client = bus_client["client"]

    response = client.post(
        "/auth/setup-owner",
        json={"username": "owner", "password": "x" * (MIN_PASSWORD_LENGTH - 1)},
    )

    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "password_too_short"


def test_setup_owner_second_call_fails(bus_client):
    client = bus_client["client"]
    _setup_owner(client)

    second = client.post(
        "/auth/setup-owner",
        json={"username": "second", "password": "another good password"},
    )

    assert second.status_code == 409
    assert second.json()["detail"]["error"] == "owner_setup_unavailable"


def test_claimed_bootstrap_auth_routes_are_reachable_without_legacy_cookie(bus_client):
    _setup_owner(bus_client["client"])
    client = _anonymous_client(bus_client)

    state_response = client.get("/auth/state")
    assert state_response.status_code == 200
    assert state_response.json()["mode"] == "claimed"

    login_response = client.post(
        "/auth/login",
        json={"username": "owner", "password": "correct horse battery staple"},
    )
    assert login_response.status_code == 200, login_response.text
    assert login_response.cookies.get(AUTH_SESSION_COOKIE)

    setup_response = client.post(
        "/auth/setup-owner",
        json={"username": "second", "password": "another good password"},
    )
    assert setup_response.status_code == 409
    assert setup_response.json()["detail"]["error"] == "owner_setup_unavailable"

    logout_response = client.post("/auth/logout")
    assert logout_response.status_code == 200
    assert logout_response.json() == {"ok": True}


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
    set_cookie = response.headers.get("set-cookie", "").lower()
    assert "httponly" in set_cookie
    assert "samesite=lax" in set_cookie
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
    set_cookie = response.headers.get("set-cookie", "").lower()
    assert f"{AUTH_SESSION_COOKIE}=" in set_cookie
    assert "max-age=0" in set_cookie or "expires=" in set_cookie
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


def test_claimed_mode_rejects_legacy_session_and_accepts_auth_session_for_app_routes(bus_client):
    setup_client = bus_client["client"]
    _setup_owner(setup_client)
    auth_token = _auth_token_from_client(setup_client)

    legacy_response = _legacy_client(bus_client).get("/app/system/state")
    assert legacy_response.status_code == 401
    assert legacy_response.json() == {"error": "auth_required"}

    auth_response = _auth_only_client(bus_client, auth_token).get("/app/system/state")
    assert auth_response.status_code == 200
    assert "status" in auth_response.json()


def test_claimed_session_token_does_not_create_legacy_bypass(bus_client):
    _setup_owner(bus_client["client"])
    client = _anonymous_client(bus_client)

    token_response = client.get("/session/token")
    assert token_response.status_code == 401
    assert token_response.json() == {"error": "login_required"}
    assert token_response.cookies.get("bus_session") is None

    app_response = client.get("/app/system/state")
    assert app_response.status_code == 401
    assert app_response.json() == {"error": "auth_required"}


def test_claimed_mode_rejects_revoked_auth_session(bus_client):
    setup_client = bus_client["client"]
    models = bus_client["models"]
    engine_module = bus_client["engine"]
    _setup_owner(setup_client)
    auth_token = _auth_token_from_client(setup_client)
    with engine_module.SessionLocal() as db:
        session = db.scalar(select(models.AuthSession).where(models.AuthSession.session_hash == hash_session_token(auth_token)))
        assert session is not None
        session.revoked_at = datetime.utcnow()
        db.commit()

    response = _auth_only_client(bus_client, auth_token).get("/app/system/state")

    assert response.status_code == 401
    assert response.json() == {"error": "auth_required"}


def test_claimed_mode_rejects_expired_auth_session(bus_client):
    setup_client = bus_client["client"]
    models = bus_client["models"]
    engine_module = bus_client["engine"]
    _setup_owner(setup_client)
    auth_token = _auth_token_from_client(setup_client)
    with engine_module.SessionLocal() as db:
        session = db.scalar(select(models.AuthSession).where(models.AuthSession.session_hash == hash_session_token(auth_token)))
        assert session is not None
        session.expires_at = datetime.utcnow() - timedelta(minutes=1)
        db.commit()

    response = _auth_only_client(bus_client, auth_token).get("/app/system/state")

    assert response.status_code == 401
    assert response.json() == {"error": "auth_required"}


def test_claimed_mode_rejects_auth_session_older_than_max_age(bus_client):
    setup_client = bus_client["client"]
    models = bus_client["models"]
    engine_module = bus_client["engine"]
    _setup_owner(setup_client)
    auth_token = _auth_token_from_client(setup_client)
    with engine_module.SessionLocal() as db:
        session = db.scalar(select(models.AuthSession).where(models.AuthSession.session_hash == hash_session_token(auth_token)))
        assert session is not None
        session.created_at = datetime.utcnow() - timedelta(days=AUTH_SESSION_MAX_AGE_DAYS, minutes=1)
        session.last_seen_at = datetime.utcnow()
        session.expires_at = datetime.utcnow() + timedelta(days=1)
        db.commit()

    response = _auth_only_client(bus_client, auth_token).get("/app/system/state")

    assert response.status_code == 401
    assert response.json() == {"error": "auth_required"}


def test_claimed_mode_rejects_idle_timed_out_auth_session(bus_client):
    setup_client = bus_client["client"]
    models = bus_client["models"]
    engine_module = bus_client["engine"]
    _setup_owner(setup_client)
    auth_token = _auth_token_from_client(setup_client)
    with engine_module.SessionLocal() as db:
        session = db.scalar(select(models.AuthSession).where(models.AuthSession.session_hash == hash_session_token(auth_token)))
        assert session is not None
        session.created_at = datetime.utcnow() - timedelta(minutes=30)
        session.last_seen_at = datetime.utcnow() - timedelta(minutes=AUTH_SESSION_IDLE_TIMEOUT_MINUTES, seconds=1)
        session.expires_at = datetime.utcnow() + timedelta(days=1)
        db.commit()

    response = _auth_only_client(bus_client, auth_token).get("/app/system/state")

    assert response.status_code == 401
    assert response.json() == {"error": "auth_required"}


def test_active_session_touches_last_seen_after_touch_interval(bus_client):
    setup_client = bus_client["client"]
    models = bus_client["models"]
    engine_module = bus_client["engine"]
    _setup_owner(setup_client)
    auth_token = _auth_token_from_client(setup_client)
    original_seen = datetime.utcnow() - timedelta(minutes=AUTH_SESSION_TOUCH_INTERVAL_MINUTES, seconds=1)
    with engine_module.SessionLocal() as db:
        session = db.scalar(select(models.AuthSession).where(models.AuthSession.session_hash == hash_session_token(auth_token)))
        assert session is not None
        session.last_seen_at = original_seen
        db.commit()

    response = _auth_only_client(bus_client, auth_token).get("/app/system/state")

    assert response.status_code == 200
    with engine_module.SessionLocal() as db:
        session = db.scalar(select(models.AuthSession).where(models.AuthSession.session_hash == hash_session_token(auth_token)))
        assert session is not None
        assert session.last_seen_at is not None
        assert session.last_seen_at > original_seen


def test_active_session_does_not_touch_inside_touch_interval(bus_client):
    setup_client = bus_client["client"]
    models = bus_client["models"]
    engine_module = bus_client["engine"]
    _setup_owner(setup_client)
    auth_token = _auth_token_from_client(setup_client)
    original_seen = datetime.utcnow().replace(microsecond=0) - timedelta(minutes=1)
    with engine_module.SessionLocal() as db:
        session = db.scalar(select(models.AuthSession).where(models.AuthSession.session_hash == hash_session_token(auth_token)))
        assert session is not None
        session.last_seen_at = original_seen
        db.commit()

    response = _auth_only_client(bus_client, auth_token).get("/app/system/state")

    assert response.status_code == 200
    with engine_module.SessionLocal() as db:
        session = db.scalar(select(models.AuthSession).where(models.AuthSession.session_hash == hash_session_token(auth_token)))
        assert session is not None
        assert session.last_seen_at == original_seen


def test_reauth_login_creates_new_valid_session_after_revocation(bus_client):
    setup_client = bus_client["client"]
    models = bus_client["models"]
    engine_module = bus_client["engine"]
    _setup_owner(setup_client)
    old_token = _auth_token_from_client(setup_client)
    with engine_module.SessionLocal() as db:
        session = db.scalar(select(models.AuthSession).where(models.AuthSession.session_hash == hash_session_token(old_token)))
        assert session is not None
        session.revoked_at = datetime.utcnow()
        db.commit()

    response = _anonymous_client(bus_client).post(
        "/auth/login",
        json={"username": "owner", "password": "correct horse battery staple"},
    )

    assert response.status_code == 200, response.text
    new_token = response.cookies.get(AUTH_SESSION_COOKIE)
    assert new_token and new_token != old_token
    assert _auth_only_client(bus_client, str(new_token)).get("/app/system/state").status_code == 200


def test_recovery_code_resets_password_burns_code_revokes_sessions_and_audits(bus_client):
    setup_client = bus_client["client"]
    models = bus_client["models"]
    engine_module = bus_client["engine"]
    setup = _setup_owner(setup_client)
    old_token = _auth_token_from_client(setup_client)
    recovery_code = setup["recovery_codes"][0]

    response = _anonymous_client(bus_client).post(
        "/auth/recover",
        json={"username": "OWNER", "recovery_code": recovery_code, "new_password": "new secure password"},
    )

    assert response.status_code == 200, response.text
    assert response.json() == {"ok": True, "login_required": True}
    assert "recovery_codes" not in response.text
    assert response.cookies.get(AUTH_SESSION_COOKIE) is None
    assert _auth_only_client(bus_client, old_token).get("/app/system/state").status_code == 401
    assert _anonymous_client(bus_client).post(
        "/auth/login",
        json={"username": "owner", "password": "correct horse battery staple"},
    ).status_code == 401
    assert _anonymous_client(bus_client).post(
        "/auth/login",
        json={"username": "owner", "password": "new secure password"},
    ).status_code == 200

    with engine_module.SessionLocal() as db:
        user = db.scalar(select(models.AuthUser).where(models.AuthUser.username_norm == "owner"))
        assert user is not None
        used_code = db.scalar(
            select(models.AuthRecoveryCode).where(
                models.AuthRecoveryCode.user_id == user.id,
                models.AuthRecoveryCode.used_at.is_not(None),
            )
        )
        assert used_code is not None
        assert recovery_code not in used_code.code_hash
        old_session = db.scalar(select(models.AuthSession).where(models.AuthSession.session_hash == hash_session_token(old_token)))
        assert old_session is not None
        assert old_session.revoked_at is not None
        event = db.scalar(select(models.AuthAuditEvent).where(models.AuthAuditEvent.action == "auth.recovery_used"))
        assert event is not None
        detail = json.loads(event.detail_json or "{}")
        assert "recovery" not in event.detail_json
        assert "code" not in event.detail_json
        assert detail["revoked_sessions"] >= 1


def test_used_recovery_code_cannot_be_reused_and_failures_are_generic(bus_client):
    setup_client = bus_client["client"]
    setup = _setup_owner(setup_client)
    code = setup["recovery_codes"][0]
    recover_client = _anonymous_client(bus_client)
    assert recover_client.post(
        "/auth/recover",
        json={"username": "owner", "recovery_code": code, "new_password": "first new password"},
    ).status_code == 200

    reused = recover_client.post(
        "/auth/recover",
        json={"username": "owner", "recovery_code": code, "new_password": "second new password"},
    )
    wrong_user = recover_client.post(
        "/auth/recover",
        json={"username": "not-owner", "recovery_code": code, "new_password": "second new password"},
    )
    wrong_code = recover_client.post(
        "/auth/recover",
        json={"username": "owner", "recovery_code": "WRONG-CODE", "new_password": "second new password"},
    )

    assert reused.status_code == 401
    assert reused.json() == {"detail": {"error": "recovery_failed"}}
    assert wrong_user.status_code == 401
    assert wrong_user.json() == reused.json()
    assert wrong_code.status_code == 401
    assert wrong_code.json() == reused.json()


def test_recovery_rate_limit_blocks_repeated_failures_with_generic_response(bus_client):
    _setup_owner(bus_client["client"])
    client = _anonymous_client(bus_client)
    generic_body = {"detail": {"error": "recovery_failed"}}
    for index in range(5):
        response = client.post(
            "/auth/recover",
            json={"username": "owner", "recovery_code": f"WRONG-{index}", "new_password": "new secure password"},
        )
        assert response.status_code == 401
        assert response.json() == generic_body

    locked = client.post(
        "/auth/recover",
        json={"username": "owner", "recovery_code": "ALSO-WRONG", "new_password": "new secure password"},
    )

    assert locked.status_code == 401
    assert locked.json() == generic_body


def test_recovery_code_regeneration_invalidates_old_unused_codes_and_audits(bus_client):
    setup_client = bus_client["client"]
    models = bus_client["models"]
    engine_module = bus_client["engine"]
    setup = _setup_owner(setup_client)
    old_code = setup["recovery_codes"][1]

    response = setup_client.post("/auth/recovery-codes/regenerate", json={})

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["ok"] is True
    assert len(payload["recovery_codes"]) == RECOVERY_CODE_COUNT
    assert old_code not in payload["recovery_codes"]
    assert "code_hash" not in response.text

    audit_response = setup_client.get("/app/audit")
    assert audit_response.status_code == 200, audit_response.text
    assert old_code not in audit_response.text
    assert payload["recovery_codes"][0] not in audit_response.text
    assert "code_hash" not in audit_response.text

    old_recovery = _anonymous_client(bus_client).post(
        "/auth/recover",
        json={"username": "owner", "recovery_code": old_code, "new_password": "new secure password"},
    )
    assert old_recovery.status_code == 401
    assert old_recovery.json() == {"detail": {"error": "recovery_failed"}}

    new_recovery = _anonymous_client(bus_client).post(
        "/auth/recover",
        json={"username": "owner", "recovery_code": payload["recovery_codes"][0], "new_password": "new secure password"},
    )
    assert new_recovery.status_code == 200, new_recovery.text

    with engine_module.SessionLocal() as db:
        event = db.scalar(
            select(models.AuthAuditEvent).where(models.AuthAuditEvent.action == "auth.recovery_codes_regenerated")
        )
        assert event is not None
        assert "recovery_codes" not in (event.detail_json or "")
        assert "code_hash" not in (event.detail_json or "")


def test_unclaimed_session_token_behavior_remains_unchanged(bus_client):
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
