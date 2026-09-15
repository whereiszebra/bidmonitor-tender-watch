#!/bin/bash
# 停止 BidMonitor（macOS / Linux / Windows Git Bash / WSL）
# 用法: bash stop.sh              # 停止默认端口 8080 上的实例
#       BIDMONITOR_PORT=8099 bash stop.sh   # 停止其它端口上的实例

PORT="${BIDMONITOR_PORT:-8080}"

if command -v lsof >/dev/null 2>&1; then
  PIDS=$(lsof -nP -iTCP:"$PORT" -sTCP:LISTEN -t 2>/dev/null || true)
  if [ -n "$PIDS" ]; then
    kill $PIDS 2>/dev/null || true
    sleep 1
    echo "⏹️  已停止端口 $PORT 上的实例 (pid=$PIDS)"
  else
    echo "端口 $PORT 上没有运行中的实例"
  fi
  exit 0
fi

# 没有 lsof 时退回进程名匹配（会停掉所有实例）
if command -v pkill >/dev/null 2>&1; then
  if pkill -f "uvicorn app:app" 2>/dev/null; then
    echo "⏹️  已停止（按进程名）"
  else
    echo "未在运行"
  fi
elif command -v taskkill >/dev/null 2>&1; then
  taskkill //F //IM python.exe >/dev/null 2>&1 && echo "⏹️  已尝试停止（Windows）" || echo "请手动结束运行 uvicorn 的进程"
else
  echo "请手动结束运行 uvicorn 的进程"
fi
