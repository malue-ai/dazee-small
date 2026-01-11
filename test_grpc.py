#!/usr/bin/env python
"""
gRPC 客户端快速测试脚本

使用方法：
    python test_grpc.py              # 测试本地服务 localhost:50051
    python test_grpc.py remote       # 测试远程服务 agent.malue.ai:50051
"""

import asyncio
import sys

# 添加项目路径
sys.path.insert(0, '.')

from grpc_server.client import ZenfluxGRPCClient


async def test_connection(server_address: str = "localhost:50051"):
    """测试 gRPC 连接"""
    print(f"\n{'='*60}")
    print(f"🧪 gRPC 连接测试")
    print(f"   服务器地址: {server_address}")
    print(f"{'='*60}\n")
    
    try:
        async with ZenfluxGRPCClient(server_address, timeout=30) as client:
            print("✅ gRPC 连接成功！\n")
            
            # 测试 1：列出活跃会话
            print("📋 测试 1: 列出活跃会话...")
            try:
                sessions = await client.list_sessions()
                print(f"   ✅ 成功！当前活跃会话数: {len(sessions)}")
                for s in sessions[:3]:
                    print(f"      - {s['session_id']}: {s['status']}")
            except Exception as e:
                print(f"   ❌ 失败: {e}")
            
            print()
            
            # 测试 2：发送简单聊天请求
            print("💬 测试 2: 发送聊天请求...")
            try:
                response = await client.chat(
                    message="你好，请简单介绍一下你自己",
                    user_id="grpc_test_user",
                )
                print(f"   ✅ 成功！")
                print(f"      Task ID: {response.get('task_id')}")
                print(f"      Status: {response.get('status')}")
            except Exception as e:
                print(f"   ❌ 失败: {e}")
            
            print()
            print(f"{'='*60}")
            print("🎉 gRPC 测试完成！")
            print(f"{'='*60}\n")
            
    except Exception as e:
        print(f"❌ 连接失败: {e}")
        print("\n💡 请确保：")
        print("   1. gRPC 服务已启动 (ENABLE_GRPC=true)")
        print("   2. 服务器地址正确")
        print("   3. 端口 50051 可访问")


async def test_stream(server_address: str = "localhost:50051"):
    """测试流式聊天"""
    print(f"\n{'='*60}")
    print(f"🌊 gRPC 流式测试")
    print(f"   服务器地址: {server_address}")
    print(f"{'='*60}\n")
    
    try:
        async with ZenfluxGRPCClient(server_address, timeout=120) as client:
            print("💬 发送流式请求: '什么是 RAG?'\n")
            print("-" * 40)
            
            async for event in client.chat_stream(
                message="什么是RAG？请简单解释",
                user_id="grpc_stream_test",
            ):
                event_type = event.get('type', event.get('event_type', 'unknown'))
                
                # 调试：打印原始事件（用 --debug 参数启用）
                if '--debug' in sys.argv:
                    print(f"\n[DEBUG] {event_type}: {event}")
                
                if event_type == 'content_delta':
                    # 尝试多种格式
                    delta = event.get('delta', '')
                    if not delta:
                        delta = event.get('data', {}).get('delta', '') if isinstance(event.get('data'), dict) else ''
                    if not delta:
                        delta = event.get('content', '')
                    print(delta, end='', flush=True)
                elif event_type == 'text_delta':
                    delta = event.get('delta', '') or event.get('text', '')
                    print(delta, end='', flush=True)
                elif event_type == 'thinking':
                    print("💭 思考中...", flush=True)
                elif event_type in ('message.assistant.done', 'done', 'end'):
                    print("\n\n✅ 流式响应完成！")
                    break
                elif 'delta' in str(event):
                    # 兜底：如果事件中包含 delta，尝试提取
                    for key in ['delta', 'text', 'content']:
                        if key in event and event[key]:
                            print(event[key], end='', flush=True)
                            break
            
            print("\n" + "-" * 40)
            
    except Exception as e:
        print(f"❌ 流式测试失败: {e}")


if __name__ == "__main__":
    # 解析参数
    if len(sys.argv) > 1 and sys.argv[1] == "remote":
        server = "agent.malue.ai:50051"
    elif len(sys.argv) > 1 and sys.argv[1] == "stream":
        asyncio.run(test_stream())
        sys.exit(0)
    else:
        server = "localhost:50051"
    
    asyncio.run(test_connection(server))

