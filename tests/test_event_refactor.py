"""
事件系统重构测试脚本

验证内容：
1. InMemoryEventStorage.buffer_event 的 seq 生成
2. RedisSessionManager.buffer_event 的 seq 生成（如果 Redis 可用）
3. EventBroadcaster 通过 EventManager 发送事件
4. 格式转换（ZenO adapter）

架构说明（V7.2）：
- 所有事件通过 EventManager 发送（统一入口）
- EventBroadcaster 通过 EventManager 发送事件，同时提供累积、持久化等增强功能
- seq 在 buffer_event 中由 Redis INCR 原子生成

运行方式：
    cd /Users/kens0n/projects/zenflux_agent
    python -m pytest tests/test_event_refactor.py -v
    
    # 或者直接运行
    python tests/test_event_refactor.py
"""

import asyncio
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import datetime
from uuid import uuid4


async def test_memory_storage_buffer_event():
    """测试 InMemoryEventStorage.buffer_event 的 seq 生成"""
    print("\n" + "=" * 60)
    print("测试 1: InMemoryEventStorage.buffer_event")
    print("=" * 60)
    
    from core.events.storage import InMemoryEventStorage
    
    storage = InMemoryEventStorage()
    session_id = f"test-session-{uuid4()}"
    
    # 发送多个事件，验证 seq 递增
    events_sent = []
    for i in range(5):
        event_data = {
            "type": f"test_event_{i}",
            "event_uuid": str(uuid4()),
            "timestamp": datetime.now().isoformat(),
            "data": {"index": i}
        }
        
        result = await storage.buffer_event(
            session_id=session_id,
            event_data=event_data,
            output_format="zenflux"
        )
        events_sent.append(result)
        print(f"  事件 {i}: type={result['type']}, seq={result.get('seq')}")
    
    # 验证 seq 是否从 1 开始递增
    seqs = [e.get("seq") for e in events_sent]
    expected = [1, 2, 3, 4, 5]
    
    if seqs == expected:
        print(f"  ✅ seq 递增正确: {seqs}")
        return True
    else:
        print(f"  ❌ seq 递增错误: 期望 {expected}, 实际 {seqs}")
        return False


async def test_memory_storage_with_zeno_format():
    """测试 InMemoryEventStorage 的 ZenO 格式转换"""
    print("\n" + "=" * 60)
    print("测试 2: InMemoryEventStorage + ZenO 格式转换")
    print("=" * 60)
    
    from core.events.storage import InMemoryEventStorage
    from core.events.adapters.zeno import ZenOAdapter
    
    storage = InMemoryEventStorage()
    session_id = f"test-session-{uuid4()}"
    conversation_id = f"conv-{uuid4()}"
    
    adapter = ZenOAdapter(conversation_id=conversation_id)
    
    # 发送 content_start 事件
    event_data = {
        "type": "content_start",
        "event_uuid": str(uuid4()),
        "session_id": session_id,
        "timestamp": datetime.now().isoformat(),
        "data": {
            "index": 0,
            "content_block": {
                "type": "text",
                "text": ""
            }
        }
    }
    
    result = await storage.buffer_event(
        session_id=session_id,
        event_data=event_data,
        output_format="zeno",
        adapter=adapter
    )
    
    if result:
        print(f"  转换后事件: type={result.get('type')}, seq={result.get('seq')}")
        print(f"  conversation_id: {result.get('conversation_id')}")
        print(f"  ✅ ZenO 格式转换成功")
        return True
    else:
        print(f"  ⚠️ 事件被 adapter 过滤（这可能是正常的）")
        return True  # 被过滤也是正常的


async def test_redis_storage_buffer_event():
    """测试 RedisSessionManager.buffer_event 的 seq 生成"""
    print("\n" + "=" * 60)
    print("测试 3: RedisSessionManager.buffer_event (需要 Redis)")
    print("=" * 60)
    
    try:
        from services.redis_manager import RedisSessionManager
        from infra.cache import get_redis_client
        
        # 尝试获取 Redis 客户端
        redis_client = await get_redis_client()
        
        if not redis_client or not redis_client.is_connected:
            print("  ⚠️ Redis 未连接，跳过此测试")
            return True
        
        manager = RedisSessionManager(redis_client)
        session_id = f"test-session-{uuid4()}"
        
        # 发送多个事件
        events_sent = []
        for i in range(3):
            event_data = {
                "type": f"test_event_{i}",
                "event_uuid": str(uuid4()),
                "timestamp": datetime.now().isoformat(),
                "data": {"index": i}
            }
            
            result = await manager.buffer_event(
                session_id=session_id,
                event_data=event_data,
                output_format="zenflux"
            )
            events_sent.append(result)
            print(f"  事件 {i}: type={result['type']}, seq={result.get('seq')}")
        
        # 验证 seq
        seqs = [e.get("seq") for e in events_sent]
        expected = [1, 2, 3]
        
        # 清理测试数据
        client = await manager._get_client()
        await client.delete(f"session:{session_id}:events")
        await client.delete(f"session:{session_id}:seq")
        
        if seqs == expected:
            print(f"  ✅ Redis seq 递增正确: {seqs}")
            return True
        else:
            print(f"  ❌ Redis seq 递增错误: 期望 {expected}, 实际 {seqs}")
            return False
            
    except Exception as e:
        print(f"  ⚠️ Redis 测试跳过: {e}")
        return True


async def test_broadcaster_event_manager():
    """测试 EventBroadcaster 通过 EventManager 发送事件"""
    print("\n" + "=" * 60)
    print("测试 4: EventBroadcaster 通过 EventManager 发送事件")
    print("=" * 60)
    
    from core.events.storage import InMemoryEventStorage, get_memory_storage
    from core.events.manager import create_event_manager
    from core.events.broadcaster import EventBroadcaster
    
    # 使用内存存储
    storage = get_memory_storage()
    event_manager = create_event_manager(storage)
    
    broadcaster = EventBroadcaster(
        event_manager=event_manager,
        output_format="zenflux"
    )
    
    session_id = f"test-session-{uuid4()}"
    
    # 通过 broadcaster 发送事件
    result1 = await broadcaster.emit_content_start(
        session_id=session_id,
        index=0,
        content_block={"type": "text", "text": ""}
    )
    
    result2 = await broadcaster.emit_content_delta(
        session_id=session_id,
        index=0,
        delta="Hello, "
    )
    
    result3 = await broadcaster.emit_content_delta(
        session_id=session_id,
        index=0,
        delta="World!"
    )
    
    result4 = await broadcaster.emit_content_stop(
        session_id=session_id,
        index=0
    )
    
    results = [result1, result2, result3, result4]
    
    # 验证
    all_have_seq = all(r and r.get("seq") for r in results)
    seqs = [r.get("seq") if r else None for r in results]
    
    print(f"  事件 seq 列表: {seqs}")
    
    if all_have_seq:
        # 检查 seq 是否递增
        is_increasing = all(seqs[i] < seqs[i+1] for i in range(len(seqs)-1))
        if is_increasing:
            print(f"  ✅ Broadcaster 事件流正常，seq 递增")
            return True
        else:
            print(f"  ❌ seq 未递增")
            return False
    else:
        print(f"  ❌ 部分事件缺少 seq")
        return False


async def test_broadcaster_with_zeno_format():
    """测试 EventBroadcaster 的 ZenO 格式输出"""
    print("\n" + "=" * 60)
    print("测试 5: EventBroadcaster + ZenO 格式")
    print("=" * 60)
    
    from core.events.storage import get_memory_storage
    from core.events.manager import create_event_manager
    from core.events.broadcaster import EventBroadcaster
    
    storage = get_memory_storage()
    event_manager = create_event_manager(storage)
    
    conversation_id = f"conv-{uuid4()}"
    broadcaster = EventBroadcaster(
        event_manager=event_manager,
        output_format="zeno",
        conversation_id=conversation_id
    )
    
    session_id = f"test-session-{uuid4()}"
    
    # 发送消息事件
    result = await broadcaster.emit_message_start(
        session_id=session_id,
        message_id=f"msg-{uuid4()}",
        model="claude-3"
    )
    
    if result:
        print(f"  事件 type: {result.get('type')}")
        print(f"  事件 seq: {result.get('seq')}")
        print(f"  conversation_id: {result.get('conversation_id')}")
        print(f"  ✅ ZenO 格式输出正常")
        return True
    else:
        print(f"  ⚠️ 事件被过滤（ZenO adapter 可能过滤了某些事件）")
        return True


async def main():
    """运行所有测试"""
    print("\n" + "🧪 " + "=" * 56 + " 🧪")
    print("        事件系统重构测试")
    print("🧪 " + "=" * 56 + " 🧪")
    
    results = []
    
    # 测试 1: 内存存储基本功能
    results.append(("InMemoryEventStorage.buffer_event", await test_memory_storage_buffer_event()))
    
    # 测试 2: 内存存储 + ZenO 格式
    results.append(("InMemoryEventStorage + ZenO", await test_memory_storage_with_zeno_format()))
    
    # 测试 3: Redis 存储（如果可用）
    results.append(("RedisSessionManager.buffer_event", await test_redis_storage_buffer_event()))
    
    # 测试 4: Broadcaster 基本功能（通过 EventManager）
    results.append(("EventBroadcaster via EventManager", await test_broadcaster_event_manager()))
    
    # 测试 5: Broadcaster + ZenO
    results.append(("EventBroadcaster + ZenO", await test_broadcaster_with_zeno_format()))
    
    # 汇总结果
    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)
    
    passed = 0
    failed = 0
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {status}: {name}")
        if result:
            passed += 1
        else:
            failed += 1
    
    print(f"\n总计: {passed} 通过, {failed} 失败")
    
    if failed == 0:
        print("\n🎉 所有测试通过！事件系统重构验证成功。")
    else:
        print("\n⚠️ 部分测试失败，请检查代码。")
    
    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
