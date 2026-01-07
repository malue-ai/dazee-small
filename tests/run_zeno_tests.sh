#!/bin/bash
# ============================================================
# ZenO 适配器测试一键运行脚本
# ============================================================

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo ""
echo "🧪 ZenO 适配器测试套件"
echo "================================"
echo ""

# 检查虚拟环境（支持 conda 和 venv）
ENV_NAME=""
if [ ! -z "$CONDA_DEFAULT_ENV" ]; then
    ENV_NAME="conda:$CONDA_DEFAULT_ENV"
elif [ ! -z "$VIRTUAL_ENV" ]; then
    ENV_NAME="venv:$VIRTUAL_ENV"
fi

if [ -z "$ENV_NAME" ]; then
    echo -e "${YELLOW}⚠️  未检测到虚拟环境${NC}"
    echo "请先激活环境："
    echo "  conda activate base"
    echo "  # 或"
    echo "  source venv/bin/activate"
    echo ""
    read -p "是否继续？(y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
else
    echo -e "${GREEN}✅ 环境已激活: $ENV_NAME${NC}"
fi
echo ""

# 设置 PYTHONPATH
export PYTHONPATH="/Users/kens0n/projects/zenflux_agent:$PYTHONPATH"

# 运行测试
echo -e "${BLUE}运行单元测试...${NC}"
echo ""

python << 'EOF'
import sys
sys.path.insert(0, '/Users/kens0n/projects/zenflux_agent')

# 只导入必要的模块
import json
import time

# 直接从文件导入适配器类
exec(open('core/events/adapters/zeno.py').read())

print("="*60)
print("🧪 ZenO 适配器单元测试")
print("="*60)
print()

# 测试 1: message_start
print("测试 1: message_start → message.assistant.start")
adapter = ZenOAdapter(conversation_id="test_conv")
event1 = {
    "type": "message_start",
    "session_id": "sess_123",
    "data": {"message_id": "msg_001"}
}
result1 = adapter.transform(event1)
print(json.dumps(result1, ensure_ascii=False, indent=2))
assert result1["type"] == "message.assistant.start"
print("✅ 通过\n")

# 测试 2: content_delta (thinking)
print("测试 2: content_delta (thinking) → delta.type: thinking")
event2 = {
    "type": "content_delta",
    "session_id": "sess_123",
    "data": {
        "delta": {
            "type": "thinking_delta",
            "thinking": "分析用户需求..."
        }
    }
}
result2 = adapter.transform(event2)
print(json.dumps(result2, ensure_ascii=False, indent=2))
assert result2["delta"]["type"] == "thinking"
print("✅ 通过\n")

# 测试 3: content_delta (text)
print("测试 3: content_delta (text) → delta.type: response")
event3 = {
    "type": "content_delta",
    "session_id": "sess_123",
    "data": {
        "delta": {
            "type": "text_delta",
            "text": "你好！我是 AI 助手。"
        }
    }
}
result3 = adapter.transform(event3)
print(json.dumps(result3, ensure_ascii=False, indent=2))
assert result3["delta"]["type"] == "response"
print("✅ 通过\n")

# 测试 4: message_delta:plan
print("测试 4: message_delta:plan → delta.type: progress")
plan_data = {
    "goal": "生成 PPT",
    "steps": [
        {"index": 0, "action": "分析需求", "status": "completed"},
        {"index": 1, "action": "生成内容", "status": "in_progress"}
    ],
    "current_step": 1,
    "progress": 0.5
}
event4 = {
    "type": "message_delta",
    "session_id": "sess_123",
    "data": {
        "delta": {
            "type": "plan",
            "content": json.dumps(plan_data)
        }
    }
}
result4 = adapter.transform(event4)
print(json.dumps(result4, ensure_ascii=False, indent=2))
assert result4["delta"]["type"] == "progress"
progress = json.loads(result4["delta"]["content"])
assert progress["title"] == "生成 PPT"
assert len(progress["subtasks"]) == 2
print("✅ 通过\n")

# 测试 5: message_stop
print("测试 5: message_stop → message.assistant.done")
adapter._accumulated_content = "完整响应内容"
event5 = {
    "type": "message_stop",
    "session_id": "sess_123",
    "data": {"message_id": "msg_001"}
}
result5 = adapter.transform(event5)
print(json.dumps(result5, ensure_ascii=False, indent=2))
assert result5["type"] == "message.assistant.done"
print("✅ 通过\n")

# 测试 6: error
print("测试 6: error → message.assistant.error")
event6 = {
    "type": "error",
    "session_id": "sess_123",
    "data": {
        "error": {
            "type": "network_error",
            "message": "API 超时"
        }
    }
}
result6 = adapter.transform(event6)
print(json.dumps(result6, ensure_ascii=False, indent=2))
assert result6["type"] == "message.assistant.error"
assert result6["error"]["retryable"] == True
print("✅ 通过\n")

print("="*60)
print("✅ 所有测试通过！")
print("="*60)
print()

EOF

echo ""
echo -e "${GREEN}🎉 测试完成！${NC}"
echo ""
echo "下一步："
echo "  1. 启动模拟服务器: python tests/test_zeno_server.py"
echo "  2. 启动 Agent: uvicorn main:app --reload"
echo "  3. 运行集成测试: python tests/test_zeno_integration.py"
echo ""

