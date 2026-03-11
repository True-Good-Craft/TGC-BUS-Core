@echo off
setlocal
title BUS-Core

REM Always run from this script's directory
cd /d "%~dp0"

REM Ensure dev mode is OFF for public builds
set "BUS_DEV="

REM Canonical native entry
python launcher.py

REM Keep window open so you can see errors/output
pause

