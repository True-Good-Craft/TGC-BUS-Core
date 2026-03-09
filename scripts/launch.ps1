# SPDX-License-Identifier: AGPL-3.0-or-later
# scripts/launch.ps1
# Dev/smoke helper for the canonical FastAPI factory.
# This is not the supported native app entry; use launcher.py / Run Core.bat.
param(
  [string]$BindHost = "127.0.0.1",
  [int]$Port = 8765,
  [string]$DbPath = $null,
  [switch]$Reload,
  [switch]$Quiet,
  [switch]$Smoke
)

# WinPS 5.1-safe color echo
function Say([string]$Text, [string]$Color = "White") {
  if (-not $Quiet) { Write-Host $Text -ForegroundColor $Color }
}

# Repo root (parent of /scripts)
$scriptDir = Split-Path -Parent $PSCommandPath
$repoRoot  = Resolve-Path (Join-Path $scriptDir "..")
Push-Location $repoRoot

# Default BUS_DEV to 0 unless explicitly set
if (-not $env:BUS_DEV) { $env:BUS_DEV = "0" }

try {
  # Ensure venv
  $venvPy = Join-Path ".\.venv\Scripts" "python.exe"
  if (-not (Test-Path $venvPy)) {
    Say "[launch] Creating venv..." "Cyan"
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw "venv creation failed." }
  }

  # Conditional pip install by hashing requirements
  $req = "requirements.txt"
  if (-not (Test-Path $req)) { throw "Missing requirements.txt at repo root." }

  $hashPath = ".\.venv\.req.hash"
  $reqHash  = (Get-FileHash -Algorithm SHA256 $req).Hash
  $oldHash  = ""
  if (Test-Path $hashPath) { $oldHash = (Get-Content $hashPath -ErrorAction SilentlyContinue) }

  if ($reqHash -ne $oldHash) {
    Say "[launch] Installing/updating dependencies..." "Cyan"
    & $venvPy -m pip install -U -r $req
    if ($LASTEXITCODE -ne 0) { throw "pip install failed." }
    $reqHash | Out-File -Encoding ascii $hashPath
  }

  # Resolve DB path for logging (default: repo data/app.db per SoT)
  $dbSource = "REPO"
  $appliedDb = $env:BUS_DB

  if ($appliedDb) {
    $dbSource = "ENV"
  } else {
    $appliedDb = Join-Path $repoRoot "data\app.db"
  }

  if ($PSBoundParameters.ContainsKey('DbPath') -and $DbPath) {
    $resolvedParam = $DbPath
    if (-not (Split-Path -IsAbsolute $resolvedParam)) {
      $resolvedParam = Join-Path $repoRoot $resolvedParam
    }
  }

  if (-not (Split-Path -IsAbsolute $appliedDb)) {
    $appliedDb = Join-Path $repoRoot $appliedDb
  }

  $dbDir = Split-Path -Parent $appliedDb
  if (-not (Test-Path $dbDir)) { New-Item -Type Directory -Path $dbDir | Out-Null }

  $env:PYTHONUTF8 = "1"

  # SPDX header warning (non-fatal)
  try {
    $missing = (git grep -L "SPDX-License-Identifier" -- "*.py" "*.ps1" "*.js" "*.ts" "*.css" "*.html" 2>$null | measure-object -line).Lines
    if ($missing -gt 0) {
      Write-Warning "[license] $missing files missing SPDX headers. Run: python scripts/tools/add_license_headers.py"
    }
  } catch {
    Write-Verbose "[license] git not available for SPDX check"
  }

  # Ensure repo root is on PYTHONPATH (so imports work even if caller runs elsewhere)
  $repoRoot = Resolve-Path (Join-Path $PSScriptRoot '..')
  $env:PYTHONPATH = "$repoRoot;$env:PYTHONPATH"

  # Canonical FastAPI entrypoint (factory) for scripted local checks.
  $appModule = 'core.api.http:create_app'
  $appArgs   = @('--factory','--host',$BindHost,'--port',$Port)

  if ($Reload) { $appArgs += "--reload" }

  # Optional safety: verify the file exists before launching
  if (-not (Test-Path (Join-Path $repoRoot 'core\api\http.py'))) {
    Write-Error "Cannot find core\api\http.py under $repoRoot. Aborting."
    exit 1
  }

  # Launch
  Say ("[launch] Starting BUS Core dev helper at http://{0}:{1}" -f $BindHost,$Port) "Green"
  & $venvPy -m uvicorn $appModule @appArgs

  if ($Smoke) {
    Start-Sleep -Seconds 2
    Say "[launch] Running smoke.ps1..." "Cyan"
    # Build URL safely with -f formatting to avoid $var: parsing errors
    $baseUrl = "http://{0}:{1}" -f $BindHost, $Port
    pwsh -NoProfile -File "$scriptDir\smoke.ps1" -BaseUrl $baseUrl
  }
  exit $LASTEXITCODE
}
finally {
  Pop-Location
}

