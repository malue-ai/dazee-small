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


async def run_agent(instance_name: str, query: str = None, force_refresh: bool = False):
    """运行 Agent"""
    from utils.instance_loader import create_agent_from_instance
    from infra.pools import get_mcp_pool
    
    print(f"\n🚀 启动实例: {instance_name}")
    if force_refresh:
        print("   模式: 强制刷新缓存")
    print("=" * 60)
    
    try:
        # 创建 Agent（🆕 V4.6: 支持缓存）
        agent = await create_agent_from_instance(instance_name, force_refresh=force_refresh)
        
        print(f"✅ Agent 就绪")
        print(f"   模型: {agent.model}")
        print("=" * 60)
        
        # 单次查询或交互模式
        if query:
            await run_query(agent, query)
        else:
            await interactive_mode(agent)
    
    finally:
        # 🆕 清理 MCP 客户端连接，使用统一的 MCPPool
        try:
            mcp_pool = get_mcp_pool()
            await mcp_pool.cleanup()
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
    
    parser = argparse.ArgumentParser(
        description="运行 Agent 实例",
        epilog="""示例:
  # 正常启动（使用缓存）
  python scripts/run_agent.py --instance test_agent
  
  # 强制刷新缓存
  python scripts/run_agent.py --instance test_agent --force-refresh
  
  # 清除缓存
  python scripts/run_agent.py --instance test_agent --clear-cache
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--instance", "-i", default="test_agent", help="实例名称")
    parser.add_argument("--query", "-q", type=str, help="用户查询（不提供则进入交互模式）")
    parser.add_argument("--force-refresh", action="store_true", 
                       help="强制刷新缓存，重新生成 Schema 和推断工具能力")
    parser.add_argument("--clear-cache", action="store_true",
                       help="清除实例缓存后退出")
    
    args = parser.parse_args()
    
    # 🆕 V4.6: 清除缓存命令
    if args.clear_cache:
        from pathlib import Path
        from utils.cache_utils import clear_cache
        
        instances_dir = Path(__file__).parent.parent / "instances"
        cache_dir = instances_dir / args.instance / ".cache"
        
        if cache_dir.exists():
            clear_cache(cache_dir)
            print(f"✅ 已清除实例 {args.instance} 的缓存: {cache_dir}")
        else:
            print(f"⚠️ 缓存目录不存在: {cache_dir}")
        return
    
    asyncio.run(run_agent(args.instance, args.query, args.force_refresh))
