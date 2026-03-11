[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$SmokeScript = Join-Path $PSScriptRoot 'smoke_isolated.ps1'
$BuildScript = Join-Path $PSScriptRoot 'build_core.ps1'
$VenvPython = Join-Path $Root '.venv\Scripts\python.exe'
$DistDir = Join-Path $Root 'dist'

if (!(Test-Path $SmokeScript)) {
  throw "Missing canonical smoke script: $SmokeScript"
}
if (!(Test-Path $BuildScript)) {
  throw "Missing canonical build script: $BuildScript"
}
if (!(Test-Path $VenvPython)) {
  throw "Missing build venv Python: $VenvPython"
}

try {
  $VersionOutput = & $VenvPython -c "from core.version import VERSION; print(VERSION)" 2>$null
}
catch {
  throw "Build venv Python is present but not runnable: $VenvPython"
}
if ($LASTEXITCODE -ne 0) {
  throw "Build venv Python is present but not runnable: $VenvPython"
}
$Version = ([string]$VersionOutput).Trim()
if ([string]::IsNullOrWhiteSpace($Version)) {
  throw 'Failed to read canonical VERSION from core/version.py.'
}

Write-Host 'BUS Core Release Check (smoke -> build -> artifact assertions)' -ForegroundColor Cyan
Write-Host "[INFO] Canonical VERSION: $Version" -ForegroundColor DarkGray

powershell -NoProfile -ExecutionPolicy Bypass -File $SmokeScript
if ($LASTEXITCODE -ne 0) {
  throw "Smoke script failed: $SmokeScript (exit code $LASTEXITCODE)"
}

powershell -NoProfile -ExecutionPolicy Bypass -File $BuildScript
if ($LASTEXITCODE -ne 0) {
  throw "Build script failed: $BuildScript (exit code $LASTEXITCODE)"
}

$PrimaryArtifact = Join-Path $DistDir 'BUS-Core.exe'
$VersionedArtifact = Join-Path $DistDir ("BUS-Core-{0}.exe" -f $Version)

if (!(Test-Path $PrimaryArtifact)) {
  throw "Missing primary build artifact: $PrimaryArtifact"
}
if (!(Test-Path $VersionedArtifact)) {
  throw "Missing versioned build artifact: $VersionedArtifact"
}

Write-Host '[PASS] Release check passed.' -ForegroundColor Green
Write-Host '[INFO] Verified artifacts:' -ForegroundColor DarkGray
Write-Host "  $PrimaryArtifact"
Write-Host "  $VersionedArtifact"
