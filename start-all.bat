@echo off
cd /d "%~dp0"
title AI Video Dubber Launcher
echo ===================================================
echo        Starting AI Video Dubber (Backend + UI)
echo ===================================================

echo [*] Giai phong cong 5173 va 8787 neu dang bi chiem dung...
powershell -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*5173*' -or $_.CommandLine -like '*8787*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }" >nul 2>&1

echo [1/2] Launching Backend Engine (FastAPI on port 8787)...
if exist "%~dp0tools\python_embed\python.exe" (
    start "AI Video Dubber - Backend Engine" cmd /k "set PATH=%~dp0tools\ffmpeg;%~dp0tools\python_embed;%PATH% && set PYTHONPATH=%~dp0engine && tools\python_embed\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8787 --app-dir engine"
) else if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" (
    start "AI Video Dubber - Backend Engine" cmd /k "set PATH=%~dp0tools\ffmpeg;%PATH% && set PYTHONPATH=%~dp0engine && "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8787 --app-dir engine"
) else (
    start "AI Video Dubber - Backend Engine" cmd /k "set PATH=%~dp0tools\ffmpeg;%PATH% && cd /d %~dp0engine && if exist .venv\Scripts\activate (call .venv\Scripts\activate) && python -m uvicorn app.main:app --host 127.0.0.1 --port 8787 --app-dir ."
)

echo [2/2] Launching Desktop App (Vite + Electron)...
start "AI Video Dubber - Desktop App" cmd /c "cd /d %~dp0desktop && npm run dev"

echo.
echo All services launched!
echo - Backend API: http://127.0.0.1:8787
echo - Frontend Web: http://127.0.0.1:5173
echo.
