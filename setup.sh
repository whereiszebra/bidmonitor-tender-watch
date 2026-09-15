#!/bin/bash
# BidMonitor 一键安装（macOS / Linux / Windows Git Bash / WSL 均可）
# 作用：建虚拟环境 → 装依赖 → 生成配置文件

set -e
cd "$(dirname "$0")"

echo "==> 检查 Python"
PYBIN=""
for c in python3 python; do
  if command -v "$c" >/dev/null 2>&1; then
    ver=$("$c" -c 'import sys;print("%d.%d"%sys.version_info[:2])' 2>/dev/null || echo "0.0")
    major=${ver%%.*}; minor=${ver##*.}
    if [ "$major" -eq 3 ] && [ "$minor" -ge 9 ]; then PYBIN="$c"; break; fi
  fi
done

if [ -z "$PYBIN" ]; then
  echo "❌ 未找到 Python 3.9+，请先安装：https://www.python.org/downloads/"
  exit 1
fi
echo "    使用 $PYBIN ($($PYBIN -V 2>&1))"

echo "==> 创建虚拟环境 .venv"
[ -d .venv ] || "$PYBIN" -m venv .venv

# Windows 虚拟环境的解释器在 Scripts/，类 Unix 在 bin/
if [ -x ".venv/bin/python" ]; then VENV_PY=".venv/bin/python"
elif [ -x ".venv/Scripts/python.exe" ]; then VENV_PY=".venv/Scripts/python.exe"
else echo "❌ 虚拟环境创建失败"; exit 1; fi
echo "    venv 解释器: $VENV_PY"

echo "==> 安装依赖（首次约 1-2 分钟）"
"$VENV_PY" -m pip install --upgrade pip -q
"$VENV_PY" -m pip install -r server/requirements.txt

echo "==> 准备配置文件"
mkdir -p server/data server/logs
if [ -f server/server_config.json ]; then
  echo "    已存在 server/server_config.json，跳过（不会覆盖你的配置）"
else
  cp server/server_config.example.json server/server_config.json
  echo "    已从模板生成 server/server_config.json（关键词/站点已预置，通知渠道需自行填写）"
fi

echo
echo "✅ 安装完成。启动："
echo "     bash start.sh"
echo "   然后访问 http://127.0.0.1:8080"
