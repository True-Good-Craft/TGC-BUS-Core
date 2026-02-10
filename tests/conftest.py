# Copyright (C) 2025 BUS Core Authors
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

import sys
import importlib
import os
from pathlib import Path

import pytest

# Ensure local stub packages (e.g., httpx) are importable during tests
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


BUS_MODULES_TO_RESET = [
    "core.api.http",
    "core.api.routes.finance_api",
    "core.api.routes.items",
    "core.api.routes.ledger_api",
    "core.api.routes.manufacturing",
    "core.api.routes.vendors",
    "core.appdb.engine",
    "core.appdb.ledger",
    "core.appdb.models",
    "core.appdb.models_recipes",
    "core.appdb.session",
    "core.journal.inventory",
    "core.journal.manufacturing",
    "core.manufacturing.service",
    "core.services.models",
    "tgc.settings",
    "tgc.state",
]


def reset_bus_modules(module_names: list[str]) -> None:
    for module_name in module_names:
        sys.modules.pop(module_name, None)


@pytest.fixture()
def bus_db_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db_path = tmp_path / "app.db"
    monkeypatch.setenv("BUS_DB", str(db_path))
    return db_path


@pytest.fixture()
def bus_app_state():
    def _apply(api_http):
        from tgc.settings import Settings
        from tgc.state import init_state

        api_http.app.state.app_state = init_state(Settings())
        return api_http.app.state.app_state

    return _apply


@pytest.fixture()
def bus_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest, bus_db_path, bus_app_state):
    bus_dev = None
    marker = request.node.get_closest_marker("bus_dev")
    if marker and marker.args:
        bus_dev = str(marker.args[0])
    if hasattr(request, "param"):
        bus_dev = str(request.param)
    if bus_dev is None:
        bus_dev = os.getenv("BUS_DEV", "0")
    monkeypatch.setenv("BUS_DEV", bus_dev)
    if not os.getenv("BUS_INVENTORY_JOURNAL"):
        monkeypatch.setenv("BUS_INVENTORY_JOURNAL", str(tmp_path / "journals" / "inventory.jsonl"))
    if not os.getenv("BUS_MANUFACTURING_JOURNAL"):
        monkeypatch.setenv("BUS_MANUFACTURING_JOURNAL", str(tmp_path / "journals" / "manufacturing.jsonl"))

    reset_bus_modules(BUS_MODULES_TO_RESET)

    import core.appdb.engine as engine_module
    import core.appdb.ledger as ledger_module
    import core.appdb.models as models_module
    import core.appdb.models_recipes as recipes_module
    import core.services.models as services_models
    import core.api.http as api_http

    engine_module = importlib.reload(engine_module)
    ledger_module = importlib.reload(ledger_module)
    models_module = importlib.reload(models_module)
    recipes_module = importlib.reload(recipes_module)
    services_models = importlib.reload(services_models)
    api_http = importlib.reload(api_http)

    bus_app_state(api_http)
    api_http.app.state.allow_writes = True

    models_module.Base.metadata.create_all(bind=engine_module.ENGINE)

    from core.config.writes import set_writes_enabled

    set_writes_enabled(True)

    from fastapi.testclient import TestClient

    client = TestClient(api_http.APP)
    session_token = api_http._load_or_create_token()
    api_http.app.state.app_state.tokens._rec.token = session_token
    client.headers.update({"Cookie": f"bus_session={session_token}"})

    env = {
        "client": client,
        "engine": engine_module,
        "models": models_module,
        "api_http": api_http,
        "recipes": recipes_module,
        "ledger": ledger_module,
    }
    try:
        yield env
    finally:
        set_writes_enabled(False)
        api_http.app.state.allow_writes = False
