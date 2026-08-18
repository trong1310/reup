@echo off
title Build AI Video Dubber (macOS Edition)
cd /d "%~dp0"
echo ================================================================
echo          DONG GOI AI VIDEO DUBBER DANG CHO MAC OS
echo ================================================================
echo.

set "PY_CMD=python"
if exist "tools\python_embed\python.exe" (
    set "PY_CMD=tools\python_embed\python.exe"
)

"%PY_CMD%" scripts\bundle_macos.py

echo.
echo ================================================================
echo Hoan tat! Thu muc xuat ra: AI-Video-Dubber-macOS
echo ================================================================
pause
