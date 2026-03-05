# SPDX-License-Identifier: AGPL-3.0-or-later

from fastapi.staticfiles import StaticFiles

from core.api.http import APP as app

app.mount("/license", StaticFiles(directory="license"), name="license")

__all__ = ["app"]

