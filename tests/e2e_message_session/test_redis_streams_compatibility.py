"""
Redis Streams 兼容性验证测试

验证本地 Redis 是否可以完全模拟 AWS MemoryDB 的 Redis Streams 功能。

该测试确保：
1. 所有 Redis Streams 命令正常工作
2. 消费者组机制完整可用
3. 消息持久化和 ACK 机制正常
4. 本地环境测试通过的代码可以直接部署到 AWS MemoryDB
"""

import asyncio
import json
import os
from typing import Dict, Any
from infra.cache.redis import get_redis_client
from infra.message_queue.streams import MessageQueueClient, get_message_queue_client

# 测试配置
CREATE_STREAM_KEY = "agent:message_create_stream"
UPDATE_STREAM_KEY = "agent:message_update_stream"
TEST_GROUP = "test_workers"
TEST_CONSUMER = "test_consumer"


class CompatibilityTestResults:
    """测试结果收集"""
    
    def __init__(self):
        self.passed = []
        self.failed = []
        self.warnings = []
    
    def add_pass(self, test_name: str, details: str = ""):
        self.passed.append((test_name, details))
        print(f"✅ {test_name}: {details}")
    
    def add_fail(self, test_name: str, error: str):
        self.failed.append((test_name, error))
        print(f"❌ {test_name}: {error}")
    
    def add_warning(self, test_name: str, message: str):
        self.warnings.append((test_name, message))
        print(f"⚠️  {test_name}: {message}")
    
    def print_summary(self):
        print("\n" + "="*60)
        print("📊 兼容性测试总结")
        print("="*60)
        print(f"✅ 通过: {len(self.passed)}")
        print(f"❌ 失败: {len(self.failed)}")
        print(f"⚠️  警告: {len(self.warnings)}")
        print("="*60)
        
        if self.passed:
            print("\n✅ 通过的测试:")
            for name, details in self.passed:
                print(f"   - {name}: {details}")
        
        if self.failed:
            print("\n❌ 失败的测试:")
            for name, error in self.failed:
                print(f"   - {name}: {error}")
        
        if self.warnings:
            print("\n⚠️  警告:")
            for name, message in self.warnings:
                print(f"   - {name}: {message}")
        
        print("\n" + "="*60)
        if not self.failed:
            print("🎉 所有测试通过！本地 Redis 完全兼容 MemoryDB Streams 功能")
        else:
            print("❌ 部分测试失败，请检查 Redis 版本和配置")
        print("="*60)


async def test_redis_version(redis_client, results: CompatibilityTestResults):
    """测试 Redis 版本是否支持 Streams"""
    print("\n1️⃣  测试 Redis 版本...")
    
    try:
        if hasattr(redis_client, '_client') and redis_client._client:
            info = await redis_client._client.info('server')
            version_str = info.get('redis_version', 'unknown')
            version_parts = version_str.split('.')
            major_version = int(version_parts[0])
            
            if major_version >= 5:
                results.add_pass(
                    "Redis 版本检查",
                    f"版本 {version_str} 支持 Streams (需要 >= 5.0)"
                )
                return True
            else:
                results.add_fail(
                    "Redis 版本检查",
                    f"版本 {version_str} 不支持 Streams (需要 >= 5.0)"
                )
                return False
    except Exception as e:
        results.add_fail("Redis 版本检查", str(e))
        return False


async def test_xadd(redis_client, mq_client, results: CompatibilityTestResults):
    """测试 XADD 命令"""
    print("\n2️⃣  测试 XADD（添加消息到 Stream）...")
    
    test_stream = "test:stream:xadd"
    
    try:
        # 清理测试数据
        if hasattr(redis_client, '_client') and redis_client._client:
            await redis_client._client.delete(test_stream)
        
        # 测试基本 XADD
        test_fields = {
            "message_id": "test_msg_1",
            "conversation_id": "test_conv_1",
            "role": "user",
            "content": '["Hello"]',
            "status": "processing",
            "metadata": {"key": "value"}
        }
        
        message_id = await mq_client.xadd(test_stream, test_fields)
        
        if message_id:
            results.add_pass("XADD 基本功能", f"成功添加消息，ID: {message_id}")
            
            # 验证消息存在
            if hasattr(redis_client, '_client') and redis_client._client:
                messages = await redis_client._client.xrange(test_stream, "-", "+", count=1)
                if messages:
                    results.add_pass("XADD 消息持久化", "消息已成功写入 Stream")
                else:
                    results.add_fail("XADD 消息持久化", "消息未找到")
        else:
            results.add_fail("XADD 基本功能", "返回 None，可能 Redis 未连接")
    
    except Exception as e:
        results.add_fail("XADD 测试", str(e))
    finally:
        # 清理
        if hasattr(redis_client, '_client') and redis_client._client:
            await redis_client._client.delete(test_stream)


async def test_xadd_maxlen(redis_client, mq_client, results: CompatibilityTestResults):
    """测试 XADD with maxlen（限制 Stream 长度）"""
    print("\n3️⃣  测试 XADD with maxlen（Stream 长度限制）...")
    
    test_stream = "test:stream:maxlen"
    
    try:
        # 清理
        if hasattr(redis_client, '_client') and redis_client._client:
            await redis_client._client.delete(test_stream)
        
        # 添加多条消息，限制最大长度为 3
        for i in range(5):
            await mq_client.xadd(
                test_stream,
                {"index": str(i), "data": f"message_{i}"},
                maxlen=3
            )
        
        # 验证只有最后 3 条消息
        if hasattr(redis_client, '_client') and redis_client._client:
            messages = await redis_client._client.xrange(test_stream, "-", "+")
            if len(messages) == 3:
                results.add_pass("XADD maxlen", "Stream 长度限制正常工作（精确裁剪）")
            else:
                # redis-py 默认使用近似裁剪（MAXLEN ~），消息数量可能略多
                results.add_warning(
                    "XADD maxlen",
                    f"近似裁剪（MAXLEN ~）结果为 {len(messages)} 条，属于正常现象"
                )
            
            # 额外验证：精确裁剪能力（MAXLEN =）
            await redis_client._client.delete(test_stream)
            for i in range(5):
                await redis_client._client.xadd(
                    test_stream,
                    {"index": str(i), "data": f"message_{i}"},
                    maxlen=3,
                    approximate=False
                )
            exact_messages = await redis_client._client.xrange(test_stream, "-", "+")
            if len(exact_messages) == 3:
                results.add_pass("XADD maxlen 精确裁剪", "Stream 精确裁剪能力正常")
            else:
                results.add_fail(
                    "XADD maxlen 精确裁剪",
                    f"期望 3 条消息，实际 {len(exact_messages)} 条"
                )
    
    except Exception as e:
        results.add_fail("XADD maxlen 测试", str(e))
    finally:
        # 清理
        if hasattr(redis_client, '_client') and redis_client._client:
            await redis_client._client.delete(test_stream)


async def test_xgroup_create(redis_client, mq_client, results: CompatibilityTestResults):
    """测试 XGROUP CREATE（创建消费者组）"""
    print("\n4️⃣  测试 XGROUP CREATE（创建消费者组）...")
    
    test_stream = "test:stream:group"
    
    try:
        # 先创建 Stream（添加一条消息）
        if hasattr(redis_client, '_client') and redis_client._client:
            await redis_client._client.delete(test_stream)
            await mq_client.xadd(test_stream, {"test": "data"})
        
        # 创建消费者组
        success = await mq_client.create_consumer_group(
            test_stream,
            TEST_GROUP,
            start_id="0"
        )
        
        if success:
            results.add_pass(
                "XGROUP CREATE",
                f"成功创建消费者组: {test_stream}/{TEST_GROUP}"
            )
            
            # 尝试再次创建（应该返回 True，因为已存在）
            success2 = await mq_client.create_consumer_group(
                test_stream,
                TEST_GROUP,
                start_id="0"
            )
            if success2:
                results.add_pass("XGROUP CREATE 幂等性", "已存在的消费者组不会报错")
        else:
            results.add_fail("XGROUP CREATE", "创建失败")
    
    except Exception as e:
        results.add_fail("XGROUP CREATE 测试", str(e))
    finally:
        # 清理
        if hasattr(redis_client, '_client') and redis_client._client:
            await redis_client._client.delete(test_stream)


async def test_xreadgroup(redis_client, mq_client, results: CompatibilityTestResults):
    """测试 XREADGROUP（消费者组读取）"""
    print("\n5️⃣  测试 XREADGROUP（消费者组读取消息）...")
    
    test_stream = "test:stream:readgroup"
    test_group = "test_read_group"
    test_consumer = "test_consumer_1"
    
    try:
        # 清理
        if hasattr(redis_client, '_client') and redis_client._client:
            await redis_client._client.delete(test_stream)
        
        # 添加测试消息
        message_id = await mq_client.xadd(test_stream, {"test": "data", "index": "1"})
        
        # 创建消费者组
        await mq_client.create_consumer_group(test_stream, test_group, start_id="0")
        
        # 使用消费者组读取消息
        if hasattr(redis_client, '_client') and redis_client._client:
            messages = await redis_client._client.xreadgroup(
                test_group,
                test_consumer,
                {test_stream: ">"},
                count=1,
                block=1000
            )
            
            if messages:
                stream_key, stream_messages = messages[0]
                if stream_messages:
                    msg_id, fields = stream_messages[0]
                    results.add_pass(
                        "XREADGROUP",
                        f"成功读取消息，ID: {msg_id.decode() if isinstance(msg_id, bytes) else msg_id}"
                    )
                else:
                    results.add_fail("XREADGROUP", "未读取到消息")
            else:
                results.add_fail("XREADGROUP", "未读取到消息")
    
    except Exception as e:
        results.add_fail("XREADGROUP 测试", str(e))
    finally:
        # 清理
        if hasattr(redis_client, '_client') and redis_client._client:
            await redis_client._client.delete(test_stream)


async def test_xack(redis_client, mq_client, results: CompatibilityTestResults):
    """测试 XACK（确认消息处理）"""
    print("\n6️⃣  测试 XACK（确认消息已处理）...")
    
    test_stream = "test:stream:ack"
    test_group = "test_ack_group"
    test_consumer = "test_consumer_2"
    
    try:
        # 清理
        if hasattr(redis_client, '_client') and redis_client._client:
            await redis_client._client.delete(test_stream)
        
        # 添加消息
        message_id = await mq_client.xadd(test_stream, {"test": "ack_test"})
        
        # 创建消费者组
        await mq_client.create_consumer_group(test_stream, test_group, start_id="0")
        
        # 读取消息
        if hasattr(redis_client, '_client') and redis_client._client:
            messages = await redis_client._client.xreadgroup(
                test_group,
                test_consumer,
                {test_stream: ">"},
                count=1,
                block=1000
            )
            
            if messages:
                stream_key, stream_messages = messages[0]
                if stream_messages:
                    msg_id, fields = stream_messages[0]
                    msg_id_str = msg_id.decode() if isinstance(msg_id, bytes) else str(msg_id)
                    
                    # ACK 消息
                    ack_count = await redis_client._client.xack(
                        test_stream,
                        test_group,
                        msg_id
                    )
                    
                    if ack_count == 1:
                        results.add_pass("XACK", f"成功确认消息: {msg_id_str}")
                        
                        # 验证消息不再在 pending 中
                        pending_info = await redis_client._client.xpending(
                            test_stream,
                            test_group
                        )
                        if pending_info and pending_info.get('pending', 0) == 0:
                            results.add_pass("XACK 效果验证", "消息已从 pending 列表移除")
                    else:
                        results.add_fail("XACK", f"ACK 失败，返回: {ack_count}")
                else:
                    results.add_fail("XACK", "未读取到消息进行 ACK")
            else:
                results.add_fail("XACK", "未读取到消息")
    
    except Exception as e:
        results.add_fail("XACK 测试", str(e))
    finally:
        # 清理
        if hasattr(redis_client, '_client') and redis_client._client:
            await redis_client._client.delete(test_stream)


async def test_xpending(redis_client, mq_client, results: CompatibilityTestResults):
    """测试 XPENDING（查询待处理消息）"""
    print("\n7️⃣  测试 XPENDING（查询待处理消息）...")
    
    test_stream = "test:stream:pending"
    test_group = "test_pending_group"
    test_consumer = "test_consumer_3"
    
    try:
        # 清理
        if hasattr(redis_client, '_client') and redis_client._client:
            await redis_client._client.delete(test_stream)
        
        # 添加消息
        await mq_client.xadd(test_stream, {"test": "pending_test"})
        
        # 创建消费者组
        await mq_client.create_consumer_group(test_stream, test_group, start_id="0")
        
        # 读取消息但不 ACK
        if hasattr(redis_client, '_client') and redis_client._client:
            await redis_client._client.xreadgroup(
                test_group,
                test_consumer,
                {test_stream: ">"},
                count=1,
                block=1000
            )
            
            # 查询 pending 消息
            pending_count = await mq_client.get_pending_count(test_stream, test_group)
            
            if pending_count >= 1:
                results.add_pass(
                    "XPENDING",
                    f"成功查询到 {pending_count} 条待处理消息"
                )
            else:
                results.add_fail("XPENDING", f"未查询到待处理消息（期望 >= 1）")
    
    except Exception as e:
        results.add_fail("XPENDING 测试", str(e))
    finally:
        # 清理
        if hasattr(redis_client, '_client') and redis_client._client:
            await redis_client._client.delete(test_stream)


async def test_message_queue_client(mq_client, results: CompatibilityTestResults):
    """测试 MessageQueueClient 的高级功能"""
    print("\n8️⃣  测试 MessageQueueClient 高级功能...")
    
    try:
        # 测试 push_create_event
        message_id = await mq_client.push_create_event(
            message_id="test_msg_1",
            conversation_id="test_conv_1",
            role="user",
            content='["Hello"]',
            status="processing",
            metadata={"key": "value"}
        )
        
        if message_id:
            results.add_pass("push_create_event", f"成功推送创建事件，ID: {message_id}")
        else:
            results.add_fail("push_create_event", "返回 None")
        
        # 测试 push_update_event
        update_id = await mq_client.push_update_event(
            message_id="test_msg_1",
            content='["Hello", "World"]',
            status="completed",
            metadata={"key": "updated_value"}
        )
        
        if update_id:
            results.add_pass("push_update_event", f"成功推送更新事件，ID: {update_id}")
        else:
            results.add_fail("push_update_event", "返回 None")
    
    except Exception as e:
        results.add_fail("MessageQueueClient 测试", str(e))


async def test_full_workflow(redis_client, mq_client, results: CompatibilityTestResults):
    """测试完整工作流程（模拟实际使用场景）"""
    print("\n9️⃣  测试完整工作流程...")
    
    test_stream = "test:stream:workflow"
    test_group = "test_workflow_group"
    test_consumer = "test_workflow_consumer"
    
    try:
        # 清理
        if hasattr(redis_client, '_client') and redis_client._client:
            await redis_client._client.delete(test_stream)
        
        # 1. 创建消费者组
        await mq_client.create_consumer_group(test_stream, test_group, start_id="0")
        
        # 2. 推送多条消息
        message_ids = []
        for i in range(3):
            msg_id = await mq_client.xadd(
                test_stream,
                {"index": str(i), "data": f"message_{i}"}
            )
            message_ids.append(msg_id)
        
        results.add_pass("工作流程-推送", f"成功推送 {len(message_ids)} 条消息")
        
        # 3. 消费者读取消息
        if hasattr(redis_client, '_client') and redis_client._client:
            messages = await redis_client._client.xreadgroup(
                test_group,
                test_consumer,
                {test_stream: ">"},
                count=10,
                block=1000
            )
            
            if messages:
                stream_key, stream_messages = messages[0]
                if len(stream_messages) == 3:
                    results.add_pass("工作流程-读取", "成功读取所有消息")
                    
                    # 4. ACK 所有消息
                    ack_count = 0
                    for msg_id, fields in stream_messages:
                        acked = await redis_client._client.xack(
                            test_stream,
                            test_group,
                            msg_id
                        )
                        ack_count += acked
                    
                    if ack_count == 3:
                        results.add_pass("工作流程-ACK", "成功确认所有消息")
                    else:
                        results.add_fail("工作流程-ACK", f"只确认了 {ack_count}/3 条消息")
                else:
                    results.add_fail(
                        "工作流程-读取",
                        f"期望 3 条消息，实际 {len(stream_messages)} 条"
                    )
            else:
                results.add_fail("工作流程-读取", "未读取到消息")
    
    except Exception as e:
        results.add_fail("完整工作流程测试", str(e))
    finally:
        # 清理
        if hasattr(redis_client, '_client') and redis_client._client:
            await redis_client._client.delete(test_stream)


async def main():
    """主测试函数"""
    print("="*60)
    print("🔍 Redis Streams 兼容性验证测试")
    print("="*60)
    print("\n测试目标：验证本地 Redis 是否可以完全模拟 AWS MemoryDB 的 Streams 功能")
    print("\n环境信息：")
    deployment_env = os.getenv("DEPLOYMENT_ENV", "local")
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    print(f"  部署环境: {deployment_env}")
    print(f"  Redis URL: {redis_url[:50]}...")
    print("="*60)
    
    results = CompatibilityTestResults()
    
    # 初始化 Redis 客户端
    redis_client = await get_redis_client()
    
    if not redis_client.is_connected:
        results.add_fail("Redis 连接", "无法连接到 Redis，请检查配置")
        results.print_summary()
        return
    
    results.add_pass("Redis 连接", "成功连接到 Redis")
    
    # 获取消息队列客户端
    mq_client = await get_message_queue_client()
    
    # 运行所有测试
    await test_redis_version(redis_client, results)
    await test_xadd(redis_client, mq_client, results)
    await test_xadd_maxlen(redis_client, mq_client, results)
    await test_xgroup_create(redis_client, mq_client, results)
    await test_xreadgroup(redis_client, mq_client, results)
    await test_xack(redis_client, mq_client, results)
    await test_xpending(redis_client, mq_client, results)
    await test_message_queue_client(mq_client, results)
    await test_full_workflow(redis_client, mq_client, results)
    
    # 打印总结
    results.print_summary()
    
    # 关闭连接
    await redis_client.close()


if __name__ == "__main__":
    # 确保使用测试配置
    if not os.getenv("DEPLOYMENT_ENV"):
        os.environ["DEPLOYMENT_ENV"] = "local"
    
    asyncio.run(main())
