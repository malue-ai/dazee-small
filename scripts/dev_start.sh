#!/bin/bash
#
# 本地前后端开发服务启动脚本
#
# 用法:
#   bash scripts/dev_start.sh              # 启动前后端
#   bash scripts/dev_start.sh --backend    # 仅启动后端
#   bash scripts/dev_start.sh --frontend   # 仅启动前端
#   bash scripts/dev_start.sh --kill       # 仅杀掉旧进程，不启动
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
FRONTEND_DIR="$PROJECT_ROOT/frontend"
# 虚拟环境：优先使用 .cursor 中约定的 liuy 环境，可通过 VENV_DIR 覆盖
VENV_DIR="${VENV_DIR:-/Users/liuyi/Documents/langchain/liuy}"

BACKEND_PORT=8000
FRONTEND_PORT=5174
HEALTH_URL="http://localhost:${BACKEND_PORT}/health"
HEALTH_TIMEOUT=180
HEALTH_INTERVAL=1
BACKEND_LOG=/tmp/zenflux_backend.log

MODE="all"
while [ $# -gt 0 ]; do
  case "$1" in
    --backend)  MODE="backend" ;;
    --frontend) MODE="frontend" ;;
    --kill)     MODE="kill" ;;
    --help|-h)
      head -12 "$0" | tail -10
      exit 0
      ;;
  esac
  shift
done

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
RESET='\033[0m'

step()    { echo -e "\n${CYAN}[$(date +%H:%M:%S)]${RESET} ${BOLD}$1${RESET}"; }
ok()      { echo -e "  ${GREEN}✓${RESET} $1"; }
warn()    { echo -e "  ${YELLOW}⚠${RESET} $1"; }
fail()    { echo -e "  ${RED}✗${RESET} $1"; }
info()    { echo -e "  ${CYAN}→${RESET} $1"; }

kill_by_port() {
  local port=$1
  local label=$2
  local pids
  pids=$(lsof -ti :"$port" 2>/dev/null || true)
  if [ -n "$pids" ]; then
    echo "$pids" | xargs kill -9 2>/dev/null || true
    ok "已终止 ${label}（端口 ${port}, PID: $(echo $pids | tr '\n' ' ')）"
  else
    info "${label} 无旧进程（端口 ${port}）"
  fi
}

cleanup_old_processes() {
  step "清理旧进程"
  kill_by_port "$BACKEND_PORT" "后端 uvicorn"
  kill_by_port "$FRONTEND_PORT" "前端 vite"
  sleep 0.5
}

start_backend() {
  step "启动后端服务"

  if [ ! -d "$VENV_DIR" ] || [ ! -x "$VENV_DIR/bin/python" ]; then
    fail "虚拟环境不存在或不可用: $VENV_DIR"
    echo -e "    请确认 liuy 环境路径，或设置: ${BOLD}export VENV_DIR=/path/to/your/venv${RESET}"
    exit 1
  fi

  info "激活虚拟环境（liuy）: $VENV_DIR"
  source "$VENV_DIR/bin/activate" 2>/dev/null || true

  # 使用与桌面应用相同的数据目录，以便读取前端设置页保存的 config.yaml（含 API Key）
  if [ -z "${ZENFLUX_DATA_DIR:-}" ]; then
    case "$(uname -s)" in
      Darwin)  ZENFLUX_DATA_DIR="${HOME:-}/Library/Application Support/com.zenflux.agent" ;;
      Linux)   ZENFLUX_DATA_DIR="${XDG_DATA_HOME:-${HOME:-}/.local/share}/com.zenflux.agent" ;;
      *)       ZENFLUX_DATA_DIR="${APPDATA:-${HOME:-}/AppData/Roaming}/com.zenflux.agent" ;;
    esac
    export ZENFLUX_DATA_DIR
    info "数据目录: ${ZENFLUX_DATA_DIR}（与桌面应用一致）"
  fi

  info "启动 uvicorn（端口 ${BACKEND_PORT}）..."
  cd "$PROJECT_ROOT"
  uvicorn main:app --host 0.0.0.0 --port "$BACKEND_PORT" --reload \
    > "$BACKEND_LOG" 2>&1 &
  local backend_pid=$!
  info "后端进程 PID: ${backend_pid}"

  info "等待后端就绪（最多 ${HEALTH_TIMEOUT}s，日志出现就绪信号可提前结束）..."
  local elapsed=0
  while [ $elapsed -lt $HEALTH_TIMEOUT ]; do
    if ! kill -0 "$backend_pid" 2>/dev/null; then
      fail "后端进程异常退出"
      echo -e "    查看日志: ${BOLD}cat ${BACKEND_LOG}${RESET}"
      tail -20 "$BACKEND_LOG" 2>/dev/null || true
      exit 1
    fi

    if curl -sf "$HEALTH_URL" > /dev/null 2>&1; then
      ok "后端就绪（${elapsed}s）— ${GREEN}${HEALTH_URL}${RESET}"
      return 0
    fi

    # 根据 uvicorn 启动态日志提前结束：Uvicorn running / Application startup complete
    if [ -f "$BACKEND_LOG" ] && grep -qi -E 'Uvicorn running|Application startup complete' "$BACKEND_LOG" 2>/dev/null; then
      if curl -sf "$HEALTH_URL" > /dev/null 2>&1; then
        ok "后端就绪（${elapsed}s，日志已就绪）— ${GREEN}${HEALTH_URL}${RESET}"
        return 0
      fi
    fi

    sleep "$HEALTH_INTERVAL"
    elapsed=$((elapsed + HEALTH_INTERVAL))
    printf "\r  ${CYAN}→${RESET} 等待中... %ds / %ds" "$elapsed" "$HEALTH_TIMEOUT"
  done

  echo ""
  fail "后端在 ${HEALTH_TIMEOUT}s 内未就绪"
  echo -e "    查看日志: ${BOLD}cat ${BACKEND_LOG}${RESET}"
  tail -20 "$BACKEND_LOG" 2>/dev/null || true
  exit 1
}

start_frontend() {
  step "启动前端服务"

  if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
    info "前端依赖未安装，正在执行 npm install ..."
    cd "$FRONTEND_DIR"
    npm install || { fail "npm install 失败"; exit 1; }
    ok "前端依赖安装完成"
  fi

  info "启动 vite（端口 ${FRONTEND_PORT}）..."
  cd "$FRONTEND_DIR"
  npm run dev > /tmp/zenflux_frontend.log 2>&1 &
  local frontend_pid=$!
  info "前端进程 PID: ${frontend_pid}"

  local elapsed=0
  local fe_timeout=15
  while [ $elapsed -lt $fe_timeout ]; do
    if ! kill -0 "$frontend_pid" 2>/dev/null; then
      fail "前端进程异常退出"
      echo -e "    查看日志: ${BOLD}cat /tmp/zenflux_frontend.log${RESET}"
      tail -20 /tmp/zenflux_frontend.log 2>/dev/null || true
      exit 1
    fi

    if curl -sf "http://localhost:${FRONTEND_PORT}" > /dev/null 2>&1; then
      ok "前端就绪（${elapsed}s）— ${GREEN}http://localhost:${FRONTEND_PORT}${RESET}"
      return 0
    fi

    sleep 1
    elapsed=$((elapsed + 1))
    printf "\r  ${CYAN}→${RESET} 等待中... %ds / %ds" "$elapsed" "$fe_timeout"
  done

  echo ""
  if kill -0 "$frontend_pid" 2>/dev/null; then
    ok "前端已启动（PID: ${frontend_pid}）— ${GREEN}http://localhost:${FRONTEND_PORT}${RESET}"
  else
    fail "前端启动失败"
    echo -e "    查看日志: ${BOLD}cat /tmp/zenflux_frontend.log${RESET}"
    exit 1
  fi
}

print_summary() {
  local be_status fe_status
  if lsof -ti :"$BACKEND_PORT" > /dev/null 2>&1; then
    be_status="${GREEN}运行中${RESET}"
  else
    be_status="${RED}未运行${RESET}"
  fi
  if lsof -ti :"$FRONTEND_PORT" > /dev/null 2>&1; then
    fe_status="${GREEN}运行中${RESET}"
  else
    fe_status="${RED}未运行${RESET}"
  fi

  echo ""
  echo -e "${BOLD}╔══════════════════════════════════════════╗${RESET}"
  echo -e "${BOLD}║         开发服务启动结果                 ║${RESET}"
  echo -e "${BOLD}╠══════════════════════════════════════════╣${RESET}"
  echo -e "${BOLD}║${RESET}  后端  ${be_status}  http://localhost:${BACKEND_PORT}     ${BOLD}║${RESET}"
  echo -e "${BOLD}║${RESET}  前端  ${fe_status}  http://localhost:${FRONTEND_PORT}     ${BOLD}║${RESET}"
  echo -e "${BOLD}╠══════════════════════════════════════════╣${RESET}"
  echo -e "${BOLD}║${RESET}  后端日志: /tmp/zenflux_backend.log      ${BOLD}║${RESET}"
  echo -e "${BOLD}║${RESET}  前端日志: /tmp/zenflux_frontend.log     ${BOLD}║${RESET}"
  echo -e "${BOLD}╚══════════════════════════════════════════╝${RESET}"
  echo ""
}

# ==================== 主流程 ====================

echo -e "\n${BOLD}ZenFlux Agent 开发服务启动${RESET}"
echo -e "项目目录: ${CYAN}${PROJECT_ROOT}${RESET}"

case "$MODE" in
  kill)
    cleanup_old_processes
    ok "旧进程已清理"
    ;;
  backend)
    cleanup_old_processes
    start_backend
    print_summary
    ;;
  frontend)
    cleanup_old_processes
    start_frontend
    print_summary
    ;;
  all)
    cleanup_old_processes
    start_backend
    start_frontend
    print_summary
    ;;
esac
