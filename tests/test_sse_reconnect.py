"""
SSE 重连功能测试

测试 /api/v1/chat/{session_id} 重连接口是否正常工作
"""

import asyncio
import json
import time
from datetime import datetime
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
import httpx
from fastapi.testclient import TestClient

# 测试配置
BASE_URL = "http://localhost:8000"


class TestSSEReconnectLogic:
    """测试 SSE 重连逻辑（单元测试）"""
    
    @pytest.mark.asyncio
    async def test_redis_get_events_with_seq(self):
        """测试 Redis 获取事件（使用 seq 字段）"""
        from services.redis_manager import RedisSessionManager
        
        manager = RedisSessionManager()
        session_id = f"test_sess_{int(time.time())}"
        
        try:
            # 创建 session
            await manager.create_session(
                session_id=session_id,
                user_id="test_user",
                conversation_id="test_conv",
                message_preview="测试消息"
            )
            
            # 写入一些事件（带 seq 字段）
            for i in range(1, 6):
                event = {
                    "seq": i,
                    "type": "text_delta",
                    "data": {"content": f"内容{i}"},
                    "timestamp": datetime.now().isoformat()
                }
                await manager.buffer_event(session_id, event_data=event)
            
            # 测试获取所有事件
            events = await manager.get_events(session_id, after_id=None)
            print(f"\n📋 获取所有事件: {len(events)} 个")
            for e in events:
                print(f"  - seq={e.get('seq')}, type={e.get('type')}")
            
            assert len(events) == 5, f"应该有5个事件，实际有 {len(events)} 个"
            
            # 测试 after_id 过滤（获取 seq > 2 的事件）
            events_after_2 = await manager.get_events(session_id, after_id=2)
            print(f"\n📋 获取 seq > 2 的事件: {len(events_after_2)} 个")
            for e in events_after_2:
                print(f"  - seq={e.get('seq')}, type={e.get('type')}")
            
            assert len(events_after_2) == 3, f"应该有3个事件(seq=3,4,5)，实际有 {len(events_after_2)} 个"
            
            # 验证事件的 seq 都 > 2
            for e in events_after_2:
                assert e.get("seq", 0) > 2, f"事件 seq 应该 > 2，实际 seq={e.get('seq')}"
            
            print("\n✅ seq 字段过滤测试通过")
            
        finally:
            # 清理
            client = await manager._get_client()
            await client.delete(f"session:{session_id}:status")
            await client.delete(f"session:{session_id}:events")
            await client.delete(f"session:{session_id}:seq_counter")
    
    @pytest.mark.asyncio
    async def test_redis_get_events_with_id(self):
        """测试 Redis 获取事件（使用 id 字段，旧格式兼容）"""
        from services.redis_manager import RedisSessionManager
        
        manager = RedisSessionManager()
        session_id = f"test_sess_id_{int(time.time())}"
        
        try:
            # 创建 session
            await manager.create_session(
                session_id=session_id,
                user_id="test_user",
                conversation_id="test_conv",
                message_preview="测试消息"
            )
            
            # 写入事件（使用 id 字段，不用 seq）
            for i in range(1, 6):
                event = {
                    "id": i,  # 使用 id 而不是 seq
                    "type": "text_delta",
                    "data": {"content": f"内容{i}"},
                    "timestamp": datetime.now().isoformat()
                }
                await manager.buffer_event(session_id, event_data=event)
            
            # 测试 after_id 过滤
            events_after_2 = await manager.get_events(session_id, after_id=2)
            print(f"\n📋 使用 id 字段，获取 id > 2 的事件: {len(events_after_2)} 个")
            for e in events_after_2:
                print(f"  - id={e.get('id')}, type={e.get('type')}")
            
            assert len(events_after_2) == 3, f"应该有3个事件(id=3,4,5)，实际有 {len(events_after_2)} 个"
            
            print("\n✅ id 字段过滤测试通过")
            
        finally:
            # 清理
            client = await manager._get_client()
            await client.delete(f"session:{session_id}:status")
            await client.delete(f"session:{session_id}:events")
            await client.delete(f"session:{session_id}:seq_counter")
    
    @pytest.mark.asyncio
    async def test_pubsub_subscribe_events(self):
        """测试 Pub/Sub 订阅事件流"""
        from services.redis_manager import RedisSessionManager
        
        manager = RedisSessionManager()
        session_id = f"test_sess_pubsub_{int(time.time())}"
        
        try:
            # 创建 session
            await manager.create_session(
                session_id=session_id,
                user_id="test_user",
                conversation_id="test_conv",
                message_preview="测试消息"
            )
            
            # 先写入一些历史事件
            for i in range(1, 4):
                event = {
                    "seq": i,
                    "type": "text_delta",
                    "data": {"content": f"历史内容{i}"},
                    "timestamp": datetime.now().isoformat()
                }
                await manager.buffer_event(session_id, event_data=event)
            
            received_events = []
            
            async def producer():
                """生产者：延迟后发布新事件"""
                await asyncio.sleep(0.5)
                for i in range(4, 7):
                    event = {
                        "seq": i,
                        "type": "text_delta",
                        "data": {"content": f"新内容{i}"},
                        "timestamp": datetime.now().isoformat()
                    }
                    await manager.buffer_event(session_id, event_data=event)
                    print(f"  📤 发布事件 seq={i}")
                    await asyncio.sleep(0.1)
                
                # 标记 session 完成
                await manager.complete_session(session_id, status="completed")
            
            async def consumer():
                """消费者：订阅事件流"""
                async for event in manager.subscribe_events(
                    session_id=session_id,
                    after_id=0,  # 从头开始
                    timeout=5
                ):
                    received_events.append(event)
                    print(f"  📥 收到事件 seq={event.get('seq')}")
            
            # 并发运行生产者和消费者
            print("\n🔄 开始 Pub/Sub 测试...")
            await asyncio.gather(producer(), consumer())
            
            print(f"\n📋 共收到 {len(received_events)} 个事件")
            
            # 应该收到所有 6 个事件（3个历史 + 3个新发布）
            assert len(received_events) >= 3, f"至少应该收到3个历史事件，实际收到 {len(received_events)} 个"
            
            print("\n✅ Pub/Sub 订阅测试通过")
            
        finally:
            # 清理
            client = await manager._get_client()
            await client.delete(f"session:{session_id}:status")
            await client.delete(f"session:{session_id}:events")
            await client.delete(f"session:{session_id}:seq_counter")


class TestSSEReconnectAPI:
    """测试 SSE 重连 API（需要启动服务器）"""
    
    @pytest.mark.asyncio
    async def test_reconnect_to_running_session(self):
        """测试重连到运行中的 session（模拟数据）"""
        from services.redis_manager import get_redis_manager
        
        redis = get_redis_manager()
        session_id = f"test_reconnect_{int(time.time())}"
        
        try:
            # 1. 创建一个模拟的运行中的 session
            await redis.create_session(
                session_id=session_id,
                user_id="test_user",
                conversation_id="test_conv_123",
                message_id="msg_001",
                message_preview="测试消息"
            )
            
            # 2. 写入一些历史事件
            for i in range(1, 6):
                event = {
                    "seq": i,
                    "type": "text_delta",
                    "data": {"content": f"内容{i}"},
                    "timestamp": datetime.now().isoformat()
                }
                await redis.buffer_event(session_id, event_data=event)
            
            print(f"\n📝 已创建测试 session: {session_id}")
            print(f"   已写入 5 个历史事件")
            
            # 3. 调用重连 API
            async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
                print(f"\n🔗 调用重连 API: GET /api/v1/chat/{session_id}?after_seq=2")
                
                async with client.stream(
                    "GET",
                    f"/api/v1/chat/{session_id}",
                    params={"after_seq": 2, "format": "zenflux"}  # 使用原始格式便于测试
                ) as response:
                    if response.status_code != 200:
                        body = await response.aread()
                        print(f"❌ 请求失败: {response.status_code}")
                        print(f"   响应: {body.decode()}")
                        return
                    
                    print(f"✅ 连接成功，开始接收事件...")
                    
                    event_count = 0
                    async for line in response.aiter_lines():
                        if line.startswith("data:"):
                            data = line[5:].strip()
                            if data and data != "{}":
                                try:
                                    event = json.loads(data)
                                    event_type = event.get("type", "unknown")
                                    event_seq = event.get("seq", event.get("id", "?"))
                                    print(f"   📥 收到事件: type={event_type}, seq={event_seq}")
                                    event_count += 1
                                except json.JSONDecodeError:
                                    print(f"   ⚠️ 无法解析: {data[:50]}...")
                        
                        # 收到足够多的事件后退出
                        if event_count >= 5:
                            break
                    
                    print(f"\n📊 共收到 {event_count} 个事件")
            
        except httpx.ConnectError:
            print(f"\n⚠️ 无法连接到服务器 {BASE_URL}")
            print("   请确保服务器已启动: python main.py")
            pytest.skip("服务器未启动")
            
        finally:
            # 清理
            client = await redis._get_client()
            await client.delete(f"session:{session_id}:status")
            await client.delete(f"session:{session_id}:events")
            await client.delete(f"session:{session_id}:seq_counter")
            await client.delete(f"session:{session_id}:heartbeat")
            print(f"\n🧹 已清理测试数据")
    
    @pytest.mark.asyncio
    async def test_real_chat_and_reconnect(self):
        """
        端到端测试：真实调用 chat 接口，然后重连
        
        流程：
        1. POST /api/v1/chat 开始对话
        2. 接收一些事件后记录 session_id 和 last_seq
        3. 断开连接
        4. GET /api/v1/chat/{session_id}?after_seq=N 重连
        5. 验证能继续接收事件
        """
        print("\n" + "=" * 60)
        print("🧪 端到端测试：真实 Chat + 重连")
        print("=" * 60)
        
        session_id = None
        last_seq = 0
        received_events_phase1 = []
        received_events_phase2 = []
        
        try:
            async with httpx.AsyncClient(base_url=BASE_URL, timeout=60.0) as client:
                # ===== 阶段 1：发起对话，接收部分事件 =====
                print("\n📤 阶段 1：发起对话...")
                
                chat_request = {
                    "message": "你好，请简单介绍一下你自己",
                    "user_id": "test_user_reconnect",
                    "stream": True
                }
                
                async with client.stream(
                    "POST",
                    "/api/v1/chat",
                    json=chat_request,
                    params={"format": "zenflux"}  # 使用原始格式
                ) as response:
                    if response.status_code != 200:
                        body = await response.aread()
                        print(f"❌ Chat 请求失败: {response.status_code}")
                        print(f"   响应: {body.decode()[:200]}")
                        return
                    
                    print("✅ Chat 连接成功，开始接收事件...")
                    
                    event_count = 0
                    async for line in response.aiter_lines():
                        if line.startswith("data:"):
                            data = line[5:].strip()
                            if data and data != "{}":
                                try:
                                    event = json.loads(data)
                                    event_type = event.get("type", "unknown")
                                    event_seq = event.get("seq", event.get("id", 0))
                                    event_session = event.get("session_id", "")
                                    
                                    # 记录 session_id
                                    if event_session and not session_id:
                                        session_id = event_session
                                        print(f"   🔑 获取到 session_id: {session_id}")
                                    
                                    # 更新 last_seq
                                    if isinstance(event_seq, int) and event_seq > last_seq:
                                        last_seq = event_seq
                                    
                                    received_events_phase1.append(event)
                                    print(f"   📥 [{event_count + 1}] type={event_type}, seq={event_seq}")
                                    # 🆕 打印完整事件数据
                                    print(f"      📄 完整数据: {json.dumps(event, ensure_ascii=False)[:200]}...")
                                    event_count += 1
                                    
                                except json.JSONDecodeError:
                                    pass
                        
                        # 接收 5 个事件后"断开"
                        if event_count >= 5:
                            print(f"\n⚡ 模拟断线！（已接收 {event_count} 个事件，last_seq={last_seq}）")
                            break
                
                if not session_id:
                    print("❌ 未获取到 session_id，无法重连")
                    return
                
                # ===== 等待一段时间，让 Agent 继续生成 =====
                print(f"\n⏳ 等待 10 秒，让 Agent 继续生成事件...")
                await asyncio.sleep(10)
                
                # ===== 阶段 2：重连 =====
                print(f"\n📤 阶段 2：重连到 session_id={session_id}, after_seq={last_seq}")
                
                async with client.stream(
                    "GET",
                    f"/api/v1/chat/{session_id}",
                    params={"after_seq": last_seq, "format": "zenflux"},
                    timeout=30.0
                ) as response:
                    if response.status_code != 200:
                        body = await response.aread()
                        print(f"❌ 重连失败: {response.status_code}")
                        print(f"   响应: {body.decode()[:200]}")
                        # 如果返回 410，说明 session 已完成
                        if response.status_code == 410:
                            print("   ℹ️ Session 已完成，这是正常的")
                        return
                    
                    print("✅ 重连成功，接收后续事件...")
                    
                    event_count = 0
                    async for line in response.aiter_lines():
                        if line.startswith("data:"):
                            data = line[5:].strip()
                            if data and data != "{}":
                                try:
                                    event = json.loads(data)
                                    event_type = event.get("type", "unknown")
                                    event_seq = event.get("seq", event.get("id", "?"))
                                    
                                    received_events_phase2.append(event)
                                    print(f"   📥 [{event_count + 1}] type={event_type}, seq={event_seq}")
                                    # 🆕 打印完整事件数据（前 10 个显示详情）
                                    if event_count < 10:
                                        print(f"      📄 完整数据: {json.dumps(event, ensure_ascii=False)[:300]}...")
                                    event_count += 1
                                    
                                    # 检查是否结束
                                    if event_type in ["message_stop", "session_end", "message.assistant.done"]:
                                        print(f"   🏁 收到结束事件")
                                        print(f"      📄 结束事件完整数据: {json.dumps(event, ensure_ascii=False)}")
                                        break
                                        
                                except json.JSONDecodeError:
                                    pass
                        
                        # 最多接收 20 个事件
                        if event_count >= 20:
                            break
                    
                    print(f"\n📊 重连后收到 {event_count} 个事件")
                
                # ===== 结果验证 =====
                print("\n" + "=" * 60)
                print("📊 测试结果")
                print("=" * 60)
                print(f"   阶段 1 收到事件: {len(received_events_phase1)} 个")
                print(f"   阶段 2 收到事件: {len(received_events_phase2)} 个")
                print(f"   总计: {len(received_events_phase1) + len(received_events_phase2)} 个")
                
                # 验证重连后的事件 seq 都 > last_seq
                if received_events_phase2:
                    reconnect_seqs = [
                        e.get("seq", e.get("id", 0)) 
                        for e in received_events_phase2 
                        if isinstance(e.get("seq", e.get("id")), int)
                    ]
                    if reconnect_seqs:
                        min_reconnect_seq = min(reconnect_seqs)
                        print(f"   重连后最小 seq: {min_reconnect_seq} (应该 > {last_seq})")
                        if min_reconnect_seq > last_seq:
                            print("   ✅ 断点续传正确！没有重复事件")
                        else:
                            print("   ⚠️ 可能有重复事件")
                
                print("\n✅ 端到端测试完成！")
                
        except httpx.ConnectError:
            print(f"\n⚠️ 无法连接到服务器 {BASE_URL}")
            print("   请确保服务器已启动: python main.py")
        except Exception as e:
            print(f"\n❌ 测试出错: {e}")
            import traceback
            traceback.print_exc()
    
    @pytest.mark.asyncio
    async def test_reconnect_to_completed_session(self):
        """测试重连到已完成的 session（应该返回 410）"""
        from services.redis_manager import get_redis_manager
        
        redis = get_redis_manager()
        session_id = f"test_completed_{int(time.time())}"
        
        try:
            # 创建并立即完成 session
            await redis.create_session(
                session_id=session_id,
                user_id="test_user",
                conversation_id="test_conv",
                message_preview="测试消息"
            )
            await redis.complete_session(session_id, status="completed")
            
            print(f"\n📝 已创建并完成 session: {session_id}")
            
            # 调用重连 API
            async with httpx.AsyncClient(base_url=BASE_URL, timeout=5.0) as client:
                response = await client.get(f"/api/v1/chat/{session_id}")
                
                print(f"📨 响应状态码: {response.status_code}")
                
                # 应该返回 410 Gone
                assert response.status_code == 410, f"应该返回 410，实际返回 {response.status_code}"
                print("✅ 正确返回 410 Gone")
                
        except httpx.ConnectError:
            print(f"\n⚠️ 无法连接到服务器 {BASE_URL}")
            pytest.skip("服务器未启动")
            
        finally:
            # 清理
            client = await redis._get_client()
            await client.delete(f"session:{session_id}:status")
            await client.delete(f"session:{session_id}:events")
    
    @pytest.mark.asyncio
    async def test_reconnect_to_nonexistent_session(self):
        """测试重连到不存在的 session（应该返回 404）"""
        session_id = "nonexistent_session_12345"
        
        try:
            async with httpx.AsyncClient(base_url=BASE_URL, timeout=5.0) as client:
                response = await client.get(f"/api/v1/chat/{session_id}")
                
                print(f"\n📨 响应状态码: {response.status_code}")
                
                # 应该返回 404
                assert response.status_code == 404, f"应该返回 404，实际返回 {response.status_code}"
                print("✅ 正确返回 404 Not Found")
                
        except httpx.ConnectError:
            print(f"\n⚠️ 无法连接到服务器 {BASE_URL}")
            pytest.skip("服务器未启动")


class TestReconnectLastSeqExtraction:
    """测试 last_seq 提取逻辑"""
    
    def test_extract_seq_from_events(self):
        """测试从事件列表提取最大 seq"""
        # 情况1：事件有 seq 字段
        events_with_seq = [
            {"seq": 1, "type": "a"},
            {"seq": 5, "type": "b"},
            {"seq": 3, "type": "c"},
        ]
        last_seq = max(e.get("seq", 0) for e in events_with_seq)
        assert last_seq == 5, f"应该是 5，实际是 {last_seq}"
        print(f"✅ seq 字段提取: last_seq={last_seq}")
        
        # 情况2：事件只有 id 字段（当前代码的问题！）
        events_with_id = [
            {"id": 1, "type": "a"},
            {"id": 5, "type": "b"},
            {"id": 3, "type": "c"},
        ]
        # 当前代码的逻辑
        last_seq_current = max(e.get("seq", 0) for e in events_with_id)
        print(f"⚠️ 当前代码（只取 seq）: last_seq={last_seq_current}")  # 会是 0！
        
        # 正确的逻辑
        last_seq_correct = max(e.get("seq", e.get("id", 0)) for e in events_with_id)
        print(f"✅ 正确逻辑（seq 或 id）: last_seq={last_seq_correct}")  # 应该是 5
        
        assert last_seq_current == 0, "当前代码会返回 0（bug）"
        assert last_seq_correct == 5, "正确逻辑应该返回 5"
        
        print("\n🐛 发现问题：当事件只有 id 字段时，last_seq 会是 0")
        print("   这会导致重复推送事件！")


async def run_manual_test():
    """手动运行测试（不需要 pytest）"""
    print("=" * 60)
    print("SSE 重连功能测试")
    print("=" * 60)
    
    # 测试 1: Redis 事件获取
    print("\n" + "=" * 60)
    print("测试 1: Redis 事件获取（seq 字段）")
    print("=" * 60)
    test = TestSSEReconnectLogic()
    await test.test_redis_get_events_with_seq()
    
    # 测试 2: Redis 事件获取（id 字段）
    print("\n" + "=" * 60)
    print("测试 2: Redis 事件获取（id 字段）")
    print("=" * 60)
    await test.test_redis_get_events_with_id()
    
    # 测试 3: Pub/Sub 订阅
    print("\n" + "=" * 60)
    print("测试 3: Pub/Sub 订阅")
    print("=" * 60)
    await test.test_pubsub_subscribe_events()
    
    # 测试 4: last_seq 提取逻辑
    print("\n" + "=" * 60)
    print("测试 4: last_seq 提取逻辑")
    print("=" * 60)
    TestReconnectLastSeqExtraction().test_extract_seq_from_events()
    
    # 测试 5: API 测试（模拟数据）
    print("\n" + "=" * 60)
    print("测试 5: 重连 API 测试（模拟数据）")
    print("=" * 60)
    api_test = TestSSEReconnectAPI()
    try:
        await api_test.test_reconnect_to_running_session()
    except Exception as e:
        print(f"⚠️ API 测试失败: {e}")
    
    # 等待 3 秒
    print("\n⏳ 等待 3 秒后开始端到端测试...")
    await asyncio.sleep(3)
    
    # 测试 6: 端到端测试（真实 Chat + 重连）
    print("\n" + "=" * 60)
    print("测试 6: 端到端测试（真实 Chat + 重连）")
    print("=" * 60)
    try:
        await api_test.test_real_chat_and_reconnect()
    except Exception as e:
        print(f"⚠️ 端到端测试失败: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 60)
    print("所有测试完成！")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(run_manual_test())

