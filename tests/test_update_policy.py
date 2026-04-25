# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import importlib
import json
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
    assert cfg.updates.channel == "stable"
    assert cfg.updates.manifest_url == "https://lighthouse.buscore.ca/update/check"
    assert cfg.updates.verified_launch_policy == "ask"


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


def test_valid_update_channels_are_accepted_on_save(tmp_path, monkeypatch):
    import core.appdata.paths as appdata_paths
    import core.config.manager as config_manager
    from core.config.update_policy import ALLOWED_UPDATE_CHANNELS

    local_app_data = tmp_path / "LocalAppData"
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))

    importlib.reload(appdata_paths)
    config_manager = importlib.reload(config_manager)

    for channel in ALLOWED_UPDATE_CHANNELS:
        config_manager.save_config({"updates": {"channel": channel}})
        assert config_manager.load_config().updates.channel == channel


def test_invalid_update_channel_is_rejected_on_save(tmp_path, monkeypatch):
    import core.appdata.paths as appdata_paths
    import core.config.manager as config_manager

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "LocalAppData"))

    importlib.reload(appdata_paths)
    config_manager = importlib.reload(config_manager)

    with pytest.raises(ValueError):
        config_manager.save_config({"updates": {"channel": "nightly"}})


def test_valid_verified_launch_policy_values_are_accepted_on_save(tmp_path, monkeypatch):
    import core.appdata.paths as appdata_paths
    import core.config.manager as config_manager

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "LocalAppData"))

    importlib.reload(appdata_paths)
    config_manager = importlib.reload(config_manager)

    for policy in ("ask", "always_newest", "current_only"):
        config_manager.save_config({"updates": {"verified_launch_policy": policy}})
        assert config_manager.load_config().updates.verified_launch_policy == policy


def test_invalid_verified_launch_policy_is_rejected_on_save(tmp_path, monkeypatch):
    import core.appdata.paths as appdata_paths
    import core.config.manager as config_manager

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "LocalAppData"))

    importlib.reload(appdata_paths)
    config_manager = importlib.reload(config_manager)

    with pytest.raises(ValueError):
        config_manager.save_config({"updates": {"verified_launch_policy": "latest"}})


def test_invalid_stored_verified_launch_policy_safely_loads_as_ask(tmp_path, monkeypatch):
    import core.appdata.paths as appdata_paths
    import core.config.manager as config_manager

    local_app_data = tmp_path / "LocalAppData"
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))

    importlib.reload(appdata_paths)
    config_manager = importlib.reload(config_manager)

    config_path = local_app_data / "BUSCore" / "config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps({"updates": {"verified_launch_policy": "latest"}}), encoding="utf-8")

    assert config_manager.load_config().updates.verified_launch_policy == "ask"


def test_invalid_stored_update_channel_is_safely_loaded_as_stable(tmp_path, monkeypatch):
    import core.appdata.paths as appdata_paths
    import core.config.manager as config_manager

    local_app_data = tmp_path / "LocalAppData"
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))

    importlib.reload(appdata_paths)
    config_manager = importlib.reload(config_manager)

    config_path = local_app_data / "BUSCore" / "config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps({"updates": {"channel": "nightly"}}), encoding="utf-8")

    assert config_manager.load_config().updates.channel == "stable"


def test_invalid_stored_update_config_does_not_block_unrelated_save(tmp_path, monkeypatch):
    import core.appdata.paths as appdata_paths
    import core.config.manager as config_manager

    local_app_data = tmp_path / "LocalAppData"
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))
    monkeypatch.setenv("BUS_DEV", "0")
    monkeypatch.delenv("BUS_ALLOW_DEV_UPDATE_MANIFEST_URLS", raising=False)

    importlib.reload(appdata_paths)
    config_manager = importlib.reload(config_manager)

    config_path = local_app_data / "BUSCore" / "config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        json.dumps({"updates": {"channel": "nightly", "manifest_url": "file:///etc/passwd"}}),
        encoding="utf-8",
    )

    config_manager.save_config({"ui": {"theme": "dark"}})

    cfg = config_manager.load_config()
    assert cfg.ui.theme == "dark"
    assert cfg.updates.channel == "stable"
    assert cfg.updates.manifest_url == "https://lighthouse.buscore.ca/update/check"


def test_unsafe_manifest_urls_are_rejected_on_save(tmp_path, monkeypatch):
    import core.appdata.paths as appdata_paths
    import core.config.manager as config_manager

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "LocalAppData"))
    monkeypatch.setenv("BUS_DEV", "0")
    monkeypatch.delenv("BUS_ALLOW_DEV_UPDATE_MANIFEST_URLS", raising=False)

    importlib.reload(appdata_paths)
    config_manager = importlib.reload(config_manager)

    for manifest_url in (
        "javascript:alert(1)",
        "file:///etc/passwd",
        "data:application/json,{}",
        "http://example.com/manifest.json",
        "http://localhost/manifest.json",
        "https://127.0.0.1/manifest.json",
    ):
        with pytest.raises(ValueError):
            config_manager.save_config({"updates": {"manifest_url": manifest_url}})


@pytest.mark.parametrize(
    "manifest_url",
    (
        "http://localhost/manifest.json",
        "https://localhost/manifest.json",
        "http://127.0.0.1/manifest.json",
        "http://192.168.1.10/manifest.json",
        "http://169.254.1.10/manifest.json",
        "http://0.0.0.0/manifest.json",
        "http://[::1]/manifest.json",
    ),
)
def test_blocked_manifest_hosts_return_not_allowed_policy_code(monkeypatch, manifest_url: str):
    from core.config.update_policy import UpdatePolicyError, validate_update_manifest_url

    monkeypatch.setenv("BUS_DEV", "0")
    monkeypatch.delenv("BUS_ALLOW_DEV_UPDATE_MANIFEST_URLS", raising=False)

    with pytest.raises(UpdatePolicyError) as exc_info:
        validate_update_manifest_url(manifest_url)

    assert exc_info.value.code == "manifest_url_not_allowed"


def test_public_http_manifest_url_still_returns_invalid_policy_code(monkeypatch):
    from core.config.update_policy import UpdatePolicyError, validate_update_manifest_url

    monkeypatch.setenv("BUS_DEV", "0")
    monkeypatch.delenv("BUS_ALLOW_DEV_UPDATE_MANIFEST_URLS", raising=False)

    with pytest.raises(UpdatePolicyError) as exc_info:
        validate_update_manifest_url("http://example.com/manifest.json")

    assert exc_info.value.code == "invalid_manifest_url"


def test_dev_mode_allows_local_manifest_url_on_save(tmp_path, monkeypatch):
    import core.appdata.paths as appdata_paths
    import core.config.manager as config_manager

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "LocalAppData"))
    monkeypatch.setenv("BUS_DEV", "1")

    importlib.reload(appdata_paths)
    config_manager = importlib.reload(config_manager)

    config_manager.save_config({"updates": {"manifest_url": "http://localhost:8765/manifest.json"}})

    assert config_manager.load_config().updates.manifest_url == "http://localhost:8765/manifest.json"


def test_invalid_stored_manifest_url_is_safely_loaded_as_default(tmp_path, monkeypatch):
    import core.appdata.paths as appdata_paths
    import core.config.manager as config_manager

    local_app_data = tmp_path / "LocalAppData"
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))
    monkeypatch.setenv("BUS_DEV", "0")
    monkeypatch.delenv("BUS_ALLOW_DEV_UPDATE_MANIFEST_URLS", raising=False)

    importlib.reload(appdata_paths)
    config_manager = importlib.reload(config_manager)

    config_path = local_app_data / "BUSCore" / "config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps({"updates": {"manifest_url": "file:///etc/passwd"}}), encoding="utf-8")

    assert config_manager.load_config().updates.manifest_url == "https://lighthouse.buscore.ca/update/check"


def test_update_service_selects_requested_partner_channel():
    from core.services.update import UpdateService

    service = UpdateService(
        fetch_manifest=lambda _url, _timeout: {
            "channels": {
                "stable": {
                    "latest": {
                        "version": "9.8.0",
                        "download": {"url": "https://example.test/stable-dl"},
                    },
                },
                "partner-3dque": {
                    "latest": {
                        "version": "9.9.9",
                        "download": {"url": "https://example.test/partner-dl"},
                    },
                },
            }
        }
    )

    result = service.check(manifest_url="https://example.test/manifest.json", channel="partner-3dque")

    assert result.error_code is None
    assert result.update_available is True
    assert result.download_url == "https://example.test/partner-dl"


def test_update_service_partner_channel_does_not_fall_back_to_channel_less_public_latest():
    from core.services.update import UpdateService

    service = UpdateService(
        fetch_manifest=lambda _url, _timeout: {
            "latest": {
                "version": "9.9.9",
                "download": {"url": "https://example.test/public-stable-dl"},
            },
        }
    )

    result = service.check(manifest_url="https://example.test/manifest.json", channel="partner-3dque")

    assert result.error_code == "channel_not_found"
    assert result.update_available is False
    assert result.download_url is None


def test_update_startup_policy_is_opt_out_and_no_hidden_polling():
    update_js = (REPO_ROOT / "core" / "ui" / "js" / "update-check.js").read_text(encoding="utf-8")

    assert "updates.enabled !== false && updates.check_on_startup !== false" in update_js
    assert "return apiGet('/app/update/check');" in update_js
    assert "apiPost('/app/update/stage', {})" in update_js
    assert "runSidebarManualUpdateStage" in update_js
    assert "runSidebarManualUpdateCheck();" in update_js
    assert "Staging verified update" in update_js
    assert "window.setInterval" not in update_js
    assert "AUTO_TIMER_MS" not in update_js
    assert "STALE_AFTER_MS" not in update_js
    assert "bus.updates.last_success_ms" not in update_js

    startup_section = update_js.split("export async function maybeRunStartupUpdateCheck()", 1)[1]
    assert "/app/update/stage" not in startup_section


def test_sidebar_uses_update_button_not_raw_download_link():
    shell_html = (REPO_ROOT / "core" / "ui" / "shell.html").read_text(encoding="utf-8")

    assert 'data-role="update-stage"' in shell_html
    assert 'data-role="update-download"' not in shell_html
    assert ">Update<" in shell_html


def test_settings_update_checkbox_defaults_to_enabled_unless_explicitly_disabled():
    settings_js = (REPO_ROOT / "core" / "ui" / "js" / "cards" / "settings.js").read_text(encoding="utf-8")

    assert "updates.enabled !== false" in settings_js
    assert "updates.check_on_startup !== false" in settings_js
    assert "check_on_startup: checkOnStartup" in settings_js
    assert "check_on_startup: autoUpdatesEnabled" not in settings_js
    assert "runSidebarManualUpdateCheck" not in settings_js
