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

# 停掉旧进程（无 pkill 的环境忽略）
if command -v pkill >/dev/null 2>&1; then
  pkill -f "uvicorn app:app" 2>/dev/null || true
  sleep 2
fi

mkdir -p server/logs server/data
cd server

echo "正在启动 BidMonitor..."
nohup "../$VENV_PY" -m uvicorn app:app --host "$HOST" --port "$PORT" \
  > logs/server.log 2>&1 &
NEWPID=$!
sleep 5

# 健康检查（比 pgrep 更可靠，跨平台一致）
if command -v curl >/dev/null 2>&1; then
  code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 8 "http://127.0.0.1:$PORT/" || true)
  if [ "$code" = "401" ] || [ "$code" = "200" ]; then
    echo "✅ 已启动 (pid=$NEWPID)"
    echo "🌐 访问地址: http://127.0.0.1:$PORT"
    echo "👤 账号密码: ${BIDMONITOR_USER:-CDKJ} / ${BIDMONITOR_PASSWORD:-cdkj}"
    echo "📋 日志: tail -f server/logs/server.log"
    exit 0
  fi
  echo "⚠️  健康检查未通过 (HTTP $code)，日志尾部："
else
  echo "ℹ️  未安装 curl，跳过健康检查。日志尾部："
fi

tail -20 logs/server.log
exit 1
