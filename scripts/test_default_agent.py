#!/usr/bin/env python
"""
测试 gRPC 默认 agent_id (dazee_agent)
"""

import asyncio
import sys
import os

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from grpc_server.client import ZenfluxGRPCClient


async def test_default_agent():
    """
    测试不传 agent_id，应该默认使用 dazee_agent
    """
    print("=" * 60)
    print(f"🚀 测试 gRPC 默认 Agent（不传 agent_id，应使用 dazee_agent）")
    print(f"🌐 服务器地址: localhost:50051")
    print("=" * 60)
    
    try:
        async with ZenfluxGRPCClient("localhost:50051") as client:
            event_count = 0
            
            # 调用 chat_stream（不传 agent_id）
            async for event in client.chat_stream(
                message="你是谁",
                user_id="test_user_default",
                conversation_id=None,
                agent_id=""  # 传空字符串，测试默认值
            ):
                event_count += 1
                event_type = event.get("type", "unknown")
                
                # 简化输出
                if event_type == "message.assistant.start":
                    print(f"\n📝 助手消息开始 (message_id: {event.get('message_id', 'N/A')})")
                
                elif event_type == "message.assistant.delta":
                    delta = event.get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        print(content, end="", flush=True)
                
                elif event_type == "message.assistant.streaming":
                    content = event.get("content", "")
                    if content:
                        print(content, end="", flush=True)
                
                elif event_type == "message.assistant.done":
                    print(f"\n\n✅ 助手消息完成 (finish_reason: {event.get('finish_reason', 'N/A')})")
                
                elif event_type == "tool.call":
                    tool_name = event.get("tool_name", "unknown")
                    print(f"\n🔧 工具调用: {tool_name}")
                
                elif event_type == "tool.result":
                    tool_name = event.get("tool_name", "unknown")
                    print(f"✅ 工具结果: {tool_name}")
                
                elif event_type == "error":
                    print(f"\n❌ 错误: {event.get('error', 'unknown')}")
            
            print("\n" + "=" * 60)
            print(f"✅ 测试完成！共收到 {event_count} 个事件")
            print("=" * 60)
    
    except Exception as e:
        print(f"\n❌ 测试失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return False
    
    return True


if __name__ == "__main__":
    success = asyncio.run(test_default_agent())
    sys.exit(0 if success else 1)
