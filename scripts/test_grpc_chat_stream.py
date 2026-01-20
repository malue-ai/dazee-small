#!/usr/bin/env python
"""
gRPC ChatStream 测试脚本

测试 gRPC 服务器的 ChatStream 接口（支持 Mock 模式）

使用方法：
    # 确保服务端已启用 Mock 模式（设置 ENABLE_MOCK_MODE=true）
    python scripts/test_grpc_chat_stream.py
"""

import asyncio
import sys
import os

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from grpc_server.client import ZenfluxGRPCClient


async def test_chat_stream(agent_id: str = "zeno_agent", host: str = "localhost:50051"):
    """
    测试 ChatStream 接口
    
    当服务端 ENABLE_MOCK_MODE=true 时，会返回 mock 数据
    
    Args:
        agent_id: Agent 实例 ID，默认 zeno_agent
        host: gRPC 服务器地址，默认 localhost:50051
    """
    print("=" * 60)
    print(f"🚀 测试 gRPC ChatStream 接口 (agent_id={agent_id})")
    print(f"🌐 服务器地址: {host}")
    print("=" * 60)
    
    try:
        async with ZenfluxGRPCClient(host) as client:
            event_count = 0
            
            # 调用 chat_stream（如果服务端启用了 mock，会返回 mock 数据）
            async for event in client.chat_stream(
                message="帮我分析一下销售数据",
                user_id="test_user_001",
                conversation_id="test_conv_001",
                agent_id=agent_id
            ):
                event_count += 1
                event_type = event.get("type", "unknown")
                
                # 根据事件类型打印不同格式
                if event_type == "message.assistant.start":
                    print(f"\n📝 [{event_count}] 助手消息开始")
                    print(f"   message_id: {event.get('message_id', 'N/A')}")
                
                elif event_type == "message.assistant.streaming":
                    content = event.get("content", "")
                    # 只打印前 80 个字符
                    preview = content[:80] + "..." if len(content) > 80 else content
                    print(f"   💬 [{event_count}] 流式内容: {preview}")
                
                elif event_type == "message.assistant.done":
                    print(f"\n✅ [{event_count}] 助手消息完成")
                    print(f"   finish_reason: {event.get('finish_reason', 'N/A')}")
                
                elif event_type == "tool.call":
                    tool_name = event.get("tool_name", "unknown")
                    print(f"\n🔧 [{event_count}] 工具调用: {tool_name}")
                    if "input" in event:
                        input_str = str(event['input'])
                        preview = input_str[:100] + "..." if len(input_str) > 100 else input_str
                        print(f"   输入: {preview}")
                
                elif event_type == "tool.result":
                    tool_name = event.get("tool_name", "unknown")
                    print(f"   ✅ [{event_count}] 工具结果: {tool_name}")
                
                elif event_type == "thinking.start":
                    print(f"\n🧠 [{event_count}] 开始思考...")
                
                elif event_type == "thinking.streaming":
                    content = event.get("content", "")
                    preview = content[:80] + "..." if len(content) > 80 else content
                    print(f"   💭 [{event_count}] 思考: {preview}")
                
                elif event_type == "thinking.done":
                    print(f"   ✅ [{event_count}] 思考完成")
                
                elif event_type == "error":
                    print(f"\n❌ [{event_count}] 错误: {event.get('error', 'unknown')}")
                
                else:
                    print(f"   📦 [{event_count}] {event_type}: {str(event)[:100]}")
            
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
    # 从命令行参数获取 agent_id 和 host
    # 用法: python test_grpc_chat_stream.py [agent_id] [host]
    # 例如: python test_grpc_chat_stream.py zeno_agent agent.malue.ai:50051
    agent_id = sys.argv[1] if len(sys.argv) > 1 else "zeno_agent"
    host = sys.argv[2] if len(sys.argv) > 2 else "localhost:50051"
    success = asyncio.run(test_chat_stream(agent_id, host))
    sys.exit(0 if success else 1)
