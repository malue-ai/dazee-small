#!/usr/bin/env python3
"""
端到端 Agent 管道验证脚本

验证流程：用户 Query → Intent → Tool Selection → RVR Loop → 结果返回

使用方式：
    cd /Users/liuyi/Documents/langchain/CoT_agent/mvp/zenflux_agent
    source /Users/liuyi/Documents/langchain/liuy/bin/activate
    python scripts/e2e_pipeline_verify.py
"""

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.agent import AgentFactory, AgentPresets
from core.events import create_event_manager, get_memory_storage


async def verify_pipeline_with_schema(user_query: str, use_prompt_driven: bool = False):
    """
    端到端验证 Agent 管道（V4.2 架构：Schema 驱动）
    
    Args:
        user_query: 真实用户查询
        use_prompt_driven: 是否使用 Prompt 驱动的 Schema 生成
    """
    print("\n" + "=" * 70)
    print("🚀 ZenFlux Agent V4.2 端到端管道验证")
    print("   架构特性：Schema 驱动 + Prompt 驱动（可选）")
    print("=" * 70)
    
    # ===== 1. 初始化 Agent（使用 AgentFactory） =====
    print("\n📦 阶段 1: 初始化 Agent")
    print("-" * 50)
    
    storage = get_memory_storage()
    event_manager = create_event_manager(storage)
    
    if use_prompt_driven:
        # 🆕 方式 1: Prompt 驱动（System Prompt → LLM 生成 Schema）
        print("   🎯 使用 Prompt 驱动方式")
        system_prompt = """
你是一个通用智能助手，能够：
- 回答各类知识问题
- 执行网页搜索获取最新信息
- 进行简单的文件操作

请始终保持友好、专业的态度。
"""
        agent = await AgentFactory.from_prompt(
            system_prompt=system_prompt,
            event_manager=event_manager,
            workspace_dir="./workspace"
        )
        print(f"   ✓ Schema 生成: LLM 自动生成")
    else:
        # 🆕 方式 2: 使用预设 Schema
        print("   🎯 使用预设 Schema")
        schema = AgentPresets.simple_qa()
        agent = AgentFactory.from_schema(
            schema=schema,
            system_prompt=None,  # 使用默认 System Prompt
            event_manager=event_manager,
            workspace_dir="./workspace"
        )
        print(f"   ✓ Schema 来源: AgentPresets.simple_qa()")
    
    print(f"   ✓ Model: {agent.model}")
    print(f"   ✓ Schema: {agent.schema.name}")
    print(f"   ✓ Schema.tools: {agent.schema.tools[:3] if agent.schema.tools else 'None'}...")
    print(f"   ✓ IntentAnalyzer: {'启用' if agent.intent_analyzer else '未启用'}")
    print(f"   ✓ ToolSelector: {'启用' if agent.tool_selector else '未启用'}")
    print(f"   ✓ PlanManager: {'启用' if agent.plan_todo_tool else '未启用'}")
    
    # ===== 2. 准备消息 =====
    print("\n📝 阶段 2: 用户输入")
    print("-" * 50)
    print(f"   Query: \"{user_query}\"")
    
    messages = [{"role": "user", "content": user_query}]
    session_id = f"e2e_verify_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    # ===== 3. 执行 Agent =====
    print("\n⚡ 阶段 3: Agent 执行")
    print("-" * 50)
    
    events_collected = {
        "intent": None,
        "thinking_blocks": [],
        "text_blocks": [],
        "tool_uses": [],
        "tool_results": [],
        "message_stop": None
    }
    
    try:
        async for event in agent.chat(
            messages=messages,
            session_id=session_id,
            enable_stream=True
        ):
            event_type = event.get("type")
            data = event.get("data", {})
            
            # 收集意图识别
            if event_type == "message_delta":
                delta = data.get("delta", {})
                if delta.get("type") == "intent":
                    events_collected["intent"] = json.loads(delta.get("content", "{}"))
                    intent = events_collected["intent"]
                    print(f"\n   🎯 意图识别:")
                    print(f"      - task_type: {intent.get('task_type')}")
                    print(f"      - complexity: {intent.get('complexity')}")
                    print(f"      - needs_plan: {intent.get('needs_plan')}")
            
            # 收集 content blocks
            elif event_type == "content_start":
                content_block = data.get("content_block", {})
                block_type = content_block.get("type")
                
                if block_type == "thinking":
                    events_collected["thinking_blocks"].append({"index": data.get("index")})
                    print(f"\n   🧠 Thinking Block #{data.get('index')} 开始...")
                
                elif block_type == "text":
                    events_collected["text_blocks"].append({"index": data.get("index")})
                    print(f"\n   📝 Text Block #{data.get('index')} 开始...")
                
                elif block_type == "tool_use":
                    tool_info = {
                        "id": content_block.get("id"),
                        "name": content_block.get("name"),
                        "input": content_block.get("input")
                    }
                    events_collected["tool_uses"].append(tool_info)
                    print(f"\n   🔧 Tool Use: {tool_info['name']}")
                    print(f"      Input: {json.dumps(tool_info['input'], ensure_ascii=False)[:200]}...")
                
                elif block_type == "tool_result":
                    result_info = {
                        "tool_use_id": content_block.get("tool_use_id"),
                        "is_error": content_block.get("is_error", False),
                        "content_preview": str(content_block.get("content", ""))[:200]
                    }
                    events_collected["tool_results"].append(result_info)
                    status = "❌ 失败" if result_info["is_error"] else "✅ 成功"
                    print(f"   📋 Tool Result: {status}")
                    print(f"      Preview: {result_info['content_preview']}...")
            
            # 收集文本内容
            elif event_type == "content_delta":
                delta = data.get("delta", {})
                if delta.get("type") == "text_delta":
                    text = delta.get("text", "")
                    if events_collected["text_blocks"]:
                        if "content" not in events_collected["text_blocks"][-1]:
                            events_collected["text_blocks"][-1]["content"] = ""
                        events_collected["text_blocks"][-1]["content"] += text
            
            # 收集完成事件
            elif event_type == "message_stop":
                events_collected["message_stop"] = data
                print(f"\n   ✅ message_stop 事件收到")
        
    except Exception as e:
        print(f"\n   ❌ 执行异常: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # ===== 4. 结果汇总 =====
    print("\n" + "=" * 70)
    print("📊 阶段 4: 执行结果汇总")
    print("=" * 70)
    
    print(f"\n   Intent: {events_collected['intent']}")
    print(f"   Thinking Blocks: {len(events_collected['thinking_blocks'])}")
    print(f"   Text Blocks: {len(events_collected['text_blocks'])}")
    print(f"   Tool Uses: {len(events_collected['tool_uses'])}")
    print(f"   Tool Results: {len(events_collected['tool_results'])}")
    
    # 显示工具调用链
    if events_collected["tool_uses"]:
        print("\n   🔗 工具调用链:")
        for i, tool in enumerate(events_collected["tool_uses"], 1):
            print(f"      {i}. {tool['name']}")
    
    # 显示最终文本响应
    if events_collected["text_blocks"]:
        final_text = events_collected["text_blocks"][-1].get("content", "")
        if final_text:
            print("\n   📄 Agent 最终响应:")
            print("   " + "-" * 50)
            # 只显示前 500 字符
            preview = final_text[:500] + ("..." if len(final_text) > 500 else "")
            for line in preview.split("\n"):
                print(f"   {line}")
    
    # 显示 Usage 统计
    usage = agent.usage_stats
    print("\n   📈 Token 统计:")
    print(f"      - Input: {usage.get('total_input_tokens', 0)}")
    print(f"      - Output: {usage.get('total_output_tokens', 0)}")
    print(f"      - Cache Read: {usage.get('total_cache_read_tokens', 0)}")
    
    print("\n" + "=" * 70)
    print("✅ 端到端验证完成")
    print("=" * 70 + "\n")


async def main():
    """主入口"""
    # 真实用户场景：简单的自然语言交互
    test_queries = [
        # 简单问答（不需要工具）
        "你好，请用一句话介绍你自己",
    ]
    
    print("\n" + "🔥" * 35)
    print("   ZenFlux Agent V4.2 - 端到端管道验证")
    print("   真实用户场景 | Schema 驱动 | 全管道追踪")
    print("🔥" * 35)
    
    for query in test_queries:
        # 使用 Schema 驱动方式验证
        await verify_pipeline_with_schema(query, use_prompt_driven=False)


if __name__ == "__main__":
    asyncio.run(main())

