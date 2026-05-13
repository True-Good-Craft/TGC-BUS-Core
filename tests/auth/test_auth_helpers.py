# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import json

from core.auth.audit import create_audit_event
from core.auth.passwords import SCRYPT_SCHEME, hash_password, password_scheme, verify_password
from core.auth.permissions import (
    OPERATOR_ROLE_KEY,
    OWNER_ROLE_KEY,
    PERMISSION_ADMIN_USERS,
    PERMISSION_INVENTORY_READ,
    VIEWER_ROLE_KEY,
    default_role_bundles,
)
from core.auth.sessions import hash_session_token
from core.auth.store import normalize_username


def test_password_hash_verifies_correct_password_and_records_scheme():
    encoded = hash_password("correct horse battery staple")

    assert encoded.startswith(f"{SCRYPT_SCHEME}$")
    assert password_scheme(encoded) == SCRYPT_SCHEME
    assert verify_password("correct horse battery staple", encoded) is True


def test_password_hash_rejects_wrong_password():
    encoded = hash_password("correct horse battery staple")

    assert verify_password("wrong password", encoded) is False
    assert verify_password("correct horse battery staple", "not-a-valid-hash") is False


def test_session_token_hash_is_deterministic_and_hides_raw_token():
    token = "raw-session-token-for-test"

    first = hash_session_token(token)
    second = hash_session_token(token)

    assert first == second
    assert first.startswith("sha256-v1$")
    assert token not in first


def test_default_permissions_and_roles_are_deterministic():
    first = default_role_bundles()
    second = default_role_bundles()

    assert first == second
    assert tuple(first) == (OWNER_ROLE_KEY, OPERATOR_ROLE_KEY, VIEWER_ROLE_KEY)
    assert PERMISSION_ADMIN_USERS in first[OWNER_ROLE_KEY]
    assert PERMISSION_INVENTORY_READ in first[VIEWER_ROLE_KEY]
    for permissions in first.values():
        assert permissions == tuple(sorted(permissions))


def test_username_normalization_is_stable():
    assert normalize_username("  Owner.Name  ") == "owner.name"
    assert normalize_username("OWNER   NAME") == "owner name"


def test_audit_event_helper_adds_sorted_detail_json(bus_client):
    engine_module = bus_client["engine"]
    bus_client["api_http"].startup_migrations()

    with engine_module.SessionLocal() as db:
        event = create_audit_event(
            db,
            action="owner.setup",
            target_type="user",
            target_id="1",
            request_id="req-1",
            detail={"b": 2, "a": 1},
        )
        db.flush()

        assert event.id is not None
        assert event.action == "owner.setup"
        assert json.loads(event.detail_json or "{}") == {"a": 1, "b": 2}
        assert event.detail_json == '{"a":1,"b":2}'
