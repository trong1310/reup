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

echo [1/2] Dang dong goi ban macOS (Thu muc AI-Video-Dubber-macOS)...
"%PY_CMD%" scripts\bundle_macos.py
if errorlevel 1 (
    echo.
    echo [ERROR] Dong goi macOS me loi! Dung qua trinh.
    pause
    exit /b 1
)

echo.
echo [2/2] Dang dong goi ban Windows Portable (Thu muc AI-Video-Dubber-Portable)...
"%PY_CMD%" scripts\bundle_portable.py
if errorlevel 1 (
    echo.
    echo [ERROR] Dong goi Windows Portable me loi! Dung qua trinh.
    pause
    exit /b 1
)

echo.
echo ================================================================
echo                    DONG GOI HOAN TAT 100%!
echo ================================================================
echo - Thu muc Windows Portable: AI-Video-Dubber-Portable
echo - Thu muc macOS Universal : AI-Video-Dubber-macOS
echo ================================================================
pause
