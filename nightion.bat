@echo off
title Nightion AI — Starting...
echo ========================================
echo   NIGHTION — Fresh Start
echo ========================================
echo.

:: 1. Kill anything already on port 8999
echo [1/4] Port Security: Checking port 8999...
setlocal enabledelayedexpansion
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8999 ^| findstr LISTENING 2^>nul') do (
    if "%%a" neq "0" (
        echo [!] Found previous instance ^(PID: %%a^). Closing...
        taskkill /f /t /pid %%a >nul 2>&1
    )
)

:: 2. Restart Ollama LLM
echo [2/4] Restarting LLM: Killing previous Ollama instances...
taskkill /f /im ollama.exe >nul 2>&1
taskkill /f /im "ollama app.exe" >nul 2>&1

:: 3. Brief pause to ensure ports are released
echo [3/4] Stability: Waiting for port release...
ping -n 3 127.0.0.1 >nul

:: 4. Set working directory
echo [4/4] Launch: Starting Ollama and Nightion fresh...
cd /d "%~dp0"

:: Start Ollama in the background
start "" /B cmd /c "ollama serve"

:: --- Find Python launcher (py preferred, fallback to python) ---
where py >nul 2>&1
if %ERRORLEVEL% == 0 (
    set PYTHON=py
) else (
    set PYTHON=python
)

echo.
echo ========================================
echo   Nightion Server Protocol Initialized
echo   Host: http://127.0.0.1:8999
echo   Python: %PYTHON%
echo ========================================
echo.

:: Open browser AFTER server has had time to start (8 seconds)
start "" cmd /c "ping -n 9 127.0.0.1 >nul && start http://127.0.0.1:8999"

:: Start Smart Cursor hotkey listener in background (windowless)
echo [+] Starting Smart Cursor (Ctrl+Shift+0)...
start "" /B pythonw smart_cursor.pyw

:: Start uvicorn — blocks here until server stops
%PYTHON% -m uvicorn nightion_core:app --host 0.0.0.0 --port 8999 --reload

if %ERRORLEVEL% neq 0 (
    echo.
    echo [ERROR] Nightion failed to start.
    echo Possible reasons:
    echo   - Python is not in your PATH (tried: %PYTHON%)
    echo   - Missing dependencies  ^(run: %PYTHON% -m pip install fastapi uvicorn^)
    echo   - Port 8999 is blocked by another service
    echo.
    pause
)
