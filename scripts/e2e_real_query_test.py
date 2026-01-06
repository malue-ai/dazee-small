"""
ZenFlux Agent V4.2.1 - 真实 Query 端到端测试

这是真正的端到端测试：
1. 用户真实 Query → SimpleAgent.chat()
2. LLM 真实处理（Claude）
3. 工具真实执行（E2B Sandbox）
4. 追踪整个管道，打印每阶段日志
5. 返回真实结果

运行前请确保设置环境变量：
- ANTHROPIC_API_KEY: Claude API Key
- E2B_API_KEY: E2B Sandbox API Key（可选，不设置则使用本地执行）
"""

import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 加载 .env 文件
from dotenv import load_dotenv
env_path = project_root / ".env"
if env_path.exists():
    load_dotenv(env_path)
    print(f"✅ 已加载 .env 文件: {env_path}")

from logger import get_logger

logger = get_logger("e2e_real_query")


async def run_real_e2e_test():
    """运行真实的端到端测试"""
    
    print("=" * 70)
    print("🚀 ZenFlux Agent V4.2.1 - 真实 Query 端到端测试")
    print("=" * 70)
    print(f"\n⏰ 开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 检查 API Keys
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    e2b_key = os.getenv("E2B_API_KEY")
    
    print(f"\n⚙️  环境检查:")
    print(f"   ANTHROPIC_API_KEY: {'✅ 已配置' if anthropic_key else '❌ 未配置'}")
    print(f"   E2B_API_KEY: {'✅ 已配置' if e2b_key else '⚠️ 未配置（将使用本地 bash）'}")
    
    if not anthropic_key:
        print("\n❌ 错误: 必须设置 ANTHROPIC_API_KEY 才能运行真实测试!")
        print("   请运行: export ANTHROPIC_API_KEY='your-key'")
        return
    
    # 导入真实组件
    from core.agent import SimpleAgent
    from core.events import create_event_manager, get_memory_storage
    
    # 创建真实的事件管理器和 Agent
    print("\n" + "─" * 70)
    print("📦 初始化 Agent...")
    print("─" * 70)
    
    storage = get_memory_storage()
    event_manager = create_event_manager(storage)
    
    agent = SimpleAgent(
        event_manager=event_manager,
        workspace_dir="./workspace",
        model="claude-sonnet-4-5-20250929"  # 使用真实模型
    )
    
    print(f"   ✅ SimpleAgent 创建成功")
    print(f"   📊 模型: {agent.model}")
    print(f"   📍 追踪: {'启用' if agent.enable_tracing else '禁用'}")
    
    # 定义真实用户 Query（真实用户语言）
    test_queries = [
        {
            "name": "简单计算",
            "query": "帮我计算 123 + 456",
        },
        {
            "name": "简单 Python 脚本",
            "query": "写个 Python 脚本计算 1 到 100 的和",
        },
        {
            "name": "待办事项应用",
            "query": "做个待办事项应用",
        },
    ]
    
    # 运行测试（复杂任务 - 需要 plan）
    test = test_queries[2]  # 待办事项应用
    
    print("\n" + "=" * 70)
    print(f"📋 测试场景: {test['name']}")
    print("=" * 70)
    print(f"\n📝 用户 Query:")
    print(f"   \"{test['query']}\"")
    print("\n" + "─" * 70)
    print("🔄 开始处理... (真实 LLM 调用)")
    print("─" * 70)
    
    # 构建消息
    messages = [
        {"role": "user", "content": test["query"]}
    ]
    
    session_id = f"e2e_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    # 收集所有事件
    events = []
    final_response = ""
    tool_calls = []
    
    try:
        # 真实调用 Agent
        async for event in agent.chat(
            messages=messages,
            session_id=session_id,
            enable_stream=True
        ):
            events.append(event)
            event_type = event.get("type", "unknown")
            
            # 实时打印关键事件
            if event_type == "message_delta":
                delta = event.get("data", {}).get("delta", {})
                delta_type = delta.get("type", "")
                
                if delta_type == "intent":
                    import json
                    intent_data = json.loads(delta.get("content", "{}"))
                    print(f"\n🎯 意图识别结果:")
                    print(f"   任务类型: {intent_data.get('task_type')}")
                    print(f"   复杂度: {intent_data.get('complexity')}")
                    print(f"   需要计划: {intent_data.get('needs_plan')}")
                
                elif delta_type == "text_delta":
                    # 累积文本响应
                    text = delta.get("text", "")
                    final_response += text
                    # 实时输出
                    print(text, end="", flush=True)
            
            elif event_type == "content_start":
                content_block = event.get("data", {}).get("content_block", {})
                block_type = content_block.get("type", "")
                
                if block_type == "tool_use":
                    tool_name = content_block.get("name", "")
                    tool_input = content_block.get("input", {})
                    print(f"\n\n🔧 工具调用: {tool_name}")
                    print(f"   输入: {str(tool_input)[:200]}...")
                    tool_calls.append({
                        "name": tool_name,
                        "input": tool_input
                    })
                
                elif block_type == "tool_result":
                    result_content = content_block.get("content", "")
                    print(f"\n📤 工具结果:")
                    print(f"   {str(result_content)[:300]}...")
            
            elif event_type == "content_delta":
                delta = event.get("data", {}).get("delta", {})
                if delta.get("type") == "thinking_delta":
                    # 可以选择是否打印 thinking
                    pass
        
        print("\n")
        print("─" * 70)
        print("✅ Agent 处理完成")
        print("─" * 70)
        
        # 获取追踪报告
        trace_report = agent.get_trace_report()
        
        if trace_report:
            print("\n📊 E2E Pipeline 追踪报告:")
            print(f"   Session: {trace_report.get('session_id')}")
            print(f"   用户 Query: {trace_report.get('user_query', '')[:50]}...")
            
            stages = trace_report.get("stages", {})
            stage_order = trace_report.get("stage_order", [])
            
            print(f"\n📍 执行路径 ({len(stage_order)} 个阶段):")
            for i, stage_name in enumerate(stage_order, 1):
                stage = stages.get(stage_name, {})
                status = stage.get("status", "unknown")
                duration = stage.get("duration_ms", 0)
                status_icon = "✅" if status == "completed" else "❌" if status == "failed" else "⏭️"
                print(f"   {i}. {status_icon} {stage_name}: {duration:.1f}ms")
            
            stats = trace_report.get("stats", {})
            print(f"\n📈 统计:")
            print(f"   总耗时: {stats.get('total_duration_ms', 0):.1f}ms")
            print(f"   工具调用: {len(tool_calls)} 次")
        
        # 打印最终响应
        print("\n" + "=" * 70)
        print("📄 最终响应:")
        print("=" * 70)
        print(final_response if final_response else "(无文本响应)")
        
        # 打印 Usage 统计
        usage = agent.usage_stats
        print("\n📊 Token 使用:")
        print(f"   输入: {usage.get('total_input_tokens', 0)}")
        print(f"   输出: {usage.get('total_output_tokens', 0)}")
        
    except Exception as e:
        print(f"\n❌ 执行失败: {str(e)}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 70)
    print(f"⏰ 完成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(run_real_e2e_test())

