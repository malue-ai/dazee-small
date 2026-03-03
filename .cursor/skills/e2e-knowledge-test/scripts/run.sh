#!/usr/bin/env bash
set -euo pipefail

# 知识库端到端测试运行器
#
# 用法：
#   bash .cursor/skills/e2e-knowledge-test/scripts/run.sh grpc   # zen0 gRPC 接口
#   bash .cursor/skills/e2e-knowledge-test/scripts/run.sh real   # 真实文档全链路
#   bash .cursor/skills/e2e-knowledge-test/scripts/run.sh chat   # 知识库 + Chat
#   bash .cursor/skills/e2e-knowledge-test/scripts/run.sh all    # 全部

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../../../.." && pwd)"
MODE="${1:-all}"

# Python 执行器：优先 conda，回退 venv，再回退系统 python
run_py() {
  if command -v conda &>/dev/null && conda env list 2>/dev/null | grep -q "^zeno "; then
    conda run -n zeno python "$@"
  elif [[ -x "/Users/liuyi/Documents/langchain/liuy/bin/python3" ]]; then
    /Users/liuyi/Documents/langchain/liuy/bin/python3 "$@"
  else
    python3 "$@"
  fi
}

# 健康检查
check_health() {
  echo "检查服务状态..."
  run_py -c "
import asyncio, grpc, sys
sys.path.insert(0, '${PROJECT_ROOT}')
from grpc_server.generated import tool_service_pb2, tool_service_pb2_grpc
async def check():
    ch = grpc.aio.insecure_channel('localhost:50051')
    stub = tool_service_pb2_grpc.HealthStub(ch)
    try:
        resp = await stub.Check(tool_service_pb2.HealthCheckRequest(service=''), timeout=5)
        if resp.status == 1:
            print('  gRPC: OK')
        else:
            print('  gRPC: UNHEALTHY'); sys.exit(1)
    except Exception as e:
        print(f'  gRPC: UNAVAILABLE ({e})'); sys.exit(1)
    await ch.close()
asyncio.run(check())
" || { echo "ERROR: gRPC 服务不可用，请先启动服务"; exit 1; }

  curl -sf http://localhost:8000/health >/dev/null 2>&1 \
    && echo "  HTTP:  OK" \
    || echo "  HTTP:  不可用（Chat 测试将跳过）"
  echo ""
}

run_grpc() {
  echo "========================================"
  echo "  zen0 gRPC 接口测试"
  echo "========================================"
  run_py "${PROJECT_ROOT}/scripts/test_zen0_grpc.py" "$@"
}

run_real() {
  echo "========================================"
  echo "  真实文档全链路测试"
  echo "========================================"
  run_py "${PROJECT_ROOT}/scripts/test_zen0_real.py" "$@"
}

run_chat() {
  echo "========================================"
  echo "  知识库 + Chat 端到端测试"
  echo "========================================"
  run_py "${PROJECT_ROOT}/scripts/test_knowledge_chat.py" "$@"
}

cd "${PROJECT_ROOT}"
check_health

case "${MODE}" in
  grpc)
    run_grpc "${@:2}"
    ;;
  real)
    run_real "${@:2}"
    ;;
  chat)
    run_chat "${@:2}"
    ;;
  all)
    run_grpc "${@:2}" || true
    echo ""
    run_real "${@:2}" || true
    echo ""
    run_chat "${@:2}" || true
    ;;
  *)
    echo "用法: $0 {grpc|real|chat|all}"
    exit 1
    ;;
esac
