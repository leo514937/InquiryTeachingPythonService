#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
FRONTEND_DIR="$ROOT_DIR/frontend"
LOG_DIR="$ROOT_DIR/.logs"
BACKEND_LOG="$LOG_DIR/backend.log"
FRONTEND_LOG="$LOG_DIR/frontend.log"
BACKEND_PORT=8010
FRONTEND_PORT=5173
BACKEND_PID=""
FRONTEND_PID=""
STARTUP_OK=0

mkdir -p "$LOG_DIR"

cleanup() {
  if [ "$STARTUP_OK" -eq 1 ]; then
    return 0
  fi

  kill_port "$BACKEND_PORT"
  kill_port "$FRONTEND_PORT"
}

trap cleanup EXIT INT TERM

detect_python() {
  if [ -x "$ROOT_DIR/.venv/Scripts/python.exe" ]; then
    printf '%s\n' "$ROOT_DIR/.venv/Scripts/python.exe"
    return 0
  fi

  if [ -x "$ROOT_DIR/.venv/bin/python" ]; then
    printf '%s\n' "$ROOT_DIR/.venv/bin/python"
    return 0
  fi

  if command -v python >/dev/null 2>&1; then
    command -v python
    return 0
  fi

  if command -v python3 >/dev/null 2>&1; then
    command -v python3
    return 0
  fi

  echo "未找到可用的 Python，请先安装 Python 或创建 .venv" >&2
  exit 1
}

pids_for_port() {
  local port="$1"
  local pids=""

  if command -v lsof >/dev/null 2>&1; then
    pids="$(lsof -ti tcp:"$port" 2>/dev/null || true)"
  fi

  if [ -z "$pids" ] && command -v netstat >/dev/null 2>&1; then
    pids="$(netstat -ano 2>/dev/null | awk -v port=":$port" '
      ($1 ~ /^TCP$/ || $1 ~ /^tcp$/) && index($2, port) { print $NF }
    ' | sort -u || true)"
  fi

  printf '%s\n' "$pids" | sed '/^$/d'
}

kill_port() {
  local port="$1"
  local pids

  pids="$(pids_for_port "$port" || true)"
  if [ -z "$pids" ]; then
    return 0
  fi

  echo "清理端口 $port 上的旧进程..."
  while IFS= read -r pid; do
    [ -z "$pid" ] && continue
    if command -v taskkill >/dev/null 2>&1; then
      taskkill /PID "$pid" /F /T >/dev/null 2>&1 || true
    else
      kill -TERM "$pid" >/dev/null 2>&1 || true
      sleep 1
      kill -KILL "$pid" >/dev/null 2>&1 || true
    fi
  done <<EOF
$pids
EOF
}

start_background() {
  local log_file="$1"
  shift

  : >"$log_file"
  if command -v nohup >/dev/null 2>&1; then
    nohup "$@" >>"$log_file" 2>&1 &
  else
    "$@" >>"$log_file" 2>&1 &
  fi
  printf '%s\n' "$!"
}

echo "初始化项目环境..."
"$(detect_python)" "$ROOT_DIR/bootstrap.py" >/dev/null

kill_port "$BACKEND_PORT"
kill_port "$FRONTEND_PORT"

echo "启动后端..."
BACKEND_PYTHON="$(detect_python)"
BACKEND_PID="$(start_background "$BACKEND_LOG" "$BACKEND_PYTHON" -m uvicorn app.main:app --host 0.0.0.0 --port "$BACKEND_PORT" --reload)"

echo "启动前端..."
if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
  (cd "$FRONTEND_DIR" && npm install)
fi
FRONTEND_PID="$(start_background "$FRONTEND_LOG" bash -lc "cd '$FRONTEND_DIR' && npm run dev")"

sleep 2
STARTUP_OK=1

echo "后端 PID: $BACKEND_PID"
echo "前端 PID: $FRONTEND_PID"
echo "后端日志: $BACKEND_LOG"
echo "前端日志: $FRONTEND_LOG"
echo "访问地址: http://127.0.0.1:$FRONTEND_PORT"
echo "API 地址:   http://127.0.0.1:$BACKEND_PORT"
