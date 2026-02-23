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
    rg -n --no-heading -e "$pattern" "$target" || true
  else
    grep -nRE "$pattern" "$target" || true
  fi
}

capture() {
  local key="$1"
  local pattern="$2"
  local target="$3"
  local file="/tmp/ui_contract_${key}.txt"
  run_search "$pattern" "$target" > "$file"
  echo "$file"
}

count_lines() {
  local file="$1"
  if [[ -s "$file" ]]; then
    wc -l < "$file" | tr -d ' '
  else
    echo 0
  fi
}

noncanonical_lines() {
  local file="$1"
  awk -F: '$1 != "core/ui/js/api/canonical.js" { print }' "$file" || true
}

A1=$(capture "a1_api" "['\"]/api/" "core/ui/js")
A2=$(capture "a2_ledger" "['\"]/ledger/" "core/ui/js")
A3=$(capture "a3_mfg" "['\"]/manufacturing/" "core/ui/js")
A4=$(capture "a4_tokens" "\\bstock_in\\b|manufacturing/run|ledger/movements" "core/ui/js")

B1=$(capture "b_qtykeys" "\\bqty\\b\\s*:|\\bqty_base\\b\\s*:|\\bquantity_int\\b\\s*:|\\boutput_qty\\b\\s*:|\\bqty_required\\b\\s*:" "core/ui/js")
C1=$(capture "c_multiplier" "\\*1000\\b|/1000\\b|\\bbaseQty\\b|\\bmultiplier\\b" "core/ui/js")
D1=$(capture "d_finance" "unit_cost_decimal" "core/ui/js")

E_STOCK_IN=$(capture "e_stock_in" "['\"]/app/stock/in['\"]" "core/ui/js")
E_STOCK_OUT=$(capture "e_stock_out" "['\"]/app/stock/out['\"]" "core/ui/js")
E_PURCHASE=$(capture "e_purchase" "['\"]/app/purchase['\"]" "core/ui/js")
E_LEDGER_HISTORY=$(capture "e_ledger_history" "['\"]/app/ledger/history['\"]" "core/ui/js")
E_MANUFACTURE=$(capture "e_manufacture" "['\"]/app/manufacture['\"]" "core/ui/js")

A_COUNT=$(( $(count_lines "$A1") + $(count_lines "$A2") + $(count_lines "$A3") + $(count_lines "$A4") ))
B_COUNT=$(count_lines "$B1")
C_COUNT=$(count_lines "$C1")
D_COUNT=$(count_lines "$D1")

E_NONCANONICAL=0
for f in "$E_STOCK_IN" "$E_STOCK_OUT" "$E_PURCHASE" "$E_LEDGER_HISTORY" "$E_MANUFACTURE"; do
  noncanon=$(noncanonical_lines "$f")
  if [[ -n "$noncanon" ]]; then
    E_NONCANONICAL=$((E_NONCANONICAL + 1))
  fi
done

STATUS="PASS"
if (( A_COUNT > 0 || B_COUNT > 0 || C_COUNT > 0 || D_COUNT > 0 || E_NONCANONICAL > 0 )); then
  STATUS="FAIL"
fi

TS="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"

{
  echo "# UI Contract Audit Report"
  echo
  echo "- Timestamp (UTC): ${TS}"
  echo "- Repo: ${ROOT_DIR}"
  echo "- Search tool: ${SEARCH_TOOL}"
  echo "- Overall status: **${STATUS}**"
  echo
  echo "## Commands"
  echo
  echo '```bash'
  echo "rg -n \"['\\\"]/api/\" core/ui/js"
  echo "rg -n \"['\\\"]/ledger/\" core/ui/js"
  echo "rg -n \"['\\\"]/manufacturing/\" core/ui/js"
  echo "rg -n \"\\bstock_in\\b|manufacturing/run|ledger/movements\" core/ui/js"
  echo "rg -n \"\\bqty\\b\\s*:|\\bqty_base\\b\\s*:|\\bquantity_int\\b\\s*:|\\boutput_qty\\b\\s*:|\\bqty_required\\b\\s*:\" core/ui/js"
  echo "rg -n \"\\*1000\\b|/1000\\b|\\bbaseQty\\b|\\bmultiplier\\b\" core/ui/js"
  echo "rg -n \"unit_cost_decimal\" core/ui/js"
  echo "rg -n \"['\\\"]/app/stock/in['\\\"]\" core/ui/js"
  echo "rg -n \"['\\\"]/app/stock/out['\\\"]\" core/ui/js"
  echo "rg -n \"['\\\"]/app/purchase['\\\"]\" core/ui/js"
  echo "rg -n \"['\\\"]/app/ledger/history['\\\"]\" core/ui/js"
  echo "rg -n \"['\\\"]/app/manufacture['\\\"]\" core/ui/js"
  echo '```'
  echo

  print_section() {
    local title="$1"
    local file="$2"
    local count
    count=$(count_lines "$file")
    echo "## ${title} (${count})"
    if (( count == 0 )); then
      echo
      echo "No matches."
      echo
    else
      echo
      echo '```text'
      cat "$file"
      echo '```'
      echo
    fi
  }

  print_section "Forbidden endpoint strings found: ['\"]/api/" "$A1"
  print_section "Forbidden endpoint strings found: ['\"]/ledger/" "$A2"
  print_section "Forbidden endpoint strings found: ['\"]/manufacturing/" "$A3"
  print_section "Forbidden endpoint token patterns found" "$A4"
  print_section "Forbidden payload keys found" "$B1"
  print_section "Multiplier/base conversion logic found" "$C1"
  print_section "Finance suspicious legacy fields found" "$D1"

  echo "## Canonical endpoint containment check"
  echo

  for pair in \
    "['\"]/app/stock/in['\"]:$E_STOCK_IN" \
    "['\"]/app/stock/out['\"]:$E_STOCK_OUT" \
    "['\"]/app/purchase['\"]:$E_PURCHASE" \
    "['\"]/app/ledger/history['\"]:$E_LEDGER_HISTORY" \
    "['\"]/app/manufacture['\"]:$E_MANUFACTURE"; do
    endpoint="${pair%%:*}"
    file="${pair#*:}"
    count=$(count_lines "$file")
    echo "### ${endpoint} (${count} matches)"
    if (( count == 0 )); then
      echo
      echo "No matches found."
      echo
      continue
    fi

    noncanon=$(noncanonical_lines "$file")
    if [[ -n "$noncanon" ]]; then
      echo
      echo "**FAIL** - found outside canonical client:"
      echo
      echo '```text'
      echo "$noncanon"
      echo '```'
      echo
    else
      echo
      echo "PASS - all matches contained in core/ui/js/api/canonical.js"
      echo
      echo '```text'
      cat "$file"
      echo '```'
      echo
    fi
  done

  echo "## Summary"
  echo
  echo "- Forbidden endpoint matches: ${A_COUNT}"
  echo "- Forbidden payload-key matches: ${B_COUNT}"
  echo "- Multiplier/base-conversion matches: ${C_COUNT}"
  echo "- Finance legacy-field matches: ${D_COUNT}"
  echo "- Canonical containment endpoint violations: ${E_NONCANONICAL}"
  echo "- Final result: **${STATUS}**"
} > "$REPORT_PATH"

echo "UI contract audit: ${STATUS}"
echo "  forbidden endpoints: ${A_COUNT}"
echo "  forbidden payload keys: ${B_COUNT}"
echo "  multiplier/base logic: ${C_COUNT}"
echo "  finance legacy fields: ${D_COUNT}"
echo "  canonical containment violations: ${E_NONCANONICAL}"
echo "  report: ${REPORT_PATH}"

if [[ "$STATUS" == "FAIL" ]]; then
  exit 1
fi
