#!/usr/bin/env python
"""
gRPC 对话上下文记忆测试脚本

测试 gRPC 服务器的 conversation_id 是否能正确记住上下文

使用方法：
    python scripts/test_grpc_conversation_memory.py [agent_id] [host]
    
示例：
    python scripts/test_grpc_conversation_memory.py dazee_agent localhost:50051
"""

import asyncio
import sys
import os
import json

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from grpc_server.client import ZenfluxGRPCClient


async def test_conversation_memory(agent_id: str = "dazee_agent", host: str = "localhost:50051"):
    """
    测试对话上下文记忆功能
    
    流程：
    1. 发送第一条消息"我叫小明"，获取 conversation_id
    2. 使用相同的 conversation_id 发送第二条消息"我叫什么名字"
    3. 验证 Agent 是否记住了"小明"
    
    Args:
        agent_id: Agent 实例 ID
        host: gRPC 服务器地址
    """
    print("=" * 70)
    print("🧪 测试 gRPC 对话上下文记忆功能")
    print(f"🤖 Agent: {agent_id}")
    print(f"🌐 服务器: {host}")
    print("=" * 70)
    
    conversation_id = None
    
    try:
        async with ZenfluxGRPCClient(host) as client:
            # ========================================
            # 第一轮对话：告诉 Agent 名字
            # ========================================
            print("\n" + "─" * 70)
            print("📤 第一轮：发送 '我叫小明'")
            print("─" * 70)
            
            event_count = 0
            assistant_content = ""
            
            async for event in client.chat_stream(
                message="我叫小明",
                user_id="test_user_memory",
                conversation_id=None,  # 第一轮不传，让系统创建新对话
                agent_id=agent_id
            ):
                event_count += 1
                event_type = event.get("type", "unknown")
                
                # 从 message.assistant.start 获取 conversation_id
                if event_type == "message.assistant.start":
                    # conversation_id 可能在 event 顶层或 data 中
                    conv_id = event.get("conversation_id")
                    if not conv_id and "data" in event:
                        conv_id = event["data"].get("conversation_id")
                    if conv_id:
                        conversation_id = conv_id
                        print(f"   🔑 获取到 conversation_id: {conversation_id}")
                
                # 累积助手回复内容
                elif event_type == "message.assistant.delta":
                    delta = event.get("delta", {})
                    if delta.get("type") == "text":
                        assistant_content += delta.get("content", "")
                
                elif event_type == "message.assistant.streaming":
                    assistant_content += event.get("content", "")
                
                elif event_type == "message.assistant.done":
                    # 从 done 事件获取完整内容
                    data = event.get("data", {})
                    if data.get("content"):
                        assistant_content = data.get("content", assistant_content)
                    print(f"\n📥 助手回复（{event_count} 个事件）:")
                    # 截取显示
                    preview = assistant_content[:200] + "..." if len(assistant_content) > 200 else assistant_content
                    print(f"   {preview}")
            
            if not conversation_id:
                print("\n❌ 错误：未能获取 conversation_id")
                return False
            
            print(f"\n✅ 第一轮完成，conversation_id: {conversation_id}")
            
            # ========================================
            # 第二轮对话：询问名字
            # ========================================
            print("\n" + "─" * 70)
            print(f"📤 第二轮：发送 '我叫什么名字'（使用 conversation_id: {conversation_id[:20]}...）")
            print("─" * 70)
            
            event_count = 0
            assistant_content = ""
            
            async for event in client.chat_stream(
                message="我叫什么名字",
                user_id="test_user_memory",
                conversation_id=conversation_id,  # 传入第一轮获取的 conversation_id
                agent_id=agent_id
            ):
                event_count += 1
                event_type = event.get("type", "unknown")
                
                # 累积助手回复内容
                if event_type == "message.assistant.delta":
                    delta = event.get("delta", {})
                    if delta.get("type") == "text":
                        assistant_content += delta.get("content", "")
                
                elif event_type == "message.assistant.streaming":
                    assistant_content += event.get("content", "")
                
                elif event_type == "message.assistant.done":
                    data = event.get("data", {})
                    if data.get("content"):
                        assistant_content = data.get("content", assistant_content)
                    print(f"\n📥 助手回复（{event_count} 个事件）:")
                    # 截取显示
                    preview = assistant_content[:200] + "..." if len(assistant_content) > 200 else assistant_content
                    print(f"   {preview}")
            
            # ========================================
            # 验证结果
            # ========================================
            print("\n" + "=" * 70)
            print("🔍 验证结果")
            print("=" * 70)
            
            # 检查回复中是否包含"小明"
            if "小明" in assistant_content:
                print("✅ 测试通过！Agent 记住了名字 '小明'")
                return True
            else:
                print("❌ 测试失败！Agent 未能记住名字")
                print(f"   回复内容: {assistant_content}")
                return False
    
    except Exception as e:
        print(f"\n❌ 测试出错: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


async def test_without_conversation_id(agent_id: str = "dazee_agent", host: str = "localhost:50051"):
    """
    对照测试：不传 conversation_id 时应该不记得上下文
    """
    print("\n" + "=" * 70)
    print("🧪 对照测试：不传 conversation_id（应该不记得上下文）")
    print("=" * 70)
    
    try:
        async with ZenfluxGRPCClient(host) as client:
            # 第一轮：告诉名字
            print("\n📤 第一轮：发送 '我叫小红'（不保存 conversation_id）")
            async for event in client.chat_stream(
                message="我叫小红",
                user_id="test_user_no_memory",
                conversation_id=None,
                agent_id=agent_id
            ):
                if event.get("type") == "message.assistant.done":
                    print("   ✅ 第一轮完成")
            
            # 第二轮：不传 conversation_id
            print("\n📤 第二轮：发送 '我叫什么名字'（不传 conversation_id，新对话）")
            assistant_content = ""
            
            async for event in client.chat_stream(
                message="我叫什么名字",
                user_id="test_user_no_memory",
                conversation_id=None,  # 不传 conversation_id
                agent_id=agent_id
            ):
                event_type = event.get("type", "unknown")
                
                if event_type == "message.assistant.delta":
                    delta = event.get("delta", {})
                    if delta.get("type") == "text":
                        assistant_content += delta.get("content", "")
                
                elif event_type == "message.assistant.streaming":
                    assistant_content += event.get("content", "")
                
                elif event_type == "message.assistant.done":
                    data = event.get("data", {})
                    if data.get("content"):
                        assistant_content = data.get("content", assistant_content)
            
            print(f"\n📥 助手回复:")
            preview = assistant_content[:200] + "..." if len(assistant_content) > 200 else assistant_content
            print(f"   {preview}")
            
            # 验证：应该不包含"小红"
            if "小红" not in assistant_content:
                print("\n✅ 对照测试通过！不传 conversation_id 时，Agent 不记得名字")
                return True
            else:
                print("\n⚠️ 对照测试异常：Agent 不应该记得名字")
                return False
    
    except Exception as e:
        print(f"\n❌ 对照测试出错: {str(e)}")
        return False


if __name__ == "__main__":
    agent_id = sys.argv[1] if len(sys.argv) > 1 else "dazee_agent"
    host = sys.argv[2] if len(sys.argv) > 2 else "localhost:50051"
    
    # 运行主测试
    success1 = asyncio.run(test_conversation_memory(agent_id, host))
    
    # 运行对照测试
    success2 = asyncio.run(test_without_conversation_id(agent_id, host))
    
    print("\n" + "=" * 70)
    print("📊 测试汇总")
    print("=" * 70)
    print(f"   上下文记忆测试: {'✅ 通过' if success1 else '❌ 失败'}")
    print(f"   对照测试:       {'✅ 通过' if success2 else '❌ 失败'}")
    print("=" * 70)
    
    sys.exit(0 if (success1 and success2) else 1)
