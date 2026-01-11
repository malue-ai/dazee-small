"""
gRPC 客户端使用示例

演示如何从其他微服务调用 Zenflux Agent 的 gRPC 接口
"""

import asyncio
from grpc_server.client import ZenfluxGRPCClient


async def example_sync_chat():
    """示例1: 同步聊天（返回 task_id）"""
    print("\n" + "="*60)
    print("示例1: 同步聊天")
    print("="*60)
    
    async with ZenfluxGRPCClient("localhost:50051") as client:
        # 发送聊天请求
        response = await client.chat(
            message="帮我生成一个产品介绍PPT",
            user_id="test_user_001",
            conversation_id="test_conv_001"
        )
        
        print(f"✅ 任务已启动")
        print(f"   Task ID: {response['task_id']}")
        print(f"   Conversation ID: {response['conversation_id']}")
        print(f"   Status: {response['status']}")
        
        # 可以轮询状态
        task_id = response['task_id']
        print(f"\n📊 查询任务状态...")
        
        while True:
            status = await client.get_session_status(task_id)
            print(f"   进度: {int(status['progress'] * 100)}% - {status['status']}")
            
            if status['status'] in ['completed', 'failed']:
                break
            
            await asyncio.sleep(2)
        
        print(f"\n✅ 任务完成！")


async def example_stream_chat():
    """示例2: 流式聊天（实时接收事件）"""
    print("\n" + "="*60)
    print("示例2: 流式聊天")
    print("="*60)
    
    async with ZenfluxGRPCClient("localhost:50051") as client:
        # 流式聊天
        print("📡 开始流式聊天...")
        
        async for event in client.chat_stream(
            message="帮我分析这个数据",
            user_id="test_user_002",
            variables={"timezone": "Asia/Shanghai"}
        ):
            event_type = event['type']
            
            # 根据事件类型处理
            if event_type == "thinking":
                print(f"💭 思考中...")
            elif event_type == "tool_call":
                tool_name = event['data'].get('name', 'unknown')
                print(f"🔧 调用工具: {tool_name}")
            elif event_type == "content_delta":
                delta = event['data'].get('delta', '')
                print(f"📝 {delta}", end='', flush=True)
            elif event_type == "message.assistant.done":
                print(f"\n✅ 回答完成！")
                break


async def example_reconnect():
    """示例3: 断线重连"""
    print("\n" + "="*60)
    print("示例3: 断线重连")
    print("="*60)
    
    async with ZenfluxGRPCClient("localhost:50051") as client:
        # 假设有一个正在运行的 session
        session_id = "sess_abc123"
        
        print(f"📡 重连到 Session: {session_id}")
        
        try:
            async for event in client.reconnect_stream(
                session_id=session_id,
                after_seq=100  # 从序号 100 之后开始
            ):
                event_type = event['type']
                
                if event_type == "reconnect_info":
                    info = event['data']
                    print(f"   Session 状态: {info.get('status')}")
                    print(f"   最后事件序号: {info.get('last_event_seq')}")
                elif event_type == "message.assistant.done":
                    print(f"✅ Session 已完成")
                    break
                else:
                    print(f"   事件: {event_type}")
        
        except Exception as e:
            print(f"❌ 重连失败: {e}")


async def example_session_management():
    """示例4: Session 管理"""
    print("\n" + "="*60)
    print("示例4: Session 管理")
    print("="*60)
    
    async with ZenfluxGRPCClient("localhost:50051") as client:
        # 列出所有会话
        print("📋 列出所有活跃会话...")
        sessions = await client.list_sessions()
        
        print(f"   总计: {len(sessions)} 个会话")
        for session in sessions[:5]:  # 只显示前5个
            print(f"   - {session['session_id']}: {session['status']} ({int(session['progress']*100)}%)")
        
        # 停止某个会话
        if sessions:
            session_id = sessions[0]['session_id']
            print(f"\n🛑 停止会话: {session_id}")
            
            result = await client.stop_session(session_id)
            print(f"   状态: {result['status']}")


async def example_microservice_integration():
    """示例5: 微服务集成场景"""
    print("\n" + "="*60)
    print("示例5: 微服务集成场景")
    print("="*60)
    
    # 假设这是另一个微服务的代码
    print("🔧 场景: 数据分析微服务调用 Agent 服务")
    
    async with ZenfluxGRPCClient("agent-service:50051") as client:
        # 1. 提交分析任务
        print("\n📤 提交数据分析任务...")
        response = await client.chat(
            message="分析这个季度的销售数据",
            user_id="analytics_service",
            files=[{
                "file_url": "s3://bucket/sales_q1.csv",
                "file_name": "sales_q1.csv"
            }]
        )
        
        task_id = response['task_id']
        print(f"   Task ID: {task_id}")
        
        # 2. 监控进度
        print(f"\n📊 监控任务进度...")
        while True:
            status = await client.get_session_status(task_id)
            progress = int(status['progress'] * 100)
            print(f"   {progress}% - {status['status']}")
            
            if status['status'] == 'completed':
                print(f"\n✅ 分析完成！")
                break
            elif status['status'] == 'failed':
                print(f"\n❌ 分析失败")
                break
            
            await asyncio.sleep(3)
        
        # 3. 获取结果并处理
        print(f"\n📦 获取分析结果...")
        summary = await client.end_session(task_id)
        print(f"   结果: {summary['summary']}")


async def main():
    """主函数"""
    print("\n" + "="*60)
    print("🚀 Zenflux Agent gRPC 客户端示例")
    print("="*60)
    print("\n确保 gRPC 服务器正在运行:")
    print("  1. 启动主服务: ENABLE_GRPC=true python main.py")
    print("  2. 或独立运行: python services/grpc/server.py")
    print()
    
    try:
        # 运行示例
        await example_sync_chat()
        # await example_stream_chat()
        # await example_reconnect()
        # await example_session_management()
        # await example_microservice_integration()
        
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        print(f"   请确保 gRPC 服务器正在运行（localhost:50051）")


if __name__ == "__main__":
    asyncio.run(main())

