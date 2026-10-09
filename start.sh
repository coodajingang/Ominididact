#!/usr/bin/env bash
set -e

# ==============================================================================
# Omnididact 生产/运行启动脚本 (支持 nohup 后台运行与生命周期管理)
#
# 使用方式:
#   ./start.sh          # 默认：使用 nohup 在后台运行服务
#   ./start.sh stop     # 停止后台服务
#   ./start.sh restart  # 重启后台服务
#   ./start.sh status   # 查看服务运行状态
#   ./start.sh log      # 实时查看输出日志
#   ./start.sh run      # 在当前终端前台运行
# ==============================================================================

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

PID_FILE="$PROJECT_DIR/app.pid"
LOG_FILE="$PROJECT_DIR/app.log"

ACTION="${1:-start}"

# 1. 停止服务命令
stop_service() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if kill -0 "$PID" 2>/dev/null; then
            echo "[INFO] 正在停止 Omnididact 服务 (PID: $PID)..."
            kill "$PID" 2>/dev/null || true
            for i in {1..10}; do
                if ! kill -0 "$PID" 2>/dev/null; then
                    break
                fi
                sleep 0.5
            done
            if kill -0 "$PID" 2>/dev/null; then
                echo "[WARNING] 服务未在预期时间内退出，强制终止..."
                kill -9 "$PID" 2>/dev/null || true
            fi
            echo "[INFO] 服务已成功停止。"
        else
            echo "[INFO] 进程 (PID: $PID) 已不存在。"
        fi
        rm -f "$PID_FILE"
    else
        echo "[INFO] 未找到运行中的 PID 文件 ($PID_FILE)。"
    fi
}

# 2. 查看状态命令
status_service() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if kill -0 "$PID" 2>/dev/null; then
            echo "[STATUS] Omnididact 正在后台运行 (PID: $PID)"
            echo "         日志文件: $LOG_FILE"
            return 0
        else
            echo "[STATUS] Omnididact 未运行 (残留无效 PID: $PID)"
            rm -f "$PID_FILE"
            return 1
        fi
    else
        echo "[STATUS] Omnididact 未运行。"
        return 1
    fi
}

# 3. 实时查看日志命令
log_service() {
    if [ -f "$LOG_FILE" ]; then
        echo "[INFO] 正在跟踪日志输出 ($LOG_FILE)，按 Ctrl+C 退出..."
        tail -f -n 50 "$LOG_FILE"
    else
        echo "[WARNING] 暂无日志文件 ($LOG_FILE)。"
    fi
    exit 0
}

# 处理子命令
case "$ACTION" in
    stop)
        stop_service
        exit 0
        ;;
    status)
        status_service
        exit 0
        ;;
    log)
        log_service
        ;;
    restart)
        stop_service
        sleep 1
        ACTION="start"
        ;;
    start|run|foreground)
        ;;
    *)
        echo "未知命令: $ACTION"
        echo "用法: $0 [start|stop|restart|status|log|run]"
        exit 1
        ;;
esac

# 检查是否已有运行中的实例
if [ -f "$PID_FILE" ]; then
    EXISTING_PID=$(cat "$PID_FILE")
    if kill -0 "$EXISTING_PID" 2>/dev/null; then
        echo "[ERROR] 服务已在后台运行中 (PID: $EXISTING_PID)！"
        echo "        如需重启请执行: $0 restart"
        echo "        如需停止请执行: $0 stop"
        exit 1
    else
        rm -f "$PID_FILE"
    fi
fi

echo "=========================================================="
echo "  Omnididact - 深度研学引擎"
echo "=========================================================="

# 4. 环境变量默认设置
export HOST="${HOST:-0.0.0.0}"
export PORT="${PORT:-8000}"
export RELOAD="${RELOAD:-false}"
export OMNIDIDACT_ENABLE_DEBUG="${OMNIDIDACT_ENABLE_DEBUG:-false}"
export NO_PROXY="${NO_PROXY:-localhost,127.0.0.1,::1}"

# 5. 加载 .env
if [ -f ".env" ]; then
    echo "[INFO] 加载 .env 配置文件..."
    set -a
    source .env
    set +a
fi

# 6. 安全 Token 校验提示
if [ -z "$OMNIDIDACT_API_TOKEN" ] && [ -z "$API_TOKEN" ]; then
    echo "[WARNING] 未检测到 OMNIDIDACT_API_TOKEN！当前为匿名无密模式。"
    echo "          生产部署强烈建议在 .env 中设置安全令牌。"
    echo "----------------------------------------------------------"
else
    echo "[SECURITY] 安全认证已开启 (API Token 保护)"
fi

echo "[INFO] 监听地址: http://$HOST:$PORT"
echo "[INFO] 代码重载: $RELOAD"
echo "[INFO] 调试模式: $OMNIDIDACT_ENABLE_DEBUG"
echo "----------------------------------------------------------"

# 7. 检测启动命令
RUN_CMD=""
if command -v uv >/dev/null 2>&1; then
    RUN_CMD="uv run python proxy.py"
elif [ -d ".venv" ]; then
    RUN_CMD=".venv/bin/python proxy.py"
elif [ -d "venv" ]; then
    RUN_CMD="venv/bin/python proxy.py"
else
    RUN_CMD="python proxy.py"
fi

# 8. 启动执行
if [ "$ACTION" = "run" ] || [ "$ACTION" = "foreground" ]; then
    echo "[INFO] 前台启动服务 ($RUN_CMD)..."
    exec $RUN_CMD
else
    echo "[INFO] 正在使用 nohup 后台启动服务..."
    nohup $RUN_CMD > "$LOG_FILE" 2>&1 &
    NEW_PID=$!
    echo "$NEW_PID" > "$PID_FILE"

    # 等待 1 秒检查进程是否存活
    sleep 1
    if kill -0 "$NEW_PID" 2>/dev/null; then
        echo "[SUCCESS] 服务已在后台成功启动！"
        echo "          进程 PID : $NEW_PID"
        echo "          日志文件 : $LOG_FILE"
        echo "          访问地址 : http://$HOST:$PORT"
        echo "----------------------------------------------------------"
        echo "  查看实时日志: $0 log  (或 tail -f $LOG_FILE)"
        echo "  停止后台服务: $0 stop"
        echo "  查看运行状态: $0 status"
        echo "=========================================================="
    else
        echo "[ERROR] 服务启动后异常退出，请查看日志:"
        echo "----------------------------------------------------------"
        tail -n 20 "$LOG_FILE"
        rm -f "$PID_FILE"
        exit 1
    fi
fi
