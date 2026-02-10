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

from __future__ import annotations

import builtins
import importlib
import importlib.util
import os
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, List, Set

from core.contracts.plugin_v2 import PluginV2
from core.public_api import PUBLIC_IMPORTS_ALLOWLIST
from core.plugins.loader import register as register_plugin_module


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_PLUGIN_DIRS = [
    ROOT_DIR / "plugins",
    ROOT_DIR / "plugins_user",
]


def _is_allowed_core_module(module_name: str) -> bool:
    if module_name == "core":
        return False
    for allowed in PUBLIC_IMPORTS_ALLOWLIST:
        if module_name == allowed or module_name.startswith(f"{allowed}."):
            return True
    return False


def _disallowed_new_core_imports(before: Set[str], after: Set[str]) -> Set[str]:
    newly = {name for name in after - before if name.startswith("core.")}
    return {name for name in newly if not _is_allowed_core_module(name)}


@contextmanager
def _capture_plugin_imports(prefix: str) -> Iterator[Set[str]]:
    captured: Set[str] = set()
    original_import = builtins.__import__

    def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):  # type: ignore[override]
        importer = None
        if isinstance(globals, dict):
            importer = globals.get("__name__")
        if importer and importer.startswith(prefix):
            resolved = name
            if level and isinstance(globals, dict):
                package = globals.get("__package__") or importer
                try:
                    resolved = importlib.util.resolve_name(name or "", package)
                except Exception:
                    resolved = name
            captured.add(resolved)
        return original_import(name, globals, locals, fromlist, level)

    builtins.__import__ = guarded_import
    try:
        yield captured
    finally:
        builtins.__import__ = original_import


def _disallowed_captured_imports(prefix: str, captured: Set[str]) -> Set[str]:
    violations: Set[str] = set()
    for name in captured:
        if not name:
            continue
        absolute = name if not name.startswith(".") else f"{prefix}{name}"
        if absolute == "core" or absolute.startswith("core."):
            if not _is_allowed_core_module(absolute):
                violations.add(absolute)
    return violations


def _resolve_plugin_dirs() -> List[Path]:
    paths: List[Path] = []
    seen: Set[Path] = set()
    for candidate in DEFAULT_PLUGIN_DIRS:
        resolved = candidate.resolve()
        if resolved.exists() and resolved not in seen:
            paths.append(resolved)
            seen.add(resolved)
    extra = os.environ.get("PLUGINS_DIRS", "")
    if extra:
        for item in extra.split(";"):
            raw = item.strip()
            if not raw:
                continue
            path = Path(raw).expanduser()
            try:
                resolved = path.resolve()
            except Exception:
                continue
            if resolved.exists() and resolved not in seen:
                paths.append(resolved)
                seen.add(resolved)
    return paths


def _iter_plugin_prefixes() -> Iterator[tuple[str, Path]]:
    if str(ROOT_DIR) not in sys.path:
        sys.path.append(str(ROOT_DIR))
    seen: Set[str] = set()
    for directory in _resolve_plugin_dirs():
        base_package = directory.name
        parent_path = str(directory.parent)
        if parent_path not in sys.path:
            sys.path.append(parent_path)
        for plugin_file in sorted(directory.rglob("plugin.py")):
            try:
                relative = plugin_file.relative_to(directory)
            except ValueError:
                continue
            if plugin_file.name != "plugin.py":
                continue
            parts = relative.parts[:-1]
            if not parts:
                continue
            if any(part.startswith("_") for part in parts):
                continue
            prefix = ".".join((base_package, *parts))
            if prefix in seen:
                continue
            seen.add(prefix)
            yield prefix, plugin_file


def _has_internal_imports(py_text: str) -> bool:
    for needle in ("import core", "from core", "import core.", "from core."):
        if needle in py_text:
            return True
    return False


def discover_alpha_plugins() -> List[PluginV2]:
    plugins: List[PluginV2] = []
    for prefix, plugin_file in _iter_plugin_prefixes():
        mod = None
        snap_before = set(sys.modules.keys())
        captured_names: Set[str] = set()
        try:
            try:
                source_text = plugin_file.read_text(encoding="utf-8")
            except Exception:
                continue
            if _has_internal_imports(source_text):
                print(f"[plugins] skipped {prefix}: internal import")
                continue
            for candidate in (f"{prefix}.plugin", prefix):
                with _capture_plugin_imports(prefix) as captured:
                    try:
                        mod = importlib.import_module(candidate)
                        captured_names = set(captured)
                        break
                    except Exception:
                        mod = None
                        captured_names = set()
                        continue
                # context manager ensures restore even on exception
            if mod is None:
                continue
            snap_after = set(sys.modules.keys())
            captured_violations = _disallowed_captured_imports(prefix, captured_names)
            module_violations = _disallowed_new_core_imports(snap_before, snap_after)
            violations = captured_violations | module_violations
            if violations:
                newly_loaded = snap_after - snap_before
                for module_name in newly_loaded:
                    if module_name.startswith(prefix):
                        sys.modules.pop(module_name, None)
                for module_name in newly_loaded:
                    if module_name.startswith("core."):
                        sys.modules.pop(module_name, None)
                continue
            register_plugin_module(mod)
            cls = getattr(mod, "Plugin", None)
            if cls and issubclass(cls, PluginV2):
                plugins.append(cls())
        except Exception:
            continue
    return plugins
