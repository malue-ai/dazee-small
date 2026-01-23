#!/usr/bin/env python3
"""
gRPC 流式聊天测试脚本

使用方法:
    python scripts/test_grpc_chat.py --message "你的消息"
"""

import argparse
import json
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import grpc
from grpc_server.generated import tool_service_pb2
from grpc_server.generated import tool_service_pb2_grpc


def test_chat_stream(
    message: str,
    user_id: str = "test_user_grpc",
    agent_id: str = "dazee_agent",
    server_addr: str = "localhost:50051"
):
    """
    测试 gRPC 流式聊天
    
    Args:
        message: 用户消息
        user_id: 用户 ID
        agent_id: Agent ID
        server_addr: gRPC 服务地址
    """
    print(f"🔗 连接到 gRPC 服务: {server_addr}")
    print(f"📨 发送消息: {message}")
    print(f"👤 用户 ID: {user_id}")
    print(f"🤖 Agent ID: {agent_id}")
    print("-" * 60)
    
    # 创建 gRPC 通道
    channel = grpc.insecure_channel(server_addr)
    stub = tool_service_pb2_grpc.ChatServiceStub(channel)
    
    # 构建请求
    request = tool_service_pb2.ChatRequest(
        message=message,
        user_id=user_id,
        agent_id=agent_id,
        stream=True,
        background_tasks=["recommended_questions"]
    )
    
    try:
        # 调用流式接口
        event_count = 0
        for event in stub.ChatStream(request, timeout=300):
            event_count += 1
            
            # 直接打印原始 data，与 HTTP SSE 格式一致
            print(f"data: {event.data}\n")
        
        print(f"\n# 流式结束，共收到 {event_count} 个事件")
        
    except grpc.RpcError as e:
        print(f"❌ gRPC 错误: {e.code()} - {e.details()}")
        return False
    except Exception as e:
        print(f"❌ 错误: {str(e)}")
        return False
    finally:
        channel.close()
    
    return True


def main():
    parser = argparse.ArgumentParser(description="gRPC 流式聊天测试")
    parser.add_argument("--message", "-m", default="我要生成订单管理系统，后增加属性", help="发送的消息")
    parser.add_argument("--user", "-u", default="test_user_008", help="用户 ID")
    parser.add_argument("--agent", "-a", default="dazee_agent", help="Agent ID")
    parser.add_argument("--addr", default="localhost:50051", help="gRPC 服务地址")
    
    args = parser.parse_args()
    
    success = test_chat_stream(
        message=args.message,
        user_id=args.user,
        agent_id=args.agent,
        server_addr=args.addr
    )
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
