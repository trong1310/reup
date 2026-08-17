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

echo.
echo ================================================================
echo Ban co muon nen thu muc thanh file .ZIP ngay bay gio khong? (Y/N)
echo ================================================================
set /p user_choice="Chon (Y/N, mac dinh N): "
if /i "%user_choice%"=="Y" (
    "%PY_CMD%" scripts\create_zip.py
)

echo.
echo Hoan tat!
pause
