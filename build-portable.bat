@echo off
title Build AI Video Dubber Portable (Toi Uu Dung Luong)
cd /d "%~dp0"
echo ================================================================
echo     DONG GOI AI VIDEO DUBBER PORTABLE (SIEU TOI UU DUNG LUONG)
echo ================================================================
echo.

set "PY_CMD=python"
if exist "tools\python_embed\python.exe" (
    set "PY_CMD=tools\python_embed\python.exe"
)

"%PY_CMD%" scripts\bundle_portable.py
if errorlevel 1 (
    echo.
    echo [ERROR] Dong goi Windows Portable me loi! Dung qua trinh.
    pause
    exit /b 1
)

echo.
echo ================================================================
echo Hoan tat! Thu muc xuat ra: AI-Video-Dubber-Portable
echo ================================================================
pause
