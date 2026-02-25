# Copyright (C) 2025 BUS Core Authors
# SPDX-License-Identifier: AGPL-3.0-or-later
<#!
Codex CI may not execute PowerShell. Use pytest smoke evidence + run this on Windows for full PS verification.
The grep patterns below intentionally detect PowerShell hashtable keys in both quoted and unquoted forms:
- legacy endpoints tokens: app stock_in, app ledger movements, app manufacturing run, app consume
- legacy qty keys: \b(qty|qty_base|quantity|quantity_int|output_qty)\b\s*=
!#>

param(
  [string]$Host = "127.0.0.1",
  [int]$Port = 8765
)

$ErrorActionPreference = "Stop"
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $repoRoot

function Get-Python {
  $candidates = @(
    (Join-Path $repoRoot ".venv/bin/python"),
    (Join-Path $repoRoot ".venv/Scripts/python.exe"),
    "python3",
    "python"
  )
  foreach ($p in $candidates) {
    if ($p -in @("python3", "python")) { return $p }
    if (Test-Path $p) { return $p }
  }
  return "python"
}

function Get-PowerShellCommand {
  if (Get-Command pwsh -ErrorAction SilentlyContinue) { return "pwsh" }
  if (Get-Command powershell -ErrorAction SilentlyContinue) { return "powershell" }
  throw "Neither 'pwsh' nor 'powershell' is available in PATH."
}

function Wait-ServerReady {
  param([string]$BaseUrl, [int]$TimeoutSec = 60)
  $deadline = (Get-Date).AddSeconds($TimeoutSec)
  while ((Get-Date) -lt $deadline) {
    try {
      $null = Invoke-RestMethod -Method Get -Uri "$BaseUrl/session/token" -TimeoutSec 3
      return $true
    } catch {
      Start-Sleep -Milliseconds 500
    }
  }
  return $false
}

$py = Get-Python
$psCmd = Get-PowerShellCommand
$baseUrl = "http://$Host`:$Port"
$tmpDir = Join-Path $repoRoot ".smoke_tmp"
New-Item -ItemType Directory -Force -Path $tmpDir | Out-Null

for ($i = 1; $i -le 2; $i++) {
  $dbPath = Join-Path $tmpDir ("smoke-run-{0}-{1}.db" -f $i, ([guid]::NewGuid().ToString("N")))
  if (Test-Path $dbPath) { Remove-Item -Force $dbPath }

  Write-Host "[smoke-runner] Run #$i using BUS_DB=$dbPath" -ForegroundColor Cyan
  $env:BUS_DB = $dbPath
  $env:PYTHONPATH = "$repoRoot"

  $server = Start-Process -FilePath $py -ArgumentList @("-m", "uvicorn", "core.api.http:create_app", "--factory", "--host", $Host, "--port", "$Port") -PassThru
  try {
    if (-not (Wait-ServerReady -BaseUrl $baseUrl -TimeoutSec 90)) {
      throw "Server did not become ready for run #$i"
    }

    & $psCmd -NoProfile -File (Join-Path $repoRoot "scripts/smoke.ps1") -BaseUrl $baseUrl
    if ($LASTEXITCODE -ne 0) {
      throw "smoke.ps1 failed on run #$i with exit code $LASTEXITCODE"
    }
    Write-Host "[smoke-runner] Run #$i PASS" -ForegroundColor Green
  }
  finally {
    if ($server -and -not $server.HasExited) {
      Stop-Process -Id $server.Id -Force
    }
    Start-Sleep -Seconds 1
  }
}

Write-Host "[smoke-runner] All smoke runs passed twice on fresh DBs." -ForegroundColor Green
