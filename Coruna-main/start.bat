@echo off
REM Coruna C2 Server 启动脚本 (Windows)

echo 🚀 Starting Coruna C2 Server...

REM 检查 Python 环境
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python is not installed
    pause
    exit /b 1
)

REM 进入后端目录
cd /d "%~dp0backend"

REM 创建虚拟环境（如果不存在）
if not exist "venv" (
    echo 📦 Creating virtual environment...
    python -m venv venv
)

REM 激活虚拟环境
call venv\Scripts\activate.bat

REM 安装依赖
echo 📥 Installing dependencies...
pip install -r requirements.txt

REM 创建必要的目录
if not exist "..\data\exfil" mkdir "..\data\exfil"
if not exist "..\data\logs" mkdir "..\data\logs"
if not exist "..\data\payloads" mkdir "..\data\payloads"

REM 启动服务器
echo ✅ Starting server...
uvicorn main:app --host 0.0.0.0 --port 8782 --reload

pause