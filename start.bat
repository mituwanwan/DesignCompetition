@echo off
echo ===========================================
echo     智慧养老院管理系统 - 启动脚本
echo ===========================================
echo.

echo [1/4] 检查 Python 环境...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ 错误: 未找到 Python，请先安装 Python 3.8+
    pause
    exit /b 1
)
echo ✅ Python 环境检查通过

echo.
echo [2/4] 安装依赖...
if exist requirements.txt (
    pip install -r requirements.txt
    if %errorlevel% neq 0 (
        echo ⚠️ 依赖安装可能存在问题，但继续尝试...
    )
    echo ✅ 依赖检查完成
) else (
    echo ⚠️ 未找到 requirements.txt，跳过依赖安装
)

echo.
echo [3/4] 初始化数据库...
python setup_db.py

echo.
echo [4/4] 启动应用服务...
echo.
echo ===========================================
echo    服务正在启动，请稍候...
echo    访问地址: http://localhost:5000
echo    默认账号: admin / Admin@123
echo    (按 Ctrl+C 停止服务)
echo ===========================================
echo.

python app.py
pause
