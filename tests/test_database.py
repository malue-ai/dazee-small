"""
数据库功能测试

测试 User, Conversation, Message 的 CRUD 操作
"""

import asyncio
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.database import init_db, db_manager
from utils.db_service import UserService, ConversationService, MessageService


async def test_user_operations():
    """测试用户操作"""
    print("\n=== 测试用户操作 ===")
    
    # 创建用户
    user1 = await UserService.create_user(
        username="test_user_1",
        email="test1@example.com",
        metadata={"plan": "free"}
    )
    assert user1.id is not None
    assert user1.username == "test_user_1"
    print(f"✓ 创建用户成功: {user1.username}")
    
    # 根据ID获取用户
    user_by_id = await UserService.get_user_by_id(user1.id)
    assert user_by_id is not None
    assert user_by_id.username == "test_user_1"
    print(f"✓ 根据ID获取用户成功")
    
    # 根据用户名获取用户
    user_by_name = await UserService.get_user_by_username("test_user_1")
    assert user_by_name is not None
    assert user_by_name.id == user1.id
    print(f"✓ 根据用户名获取用户成功")
    
    return user1


async def test_conversation_operations(user_id: int):
    """测试对话操作"""
    print("\n=== 测试对话操作 ===")
    
    # 创建对话
    conv1 = await ConversationService.create_conversation(
        user_id=user_id,
        conversation_id="test_conv_1",
        title="测试对话1",
        metadata={"topic": "test"}
    )
    assert conv1.id is not None
    assert conv1.conversation_id == "test_conv_1"
    print(f"✓ 创建对话成功: {conv1.title}")
    
    # 获取对话
    conv = await ConversationService.get_conversation("test_conv_1")
    assert conv is not None
    assert conv.title == "测试对话1"
    print(f"✓ 获取对话成功")
    
    # 创建第二个对话
    conv2 = await ConversationService.create_conversation(
        user_id=user_id,
        conversation_id="test_conv_2",
        title="测试对话2"
    )
    print(f"✓ 创建第二个对话成功")
    
    # 获取用户的所有对话
    conversations = await ConversationService.get_user_conversations(user_id)
    assert len(conversations) >= 2
    print(f"✓ 获取用户对话列表成功: {len(conversations)} 个对话")
    
    # 更新对话标题
    await ConversationService.update_conversation_title("test_conv_1", "更新后的标题")
    updated_conv = await ConversationService.get_conversation("test_conv_1")
    assert updated_conv.title == "更新后的标题"
    print(f"✓ 更新对话标题成功")
    
    return conv1


async def test_message_operations(conversation_id: str):
    """测试消息操作"""
    print("\n=== 测试消息操作 ===")
    
    # 创建用户消息
    msg1 = await MessageService.create_message(
        conversation_id=conversation_id,
        role="user",
        content="这是第一条用户消息",
        metadata={"ip": "127.0.0.1"}
    )
    assert msg1.id is not None
    assert msg1.role == "user"
    print(f"✓ 创建用户消息成功")
    
    # 创建助手消息
    msg2 = await MessageService.create_message(
        conversation_id=conversation_id,
        role="assistant",
        content="这是助手的回复",
        metadata={"model": "claude-3", "tokens": 50}
    )
    assert msg2.role == "assistant"
    print(f"✓ 创建助手消息成功")
    
    # 创建更多消息
    for i in range(3, 6):
        await MessageService.create_message(
            conversation_id=conversation_id,
            role="user" if i % 2 == 1 else "assistant",
            content=f"消息 {i}"
        )
    print(f"✓ 创建多条消息成功")
    
    # 获取所有消息
    all_messages = await MessageService.get_conversation_messages(conversation_id)
    assert len(all_messages) >= 5
    print(f"✓ 获取所有消息成功: {len(all_messages)} 条")
    
    # 获取最近的消息
    recent = await MessageService.get_recent_messages(conversation_id, limit=3)
    assert len(recent) == 3
    print(f"✓ 获取最近消息成功: {len(recent)} 条")
    
    # 验证消息顺序（最早的在前）
    assert recent[0].created_at <= recent[-1].created_at
    print(f"✓ 消息顺序正确")


async def test_metadata():
    """测试元数据功能"""
    print("\n=== 测试元数据功能 ===")
    
    # 创建带复杂元数据的用户
    complex_metadata = {
        "plan": "pro",
        "preferences": {
            "language": "zh",
            "theme": "dark",
            "notifications": True
        },
        "tags": ["developer", "ai-enthusiast"]
    }
    
    user = await UserService.create_user(
        username="metadata_test_user",
        metadata=complex_metadata
    )
    
    # 验证元数据
    retrieved_user = await UserService.get_user_by_id(user.id)
    assert retrieved_user.metadata["plan"] == "pro"
    assert retrieved_user.metadata["preferences"]["language"] == "zh"
    assert "developer" in retrieved_user.metadata["tags"]
    print(f"✓ 复杂元数据存储和读取成功")


async def cleanup_test_data():
    """清理测试数据"""
    print("\n=== 清理测试数据 ===")
    
    async with db_manager.get_connection() as db:
        # 删除测试消息
        await db.execute("DELETE FROM messages WHERE conversation_id LIKE 'test_conv_%'")
        
        # 删除测试对话
        await db.execute("DELETE FROM conversations WHERE conversation_id LIKE 'test_conv_%'")
        
        # 删除测试用户
        await db.execute("DELETE FROM users WHERE username LIKE 'test_user_%' OR username LIKE 'metadata_test_%'")
        
        await db.commit()
    
    print("✓ 测试数据清理完成")


async def main():
    """运行所有测试"""
    print("\n" + "="*60)
    print("🧪 开始数据库功能测试")
    print("="*60)
    
    try:
        # 初始化数据库
        await init_db()
        print("✓ 数据库初始化完成")
        
        # 测试用户操作
        user = await test_user_operations()
        
        # 测试对话操作
        conversation = await test_conversation_operations(user.id)
        
        # 测试消息操作
        await test_message_operations(conversation.conversation_id)
        
        # 测试元数据
        await test_metadata()
        
        # 清理测试数据
        await cleanup_test_data()
        
        print("\n" + "="*60)
        print("✅ 所有测试通过！")
        print("="*60 + "\n")
        
    except AssertionError as e:
        print(f"\n❌ 测试失败: {str(e)}")
        raise
    except Exception as e:
        print(f"\n❌ 测试出错: {str(e)}")
        raise


if __name__ == "__main__":
    asyncio.run(main())

