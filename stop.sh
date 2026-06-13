#!/usr/bin/env bash
# DevManager 本地开发环境停止脚本

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PIDS_DIR="$ROOT/.pids"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; RESET='\033[0m'

info()    { echo -e "${CYAN}▶${RESET} $*"; }
success() { echo -e "${GREEN}✓${RESET} $*"; }
warn()    { echo -e "${YELLOW}⚠${RESET} $*"; }

stop_pid() {
  local name="$1"
  local pidfile="$PIDS_DIR/${name}.pid"

  if [[ ! -f "$pidfile" ]]; then
    warn "$name：未找到 PID 文件，跳过"
    return
  fi

  local pid
  pid=$(cat "$pidfile")

  if kill -0 "$pid" 2>/dev/null; then
    pkill -P "$pid" 2>/dev/null || true   # 先杀子进程
    kill "$pid" 2>/dev/null
    for _ in $(seq 1 10); do
      kill -0 "$pid" 2>/dev/null || break
      sleep 0.5
    done
    if kill -0 "$pid" 2>/dev/null; then
      kill -9 "$pid" 2>/dev/null
      warn "$name（PID=$pid）强制终止"
    else
      success "$name（PID=$pid）已停止"
    fi
  else
    warn "$name（PID=$pid）进程不存在，可能已退出"
  fi

  rm -f "$pidfile"
}

info "停止前端开发服务器…"
stop_pid "web"

info "停止 ARQ Worker…"
stop_pid "worker"

info "停止 API 网关…"
stop_pid "api-gateway"

echo
success "所有服务已停止（PostgreSQL / Redis 系统服务保持运行）"
