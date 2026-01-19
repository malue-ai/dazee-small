"""
测试数据和工具函数

提供测试所需的 Mock 数据和辅助函数。
"""

import json
from typing import Dict, Any, Optional
from uuid import uuid4
from datetime import datetime

# 测试前缀，用于标识测试数据
TEST_PREFIX = "test_e2e_"


def generate_test_user_id() -> str:
    """生成测试用户 ID"""
    return f"{TEST_PREFIX}user_{uuid4().hex[:16]}"


def generate_test_conversation_id() -> str:
    """生成测试对话 ID"""
    return f"{TEST_PREFIX}conv_{uuid4().hex[:16]}"


def generate_test_message_id() -> str:
    """生成测试消息 ID"""
    return f"{TEST_PREFIX}msg_{uuid4().hex[:16]}"


def create_mock_user_data(
    user_id: Optional[str] = None,
    username: Optional[str] = None,
    email: Optional[str] = None
) -> Dict[str, Any]:
    """
    创建 Mock 用户数据
    
    Args:
        user_id: 用户 ID（可选）
        username: 用户名（可选）
        email: 邮箱（可选）
        
    Returns:
        用户数据字典
    """
    return {
        "id": user_id or generate_test_user_id(),
        "username": username or f"test_user_{uuid4().hex[:8]}",
        "email": email or f"test_{uuid4().hex[:8]}@example.com",
        "avatar_url": None,
        "metadata": {}
    }


def create_mock_conversation_data(
    user_id: str,
    conversation_id: Optional[str] = None,
    title: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    创建 Mock 对话数据
    
    Args:
        user_id: 用户 ID（必需）
        conversation_id: 对话 ID（可选）
        title: 对话标题（可选）
        metadata: 元数据（可选）
        
    Returns:
        对话数据字典
    """
    return {
        "user_id": user_id,
        "id": conversation_id or generate_test_conversation_id(),
        "title": title or "测试对话",
        "metadata": metadata or {
            "schema_version": "conversation_meta_v1",
            "status": "active"
        }
    }


def create_mock_message_data(
    conversation_id: str,
    role: str = "user",
    message_id: Optional[str] = None,
    content: Optional[str] = None,
    status: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    创建 Mock 消息数据
    
    Args:
        conversation_id: 对话 ID（必需）
        role: 消息角色（user/assistant/system）
        message_id: 消息 ID（可选）
        content: 消息内容（JSON 字符串，可选）
        status: 消息状态（可选）
        metadata: 元数据（可选）
        
    Returns:
        消息数据字典
    """
    if content is None:
        if role == "user":
            content = json.dumps([{"type": "text", "text": "这是一条测试消息"}])
        elif role == "assistant":
            content = json.dumps([{"type": "text", "text": "这是 AI 的回复"}])
        else:
            content = json.dumps([{"type": "text", "text": "系统消息"}])
    
    return {
        "id": message_id or generate_test_message_id(),
        "conversation_id": conversation_id,
        "role": role,
        "content": content,
        "status": status,
        "metadata": metadata or {}
    }


def create_mock_placeholder_message_data(
    conversation_id: str,
    message_id: Optional[str] = None,
    session_id: Optional[str] = None,
    model: str = "claude-3-5-sonnet"
) -> Dict[str, Any]:
    """
    创建 Mock 占位消息数据（两阶段持久化 - 阶段一）
    
    Args:
        conversation_id: 对话 ID
        message_id: 消息 ID（可选）
        session_id: 会话 ID（可选）
        model: 模型名称
        
    Returns:
        占位消息数据字典
    """
    return create_mock_message_data(
        conversation_id=conversation_id,
        role="assistant",
        message_id=message_id,
        content="[]",  # 空数组
        status="streaming",
        metadata={
            "schema_version": "message_meta_v1",
            "session_id": session_id or f"test_session_{uuid4().hex[:16]}",
            "model": model,
            "stream": {
                "phase": "placeholder",
                "chunk_count": 0
            }
        }
    )


def create_mock_completed_message_data(
    conversation_id: str,
    message_id: str,
    content_blocks: list,
    session_id: Optional[str] = None,
    model: str = "claude-3-5-sonnet",
    usage: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    创建 Mock 完成消息数据（两阶段持久化 - 阶段二）
    
    Args:
        conversation_id: 对话 ID
        message_id: 消息 ID（必需，用于更新）
        content_blocks: 完整的 content blocks 列表
        session_id: 会话 ID（可选）
        model: 模型名称
        usage: 计费信息（可选）
        
    Returns:
        完成消息数据字典
    """
    content_json = json.dumps(content_blocks, ensure_ascii=False)
    
    metadata = {
        "schema_version": "message_meta_v1",
        "session_id": session_id or f"test_session_{uuid4().hex[:16]}",
        "model": model,
        "stream": {
            "phase": "final",
            "chunk_count": len(content_blocks)
        }
    }
    
    if usage:
        metadata["usage"] = usage
    
    return {
        "id": message_id,
        "conversation_id": conversation_id,
        "role": "assistant",
        "content": content_json,
        "status": "completed",
        "metadata": metadata
    }


def create_mock_content_blocks() -> list:
    """
    创建 Mock content blocks（完整的 AI 回复）
    
    Returns:
        content blocks 列表
    """
    return [
        {
            "type": "thinking",
            "thinking": "让我思考一下用户的问题...",
            "signature": f"sig_{uuid4().hex[:16]}"
        },
        {
            "type": "text",
            "text": "根据您的问题，我为您提供以下解答：\n\n1. 首先...\n2. 其次...\n3. 最后..."
        },
        {
            "type": "tool_use",
            "id": f"toolu_{uuid4().hex[:16]}",
            "name": "web_search",
            "input": {"query": "测试查询"}
        },
        {
            "type": "tool_result",
            "tool_use_id": f"toolu_{uuid4().hex[:16]}",
            "content": "搜索结果：...",
            "is_error": False
        }
    ]


def create_mock_usage_data() -> Dict[str, Any]:
    """
    创建 Mock 计费信息（usage）
    
    Returns:
        usage 数据字典
    """
    return {
        "prompt_tokens": 1234,
        "completion_tokens": 567,
        "thinking_tokens": 120,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
        "total_tokens": 1921,
        "prompt_price": 0.0123,
        "completion_price": 0.0345,
        "thinking_price": 0.0012,
        "cache_read_price": 0.0,
        "cache_write_price": 0.0,
        "total_price": 0.048,
        "avg_prompt_unit_price": 0.00001,
        "avg_completion_unit_price": 0.00006,
        "latency_ms": 1450,
        "llm_calls": 1,
        "cache_hit_rate": 0.0,
        "cost_saved_by_cache": 0.0,
        "llm_call_details": [
            {
                "call_id": f"call_{uuid4().hex[:16]}",
                "message_id": f"msg_{uuid4().hex[:16]}",
                "model": "claude-3-5-sonnet",
                "purpose": "primary",
                "timestamp": datetime.now().isoformat(),
                "input_tokens": 1234,
                "output_tokens": 567,
                "thinking_tokens": 120,
                "cache_read_tokens": 0,
                "cache_write_tokens": 0,
                "input_unit_price": 0.00001,
                "output_unit_price": 0.00006,
                "thinking_unit_price": 0.00001,
                "cache_read_unit_price": 0.0,
                "cache_write_unit_price": 0.0,
                "input_total_price": 0.0123,
                "output_total_price": 0.0345,
                "thinking_total_price": 0.0012,
                "cache_read_price": 0.0,
                "cache_write_price": 0.0,
                "total_price": 0.048,
                "latency_ms": 1450,
                "metadata": {}
            }
        ]
    }


def is_test_data(identifier: str) -> bool:
    """
    判断是否为测试数据
    
    Args:
        identifier: ID（user_id, conversation_id, message_id 等）
        
    Returns:
        是否为测试数据
    """
    return identifier.startswith(TEST_PREFIX)


async def cleanup_test_data(
    session,
    user_id: Optional[str] = None,
    conversation_id: Optional[str] = None,
    message_id: Optional[str] = None
):
    """
    清理测试数据
    
    Args:
        session: 数据库会话
        user_id: 用户 ID（可选，如果提供则删除该用户及其所有对话和消息）
        conversation_id: 对话 ID（可选，如果提供则删除该对话及其所有消息）
        message_id: 消息 ID（可选，如果提供则删除该消息）
    """
    from infra.database.crud.base import delete_by_id
    from infra.database.models import User, Conversation, Message
    
    try:
        if message_id:
            # 删除单条消息
            await delete_by_id(session, Message, message_id)
            print(f"✅ 已删除测试消息: {message_id}")
        
        if conversation_id:
            # 删除对话（级联删除消息）
            await delete_by_id(session, Conversation, conversation_id)
            print(f"✅ 已删除测试对话: {conversation_id}")
        
        if user_id:
            # 删除用户（级联删除对话和消息）
            await delete_by_id(session, User, user_id)
            print(f"✅ 已删除测试用户: {user_id}")
            
    except Exception as e:
        print(f"⚠️ 清理测试数据失败: {str(e)}")
