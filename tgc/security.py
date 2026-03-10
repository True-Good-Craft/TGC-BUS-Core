# Copyright (C) 2025 BUS Core Authors
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

from fastapi import Request, Response


async def require_token_ctx(request: Request):
    # Compatibility wrapper: core.api.http owns request auth validation.
    from core.api.http import require_token_ctx as canonical_require_token_ctx

    canonical_require_token_ctx(request)
    return None  # context placeholder


def set_session_cookie(resp: Response, token: str, s) -> None:
    # starlette expects lowercase for samesite
    same_site = (getattr(s, "same_site", "lax") or "lax").lower()
    resp.set_cookie(
        key=s.session_cookie_name,
        value=token,
        httponly=True,
        samesite=same_site,
        secure=bool(getattr(s, "secure_cookie", False)),
        path="/",
        max_age=7 * 24 * 3600,
    )


# Back-compat alias for older imports
attach_session_cookie = set_session_cookie
