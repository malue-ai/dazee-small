#!/bin/bash
# 运行端到端测试脚本
#
# 使用方法：
#   # 本地测试模式（默认，使用本地 Redis）
#   bash tests/e2e_message_session/run_tests.sh
#
#   # 部署发布模式（使用 AWS MemoryDB）
#   TEST_MODE=production bash tests/e2e_message_session/run_tests.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/../.."

# 激活虚拟环境（如果存在）
if [ -f "/Users/liuyi/Documents/langchain/liuy/bin/activate" ]; then
    source /Users/liuyi/Documents/langchain/liuy/bin/activate
fi

# 设置部署环境（默认本地测试环境）
DEPLOYMENT_ENV=${DEPLOYMENT_ENV:-local}
export DEPLOYMENT_ENV

echo "============================================================"
echo "🚀 开始运行端到端测试"
echo "============================================================"
echo "部署环境: $DEPLOYMENT_ENV"
echo ""

# 如果是本地环境，检查并启动 Redis
if [ "$DEPLOYMENT_ENV" = "local" ] || [ "$DEPLOYMENT_ENV" = "development" ]; then
    echo "📋 检查本地 Redis..."
    if ! redis-cli ping &> /dev/null 2>&1; then
        echo "⚠️  本地 Redis 未运行，尝试启动..."
        bash "$SCRIPT_DIR/start_local_redis.sh" || {
            echo "❌ 无法启动本地 Redis，请手动启动："
            echo "   brew services start redis"
            echo "   或: docker run -d -p 6379:6379 redis:7-alpine"
            exit 1
        }
    else
        echo "✅ 本地 Redis 已运行"
    fi
    echo ""
fi

# 运行测试
echo "============================================================"
echo "1️⃣ 连通性测试"
echo "============================================================"
python tests/e2e_message_session/test_connectivity.py || {
    echo "❌ 连通性测试失败"
    exit 1
}

echo ""
echo "============================================================"
echo "2️⃣ Schema IO 测试"
echo "============================================================"
python tests/e2e_message_session/test_schema_io.py || {
    echo "❌ Schema IO 测试失败"
    exit 1
}

echo ""
echo "============================================================"
echo "3️⃣ 端到端流程测试"
echo "============================================================"
python tests/e2e_message_session/test_e2e_flow.py || {
    echo "❌ 端到端流程测试失败"
    exit 1
}

echo ""
echo "============================================================"
echo "🎉 所有测试通过！"
echo "============================================================"
