#!/bin/bash

# Coruna C2 Server 启动脚本

echo "🚀 Starting Coruna C2 Server..."

# 检查 Python 环境
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed"
    exit 1
fi

# 进入后端目录
cd "$(dirname "$0")/backend"

# 创建虚拟环境（如果不存在）
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi

# 激活虚拟环境
source venv/bin/activate

# 安装依赖
echo "📥 Installing dependencies..."
pip install -r requirements.txt

# 创建必要的目录
mkdir -p ../data/exfil
mkdir -p ../data/logs
mkdir -p ../data/payloads

# 启动服务器
echo "✅ Starting server..."
uvicorn main:app --host 0.0.0.0 --port 8782 --reload