#!/bin/bash

# E2B API Key 设置脚本
# 
# 使用方式：
#   bash scripts/set_e2b_key.sh e2b_your_actual_key_here

if [ -z "$1" ]; then
    echo "❌ 请提供 E2B API Key"
    echo ""
    echo "使用方式:"
    echo "  bash scripts/set_e2b_key.sh e2b_your_actual_key_here"
    echo ""
    echo "获取 API Key: https://e2b.dev/dashboard"
    exit 1
fi

E2B_KEY="$1"

# 项目根目录
PROJECT_DIR="/Users/liuyi/Documents/langchain/CoT_agent/mvp/zenflux_agent"
ENV_FILE="$PROJECT_DIR/.env"

echo "======================================================================"
echo "🔑 设置 E2B API Key"
echo "======================================================================"

# 创建或更新 .env 文件
if [ -f "$ENV_FILE" ]; then
    # 检查是否已有 E2B_API_KEY
    if grep -q "E2B_API_KEY=" "$ENV_FILE"; then
        # 更新现有 key
        if [[ "$OSTYPE" == "darwin"* ]]; then
            # macOS
            sed -i '' "s/E2B_API_KEY=.*/E2B_API_KEY=$E2B_KEY/" "$ENV_FILE"
        else
            # Linux
            sed -i "s/E2B_API_KEY=.*/E2B_API_KEY=$E2B_KEY/" "$ENV_FILE"
        fi
        echo "✅ 已更新 $ENV_FILE 中的 E2B_API_KEY"
    else
        # 追加新 key
        echo "" >> "$ENV_FILE"
        echo "# E2B Configuration" >> "$ENV_FILE"
        echo "E2B_API_KEY=$E2B_KEY" >> "$ENV_FILE"
        echo "✅ 已添加 E2B_API_KEY 到 $ENV_FILE"
    fi
else
    # 创建新文件
    cat > "$ENV_FILE" << EOF
# Zenflux Agent 环境变量配置

# E2B Configuration
E2B_API_KEY=$E2B_KEY

# Anthropic API Key
# ANTHROPIC_API_KEY=sk-ant-***

# 其他 API Keys
# EXA_API_KEY=***
# SLIDESPEAK_API_KEY=***
# RAGIE_API_KEY=***
EOF
    echo "✅ 已创建 $ENV_FILE"
fi

echo ""
echo "验证配置:"
source "$ENV_FILE"
echo "  E2B_API_KEY: ${E2B_API_KEY:0:10}..."

echo ""
echo "======================================================================"
echo "✅ 配置完成！"
echo "======================================================================"
echo ""
echo "下一步："
echo "  bash scripts/test_e2b_complete.sh"
echo ""

