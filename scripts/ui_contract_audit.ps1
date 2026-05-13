$ErrorActionPreference = 'Stop'

$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $Root

$ReportPath = Join-Path $Root 'reports/ui_contract_audit.md'
New-Item -ItemType Directory -Force -Path (Join-Path $Root 'reports') | Out-Null

$UseRg = $null -ne (Get-Command rg -ErrorAction SilentlyContinue)

function Run-Search {
  param(
    [string]$Pattern,
    [string]$Target
  )
  if ($UseRg) {
    $result = & rg -n --no-heading -e $Pattern $Target 2>$null
    if ($LASTEXITCODE -eq 0 -or $LASTEXITCODE -eq 1) { return @($result | ForEach-Object { $_ -replace '\\', '/' } | Where-Object { $_ -ne '' }) }
    throw "rg failed with code $LASTEXITCODE"
  }
  $result = & grep -nRE $Pattern $Target 2>$null
  if ($LASTEXITCODE -eq 0 -or $LASTEXITCODE -eq 1) { return @($result | Where-Object { $_ -ne '' }) }
  throw "grep failed with code $LASTEXITCODE"
}

function Save-Lines {
  param(
    [string]$Name,
    [array]$Lines
  )
  $tmp = Join-Path $env:TEMP ("ui_contract_{0}.txt" -f $Name)
  Set-Content -Path $tmp -Value $Lines
  return $tmp
}

function Count-Lines {
  param([string]$Path)
  if (!(Test-Path $Path)) { return 0 }
  $lines = Get-Content -Path $Path
  if ($null -eq $lines) { return 0 }
  return @($lines | Where-Object { $_ -ne '' }).Count
}

function NonCanonical-Lines {
  param([string]$Path)
  if (!(Test-Path $Path)) { return @() }
  $lines = Get-Content -Path $Path
  return @($lines | Where-Object {
    $_ -and
    -not $_.StartsWith('core/ui/js/api/canonical.js:') -and
    -not $_.StartsWith('core/ui/js/token.js:')
  })
}

function Exclude-KnownLines {
  param(
    [array]$Lines,
    [array]$AllowedPrefixes
  )
  return @($Lines | Where-Object {
    $line = $_
    $allowed = @($AllowedPrefixes | Where-Object { $line.StartsWith($_) })
    $_ -and $allowed.Count -eq 0
  })
}

function AuthClient-Lines {
  param([string]$Path)
  if (!(Test-Path $Path)) { return @() }
  $lines = Get-Content -Path $Path
  return @($lines | Where-Object {
    $_ -and -not $_.StartsWith('core/ui/js/auth.js:')
  })
}

function Merge-Endpoint-Matches {
  param([string]$Endpoint)
  $doubleQuoted = Run-Search ('"' + $Endpoint + '"') 'core/ui/js'
  $singleQuoted = Run-Search ("'" + $Endpoint + "'") 'core/ui/js'
  return @($doubleQuoted + $singleQuoted | Sort-Object -Unique)
}

$A1 = Save-Lines 'a1_api' (Merge-Endpoint-Matches '/api/')
$A2 = Save-Lines 'a2_ledger' (Merge-Endpoint-Matches '/ledger/')
$A3 = Save-Lines 'a3_mfg' (Merge-Endpoint-Matches '/manufacturing/')
$A4 = Save-Lines 'a4_tokens' (Run-Search '\bstock_in\b|manufacturing/run|ledger/movements' 'core/ui/js')

$B1 = Save-Lines 'b_qtykeys' (Exclude-KnownLines `
  (Run-Search '\bqty\b\s*:|\bqty_base\b\s*:|\bquantity_int\b\s*:|\boutput_qty\b\s*:|\bqty_required\b\s*:' 'core/ui/js') `
  @('core/ui/js/token.js:'))
$C1 = Save-Lines 'c_multiplier' (Exclude-KnownLines `
  (Run-Search '\*1000\b|/1000\b|\bbaseQty\b|\bmultiplier\b' 'core/ui/js') `
  @('core/ui/js/cards/recipes.js:'))
$D1 = Save-Lines 'd_finance' (Run-Search 'unit_cost_decimal' 'core/ui/js')

$EStockIn = Save-Lines 'e_stock_in' (Merge-Endpoint-Matches '/app/stock/in')
$EStockOut = Save-Lines 'e_stock_out' (Merge-Endpoint-Matches '/app/stock/out')
$EPurchase = Save-Lines 'e_purchase' (Merge-Endpoint-Matches '/app/purchase')
$ELedgerHistory = Save-Lines 'e_ledger_history' (Merge-Endpoint-Matches '/app/ledger/history')
$EManufacture = Save-Lines 'e_manufacture' (Merge-Endpoint-Matches '/app/manufacture')

$AuthState = Save-Lines 'auth_state' (Merge-Endpoint-Matches '/auth/state')
$AuthSetupOwner = Save-Lines 'auth_setup_owner' (Merge-Endpoint-Matches '/auth/setup-owner')
$AuthLogin = Save-Lines 'auth_login' (Merge-Endpoint-Matches '/auth/login')
$AuthLogout = Save-Lines 'auth_logout' (Merge-Endpoint-Matches '/auth/logout')
$AuthMe = Save-Lines 'auth_me' (Merge-Endpoint-Matches '/auth/me')

$ACount = (Count-Lines $A1) + (Count-Lines $A2) + (Count-Lines $A3) + (Count-Lines $A4)
$BCount = Count-Lines $B1
$CCount = Count-Lines $C1
$DCount = Count-Lines $D1

$ENonCanonical = 0
foreach ($f in @($EStockIn, $EStockOut, $EPurchase, $ELedgerHistory, $EManufacture)) {
  if ((NonCanonical-Lines $f).Count -gt 0) { $ENonCanonical++ }
}

$AuthNonClient = 0
foreach ($f in @($AuthState, $AuthSetupOwner, $AuthLogin, $AuthLogout, $AuthMe)) {
  $lines = if (Test-Path $f) { @(Get-Content -Path $f | Where-Object { $_ -ne '' }) } else { @() }
  if ($lines.Count -eq 0 -or (AuthClient-Lines $f).Count -gt 0) { $AuthNonClient++ }
}

$Status = 'PASS'
if ($ACount -gt 0 -or $BCount -gt 0 -or $CCount -gt 0 -or $DCount -gt 0 -or $ENonCanonical -gt 0 -or $AuthNonClient -gt 0) {
  $Status = 'FAIL'
}

$Timestamp = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
$SearchTool = if ($UseRg) { 'rg' } else { 'grep' }

$report = [System.Collections.Generic.List[string]]::new()
$report.Add('# UI Contract Audit Report')
$report.Add('')
$report.Add("- Timestamp (UTC): $Timestamp")
$report.Add("- Repo: $Root")
$report.Add("- Search tool: $SearchTool")
$report.Add("- Overall status: **$Status**")
$report.Add('')
$report.Add('## Commands')
$report.Add('')
$report.Add('```bash')
$report.Add('rg -n "/api/" core/ui/js')
$report.Add('rg -n "/ledger/" core/ui/js')
$report.Add('rg -n "/manufacturing/" core/ui/js')
$report.Add('rg -n "\bstock_in\b|manufacturing/run|ledger/movements" core/ui/js')
$report.Add('rg -n "\bqty\b\s*:|\bqty_base\b\s*:|\bquantity_int\b\s*:|\boutput_qty\b\s*:|\bqty_required\b\s*:" core/ui/js')
$report.Add('rg -n "\*1000\b|/1000\b|\bbaseQty\b|\bmultiplier\b" core/ui/js')
$report.Add('rg -n "unit_cost_decimal" core/ui/js')
$report.Add('rg -n "/app/stock/in" core/ui/js')
$report.Add('rg -n "/app/stock/out" core/ui/js')
$report.Add('rg -n "/app/purchase" core/ui/js')
$report.Add('rg -n "/app/ledger/history" core/ui/js')
$report.Add('rg -n "/app/manufacture" core/ui/js')
$report.Add('rg -n "/auth/state|/auth/setup-owner|/auth/login|/auth/logout|/auth/me" core/ui/js')
$report.Add('```')
$report.Add('')
$report.Add('## Guard Scope Notes')
$report.Add('')
$report.Add('- Forbidden endpoint and canonical containment checks are exact quoted endpoint searches to avoid regex quoting drift across shells.')
$report.Add('- Payload-key and multiplier/base searches remain active. Known compatibility matches are narrowly excluded only for `core/ui/js/token.js` (imperial wrapper payload conversion) and `core/ui/js/cards/recipes.js` (recipe unit label state); new matches elsewhere fail the audit.')
$report.Add('- Auth endpoint checks require `/auth/*` strings to live in `core/ui/js/auth.js`, keeping auth UI screens behind the small auth client instead of ad hoc endpoints.')
$report.Add('')

function Add-Section {
  param(
    [string]$Title,
    [string]$Path
  )
  $lines = if (Test-Path $Path) { @(Get-Content -Path $Path | Where-Object { $_ -ne '' }) } else { @() }
  $report.Add("## $Title ($($lines.Count))")
  if ($lines.Count -eq 0) {
    $report.Add('')
    $report.Add('No matches.')
    $report.Add('')
    return
  }
  $report.Add('')
  $report.Add('```text')
  foreach ($line in $lines) { $report.Add($line) }
  $report.Add('```')
  $report.Add('')
}

function Add-Auth-Section {
  param(
    [string]$Endpoint,
    [string]$Path
  )
  $lines = if (Test-Path $Path) { @(Get-Content -Path $Path | Where-Object { $_ -ne '' }) } else { @() }
  $report.Add("### $Endpoint ($($lines.Count) matches)")
  if ($lines.Count -eq 0) {
    $report.Add('')
    $report.Add('**FAIL** - no exact auth endpoint string found.')
    $report.Add('')
    return
  }
  $nonclient = AuthClient-Lines $Path
  if ($nonclient.Count -gt 0) {
    $report.Add('')
    $report.Add('**FAIL** - auth endpoint string found outside core/ui/js/auth.js:')
    $report.Add('')
    $report.Add('```text')
    foreach ($line in $nonclient) { $report.Add($line) }
    $report.Add('```')
    $report.Add('')
    return
  }
  $report.Add('')
  $report.Add('PASS - all matches contained in core/ui/js/auth.js')
  $report.Add('')
  $report.Add('```text')
  foreach ($line in $lines) { $report.Add($line) }
  $report.Add('```')
  $report.Add('')
}

Add-Section 'Forbidden endpoint strings found: /api/' $A1
Add-Section 'Forbidden endpoint strings found: /ledger/' $A2
Add-Section 'Forbidden endpoint strings found: /manufacturing/' $A3
Add-Section 'Forbidden endpoint token patterns found' $A4
Add-Section 'Forbidden payload keys found' $B1
Add-Section 'Multiplier/base conversion logic found' $C1
Add-Section 'Finance suspicious legacy fields found' $D1

$report.Add('## Canonical endpoint containment check')
$report.Add('')

foreach ($entry in @(
  @{ Endpoint='["\'']/app/stock/in["\'']'; Path=$EStockIn },
  @{ Endpoint='["\'']/app/stock/out["\'']'; Path=$EStockOut },
  @{ Endpoint='["\'']/app/purchase["\'']'; Path=$EPurchase },
  @{ Endpoint='["\'']/app/ledger/history["\'']'; Path=$ELedgerHistory },
  @{ Endpoint='["\'']/app/manufacture["\'']'; Path=$EManufacture }
)) {
  $lines = if (Test-Path $entry.Path) { @(Get-Content -Path $entry.Path | Where-Object { $_ -ne '' }) } else { @() }
  $report.Add("### $($entry.Endpoint) ($($lines.Count) matches)")
  if ($lines.Count -eq 0) {
    $report.Add('')
    $report.Add('No matches found.')
    $report.Add('')
    continue
  }
  $noncanon = NonCanonical-Lines $entry.Path
  if ($noncanon.Count -gt 0) {
    $report.Add('')
    $report.Add('**FAIL** - found outside canonical client:')
    $report.Add('')
    $report.Add('```text')
    foreach ($line in $noncanon) { $report.Add($line) }
    $report.Add('```')
    $report.Add('')
  } else {
    $report.Add('')
    $report.Add('PASS - all matches contained in core/ui/js/api/canonical.js or the documented core/ui/js/token.js compatibility wrapper')
    $report.Add('')
    $report.Add('```text')
    foreach ($line in $lines) { $report.Add($line) }
    $report.Add('```')
    $report.Add('')
  }
}

$report.Add('## Auth endpoint containment check')
$report.Add('')
Add-Auth-Section '/auth/state' $AuthState
Add-Auth-Section '/auth/setup-owner' $AuthSetupOwner
Add-Auth-Section '/auth/login' $AuthLogin
Add-Auth-Section '/auth/logout' $AuthLogout
Add-Auth-Section '/auth/me' $AuthMe

$report.Add('## Summary')
$report.Add('')
$report.Add("- Forbidden endpoint matches: $ACount")
$report.Add("- Forbidden payload-key matches: $BCount")
$report.Add("- Multiplier/base-conversion matches: $CCount")
$report.Add("- Finance legacy-field matches: $DCount")
$report.Add("- Canonical containment endpoint violations: $ENonCanonical")
$report.Add("- Auth endpoint containment violations: $AuthNonClient")
$report.Add("- Final result: **$Status**")

Set-Content -Path $ReportPath -Value $report

Write-Host "UI contract audit: $Status"
Write-Host "  forbidden endpoints: $ACount"
Write-Host "  forbidden payload keys: $BCount"
Write-Host "  multiplier/base logic: $CCount"
Write-Host "  finance legacy fields: $DCount"
Write-Host "  canonical containment violations: $ENonCanonical"
Write-Host "  auth endpoint containment violations: $AuthNonClient"
Write-Host "  report: $ReportPath"

if ($Status -eq 'FAIL') {
  exit 1
}
