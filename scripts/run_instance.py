#!/usr/bin/env python3
"""
实例运行器 - 交互式运行智能体实例

用法：
    python scripts/run_instance.py --instance test_agent
    python scripts/run_instance.py --list
    python scripts/run_instance.py  # 交互式选择
"""

import os
import sys
import asyncio
from pathlib import Path

# 添加项目根目录到路径
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from logger import get_logger

logger = get_logger("run_instance")


async def cleanup_agent(agent):
    """
    清理 Agent 资源（显式关闭 MCP 客户端）
    
    这样可以避免 asyncio 事件循环退出时的 RuntimeError:
    "athrow(): asynchronous generator is already running"
    """
    if hasattr(agent, '_mcp_clients') and agent._mcp_clients:
        for client in agent._mcp_clients:
            try:
                await client.disconnect()
            except Exception:
                pass  # 忽略关闭时的错误


async def interactive_chat(agent, instance_name: str):
    """
    交互式对话循环
    
    Args:
        agent: Agent 实例
        instance_name: 实例名称
    """
    print(f"\n{'='*60}")
    print(f"🤖 {instance_name} 已启动")
    print(f"{'='*60}")
    print("输入 'exit' 或 'quit' 退出")
    print("输入 'clear' 清空对话历史")
    print("输入 'info' 查看实例信息")
    print(f"{'='*60}\n")
    
    messages = []
    
    while True:
        try:
            # 获取用户输入
            user_input = input("\n👤 你: ").strip()
            
            if not user_input:
                continue
            
            # 命令处理
            if user_input.lower() in ("exit", "quit", "q"):
                print("\n👋 再见！")
                break
            
            if user_input.lower() == "clear":
                messages = []
                print("🗑️ 对话历史已清空")
                continue
            
            if user_input.lower() == "info":
                print(f"\n📋 实例: {instance_name}")
                print(f"   模型: {getattr(agent, 'model', 'unknown')}")
                print(f"   最大轮数: {getattr(agent, 'max_turns', 'unknown')}")
                print(f"   消息数: {len(messages)}")
                continue
            
            # 添加用户消息
            messages.append({
                "role": "user",
                "content": user_input
            })
            
            # 调用 Agent
            print("\n🤖 助手: ", end="", flush=True)
            
            response_text = ""
            
            # 流式输出（使用 chat 方法）
            async for event in agent.chat(messages=messages):
                event_type = event.get("type", "")
                
                if event_type == "message_delta":
                    delta = event.get("delta", {})
                    text = delta.get("text", "")
                    if text:
                        print(text, end="", flush=True)
                        response_text += text
                
                elif event_type == "tool_use":
                    tool_name = event.get("tool_name", "unknown")
                    print(f"\n   🔧 调用工具: {tool_name}", flush=True)
                
                elif event_type == "tool_result":
                    status = event.get("status", "unknown")
                    print(f"   ✓ 工具完成: {status}", flush=True)
                
                elif event_type == "error":
                    error = event.get("error", "unknown")
                    print(f"\n   ❌ 错误: {error}", flush=True)
            
            print()  # 换行
            
            # 添加助手消息到历史
            if response_text:
                messages.append({
                    "role": "assistant",
                    "content": response_text
                })
            
        except KeyboardInterrupt:
            print("\n\n👋 已中断，再见！")
            break
        except Exception as e:
            print(f"\n❌ 错误: {str(e)}")
            logger.error(f"对话错误: {str(e)}", exc_info=True)


async def main():
    """主函数"""
    import argparse
    from utils.instance_loader import (
        list_instances,
        print_available_instances,
        create_agent_from_instance,
        load_instance_config
    )
    
    parser = argparse.ArgumentParser(
        description="运行智能体实例",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  python scripts/run_instance.py --list              # 列出所有实例
  python scripts/run_instance.py --instance test_agent  # 运行指定实例
  python scripts/run_instance.py                     # 交互式选择
        """
    )
    parser.add_argument("--list", "-l", action="store_true", help="列出所有可用实例")
    parser.add_argument("--instance", "-i", type=str, help="要运行的实例名称")
    parser.add_argument("--skip-mcp", action="store_true", help="跳过 MCP 工具注册")
    parser.add_argument("--skip-skills", action="store_true", help="跳过 Claude Skills 注册")
    parser.add_argument("--single", "-s", type=str, help="单次执行（非交互模式）")
    parser.add_argument("--files", "-f", type=str, nargs="+", help="附加文件 URL（格式: name:url）")
    
    args = parser.parse_args()
    
    # 列出实例
    if args.list:
        print_available_instances()
        return
    
    # 确定要运行的实例
    instance_name = args.instance
    
    if not instance_name:
        # 交互式选择
        instances = list_instances()
        
        if not instances:
            print("❌ 没有可用的实例")
            print("   请在 instances/ 目录下创建实例")
            return
        
        print("\n📦 可用实例:")
        for i, name in enumerate(instances, 1):
            try:
                config = load_instance_config(name)
                print(f"   {i}. {name}: {config.description or '(无描述)'}")
            except:
                print(f"   {i}. {name}")
        
        print()
        choice = input("请选择实例编号（或输入名称）: ").strip()
        
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(instances):
                instance_name = instances[idx]
            else:
                print("❌ 无效的选择")
                return
        else:
            instance_name = choice
    
    # 检查实例是否存在
    if instance_name not in list_instances():
        print(f"❌ 实例不存在: {instance_name}")
        print_available_instances()
        return
    
    # 加载实例
    print(f"\n⏳ 正在加载实例: {instance_name}...")
    
    try:
        agent = await create_agent_from_instance(
            instance_name,
            skip_mcp_registration=args.skip_mcp,
            skip_skills_registration=args.skip_skills
        )
    except Exception as e:
        print(f"❌ 加载失败: {str(e)}")
        logger.error(f"加载实例失败: {str(e)}", exc_info=True)
        return
    
    # 单次执行模式
    if args.single:
        print(f"\n👤 输入: {args.single}")
        
        # 构建消息内容
        content = args.single
        
        # 处理文件参数 - 把文件信息追加到消息内容中
        if args.files:
            file_info_lines = ["\n\n---\n**用户上传的文件：**"]
            for f in args.files:
                if ":" in f:
                    name, url = f.split(":", 1)
                else:
                    name = f.split("/")[-1]
                    url = f
                file_info_lines.append(f"- 文件名: {name}")
                file_info_lines.append(f"  URL: {url}")
                print(f"📎 附件: {name}")
            
            content += "\n".join(file_info_lines)
        
        user_message = {"role": "user", "content": content}
        
        print("\n🤖 输出: ", end="", flush=True)
        
        messages = [user_message]
        
        try:
            async for event in agent.chat(messages=messages):
                event_type = event.get("type", "")
                if event_type == "message_delta":
                    delta = event.get("delta", {})
                    text = delta.get("text", "")
                    if text:
                        print(text, end="", flush=True)
            
            print()
        finally:
            # 🆕 显式关闭 MCP 客户端，避免 asyncio 退出时的错误
            await cleanup_agent(agent)
        return
    
    # 交互模式
    try:
        await interactive_chat(agent, instance_name)
    finally:
        # 🆕 显式关闭 MCP 客户端
        await cleanup_agent(agent)


if __name__ == "__main__":
    asyncio.run(main())
