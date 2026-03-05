# SPDX-License-Identifier: AGPL-3.0-or-later

import importlib
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

pytestmark = pytest.mark.unit


def test_app_db_path_creates_directory(tmp_path, monkeypatch):
    import core.appdb.paths as appdb_paths

    local_app_data = tmp_path / "LocalAppData"
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))

    importlib.reload(appdb_paths)

    db_path = appdb_paths.app_db_path()

    assert db_path == local_app_data / "BUSCore" / "app" / "app.db"
    assert db_path.parent == local_app_data / "BUSCore" / "app"


def test_resolve_db_path_defaults_to_demo(tmp_path, monkeypatch):
    import core.appdata.paths as appdata_paths

    local_app_data = tmp_path / "LocalAppData"
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))
    monkeypatch.delenv("BUS_DB", raising=False)
    monkeypatch.delenv("BUS_MODE", raising=False)

    appdata_paths = importlib.reload(appdata_paths)

    assert appdata_paths.resolve_bus_mode() == "demo"
    assert Path(appdata_paths.resolve_db_path()).name == "app_demo.db"


def test_resolve_bus_mode_priority_config_over_env_and_flag(tmp_path, monkeypatch):
    import core.appdata.paths as appdata_paths

    local_app_data = tmp_path / "LocalAppData"
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))
    monkeypatch.setenv("BUS_MODE", "prod")
    monkeypatch.delenv("BUS_DB", raising=False)

    appdata_paths = importlib.reload(appdata_paths)
    app_root = appdata_paths.app_root()
    app_root.mkdir(parents=True, exist_ok=True)

    (app_root / "bus_mode.flag").write_text("prod", encoding="utf-8")
    (app_root / "bus_mode.json").write_text(json.dumps({"BUS_MODE": "demo"}), encoding="utf-8")

    appdata_paths = importlib.reload(appdata_paths)

    assert appdata_paths.resolve_bus_mode() == "demo"
    assert Path(appdata_paths.resolve_db_path()).name == "app_demo.db"


def test_resolve_bus_mode_priority_env_over_flag(tmp_path, monkeypatch):
    import core.appdata.paths as appdata_paths

    local_app_data = tmp_path / "LocalAppData"
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))
    monkeypatch.setenv("BUS_MODE", "prod")
    monkeypatch.delenv("BUS_DB", raising=False)

    appdata_paths = importlib.reload(appdata_paths)
    app_root = appdata_paths.app_root()
    app_root.mkdir(parents=True, exist_ok=True)

    (app_root / "bus_mode.flag").write_text("demo", encoding="utf-8")
    cfg = app_root / "bus_mode.json"
    cfg.unlink(missing_ok=True)

    appdata_paths = importlib.reload(appdata_paths)

    assert appdata_paths.resolve_bus_mode() == "prod"
    assert Path(appdata_paths.resolve_db_path()).name == "app.db"


def test_resolve_bus_mode_defaults_prod_when_bus_db_set(tmp_path, monkeypatch):
    import core.appdata.paths as appdata_paths

    local_app_data = tmp_path / "LocalAppData"
    explicit_db = tmp_path / "custom" / "explicit.db"
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))
    monkeypatch.setenv("BUS_DB", str(explicit_db))
    monkeypatch.delenv("BUS_MODE", raising=False)

    appdata_paths = importlib.reload(appdata_paths)

    assert appdata_paths.resolve_bus_mode() == "prod"
    assert Path(appdata_paths.resolve_db_path()) == explicit_db.resolve()


def test_db_url_uses_posix(monkeypatch, tmp_path):
    local_app_data = tmp_path / "LocalAppData"
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))
    monkeypatch.delenv("BUS_ROOT", raising=False)
    monkeypatch.delenv("BUS_DB", raising=False)
    monkeypatch.delenv("BUS_MODE", raising=False)

    import core.config.paths as config_paths

    importlib.reload(config_paths)

    assert config_paths.DB_PATH.name == "app_demo.db"
    assert config_paths.DB_URL.drivername == "sqlite+pysqlite"
    assert config_paths.DB_URL.get_backend_name() == "sqlite"
    assert config_paths.DB_URL.database == config_paths.DB_PATH.as_posix()
