#!/usr/bin/env python
"""
gRPC 重连功能测试脚本

测试场景：
1. 发起一个流式聊天请求，获取 session_id
2. 收集一些事件后主动断开
3. 等待指定时间（默认 30 秒）
4. 使用 reconnect_stream 重新连接，验证能否继续接收事件

使用方法：
    # 基本用法（等待 30 秒后重连）
    python scripts/test_grpc_reconnect.py
    
    # 自定义等待时间（10 秒）
    python scripts/test_grpc_reconnect.py --wait 10
    
    # 自定义 agent_id 和 host
    python scripts/test_grpc_reconnect.py --agent dazee_agent --host localhost:50051
    
    # 不等待，立即重连（用于测试已完成的会话）
    python scripts/test_grpc_reconnect.py --wait 0
"""

import asyncio
import sys
import os
import argparse
from datetime import datetime

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from grpc_server.client import ZenfluxGRPCClient


def print_event(event_count: int, event: dict, prefix: str = ""):
    """
    格式化打印事件
    
    Args:
        event_count: 事件计数
        event: 事件字典
        prefix: 打印前缀
    """
    event_type = event.get("type", "unknown")
    seq = event.get("seq", "N/A")
    
    # 根据事件类型打印不同格式
    if event_type == "message.assistant.start":
        print(f"{prefix}📝 [{event_count}] [seq={seq}] 助手消息开始")
        print(f"{prefix}   message_id: {event.get('message_id', 'N/A')}")
        if "session_id" in event:
            print(f"{prefix}   session_id: {event.get('session_id')}")
    
    elif event_type == "message.assistant.delta":
        delta = event.get("delta", {})
        delta_type = delta.get("type", "unknown")
        content = delta.get("content", "")
        preview = content[:60] + "..." if len(content) > 60 else content
        print(f"{prefix}   💬 [{event_count}] [seq={seq}] [{delta_type}] {preview}")
    
    elif event_type == "message.assistant.streaming":
        content = event.get("content", "")
        preview = content[:60] + "..." if len(content) > 60 else content
        print(f"{prefix}   💬 [{event_count}] [seq={seq}] 流式内容: {preview}")
    
    elif event_type == "message.assistant.done":
        print(f"{prefix}✅ [{event_count}] [seq={seq}] 助手消息完成")
        print(f"{prefix}   finish_reason: {event.get('finish_reason', 'N/A')}")
    
    elif event_type == "tool.call":
        tool_name = event.get("tool_name", "unknown")
        print(f"{prefix}🔧 [{event_count}] [seq={seq}] 工具调用: {tool_name}")
    
    elif event_type == "tool.result":
        tool_name = event.get("tool_name", "unknown")
        print(f"{prefix}   ✅ [{event_count}] [seq={seq}] 工具结果: {tool_name}")
    
    elif event_type == "thinking.start":
        print(f"{prefix}🧠 [{event_count}] [seq={seq}] 开始思考...")
    
    elif event_type == "thinking.streaming":
        content = event.get("content", "")
        preview = content[:60] + "..." if len(content) > 60 else content
        print(f"{prefix}   💭 [{event_count}] [seq={seq}] 思考: {preview}")
    
    elif event_type == "thinking.done":
        print(f"{prefix}   ✅ [{event_count}] [seq={seq}] 思考完成")
    
    elif event_type == "message.assistant.error":
        error = event.get("error", {})
        print(f"{prefix}❌ [{event_count}] [seq={seq}] 错误: {error.get('message', 'unknown')}")
        print(f"{prefix}   code: {error.get('code', 'N/A')}")
    
    elif event_type == "reconnect_info":
        print(f"{prefix}🔄 [{event_count}] [seq={seq}] 重连信息")
        print(f"{prefix}   session_id: {event.get('session_id', 'N/A')}")
        print(f"{prefix}   status: {event.get('status', 'N/A')}")
    
    else:
        print(f"{prefix}📦 [{event_count}] [seq={seq}] {event_type}")


async def test_reconnect(
    agent_id: str = "dazee_agent",
    host: str = "localhost:50051",
    wait_seconds: int = 30,
    max_events_before_disconnect: int = 5,
    message: str = "你好，请帮我分析一下销售数据"
):
    """
    测试 gRPC 重连功能
    
    Args:
        agent_id: Agent 实例 ID
        host: gRPC 服务器地址
        wait_seconds: 断开后等待重连的时间（秒）
        max_events_before_disconnect: 收到多少个事件后主动断开
        message: 发送的消息
    """
    print("=" * 70)
    print(f"🚀 gRPC 重连功能测试")
    print(f"   服务器: {host}")
    print(f"   Agent: {agent_id}")
    print(f"   等待时间: {wait_seconds} 秒")
    print(f"   断开前事件数: {max_events_before_disconnect}")
    print("=" * 70)
    
    session_id = None
    last_seq = 0
    events_received = []
    
    # ==================== 第一阶段：发起请求并收集事件 ====================
    print(f"\n📡 第一阶段：发起聊天请求")
    print(f"   消息: {message}")
    print("-" * 70)
    
    try:
        async with ZenfluxGRPCClient(host) as client:
            event_count = 0
            
            async for event in client.chat_stream(
                message=message,
                user_id="test_reconnect_user",
                conversation_id=None,
                agent_id=agent_id
            ):
                event_count += 1
                events_received.append(event)
                
                # 提取 session_id（通常在第一个事件中）
                if "session_id" in event and not session_id:
                    session_id = event["session_id"]
                    print(f"\n   🔑 获取到 session_id: {session_id}")
                
                # 更新 last_seq
                if "seq" in event:
                    try:
                        last_seq = int(event["seq"])
                    except (ValueError, TypeError):
                        pass
                
                print_event(event_count, event, "   ")
                
                # 收集指定数量的事件后断开
                if event_count >= max_events_before_disconnect:
                    print(f"\n   ⚡ 已收到 {event_count} 个事件，主动断开连接")
                    break
            
            print(f"\n   📊 第一阶段总结:")
            print(f"      - 收到事件: {event_count}")
            print(f"      - session_id: {session_id}")
            print(f"      - last_seq: {last_seq}")
    
    except Exception as e:
        print(f"\n   ❌ 第一阶段错误: {str(e)}")
        import traceback
        traceback.print_exc()
    
    # 检查是否获取到 session_id
    if not session_id:
        print("\n❌ 测试失败：未能获取 session_id")
        print("   请检查服务端是否正常运行，或者事件格式是否包含 session_id")
        return False
    
    # ==================== 等待阶段 ====================
    if wait_seconds > 0:
        print(f"\n⏳ 等待 {wait_seconds} 秒后重连...")
        print(f"   开始时间: {datetime.now().strftime('%H:%M:%S')}")
        
        # 每 5 秒打印一次倒计时
        remaining = wait_seconds
        while remaining > 0:
            wait_chunk = min(5, remaining)
            await asyncio.sleep(wait_chunk)
            remaining -= wait_chunk
            if remaining > 0:
                print(f"   剩余 {remaining} 秒...")
        
        print(f"   结束时间: {datetime.now().strftime('%H:%M:%S')}")
    
    # ==================== 第二阶段：重连 ====================
    print(f"\n🔄 第二阶段：使用 reconnect_stream 重连")
    print(f"   session_id: {session_id}")
    print(f"   after_seq: {last_seq}")
    print("-" * 70)
    
    reconnect_event_count = 0
    reconnect_success = False
    
    try:
        async with ZenfluxGRPCClient(host) as client:
            async for event in client.reconnect_stream(
                session_id=session_id,
                after_seq=last_seq
            ):
                reconnect_event_count += 1
                
                # 更新 last_seq
                if "seq" in event:
                    try:
                        last_seq = int(event["seq"])
                    except (ValueError, TypeError):
                        pass
                
                print_event(reconnect_event_count, event, "   ")
                
                # 检查是否成功接收到事件
                event_type = event.get("type", "")
                if event_type not in ["message.assistant.error"]:
                    reconnect_success = True
                
                # 如果收到完成事件，结束重连
                if event_type in ["message.assistant.done", "session_end", "message_complete"]:
                    print(f"\n   ✅ 会话已完成")
                    break
            
            print(f"\n   📊 第二阶段总结:")
            print(f"      - 重连收到事件: {reconnect_event_count}")
            print(f"      - 最后 seq: {last_seq}")
    
    except Exception as e:
        print(f"\n   ❌ 重连错误: {str(e)}")
        import traceback
        traceback.print_exc()
    
    # ==================== 测试结果 ====================
    print("\n" + "=" * 70)
    total_events = len(events_received) + reconnect_event_count
    print(f"📋 测试结果总结")
    print(f"   第一阶段事件数: {len(events_received)}")
    print(f"   重连后事件数: {reconnect_event_count}")
    print(f"   总事件数: {total_events}")
    
    if reconnect_success:
        print(f"\n✅ 重连测试成功！")
    else:
        print(f"\n⚠️ 重连测试完成，但可能存在问题")
        print(f"   - 如果会话已结束，重连不会收到新事件")
        print(f"   - 检查 session_id 是否有效")
    
    print("=" * 70)
    return reconnect_success


async def test_reconnect_with_existing_session(
    session_id: str,
    host: str = "localhost:50051",
    after_seq: int = 0
):
    """
    直接使用已有的 session_id 测试重连
    
    Args:
        session_id: 已存在的 session_id
        host: gRPC 服务器地址
        after_seq: 从哪个序号之后开始
    """
    print("=" * 70)
    print(f"🔄 直接重连到已有会话")
    print(f"   服务器: {host}")
    print(f"   session_id: {session_id}")
    print(f"   after_seq: {after_seq}")
    print("=" * 70)
    
    event_count = 0
    
    try:
        async with ZenfluxGRPCClient(host) as client:
            async for event in client.reconnect_stream(
                session_id=session_id,
                after_seq=after_seq
            ):
                event_count += 1
                print_event(event_count, event, "   ")
                
                # 如果收到完成事件，结束
                event_type = event.get("type", "")
                if event_type in ["message.assistant.done", "session_end", "message_complete"]:
                    print(f"\n   ✅ 会话已完成")
                    break
        
        print(f"\n📊 重连总结:")
        print(f"   收到事件: {event_count}")
        return True
    
    except Exception as e:
        print(f"\n❌ 重连失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="gRPC 重连功能测试")
    parser.add_argument("--agent", "-a", default="dazee_agent", help="Agent 实例 ID")
    parser.add_argument("--host", "-H", default="localhost:50051", help="gRPC 服务器地址")
    parser.add_argument("--wait", "-w", type=int, default=30, help="断开后等待重连的时间（秒）")
    parser.add_argument("--events", "-e", type=int, default=5, help="收到多少个事件后断开")
    parser.add_argument("--message", "-m", default="你好，请介绍一下你自己", help="发送的消息")
    parser.add_argument("--session", "-s", help="直接重连到已有的 session_id（跳过第一阶段）")
    parser.add_argument("--after-seq", type=int, default=0, help="从哪个序号之后开始（与 --session 配合使用）")
    
    args = parser.parse_args()
    
    if args.session:
        # 直接重连模式
        success = asyncio.run(test_reconnect_with_existing_session(
            session_id=args.session,
            host=args.host,
            after_seq=args.after_seq
        ))
    else:
        # 完整测试模式
        success = asyncio.run(test_reconnect(
            agent_id=args.agent,
            host=args.host,
            wait_seconds=args.wait,
            max_events_before_disconnect=args.events,
            message=args.message
        ))
    
    sys.exit(0 if success else 1)
