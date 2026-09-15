#!/bin/bash
# BidMonitor 启动脚本（macOS / Linux / Windows Git Bash / WSL 均可）
# 用法: bash start.sh
#       bash stop.sh  停止

set -e
cd "$(dirname "$0")"

# 定位虚拟环境解释器：类 Unix 在 bin/，Windows 在 Scripts/
if [ -x ".venv/bin/python" ]; then
  VENV_PY=".venv/bin/python"
elif [ -x ".venv/Scripts/python.exe" ]; then
  VENV_PY=".venv/Scripts/python.exe"
else
  echo "❌ 未找到虚拟环境，请先执行： bash setup.sh"
  exit 1
fi

# 首次运行自动从模板生成配置
if [ ! -f server/server_config.json ] && [ -f server/server_config.example.json ]; then
  cp server/server_config.example.json server/server_config.json
  echo "ℹ️  已从模板生成 server/server_config.json"
fi

HOST="${BIDMONITOR_HOST:-127.0.0.1}"
PORT="${BIDMONITOR_PORT:-8080}"

# 只停掉「占用本端口」的旧实例。
# 注意：不能用 pkill -f "uvicorn app:app" —— 那会误杀跑在其它端口上的实例
# （多环境/多端口并存时特别危险）。
if command -v lsof >/dev/null 2>&1; then
  OLD_PIDS=$(lsof -nP -iTCP:"$PORT" -sTCP:LISTEN -t 2>/dev/null || true)
  if [ -n "$OLD_PIDS" ]; then
    echo "ℹ️  端口 $PORT 已被占用，先停止旧实例: $OLD_PIDS"
    kill $OLD_PIDS 2>/dev/null || true
    sleep 2
  fi
fi

mkdir -p server/logs server/data
cd server

echo "正在启动 BidMonitor..."
nohup "../$VENV_PY" -m uvicorn app:app --host "$HOST" --port "$PORT" \
  > logs/server.log 2>&1 &
NEWPID=$!

# 轮询健康检查：解析成百毫秒级，固定 sleep 容易误判失败
ok=""
for _ in $(seq 1 20); do
  sleep 1
  if command -v curl >/dev/null 2>&1; then
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "http://127.0.0.1:$PORT/" || true)
    case "$code" in 200|401) ok="yes"; break;; esac
  else
    # 没有 curl 时退化为检查进程是否还在
    if kill -0 "$NEWPID" 2>/dev/null; then ok="yes"; break; fi
  fi
  kill -0 "$NEWPID" 2>/dev/null || break   # 进程已退出，不必再等
done

if [ -n "$ok" ]; then
  echo "✅ 已启动 (pid=$NEWPID)"
  echo "🌐 访问地址: http://127.0.0.1:$PORT"
  echo "👤 账号密码: ${BIDMONITOR_USER:-CDKJ} / ${BIDMONITOR_PASSWORD:-cdkj}"
  echo "📋 日志: tail -f server/logs/server.log"
  exit 0
fi

echo "❌ 启动失败，日志尾部："
tail -20 logs/server.log
exit 1
