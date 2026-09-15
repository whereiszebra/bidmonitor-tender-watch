#!/bin/bash
# 停止 BidMonitor（macOS / Linux / Windows Git Bash / WSL）

if command -v pkill >/dev/null 2>&1; then
  if pkill -f "uvicorn app:app" 2>/dev/null; then
    echo "⏹️  已停止"
  else
    echo "未在运行"
  fi
elif command -v taskkill >/dev/null 2>&1; then
  # Windows：按窗口标题匹配不到，用 wmic 找命令行含 uvicorn 的进程
  if taskkill //F //FI "IMAGENAME eq python.exe" //FI "WINDOWTITLE eq *uvicorn*" >/dev/null 2>&1; then
    echo "⏹️  已尝试停止（Windows）"
  else
    echo "Windows 下请手动结束运行 uvicorn 的 python 进程"
  fi
else
  echo "请手动结束运行 uvicorn 的进程"
fi
