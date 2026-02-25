@echo off
cd /d "%~dp0"

echo ==========================================
echo Running BUS Core Smoke Test
echo ==========================================

powershell -NoProfile -ExecutionPolicy Bypass -File ".\scripts\smoke.ps1"

echo.
echo ==========================================
echo Smoke test finished.
echo ==========================================
pause