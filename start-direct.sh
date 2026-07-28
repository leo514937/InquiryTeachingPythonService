#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_DIR="$ROOT_DIR/frontend"
LOG_DIR="$ROOT_DIR/.logs"

BACKEND_PORT="${BACKEND_PORT:-8010}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"
PUBLIC_IP="${PUBLIC_IP:-152.136.39.252}"

BACKEND_LOG="$LOG_DIR/backend.log"
FRONTEND_LOG="$LOG_DIR/frontend.log"

if [[ $EUID -ne 0 ]]; then
    echo "请使用 sudo 运行：sudo $0"
    exit 1
fi

stop_listener() {
    local port="$1"
    local pids

    pids="$(lsof -t -iTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)"

    if [[ -z "$pids" ]]; then
        echo "端口 $port 当前未被占用"
        return
    fi

    echo "停止端口 $port 上的进程：$pids"
    kill $pids 2>/dev/null || true

    for _ in {1..10}; do
        if ! lsof -t -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
            echo "端口 $port 已释放"
            return
        fi
        sleep 1
    done

    pids="$(lsof -t -iTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)"
    if [[ -n "$pids" ]]; then
        echo "进程未正常退出，强制停止：$pids"
        kill -9 $pids 2>/dev/null || true
    fi
}

wait_http() {
    local name="$1"
    local url="$2"

    for _ in {1..30}; do
        if curl -fsS --connect-timeout 2 "$url" >/dev/null 2>&1; then
            echo "$name 已就绪：$url"
            return 0
        fi
        sleep 1
    done

    echo "$name 启动失败或未及时就绪：$url"
    return 1
}

echo "检查项目环境……"

if [[ ! -x "$ROOT_DIR/.venv/bin/python" ]]; then
    echo "未找到 Python 虚拟环境：$ROOT_DIR/.venv"
    exit 1
fi

if [[ ! -f "$FRONTEND_DIR/package.json" ]]; then
    echo "未找到前端 package.json"
    exit 1
fi

if [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
    echo "前端依赖未安装，请先执行："
    echo "cd $FRONTEND_DIR && npm install"
    exit 1
fi

if ! command -v npm >/dev/null 2>&1; then
    echo "未找到 npm，请先安装 Node.js 并确保 npm 在 PATH 中"
    exit 1
fi

install -d "$LOG_DIR"

# 防止之前的 systemd 服务自动重新占用 8010
systemctl disable --now inquiry-teaching 2>/dev/null || true

stop_listener "$BACKEND_PORT"
stop_listener "$FRONTEND_PORT"

echo "启动后端……"

(
    cd "$ROOT_DIR"
    nohup "$ROOT_DIR/.venv/bin/python" \
        -m uvicorn app.main:app \
        --host 0.0.0.0 \
        --port "$BACKEND_PORT" \
        > "$BACKEND_LOG" 2>&1 < /dev/null &
)

echo "启动前端……"

(
    cd "$FRONTEND_DIR"
    nohup env "VITE_API_BASE=http://$PUBLIC_IP:$BACKEND_PORT" \
        npm run dev -- \
        --host 0.0.0.0 \
        --port "$FRONTEND_PORT" \
        --strictPort \
        > "$FRONTEND_LOG" 2>&1 < /dev/null &
)

backend_ok=false
frontend_ok=false

if wait_http "后端" "http://127.0.0.1:$BACKEND_PORT/health"; then
    backend_ok=true
fi

if wait_http "前端" "http://127.0.0.1:$FRONTEND_PORT/"; then
    frontend_ok=true
fi

echo
echo "后端日志：$BACKEND_LOG"
echo "前端日志：$FRONTEND_LOG"

if [[ "$backend_ok" == true ]]; then
    echo "后端地址：http://$PUBLIC_IP:$BACKEND_PORT"
    echo "接口文档：http://$PUBLIC_IP:$BACKEND_PORT/docs"
else
    echo "后端启动失败，请查看：tail -n 100 $BACKEND_LOG"
fi

if [[ "$frontend_ok" == true ]]; then
    echo "前端地址：http://$PUBLIC_IP:$FRONTEND_PORT"
else
    echo "前端启动失败，请查看：tail -n 100 $FRONTEND_LOG"
fi

if [[ "$backend_ok" != true || "$frontend_ok" != true ]]; then
    exit 1
fi
