# SPDX-License-Identifier: AGPL-3.0-or-later
"""Drift guard: one canonical version source, no hardcoded semver in UI JS."""
import re
import tomllib
from pathlib import Path

from core.version import INTERNAL_VERSION, VERSION

REPO_ROOT = Path(__file__).parent.parent
UI_JS_DIR = REPO_ROOT / "core" / "ui" / "js"
SEMVER_RE = re.compile(r"\b\d+\.\d+\.\d+\b")
STRICT_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")
INTERNAL_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+\.\d+$")


def test_version_has_strict_semver_format():
    """Public VERSION must remain strict X.Y.Z."""
    assert STRICT_VERSION_RE.match(VERSION), (
        f"core/version.py VERSION={VERSION!r} must be strict X.Y.Z."
    )


def test_internal_version_has_expected_four_part_format():
    """Internal working version must remain X.Y.Z.R."""
    assert INTERNAL_VERSION_RE.match(INTERNAL_VERSION), (
        f"core/version.py INTERNAL_VERSION={INTERNAL_VERSION!r} must be X.Y.Z.R."
    )
    assert INTERNAL_VERSION.startswith(f"{VERSION}."), (
        f"INTERNAL_VERSION={INTERNAL_VERSION!r} must extend VERSION={VERSION!r}."
    )


def test_pyproject_version_matches_canonical():
    """pyproject.toml [project] version must equal core.version.VERSION."""
    data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    declared = data["project"]["version"]
    assert declared == VERSION, (
        f"pyproject.toml version={declared!r} does not match core/version.py VERSION={VERSION!r}. "
        "Update pyproject.toml to match core/version.py."
    )


def test_no_hardcoded_semver_in_ui_js():
    """No semver literals in runtime UI JS (changelog/docs are not here)."""
    violations: list[str] = []
    for js_file in UI_JS_DIR.rglob("*.js"):
        text = js_file.read_text(encoding="utf-8", errors="replace")
        for lineno, line in enumerate(text.splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("//") or stripped.startswith("*"):
                continue
            for m in SEMVER_RE.finditer(line):
                violations.append(f"{js_file.relative_to(UI_JS_DIR)}:{lineno}: {m.group()!r}")
    assert not violations, (
        "Hardcoded semver literals found in core/ui/js/ — remove them:\n"
        + "\n".join(violations)
    )
