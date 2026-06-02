#!/bin/bash

echo "==========================================="
echo "    智慧养老院管理系统 - 启动脚本"
echo "==========================================="
echo ""

echo "[1/4] 检查 Python 环境..."
if ! command -v python3 &> /dev/null && ! command -v python &> /dev/null; then
    echo "❌ 错误: 未找到 Python，请先安装 Python 3.8+"
    exit 1
fi

PYTHON_CMD="python3"
if ! command -v python3 &> /dev/null; then
    PYTHON_CMD="python"
fi
$PYTHON_CMD --version
echo "✅ Python 环境检查通过"

echo ""
echo "[2/4] 安装依赖..."
if [ -f requirements.txt ]; then
    $PYTHON_CMD -m pip install -r requirements.txt
    if [ $? -ne 0 ]; then
        echo "⚠️ 依赖安装可能存在问题，但继续尝试..."
    fi
    echo "✅ 依赖检查完成"
else
    echo "⚠️ 未找到 requirements.txt，跳过依赖安装"
fi

echo ""
echo "[3/4] 初始化数据库..."
$PYTHON_CMD setup_db.py

echo ""
echo "[4/4] 启动应用服务..."
echo ""
echo "==========================================="
echo "   服务正在启动，请稍候..."
echo "   访问地址: http://localhost:5000"
echo "   默认账号: admin / Admin@123"
echo "   (按 Ctrl+C 停止服务)"
echo "==========================================="
echo ""

$PYTHON_CMD app.py
