# SPDX-License-Identifier: AGPL-3.0-or-later
"""Drift guard: one supported runtime authority map."""

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _read(rel_path: str) -> str:
    return (REPO_ROOT / rel_path).read_text(encoding="utf-8")


def test_legacy_runtime_surfaces_are_removed() -> None:
    for rel_path in ("app.py", "tgc/http.py", "core/main.py", "tgc_controller.spec"):
        assert not (REPO_ROOT / rel_path).exists(), (
            f"{rel_path} should not exist; legacy runtime surfaces must stay removed."
        )


def test_canonical_runtime_references_are_explicit() -> None:
    assert "python launcher.py" in _read("README.md")
    assert "Launch via `launcher.py`" in _read("SOT.md")
    assert "core.api.http:create_app" in _read("Dockerfile")
    assert "python launcher.py" in _read("Run Core.bat")


def test_removed_runtime_references_are_not_advertised() -> None:
    checked = "\n".join(
        _read(rel_path)
        for rel_path in (
            "README.md",
            "SOT.md",
            "docs/TRANSPARENCY.md",
            "docs/DATA_LIFECYCLE.md",
            "docs/windows-runbook.md",
            "license/README.md",
            "license/SOT.md",
            "launcher.py",
        )
    )
    assert "core.api.http:APP" not in checked
    assert "python app.py" not in checked


def test_scripts_launch_is_demoted_to_dev_helper() -> None:
    launch_script = _read("scripts/launch.ps1")
    assert "Dev/smoke helper" in launch_script
    assert "core.api.http:create_app" in launch_script
