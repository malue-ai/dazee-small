#!/usr/bin/env python3
"""
Client Agent 端到端真实验证

验证理念：
- 模拟真实用户自然语言查询，用户不知道背后有什么工具/Skill
- 验证完整调用链：意图识别 → 路由 → Plan → 工具选择 → 执行 → 反思 → React
- 观察 Agent 的推理和决策过程

测试场景（自然语言，不提示具体工具）：
1. "帮我看看现在屏幕上显示的是什么"
2. "把当前桌面保存一张图片到桌面"  
3. "打开飞书，在我的工作群里发一条消息说今天下班后有个小聚会"
"""

import asyncio
import sys
import os
from pathlib import Path
from datetime import datetime
from uuid import uuid4

# 添加项目根目录
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# 加载环境变量
from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(PROJECT_ROOT / "instances" / "client_agent" / ".env")

from logger import get_logger

logger = get_logger("e2e.real_query")


class RealQueryE2ETest:
    """真实用户查询端到端测试"""
    
    def __init__(self):
        self.agent = None
        self.event_manager = None
        self.collected_events = []
        
    async def setup(self):
        """初始化 Agent"""
        from scripts.instance_loader import create_agent_from_instance
        from core.events.manager import create_event_manager
        from core.events.storage import InMemoryEventStorage
        
        print("📦 初始化 client_agent...")
        
        # 创建事件存储和管理器
        storage = InMemoryEventStorage()
        self.event_manager = create_event_manager(storage)
        
        self.agent = await create_agent_from_instance(
            instance_name="client_agent",
            event_manager=self.event_manager,
            skip_mcp_registration=True,
        )
        
        print(f"✅ Agent 就绪: {type(self.agent).__name__}")
        print(f"   模型: {getattr(self.agent, 'model', 'N/A')}")
        
    async def run_query(self, query: str, timeout: int = 120) -> dict:
        """
        执行用户查询（完整端到端流程）
        
        流程：
        1. ChatService.chat() 入口
        2. _run_agent() 消息持久化 + 上下文加载
        3. AgentRouter.route() 意图分析 + 复杂度评估
        4. SimpleAgent.chat() 或 MultiAgentOrchestrator.execute()
        5. _run_rvr_loop() RVR 循环
           - React: LLM 推理
           - Validate: 工具选择验证
           - Reflect: 结果反思
        6. EventBroadcaster 事件推送
        """
        session_id = f"e2e_{uuid4().hex[:8]}"
        message_id = f"msg_{uuid4().hex[:8]}"
        conversation_id = f"conv_{uuid4().hex[:8]}"
        
        print(f"\n{'='*70}")
        print(f"📝 用户查询: {query}")
        print(f"{'='*70}")
        print(f"   Session: {session_id}")
        
        # 初始化 broadcaster
        self.agent.broadcaster.start_message(session_id, message_id, conversation_id)
        
        # 收集事件
        events = []
        tool_calls = []
        content_blocks = []
        thinking_blocks = []
        
        # 执行 Agent
        start_time = datetime.now()
        
        try:
            async for event in self.agent.chat(
                messages=[{"role": "user", "content": query}],
                session_id=session_id,
                message_id=message_id,
                enable_stream=True
            ):
                events.append(event)
                event_type = event.get("type", "unknown")
                
                # 记录关键事件
                if event_type == "intent":
                    intent_data = event.get("content", "{}")
                    print(f"\n🎯 意图识别:")
                    try:
                        import json
                        intent = json.loads(intent_data)
                        print(f"   任务类型: {intent.get('task_type', 'N/A')}")
                        print(f"   复杂度: {intent.get('complexity', 'N/A')}")
                        print(f"   需要 Plan: {intent.get('needs_plan', False)}")
                    except:
                        print(f"   {intent_data}")
                
                # 🔧 content_start 里包含 tool_use 信息
                # 事件格式: {"type": "content_start", "data": {"content_block": {...}}}
                elif event_type == "content_start":
                    data = event.get("data", {})
                    content_block = data.get("content_block", {})
                    block_type = content_block.get("type", "")
                    
                    if block_type == "tool_use":
                        tool_name = content_block.get("name", "unknown")
                        tool_input = content_block.get("input", {})
                        tool_id = content_block.get("id", "")
                        tool_calls.append({"name": tool_name, "input": tool_input, "id": tool_id})
                        print(f"\n🔧 工具调用: {tool_name}")
                        # 显示关键参数
                        if isinstance(tool_input, dict):
                            for k, v in list(tool_input.items())[:3]:
                                v_str = str(v)[:100] + "..." if len(str(v)) > 100 else str(v)
                                print(f"   {k}: {v_str}")
                    
                    elif block_type == "tool_result":
                        result = content_block.get("content", "")
                        is_error = content_block.get("is_error", False)
                        status = "❌" if is_error else "✅"
                        result_str = str(result)[:200] + "..." if len(str(result)) > 200 else str(result)
                        print(f"   {status} 结果: {result_str}")
                    
                    elif block_type == "thinking":
                        thinking = content_block.get("thinking", "")
                        if thinking and len(thinking) > 50:
                            thinking_blocks.append(thinking)
                            print(f"\n💭 思考: {thinking[:100]}...")
                    
                    elif block_type == "text":
                        text = content_block.get("text", "")
                        if text:
                            content_blocks.append(text)
                            print(f"\n📝 回复: {text[:150]}...")
                
                elif event_type == "content_delta":
                    delta = event.get("delta", "")
                    # delta 可能是字符串
                    if isinstance(delta, str) and delta:
                        content_blocks.append(delta)
                    elif isinstance(delta, dict):
                        if delta.get("type") == "thinking":
                            thinking = delta.get("thinking", "")
                            if thinking and len(thinking) > 50:
                                thinking_blocks.append(thinking)
                        elif delta.get("type") == "text":
                            text = delta.get("text", "")
                            if text:
                                content_blocks.append(text)
                
                elif event_type == "message_stop":
                    print(f"\n📍 消息结束")
                    
        except asyncio.TimeoutError:
            print(f"\n⚠️ 执行超时 ({timeout}s)")
        except Exception as e:
            print(f"\n❌ 执行失败: {e}")
            import traceback
            traceback.print_exc()
        
        elapsed = (datetime.now() - start_time).total_seconds()
        
        # 汇总结果
        final_content = "".join(content_blocks)
        
        print(f"\n{'='*70}")
        print(f"📊 执行统计")
        print(f"{'='*70}")
        print(f"   耗时: {elapsed:.2f}s")
        print(f"   事件总数: {len(events)}")
        print(f"   工具调用: {len(tool_calls)}")
        print(f"   思考块: {len(thinking_blocks)}")
        
        if tool_calls:
            print(f"\n🔧 工具调用列表:")
            for i, tc in enumerate(tool_calls, 1):
                print(f"   {i}. {tc['name']}")
        
        if final_content:
            print(f"\n📝 Agent 回复:")
            # 限制输出长度
            if len(final_content) > 500:
                print(f"   {final_content[:500]}...")
            else:
                print(f"   {final_content}")
        
        return {
            "query": query,
            "session_id": session_id,
            "elapsed": elapsed,
            "events": events,
            "tool_calls": tool_calls,
            "thinking_blocks": thinking_blocks,
            "final_content": final_content,
            "success": len(events) > 0
        }


async def main():
    """主测试入口"""
    print("=" * 70)
    print("Client Agent 端到端真实验证")
    print("模拟用户自然语言查询，验证完整调用链")
    print("=" * 70)
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 检查 API Key
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("\n❌ 错误: 未设置 ANTHROPIC_API_KEY 环境变量")
        print("   请设置: export ANTHROPIC_API_KEY=your-key")
        return 1
    
    tester = RealQueryE2ETest()
    await tester.setup()
    
    # 真实用户查询场景（用户不知道背后有什么工具）
    # 更复杂的截屏场景：用户想截取当前屏幕并保存分析
    test_queries = [
        # 复杂场景: 截取屏幕，分析内容，并保存到指定位置
        "截取我当前电脑屏幕的图片，保存到桌面，文件名用当前时间命名，然后告诉我屏幕上主要显示的是什么应用",
    ]
    
    results = []
    
    for query in test_queries:
        result = await tester.run_query(query)
        results.append(result)
        
        # 等待一下再执行下一个
        await asyncio.sleep(2)
    
    # 最终汇总
    print("\n" + "=" * 70)
    print("测试结果汇总")
    print("=" * 70)
    
    for i, r in enumerate(results, 1):
        status = "✅" if r["success"] and r["tool_calls"] else "⚠️"
        print(f"\n{status} 场景 {i}: {r['query'][:50]}...")
        print(f"   工具调用: {len(r['tool_calls'])}")
        print(f"   耗时: {r['elapsed']:.2f}s")
        if r["tool_calls"]:
            print(f"   使用工具: {', '.join([tc['name'] for tc in r['tool_calls']])}")
    
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
