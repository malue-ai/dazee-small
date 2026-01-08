"""
运行 Agent 实例 - 真正的端对端流程

用法：
    python scripts/run_agent.py --instance test_agent --query "你的问题"
    python scripts/run_agent.py --instance test_agent  # 交互模式
"""

import asyncio
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from logger import get_logger
logger = get_logger("run_agent")


async def run_agent(instance_name: str, query: str = None):
    """运行 Agent"""
    from scripts.instance_loader import create_agent_from_instance
    from services.mcp_client import clear_mcp_client_cache
    
    print(f"\n🚀 启动实例: {instance_name}")
    print("=" * 60)
    
    try:
        # 创建 Agent
        agent = await create_agent_from_instance(instance_name)
        
        print(f"✅ Agent 就绪")
        print(f"   模型: {agent.model}")
        print("=" * 60)
        
        # 单次查询或交互模式
        if query:
            await run_query(agent, query)
        else:
            await interactive_mode(agent)
    
    finally:
        # 🆕 清理 MCP 客户端连接，避免异步上下文错误
        try:
            await clear_mcp_client_cache()
        except Exception as e:
            logger.debug(f"清理 MCP 缓存时出错: {e}")


async def run_query(agent, query: str):
    """执行单次查询"""
    print(f"\n📝 用户输入: {query}")
    print("-" * 40)
    
    messages = [{"role": "user", "content": query}]
    
    print("\n🤖 Agent 响应:\n")
    
    # 流式输出
    async for event in agent.chat(messages=messages, session_id="test_session"):
        event_type = event.get("type", "unknown")
        
        if event_type == "text_delta":
            # 文本输出
            print(event.get("content", ""), end="", flush=True)
        
        elif event_type == "tool_use":
            # 工具调用
            tool_name = event.get("tool_name", "unknown")
            tool_input = event.get("input", {})
            print(f"\n\n🔧 调用工具: {tool_name}")
            print(f"   参数: {tool_input}")
        
        elif event_type == "tool_result":
            # 工具结果
            result = event.get("result", "")
            print(f"\n📊 工具结果:")
            print("-" * 40)
            if len(str(result)) > 500:
                print(str(result)[:500] + "...")
            else:
                print(result)
            print("-" * 40)
        
        elif event_type == "thinking":
            # 思考过程
            pass  # 可选显示
        
        elif event_type == "error":
            print(f"\n❌ 错误: {event.get('message', 'unknown')}")
        
        elif event_type == "done":
            print("\n")
    
    print("\n" + "=" * 60)


async def interactive_mode(agent):
    """交互模式"""
    print("\n💬 进入交互模式 (输入 'quit' 退出)")
    print("-" * 40)
    
    while True:
        try:
            query = input("\n你: ").strip()
            
            if query.lower() in ["quit", "exit", "q"]:
                print("👋 再见!")
                break
            
            if not query:
                continue
            
            await run_query(agent, query)
            
        except KeyboardInterrupt:
            print("\n👋 再见!")
            break
        except Exception as e:
            print(f"\n❌ 错误: {e}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="运行 Agent 实例")
    parser.add_argument("--instance", "-i", default="test_agent", help="实例名称")
    parser.add_argument("--query", "-q", type=str, help="用户查询（不提供则进入交互模式）")
    
    args = parser.parse_args()
    
    asyncio.run(run_agent(args.instance, args.query))
