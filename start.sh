#!/usr/bin/env bash
# DevManager 本地开发环境启动脚本（无 Docker）
# 依赖：系统已安装 PostgreSQL 16 + Redis 7（systemd 服务）

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PIDS_DIR="$ROOT/.pids"
LOGS_DIR="$ROOT/.logs"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

info()    { echo -e "${CYAN}▶${RESET} $*"; }
success() { echo -e "${GREEN}✓${RESET} $*"; }
warn()    { echo -e "${YELLOW}⚠${RESET} $*"; }
die()     { echo -e "${RED}✗ $*${RESET}" >&2; exit 1; }

command -v uv  >/dev/null 2>&1 || die "未找到 uv（curl -LsSf https://astral.sh/uv/install.sh | sh）"
command -v npm >/dev/null 2>&1 || die "未找到 npm，请先安装 Node.js"

mkdir -p "$PIDS_DIR" "$LOGS_DIR"

# ── 环境变量 ──────────────────────────────────────────────────────────────────
[[ -f "$ROOT/.env" ]] && { set -a; source "$ROOT/.env"; set +a; }

export DATABASE_URL="${DATABASE_URL:-postgresql+asyncpg://postgres:sinopharm%401089@localhost:5432/agent_devops}"
export REDIS_URL="${REDIS_URL:-redis://localhost:6379}"
export API_SECRET_KEY="${API_SECRET_KEY:-change-me-in-production}"

# ── 1. 检查 PostgreSQL ────────────────────────────────────────────────────────
info "检查 PostgreSQL…"
if pg_isready -h localhost -p 5432 -q 2>/dev/null; then
  success "PostgreSQL 已就绪（localhost:5432）"
else
  info "尝试启动 PostgreSQL…"
  sudo service postgresql start 2>/dev/null || sudo pg_ctlcluster 16 main start 2>/dev/null \
    || die "PostgreSQL 启动失败，请手动执行：sudo service postgresql start"
  sleep 2
  pg_isready -h localhost -p 5432 -q || die "PostgreSQL 仍未就绪"
  success "PostgreSQL 已启动"
fi

# ── 2. 检查 Redis ─────────────────────────────────────────────────────────────
info "检查 Redis…"
if redis-cli -p 6379 ping 2>/dev/null | grep -q PONG; then
  success "Redis 已就绪（localhost:6379）"
else
  info "尝试启动 Redis…"
  sudo service redis-server start 2>/dev/null \
    || die "Redis 启动失败，请手动执行：sudo service redis-server start"
  sleep 1
  redis-cli -p 6379 ping | grep -q PONG || die "Redis 仍未就绪"
  success "Redis 已启动"
fi

# ── 3. 数据库迁移 ──────────────────────────────────────────────────────────────
info "运行数据库迁移…"
MIGRATION="$ROOT/migrations/postgres/001_initial_schema.sql"
if [[ -f "$MIGRATION" ]]; then
  sudo -u postgres psql -d agent_devops -f "$MIGRATION" >/dev/null 2>&1 \
    && success "迁移完成" || warn "迁移已应用或部分失败（跳过）"
else
  warn "未找到迁移文件，跳过"
fi

# ── 4. API 网关 ────────────────────────────────────────────────────────────────
info "启动 API 网关（端口 8010）…"
cd "$ROOT/apps/api-gateway"
uv run uvicorn api_gateway.main:app \
  --host 0.0.0.0 --port 8010 --reload \
  >"$LOGS_DIR/api-gateway.log" 2>&1 &
echo $! >"$PIDS_DIR/api-gateway.pid"
success "API 网关 PID=$(cat "$PIDS_DIR/api-gateway.pid")"

# ── 5. ARQ Worker ─────────────────────────────────────────────────────────────
info "启动 ARQ Worker…"
cd "$ROOT/apps/worker"
uv run arq worker.main.WorkerSettings \
  >"$LOGS_DIR/worker.log" 2>&1 &
echo $! >"$PIDS_DIR/worker.pid"
success "Worker PID=$(cat "$PIDS_DIR/worker.pid")"

# ── 6. 前端开发服务器 ─────────────────────────────────────────────────────────
info "启动前端（端口 8173）…"
cd "$ROOT/apps/web"
[[ ! -d node_modules ]] && npm install --silent
# 直接调用 vite 二进制，避免 npm run dev 留下孤儿进程导致 PID 追踪失效
node node_modules/.bin/vite >"$LOGS_DIR/web.log" 2>&1 &
echo $! >"$PIDS_DIR/web.pid"
success "前端 PID=$(cat "$PIDS_DIR/web.pid")"

# ── 就绪提示 ──────────────────────────────────────────────────────────────────
echo
echo -e "${BOLD}══════════════════════════════════════${RESET}"
echo -e "${GREEN}${BOLD}  DevManager 已启动${RESET}"
echo -e "${BOLD}══════════════════════════════════════${RESET}"
echo -e "  前端        ${CYAN}http://localhost:8173${RESET}"
echo -e "  API 网关    ${CYAN}http://localhost:8010${RESET}"
echo -e "  API 文档    ${CYAN}http://localhost:8010/docs${RESET}"
echo -e "  日志目录    ${CYAN}$LOGS_DIR/${RESET}"
echo -e "${BOLD}══════════════════════════════════════${RESET}"
echo
echo -e "查看日志：${YELLOW}tail -f .logs/api-gateway.log${RESET}"
echo -e "停止服务：${YELLOW}./stop.sh${RESET}"
