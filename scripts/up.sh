#!/usr/bin/env bash
set -euo pipefail
docker compose up -d --wait
if command -v open >/dev/null 2>&1; then
  open "http://localhost:8765/ui/shell.html#/home"
else
  xdg-open "http://localhost:8765/ui/shell.html#/home" >/dev/null 2>&1 || true
fi
