#!/bin/bash
# Mem0 个性化机制验证测试 - 快速运行脚本

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}======================================================================${NC}"
echo -e "${BLUE}Mem0 个性化机制验证测试${NC}"
echo -e "${BLUE}======================================================================${NC}"
echo ""

# 检查环境变量
echo -e "${YELLOW}检查环境变量...${NC}"

check_env_var() {
    if [ -z "${!1}" ]; then
        echo -e "${RED}❌ 缺少环境变量: $1${NC}"
        return 1
    else
        echo -e "${GREEN}✅ $1: ${!1:0:10}...${NC}"
        return 0
    fi
}

all_ok=true

check_env_var "OPENAI_API_KEY" || all_ok=false
check_env_var "ANTHROPIC_API_KEY" || all_ok=false

# 检查向量存储配置
VECTOR_STORE=${VECTOR_STORE_PROVIDER:-qdrant}
echo -e "${BLUE}向量存储提供商: $VECTOR_STORE${NC}"

if [ "$VECTOR_STORE" = "tencent" ]; then
    check_env_var "TENCENT_VDB_URL" || all_ok=false
    check_env_var "TENCENT_VDB_API_KEY" || all_ok=false
else
    check_env_var "QDRANT_URL" || all_ok=false
fi

if [ "$all_ok" = false ]; then
    echo ""
    echo -e "${RED}环境配置不完整，请检查 .env 文件${NC}"
    echo -e "${YELLOW}参考 env.example.claude-openai 或 env.example.claude-ollama${NC}"
    exit 1
fi

echo ""
echo -e "${GREEN}环境检查通过！${NC}"
echo ""

# 进入项目根目录
cd "$(dirname "$0")/.."

# 运行测试
echo -e "${BLUE}开始运行测试...${NC}"
echo ""

python tests/test_mem0_personalization_e2e.py

# 检查测试结果
if [ $? -eq 0 ]; then
    echo ""
    echo -e "${GREEN}======================================================================${NC}"
    echo -e "${GREEN}测试完成！${NC}"
    echo -e "${GREEN}======================================================================${NC}"
    echo ""
    echo -e "${BLUE}查看详细报告:${NC}"
    echo -e "  cat MEM0_PERSONALIZATION_VALIDATION_REPORT.md"
    echo ""
else
    echo ""
    echo -e "${RED}======================================================================${NC}"
    echo -e "${RED}测试失败，请检查日志输出${NC}"
    echo -e "${RED}======================================================================${NC}"
    exit 1
fi
