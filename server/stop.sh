#!/bin/bash
# BidMonitor 停止脚本

echo "正在停止 BidMonitor 服务..."
pkill -f "uvicorn app:app" 2>/dev/null

if pgrep -f "uvicorn app:app" > /dev/null; then
    echo "❌ 停止失败，尝试强制终止..."
    pkill -9 -f "uvicorn app:app"
fi

echo "⏹️ BidMonitor 已停止"
