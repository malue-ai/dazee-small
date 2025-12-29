#!/bin/bash

# E2B 完整测试脚本
# 
# 功能：
# 1. 检查虚拟环境
# 2. 安装依赖
# 3. 配置 E2B API Key
# 4. 运行完整测试
#
# 运行方式：
#   bash scripts/test_e2b_complete.sh

set -e  # 遇到错误立即退出

echo "======================================================================"
echo "🚀 E2B 完整测试流程"
echo "======================================================================"

# 项目根目录
PROJECT_DIR="/Users/liuyi/Documents/langchain/CoT_agent/mvp/zenflux_agent"
cd "$PROJECT_DIR"

# 1. 激活虚拟环境
echo ""
echo "1️⃣ 激活虚拟环境..."
VENV_PATH="/Users/liuyi/Documents/langchain/liuy/bin/activate"

if [ -f "$VENV_PATH" ]; then
    source "$VENV_PATH"
    echo "✅ 虚拟环境已激活: liuy"
    echo "   Python 版本: $(python --version)"
else
    echo "❌ 虚拟环境不存在: $VENV_PATH"
    exit 1
fi

# 2. 检查依赖
echo ""
echo "2️⃣ 检查依赖..."

# 检查 E2B SDK
if python -c "import e2b_code_interpreter" 2>/dev/null; then
    echo "✅ E2B SDK 已安装"
else
    echo "❌ E2B SDK 未安装"
    echo "   正在安装..."
    pip install e2b e2b-code-interpreter -q
    echo "✅ E2B SDK 安装完成"
fi

# 检查其他依赖
if python -c "import anthropic" 2>/dev/null; then
    echo "✅ Anthropic SDK 已安装"
else
    echo "❌ 缺少依赖，正在安装..."
    pip install -r requirements.txt -q
    echo "✅ 依赖安装完成"
fi

# 3. 检查 E2B API Key
echo ""
echo "3️⃣ 检查 E2B API Key..."

# 加载 .env 文件
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

if [ -z "$E2B_API_KEY" ]; then
    echo "❌ E2B_API_KEY 未配置"
    echo ""
    echo "请选择配置方式:"
    echo "  1. 手动创建 .env 文件并添加: E2B_API_KEY=your_key"
    echo "  2. 运行配置向导: python scripts/configure_e2b.py"
    echo ""
    echo "获取 API Key: https://e2b.dev/dashboard"
    exit 1
else
    echo "✅ E2B_API_KEY 已配置: ${E2B_API_KEY:0:10}..."
fi

# 4. 运行测试
echo ""
echo "4️⃣ 运行 E2B 端到端真实测试..."
echo ""
echo "⚠️  注意：这是真实测试，会调用真实的 E2B API"
echo "⚠️  预计时间：2-5 分钟"
echo ""

read -p "是否继续? (y/n): " -n 1 -r
echo ""

if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo ""
    python tests/test_e2b_e2e_real.py
else
    echo "❌ 测试已取消"
    exit 0
fi

echo ""
echo "======================================================================"
echo "🎉 E2B 测试完成！"
echo "======================================================================"

