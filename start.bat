@echo off
chcp 65001 >nul
title Omnididact - Study and Research Engine

REM 切换到当前脚本所在目录
cd /d "%~dp0"

echo ========================================================
echo   Omnididact - 深度研学引擎 (Windows 启动器)
echo   端口: 8001   热重载: false
echo ========================================================

REM 配置环境变量 (使用双引号避免行末空格隐形污染，并绕过 Windows 系统代理)
set "HOST=127.0.0.1"
set "PORT=8001"
set "RELOAD=false"
set "NO_PROXY=localhost,127.0.0.1,::1"

REM 如果本地存在 Python 虚拟环境，则优先激活
if exist "venv\Scripts\activate.bat" (
    echo [INFO] 正在激活虚拟环境: venv
    call venv\Scripts\activate.bat
    goto :check_python
)
if exist ".venv\Scripts\activate.bat" (
    echo [INFO] 正在激活虚拟环境: .venv
    call .venv\Scripts\activate.bat
    goto :check_python
)

:check_python
REM 检查 Python 环境
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] 未找到 Python 环境，请确保已安装 Python 并已将其添加到系统环境变量 PATH 中！
    echo.
    pause
    exit /b 1
)

echo [INFO] 正在启动服务: http://%HOST%:%PORT% (RELOAD=%RELOAD%)...
echo [INFO] 按 Ctrl+C 可停止运行。
echo.

python proxy.py

if errorlevel 1 (
    echo.
    echo [ERROR] 程序异常退出，退出代码: %errorlevel%
)

echo.
pause
