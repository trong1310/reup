@echo off
cd /d "%~dp0"
if exist "..\tools\python_embed\python.exe" (
    set "PATH=%~dp0..\tools\ffmpeg;%~dp0..\tools\python_embed;%PATH%"
    set "PYTHONPATH=%~dp0"
    ..\tools\python_embed\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8787 --reload
) else (
    if exist .venv\Scripts\activate call .venv\Scripts\activate
    python -m uvicorn app.main:app --host 127.0.0.1 --port 8787 --reload
)
