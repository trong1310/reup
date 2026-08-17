@echo off
title Build AI Video Dubber (Windows + macOS)
cd /d "%~dp0"
echo ================================================================
echo    DONG GOI AI VIDEO DUBBER: CA 2 PHIEN BAN (WINDOWS + MACOS)
echo ================================================================
echo.

set "PY_CMD=python"
if exist "tools\python_embed\python.exe" (
    set "PY_CMD=tools\python_embed\python.exe"
)

echo [1/3] Dang dong goi ban macOS Universal...
"%PY_CMD%" scripts\bundle_macos.py

echo.
echo [2/3] Dang dong goi ban Windows Portable...
"%PY_CMD%" scripts\bundle_portable.py

echo.
echo [3/3] Dang nen file ZIP Windows...
"%PY_CMD%" scripts\create_zip.py

echo.
echo ================================================================
echo                    DONG GOI HOAN TAT 100%!
echo ================================================================
echo - Ban Windows Portable: AI-Video-Dubber-Portable.zip (va thu muc AI-Video-Dubber-Portable)
echo - Ban macOS Universal : AI-Video-Dubber-macOS.zip (va thu muc AI-Video-Dubber-macOS)
echo ================================================================
pause
