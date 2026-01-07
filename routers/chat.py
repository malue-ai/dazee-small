"""
Chat 路由层 - 仅处理 HTTP 请求/响应

职责：
- HTTP 请求解析和参数验证
- 调用 Service 层处理业务逻辑
- 流式响应封装（SSE）
- 异常转换为 HTTP 异常

提供功能：
- 同步聊天、流式聊天
- 会话管理
- 结果改进（HITL）
"""

from logger import get_logger
import json
import asyncio
import time
from enum import Enum
from fastapi import APIRouter, HTTPException, BackgroundTasks, status, Query
from fastapi.responses import StreamingResponse
from typing import Dict, Any, Optional
from datetime import datetime

from models.api import APIResponse
from models.chat import (
    ChatRequest,
    ChatResponse,
    StreamEvent,
    SessionInfo,
    RefineRequest
)
from services import (
    get_chat_service,
    get_session_service,
    get_conversation_service,
    SessionNotFoundError,
    AgentExecutionError,
)

# 配置日志
logger = get_logger("chat_router")

# 创建路由器
router = APIRouter(
    prefix="/api/v1",
    tags=["chat"],
    responses={404: {"description": "Not found"}},
)

# 获取服务实例
chat_service = get_chat_service()
session_service = get_session_service()
conversation_service = get_conversation_service()


# ==================== 错误码定义 ====================

class ErrorCode:
    """统一错误码定义"""
    VALIDATION_ERROR = "VALIDATION_ERROR"       # 参数验证失败
    SESSION_NOT_FOUND = "SESSION_NOT_FOUND"     # Session 不存在
    AGENT_ERROR = "AGENT_ERROR"                 # Agent 执行错误
    EXTERNAL_SERVICE_ERROR = "EXTERNAL_SERVICE"  # 外部服务错误（LLM、Redis 等）
    INTERNAL_ERROR = "INTERNAL_ERROR"           # 内部错误


def create_error_response(code: str, message: str, detail: str = None) -> Dict[str, Any]:
    """
    创建统一的错误响应格式
    
    Args:
        code: 错误码
        message: 用户可见的错误信息
        detail: 详细错误信息（仅用于日志，不返回给用户）
    """
    return {
        "code": code,
        "message": message,
        "timestamp": datetime.now().isoformat()
    }


def sanitize_error_message(error: Exception) -> str:
    """
    清理错误信息，隐藏敏感内容
    
    Args:
        error: 异常对象
        
    Returns:
        安全的错误信息
    """
    error_str = str(error)
    
    # 定义敏感关键词列表
    sensitive_keywords = [
        "api_key", "token", "password", "secret", "credential",
        "authorization", "bearer", "sk-", "pk-"
    ]
    
    # 检查是否包含敏感信息
    error_lower = error_str.lower()
    for keyword in sensitive_keywords:
        if keyword in error_lower:
            return "系统内部错误，请稍后重试"
    
    # 如果错误信息过长，截断
    if len(error_str) > 200:
        return error_str[:200] + "..."
    
    return error_str


# ==================== 辅助函数 ====================

def sanitize_for_json(obj: Any) -> Any:
    """
    清理对象使其可以JSON序列化
    处理Enum、ToolType等不可序列化的对象
    """
    if obj is None:
        return None
    elif isinstance(obj, Enum):
        return obj.value
    elif isinstance(obj, dict):
        return {k: sanitize_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [sanitize_for_json(item) for item in obj]
    elif isinstance(obj, (str, int, float, bool)):
        return obj
    else:
        # 尝试转换为字符串
        try:
            return str(obj)
        except Exception:
            return None


# ==================== 聊天接口 ====================

@router.post("/chat")
async def chat(
    request: ChatRequest, 
    background_tasks: BackgroundTasks,
    format: str = Query("zeno", description="事件格式：zeno（ZenO SSE 规范 v2.0.1，默认）或 zenflux（原始格式）")
):
    """
    统一聊天接口（支持流式和同步两种模式）
    
    根据 `stream` 参数自动选择返回模式：
    - `stream=true`: 流式模式（SSE），实时推送事件
    - `stream=false`: 同步模式，立即返回 task_id，客户端轮询查询结果
    
    ## 参数
    - **message**: 用户消息（必填）
    - **user_id**: 用户ID（必填，用于 Session 管理）
    - **message_id**: 消息ID（可选，用于追踪）
    - **conversation_id**: 对话ID（可选，用于关联数据库对话）
    - **stream**: 是否使用流式输出（默认为 true）
    - **background_tasks**: 后台任务列表（可选），如 `["title_generation"]`
    - **file**: 附件文件路径或URL（可选）
    - **variables**: 前端上下文变量（可选），如位置、时区等
    
    ---
    
    ## 模式1：流式模式 (`stream=true`)
    
    **返回**: SSE 事件流
    
    **使用场景**: 需要实时看到 Agent 的思考过程和执行步骤
    
    **特点**:
    - Agent 在后台运行，事件写入 Redis
    - SSE 从 Redis 实时读取事件并推送
    - 支持断线重连（从 Redis 补偿丢失的事件）
    - Agent 执行不受 SSE 连接影响
    
    **SSE 事件格式**:
    ```
    id: 1
    event: session_start
    data: {"id":1,"session_id":"sess_xxx","type":"session_start","data":{...},"timestamp":"..."}
    
    id: 2
    event: message_start
    data: {"id":2,"session_id":"sess_xxx","type":"message_start","data":{...},"timestamp":"..."}
    
    ...
    
    event: done
    data: {}
    ```
    
    详细协议见：`docs/03-EVENT-PROTOCOL.md`
    
    ---
    
    ## 模式2：同步模式 (`stream=false`)
    
    **返回**: 
    ```json
    {
      "code": 200,
      "message": "任务已启动，请轮询 /api/v1/session/{task_id} 查看结果",
      "data": {
        "task_id": "sess_abc123",
        "conversation_id": "conv_xyz",
        "status": "running"
      }
    }
    ```
    
    **使用场景**: 不需要实时反馈，只关心最终结果
    
    **特点**:
    - 立即返回 `task_id`（就是 `session_id`）
    - Agent 在后台运行，事件写入 Redis，结果写入数据库
    - 客户端通过轮询 `/api/v1/session/{task_id}/status` 查询状态
    - 最终从数据库读取结果（Message 表）
    - 不使用 SSE，更简单可靠
    
    **客户端轮询流程**:
    ```
    1. POST /api/v1/chat (stream=false) → 返回 task_id
    2. 轮询 GET /api/v1/session/{task_id}/status → 查看进度
    3. 状态变为 "completed" 后，从数据库读取结果
    ```
    
    ---
    
    ## 选择建议
    
    - **Web 界面**: 推荐流式模式（实时体验更好）
    - **API 集成**: 推荐同步模式（简单直接）
    - **移动端/不稳定网络**: 推荐同步模式（轮询更可靠）
    """
    try:
        # 验证 user_id（必填）
        if not request.user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=create_error_response(
                    ErrorCode.VALIDATION_ERROR,
                    "user_id 是必填参数"
                )
            )
        
        # 记录请求信息
        logger.info(
            f"📨 收到{'流式' if request.stream else '同步'}聊天请求: "
            f"user_id={request.user_id}, "
            f"message_id={request.message_id}, "
            f"conversation_id={request.conversation_id}, "
            f"message={str(request.message)[:50]}..."
        )
        
        # 记录额外的上下文信息
        if request.variables:
            logger.debug(f"📍 前端变量: {request.variables}")
        if request.files:
            logger.info(f"📎 文件: {len(request.files)} 个")
        if request.background_tasks:
            logger.info(f"⏱️ 后台任务: {request.background_tasks}")
        
        # 转换 files 为字典列表
        files_data = None
        if request.files:
            files_data = [f.model_dump() for f in request.files]
        
        # ===== 流式模式（默认） =====
        if request.stream:
            # 初始化格式适配器
            adapter = None
            if format == "zeno":
                from core.events.adapters.zeno import ZenOAdapter
                adapter = ZenOAdapter(conversation_id=request.conversation_id)
                logger.info("📋 使用 ZenO 格式适配器")
            
            async def event_generator():
                """生成 SSE 事件流"""
                try:
                    # 🎯 使用统一的 chat() 入口
                    async for event in await chat_service.chat(
                        message=request.message,
                        user_id=request.user_id,
                        conversation_id=request.conversation_id,
                        message_id=request.message_id,
                        stream=True,
                        background_tasks=request.background_tasks,
                        files=files_data
                    ):
                        # 格式转换
                        if adapter:
                            transformed_event = adapter.transform(event)
                            if transformed_event is None:
                                # 适配器过滤了此事件，跳过
                                continue
                            event = transformed_event
                        
                        # ZenO 格式只输出 data 行
                        yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                
                except AgentExecutionError as e:
                    logger.error(f"❌ 流式对话错误: {str(e)}")
                    error_event = {
                        "type": "message.assistant.error",
                        "message_id": request.message_id or "",
                        "timestamp": int(time.time() * 1000),
                        "error": {
                            "type": "business",
                            "code": "AGENT_ERROR",
                            "message": "对话处理失败，请稍后重试",
                            "retryable": True
                        }
                    }
                    yield f"data: {json.dumps(error_event, ensure_ascii=False)}\n\n"
                    
                except ConnectionError as e:
                    logger.error(f"❌ 连接错误: {str(e)}", exc_info=True)
                    error_event = {
                        "type": "message.assistant.error",
                        "message_id": request.message_id or "",
                        "timestamp": int(time.time() * 1000),
                        "error": {
                            "type": "network",
                            "code": "CONNECTION_ERROR",
                            "message": "服务连接失败，请稍后重试",
                            "retryable": True
                        }
                    }
                    yield f"data: {json.dumps(error_event, ensure_ascii=False)}\n\n"
                    
                except Exception as e:
                    logger.error(f"❌ 流式对话错误: {str(e)}", exc_info=True)
                    safe_message = sanitize_error_message(e)
                    error_event = {
                        "type": "message.assistant.error",
                        "message_id": request.message_id or "",
                        "timestamp": int(time.time() * 1000),
                        "error": {
                            "type": "unknown",
                            "code": "INTERNAL_ERROR",
                            "message": safe_message,
                            "retryable": False
                        }
                    }
                    yield f"data: {json.dumps(error_event, ensure_ascii=False)}\n\n"
            
            return StreamingResponse(
                event_generator(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                }
            )
        
        # ===== 同步模式（立即返回 task_id） =====
        else:
            # 🎯 使用统一的 chat() 入口
            result = await chat_service.chat(
                message=request.message,
                user_id=request.user_id,
                conversation_id=request.conversation_id,
                message_id=request.message_id,
                stream=False,
                background_tasks=request.background_tasks,
                files=files_data
            )
            
            # 后台清理任务（使用带锁的异步清理）
            background_tasks.add_task(session_service.cleanup_inactive_sessions)
            
            logger.info(f"✅ 任务已启动: task_id={result['task_id']}")
            
            # 立即返回 task_id
            return APIResponse(
                code=200,
                message=result.get("message", "任务已启动"),
                data=result
            )
    
    except HTTPException:
        raise
    except AgentExecutionError as e:
        logger.error(f"❌ 对话执行失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=create_error_response(
                ErrorCode.AGENT_ERROR,
                "对话处理失败，请稍后重试"
            )
        )
    except ConnectionError as e:
        logger.error(f"❌ 连接错误: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=create_error_response(
                ErrorCode.EXTERNAL_SERVICE_ERROR,
                "服务暂时不可用，请稍后重试"
            )
        )
    except Exception as e:
        logger.error(f"❌ 聊天接口错误: {str(e)}", exc_info=True)
        safe_message = sanitize_error_message(e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=create_error_response(
                ErrorCode.INTERNAL_ERROR,
                safe_message
            )
        )



# ==================== SSE 重连接口 ====================

@router.get("/chat/{session_id}")
async def reconnect_chat_stream(
    session_id: str,
    after_seq: Optional[int] = Query(None, description="从哪个序号之后开始（断点续传）"),
    format: str = Query("zeno", description="事件格式：zeno（ZenO SSE 规范 v2.0.1，默认）或 zenflux（原始格式）")
):
    """
    重连到已存在的 Session SSE 流（断线重连）
    
    ## 使用场景
    用户刷新页面或断线后，重新连接到正在运行的 Agent Session
    
    ## 参数
    - **session_id**: Session ID
    - **after_seq**: 从哪个序号之后开始（可选，用于断点续传）
    
    ## 返回
    SSE 事件流，首先发送一个 `reconnect_info` 事件包含上下文信息：
    ```
    event: reconnect_info
    data: {
      "session_id": "sess_xxx",
      "conversation_id": "conv_xxx",
      "message_id": "msg_xxx",
      "status": "running",
      "last_event_seq": 150,
      "total_buffered_events": 150
    }
    ```
    
    然后推送 seq > after_seq 的所有事件
    
    ## 流程
    1. 先发送 `reconnect_info` 事件（包含上下文）
    2. 发送所有丢失的历史事件（从 Redis 缓冲区）
    3. 订阅 Pub/Sub 实时推送新事件
    4. Session 完成时发送 `done` 事件
    """
    try:
        logger.info(f"📨 SSE 重连请求: session_id={session_id}, after_seq={after_seq}")
        
        # 1. 检查 Session 是否存在
        status_data = await session_service.get_session_status(session_id)
        
        if not status_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=create_error_response(
                    ErrorCode.SESSION_NOT_FOUND,
                    "Session 不存在或已过期"
                )
            )
        
        session_status = status_data.get("status")
        
        # 如果 Session 已完成，返回错误
        if session_status in ["completed", "failed", "timeout", "stopped"]:
            logger.info(f"ℹ️ Session 已结束: status={session_status}")
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail=create_error_response(
                    ErrorCode.SESSION_NOT_FOUND,
                    f"Session 已结束 (status={session_status})，请从数据库读取历史记录"
                )
            )
        
        # 初始化格式适配器
        adapter = None
        if format == "zeno":
            from core.events.adapters.zeno import ZenOAdapter
            adapter = ZenOAdapter(conversation_id=status_data.get("conversation_id"))
            logger.info("📋 重连使用 ZenO 格式适配器")
        
        async def reconnect_event_generator():
            """重连事件生成器"""
            try:
                # 🎯 第1步：发送重连信息（包含上下文）
                reconnect_info = {
                    "type": "reconnect_info",
                    "data": {
                        "session_id": session_id,
                        "conversation_id": status_data.get("conversation_id"),
                        "message_id": status_data.get("message_id"),
                        "user_id": status_data.get("user_id"),
                        "status": session_status,
                        "last_event_seq": status_data.get("last_event_seq", 0),
                        "start_time": status_data.get("start_time"),
                        "message_preview": status_data.get("message_preview", "")
                    },
                    "timestamp": datetime.now().isoformat()
                }
                
                yield f"event: reconnect_info\n"
                yield f"data: {json.dumps(reconnect_info, ensure_ascii=False)}\n\n"
                
                logger.info(f"📤 已发送 reconnect_info: conversation_id={status_data.get('conversation_id')}")
                
                # 🎯 第2步：获取并推送历史事件（断点补偿）
                history_events = await session_service.get_session_events(
                    session_id=session_id,
                    after_id=after_seq or 0,
                    limit=10000  # 获取所有历史事件
                )
                
                if history_events:
                    logger.info(f"📤 推送 {len(history_events)} 个历史事件")
                    for event in history_events:
                        # 格式转换
                        if adapter:
                            transformed_event = adapter.transform(event)
                            if transformed_event is None:
                                continue
                            event = transformed_event
                        
                        event_type = event.get("type", "message")
                        event_uuid = event.get("event_uuid", "") or event.get("timestamp", "")
                        
                        yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                
                # 🎯 第3步：订阅 Pub/Sub 实时推送新事件
                redis = session_service.redis
                last_seq = after_seq or 0
                if history_events:
                    # 更新 last_seq 为历史事件中的最大序号
                    last_seq = max(
                        e.get("seq", 0) for e in history_events
                    ) if history_events else last_seq
                
                logger.info(f"📡 开始订阅实时事件流: session_id={session_id}, after_seq={last_seq}")
                
                async for event in redis.subscribe_events(
                    session_id=session_id,
                    after_id=last_seq,
                    timeout=300  # 5 分钟超时
                ):
                    # 格式转换
                    if adapter:
                        transformed_event = adapter.transform(event)
                        if transformed_event is None:
                            continue
                        event = transformed_event
                    
                    event_type = event.get("type", "message")
                    event_uuid = event.get("event_uuid", "") or event.get("timestamp", "")
                    
                    yield f"id: {event_uuid}\n"
                    yield f"event: {event_type}\n"
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                    
                    # 检查是否结束
                    if event_type in ["session_end", "message_complete", "message.assistant.done"]:
                        break
                
                # 发送完成事件
                yield f"event: done\n"
                yield f"data: {{}}\n\n"
                logger.info(f"✅ SSE 重连流结束: session_id={session_id}")
                
            except asyncio.CancelledError:
                logger.warning(f"⚠️ SSE 重连流被取消: session_id={session_id}")
                raise
            except Exception as e:
                logger.error(f"❌ SSE 重连流错误: {str(e)}", exc_info=True)
                error_response = create_error_response(
                    ErrorCode.INTERNAL_ERROR,
                    sanitize_error_message(e)
                )
                yield f"event: error\n"
                yield f"data: {json.dumps(error_response, ensure_ascii=False)}\n\n"
        
        return StreamingResponse(
            reconnect_event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            }
        )
    
    except HTTPException:
        raise
    except SessionNotFoundError as e:
        logger.warning(f"⚠️ Session 不存在: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=create_error_response(
                ErrorCode.SESSION_NOT_FOUND,
                "Session 不存在或已过期"
            )
        )
    except Exception as e:
        logger.error(f"❌ SSE 重连错误: {str(e)}", exc_info=True)
        safe_message = sanitize_error_message(e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=create_error_response(
                ErrorCode.INTERNAL_ERROR,
                safe_message
            )
        )


# ==================== Session 状态查询接口 ====================

@router.get("/session/{session_id}/status", response_model=APIResponse[Dict])
async def get_session_status(session_id: str):
    """
    查询 Session 状态（用于断线重连判断）
    
    ## 使用场景
    用户刷新页面后，前端需要判断：
    1. Session 是否还在运行？
    2. 当前进度如何？
    3. 最后一个事件ID是多少？
    
    ## 参数
    - **session_id**: Session ID
    
    ## 返回
    ```json
    {
      "session_id": "sess_abc123",
      "user_id": "user_001",
      "conversation_id": "conv_abc",
      "message_id": "msg_xyz",
      "status": "running",          # running/completed/failed/timeout
      "last_event_id": 250,
      "start_time": "2023-12-24T12:00:00Z",
      "last_heartbeat": "2023-12-24T12:05:30Z",
      "progress": 0.6,
      "total_turns": 5,
      "message_preview": "帮我生成PPT..."
    }
    ```
    
    ## 状态说明
    - **running**: 正在运行，可以重连
    - **completed**: 已完成，可以获取完整结果
    - **failed**: 执行失败
    - **timeout**: 超时（超过60秒无心跳）
    """
    try:
        logger.info(f"📨 查询 Session 状态: session_id={session_id}")
        
        # 调用 Service 层（异步）
        status_data = await session_service.get_session_status(session_id)
        
        logger.info(f"✅ Session 状态: {status_data.get('status')}")
        
        return APIResponse(
            code=200,
            message="success",
            data=status_data
        )
    
    except SessionNotFoundError as e:
        logger.warning(f"⚠️ Session 不存在: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=create_error_response(
                ErrorCode.SESSION_NOT_FOUND,
                "Session 不存在或已过期"
            )
        )
    except Exception as e:
        logger.error(f"❌ 查询 Session 状态错误: {str(e)}", exc_info=True)
        safe_message = sanitize_error_message(e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=create_error_response(
                ErrorCode.INTERNAL_ERROR,
                safe_message
            )
        )


@router.get("/session/{session_id}/events", response_model=APIResponse[Dict])
async def get_session_events(
    session_id: str,
    after_id: Optional[int] = Query(None, description="从哪个事件ID之后开始"),
    limit: int = Query(100, description="最多返回多少个事件", ge=1, le=1000)
):
    """
    获取 Session 的事件列表（用于断线补偿）
    
    ## 使用场景
    用户断线期间，Agent 继续产生事件。重连前需要先获取丢失的事件。
    
    ## 参数
    - **session_id**: Session ID
    - **after_id**: 从哪个事件ID之后开始（可选）
    - **limit**: 最多返回多少个事件（默认100，最大1000）
    
    ## 返回
    ```json
    {
      "session_id": "sess_abc123",
      "events": [
        {"id": 101, "type": "thinking", "data": {...}, "timestamp": "..."},
        {"id": 102, "type": "tool_call", "data": {...}, "timestamp": "..."},
        ...
      ],
      "total": 50,
      "has_more": false,
      "last_event_id": 150
    }
    ```
    
    ## 示例流程
    ```
    1. 用户上次收到事件 id=100
    2. 断线期间，Agent 产生了事件 101-150
    3. 用户重连前调用：GET /session/{id}/events?after_id=100
    4. 获取事件 101-150，渲染到界面
    5. 然后重新连接 SSE：GET /chat/stream?after_id=150
    ```
    """
    try:
        logger.info(
            f"📨 获取 Session 事件: session_id={session_id}, "
            f"after_id={after_id}, limit={limit}"
        )
        
        # 调用 Service 层（异步）
        events = await session_service.get_session_events(
            session_id=session_id,
            after_id=after_id,
            limit=limit
        )
        
        # 构建响应
        # 🔧 事件使用 seq 字段（新格式）或 id（旧格式兼容）
        last_event_id = 0
        if events:
            last_event = events[-1]
            last_event_id = last_event.get("seq", last_event.get("id", 0))
        else:
            last_event_id = after_id or 0
        
        response_data = {
            "session_id": session_id,
            "events": events,
            "total": len(events),
            "has_more": len(events) >= limit,  # 如果返回数量达到 limit，可能还有更多
            "last_event_id": last_event_id
        }
        
        logger.info(f"✅ 返回 {len(events)} 个事件")
        
        return APIResponse(
            code=200,
            message="success",
            data=response_data
        )
    
    except SessionNotFoundError as e:
        logger.warning(f"⚠️ Session 不存在: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=create_error_response(
                ErrorCode.SESSION_NOT_FOUND,
                "Session 不存在或已过期"
            )
        )
    except Exception as e:
        logger.error(f"❌ 获取 Session 事件错误: {str(e)}", exc_info=True)
        safe_message = sanitize_error_message(e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=create_error_response(
                ErrorCode.INTERNAL_ERROR,
                safe_message
            )
        )


@router.get("/user/{user_id}/sessions", response_model=APIResponse[Dict])
async def get_user_sessions(user_id: str):
    """
    获取用户的所有活跃 Session
    
    ## 使用场景
    用户刷新页面后，如果没有保存 session_id，可以通过此接口找回所有运行中的任务。
    
    ## 参数
    - **user_id**: 用户ID
    
    ## 返回
    ```json
    {
      "user_id": "user_001",
      "sessions": [
        {
          "session_id": "sess_abc123",
          "conversation_id": "conv_001",
          "message_id": "msg_001",
          "status": "running",
          "progress": 0.6,
          "start_time": "2023-12-24T12:00:00Z",
          "message_preview": "帮我生成PPT..."
        },
        {
          "session_id": "sess_def456",
          "conversation_id": "conv_002",
          "message_id": "msg_002",
          "status": "running",
          "progress": 0.3,
          "start_time": "2023-12-24T12:10:00Z",
          "message_preview": "分析数据..."
        }
      ],
      "total": 2
    }
    ```
    """
    try:
        logger.info(f"📨 获取用户的活跃 Session: user_id={user_id}")
        
        # 调用 Service 层（异步）
        sessions = await session_service.get_user_sessions(user_id)
        
        response_data = {
            "user_id": user_id,
            "sessions": sessions,
            "total": len(sessions)
        }
        
        logger.info(f"✅ 返回 {len(sessions)} 个活跃 Session")
        
        return APIResponse(
            code=200,
            message="success",
            data=response_data
        )
    
    except Exception as e:
        logger.error(f"❌ 获取用户 Session 错误: {str(e)}", exc_info=True)
        safe_message = sanitize_error_message(e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=create_error_response(
                ErrorCode.INTERNAL_ERROR,
                safe_message
            )
        )


# ==================== Session 控制接口 ====================

@router.post("/session/{session_id}/stop", response_model=APIResponse[Dict])
async def stop_session(session_id: str):
    """
    停止正在运行的 Session（用户主动中断）
    
    ## 使用场景
    用户觉得 AI 回答不满意，想要立即停止当前输出
    
    ## 参数
    - **session_id**: Session ID
    
    ## 返回
    ```json
    {
      "code": 200,
      "message": "Session 已停止",
      "data": {
        "session_id": "sess_abc123",
        "status": "stopped",
        "stopped_at": "2023-12-24T12:00:00Z"
      }
    }
    ```
    
    ## 行为
    - 在 Redis 中设置停止标志
    - Agent 执行循环会检测到标志并停止
    - 发送 `session_stopped` 事件（流式模式会收到）
    - 更新数据库状态为 "stopped"
    - 保存已生成的部分内容（不丢失）
    
    ## 注意事项
    - 停止是异步的，Agent 会在下一个检查点停止（通常在几百毫秒内）
    - 已生成的内容会被保存到数据库
    - SSE 流会收到 `session_stopped` 事件
    - 停止后可以查看部分结果
    """
    try:
        logger.info(f"📨 停止 Session 请求: session_id={session_id}")
        
        # 调用 Service 层停止 Session
        result = await session_service.stop_session(session_id)
        
        logger.info(f"✅ Session 已停止: session_id={session_id}")
        
        return APIResponse(
            code=200,
            message="Session 已停止",
            data=result
        )
    
    except SessionNotFoundError as e:
        logger.warning(f"⚠️ Session 不存在: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=create_error_response(
                ErrorCode.SESSION_NOT_FOUND,
                "Session 不存在或已过期"
            )
        )
    except Exception as e:
        logger.error(f"❌ 停止 Session 错误: {str(e)}", exc_info=True)
        safe_message = sanitize_error_message(e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=create_error_response(
                ErrorCode.INTERNAL_ERROR,
                safe_message
            )
        )


# ==================== Session 管理接口（已有，保持不变） ====================

@router.get("/session/{session_id}", response_model=APIResponse[SessionInfo])
async def get_session(session_id: str):
    """
    获取会话信息
    
    返回指定会话的详细信息，包括活跃状态、消息数量、执行计划等
    
    ## 参数
    - **session_id**: 会话ID
    
    ## 返回
    会话详细信息
    """
    try:
        logger.info(f"📨 获取会话信息: session_id={session_id}")
        
        # 调用 Service 层（异步）
        session_info = await session_service.get_session_info(session_id)
        
        response = SessionInfo(
            session_id=session_info["session_id"],
            active=session_info.get("status") == "running",
            turns=session_info.get("total_turns", 0),
            message_count=0,  # 从 Redis 状态中无法获取，设为 0
            has_plan=False,   # 从 Redis 状态中无法获取，设为 False
            start_time=session_info.get("start_time")
        )
        
        logger.info(f"✅ 会话信息已返回: session_id={session_id}")
        
        return APIResponse(
            code=200,
            message="success",
            data=response
        )
    
    except SessionNotFoundError as e:
        logger.warning(f"⚠️ 会话不存在: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=create_error_response(
                ErrorCode.SESSION_NOT_FOUND,
                "会话不存在或已过期"
            )
        )
    except Exception as e:
        logger.error(f"❌ 获取会话信息错误: {str(e)}", exc_info=True)
        safe_message = sanitize_error_message(e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=create_error_response(
                ErrorCode.INTERNAL_ERROR,
                safe_message
            )
        )


@router.delete("/session/{session_id}", response_model=APIResponse[Dict])
async def end_session(session_id: str):
    """
    结束会话
    
    结束指定会话并返回会话摘要
    
    ## 参数
    - **session_id**: 会话ID
    
    ## 返回
    会话摘要（包含轮次、消息数量、工具调用次数等）
    """
    try:
        logger.info(f"📨 结束会话请求: session_id={session_id}")
        
        # 调用 Service 层（异步）
        summary = await session_service.end_session(session_id)
        
        # 清理摘要数据
        summary = sanitize_for_json(summary)
        
        logger.info(f"✅ 会话已结束: session_id={session_id}")
        
        return APIResponse(
            code=200,
            message="会话已结束",
            data=summary
        )
    
    except SessionNotFoundError as e:
        logger.warning(f"⚠️ 会话不存在: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=create_error_response(
                ErrorCode.SESSION_NOT_FOUND,
                "会话不存在或已过期"
            )
        )
    except Exception as e:
        logger.error(f"❌ 结束会话错误: {str(e)}", exc_info=True)
        safe_message = sanitize_error_message(e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=create_error_response(
                ErrorCode.INTERNAL_ERROR,
                safe_message
            )
        )


@router.get("/sessions", response_model=APIResponse[Dict])
async def list_sessions():
    """
    列出所有活跃会话
    
    返回当前所有活跃会话的列表和统计信息
    
    ## 返回
    包含会话总数和会话列表
    """
    try:
        logger.info("📨 列出所有会话")
        
        # 调用 Service 层（异步）
        sessions = await session_service.list_sessions()
        
        logger.info(f"✅ 返回 {len(sessions)} 个会话")
        
        return APIResponse(
            code=200,
            message="success",
            data={
                "total": len(sessions),
                "sessions": sessions
            }
        )
    
    except Exception as e:
        logger.error(f"❌ 列出会话错误: {str(e)}", exc_info=True)
        safe_message = sanitize_error_message(e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=create_error_response(
                ErrorCode.INTERNAL_ERROR,
                safe_message
            )
        )
