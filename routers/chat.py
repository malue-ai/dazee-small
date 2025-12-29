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
async def chat(request: ChatRequest, background_tasks: BackgroundTasks):
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
    
    详细协议见：`docs/03-SSE-EVENT-PROTOCOL.md`
    
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
                detail="user_id 是必填参数"
            )
        
        # 记录请求信息
        logger.info(
            f"📨 收到{'流式' if request.stream else '同步'}聊天请求: "
            f"user_id={request.user_id}, "
            f"message_id={request.message_id}, "
            f"conversation_id={request.conversation_id}, "
            f"message={request.message[:50]}..."
        )
        
        # 记录额外的上下文信息
        if request.variables:
            logger.debug(f"📍 前端变量: {request.variables}")
        if request.file:
            logger.info(f"📎 附件: {request.file}")
        if request.background_task:
            logger.info(f"⏱️ 后台任务模式")
        
        # ===== 流式模式（默认） =====
        if request.stream:
            # 直接返回 SSE 流
            async def event_generator():
                """
                生成 SSE 事件流（符合 SSE 协议标准）
                
                SSE 格式：
                id: 1
                event: message_start
                data: {"id":1,"session_id":"sess_xxx","data":{...},"timestamp":"..."}
                
                """
                session_id = None
                try:
                    # 调用 Service 层流式对话
                    async for event in chat_service.chat_stream(
                        message=request.message,
                        user_id=request.user_id,
                        conversation_id=request.conversation_id,
                        message_id=request.message_id
                    ):
                        # 提取事件类型（用于 SSE event: 字段）
                        event_type = event.get("type", "message")
                        event_seq = event.get("seq", 0)  # 使用 seq 作为 SSE id
                        
                        # 记录 session_id（从第一个事件获取）
                        if not session_id:
                            session_id = event.get("session_id")
                        
                        # 🎯 SSE 协议格式输出
                        # id: 使用 seq（session 内序号，从 1 开始）
                        yield f"id: {event_seq}\n"
                        # event: 事件类型（前端可以 addEventListener(type, ...)）
                        yield f"event: {event_type}\n"
                        # data: JSON 数据（包含 event_uuid, seq, 和所有上下文字段）
                        yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                    
                    # 发送完成事件
                    yield f"event: done\n"
                    yield f"data: {{}}\n\n"
                
                except AgentExecutionError as e:
                    logger.error(f"❌ 流式对话错误: {str(e)}")
                    yield f"event: error\n"
                    yield f"data: {json.dumps({'message': str(e)}, ensure_ascii=False)}\n\n"
                except Exception as e:
                    logger.error(f"❌ 流式对话错误: {str(e)}", exc_info=True)
                    yield f"event: error\n"
                    yield f"data: {json.dumps({'message': f'内部错误: {str(e)}'}, ensure_ascii=False)}\n\n"
            
            return StreamingResponse(
                event_generator(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",  # 禁用 Nginx 缓冲
                }
            )
        
        # ===== 同步模式（立即返回 task_id） =====
        else:
            # 调用 Service 层同步对话（启动后台任务）
            result = await chat_service.chat_sync(
                message=request.message,
                user_id=request.user_id,
                conversation_id=request.conversation_id,
                message_id=request.message_id,
                verbose=False
            )
            
            # 后台清理任务
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
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    except Exception as e:
        logger.error(f"❌ 聊天接口错误: {str(e)}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"内部错误: {str(e)}")



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
        
        # 调用 Service 层
        status_data = session_service.get_session_status(session_id)
        
        logger.info(f"✅ Session 状态: {status_data.get('status')}")
        
        return APIResponse(
            code=200,
            message="success",
            data=status_data
        )
    
    except SessionNotFoundError as e:
        logger.warning(f"⚠️ Session 不存在: {str(e)}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"❌ 查询 Session 状态错误: {str(e)}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


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
        
        # 调用 Service 层
        events = session_service.get_session_events(
            session_id=session_id,
            after_id=after_id,
            limit=limit
        )
        
        # 构建响应
        last_event_id = events[-1]["id"] if events else (after_id or 0)
        
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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"❌ 获取 Session 事件错误: {str(e)}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


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
        
        # 调用 Service 层
        sessions = session_service.get_user_sessions(user_id)
        
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
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


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
        
        # 调用 Service 层
        session_info = session_service.get_session_info(session_id)
        
        response = SessionInfo(
            session_id=session_info["session_id"],
            active=session_info["active"],
            turns=session_info["turns"],
            message_count=session_info["message_count"],
            has_plan=session_info["has_plan"],
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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"❌ 获取会话信息错误: {str(e)}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


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
        
        # 调用 Service 层
        summary = session_service.end_session(session_id)
        
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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"❌ 结束会话错误: {str(e)}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


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
        
        # 调用 Service 层
        sessions = session_service.list_sessions()
        
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
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

