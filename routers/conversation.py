"""
Conversation 路由层 - 对话管理接口

职责：
- 对话 CRUD（创建、查询、更新、删除）
- 对话列表查询
- 历史消息查询
- 对话标题管理

设计原则：
- 只处理 HTTP 协议
- 调用 Service 层处理业务逻辑
- 异常转换为 HTTP 异常
"""

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, status

from logger import get_logger
from models.api import APIResponse
from models.database import Conversation, Message
from services.conversation_service import (
    ConversationNotFoundError,
    ConversationService,
    get_conversation_service,
)

# 配置日志
logger = get_logger("conversation_router")

# 创建路由器
router = APIRouter(
    prefix="/api/v1/conversations",
    tags=["conversations"],
    responses={404: {"description": "Not found"}},
)

# 获取服务实例
conversation_service = get_conversation_service()


# ==================== 搜索 ====================


@router.get("/search", response_model=APIResponse[dict])
async def search_conversations(
    user_id: str = Query(..., description="用户ID"),
    q: str = Query(..., description="搜索关键词"),
    limit: int = Query(20, description="返回数量", ge=1, le=50),
):
    """
    搜索对话（标题 + 消息内容全文搜索）

    ## 参数
    - **user_id**: 用户ID（必填）
    - **q**: 搜索关键词（必填）
    - **limit**: 返回数量（默认20，最大50）

    ## 返回
    ```json
    {
      "code": 200,
      "message": "success",
      "data": {
        "conversations": [
          {
            "conversation": { "id": "conv_xxx", "title": "..." },
            "match_type": "title|content",
            "snippet": "匹配的消息片段..."
          }
        ],
        "total": 5
      }
    }
    ```
    """
    try:
        logger.info(f"📨 搜索对话: user_id={user_id}, q={q}, limit={limit}")

        result = await conversation_service.search_conversations(
            user_id=user_id,
            query=q,
            limit=limit,
        )

        logger.info(f"✅ 搜索完成，返回 {result['total']} 条结果")

        return APIResponse(code=200, message="success", data=result)

    except Exception as e:
        logger.error(f"❌ 搜索对话失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"搜索对话失败: {str(e)}",
        )


# ==================== 对话 CRUD ====================


@router.post("", response_model=APIResponse[Conversation])
async def create_conversation(
    user_id: str = Query(..., description="用户ID"),
    title: str = Query("新对话", description="对话标题"),
):
    """
    创建新对话

    ## 参数
    - **user_id**: 用户ID（必填）
    - **title**: 对话标题（可选，默认"新对话"）

    ## 返回
    ```json
    {
      "code": 200,
      "message": "success",
      "data": {
        "id": "conv_abc123",
        "user_id": "user_001",
        "title": "新对话",
        "created_at": "2024-01-01T12:00:00",
        "updated_at": "2024-01-01T12:00:00",
        "metadata": {}
      }
    }
    ```
    """
    try:
        logger.info(f"📨 创建新对话: user_id={user_id}, title={title}")

        conversation = await conversation_service.create_conversation(user_id=user_id, title=title)

        logger.info(f"✅ 对话创建成功: id={conversation.id}")

        return APIResponse(code=200, message="success", data=conversation)

    except Exception as e:
        logger.error(f"❌ 创建对话失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"创建对话失败: {str(e)}"
        )


@router.get("/{conversation_id}", response_model=APIResponse[Conversation])
async def get_conversation(conversation_id: str):
    """
    获取对话详情

    ## 参数
    - **conversation_id**: 对话ID

    ## 返回
    对话详细信息
    """
    try:
        logger.info(f"📨 获取对话详情: conversation_id={conversation_id}")

        conversation = await conversation_service.get_conversation(conversation_id)

        logger.info(f"✅ 对话查询成功")

        return APIResponse(code=200, message="success", data=conversation)

    except ConversationNotFoundError as e:
        logger.warning(f"⚠️ 对话不存在: {str(e)}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"❌ 获取对话失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"获取对话失败: {str(e)}"
        )


@router.get("", response_model=APIResponse[dict])
async def list_conversations(
    user_id: str = Query(..., description="用户ID"),
    limit: int = Query(20, description="每页数量", ge=1, le=100),
    offset: int = Query(0, description="偏移量", ge=0),
):
    """
    获取用户的对话列表

    ## 参数
    - **user_id**: 用户ID（必填）
    - **limit**: 每页数量（默认20，最大100）
    - **offset**: 偏移量（默认0）

    ## 返回
    ```json
    {
      "code": 200,
      "message": "success",
      "data": {
        "conversations": [
          {
            "id": "conv_abc123",
            "user_id": "user_001",
            "title": "讨论Python编程",
            "created_at": "2024-01-01T12:00:00",
            "updated_at": "2024-01-01T12:30:00",
            "message_count": 10,
            "last_message": "好的，我理解了",
            "last_message_at": "2024-01-01T12:30:00"
          },
          ...
        ],
        "total": 50,
        "limit": 20,
        "offset": 0
      }
    }
    ```
    """
    try:
        logger.info(f"📨 获取对话列表: user_id={user_id}, limit={limit}, offset={offset}")

        result = await conversation_service.list_conversations(
            user_id=user_id, limit=limit, offset=offset
        )

        logger.info(f"✅ 返回 {len(result['conversations'])} 条对话")

        return APIResponse(code=200, message="success", data=result)

    except Exception as e:
        logger.error(f"❌ 获取对话列表失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"获取对话列表失败: {str(e)}"
        )


@router.put("/{conversation_id}", response_model=APIResponse[Conversation])
async def update_conversation(
    conversation_id: str, title: Optional[str] = Query(None, description="新标题")
):
    """
    更新对话信息

    ## 参数
    - **conversation_id**: 对话ID
    - **title**: 新标题（可选）

    ## 返回
    更新后的对话信息
    """
    try:
        logger.info(f"📨 更新对话: conversation_id={conversation_id}, title={title}")

        conversation = await conversation_service.update_conversation(
            conversation_id=conversation_id, title=title
        )

        logger.info(f"✅ 对话更新成功")

        return APIResponse(code=200, message="success", data=conversation)

    except ConversationNotFoundError as e:
        logger.warning(f"⚠️ 对话不存在: {str(e)}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"❌ 更新对话失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"更新对话失败: {str(e)}"
        )


@router.delete("/{conversation_id}", response_model=APIResponse[dict])
async def delete_conversation(conversation_id: str):
    """
    删除对话

    ## 参数
    - **conversation_id**: 对话ID

    ## 返回
    ```json
    {
      "code": 200,
      "message": "success",
      "data": {
        "conversation_id": "conv_abc123",
        "deleted": true,
        "deleted_messages": 10
      }
    }
    ```

    ## 注意
    删除对话会同时删除该对话下的所有消息
    """
    try:
        logger.info(f"📨 删除对话: conversation_id={conversation_id}")

        result = await conversation_service.delete_conversation(conversation_id)

        logger.info(f"✅ 对话删除成功，同时删除了 {result['deleted_messages']} 条消息")

        return APIResponse(code=200, message="success", data=result)

    except ConversationNotFoundError as e:
        logger.warning(f"⚠️ 对话不存在: {str(e)}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"❌ 删除对话失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"删除对话失败: {str(e)}"
        )


# ==================== 历史消息查询 ====================


@router.get("/{conversation_id}/messages", response_model=APIResponse[dict])
async def get_conversation_messages(
    conversation_id: str,
    limit: int = Query(50, description="每页数量", ge=1, le=200),
    offset: int = Query(0, description="偏移量（当 before_cursor 为 None 时使用）", ge=0),
    order: str = Query("asc", description="排序方式（asc/desc）"),
    before_cursor: Optional[str] = Query(
        None, description="游标（message_id），用于分页加载更早的消息"
    ),
):
    """
    获取对话的历史消息（支持基于游标的分页，对齐文档规范）

    ## 参数
    - **conversation_id**: 对话ID
    - **limit**: 每页数量（默认50，最大200）
    - **offset**: 偏移量（默认0，当 before_cursor 为 None 时使用）
    - **order**: 排序方式（asc=时间正序, desc=时间倒序）
    - **before_cursor**: 游标（message_id），用于分页加载更早的消息（对齐文档规范）

    ## 返回
    ```json
    {
      "code": 200,
      "message": "success",
      "data": {
        "conversation_id": "conv_abc123",
        "conversation_metadata": {
          "project_type": "react_fullstack"
        },
        "messages": [
          {
            "id": "msg_xxx",
            "conversation_id": "conv_abc123",
            "role": "user",
            "content": [{"type": "text", "text": "你好"}],
            "created_at": "2024-01-01T12:00:00",
            "metadata": {}
          },
          ...
        ],
        "total": 100,
        "limit": 50,
        "offset": 0,
        "has_more": true,
        "next_cursor": "msg_yyy"  // 用于下次分页（当使用 before_cursor 时）
      }
    }
    ```

    ## 使用场景
    - **初始加载**：不传 before_cursor，使用 offset 分页
    - **向上滚动加载**：传 before_cursor，获取更早的消息（对齐文档规范）
    - 搜索历史消息
    """
    try:
        logger.info(
            f"📨 获取对话历史: conversation_id={conversation_id}, "
            f"limit={limit}, offset={offset}, order={order}, before_cursor={before_cursor}"
        )

        # 验证排序方式
        if order not in ["asc", "desc"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="排序方式必须是 'asc' 或 'desc'"
            )

        result = await conversation_service.get_conversation_messages(
            conversation_id=conversation_id,
            limit=limit,
            offset=offset,
            order=order,
            before_cursor=before_cursor,
        )

        logger.info(
            f"✅ 返回 {len(result['messages'])} 条消息, "
            f"has_more={result.get('has_more')}, next_cursor={result.get('next_cursor')}"
        )

        return APIResponse(code=200, message="success", data=result)

    except ConversationNotFoundError as e:
        logger.warning(f"⚠️ 对话不存在: {str(e)}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"❌ 获取历史消息失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"获取历史消息失败: {str(e)}"
        )


@router.post("/{conversation_id}/preload", response_model=APIResponse[dict])
async def preload_conversation_context(
    conversation_id: str,
    limit: int = Query(50, description="预加载消息数量", ge=1, le=200),
    force: bool = Query(False, description="是否强制刷新缓存"),
):
    """
    预加载会话上下文到内存缓存（用于用户打开会话窗口前）

    ## 参数
    - **conversation_id**: 对话ID
    - **limit**: 预加载消息数量（默认50，最大200）
    - **force**: 是否强制刷新缓存（默认False）

    ## 返回
    ```json
    {
      "code": 200,
      "message": "success",
      "data": {
        "conversation_id": "conv_abc123",
        "cache_hit": false,
        "message_count": 50,
        "oldest_cursor": "msg_0001",
        "last_updated": "2024-01-01T12:00:00",
        "effective_limit": 50
      }
    }
    ```
    """
    try:
        logger.info(
            f"📨 预加载会话上下文: conversation_id={conversation_id}, "
            f"limit={limit}, force={force}"
        )

        # 校验对话是否存在
        await conversation_service.get_conversation(conversation_id)

        session_cache = get_session_cache_service()
        result = await session_cache.warmup_context(
            conversation_id=conversation_id, limit=limit, force=force
        )
        context = result["context"]

        data = {
            "conversation_id": conversation_id,
            "cache_hit": result["cache_hit"],
            "message_count": len(context.messages),
            "oldest_cursor": context.oldest_cursor,
            "last_updated": context.last_updated.isoformat() if context.last_updated else None,
            "effective_limit": result["effective_limit"],
        }

        logger.info(
            f"✅ 会话上下文预加载完成: conversation_id={conversation_id}, "
            f"message_count={data['message_count']}, cache_hit={data['cache_hit']}"
        )

        return APIResponse(code=200, message="success", data=data)

    except ConversationNotFoundError as e:
        logger.warning(f"⚠️ 对话不存在: {str(e)}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"❌ 预加载会话上下文失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"预加载会话上下文失败: {str(e)}",
        )


@router.get("/{conversation_id}/summary", response_model=APIResponse[dict])
async def get_conversation_summary(conversation_id: str):
    """
    获取对话摘要

    ## 参数
    - **conversation_id**: 对话ID

    ## 返回
    ```json
    {
      "code": 200,
      "message": "success",
      "data": {
        "conversation_id": "conv_abc123",
        "title": "讨论Python编程",
        "message_count": 50,
        "user_message_count": 25,
        "assistant_message_count": 25,
        "created_at": "2024-01-01T12:00:00",
        "updated_at": "2024-01-01T15:30:00",
        "last_message": {
          "role": "assistant",
          "content": "好的，我理解了",
          "created_at": "2024-01-01T15:30:00"
        }
      }
    }
    ```

    ## 使用场景
    - 对话列表展示
    - 对话预览
    - 统计分析
    """
    try:
        logger.info(f"📨 获取对话摘要: conversation_id={conversation_id}")

        summary = await conversation_service.get_conversation_summary(conversation_id)

        logger.info(f"✅ 对话摘要获取成功")

        return APIResponse(code=200, message="success", data=summary)

    except ConversationNotFoundError as e:
        logger.warning(f"⚠️ 对话不存在: {str(e)}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"❌ 获取对话摘要失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"获取对话摘要失败: {str(e)}"
        )
