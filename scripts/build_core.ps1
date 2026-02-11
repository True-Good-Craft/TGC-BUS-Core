param(
  [string]$Version = "0.10.6",
  [string]$Name    = "BUS-Core",
  [string]$Company = "True Good Craft",
  [string]$Product = "TGC BUS Core",
  [string]$Desc    = "Local-first Business Utility System Core (AGPL) by True Good Craft"
)

$ErrorActionPreference = "Stop"

# -----------------------------
# Repo root
# -----------------------------
$ROOT = Split-Path -Parent $PSScriptRoot
Set-Location $ROOT

$DIST = Join-Path $ROOT "dist"
$BUILD = Join-Path $ROOT "build"

Write-Host "[INFO] BUS Core build starting" -ForegroundColor Cyan
Write-Host "[INFO] Root: $ROOT" -ForegroundColor DarkGray

# -----------------------------
# Pre-flight
# -----------------------------
$spec = Join-Path $ROOT "$Name.spec"
if (!(Test-Path $spec)) {
  throw "Spec not found: $spec`nExpected '$Name.spec' at repo root."
}

# Ensure version is X.Y.Z
$verParts = $Version.Split(".")
if ($verParts.Count -ne 3) { throw "Version must be X.Y.Z (got '$Version')" }
$VMAJOR = [int]$verParts[0]
$VMINOR = [int]$verParts[1]
$VPATCH = [int]$verParts[2]

# -----------------------------
# Clean build outputs
# -----------------------------
Write-Host "[INFO] Cleaning previous builds" -ForegroundColor Cyan
Remove-Item -Recurse -Force $BUILD -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force $DIST  -ErrorAction SilentlyContinue

# -----------------------------
# Env (prod mode)
# -----------------------------
$env:BUS_DEV = "0"
$env:APP_VERSION = $Version

# -----------------------------
# Ensure PyInstaller is available
# -----------------------------
# Prefer existing venv if present; do not auto-nuke unless you want that policy.
$venvPy = Join-Path $ROOT ".venv\Scripts\python.exe"
if (!(Test-Path $venvPy)) {
  throw "Missing venv at .venv. Create it once, then reuse.`nExpected: $venvPy"
}

# Ensure pyinstaller exists in the venv
& $venvPy -m pip show pyinstaller *> $null
if ($LASTEXITCODE -ne 0) {
  Write-Host "[INFO] Installing PyInstaller into .venv" -ForegroundColor Cyan
  & $venvPy -m pip install --upgrade pyinstaller
}

# -----------------------------
# Write Windows version-info file (Explorer metadata)
# -----------------------------
$versionFile = Join-Path $ROOT "scripts\_win_version_info.txt"
$year = (Get-Date).Year

@"
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=($VMAJOR, $VMINOR, $VPATCH, 0),
    prodvers=($VMAJOR, $VMINOR, $VPATCH, 0),
    mask=0x3f,
    flags=0x0,
    OS=0x4,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        '040904B0',
        [
          StringStruct('CompanyName', '$Company'),
          StringStruct('FileDescription', '$Desc'),
          StringStruct('FileVersion', '$Version'),
          StringStruct('InternalName', '$Name'),
          StringStruct('LegalCopyright', 'Copyright (c) $year $Company'),
          StringStruct('OriginalFilename', '$Name.exe'),
          StringStruct('ProductName', '$Product'),
          StringStruct('ProductVersion', '$Version')
        ]
      )
    ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"@ | Set-Content -Encoding UTF8 $versionFile

Write-Host "[INFO] Version info written: $versionFile" -ForegroundColor DarkGray

# -----------------------------
# Build via SPEC (canonical)
# -----------------------------
Write-Host "[INFO] Running PyInstaller (SPEC, expected ONEFILE)" -ForegroundColor Cyan
& $venvPy -m PyInstaller `
  --noconfirm `
  --clean `
  $spec

# -----------------------------
# Post: Validate onefile output
# -----------------------------
$exeOut = Join-Path $DIST "$Name.exe"
if (!(Test-Path $exeOut)) {
  Write-Host "[INFO] Dist contents:" -ForegroundColor Yellow
  if (Test-Path $DIST) { Get-ChildItem $DIST | Format-Table Name, Mode, Length }
  throw "Build failed: expected onefile EXE not found at: $exeOut"
}

# Hard fail if onedir artifacts exist (this prevents the exact bug you hit)
$onedirPath = Join-Path $DIST $Name
$internalPath = Join-Path $onedirPath "_internal"
if (Test-Path $internalPath) {
  throw "Build produced ONEDIR artifacts ($internalPath). Expected ONEFILE only. Fix the .spec (remove COLLECT and exclude_binaries)."
}

# Optional: rename output to include version (keeps releases sane)
$finalExe = Join-Path $DIST "$Name-$Version.exe"
Copy-Item $exeOut $finalExe -Force

Write-Host "[PASS] Build complete (ONEFILE): $finalExe" -ForegroundColor Green
Write-Host ""
Write-Host "Next:" -ForegroundColor Cyan
Write-Host "  signtool sign /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 /a `"$finalExe`""
Write-Host "  signtool verify /pa /v `"$finalExe`""
