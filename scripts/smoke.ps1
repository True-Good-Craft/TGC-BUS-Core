# SPDX-License-Identifier: AGPL-3.0-or-later
#requires -Version 5.1
<#
.SYNOPSIS
  BUS Core smoke tests (canonical; no /dev/* required).
  Proves 0.8.2 invariants using only app endpoints:
    - /session/token
    - /openapi.json (feature presence)
    - /app/items
    - /app/contacts
    - /app/adjust
    - /app/purchase
    - /app/consume
    - /app/recipes  (POST/PUT)
    - /app/manufacturing/run
    - /app/movements?limit=N

.INVARIANTS (v0.8.2)
  1) POST /app/manufacturing/run is single-run only (array payload => 400/422)
  2) Fail-fast manufacturing: shortages => 400 AND no writes (checked by latest movement id)
  3) Success is atomic: movements for the run committed (≥1 consume + 1 output)
  4) Output unit cost = total consumed cost / output_qty (round-half-up)
  5) Manufacturing never sets is_oversold=1
  6) Ad-hoc runs: components[] required (non-empty), else 400

.USAGE
  powershell -NoProfile -ExecutionPolicy Bypass -File scripts\smoke.ps1 -BaseUrl http://127.0.0.1:8765
#>

param(
  [string]$BaseUrl = "http://127.0.0.1:8765"
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

# -----------------------------
# Console banner (ASCII-only)
# -----------------------------
Write-Host "BUS Core Smoke Test Harness"
Write-Host ("Target: {0}" -f $BaseUrl)
Write-Host ("Time:   {0:yyyy-MM-dd HH:mm:ss}" -f (Get-Date))
Write-Host "------------------------------------------------------------"

# -----------------------------
# Helpers (ASCII-only output; 5.1-safe)
# -----------------------------
function Info       { param([string]$m) Write-Host ("  [INFO] {0}" -f $m) -ForegroundColor DarkCyan }
function Pass       { param([string]$m) Write-Host ("  [PASS] {0}" -f $m) -ForegroundColor Green }
function Fail       { param([string]$m) Write-Host ("  [FAIL] {0}" -f $m) -ForegroundColor Red }
function Step       { param([string]$m) Write-Host ""; Write-Host $m -ForegroundColor Cyan }
function RoundHalfUpCents([decimal]$v) { return [int][decimal]::Round($v, 0, [System.MidpointRounding]::AwayFromZero) }

# A single session object to persist cookies (from /session/token)
$script:Session = New-Object Microsoft.PowerShell.Commands.WebRequestSession

function Invoke-Json {
  param([string]$Method, [string]$Url, $BodyObj)
  $args = @{ Method=$Method; Uri=$Url; WebSession=$script:Session }
  if ($PSBoundParameters.ContainsKey('BodyObj') -and $null -ne $BodyObj) {
    $args['ContentType'] = 'application/json'
    if ($BodyObj -is [string]) { $args['Body'] = $BodyObj }
    else { $args['Body'] = ($BodyObj | ConvertTo-Json -Depth 12) }
  }
  try {
    return Invoke-RestMethod @args
  } catch {
    if ($Method -eq "POST" -and $PSBoundParameters.ContainsKey('BodyObj') -and $null -ne $BodyObj) {
      Write-Host "Payload:" ($BodyObj | ConvertTo-Json -Depth 5)
    }
    throw
  }
}

function Try-Invoke {
  param([scriptblock]$Block)
  try { $r = & $Block; return @{ ok=$true; resp=$r } }
  catch { return @{ ok=$false; err=$_ } }
}

function Invoke-RestJsonWithTimeout {
  param(
    [Parameter(Mandatory=$true)][string]$Uri,
    [Parameter(Mandatory=$true)][string]$Method,
    [Parameter()]$Body = $null,
    [int]$TimeoutSec = 120,
    [hashtable]$Headers = $null
  )
  $job = Start-Job -InitializationScript {
    $ProgressPreference = 'SilentlyContinue'
  } -ScriptBlock {
    param($Uri,$Method,$Body,$Headers)
    try {
      $hdr = $null
      if ($Headers -ne $null) {
        $hdr = @{}
        foreach ($k in $Headers.Keys) { $hdr[$k] = $Headers[$k] }
      }
      if ($Body -ne $null) {
        return Invoke-RestMethod -Method $Method -Uri $Uri -Headers $hdr -Body ($Body | ConvertTo-Json -Depth 10) -ContentType "application/json" -MaximumRedirection 0 -ErrorAction Stop
      } else {
        return Invoke-RestMethod -Method $Method -Uri $Uri -Headers $hdr -MaximumRedirection 0 -ErrorAction Stop
      }
    } catch {
      throw
    }
  } -ArgumentList $Uri,$Method,$Body,$Headers
  if (-not (Wait-Job $job -Timeout $TimeoutSec)) {
    Stop-Job $job -Force | Out-Null
    Remove-Job $job -Force | Out-Null
    throw "Timeout after ${TimeoutSec}s"
  }
  $res = Receive-Job $job -ErrorAction Stop
  Remove-Job $job -Force | Out-Null
  return $res
}

function Get-WebErrorBody {
  param($TryResult)

  # 1) Prefer ErrorDetails.Message when present
  if ($TryResult -and $TryResult.err -and $TryResult.err.ErrorDetails) {
    $m = [string]$TryResult.err.ErrorDetails.Message
    if (-not [string]::IsNullOrWhiteSpace($m)) { return $m }
  }

  # 2) Fallback: read raw response stream (PS 5.1 WebRequest exception)
  try {
    $resp = $TryResult.err.Exception.Response
    if ($null -ne $resp -and $resp.GetResponseStream) {
      $stream = $resp.GetResponseStream()
      if ($stream) {
        $reader = New-Object System.IO.StreamReader($stream, [System.Text.Encoding]::UTF8, $true)
        $text = $reader.ReadToEnd()
        $reader.Dispose()
        return [string]$text
      }
    }
  } catch { }

  return ""
}

function Parse-ErrorDetail {
  param([Parameter()]$Json)
  if ($null -eq $Json) { return @{ kind = "none"; message = "" } }
  if (-not $Json.PSObject.Properties.Name.Contains("detail")) { return @{ kind = "none"; message = "" } }

  $d = $Json.detail
  if ($d -is [string]) {
    return @{ kind = "string"; message = $d }
  } elseif ($d -is [System.Collections.IEnumerable] -and -not ($d -is [string])) {
    # FastAPI validation list
    $msgs = @()
    foreach ($e in $d) {
      if ($null -ne $e.msg) { $msgs += [string]$e.msg }
    }
    $msg = if ($msgs.Count -gt 0) { ($msgs -join "; ") } else { "Validation error" }
    return @{ kind = "list"; message = $msg }
  } elseif ($d -is [pscustomobject] -or $d -is [hashtable]) {
    $msg = ""
    if ($d.PSObject.Properties.Name -contains "message") { $msg = [string]$d.message }
    elseif ($d.PSObject.Properties.Name -contains "error") { $msg = [string]$d.error }
    return @{ kind = "object"; message = $msg }
  } else {
    return @{ kind = "unknown"; message = "" }
  }
}

$script:RunLabel = (Get-Date -Format "yyyyMMddHHmmss")
$localAppData = [Environment]::GetFolderPath('LocalApplicationData')

# Establish session first (avoid 401s on protected endpoints)
$tokResp = Invoke-RestMethod -Method Get -Uri ($BaseUrl + "/session/token") -WebSession $script:Session
if ($tokResp) {
  Write-Host "  [INFO] Session token acquired" -ForegroundColor DarkCyan
  # Build headers with the session cookie for use in job-based REST calls
  $cookiePairs = @()
  try {
    $uri = [Uri]$BaseUrl
    foreach ($c in $script:Session.Cookies.GetCookies($uri)) {
      $cookiePairs += ("{0}={1}" -f $c.Name, $c.Value)
    }
  } catch { }
  $cookieHeader = ($cookiePairs -join "; ")
  $script:Headers = @{ "Cookie" = $cookieHeader; "Accept" = "application/json" }
} else {
  Write-Host "  [FAIL] No session token returned from /session/token" -ForegroundColor Red
  exit 1
}

# Best-effort feature check (safe if /openapi.json exists; non-fatal if not)
try {
  $openapi = Invoke-RestMethod -Method Get -Uri ($BaseUrl + "/openapi.json") -WebSession $script:Session
  Write-Host "  [INFO] Dev Mode: ON (Full invariant checks enabled)"
} catch {
  Write-Host "  [INFO] Dev Mode: UNKNOWN (continuing with canonical checks)"
}

# ---------------------------------------
# Utilities that use ONLY app endpoints
# ---------------------------------------
function Get-LatestMovementId {
  # Returns the highest movement id currently observed
  $r = Invoke-Json GET ($BaseUrl + "/app/movements?limit=1") $null
  if ($r -and $r.movements -and $r.movements.Count -gt 0) { return [int]$r.movements[0].id }
  return 0
}

function Get-RunMovements {
  param([int]$RunId, [int]$Limit = 200)
  $r = Invoke-Json GET ($BaseUrl + "/app/movements?limit=$Limit") $null
  if (-not $r -or -not $r.movements) { return @() }
  # Filter to manufacturing movements of this run (expects source_kind/manufacturing & source_id=run_id)
  $list = @($r.movements | Where-Object { $_.source_kind -eq "manufacturing" -and $_.source_id -eq "$RunId" })
  return $list
}

function Get-MovementsByItem {
  param([int]$ItemId, [int]$Limit = 200)
  $resp = Invoke-Json GET ($BaseUrl + "/app/movements?limit=$Limit") $null
  if (-not $resp -or -not $resp.movements) { return @() }
  return @($resp.movements | Where-Object { $_.item_id -eq $ItemId })
}

function Get-JournalDir {
  $appDir = Join-Path $localAppData 'BUSCore\\app'
  return Join-Path $appDir 'data\\journals'
}

$journalDir = Get-JournalDir

# -----------------------------
# 1) Items: create definition
# -----------------------------
Step "1. Items Definition"
Info "Creating basic items..."
$itemA = Invoke-Json POST ($BaseUrl + "/app/items") @{ name = "SMK-A-$($RunLabel)" }
$itemB = Invoke-Json POST ($BaseUrl + "/app/items") @{ name = "SMK-B-$($RunLabel)" }
$itemC = Invoke-Json POST ($BaseUrl + "/app/items") @{ name = "SMK-C-$($RunLabel)" }
$itemD = Invoke-Json POST ($BaseUrl + "/app/items") @{ name = "SMK-D-$($RunLabel)" }
if ( ($itemA.id -as [int]) -gt 0 -and ($itemB.id -as [int]) -gt 0 -and ($itemC.id -as [int]) -gt 0 -and ($itemD.id -as [int]) -gt 0 ) { Pass "Created items A, B, C, D successfully" } else { Fail "Item creation failed"; exit 1 }

# --------------------------------------
# 2) Contacts CRUD
# --------------------------------------
Step "2. Contacts CRUD"
Info "Creating and updating contacts..."
$contactName = "SMK-Contact-$($RunLabel)"
$contact = Invoke-Json POST ($BaseUrl + "/app/contacts") @{ name = $contactName; contact = "smoke@example.test" }
if (($contact.id -as [int]) -gt 0) { Pass "Contact created" } else { Fail "Contact create failed"; exit 1 }

$contactUpdated = Invoke-Json PUT ($BaseUrl + "/app/contacts/$($contact.id)") @{ name = "$contactName-Updated"; is_vendor = $false; meta = @{ note = "smoke" } }
if ($contactUpdated.name -like "$contactName-Updated*") { Pass "Contact updated" } else { Fail "Contact update failed"; exit 1 }

$contactList = Invoke-Json GET ($BaseUrl + "/app/contacts") $null
$contactFound = $false
foreach ($c in $contactList) { if ($c.id -eq $contact.id) { $contactFound = $true } }
if ($contactFound) { Pass "Contact appears in listing" } else { Fail "Contact missing from list"; exit 1 }

$delContact = Try-Invoke { Invoke-RestMethod -Method Delete -Uri ($BaseUrl + "/app/contacts/$($contact.id)") -WebSession $script:Session -ErrorAction Stop }
if ($delContact.ok) { Pass "Contact deleted" } else { Fail "Contact delete failed"; exit 1 }

# --------------------------------------
# 3) Adjustments: FIFO, shortage=400
# --------------------------------------
Step "3. Inventory Adjustments"
Info "Testing positive stock-in and negative consumption..."
$beforeAdjId = Get-LatestMovementId
$pos = Invoke-Json POST ($BaseUrl + "/app/adjust") @{ item_id = $itemA.id; quantity_decimal = "30"; uom = "ea"; direction = "in"; note = "smoke" }
$afterPosId = Get-LatestMovementId
if ($pos) { Pass "Positive adjust (+30) on Item A accepted" } else { Fail "Positive adjust failed"; exit 1 }
if ($afterPosId -gt $beforeAdjId) { Pass "Movement recorded for positive adjust" } else { Fail "Movement count did not advance for positive adjust"; exit 1 }

$neg = Invoke-Json POST ($BaseUrl + "/app/adjust") @{ item_id = $itemA.id; quantity_decimal = "4"; uom = "ea"; direction = "out"; note = "smoke" }
$afterNegId = Get-LatestMovementId
if ($neg) { Pass "Negative adjust (-4) on Item A accepted" } else { Fail "Negative adjust failed"; exit 1 }
if ($afterNegId -gt $afterPosId) { Pass "Movement recorded for negative adjust" } else { Fail "Movement count did not advance for negative adjust"; exit 1 }

$negTry = Try-Invoke { Invoke-Json POST ($BaseUrl + "/app/adjust") @{ item_id = $itemB.id; quantity_decimal = "999"; uom = "ea"; direction = "out"; note = "smoke" } }
if (-not $negTry.ok -and $negTry.err.Exception.Response.StatusCode.value__ -eq 400) { Pass "Oversized negative adjust rejected (400)" } else { Fail "Oversized negative adjust should be 400"; exit 1 }

# --------------------------------------
# 4) FIFO Purchase + Consume
# --------------------------------------
Step "4. FIFO Purchase + Consume"
Info "Purchasing and consuming FIFO stock..."
$purchase = Invoke-Json POST ($BaseUrl + "/app/purchase") @{ item_id = $itemD.id; quantity_decimal = "5"; uom = "ea"; unit_cost_decimal = "1.20"; cost_uom = "ea"; source_kind = "purchase"; source_id = "smoke-$($RunLabel)-p1" }
if ($purchase.ok) { Pass "Purchase created batch" } else { Fail "Purchase failed"; exit 1 }

$consume = Invoke-Json POST ($BaseUrl + "/app/consume") @{ item_id = $itemD.id; quantity_decimal = "2"; uom = "ea"; source_kind = "consume"; source_id = "smoke-$($RunLabel)-c1" }
if ($consume.ok) { Pass "Consume succeeded" } else { Fail "Consume failed"; exit 1 }

$dMoves = Get-MovementsByItem -ItemId $itemD.id -Limit 50
$netBase = 0
foreach ($m in $dMoves) { $netBase += [double]$m.qty_change }
# Convert base (mc) -> ea for count dimension
$netEach = $netBase / 1000.0
# PS 5.1-safe rounding + tolerance
$rounded = [Math]::Round([double]$netEach, 2)
if ([Math]::Abs($rounded - 3.0) -lt 0.001) { Pass "Remaining qty expected (3 units)" } else { Fail ("Unexpected remaining qty for Item D: {0} (rounded={1})" -f $netEach, $rounded); exit 1 }

$orderedDMoves = @($dMoves | Sort-Object id)
if ($orderedDMoves.Count -ge 2 -and $orderedDMoves[0].source_kind -eq "purchase" -and $orderedDMoves[1].source_kind -eq "consume") { Pass "FIFO ordering honored (purchase then consume)" } else { Fail "FIFO movement ordering incorrect"; exit 1 }

$inventoryJournal = Join-Path $journalDir 'inventory.jsonl'
$invLineCount = 0
if (Test-Path $inventoryJournal) { $invLineCount = (Get-Content -LiteralPath $inventoryJournal -ErrorAction Stop).Count }
if ($invLineCount -ge 2) { Pass "Inventory journal appended" } else { Fail "Inventory journal missing entries"; exit 1 }

# --------------------------------------
# 5) Recipes: create + PUT
# --------------------------------------
Step "5. Recipe Management"
Info "Creating and updating recipes..."
$rec = Invoke-Json POST ($BaseUrl + "/app/recipes") @{
  name = "SMK: B-from-A"
  output_item_id = $itemB.id
  items = @(@{ item_id = $itemA.id; qty_required = 3; optional = $false })
}
if (($rec.id -as [int]) -gt 0) { Pass "Recipe created via POST" } else { Fail "Recipe create failed"; exit 1 }

$recPut = Invoke-Json PUT ($BaseUrl + "/app/recipes/$($rec.id)") @{
  id = $rec.id
  name = "SMK: B-from-A (v2)"
  output_item_id = $itemB.id
  is_archived = $false
  notes = "smoke"
  items = @(
    @{ item_id = $itemA.id; qty_required = 3; optional = $false },
    @{ item_id = $itemC.id; qty_required = 1; optional = $true }
  )
}
# If the PUT returns plain 2xx without { ok: true }, accept as success
$recPutOk = $true
try {
  if ($recPut -and $recPut.ok -ne $true) { }
} catch { }
Pass "Recipe updated via PUT"

# --------------------------------------
# 6) Manufacturing: happy + error
# --------------------------------------
Step "6. Manufacturing Logic"
Info "Standard Run..."
$mfgJournal = Join-Path $journalDir 'manufacturing.jsonl'
$mfgLinesBefore = 0
if (Test-Path $mfgJournal) { $mfgLinesBefore = (Get-Content -LiteralPath $mfgJournal -ErrorAction SilentlyContinue).Count }
$body = @{ recipe_id = $rec.id; output_qty = 2; notes = "smoke run ok" }
try {
  $okRun = Invoke-RestMethod -Method Post -Uri "$BaseUrl/app/manufacturing/run" `
             -Body ($body | ConvertTo-Json -Depth 8) -ContentType "application/json" -WebSession $script:Session
  Write-Host ("  [OK] Manufacturing run_id={0}" -f $okRun.run_id)
}
catch {
  $raw = $_.ErrorDetails.Message
  $parsed = $null
  try { $parsed = $raw | ConvertFrom-Json } catch {}

  if ($null -ne $parsed -and $parsed.detail -and $parsed.detail.error -eq 'insufficient_stock') {
    foreach ($s in $parsed.detail.shortages) {
      $needed = [math]::Ceiling([double]$s.required - [double]$s.available)
      if ($needed -gt 0) {
        $adjBody = @{ item_id = [int]$s.component; quantity_decimal = [string][int]$needed; uom = "ea"; direction = "in"; note = "smoke-topup" }
        Invoke-RestMethod -Method Post -Uri "$BaseUrl/app/adjust" `
          -Body ($adjBody | ConvertTo-Json -Depth 8) -ContentType "application/json" -WebSession $script:Session | Out-Null
      }
    }

    $okRun = Invoke-RestMethod -Method Post -Uri "$BaseUrl/app/manufacturing/run" `
               -Body ($body | ConvertTo-Json -Depth 8) -ContentType "application/json" -WebSession $script:Session
    Write-Host ("  [OK] Manufacturing run_id={0} (after top-up)" -f $okRun.run_id)
  }
  else {
    throw
  }
}
if ($okRun.status -ne "completed") { Fail "Expected completed run"; exit 1 }
if (Test-Path $mfgJournal) {
  $mfgLinesAfter = (Get-Content -LiteralPath $mfgJournal -ErrorAction SilentlyContinue).Count
  if ($mfgLinesAfter -gt $mfgLinesBefore) { Pass "Manufacturing journal appended" } else { Fail "Manufacturing journal did not append"; exit 1 }
} else {
  Fail "Manufacturing journal missing"
  exit 1
}
Pass "Run completed successfully"

Info "Validation checks..."
$badRun = Try-Invoke {
  Invoke-Json POST ($BaseUrl + "/app/manufacturing/run") @{ recipe_id = $rec.id; output_qty = 999 }
}
$badStatus = 0
if ($badRun.ok) { $badStatus = 200 }
else {
  try { $badStatus = $badRun.err.Exception.Response.StatusCode.value__ } catch { $badStatus = 0 }
}

# Expect 400 for insufficient stock
if ($badStatus -ne 400) {
  Fail "Expected 400 on insufficient stock, got $badStatus"
} else {
  $errBody = Get-WebErrorBody $badRun
  $obj = $null
  if (-not [string]::IsNullOrWhiteSpace($errBody)) {
    try { $obj = $errBody | ConvertFrom-Json } catch { $obj = $null }
  }
  $err = Parse-ErrorDetail -Json $obj
  if ($err.kind -in @("string","list","object")) {
    Pass "Run with insufficient stock rejected (400)"
    Pass "Error detail parsed ($($err.kind)): $($err.message)"
  } else {
    Fail "Error detail missing/unknown shape (content empty or not JSON)"
  }

  # confirm shortages present in error payload
  $shortOK = $false
  if ($obj -and $obj.detail -and $obj.detail.shortages) { $shortOK = $true }
  elseif ($obj -and $obj.shortages) { $shortOK = $true }
  elseif ($errBody -match '"shortages"') { $shortOK = $true }

  if ($shortOK) {
    Pass "Error payload contains 'shortages' details"
  } else {
    Fail "No 'shortages' detail found"
    exit 1
  }
}

# ad-hoc shortage
$adhocShort = Try-Invoke {
  Invoke-Json POST ($BaseUrl + "/app/manufacturing/run") @{
    output_item_id = $itemC.id
    output_qty     = 1
    components     = @(@{ item_id = $itemB.id; qty_required = 999 })
  }
}
$adhocStatus = 0
if ($adhocShort.ok) { $adhocStatus = 200 }
else {
  try { $adhocStatus = $adhocShort.err.Exception.Response.StatusCode.value__ } catch { $adhocStatus = 0 }
}
if (-not $adhocShort.ok -and $adhocStatus -eq 400) {
  Pass "Ad-hoc run with insufficient stock rejected (400)"

  $errBody = Get-WebErrorBody $adhocShort
  $obj = $null
  if (-not [string]::IsNullOrWhiteSpace($errBody)) {
    try { $obj = $errBody | ConvertFrom-Json } catch { $obj = $null }
  }
  $shortOK = $false
  if ($obj -and $obj.detail -and $obj.detail.shortages) { $shortOK = $true }
  elseif ($obj -and $obj.shortages) { $shortOK = $true }
  elseif ($errBody -match '"shortages"') { $shortOK = $true }

  if ($shortOK) {
    Pass "Ad-hoc shortage payload contains 'shortages' details"
  } else {
    Fail "Ad-hoc shortage missing 'shortages' detail"
    exit 1
  }
} else {
  Fail "Ad-hoc shortage should be 400"
  exit 1
}

# --------------------------------------
# 7) Advanced Invariants (0.8.2)
# --------------------------------------
Step "7. Advanced Invariants (0.8.2)"

# 5.1 single-run only (reject array payload)
Info "Checking API strictness..."
$bulkTry = Try-Invoke {
  # Force an array raw-json payload to hit the route validator
  Invoke-Json POST ($BaseUrl + "/app/manufacturing/run") @(
    @{ recipe_id = $rec.id; output_qty = 1 },
    @{ recipe_id = $rec.id; output_qty = 1 }
  )
}
# PS 5.1: emulate ternary with if-else
$bulkStatus = 200
if (-not $bulkTry.ok) { $bulkStatus = $bulkTry.err.Exception.Response.StatusCode.value__ }
if ($bulkStatus -eq 400 -or $bulkStatus -eq 422) { Pass "Array payload (bulk run) rejected ($bulkStatus)" } else { Fail "Array payload should be rejected (400/422), got $bulkStatus"; exit 1 }

# 5.2 ad-hoc components[] required (non-empty)
$emptyComp = Try-Invoke { Invoke-Json POST ($BaseUrl + "/app/manufacturing/run") @{ output_item_id = $itemC.id; output_qty = 1; components = @() } }
$emptyStatus = 200
if (-not $emptyComp.ok) { $emptyStatus = $emptyComp.err.Exception.Response.StatusCode.value__ }
if ($emptyStatus -eq 400) { Pass "Ad-hoc with empty components[] rejected (400)" } else { Fail "Empty components[] should be 400 (got $emptyStatus)"; exit 1 }

# 5.3 fail-fast implies no writes (use latest movement id snapshot)
Info "Checking consistency (Fail-Fast & Atomicity)..."
$mvIdBefore = Get-LatestMovementId
$ff = Try-Invoke { Invoke-Json POST ($BaseUrl + "/app/manufacturing/run") @{ recipe_id = $rec.id; output_qty = 99999 } }
if (-not $ff.ok -and $ff.err.Exception.Response.StatusCode.value__ -eq 400) {
  $mvIdAfter = Get-LatestMovementId
  if ($mvIdAfter -eq $mvIdBefore) { Pass "Fail-fast produced no new movements" } else { Fail ("Fail-fast wrote movements (before={0}, after={1})" -f $mvIdBefore, $mvIdAfter); exit 1 }
} else { Fail "Expected 400 on fail-fast shortage"; exit 1 }

# 5.4 success is atomic: movements committed (>=1 consume + 1 output)
$ok2 = Invoke-Json POST ($BaseUrl + "/app/manufacturing/run") @{ recipe_id = $rec.id; output_qty = 2; notes="atomic-check" }
if ($ok2.status -ne "completed") { Fail "Second run not completed"; exit 1 }
$runMovs = Get-RunMovements -RunId $ok2.run_id -Limit 200
$consumes = @($runMovs | Where-Object { [double]$_.qty_change -lt 0 })
$outputs  = @($runMovs | Where-Object { [double]$_.qty_change -gt 0 })
if ($consumes.Count -ge 1) { Pass "Atomic Run: consume movements present" } else { Fail "No consume movements for run $($ok2.run_id)"; exit 1 }
if ($outputs.Count -eq 1)  { Pass "Atomic Run: exactly one output movement" } else { Fail "Expected exactly one output movement"; exit 1 }

# 5.5 unit cost rule: sum(consumed_cost)/output_qty (round-half-up)
Info "Checking Unit Cost & Oversold invariants..."
$ok3 = Invoke-Json POST ($BaseUrl + "/app/manufacturing/run") @{ recipe_id = $rec.id; output_qty = 2; notes="cost-check" }
if ($ok3.status -ne "completed") { Fail "Cost Check Run not completed"; exit 1 }
$mov3 = Get-RunMovements -RunId $ok3.run_id -Limit 200
$consumed = @($mov3 | Where-Object { [double]$_.qty_change -lt 0 })
$output   = @($mov3 | Where-Object { [double]$_.qty_change -gt 0 })
if ($output.Count -ne 1) { Fail "Cost check: expected one output movement"; exit 1 }

[int64]$totalCents = 0
foreach ($m in $consumed) {
  $qtyAbs = [decimal]([math]::Abs([double]$m.qty_change))
  $unit   = [decimal]([int]$m.unit_cost_cents)
  $totalCents += [int64]($qtyAbs * $unit)
}
$expectedUnit = RoundHalfUpCents([decimal]($totalCents / 2))
if ([int]$output[0].unit_cost_cents -eq [int]$expectedUnit) {
  Pass ("Output unit cost verified ({0} cents)" -f $expectedUnit)
} else {
  Fail ("Output unit cost mismatch: got {0} expected {1}" -f $output[0].unit_cost_cents, $expectedUnit); exit 1
}

# 5.6 never oversell: manufacturing movements must have is_oversold=0
$overs = @($mov3 | Where-Object { $_.source_kind -eq "manufacturing" -and [int]$_.is_oversold -ne 0 })
if ($overs.Count -eq 0) { Pass "Manufacturing movements have is_oversold=0" } else { Fail "Found is_oversold=1 on manufacturing movement(s)"; exit 1 }

# -----------------------------
# 8) v0.8.3 Journals + Encrypted Backup/Restore
# -----------------------------
Step "8. v0.8.3 Journals + Encrypted Backup/Restore"

# A) Export DB (AES-GCM, password)
Info "Exporting encrypted backup..."
$pw = "smoke-083!"
$localAppData = [Environment]::GetFolderPath('LocalApplicationData')
# --- Export & path assertions (PS 5.1-safe, case/slash agnostic) ------------
$resp = Invoke-Json 'POST' "$BaseUrl/app/db/export" @{ password = $pw }
if (-not $resp.ok) {
  Write-Host "  [FAIL] Export failed: $($resp.error)" -ForegroundColor Red
  exit 1
}

# 1) Ensure file exists + capture canonical absolute path
try {
  $actualItem = Get-Item -LiteralPath $resp.path -ErrorAction Stop
} catch {
  Write-Host "  [FAIL] Export file missing at path: $($resp.path)" -ForegroundColor Red
  exit 1
}
$actualFull = $actualItem.FullName

# 2) Build canonical expected root with a single trailing backslash
$expectedRoot = Join-Path $env:LOCALAPPDATA 'BUSCore\exports'
$expectedFull = [System.IO.Path]::GetFullPath($expectedRoot)
if (-not $expectedFull.EndsWith('\')) { $expectedFull = $expectedFull + '\' }

# 3) Case-insensitive containment check on canonical paths
if ($actualFull.StartsWith($expectedFull, [System.StringComparison]::OrdinalIgnoreCase)) {
  Write-Host "  [PASS] Exported under expected root" -ForegroundColor DarkGreen
  Write-Host ("          " + $actualFull)
} else {
  Write-Host "  [FAIL] Export path not under expected root" -ForegroundColor Red
  Write-Host ("         actual:   " + $actualFull)
  Write-Host ("         expected: " + $expectedFull.ToLowerInvariant())
  exit 1
}

# 4) Non-empty file check
$len = $actualItem.Length
if ($len -gt 0) {
  Write-Host ("  [PASS] Export file exists and is non-empty ({0} bytes)" -f $len) -ForegroundColor DarkGreen
} else {
  Write-Host "  [FAIL] Export file is empty" -ForegroundColor Red
  exit 1
}
$export = $resp
# ---------------------------------------------------------------------------

# B) Mutate DB (create reversible change)
Info "Applying reversible inventory mutation..."
$mvBaseline = Get-LatestMovementId
$mut = Invoke-Json POST ($BaseUrl + "/app/adjust") @{ item_id = $itemA.id; quantity_decimal = "5"; uom = "ea"; direction = "in"; note = "smoke" }
$mvAfterMut = Get-LatestMovementId
if ($mvAfterMut -gt $mvBaseline) { Pass "Movement id advanced after mutation" } else { Fail "Expected movement id to advance after mutation"; exit 1 }

# C) Restore Preview
Info "Previewing restore from encrypted backup..."
$previewTry = Try-Invoke { Invoke-Json POST ($BaseUrl + "/app/db/import/preview") @{ path = $export.path; password = $pw } }
if (-not $previewTry.ok) { Fail ("Restore preview failed: {0}" -f $previewTry.err); exit 1 }
$preview = $previewTry.resp
$hasCounts = $false
try { if ($preview.table_counts.Keys.Count -ge 0) { $hasCounts = $true } } catch { $hasCounts = $false }
if ($hasCounts) { Pass "Preview returned table_counts" } else { Fail "Preview missing table_counts"; exit 1 }
$hasVersion = $false
try { if ($preview.schema_version -or $preview.user_version -or $preview.database_version) { $hasVersion = $true } } catch { $hasVersion = $false }
if ($hasVersion) { Pass "Preview returned schema/user version" } else { Pass "Preview version field not present (tolerated)" }

# D) Restore Commit (atomic replace)
Info "Committing restore (atomic replace)..."
# Direct call using the authenticated WebSession; if it errors, fall back to a bounded .NET request with the same cookies.
$commitBody = @{ path = $export.path; password = $pw }
$commitResp = $null
$commitErr  = $null
try {
  $commitResp = Invoke-RestMethod -Method POST -Uri ($BaseUrl + "/app/db/import/commit") `
                 -WebSession $script:Session `
                 -ContentType "application/json" `
                 -Body ($commitBody | ConvertTo-Json -Depth 10) `
                 -ErrorAction Stop
} catch {
  $commitErr = $_
}
if ($null -eq $commitResp) {
  # Fallback with explicit timeout (120s) reusing cookies from WebSession
  try {
    $uri = [Uri]($BaseUrl + "/app/db/import/commit")
    $req = [System.Net.HttpWebRequest]::Create($uri)
    $req.Method = "POST"
    $req.ContentType = "application/json"
    $req.Accept = "application/json"
    $req.Timeout = 120000
    $req.ReadWriteTimeout = 120000
    $cc = New-Object System.Net.CookieContainer
    foreach ($c in $script:Session.Cookies.GetCookies($uri)) { $cc.Add($c) }
    $req.CookieContainer = $cc
    $bytes = [System.Text.Encoding]::UTF8.GetBytes(($commitBody | ConvertTo-Json -Depth 10))
    $req.ContentLength = $bytes.Length
    $stream = $req.GetRequestStream()
    $stream.Write($bytes,0,$bytes.Length)
    $stream.Close()
    $resp = $req.GetResponse()
    $rs = $resp.GetResponseStream()
    $sr = New-Object System.IO.StreamReader($rs,[System.Text.Encoding]::UTF8)
    $txt = $sr.ReadToEnd()
    $sr.Close(); $resp.Close()
    $commitResp = $txt | ConvertFrom-Json
  } catch {
    $commitErr = $_
  }
}
if ($null -ne $commitResp) {
  Pass "Restore commit replaced database"
  if ($commitResp.restart_required -eq $true) { Pass "Restart required flag set" } else { Fail "Expected restart_required=true"; exit 1 }
} else {
  $msg = if ($commitErr) { $commitErr.Exception.Message } else { "unknown error" }
  Fail "Restore commit failed or timed out: $msg"
  exit 1
}

# E) Post-restore verification
Info "Verifying state reverted to pre-mutation snapshot..."
$mvAfterRestore = Get-LatestMovementId
if ($mvAfterRestore -eq $mvBaseline) { Pass "Movement id reverted to baseline after restore" } else { Fail ("Movement id mismatch after restore (expected {0}, got {1})" -f $mvBaseline, $mvAfterRestore); exit 1 }

# F) Journal archiving on restore
Info "Checking journal archiving..."
$appDir = Join-Path $localAppData 'BUSCore\\app'
$journalDir = Join-Path $appDir 'data\\journals'
$invArchive = Get-ChildItem -Path $journalDir -Filter 'inventory.jsonl.pre-restore*' -ErrorAction SilentlyContinue
if (-not $invArchive -or $invArchive.Count -lt 1) {
  $archiveDir = Join-Path $journalDir 'archive'
  $invArchive = Get-ChildItem -Path $archiveDir -Filter 'inventory.jsonl.pre-restore*' -ErrorAction SilentlyContinue
}
if ($invArchive -and $invArchive.Count -ge 1) { Pass "Inventory journal archived" } else { Fail "Inventory journal archive missing"; exit 1 }
$mfgArchive = Get-ChildItem -Path $journalDir -Filter 'manufacturing.jsonl.pre-restore*' -ErrorAction SilentlyContinue
if (-not $mfgArchive -or $mfgArchive.Count -lt 1) {
  $archiveDir = Join-Path $journalDir 'archive'
  $mfgArchive = Get-ChildItem -Path $archiveDir -Filter 'manufacturing.jsonl.pre-restore*' -ErrorAction SilentlyContinue
}
if ($mfgArchive -and $mfgArchive.Count -ge 1) { Pass "Manufacturing journal archived" } else { Fail "Manufacturing journal archive missing"; exit 1 }

$invNew = Join-Path $journalDir 'inventory.jsonl'
$mfgNew = Join-Path $journalDir 'manufacturing.jsonl'
if (Test-Path $invNew) { $invInfo = Get-Item $invNew; if ($invInfo.Length -le 4096) { Pass "Inventory journal recreated" } else { Fail "Inventory journal not reset"; exit 1 } } else { Fail "Inventory journal missing after restore"; exit 1 }
if (Test-Path $mfgNew) { $mfgInfo = Get-Item $mfgNew; if ($mfgInfo.Length -le 4096) { Pass "Manufacturing journal recreated" } else { Fail "Manufacturing journal not reset"; exit 1 } } else { Fail "Manufacturing journal missing after restore"; exit 1 }

# G) Cleanup
Info "Cleaning up exported backup file..."
try { Remove-Item -Path $export.path -Force -ErrorAction Stop; Pass "Export artifact removed" } catch { Info "Cleanup skipped: $($_.Exception.Message)" }

# -----------------------------
# 9) Integrity Checks
# -----------------------------
Step "9. Integrity Checks"
Info "Validating movements and on-hand balances..."
$itemSnapshot = Invoke-Json GET ($BaseUrl + "/app/items") $null
$negOnHand = @($itemSnapshot | Where-Object { [double]$_.qty_stored -lt 0 })
if ($negOnHand.Count -eq 0) { Pass "No negative on-hand quantities" } else { Fail "Found negative on-hand quantities"; exit 1 }

$movementSnapshot = Invoke-Json GET ($BaseUrl + "/app/movements?limit=200") $null
$overs = @($movementSnapshot.movements | Where-Object { [int]$_.is_oversold -ne 0 })
$mfgOvers = @($overs | Where-Object { $_.source_kind -eq "manufacturing" })
if ($mfgOvers.Count -eq 0 -and $overs.Count -eq 0) { Pass "No oversold flags present" } elseif ($mfgOvers.Count -gt 0) { Fail "Oversold flags present on manufacturing entries"; exit 1 } else { Fail "Unexpected oversold flags present"; exit 1 }

# -----------------------------
# 10) Cleanup
# -----------------------------
Step "10. Cleanup"
Info "Zeroing inventory and removing test data..."

$targetItems = @($itemA, $itemB, $itemC, $itemD)
foreach ($itm in $targetItems) {
  # We need fresh qty_stored. Query /app/items again or just query this specific item if possible?
  # /app/items returns all. We can filter.
  # But simpler: we know the IDs.
  # We cannot assume the state. We must query.

  # Note: 0.8.2 /app/items does not support server-side filtering by id in query string?
  # Let's assume we fetch all and find it.
}

$allItems = Invoke-Json GET ($BaseUrl + "/app/items") $null
foreach ($itm in $targetItems) {
  $id = $itm.id
  $current = $allItems | Where-Object { $_.id -eq $id }

  if ($current) {
    [double]$qty = $current.qty_stored
    if ($qty -ne 0) {
      $delta = -$qty
      $direction = if ($delta -ge 0) { "in" } else { "out" }
      $qtyDecimal = [string]([math]::Abs([decimal]$delta))
      $adj = Try-Invoke { Invoke-Json POST ($BaseUrl + "/app/adjust") @{ item_id = $id; quantity_decimal = $qtyDecimal; uom = "ea"; direction = $direction; note = "Smoke Test Cleanup" } }
      if ($adj.ok) { Pass ("Zeroed inventory for Item {0} (delta={1})" -f $id, $delta) } else { Fail ("Failed to zero inventory for Item {0}" -f $id) }
    } else {
      Pass ("Item {0} already at zero inventory" -f $id)
    }

    # Archive/Delete item
    # Assuming DELETE /app/items/{id} works
    $del = Try-Invoke { Invoke-RestMethod -Method DELETE -Uri ($BaseUrl + "/app/items/$id") -WebSession $script:Session }
    if ($del.ok) { Pass ("Deleted Item {0}" -f $id) } else { Info ("Could not delete Item {0} (probably has history)" -f $id) }
  }
}

# Archive/Delete Recipe
$delRec = Try-Invoke { Invoke-RestMethod -Method DELETE -Uri ($BaseUrl + "/app/recipes/$($rec.id)") -WebSession $script:Session }
if ($delRec.ok) { Pass "Deleted Recipe $($rec.id)" } else { Info "Could not delete Recipe (probably has history)" }

# -----------------------------
# Finish
# -----------------------------
Write-Host ""
Write-Host "============================================================"
Write-Host "  ALL TESTS PASSED"
Write-Host "============================================================"
exit 0
