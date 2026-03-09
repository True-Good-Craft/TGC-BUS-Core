# SPDX-License-Identifier: AGPL-3.0-or-later
# TGC BUS Core (Business Utility System Core)
# Copyright (C) 2025 True Good Craft
#
# This file is part of TGC BUS Core.
#
# TGC BUS Core is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# TGC BUS Core is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with TGC BUS Core.  If not, see <https://www.gnu.org/licenses/>.

"""Renderer helpers for CLI menus."""

from __future__ import annotations

from typing import Any, Dict, Iterable

from core.brand import NAME, VENDOR
from core.services.capabilities import list_caps
from core.menu_spec import (
    CONTROLLER_CONFIG_MENU,
    MAIN_MENU,
    STATUS_PLUGINS_SECTIONS,
    SUBMENU_DATA_OPS,
)
from core.plugins_state import is_enabled as plugin_enabled
from core.unilog import write as unilog_write


def render_main_menu(quiet: bool = False) -> None:
    if not quiet:
        print(f"{NAME} — Controller Menu")
        print(f"made by: {VENDOR}")
        print()
    for key, label in MAIN_MENU:
        print(f" {key:>1}) {label}")
    print()
    print("Select an option (1–4, or q to quit): ", end="")


def render_data_ops_menu() -> None:
    print()
    print(MAIN_MENU[1][1])  # "Data Operations — …"
    for key, label in SUBMENU_DATA_OPS:
        print(f"  {key}) {label}")
    print()
    print("Select a workflow (12, 15, 2–6, or b to go back): ", end="")


def render_controller_tools_menu() -> None:
    print()
    print(MAIN_MENU[3][1])  # "Controller Config & Tools — …"
    for key, label in CONTROLLER_CONFIG_MENU:
        print(f"  {key}) {label}")
    print()
    print("Select a controller tool (1–6, or b to go back): ", end="")


def render_status_plugins_overview(payload: Dict[str, Any]) -> None:
    sections = STATUS_PLUGINS_SECTIONS
    core_label = sections[0]
    apis_label = sections[1]
    plugins_label = sections[2]
    caps_label = sections[3]

    core_block = payload.get("core", {}) or {}
    plugin_block = payload.get("plugins", {}) or {}
    items = plugin_block.get("items", []) or []
    summary = plugin_block.get("summary", {}) or {}

    flags = core_block.get("isolation", {}).get("flags", {}) or {}
    ready_flag = bool(core_block.get("ready"))
    safe_mode = "ON" if flags.get("OFFLINE_SAFE_MODE") else "OFF"
    subprocess = "ON" if flags.get("PLUGIN_SUBPROCESS") else "OFF"
    logging_info = core_block.get("logging", {}) or {}
    log_path = logging_info.get("path")

    print()
    print(MAIN_MENU[0][1])
    print("=" * len(MAIN_MENU[0][1]))
    print(f"{core_label}:")
    print(f"  Ready: {ready_flag}")
    print(f"  SafeMode: {safe_mode} • Subprocess: {subprocess}")
    if log_path:
        print(f"  Unified log path: {log_path}")
    print()

    def _api_status(plugin_name: str, required_keys: Iterable[str] | None = None) -> str:
        plugin_item = next((it for it in items if it.get("name") == plugin_name), None)
        if not plugin_item:
            return "MISSING"
        if not plugin_item.get("enabled") or not plugin_item.get("manifest_ok"):
            return "MISSING"
        missing_env = set(plugin_item.get("config", {}).get("missing_env") or [])
        if required_keys is None:
            return "READY" if not missing_env else "MISSING"
        return "READY" if not any(key in missing_env for key in required_keys) else "MISSING"

    notion_status = _api_status("notion-plugin")
    drive_status = _api_status(
        "google-plugin",
        ["GOOGLE_APPLICATION_CREDENTIALS", "DRIVE_ROOT_FOLDER_ID"],
    )
    sheets_status = _api_status(
        "google-plugin",
        ["GOOGLE_APPLICATION_CREDENTIALS", "SHEET_INVENTORY_ID"],
    )
    print(f"{apis_label}:")
    print(f"  Notion: {notion_status}")
    print(f"  Drive: {drive_status}")
    print(f"  Sheets: {sheets_status}")
    print()

    print(f"{plugins_label}:")
    if not items:
        print("  (no plugins discovered)")
    else:
        for item in sorted(items, key=lambda it: str(it.get("name"))):
            name = item.get("name") or "(unknown)"
            version = item.get("version") or "?"
            enabled = "enabled" if item.get("enabled") else "disabled"
            manifest_state = "ok" if item.get("manifest_ok") else "error"
            config_info = item.get("config", {}) or {}
            missing_env = [str(v) for v in (config_info.get("missing_env") or [])]
            config_state = "ok" if not missing_env else f"missing: {', '.join(missing_env)}"
            health_info = item.get("health", {}) or {}
            health_status = health_info.get("status") or "unknown"
            print(
                f"  - {name}@{version} [{enabled}; manifest={manifest_state}; "
                f"config={config_state}; health={health_status}]"
            )
            notes = health_info.get("notes")
            if isinstance(notes, list) and notes:
                preview = "; ".join(str(n) for n in notes)
                print(f"      notes: {preview}")
    print()

    index_caps = []
    print(f"{caps_label}:")
    for capability, meta in sorted(list_caps().items()):
        if ".index" not in capability:
            continue
        index_caps.append(capability)
        plugin_name = meta.get("plugin") or "?"
        scopes = meta.get("scopes") or []
        scope_text = ", ".join(scopes) if scopes else "(none)"
        network_flag = "true" if meta.get("network") else "false"
        plugin_state = "enabled" if plugin_enabled(plugin_name) else "disabled"
        version = meta.get("version") or "?"
        print(
            "  - {cap} (plugin: {plugin}@{version}, scopes: {scopes}, "
            "network={network}, plugin_state={state})".format(
                cap=capability,
                plugin=plugin_name,
                version=version,
                scopes=scope_text,
                network=network_flag,
                state=plugin_state,
            )
        )
    if not index_caps:
        print("  (no indexing capabilities registered)")

    api_ready_count = sum(
        1 for status in (notion_status, drive_status, sheets_status) if status == "READY"
    )
    enabled_count = sum(1 for item in items if item.get("enabled"))
    counts = {
        "core_ready": ready_flag,
        "plugins_total": len(items),
        "plugins_enabled": enabled_count,
        "plugins_ok": summary.get("ok", 0),
        "indexing_caps": len(index_caps),
        "apis_ready": api_ready_count,
    }
    unilog_write("menu.view.status_plugins", None, counts=counts)


# --- Backward compatibility alias for older menu callers ---
def render_root(quiet: bool = False) -> None:
    """Legacy entrypoint. Calls render_main_menu()."""
    return render_main_menu(quiet=quiet)

