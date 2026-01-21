"""
端到端流程测试

按照两阶段持久化流程图进行完整流程测试。
"""

import os
import asyncio
import sys
import json
import time
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
TestConfig = config.TestConfig

from logger import get_logger
from infra.database.engine import AsyncSessionLocal
from infra.database.crud import (
    get_or_create_user,
    create_conversation,
    get_conversation,
    create_message,
    get_message,
    update_message,
    list_messages,
    delete_conversation,
)
from infra.cache.redis import get_redis_client
from infra.message_queue.streams import MessageQueueClient, get_message_queue_client
from infra.message_queue.workers import InsertWorker, UpdateWorker
from .fixtures import (
    create_mock_user_data,
    create_mock_conversation_data,
    create_mock_message_data,
    create_mock_placeholder_message_data,
    create_mock_completed_message_data,
    create_mock_content_blocks,
    create_mock_usage_data,
    cleanup_test_data,
    generate_test_message_id,
)

logger = get_logger("test_e2e_flow")


async def simulate_phase1_placeholder_creation(
    session,
    conversation_id: str,
    session_id: str,
    model: str = "claude-3-5-sonnet"
):
    """
    模拟阶段一：占位消息创建
    
    按照流程图：
    1. API Service → SessionManager: 创建占位消息
    2. SessionManager → message_create_stream: 推送占位消息
    3. InsertWorker 消费并写入 PostgreSQL
    """
    print("\n" + "=" * 60)
    print("📝 阶段一：占位消息创建")
    print("=" * 60)
    
    assistant_message_id = generate_test_message_id()
    
    # 1. 创建占位消息（模拟 SessionManager）
    print("\n1️⃣ 创建占位消息（模拟 SessionManager）...")
    placeholder_metadata = {
        "schema_version": "message_meta_v1",
        "session_id": session_id,
        "model": model,
        "stream": {
            "phase": "placeholder",
            "chunk_count": 0
        }
    }
    
    placeholder_msg = await create_message(
        session=session,
        conversation_id=conversation_id,
        role="assistant",
        content="[]",  # 空数组
        message_id=assistant_message_id,
        status="streaming",
        metadata=placeholder_metadata
    )
    
    assert placeholder_msg.id == assistant_message_id, "占位消息 ID 不匹配"
    assert placeholder_msg.status == "streaming", "占位消息状态不正确"
    assert placeholder_msg.extra_data.get("stream", {}).get("phase") == "placeholder", "占位消息 phase 不正确"
    print(f"   ✅ 占位消息创建成功: id={assistant_message_id}, status={placeholder_msg.status}")
    
    # 2. 推送到 Redis Streams（模拟 SessionManager）
    print("\n2️⃣ 推送到 Redis Streams（模拟 SessionManager）...")
    mq_client = await get_message_queue_client()
    stream_id = await mq_client.push_create_event(
        message_id=assistant_message_id,
        conversation_id=conversation_id,
        role="assistant",
        content="[]",
        status="streaming",
        metadata=placeholder_metadata
    )
    
    if stream_id:
        print(f"   ✅ 占位消息已推送到 Stream: stream_id={stream_id}")
    else:
        print("   ⚠️ 推送到 Stream 失败（可能 Redis 未连接，继续测试）")
    
    # 3. 验证占位消息在数据库中
    print("\n3️⃣ 验证占位消息在数据库中...")
    db_msg = await get_message(session, assistant_message_id)
    assert db_msg is not None, "占位消息在数据库中不存在"
    assert db_msg.status == "streaming", "数据库中的状态不正确"
    assert db_msg.extra_data.get("stream", {}).get("phase") == "placeholder", "数据库中的 phase 不正确"
    print(f"   ✅ 占位消息验证成功: id={db_msg.id}, status={db_msg.status}")
    
    return assistant_message_id


async def simulate_streaming_content():
    """
    模拟流式传输
    
    按照流程图：
    - LLM → API Service: 返回 chunk
    - API Service → User: 发送 chunk
    - 累积 content blocks 到内存
    """
    print("\n" + "=" * 60)
    print("🌊 流式传输模拟")
    print("=" * 60)
    
    # 模拟多个 content chunks
    chunks = [
        {"type": "thinking", "thinking": "让我思考一下...", "signature": f"sig_{int(time.time())}"},
        {"type": "text", "text": "根据您的问题，"},
        {"type": "text", "text": "我为您提供以下解答：\n\n"},
        {"type": "text", "text": "1. 首先，我们需要..."},
        {"type": "tool_use", "id": f"toolu_{int(time.time())}", "name": "web_search", "input": {"query": "test"}},
        {"type": "tool_result", "tool_use_id": f"toolu_{int(time.time())}", "content": "搜索结果...", "is_error": False},
        {"type": "text", "text": "\n2. 其次，我们应该..."},
        {"type": "text", "text": "\n3. 最后，建议您..."}
    ]
    
    print(f"\n1️⃣ 模拟 {len(chunks)} 个 content chunks...")
    for i, chunk in enumerate(chunks, 1):
        print(f"   📦 Chunk {i}/{len(chunks)}: type={chunk.get('type')}")
        await asyncio.sleep(0.1)  # 模拟流式延迟
    
    # 累积 content blocks
    print("\n2️⃣ 累积 content blocks...")
    accumulated_blocks = []
    for chunk in chunks:
        if chunk["type"] == "text" and accumulated_blocks and accumulated_blocks[-1].get("type") == "text":
            # 合并连续的 text blocks
            accumulated_blocks[-1]["text"] += chunk["text"]
        else:
            accumulated_blocks.append(chunk)
    
    print(f"   ✅ 累积完成: {len(accumulated_blocks)} 个 blocks")
    for i, block in enumerate(accumulated_blocks, 1):
        print(f"      Block {i}: type={block.get('type')}")
    
    return accumulated_blocks


async def simulate_phase2_final_update(
    session,
    conversation_id: str,
    message_id: str,
    content_blocks: list,
    session_id: str,
    model: str = "claude-3-5-sonnet"
):
    """
    模拟阶段二：最终消息更新
    
    按照流程图：
    1. API Service → SessionManager: 更新内存消息（content, status='completed'）
    2. SessionManager → message_update_stream: 推送更新事件
    3. UpdateWorker 消费并更新 PostgreSQL
    """
    print("\n" + "=" * 60)
    print("✅ 阶段二：最终消息更新")
    print("=" * 60)
    
    # 1. 更新消息（模拟 SessionManager）
    print("\n1️⃣ 更新消息（模拟 SessionManager）...")
    content_json = json.dumps(content_blocks, ensure_ascii=False)
    usage_data = create_mock_usage_data()
    
    update_metadata = {
        "stream": {
            "phase": "final",
            "chunk_count": len(content_blocks)
        },
        "usage": usage_data
    }
    
    updated_msg = await update_message(
        session=session,
        message_id=message_id,
        content=content_json,
        status="completed",
        metadata=update_metadata
    )
    
    assert updated_msg.status == "completed", "状态更新失败"
    assert updated_msg.extra_data.get("stream", {}).get("phase") == "final", "phase 更新失败"
    assert "usage" in updated_msg.extra_data, "usage 未合并"
    print(f"   ✅ 消息更新成功: status={updated_msg.status}, phase={updated_msg.extra_data.get('stream', {}).get('phase')}")
    
    # 2. 推送到 Redis Streams（模拟 SessionManager）
    print("\n2️⃣ 推送到 Redis Streams（模拟 SessionManager）...")
    mq_client = await get_message_queue_client()
    stream_id = await mq_client.push_update_event(
        message_id=message_id,
        content=content_json,
        status="completed",
        metadata=update_metadata
    )
    
    if stream_id:
        print(f"   ✅ 更新事件已推送到 Stream: stream_id={stream_id}")
    else:
        print("   ⚠️ 推送到 Stream 失败（可能 Redis 未连接，继续测试）")
    
    # 3. 验证最终消息在数据库中
    print("\n3️⃣ 验证最终消息在数据库中...")
    db_msg = await get_message(session, message_id)
    assert db_msg is not None, "最终消息在数据库中不存在"
    assert db_msg.status == "completed", "数据库中的状态不正确"
    assert db_msg.extra_data.get("stream", {}).get("phase") == "final", "数据库中的 phase 不正确"
    
    # 验证 content blocks
    blocks = db_msg.content_blocks
    assert len(blocks) == len(content_blocks), f"content blocks 数量不匹配: {len(blocks)} != {len(content_blocks)}"
    print(f"   ✅ 最终消息验证成功: id={db_msg.id}, status={db_msg.status}, blocks={len(blocks)}")
    
    # 验证 metadata 深度合并
    assert "usage" in db_msg.extra_data, "usage 未保存"
    assert db_msg.extra_data["usage"]["total_tokens"] == 1921, "usage 数据不正确"
    print(f"   ✅ metadata 深度合并验证成功: usage.total_tokens={db_msg.extra_data['usage']['total_tokens']}")
    
    return updated_msg


async def verify_complete_flow(conversation_id: str, message_id: str):
    """
    验证完整流程
    
    验证点：
    1. 占位消息的 metadata.stream.phase = "placeholder"
    2. 最终消息的 metadata.stream.phase = "final"
    3. content 字段包含完整的 content blocks
    4. status 从 'streaming' 变为 'completed'
    5. metadata 深度合并正确（usage, tool_calls 等）
    """
    print("\n" + "=" * 60)
    print("🔍 完整流程验证")
    print("=" * 60)
    
    async with AsyncSessionLocal() as session:
        # 获取最终消息
        final_msg = await get_message(session, message_id)
        assert final_msg is not None, "最终消息不存在"
        
        # 验证点 1: status 流转
        print("\n1️⃣ 验证 status 流转...")
        assert final_msg.status == "completed", f"状态不正确: {final_msg.status}"
        print("   ✅ status 从 'streaming' 变为 'completed'")
        
        # 验证点 2: phase 流转
        print("\n2️⃣ 验证 phase 流转...")
        phase = final_msg.extra_data.get("stream", {}).get("phase")
        assert phase == "final", f"phase 不正确: {phase}"
        print("   ✅ phase 从 'placeholder' 变为 'final'")
        
        # 验证点 3: content blocks
        print("\n3️⃣ 验证 content blocks...")
        blocks = final_msg.content_blocks
        assert len(blocks) > 0, "content blocks 为空"
        assert any(b.get("type") == "text" for b in blocks), "缺少 text block"
        print(f"   ✅ content 包含 {len(blocks)} 个 blocks")
        
        # 验证点 4: metadata 深度合并
        print("\n4️⃣ 验证 metadata 深度合并...")
        assert "usage" in final_msg.extra_data, "usage 未合并"
        assert "stream" in final_msg.extra_data, "stream 未合并"
        usage = final_msg.extra_data["usage"]
        assert usage.get("total_tokens") == 1921, "usage.total_tokens 不正确"
        print("   ✅ metadata 深度合并正确")
        
        # 验证点 5: 消息列表
        print("\n5️⃣ 验证消息列表...")
        messages = await list_messages(
            session=session,
            conversation_id=conversation_id,
            limit=10
        )
        assert len(messages) >= 2, f"消息数量不正确: {len(messages)}"
        print(f"   ✅ 消息列表包含 {len(messages)} 条消息")
        
        print("\n✅ 完整流程验证通过")


async def main():
    """主测试函数"""
    print("\n" + "=" * 60)
    print("🚀 开始端到端流程测试")
    print("=" * 60)
    
    test_user_id = None
    test_conv_id = None
    test_message_id = None
    session_id = f"test_session_{int(time.time())}"
    
    try:
        # 准备测试数据
        print("\n📋 准备测试数据...")
        user_data = create_mock_user_data()
        test_user_id = user_data["id"]
        
        async with AsyncSessionLocal() as session:
            # 创建用户
            user = await get_or_create_user(
                session=session,
                user_id=test_user_id,
                username=user_data["username"]
            )
            print(f"   ✅ 用户创建: id={user.id}")
            
            # 创建对话
            conv_data = create_mock_conversation_data(user_id=test_user_id)
            test_conv_id = conv_data["id"]
            conv = await create_conversation(
                session=session,
                user_id=test_user_id,
                title=conv_data["title"],
                metadata=conv_data["metadata"]
            )
            conv.id = test_conv_id
            await session.commit()
            await session.refresh(conv)
            print(f"   ✅ 对话创建: id={conv.id}")
            
            # 创建用户消息
            user_msg_data = create_mock_message_data(
                conversation_id=test_conv_id,
                role="user"
            )
            user_msg = await create_message(
                session=session,
                conversation_id=test_conv_id,
                role="user",
                content=user_msg_data["content"],
                message_id=user_msg_data["id"],
                metadata=user_msg_data["metadata"]
            )
            print(f"   ✅ 用户消息创建: id={user_msg.id}")
        
        # 阶段一：占位消息创建
        async with AsyncSessionLocal() as session:
            test_message_id = await simulate_phase1_placeholder_creation(
                session=session,
                conversation_id=test_conv_id,
                session_id=session_id
            )
        
        # 流式传输模拟
        content_blocks = await simulate_streaming_content()
        
        # 阶段二：最终消息更新
        async with AsyncSessionLocal() as session:
            await simulate_phase2_final_update(
                session=session,
                conversation_id=test_conv_id,
                message_id=test_message_id,
                content_blocks=content_blocks,
                session_id=session_id
            )
        
        # 验证完整流程
        await verify_complete_flow(test_conv_id, test_message_id)
        
        print("\n" + "=" * 60)
        print("🎉 端到端流程测试通过！")
        print("=" * 60)
        return 0
        
    except Exception as e:
        print(f"\n❌ 端到端流程测试失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return 1
        
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


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
