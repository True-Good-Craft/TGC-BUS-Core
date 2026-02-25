#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

REPORT_PATH="reports/ui_contract_audit.md"
mkdir -p reports

if command -v rg >/dev/null 2>&1; then
  SEARCH_TOOL="rg"
else
  SEARCH_TOOL="grep"
fi

run_search() {
  local pattern="$1"
  local target="$2"
  if [[ "$SEARCH_TOOL" == "rg" ]]; then
    rg -n --no-heading -e "$pattern" "$target" 2>/dev/null || true
  else
    grep -nRE "$pattern" "$target" 2>/dev/null || true
  fi
}

normalize_lines() {
  sed 's|^\./||' | awk 'NF'
}

count_lines() {
  local f="$1"
  [[ -s "$f" ]] || { echo 0; return; }
  awk 'NF{c++} END{print c+0}' "$f"
}

save_search() {
  local pattern="$1"
  local target="$2"
  local out
  out="$(mktemp)"
  run_search "$pattern" "$target" | normalize_lines > "$out"
  printf '%s\n' "$out"
}

filter_excluded_prefixes() {
  local in_file="$1"
  local out_file="$2"
  shift 2
  cp "$in_file" "$out_file"
  local prefix
  for prefix in "$@"; do
    grep -Ev "^${prefix}:" "$out_file" > "${out_file}.tmp" || true
    mv "${out_file}.tmp" "$out_file"
  done
}

merge_endpoint_matches() {
  local endpoint="$1"
  local out
  out="$(mktemp)"
  {
    run_search "\"${endpoint}\"" core/ui/js
    run_search "'${endpoint}'" core/ui/js
  } | normalize_lines | grep -Ev '^core/ui/js/token\.js:' | sort -u > "$out"
  printf '%s\n' "$out"
}

noncanonical_violation_count() {
  local f="$1"
  [[ -s "$f" ]] || { echo 0; return; }
  if awk 'NF && $0 !~ /^core\/ui\/js\/api\/canonical\.js:/' "$f" | grep -q .; then
    echo 1
  else
    echo 0
  fi
}

append_section() {
  local title="$1"
  local f="$2"
  local count
  count="$(count_lines "$f")"
  {
    echo "## $title ($count)"
    echo
    if [[ "$count" -eq 0 ]]; then
      echo "No matches."
      echo
    else
      echo '```text'
      cat "$f"
      echo '```'
      echo
    fi
  } >> "$REPORT_PATH"
}

A1="$(save_search "['\"]/api/" core/ui/js)"
A2="$(save_search "['\"]/ledger/" core/ui/js)"
A3="$(save_search "['\"]/manufacturing/" core/ui/js)"
A4="$(save_search "\\bstock_in\\b|manufacturing/run|ledger/movements" core/ui/js)"

B1_RAW="$(save_search "\\bqty\\b\\s*:|\\bqty_base\\b\\s*:|\\bquantity_int\\b\\s*:|\\boutput_qty\\b\\s*:|\\bqty_required\\b\\s*:" core/ui/js)"
B1="$(mktemp)"
filter_excluded_prefixes "$B1_RAW" "$B1" \
  'core/ui/js/token.js' \
  'core/ui/js/lib/units.js' \
  'core/ui/js/utils/measurement.js'

C1_RAW="$(save_search "\\*1000\\b|/1000\\b|\\bbaseQty\\b|\\bmultiplier\\b" core/ui/js)"
C1="$(mktemp)"
filter_excluded_prefixes "$C1_RAW" "$C1" \
  'core/ui/js/token.js' \
  'core/ui/js/lib/units.js' \
  'core/ui/js/utils/measurement.js'

D1="$(save_search "unit_cost_decimal" core/ui/js)"

E_STOCK_IN="$(merge_endpoint_matches '/app/stock/in')"
E_STOCK_OUT="$(merge_endpoint_matches '/app/stock/out')"
E_PURCHASE="$(merge_endpoint_matches '/app/purchase')"
E_LEDGER_HISTORY="$(merge_endpoint_matches '/app/ledger/history')"
E_MANUFACTURE="$(merge_endpoint_matches '/app/manufacture')"

A_COUNT=$(( $(count_lines "$A1") + $(count_lines "$A2") + $(count_lines "$A3") + $(count_lines "$A4") ))
B_COUNT="$(count_lines "$B1")"
C_COUNT="$(count_lines "$C1")"
D_COUNT="$(count_lines "$D1")"
E_NONCANONICAL=$(( $(noncanonical_violation_count "$E_STOCK_IN") + $(noncanonical_violation_count "$E_STOCK_OUT") + $(noncanonical_violation_count "$E_PURCHASE") + $(noncanonical_violation_count "$E_LEDGER_HISTORY") + $(noncanonical_violation_count "$E_MANUFACTURE") ))

STATUS="PASS"
if (( A_COUNT > 0 || B_COUNT > 0 || C_COUNT > 0 || D_COUNT > 0 || E_NONCANONICAL > 0 )); then
  STATUS="FAIL"
fi

TIMESTAMP="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

{
  echo '# UI Contract Audit Report'
  echo
  echo "- Timestamp (UTC): $TIMESTAMP"
  echo "- Repo: $ROOT_DIR"
  echo "- Search tool: $SEARCH_TOOL"
  echo "- Overall status: **$STATUS**"
  echo
  echo '## Commands'
  echo
  echo '```bash'
  echo "${SEARCH_TOOL} -n \"['\\\"]/api/\" core/ui/js"
  echo "${SEARCH_TOOL} -n \"['\\\"]/ledger/\" core/ui/js"
  echo "${SEARCH_TOOL} -n \"['\\\"]/manufacturing/\" core/ui/js"
  echo "${SEARCH_TOOL} -n \"\\bstock_in\\b|manufacturing/run|ledger/movements\" core/ui/js"
  echo "${SEARCH_TOOL} -n \"\\bqty\\b\\s*:|\\bqty_base\\b\\s*:|\\bquantity_int\\b\\s*:|\\boutput_qty\\b\\s*:|\\bqty_required\\b\\s*:\" core/ui/js"
  echo "${SEARCH_TOOL} -n \"\\*1000\\b|/1000\\b|\\bbaseQty\\b|\\bmultiplier\\b\" core/ui/js"
  echo "${SEARCH_TOOL} -n \"unit_cost_decimal\" core/ui/js"
  echo "${SEARCH_TOOL} -n \"[\"'\'']/app/stock/in[\"'\'']\" core/ui/js"
  echo "${SEARCH_TOOL} -n \"[\"'\'']/app/stock/out[\"'\'']\" core/ui/js"
  echo "${SEARCH_TOOL} -n \"[\"'\'']/app/purchase[\"'\'']\" core/ui/js"
  echo "${SEARCH_TOOL} -n \"[\"'\'']/app/ledger/history[\"'\'']\" core/ui/js"
  echo "${SEARCH_TOOL} -n \"[\"'\'']/app/manufacture[\"'\'']\" core/ui/js"
  echo '```'
  echo
} > "$REPORT_PATH"

append_section "Forbidden endpoint strings found: ['\"]/api/" "$A1"
append_section "Forbidden endpoint strings found: ['\"]/ledger/" "$A2"
append_section "Forbidden endpoint strings found: ['\"]/manufacturing/" "$A3"
append_section 'Forbidden endpoint token patterns found' "$A4"
append_section 'Forbidden payload keys found' "$B1"
append_section 'Multiplier/base conversion logic found' "$C1"
append_section 'Finance suspicious legacy fields found' "$D1"

{
  echo '## Canonical endpoint containment check'
  echo
} >> "$REPORT_PATH"

append_canonical_section() {
  local endpoint="$1"
  local f="$2"
  local count
  count="$(count_lines "$f")"
  {
    echo "### [\"'\"]/app/${endpoint}[\"'\"] (${count} matches)"
    if [[ "$count" -eq 0 ]]; then
      echo
      echo 'No matches found.'
      echo
      return
    fi
    local noncanon
    noncanon="$(mktemp)"
    awk 'NF && $0 !~ /^core\/ui\/js\/api\/canonical\.js:/' "$f" > "$noncanon"
    if [[ -s "$noncanon" ]]; then
      echo
      echo '**FAIL** - found outside canonical client:'
      echo
      echo '```text'
      cat "$noncanon"
      echo '```'
      echo
    else
      echo
      echo 'PASS - all matches contained in core/ui/js/api/canonical.js'
      echo
      echo '```text'
      cat "$f"
      echo '```'
      echo
    fi
    rm -f "$noncanon"
  } >> "$REPORT_PATH"
}

append_canonical_section 'stock/in' "$E_STOCK_IN"
append_canonical_section 'stock/out' "$E_STOCK_OUT"
append_canonical_section 'purchase' "$E_PURCHASE"
append_canonical_section 'ledger/history' "$E_LEDGER_HISTORY"
append_canonical_section 'manufacture' "$E_MANUFACTURE"

{
  echo '## Summary'
  echo
  echo "- Forbidden endpoint matches: $A_COUNT"
  echo "- Forbidden payload-key matches: $B_COUNT"
  echo "- Multiplier/base-conversion matches: $C_COUNT"
  echo "- Finance legacy-field matches: $D_COUNT"
  echo "- Canonical containment endpoint violations: $E_NONCANONICAL"
  echo "- Final result: **$STATUS**"
} >> "$REPORT_PATH"

echo "UI contract audit: $STATUS"
echo "  forbidden endpoints: $A_COUNT"
echo "  forbidden payload keys: $B_COUNT"
echo "  multiplier/base logic: $C_COUNT"
echo "  finance legacy fields: $D_COUNT"
echo "  canonical containment violations: $E_NONCANONICAL"
echo "  report: $REPORT_PATH"

rm -f "$A1" "$A2" "$A3" "$A4" "$B1_RAW" "$B1" "$C1_RAW" "$C1" "$D1" "$E_STOCK_IN" "$E_STOCK_OUT" "$E_PURCHASE" "$E_LEDGER_HISTORY" "$E_MANUFACTURE"

[[ "$STATUS" == "PASS" ]]
