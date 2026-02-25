# SPDX-License-Identifier: AGPL-3.0-or-later
"""Drift guard: one canonical version source, no hardcoded semver in UI JS."""
import re
import tomllib
from pathlib import Path

from core.version import VERSION

REPO_ROOT = Path(__file__).parent.parent
UI_JS_DIR = REPO_ROOT / "core" / "ui" / "js"
# Pattern for semver literals like 0.10.5 or 0.11.0 — 3-part dotted numbers
SEMVER_RE = re.compile(r"\b\d+\.\d+\.\d+\b")


def test_version_file_matches_canonical():
    """Repo VERSION file must equal core.version.VERSION (the single source of truth)."""
    declared = (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()
    assert declared == VERSION, (
        f"VERSION file={declared!r} does not match core/version.py VERSION={VERSION!r}. "
        "Update the VERSION file to match core/version.py."
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
