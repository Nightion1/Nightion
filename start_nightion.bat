@echo off
title Nightion — AI Coding Brain
color 0B
echo.
echo ==========================================
echo     NIGHTION  v1.0  - Starting Up...
echo ==========================================
echo.

:: Make sure we're in the right directory
cd /d "%~dp0"

:: Check if Ollama is running, start it if not
tasklist /FI "IMAGENAME eq ollama.exe" 2>NUL | find /I "ollama.exe" >NUL
if %errorlevel% neq 0 (
    echo [*] Starting Ollama in background...
    where ollama >nul 2>&1
    if %errorlevel%==0 (
        start /min "" ollama serve
    ) else if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" (
        start /min "" "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" serve
    )
    timeout /t 3 /nobreak >nul
) else (
    echo [OK] Ollama is already running.
)

echo [*] Launching Nightion server...
echo [*] Open your browser to: http://localhost:8000
echo.
echo Press Ctrl+C to stop Nightion.
echo.

:: Open browser after 3 seconds
start "" cmd /c "timeout /t 3 /nobreak >nul && start http://localhost:8000"

:: Start the server
python server.py

