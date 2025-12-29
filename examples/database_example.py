"""
数据库使用示例

演示如何使用 User, Conversation, Message 三个表
"""

import asyncio
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.database import init_db
from utils.db_service import UserService, ConversationService, MessageService


async def main():
    """数据库使用示例"""
    
    # 1. 初始化数据库
    print("=== 初始化数据库 ===")
    await init_db()
    print("✓ 数据库初始化完成\n")
    
    # 2. 创建用户
    print("=== 创建用户 ===")
    user = await UserService.create_user(
        username="test_user",
        email="test@example.com",
        metadata={"source": "web", "plan": "free"}
    )
    print(f"✓ 创建用户: {user.username} (ID: {user.id})\n")
    
    # 3. 创建对话
    print("=== 创建对话 ===")
    conversation = await ConversationService.create_conversation(
        user_id=user.id,
        conversation_id="conv_123456",
        title="关于 AI 的讨论",
        metadata={"topic": "AI", "language": "zh"}
    )
    print(f"✓ 创建对话: {conversation.title} (ID: {conversation.conversation_id})\n")
    
    # 4. 添加消息
    print("=== 添加消息 ===")
    
    # 用户消息
    msg1 = await MessageService.create_message(
        conversation_id=conversation.conversation_id,
        role="user",
        content="什么是人工智能？",
        metadata={"ip": "127.0.0.1"}
    )
    print(f"✓ 用户消息: {msg1.content[:20]}...")
    
    # 助手回复
    msg2 = await MessageService.create_message(
        conversation_id=conversation.conversation_id,
        role="assistant",
        content="人工智能（AI）是计算机科学的一个分支，致力于创建能够执行通常需要人类智能的任务的系统...",
        metadata={"model": "claude-3", "tokens": 150}
    )
    print(f"✓ 助手消息: {msg2.content[:20]}...\n")
    
    # 5. 查询消息历史
    print("=== 查询消息历史 ===")
    messages = await MessageService.get_conversation_messages(conversation.conversation_id)
    print(f"✓ 共 {len(messages)} 条消息:")
    for msg in messages:
        print(f"  - [{msg.role}] {msg.content[:30]}...")
    print()
    
    # 6. 查询用户的所有对话
    print("=== 查询用户对话列表 ===")
    conversations = await ConversationService.get_user_conversations(user.id)
    print(f"✓ 用户 {user.username} 共有 {len(conversations)} 个对话:")
    for conv in conversations:
        print(f"  - {conv.title} (更新时间: {conv.updated_at})")
    print()
    
    # 7. 更新对话标题
    print("=== 更新对话标题 ===")
    await ConversationService.update_conversation_title(
        conversation.conversation_id,
        "深入探讨人工智能"
    )
    updated_conv = await ConversationService.get_conversation(conversation.conversation_id)
    print(f"✓ 新标题: {updated_conv.title}\n")
    
    # 8. 获取最近的消息
    print("=== 获取最近消息 ===")
    recent = await MessageService.get_recent_messages(conversation.conversation_id, limit=2)
    print(f"✓ 最近 {len(recent)} 条消息:")
    for msg in recent:
        print(f"  - [{msg.role}] {msg.content[:30]}...")
    
    print("\n✅ 示例完成！")


if __name__ == "__main__":
    asyncio.run(main())

