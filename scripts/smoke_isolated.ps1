# SPDX-License-Identifier: AGPL-3.0-or-later
#requires -Version 5.1
param(
  [string]$BindHost = "127.0.0.1",
  [int]$Port = 8765,
  [int]$HealthTimeoutSec = 30
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

function Get-FreeTcpPort {
  $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, 0)
  $listener.Start()
  try {
    return ([System.Net.IPEndPoint]$listener.LocalEndpoint).Port
  }
  finally {
    $listener.Stop()
  }
}

function Test-TcpPortInUse {
  param(
    [string]$TargetHost,
    [int]$Port
  )

  $client = New-Object System.Net.Sockets.TcpClient
  try {
    $async = $client.BeginConnect($TargetHost, $Port, $null, $null)
    if (-not $async.AsyncWaitHandle.WaitOne(250, $false)) {
      return $false
    }
    $client.EndConnect($async) | Out-Null
    return $true
  }
  catch {
    return $false
  }
  finally {
    $client.Close()
  }
}

$scriptDir = Split-Path -Parent $PSCommandPath
$repoRoot = Resolve-Path (Join-Path $scriptDir "..")

$hadOriginalBusDb = $null -ne (Get-Item Env:BUS_DB -ErrorAction SilentlyContinue)
$originalBusDb = $env:BUS_DB
$hadOriginalLocalAppData = $null -ne (Get-Item Env:LOCALAPPDATA -ErrorAction SilentlyContinue)
$originalLocalAppData = $env:LOCALAPPDATA
$hadOriginalAllowWrites = $null -ne (Get-Item Env:ALLOW_WRITES -ErrorAction SilentlyContinue)
$originalAllowWrites = $env:ALLOW_WRITES
$hadOriginalReadOnly = $null -ne (Get-Item Env:READ_ONLY -ErrorAction SilentlyContinue)
$originalReadOnly = $env:READ_ONLY

$guid = [guid]::NewGuid().ToString()
$tempRoot = [System.IO.Path]::GetTempPath()
$tempDir = Join-Path $tempRoot ("buscore-smoke-" + $guid)
$tempDbPath = Join-Path $tempDir "app.db"
New-Item -ItemType Directory -Path $tempDir -Force | Out-Null

$server = $null

try {
  $env:BUS_DB = $tempDbPath
  $env:LOCALAPPDATA = $tempDir
  $env:ALLOW_WRITES = "1"
  $env:READ_ONLY = "0"
  Write-Host ("[smoke] BUS_DB -> {0}" -f $tempDbPath)
  if (Test-TcpPortInUse -TargetHost $BindHost -Port $Port) {
    $requestedPort = $Port
    $Port = Get-FreeTcpPort
    Write-Host ("[smoke] Port {0} busy; using isolated port {1}" -f $requestedPort, $Port)
  }

  $launchScript = Join-Path $scriptDir "launch.ps1"
  $server = Start-Process -FilePath "powershell" -ArgumentList @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", ('"{0}"' -f $launchScript),
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

  if ($hadOriginalLocalAppData) {
    $env:LOCALAPPDATA = $originalLocalAppData
  } else {
    Remove-Item Env:LOCALAPPDATA -ErrorAction SilentlyContinue
  }

  if ($hadOriginalAllowWrites) {
    $env:ALLOW_WRITES = $originalAllowWrites
  } else {
    Remove-Item Env:ALLOW_WRITES -ErrorAction SilentlyContinue
  }

  if ($hadOriginalReadOnly) {
    $env:READ_ONLY = $originalReadOnly
  } else {
    Remove-Item Env:READ_ONLY -ErrorAction SilentlyContinue
  }

  try {
    if (Test-Path $tempDir) {
      Remove-Item -Path $tempDir -Recurse -Force -ErrorAction SilentlyContinue
    }
  } catch {
    Write-Verbose "Failed to clean temp smoke directory"
  }
}
