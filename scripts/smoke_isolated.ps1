# SPDX-License-Identifier: AGPL-3.0-or-later
#requires -Version 5.1
param(
  [string]$BindHost = "127.0.0.1",
  [int]$Port = 8765,
  [int]$HealthTimeoutSec = 30
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$scriptDir = Split-Path -Parent $PSCommandPath
$repoRoot = Resolve-Path (Join-Path $scriptDir "..")

$hadOriginalBusDb = $null -ne (Get-Item Env:BUS_DB -ErrorAction SilentlyContinue)
$originalBusDb = $env:BUS_DB

$guid = [guid]::NewGuid().ToString()
$tempRoot = [System.IO.Path]::GetTempPath()
$tempDir = Join-Path $tempRoot ("buscore-smoke-" + $guid)
$tempDbPath = Join-Path $tempDir "app.db"
New-Item -ItemType Directory -Path $tempDir -Force | Out-Null

$server = $null

try {
  $env:BUS_DB = $tempDbPath
  Write-Host ("[smoke] BUS_DB -> {0}" -f $tempDbPath)

  $launchScript = Join-Path $scriptDir "launch.ps1"
  $server = Start-Process -FilePath "powershell" -ArgumentList @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", $launchScript,
    "-BindHost", $BindHost,
    "-Port", $Port,
    "-Quiet"
  ) -WorkingDirectory $repoRoot -PassThru

  $healthUrl = "http://{0}:{1}/health" -f $BindHost, $Port
  $deadline = (Get-Date).AddSeconds($HealthTimeoutSec)
  $healthy = $false

  while ((Get-Date) -lt $deadline) {
    if ($server.HasExited) {
      throw "Server exited before becoming healthy (exit code $($server.ExitCode))."
    }

    try {
      $resp = Invoke-WebRequest -Uri $healthUrl -Method GET -UseBasicParsing -TimeoutSec 2
      if ($resp.StatusCode -eq 200) {
        $healthy = $true
        break
      }
    } catch {
      Start-Sleep -Milliseconds 500
    }
  }

  if (-not $healthy) {
    throw "Health check timed out after $HealthTimeoutSec seconds: $healthUrl"
  }

  $smokeScript = Join-Path $scriptDir "smoke.ps1"
  $baseUrl = "http://{0}:{1}" -f $BindHost, $Port
  powershell -NoProfile -ExecutionPolicy Bypass -File $smokeScript -BaseUrl $baseUrl
  if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
  }
}
finally {
  if ($server -and -not $server.HasExited) {
    try {
      Stop-Process -Id $server.Id -Force -ErrorAction Stop
    } catch {
      Write-Warning ("Failed to stop server process {0}: {1}" -f $server.Id, $_)
    }
  }

  if ($hadOriginalBusDb) {
    $env:BUS_DB = $originalBusDb
  } else {
    Remove-Item Env:BUS_DB -ErrorAction SilentlyContinue
  }

  try {
    if (Test-Path $tempDir) {
      Remove-Item -Path $tempDir -Recurse -Force -ErrorAction SilentlyContinue
    }
  } catch {
    Write-Verbose "Failed to clean temp smoke directory"
  }
}
