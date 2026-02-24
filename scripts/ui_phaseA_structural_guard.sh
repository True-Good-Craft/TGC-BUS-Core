#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if command -v rg >/dev/null 2>&1; then
  SEARCH_TOOL="rg"
else
  SEARCH_TOOL="grep"
fi

search_lines() {
  local pattern="$1"
  local target="$2"
  if [[ "$SEARCH_TOOL" == "rg" ]]; then
    rg -n --no-heading -e "$pattern" "$target" 2>/dev/null || true
  else
    grep -nRE "$pattern" "$target" 2>/dev/null || true
  fi
}

print_guard() {
  local label="$1"
  local status="$2"
  echo "${label}: ${status}"
}

failures=0

# Guard 1
G1="$(search_lines 'fetch\(' core/ui | awk 'NF' | sed 's|^\./||' | grep -Ev '^core/ui/js/api\.js:|^core/ui/js/token\.js:' || true)"
if [[ -n "$G1" ]]; then
  print_guard 'Guard 1 (fetch outside api.js/token.js)' 'FAIL'
  printf '%s\n' "$G1"
  failures=$((failures + 1))
else
  print_guard 'Guard 1 (fetch outside api.js/token.js)' 'PASS'
fi

# Guard 2
G2="$(search_lines 'window\.fetch' core/ui | awk 'NF' | sed 's|^\./||' | grep -Ev '^core/ui/js/token\.js:' || true)"
if [[ -n "$G2" ]]; then
  print_guard 'Guard 2 (window.fetch outside token.js)' 'FAIL'
  printf '%s\n' "$G2"
  failures=$((failures + 1))
else
  print_guard 'Guard 2 (window.fetch outside token.js)' 'PASS'
fi

# Guard 3
G3="$(search_lines '/app/inventory/run' core/ui | awk 'NF' | sed 's|^\./||' || true)"
if [[ -n "$G3" ]]; then
  print_guard 'Guard 3 (/app/inventory/run under core/ui)' 'FAIL'
  printf '%s\n' "$G3"
  failures=$((failures + 1))
else
  print_guard 'Guard 3 (/app/inventory/run under core/ui)' 'PASS'
fi

# Guard 4
G4="$(
  {
    search_lines '(qty_base|\bqty\b|quantity_int|output_qty|qty_required|raw_qty)\s*:' core/ui/app.js
    search_lines '(qty_base|\bqty\b|quantity_int|output_qty|qty_required|raw_qty)\s*:' core/ui/js/cards
    search_lines '(qty_base|\bqty\b|quantity_int|output_qty|qty_required|raw_qty)\s*:' core/ui/js/routes
    search_lines '(qty_base|\bqty\b|quantity_int|output_qty|qty_required|raw_qty)\s*:' core/ui/js/api
  } | awk 'NF' | sed 's|^\./||' | grep -Ev '^core/ui/js/token\.js:|^core/ui/js/lib/units\.js:|^core/ui/js/utils/measurement\.js:' || true
)"
if [[ -n "$G4" ]]; then
  print_guard 'Guard 4 (legacy qty-key payload signatures)' 'FAIL'
  printf '%s\n' "$G4"
  failures=$((failures + 1))
else
  print_guard 'Guard 4 (legacy qty-key payload signatures)' 'PASS'
fi

# Guard 5 (note only)
G5="$(search_lines '\*\s*1000|/\s*1000|\bmultiplier\b|\bbaseQty\b|toMetricBase\(|fromBaseQty\(' core/ui | awk 'NF' | sed 's|^\./||' || true)"
if [[ -n "$G5" ]]; then
  print_guard 'Guard 5 (conversion signatures)' 'NOTE'
  printf '%s\n' "$G5"
else
  print_guard 'Guard 5 (conversion signatures)' 'PASS'
fi

# Guard 6
G6="$(search_lines "uom\s*:\s*.*\|\|\s*['\"]ea['\"]|uom\s*:\s*['\"]ea['\"]" core/ui/js/cards | awk 'NF' | sed 's|^\./||' || true)"
if [[ -n "$G6" ]]; then
  print_guard "Guard 6 (uom fallback-to-'ea' payload patterns in cards)" 'FAIL'
  printf '%s\n' "$G6"
  failures=$((failures + 1))
else
  print_guard "Guard 6 (uom fallback-to-'ea' payload patterns in cards)" 'PASS'
fi

if (( failures > 0 )); then
  echo "Phase A structural guard: FAIL (${failures} failing guard(s))"
  exit 1
fi

echo 'Phase A structural guard: PASS'
