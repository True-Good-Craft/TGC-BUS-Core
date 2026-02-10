# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from tests.conftest import reset_bus_modules

pytestmark = pytest.mark.unit


def _write_plugin(tmp_path: Path, package_name: str, plugin_source: str) -> None:
    plugin_dir = tmp_path / "plugins" / package_name
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / "__init__.py").write_text("", encoding="utf-8")
    (plugin_dir / "plugin.py").write_text(plugin_source, encoding="utf-8")


def test_discovery_rejects_internal_imports(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_plugin(
        tmp_path,
        "violator",
        "from core.contracts.plugin_v2 import PluginV2\n"
        "from core._internal import runtime  # forbidden\n"
        "class Plugin(PluginV2):\n"
        "    id='violator'; name='Violator'; version='0.0'; api_version='2'\n"
        "    def describe(self): return {'services':[], 'scopes':['read_base']}\n"
        "    def register_broker(self, b): pass\n",
    )
    monkeypatch.setenv("PLUGINS_DIRS", str(tmp_path / "plugins"))

    reset_bus_modules(["core.plugins_alpha"])
    mod = importlib.import_module("core.plugins_alpha")
    plugins = mod.discover_alpha_plugins()

    ids = [getattr(plugin, "id", "unknown") for plugin in plugins]
    assert "violator" not in ids


def test_discovery_ignores_non_plugin_interface(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_plugin(
        tmp_path,
        "not_a_plugin",
        "class Plugin:\n"
        "    id='not_a_plugin'\n",
    )
    monkeypatch.setenv("PLUGINS_DIRS", str(tmp_path / "plugins"))

    reset_bus_modules(["core.plugins_alpha"])
    mod = importlib.import_module("core.plugins_alpha")
    plugins = mod.discover_alpha_plugins()

    ids = {getattr(plugin, "id", "unknown") for plugin in plugins}
    assert "not_a_plugin" not in ids
