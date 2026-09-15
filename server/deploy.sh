#!/bin/bash
# BidMonitor 服务器部署脚本
# 在阿里云服务器上执行此脚本

echo "=========================================="
echo "   BidMonitor 服务器部署脚本"
echo "=========================================="

# 进入项目目录
cd /opt/bidmonitor

# 激活虚拟环境
source venv/bin/activate

# 安装依赖
echo "📦 安装依赖..."
pip install -r server/requirements.txt

# 创建数据目录
mkdir -p data

# 启动服务（前台运行，用于测试）
echo "🚀 启动服务..."
echo "访问地址: http://$(curl -s ifconfig.me):8080"
echo ""
echo "按 Ctrl+C 停止服务"
echo ""

cd server
python app.py
