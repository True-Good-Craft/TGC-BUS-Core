# SPDX-License-Identifier: AGPL-3.0-or-later

import importlib
import json
from pathlib import Path

import pytest

from core.policy.model import Policy, Role

pytestmark = pytest.mark.unit


def _local_app_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    local_app_data = tmp_path / "LocalAppData"
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))
    return local_app_data


def _canonical_config(local_app_data: Path) -> Path:
    return local_app_data / "BUSCore" / "config.json"


def _legacy_config(local_app_data: Path) -> Path:
    return local_app_data / "BUSCore" / "app" / "config.json"


@pytest.fixture()
def real_localappdata_sentinel(tmp_path_factory, monkeypatch: pytest.MonkeyPatch):
    real_local_app_data = tmp_path_factory.mktemp("real-localappdata")
    sentinel_path = _canonical_config(real_local_app_data)
    sentinel_path.parent.mkdir(parents=True, exist_ok=True)
    sentinel_payload = {
        "dev": {"writes_enabled": False},
        "sentinel": "real-appdata-must-not-change",
    }
    sentinel_text = json.dumps(sentinel_payload, indent=2, sort_keys=True)
    sentinel_path.write_text(sentinel_text, encoding="utf-8")
    monkeypatch.setenv("LOCALAPPDATA", str(real_local_app_data))

    yield {
        "local_app_data": real_local_app_data,
        "path": sentinel_path,
        "text": sentinel_text,
    }

    assert sentinel_path.read_text(encoding="utf-8") == sentinel_text


@pytest.fixture()
def bus_client_after_real_localappdata(real_localappdata_sentinel, bus_client):
    return bus_client


def test_canonical_config_path_is_root_buscore_config(tmp_path, monkeypatch):
    import core.appdata.paths as appdata_paths

    local_app_data = _local_app_data(tmp_path, monkeypatch)
    appdata_paths = importlib.reload(appdata_paths)

    assert appdata_paths.config_path() == _canonical_config(local_app_data)


def test_set_writes_enabled_persists_only_to_canonical_config(tmp_path, monkeypatch):
    import core.config.manager as config_manager
    import core.config.writes as config_writes

    local_app_data = _local_app_data(tmp_path, monkeypatch)
    config_manager = importlib.reload(config_manager)
    config_writes = importlib.reload(config_writes)

    result = config_writes.set_writes_enabled(True)

    assert result == {"enabled": True}
    payload = json.loads(_canonical_config(local_app_data).read_text(encoding="utf-8"))
    assert payload["dev"]["writes_enabled"] is True
    assert not _legacy_config(local_app_data).exists()


def test_bus_client_isolates_write_gate_config_from_real_appdata(real_localappdata_sentinel, bus_client_after_real_localappdata):
    sentinel_path = real_localappdata_sentinel["path"]
    sentinel_text = real_localappdata_sentinel["text"]
    isolated_local_app_data = bus_client_after_real_localappdata["local_app_data"]
    isolated_config_path = _canonical_config(isolated_local_app_data)

    assert sentinel_path.read_text(encoding="utf-8") == sentinel_text
    assert isolated_local_app_data != real_localappdata_sentinel["local_app_data"]
    assert isolated_config_path.exists()

    payload = json.loads(isolated_config_path.read_text(encoding="utf-8"))
    assert payload["dev"]["writes_enabled"] is True


def test_policy_persists_in_canonical_config_without_expanding_public_config_shape(tmp_path, monkeypatch):
    import core.config.manager as config_manager
    import core.policy.store as policy_store

    local_app_data = _local_app_data(tmp_path, monkeypatch)
    config_manager = importlib.reload(config_manager)
    policy_store = importlib.reload(policy_store)

    policy_store.save_policy(Policy(role=Role.TESTER, plan_only=True))

    payload = json.loads(_canonical_config(local_app_data).read_text(encoding="utf-8"))
    assert payload["policy"] == {"role": "tester", "plan_only": True}
    assert "policy" not in config_manager.load_config().model_dump()
    assert not _legacy_config(local_app_data).exists()


def test_save_config_preserves_internal_policy_section(tmp_path, monkeypatch):
    import core.config.manager as config_manager
    import core.policy.store as policy_store

    local_app_data = _local_app_data(tmp_path, monkeypatch)
    config_manager = importlib.reload(config_manager)
    policy_store = importlib.reload(policy_store)

    policy_store.save_policy(Policy(role=Role.TESTER, plan_only=True))
    config_manager.save_config({"ui": {"theme": "dark"}})

    payload = json.loads(_canonical_config(local_app_data).read_text(encoding="utf-8"))
    assert payload["policy"] == {"role": "tester", "plan_only": True}
    assert payload["ui"]["theme"] == "dark"


def test_legacy_config_is_read_only_compatibility_input_when_canonical_values_absent(tmp_path, monkeypatch):
    import core.config.manager as config_manager
    import core.config.writes as config_writes
    import core.policy.store as policy_store

    local_app_data = _local_app_data(tmp_path, monkeypatch)
    legacy_path = _legacy_config(local_app_data)
    legacy_path.parent.mkdir(parents=True, exist_ok=True)
    legacy_path.write_text(
        json.dumps({"writes_enabled": True, "role": "tester", "plan_only": True}, indent=2),
        encoding="utf-8",
    )

    config_manager = importlib.reload(config_manager)
    config_writes = importlib.reload(config_writes)
    policy_store = importlib.reload(policy_store)

    assert config_writes.get_writes_enabled() is True
    assert config_manager.load_config().dev.writes_enabled is True
    assert policy_store.load_policy() == Policy(role=Role.TESTER, plan_only=True)
    assert not _canonical_config(local_app_data).exists()


def test_canonical_config_overrides_legacy_values_when_present(tmp_path, monkeypatch):
    import core.config.manager as config_manager
    import core.config.writes as config_writes
    import core.policy.store as policy_store

    local_app_data = _local_app_data(tmp_path, monkeypatch)
    canonical_path = _canonical_config(local_app_data)
    canonical_path.parent.mkdir(parents=True, exist_ok=True)
    canonical_path.write_text(
        json.dumps(
            {
                "dev": {"writes_enabled": False},
                "policy": {"role": "owner", "plan_only": False},
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    legacy_path = _legacy_config(local_app_data)
    legacy_path.parent.mkdir(parents=True, exist_ok=True)
    legacy_path.write_text(
        json.dumps({"writes_enabled": True, "role": "tester", "plan_only": True}, indent=2),
        encoding="utf-8",
    )

    config_manager = importlib.reload(config_manager)
    config_writes = importlib.reload(config_writes)
    policy_store = importlib.reload(policy_store)

    assert config_writes.get_writes_enabled() is False
    assert config_manager.load_config().dev.writes_enabled is False
    assert policy_store.load_policy() == Policy(role=Role.OWNER, plan_only=False)


def test_config_authority_drift_guards_cover_code_and_docs():
    repo_root = Path(__file__).resolve().parents[1]
    writes_module = (repo_root / "core" / "config" / "writes.py").read_text(encoding="utf-8")
    policy_store = (repo_root / "core" / "policy" / "store.py").read_text(encoding="utf-8")
    http_module = (repo_root / "core" / "api" / "http.py").read_text(encoding="utf-8")
    system_map = (repo_root / "01_SYSTEM_MAP.md").read_text(encoding="utf-8")
    data_map = (repo_root / "03_DATA_CONFIG_AND_STATE_MODEL.md").read_text(encoding="utf-8")
    security_map = (repo_root / "04_SECURITY_TRUST_AND_OPERATIONS.md").read_text(encoding="utf-8")
    sot = (repo_root / "SOT.md").read_text(encoding="utf-8")

    assert "core.config.paths" not in writes_module
    assert "core.config.paths" not in policy_store
    assert "get_writes_enabled()" in http_module
    assert "_calc_default_allow_writes()" not in http_module.split("def _buscore_writeflag_startup", 1)[1].split("def ensure_core_initialized", 1)[0]

    for doc in (system_map, data_map, security_map, sot):
        assert "%LOCALAPPDATA%\\BUSCore\\config.json" in doc
        assert "%LOCALAPPDATA%\\BUSCore\\app\\config.json" in doc

