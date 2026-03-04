# scripts/release-check.ps1
[CmdletBinding()]
param(
  [string]$Python = "python"
)

$ErrorActionPreference = 'Stop'

Write-Host "BUS Core Release Check (smoke → build)" -ForegroundColor Cyan

# Run smoke (must pass)
powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "smoke_isolated.ps1")

# Build Windows artifacts
powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "build-windows.ps1") -Python $Python

Write-Host "[DONE] Release check passed." -ForegroundColor Green
