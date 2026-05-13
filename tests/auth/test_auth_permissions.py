from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select

from core.api.routes.auth import AUTH_SESSION_COOKIE
from core.auth.passwords import SCRYPT_SCHEME, hash_password
from core.auth.permissions import OPERATOR_ROLE_KEY, VIEWER_ROLE_KEY
from core.auth.store import normalize_username


OWNER_PASSWORD = "correct horse battery staple"


def _anonymous_client(bus_client) -> TestClient:
    return TestClient(bus_client["api_http"].APP)


def _legacy_session_token(bus_client) -> str:
    return bus_client["api_http"].app.state.app_state.tokens.current()


def _setup_owner(client: TestClient) -> str:
    response = client.post(
        "/auth/setup-owner",
        json={"username": "owner", "password": OWNER_PASSWORD},
    )
    assert response.status_code == 200, response.text
    token = response.cookies.get(AUTH_SESSION_COOKIE)
    assert token
    existing_cookie = client.headers.get("Cookie", "")
    if AUTH_SESSION_COOKIE not in existing_cookie:
        separator = "; " if existing_cookie else ""
        client.headers.update({"Cookie": f"{existing_cookie}{separator}{AUTH_SESSION_COOKIE}={token}"})
    return str(token)


def _create_user_with_role(bus_client, username: str, role_key: str, password: str = OWNER_PASSWORD) -> None:
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
        )
        db.add(user)
        db.flush()
        db.add(models.AuthUserRole(user_id=int(user.id), role_id=int(role.id)))
        db.commit()


def _login(bus_client, username: str, password: str = OWNER_PASSWORD) -> TestClient:
    client = _anonymous_client(bus_client)
    response = client.post("/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    token = response.cookies.get(AUTH_SESSION_COOKIE)
    assert token
    client.headers.update({"Cookie": f"{AUTH_SESSION_COOKIE}={token}"})
    return client


def test_claimed_owner_can_access_representative_permission_families(bus_client):
    client = bus_client["client"]
    _setup_owner(client)

    cases = [
        ("get", "/app/items", {}),
        ("get", "/app/ledger/history", {}),
        ("get", "/app/recipes", {}),
        ("get", "/app/manufacturing/runs", {}),
        ("get", "/app/vendors", {}),
        ("get", "/app/finance/summary", {"params": {"from": "2026-01-01", "to": "2026-01-31"}}),
        ("get", "/app/logs", {}),
        ("get", "/app/config", {}),
        ("get", "/app/update/check", {}),
        ("get", "/app/system/state", {}),
        ("get", "/logs", {}),
    ]

    for method, path, kwargs in cases:
        response = getattr(client, method)(path, **kwargs)
        assert response.status_code == 200, f"{method.upper()} {path}: {response.text}"


def test_claimed_viewer_can_read_but_cannot_write_inventory_finance_or_settings(bus_client):
    _setup_owner(bus_client["client"])
    _create_user_with_role(bus_client, "viewer", VIEWER_ROLE_KEY)
    client = _login(bus_client, "viewer")

    read_cases = [
        ("/app/items", {}),
        ("/app/finance/summary", {"params": {"from": "2026-01-01", "to": "2026-01-31"}}),
        ("/app/config", {}),
        ("/app/logs", {}),
    ]
    for path, kwargs in read_cases:
        response = client.get(path, **kwargs)
        assert response.status_code == 200, f"GET {path}: {response.text}"

    denied_cases = [
        ("/app/items", {"name": "Blocked item", "dimension": "count", "uom": "ea"}),
        ("/app/finance/expense", {"amount_cents": 1}),
        ("/app/config", {"ui": {"theme": "system"}}),
    ]
    for path, payload in denied_cases:
        response = client.post(path, json=payload)
        assert response.status_code == 403, f"POST {path}: {response.text}"
        assert response.json()["detail"]["error"] == "permission_denied"


def test_claimed_operator_can_use_inventory_and_manufacturing_but_not_finance_or_admin(bus_client):
    _setup_owner(bus_client["client"])
    _create_user_with_role(bus_client, "operator", OPERATOR_ROLE_KEY)
    client = _login(bus_client, "operator")

    item_response = client.post(
        "/app/items",
        json={"name": "Operator item", "dimension": "count", "uom": "ea"},
    )
    assert item_response.status_code == 200, item_response.text

    runs_response = client.get("/app/manufacturing/runs")
    assert runs_response.status_code == 200, runs_response.text

    invalid_run_response = client.post("/app/manufacture", json={})
    assert invalid_run_response.status_code == 400, invalid_run_response.text

    denied_cases = [
        ("/app/finance/expense", {"amount_cents": 1}),
        ("/app/config", {"ui": {"theme": "system"}}),
        ("/server/restart", {}),
    ]
    for path, payload in denied_cases:
        response = client.post(path, json=payload)
        assert response.status_code == 403, f"POST {path}: {response.text}"
        assert response.json()["detail"]["error"] == "permission_denied"


def test_claimed_missing_session_gets_401_before_permission_check(bus_client):
    _setup_owner(bus_client["client"])
    client = _anonymous_client(bus_client)

    response = client.get("/app/items")

    assert response.status_code == 401
    assert response.json() == {"error": "auth_required"}


def test_unclaimed_mode_keeps_legacy_permission_compatibility(bus_client):
    client = _anonymous_client(bus_client)

    token_response = client.get("/session/token")
    assert token_response.status_code == 200
    token = token_response.json()["token"]

    response = client.get("/app/items", headers={"Cookie": f"bus_session={token}"})

    assert response.status_code == 200


def test_claimed_legacy_session_still_cannot_reach_permissioned_route(bus_client):
    _setup_owner(bus_client["client"])
    legacy_token = _legacy_session_token(bus_client)
    client = _anonymous_client(bus_client)

    response = client.get("/app/items", headers={"Cookie": f"bus_session={legacy_token}"})

    assert response.status_code == 401
    assert response.json() == {"error": "auth_required"}
