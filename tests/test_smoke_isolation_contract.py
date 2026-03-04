# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from pathlib import Path


def test_smoke_isolation_wrapper_contract() -> None:
    path = Path("scripts/smoke_isolated.ps1")
    assert path.exists()

    text = path.read_text(encoding="utf-8")
    assert "BUS_DB" in text
    assert "[smoke] BUS_DB ->" in text
