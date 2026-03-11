# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from pathlib import Path


def test_smoke_isolation_wrapper_contract() -> None:
    path = Path("scripts/smoke_isolated.ps1")
    assert path.exists()

    text = path.read_text(encoding="utf-8")
    assert "BUS_DB" in text
    assert "LOCALAPPDATA" in text
    assert "ALLOW_WRITES" in text
    assert "READ_ONLY" in text
    assert "[smoke] BUS_DB ->" in text
    assert "Get-FreeTcpPort" in text
    assert "Test-TcpPortInUse" in text
    assert "Port {0} busy; using isolated port {1}" in text
    assert '"-File", (\'"{0}"\' -f $launchScript)' in text


def test_smoke_honors_localappdata_override() -> None:
    text = Path("scripts/smoke.ps1").read_text(encoding="utf-8")

    assert "function Get-LocalAppDataPath" in text
    assert "$env:LOCALAPPDATA" in text
    assert "$localAppData = Get-LocalAppDataPath" in text
    assert "$localAppData = [Environment]::GetFolderPath('LocalApplicationData')" not in text
    assert "$env:BUS_DB" in text
    assert "Split-Path -Parent $env:BUS_DB" in text
    assert "$journalDir = Get-JournalDir" in text

