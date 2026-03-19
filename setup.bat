@echo off
title Nightion Setup
color 0B
echo.
echo ==========================================
echo   NIGHTION — AI CODING BRAIN  Setup
echo ==========================================
echo.

:: Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in PATH.
    echo Download Python 3.10+ from https://www.python.org/downloads/
    pause
    exit /b 1
)

echo [1/4] Python found. Installing dependencies...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install dependencies.
    pause
    exit /b 1
)

echo.
echo [2/4] Checking Ollama...

:: Try common install paths
set OLLAMA_FOUND=0
where ollama >nul 2>&1 && set OLLAMA_FOUND=1
if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" set OLLAMA_FOUND=1
if exist "%USERPROFILE%\AppData\Local\Programs\Ollama\ollama.exe" set OLLAMA_FOUND=1

if %OLLAMA_FOUND%==0 (
    echo [WARNING] Ollama not found in PATH.
    echo Please make sure Ollama is running. Download: https://ollama.com/download/windows
    echo After installing, restart this script.
    pause
    exit /b 1
)

echo [OK] Ollama found.
echo.
echo [3/4] Pulling DeepSeek-Coder model (3.8 GB - may take a few minutes)...
echo This only needs to happen once!
echo.

:: Try to pull the model
where ollama >nul 2>&1
if %errorlevel%==0 (
    ollama pull deepseek-coder:6.7b
) else (
    "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" pull deepseek-coder:6.7b
)

echo.
echo [4/4] Setup complete!
echo.
echo ==========================================
echo   To start Nightion, run:
echo     start_nightion.bat
echo ==========================================
echo.
pause
