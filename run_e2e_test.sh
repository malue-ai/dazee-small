#!/bin/bash
# E2E 测试运行脚本
# 隔离路径避免冲突

set -e

# 切换到脚本所在目录
cd "$(dirname "$0")"

# 激活虚拟环境
source /Users/liuyi/Documents/langchain/liuy/bin/activate

# 加载环境变量
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

# 清理 Python 路径，确保项目目录优先
export PYTHONPATH="$(pwd):$PYTHONPATH"

# 解析参数
TEST_TYPE="${1:-smoke}"

case "$TEST_TYPE" in
    smoke)
        echo "运行冒烟测试（不需要 API 和数据库）..."
        python tests/test_e2e_agent_pipeline.py smoke
        ;;
    quick)
        echo "运行快速场景测试（需要 API Key）..."
        python -m pytest tests/test_e2e_agent_pipeline.py -k "simple_qa or code_generation" -v -s --rootdir="$(pwd)" -p no:cacheprovider
        ;;
    full)
        echo "运行完整测试（需要数据库和 API Key）..."
        python -m pytest tests/test_e2e_agent_pipeline.py -v -s --rootdir="$(pwd)" -p no:cacheprovider
        ;;
    *)
        echo "未知参数: $TEST_TYPE"
        echo "可用参数: smoke, quick, full"
        exit 1
        ;;
esac
