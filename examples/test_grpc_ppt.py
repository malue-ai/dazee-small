"""
gRPC 流式聊天测试脚本

对应 HTTP 请求:
curl -X POST "http://localhost:8000/api/v1/chat?format=zeno" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "帮我写一个PPT吧，做一个AI新技术的分享的，你需要先去网络上找资料",
    "user_id": "test_user_008",
    "conversation_id":"fa35fa57fb9e4f3bab39ac40ecf21ba0",
    "agent_id": "dazee_agent",
    "stream": true,
    "background_tasks": ["recommended_questions"]
  }'
"""

import asyncio
import json
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from grpc_server.client import ZenfluxGRPCClient


async def test_stream_chat():
    """测试流式聊天"""
    print("\n" + "=" * 60)
    print("🚀 gRPC 流式聊天测试 - PPT 生成")
    print("=" * 60)
    
    # 连接到 gRPC 服务器
    async with ZenfluxGRPCClient("localhost:50051", timeout=1800) as client:
        print("\n📡 开始流式聊天...")
        print("-" * 60)
        
        response_text = ""
        thinking_text = ""
        
        async for event in client.chat_stream(
            message="帮我写一个PPT吧，做一个AI新技术的分享的，你需要先去网络上找资料",
            user_id="test_user_008",
            agent_id="dazee_agent",
            background_tasks=["recommended_questions"]
        ):
            event_type = event.get("type", "")
            seq = event.get("seq", "")
            
            # 根据 ZenO 事件类型处理
            if event_type == "message.assistant.start":
                session_id = event.get("session_id", "")
                conversation_id = event.get("conversation_id", "")
                print(f"\n✅ 消息开始")
                print(f"   session_id: {session_id}")
                print(f"   conversation_id: {conversation_id}")
                print("-" * 60)
            
            elif event_type == "message.assistant.delta":
                delta = event.get("delta", {})
                delta_type = delta.get("type", "")
                content = delta.get("content", "")
                
                if delta_type == "thinking":
                    # 思考内容
                    thinking_text += content
                    print(f"💭 [thinking] {content[:100]}..." if len(content) > 100 else f"💭 [thinking] {content}")
                
                elif delta_type == "response":
                    # 回复内容
                    response_text += content
                    print(f"📝 [response] {content}", end="", flush=True)
                
                elif delta_type == "progress":
                    # 任务进度
                    print(f"\n📊 [progress] {json.dumps(content, ensure_ascii=False)[:200]}")
                
                elif delta_type == "search":
                    # 搜索结果
                    print(f"\n🔍 [search] 搜索完成")
                
                elif delta_type == "ppt":
                    # PPT 生成结果
                    print(f"\n📑 [ppt] PPT 已生成: {content.get('url', 'N/A') if isinstance(content, dict) else content[:100]}")
                
                elif delta_type == "recommended":
                    # 推荐问题
                    print(f"\n💡 [recommended] {content}")
                
                elif delta_type == "intent":
                    # 意图识别
                    print(f"\n🎯 [intent] {content}")
                
                else:
                    # 其他类型
                    print(f"\n📦 [{delta_type}] {str(content)[:200]}")
            
            elif event_type == "message.assistant.done":
                print(f"\n\n" + "=" * 60)
                print("✅ 消息完成")
                data = event.get("data", {})
                final_content = data.get("content", "")
                print(f"   最终内容长度: {len(final_content)} 字符")
                break
            
            elif event_type == "message.assistant.error":
                error = event.get("error", {})
                print(f"\n❌ 错误: {error.get('message', '未知错误')}")
                break
        
        print("\n" + "=" * 60)
        print("📊 统计")
        print("=" * 60)
        print(f"   思考内容: {len(thinking_text)} 字符")
        print(f"   回复内容: {len(response_text)} 字符")


async def main():
    """主函数"""
    print("\n" + "=" * 60)
    print("🔧 Zenflux Agent gRPC 测试")
    print("=" * 60)
    print("\n确保服务正在运行:")
    print("  1. HTTP 服务: python main.py")
    print("  2. gRPC 服务: ENABLE_GRPC=true python main.py")
    print("  3. 或者: python -m grpc_server.server")
    print()
    
    try:
        await test_stream_chat()
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
