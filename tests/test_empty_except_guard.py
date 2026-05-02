# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import ast
import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "pytest-instance-lock",
    "pytest-instance-lock2",
    "venv",
}
APPROVED_COMMENT_TERMS = (
    "already",
    "best-effort",
    "cache",
    "cleanup",
    "compatibility fallback",
    "config cleanup",
    "expected fallback",
    "non-fatal",
    "optional",
)


def _iter_python_files() -> list[Path]:
    files: list[Path] = []
    for current_root, dirs, filenames in os.walk(REPO_ROOT):
        dirs[:] = [
            dirname
            for dirname in dirs
            if dirname not in SKIP_DIRS and not dirname.startswith(".tmp")
        ]
        for filename in filenames:
            if filename.endswith(".py"):
                files.append(Path(current_root) / filename)
    return sorted(files)


def _comment_text(lines: list[str], start_line: int, end_line: int) -> str:
    comments: list[str] = []
    for line in lines[start_line - 1 : end_line]:
        if "#" in line:
            comments.append(line.split("#", 1)[1].strip().lower())
    return " ".join(comments)


def test_empty_except_handlers_explain_intent() -> None:
    violations: list[str] = []
    for path in _iter_python_files():
        rel_path = path.relative_to(REPO_ROOT).as_posix()
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=rel_path)
        lines = source.splitlines()
        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            if len(node.body) != 1 or not isinstance(node.body[0], ast.Pass):
                continue
            comment = _comment_text(lines, node.lineno, node.body[0].lineno)
            if not any(term in comment for term in APPROVED_COMMENT_TERMS):
                violations.append(f"{rel_path}:{node.lineno} undocumented empty except")

    assert not violations, "Empty except handlers must explain non-fatal intent:\n" + "\n".join(violations)