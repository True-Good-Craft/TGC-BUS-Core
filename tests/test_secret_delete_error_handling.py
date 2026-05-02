# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import pytest
from fastapi import HTTPException
from starlette.responses import Response

from core.api import http as api_http
from core.secrets.manager import SecretError

pytestmark = pytest.mark.unit


def test_settings_google_delete_tolerates_missing_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        api_http.Secrets,
        "delete",
        lambda _plugin_id, _key: (_ for _ in ()).throw(SecretError("Secret not found")),
    )

    assert api_http.settings_google_delete(Response()) == {"ok": True}


def test_settings_google_delete_uses_controlled_error_on_delete_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        api_http.Secrets,
        "delete",
        lambda _plugin_id, _key: (_ for _ in ()).throw(SecretError("Secret delete failed")),
    )

    with pytest.raises(HTTPException) as exc_info:
        api_http.settings_google_delete(Response())

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "secret_delete_error"


def test_oauth_revoke_uses_controlled_error_on_delete_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(api_http.Secrets, "get", lambda _plugin_id, _key: "refresh-token")
    monkeypatch.setattr(api_http.requests, "post", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        api_http.Secrets,
        "delete",
        lambda _plugin_id, _key: (_ for _ in ()).throw(SecretError("Secret delete failed")),
    )

    with pytest.raises(HTTPException) as exc_info:
        api_http.oauth_google_revoke()

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "secret_delete_error"