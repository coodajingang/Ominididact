@echo off
chcp 65001 >nul
title Omnididact - Study and Research Engine
setlocal enabledelayedexpansion

REM 切换到当前脚本所在目录
cd /d "%~dp0"

echo ========================================================
echo   Omnididact - 深度研学引擎 (Windows 启动器)
echo ========================================================

REM 1. 如果存在 .env 文件，则逐行读取并加载环境变量
if exist ".env" (
    echo [INFO] 正在加载 .env 配置文件...
    for /f "usebackq tokens=1* delims==" %%A in (".env") do (
        set "KEY=%%A"
        set "VAL=%%B"
        REM 过滤空行与以 # 开头的注释行
        if not "!KEY:~0,1!"=="#" (
            if not "!KEY!"=="" (
                set "!KEY!=!VAL!"
            )
        )
    )
)

REM 2. 设置默认回退值（如果 .env 未配置则使用默认值）
if "%HOST%"=="" set "HOST=0.0.0.0"
if "%PORT%"=="" set "PORT=8000"
if "%RELOAD%"=="" set "RELOAD=false"
if "%NO_PROXY%"=="" set "NO_PROXY=localhost,127.0.0.1,::1"

REM 3. 安全 Token 校验提示
if "%OMNIDIDACT_API_TOKEN%"=="" (
    if "%API_TOKEN%"=="" (
        echo [WARNING] 未检测到 OMNIDIDACT_API_TOKEN，当前为匿名无密模式。
        echo           生产部署强烈建议在 .env 中设置安全令牌。
        echo --------------------------------------------------------
    ) else (
        echo [SECURITY] 安全认证已开启 (API Token 保护)
    )
) else (
    echo [SECURITY] 安全认证已开启 (API Token 保护)
)

echo [INFO] 监听地址: http://%HOST%:%PORT%
echo [INFO] 代码重载: %RELOAD%
echo --------------------------------------------------------

REM 4. 优先使用 uv 运行环境，其次激活虚拟环境，最后使用系统 Python
where uv >nul 2>&1
if not errorlevel 1 (
    echo [INFO] 使用 uv 运行环境启动...
    uv run python proxy.py
    goto :end
)

if exist ".venv\Scripts\activate.bat" (
    echo [INFO] 正在激活虚拟环境: .venv
    call .venv\Scripts\activate.bat
    python proxy.py
    goto :end
)

if exist "venv\Scripts\activate.bat" (
    echo [INFO] 正在激活虚拟环境: venv
    call venv\Scripts\activate.bat
    python proxy.py
    goto :end
)

python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] 未找到 Python 环境，请确保已安装 Python 并已将其添加到 PATH 中！
    pause
    exit /b 1
)

python proxy.py

:end
if errorlevel 1 (
    echo.
    echo [ERROR] 程序异常退出，退出代码: %errorlevel%
)
echo.
pause
