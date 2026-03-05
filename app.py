# SPDX-License-Identifier: AGPL-3.0-or-later
"""BUS Core entry point."""

from __future__ import annotations

import sys
import uuid
from pathlib import Path
from typing import Iterable

from fastapi.responses import Response

from core.api.app_router import router as app_router
from core.api.http import APP as app
from core.version import VERSION
from tgc.cli_main import main as cli_main


def _has_domain_routes(routes: Iterable[object]) -> bool:
    for route in routes:
        path = getattr(route, "path", "")
        if isinstance(path, str) and path.startswith("/app/"):
            return True
    return False


if not _has_domain_routes(app.router.routes):
    app.include_router(app_router, prefix="/app")

@app.get("/session/token")
async def get_session_token() -> Response:
    token = str(uuid.uuid4())
    response = Response(content=token)
    response.set_cookie(
        key="X-Session-Token",
        value=token,
        httponly=True,
        samesite="lax",
    )
    data_dir = Path("data")
    data_dir.mkdir(parents=True, exist_ok=True)
    with open(data_dir / "session_token.txt", "w", encoding="utf-8") as file:
        file.write(token)
    return response

print(f"TGC Controller — version {VERSION}")


def main() -> int:
    return cli_main()


__all__ = ["app", "main"]


if __name__ == "__main__":
    sys.exit(main())
