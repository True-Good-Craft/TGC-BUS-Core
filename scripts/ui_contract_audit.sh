#!/usr/bin/env bash
set -euo pipefail

# (1) fetch guard
bad=$(grep -R "fetch(" -n core/ui | grep -v "core/ui/js/api.js" | grep -v "core/ui/js/token.js" || true)
if [ -n "$bad" ]; then
  echo "FAIL fetch guard"
  echo "$bad"
  exit 1
fi
echo "PASS fetch guard"

# (2) window.fetch guard
bad=$(grep -R "window\\.fetch" -n core/ui | grep -v "core/ui/js/token.js" || true)
if [ -n "$bad" ]; then
  echo "FAIL window.fetch guard"
  echo "$bad"
  exit 1
fi
echo "PASS window.fetch guard"

# (3) forbidden legacy endpoint
bad=$(grep -R "/app/inventory/run" -n core/ui || true)
if [ -n "$bad" ]; then
  echo "FAIL legacy endpoint /app/inventory/run"
  echo "$bad"
  exit 1
fi
echo "PASS legacy endpoint guard"

# (4) forbidden legacy qty keys anywhere in core/ui (basic scan)
bad=$(grep -R -nE "\"qty_base\"|\bqty_base\b|\"qty\"|\bqty\b|\"quantity_int\"|\bquantity_int\b|\"output_qty\"|\boutput_qty\b|\"qty_required\"|\bqty_required\b|\"raw_qty\"|\braw_qty\b" core/ui || true)
if [ -n "$bad" ]; then
  echo "FAIL legacy qty keys present"
  echo "$bad"
  exit 1
fi
echo "PASS legacy qty keys guard"

# (5) forbidden conversion signatures (basic scan)
bad=$(grep -R -nE "\*\s*1000|/\s*1000|multiplier|baseQty|toMetricBase\(|fromBaseQty\(" core/ui || true)
if [ -n "$bad" ]; then
  echo "NOTE: conversion signatures found (may be allowed until Phase B)."
  echo "$bad"
  # DO NOT fail here (Phase B purge authorized later). Exit 0 for this section.
fi
echo "PASS conversion signatures guard"

# (6) mutation uom fallback 'ea' detector (WARN-only, Phase A should fail)
bad=$(grep -R -nE "uom\s*:\s*.*\|\|\s*['\"]ea['\"]|uom\s*:\s*['\"]ea['\"]" core/ui/js/cards || true)
if [ -n "$bad" ]; then
  echo "WARN: uom fallback patterns found (should be zero for payload paths after Phase A):"
  echo "$bad"
  # Fail in Phase A postwork:
  exit 1
fi
echo "PASS uom fallback guard"
