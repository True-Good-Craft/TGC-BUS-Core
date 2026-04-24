# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import importlib
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_missing_update_config_defaults_to_enabled_startup_checks(tmp_path, monkeypatch):
    import core.appdata.paths as appdata_paths
    import core.config.manager as config_manager

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "LocalAppData"))

    importlib.reload(appdata_paths)
    config_manager = importlib.reload(config_manager)

    cfg = config_manager.load_config()

    assert cfg.updates.enabled is True
    assert cfg.updates.check_on_startup is True


def test_explicit_update_opt_out_values_are_preserved(tmp_path, monkeypatch):
    import core.appdata.paths as appdata_paths
    import core.config.manager as config_manager

    local_app_data = tmp_path / "LocalAppData"
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))

    importlib.reload(appdata_paths)
    config_manager = importlib.reload(config_manager)

    config_path = local_app_data / "BUSCore" / "config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        '{"updates":{"enabled":false,"check_on_startup":false}}',
        encoding="utf-8",
    )

    cfg = config_manager.load_config()

    assert cfg.updates.enabled is False
    assert cfg.updates.check_on_startup is False


def test_update_startup_policy_is_opt_out_and_no_hidden_polling():
    update_js = (REPO_ROOT / "core" / "ui" / "js" / "update-check.js").read_text(encoding="utf-8")

    assert "updates.enabled !== false && updates.check_on_startup !== false" in update_js
    assert "return apiGet('/app/update/check');" in update_js
    assert "runSidebarManualUpdateCheck();" in update_js
    assert "window.setInterval" not in update_js
    assert "AUTO_TIMER_MS" not in update_js
    assert "STALE_AFTER_MS" not in update_js
    assert "bus.updates.last_success_ms" not in update_js


def test_settings_update_checkbox_defaults_to_enabled_unless_explicitly_disabled():
    settings_js = (REPO_ROOT / "core" / "ui" / "js" / "cards" / "settings.js").read_text(encoding="utf-8")

    assert "updates.enabled !== false" in settings_js
    assert "updates.check_on_startup !== false" in settings_js
    assert "check_on_startup: checkOnStartup" in settings_js
    assert "check_on_startup: autoUpdatesEnabled" not in settings_js
    assert "runSidebarManualUpdateCheck" not in settings_js
