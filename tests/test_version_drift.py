# SPDX-License-Identifier: AGPL-3.0-or-later
"""Drift guard: one canonical version source, no hardcoded semver in UI JS."""
import re
from pathlib import Path

import pytest

from core.version import VERSION

UI_JS_DIR = Path(__file__).parent.parent / "core" / "ui" / "js"
# Pattern for semver literals like 0.10.5 or 0.11.0 — 3-part dotted numbers
SEMVER_RE = re.compile(r"\b\d+\.\d+\.\d+\b")


def test_canonical_version_is_0_11_0():
    """core/version.py must declare the canonical version 0.11.0."""
    assert VERSION == "0.11.0", (
        f"core/version.py VERSION={VERSION!r}; expected '0.11.0'. "
        "Update core/version.py to bump the version."
    )


def test_no_hardcoded_semver_in_ui_js():
    """No semver literals in runtime UI JS (changelog/docs are not here)."""
    violations: list[str] = []
    for js_file in UI_JS_DIR.rglob("*.js"):
        text = js_file.read_text(encoding="utf-8", errors="replace")
        for lineno, line in enumerate(text.splitlines(), 1):
            # Skip lines that are clearly license/comment boilerplate
            stripped = line.strip()
            if stripped.startswith("//") or stripped.startswith("*"):
                continue
            for m in SEMVER_RE.finditer(line):
                violations.append(f"{js_file.relative_to(UI_JS_DIR)}:{lineno}: {m.group()!r}")
    assert not violations, (
        "Hardcoded semver literals found in core/ui/js/ — remove them:\n"
        + "\n".join(violations)
    )
