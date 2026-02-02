"""
Schema IO 读写测试

测试所有表的 CRUD 操作和 Redis Streams 读写。
"""

import os
import asyncio
import sys
import json
from pathlib import Path

import pytest

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

RUN_E2E_DB_TESTS = os.getenv("RUN_E2E_DB_TESTS", "false").lower() == "true"
if not RUN_E2E_DB_TESTS:
    pytest.skip("未启用 RUN_E2E_DB_TESTS，跳过数据库/Redis 端到端测试", allow_module_level=True)

# 导入测试配置（自动设置环境变量）
# 注意：必须在导入其他模块之前设置环境变量
import importlib.util
config_path = Path(__file__).parent / "config.py"
spec = importlib.util.spec_from_file_location("config", config_path)
config = importlib.util.module_from_spec(spec)
spec.loader.exec_module(config)
DeploymentConfig = config.DeploymentConfig

from logger import get_logger
from infra.database.engine import AsyncSessionLocal
from infra.database.crud import (
    get_or_create_user,
    create_conversation,
    get_conversation,
    update_conversation,
    create_message,
    get_message,
    update_message,
    list_messages,
    delete_conversation,
)
from infra.cache.redis import get_redis_client
from infra.message_queue.streams import MessageQueueClient, get_message_queue_client
from .fixtures import (
    create_mock_user_data,
    create_mock_conversation_data,
    create_mock_message_data,
    create_mock_placeholder_message_data,
    create_mock_completed_message_data,
    create_mock_content_blocks,
    create_mock_usage_data,
    cleanup_test_data,
    is_test_data,
)

logger = get_logger("test_schema_io")


async def test_user_crud():
    """测试 User 表 CRUD 操作"""
    print("\n" + "=" * 60)
    print("👤 User 表 CRUD 测试")
    print("=" * 60)
    
    user_data = create_mock_user_data()
    user_id = user_data["id"]
    
    try:
        async with AsyncSessionLocal() as session:
            # CREATE
            print("\n1️⃣ 测试 CREATE...")
            user = await get_or_create_user(
                session=session,
                user_id=user_id,
                username=user_data["username"]
            )
            assert user.id == user_id, "用户 ID 不匹配"
            assert user.username == user_data["username"], "用户名不匹配"
            print(f"   ✅ 用户创建成功: id={user.id}, username={user.username}")
            
            # READ
            print("\n2️⃣ 测试 READ...")
            from infra.database.crud.base import get_by_id
            from infra.database.models import User
            user_read = await get_by_id(session, User, user_id)
            assert user_read is not None, "用户不存在"
            assert user_read.id == user_id, "读取的用户 ID 不匹配"
            print(f"   ✅ 用户读取成功: id={user_read.id}")
            
            # UPDATE
            print("\n3️⃣ 测试 UPDATE...")
            new_email = f"updated_{user_id}@example.com"
            user_read.email = new_email
            await session.commit()
            await session.refresh(user_read)
            assert user_read.email == new_email, "邮箱更新失败"
            print(f"   ✅ 用户更新成功: email={user_read.email}")
            
            print("\n✅ User 表 CRUD 测试通过")
            return user_id, True
            
    except Exception as e:
        print(f"\n❌ User 表 CRUD 测试失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return user_id, False


async def test_conversation_crud(user_id: str):
    """测试 Conversation 表 CRUD 操作"""
    print("\n" + "=" * 60)
    print("💬 Conversation 表 CRUD 测试")
    print("=" * 60)
    
    conv_data = create_mock_conversation_data(user_id=user_id)
    conv_id = conv_data["id"]
    
    try:
        async with AsyncSessionLocal() as session:
            # CREATE
            print("\n1️⃣ 测试 CREATE...")
            conv = await create_conversation(
                session=session,
                user_id=user_id,
                title=conv_data["title"],
                metadata=conv_data["metadata"]
            )
            # 使用我们生成的 ID
            conv.id = conv_id
            await session.commit()
            await session.refresh(conv)
            assert conv.id == conv_id, "对话 ID 不匹配"
            print(f"   ✅ 对话创建成功: id={conv.id}, title={conv.title}")
            
            # READ
            print("\n2️⃣ 测试 READ...")
            conv_read = await get_conversation(session, conv_id)
            assert conv_read is not None, "对话不存在"
            assert conv_read.id == conv_id, "读取的对话 ID 不匹配"
            print(f"   ✅ 对话读取成功: id={conv_read.id}")
            
            # UPDATE
            print("\n3️⃣ 测试 UPDATE...")
            new_title = "更新后的标题"
            updated_conv = await update_conversation(
                session=session,
                conversation_id=conv_id,
                title=new_title
            )
            assert updated_conv.title == new_title, "标题更新失败"
            print(f"   ✅ 对话更新成功: title={updated_conv.title}")
            
            # 测试 metadata 更新
            new_metadata = {"test_key": "test_value", "nested": {"key": "value"}}
            updated_conv = await update_conversation(
                session=session,
                conversation_id=conv_id,
                metadata=new_metadata
            )
            assert updated_conv.extra_data.get("test_key") == "test_value", "metadata 更新失败"
            print(f"   ✅ metadata 更新成功")
            
            print("\n✅ Conversation 表 CRUD 测试通过")
            return conv_id, True
            
    except Exception as e:
        print(f"\n❌ Conversation 表 CRUD 测试失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return conv_id, False


async def test_message_crud(conversation_id: str):
    """测试 Message 表 CRUD 操作"""
    print("\n" + "=" * 60)
    print("📨 Message 表 CRUD 测试")
    print("=" * 60)
    
    # 测试用户消息
    user_msg_data = create_mock_message_data(
        conversation_id=conversation_id,
        role="user"
    )
    user_msg_id = user_msg_data["id"]
    
    # 测试占位消息
    placeholder_msg_data = create_mock_placeholder_message_data(
        conversation_id=conversation_id
    )
    placeholder_msg_id = placeholder_msg_data["id"]
    
    try:
        async with AsyncSessionLocal() as session:
            # CREATE - 用户消息
            print("\n1️⃣ 测试 CREATE (用户消息)...")
            user_msg = await create_message(
                session=session,
                conversation_id=conversation_id,
                role="user",
                content=user_msg_data["content"],
                message_id=user_msg_id,
                metadata=user_msg_data["metadata"]
            )
            assert user_msg.id == user_msg_id, "用户消息 ID 不匹配"
            print(f"   ✅ 用户消息创建成功: id={user_msg.id}")
            
            # CREATE - 占位消息
            print("\n2️⃣ 测试 CREATE (占位消息)...")
            placeholder_msg = await create_message(
                session=session,
                conversation_id=conversation_id,
                role="assistant",
                content=placeholder_msg_data["content"],
                message_id=placeholder_msg_id,
                status=placeholder_msg_data["status"],
                metadata=placeholder_msg_data["metadata"]
            )
            assert placeholder_msg.id == placeholder_msg_id, "占位消息 ID 不匹配"
            assert placeholder_msg.status == "streaming", "占位消息状态不正确"
            assert placeholder_msg.extra_data.get("stream", {}).get("phase") == "placeholder", "占位消息 phase 不正确"
            print(f"   ✅ 占位消息创建成功: id={placeholder_msg.id}, status={placeholder_msg.status}")
            
            # READ
            print("\n3️⃣ 测试 READ...")
            msg_read = await get_message(session, placeholder_msg_id)
            assert msg_read is not None, "消息不存在"
            assert msg_read.id == placeholder_msg_id, "读取的消息 ID 不匹配"
            print(f"   ✅ 消息读取成功: id={msg_read.id}")
            
            # UPDATE - 更新为完成状态
            print("\n4️⃣ 测试 UPDATE (状态流转)...")
            content_blocks = create_mock_content_blocks()
            content_json = json.dumps(content_blocks, ensure_ascii=False)
            usage_data = create_mock_usage_data()
            
            # 测试深度合并 metadata
            update_metadata = {
                "stream": {
                    "phase": "final",
                    "chunk_count": len(content_blocks)
                },
                "usage": usage_data
            }
            
            updated_msg = await update_message(
                session=session,
                message_id=placeholder_msg_id,
                content=content_json,
                status="completed",
                metadata=update_metadata
            )
            assert updated_msg.status == "completed", "状态更新失败"
            assert updated_msg.extra_data.get("stream", {}).get("phase") == "final", "phase 更新失败"
            assert "usage" in updated_msg.extra_data, "usage 未合并"
            assert updated_msg.extra_data["usage"]["total_tokens"] == 1921, "usage 数据不正确"
            print(f"   ✅ 消息更新成功: status={updated_msg.status}, phase={updated_msg.extra_data.get('stream', {}).get('phase')}")
            
            # 测试 content blocks 解析
            print("\n5️⃣ 测试 content blocks 解析...")
            blocks = updated_msg.content_blocks
            assert len(blocks) == 4, f"content blocks 数量不正确: {len(blocks)}"
            assert blocks[0]["type"] == "thinking", "第一个 block 类型不正确"
            assert blocks[1]["type"] == "text", "第二个 block 类型不正确"
            print(f"   ✅ content blocks 解析成功: {len(blocks)} 个 blocks")
            
            # LIST
            print("\n6️⃣ 测试 LIST...")
            messages = await list_messages(
                session=session,
                conversation_id=conversation_id,
                limit=10
            )
            assert len(messages) >= 2, f"消息列表数量不正确: {len(messages)}"
            print(f"   ✅ 消息列表查询成功: {len(messages)} 条消息")
            
            print("\n✅ Message 表 CRUD 测试通过")
            return [user_msg_id, placeholder_msg_id], True
            
    except Exception as e:
        print(f"\n❌ Message 表 CRUD 测试失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return [user_msg_id, placeholder_msg_id], False


async def test_redis_streams():
    """测试 Redis Streams 操作"""
    print("\n" + "=" * 60)
    print("🔴 Redis Streams 测试")
    print("=" * 60)
    
    try:
        mq_client = await get_message_queue_client()
        redis = await get_redis_client()
        
        if not redis.is_connected:
            print("   ⚠️ Redis 未连接，跳过 Streams 测试")
            return False
        
        # 1. 测试创建事件推送
        print("\n1️⃣ 测试推送创建事件...")
        test_message_id = f"test_msg_{asyncio.get_event_loop().time()}"
        test_conv_id = f"test_conv_{asyncio.get_event_loop().time()}"
        
        stream_id = await mq_client.push_create_event(
            message_id=test_message_id,
            conversation_id=test_conv_id,
            role="assistant",
            content="[]",
            status="streaming",
            metadata={
                "schema_version": "message_meta_v1",
                "stream": {"phase": "placeholder", "chunk_count": 0}
            }
        )
        
        if stream_id:
            print(f"   ✅ 创建事件推送成功: stream_id={stream_id}")
        else:
            print("   ❌ 创建事件推送失败")
            return False
        
        # 2. 测试更新事件推送
        print("\n2️⃣ 测试推送更新事件...")
        content_blocks = create_mock_content_blocks()
        content_json = json.dumps(content_blocks, ensure_ascii=False)
        
        update_stream_id = await mq_client.push_update_event(
            message_id=test_message_id,
            content=content_json,
            status="completed",
            metadata={
                "stream": {"phase": "final", "chunk_count": len(content_blocks)}
            }
        )
        
        if update_stream_id:
            print(f"   ✅ 更新事件推送成功: stream_id={update_stream_id}")
        else:
            print("   ❌ 更新事件推送失败")
            return False
        
        # 3. 测试消费者组创建
        print("\n3️⃣ 测试消费者组创建...")
        group_created = await mq_client.create_consumer_group(
            mq_client.CREATE_STREAM_KEY,
            "test_consumer_group"
        )
        if group_created:
            print("   ✅ 消费者组创建成功")
        else:
            print("   ⚠️ 消费者组可能已存在（这是正常的）")
        
        # 4. 测试读取消息
        print("\n4️⃣ 测试读取消息...")
        if hasattr(redis, '_client') and redis._client:
            messages = await redis._client.xread(
                {mq_client.CREATE_STREAM_KEY: "0"},
                count=1
            )
            if messages:
                print(f"   ✅ 读取消息成功: {len(messages)} 条")
            else:
                print("   ⚠️ 未读取到消息（可能已被消费）")
        
        print("\n✅ Redis Streams 测试通过")
        return True
        
    except Exception as e:
        print(f"\n❌ Redis Streams 测试失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """主测试函数"""
    print("\n" + "=" * 60)
    print("🚀 开始 Schema IO 读写测试")
    print("=" * 60)
    
    results = []
    test_user_id = None
    test_conv_id = None
    test_message_ids = []
    
    try:
        # 1. User CRUD
        user_id, user_result = await test_user_crud()
        test_user_id = user_id
        results.append(("User CRUD", user_result))
        
        if not user_result:
            print("\n⚠️ User CRUD 失败，跳过后续测试")
            return 1
        
        # 2. Conversation CRUD
        conv_id, conv_result = await test_conversation_crud(test_user_id)
        test_conv_id = conv_id
        results.append(("Conversation CRUD", conv_result))
        
        if not conv_result:
            print("\n⚠️ Conversation CRUD 失败，跳过后续测试")
            return 1
        
        # 3. Message CRUD
        msg_ids, msg_result = await test_message_crud(test_conv_id)
        test_message_ids = msg_ids
        results.append(("Message CRUD", msg_result))
        
        # 4. Redis Streams
        streams_result = await test_redis_streams()
        results.append(("Redis Streams", streams_result))
        
    finally:
        # 清理测试数据
        print("\n" + "=" * 60)
        print("🧹 清理测试数据")
        print("=" * 60)
        
        try:
            async with AsyncSessionLocal() as session:
                if test_conv_id:
                    await cleanup_test_data(session, conversation_id=test_conv_id)
                if test_user_id:
                    await cleanup_test_data(session, user_id=test_user_id)
        except Exception as e:
            print(f"⚠️ 清理测试数据失败: {str(e)}")
    
    # 汇总结果
    print("\n" + "=" * 60)
    print("📊 测试结果汇总")
    print("=" * 60)
    
    for name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{name:30s} {status}")
    
    all_passed = all(result for _, result in results)
    
    if all_passed:
        print("\n🎉 所有 Schema IO 测试通过！")
        return 0
    else:
        print("\n⚠️ 部分测试失败")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
