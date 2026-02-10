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
- SSE 断线重连
"""

# ==================== 标准库 ====================
import asyncio
import functools
import json
import time
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, Optional, TypeVar

# ==================== 第三方库 ====================
from fastapi import APIRouter, BackgroundTasks, Body, HTTPException, Query, status
from fastapi.responses import StreamingResponse

# ==================== 本地模块 ====================
from logger import get_logger, set_request_context
from models.api import APIResponse
from models.chat import (
    ChatRequest,
    ChatResponse,
    RefineRequest,
    SessionInfo,
    StreamEvent,
)
from services import (
    AgentExecutionError,
    SessionNotFoundError,
    get_chat_service,
    get_conversation_service,
    get_session_service,
)
from services.agent_registry import AgentNotFoundError

# ==================== 配置初始化 ====================

logger = get_logger("chat_router")

router = APIRouter(
    prefix="/api/v1",
    tags=["chat"],
    responses={404: {"description": "Not found"}},
)

# 获取服务实例（单例）
chat_service = get_chat_service()
session_service = get_session_service()
conversation_service = get_conversation_service()


# ==================== 错误码定义 ====================


class ErrorCode:
    """统一错误码定义"""

    VALIDATION_ERROR = "VALIDATION_ERROR"  # 参数验证失败
    SESSION_NOT_FOUND = "SESSION_NOT_FOUND"  # Session 不存在
    AGENT_NOT_FOUND = "AGENT_NOT_FOUND"  # Agent 不存在
    AGENT_ERROR = "AGENT_ERROR"  # Agent 执行错误
    EXTERNAL_SERVICE_ERROR = "EXTERNAL_SERVICE"  # 外部服务错误（LLM 等）
    INTERNAL_ERROR = "INTERNAL_ERROR"  # 内部错误


# ==================== 辅助函数 ====================


def create_error_response(code: str, message: str, detail: str = None) -> Dict[str, Any]:
    """
    创建统一的错误响应格式

    Args:
        code: 错误码
        message: 用户可见的错误信息
        detail: 详细错误信息（仅用于日志，不返回给用户）

    Returns:
        错误响应字典
    """
    return {"code": code, "message": message, "timestamp": datetime.now().isoformat()}


def sanitize_error_message(error: Exception) -> str:
    """
    清理错误信息，隐藏敏感内容

    Args:
        error: 异常对象

    Returns:
        安全的错误信息
    """
    error_str = str(error)

    # 敏感关键词列表
    sensitive_keywords = [
        "api_key",
        "token",
        "password",
        "secret",
        "credential",
        "authorization",
        "bearer",
        "sk-",
        "pk-",
    ]

    # 检查是否包含敏感信息
    error_lower = error_str.lower()
    for keyword in sensitive_keywords:
        if keyword in error_lower:
            return "系统内部错误，请稍后重试"

    # 截断过长的错误信息
    if len(error_str) > 200:
        return error_str[:200] + "..."

    return error_str


def sanitize_for_json(obj: Any) -> Any:
    """
    清理对象使其可以 JSON 序列化
    处理 Enum、ToolType 等不可序列化的对象

    Args:
        obj: 待清理的对象

    Returns:
        可序列化的对象
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
        try:
            return str(obj)
        except Exception:
            return None


# ==================== 异常处理装饰器 ====================

# 泛型类型变量
T = TypeVar("T")


def handle_exceptions(operation_name: str):
    """
    统一异常处理装饰器

    Args:
        operation_name: 操作名称，用于日志记录

    Usage:
        @handle_exceptions("获取会话状态")
        async def get_session_status(...):
            ...
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            try:
                return await func(*args, **kwargs)
            except HTTPException:
                # HTTPException 直接向上抛出
                raise
            except SessionNotFoundError as e:
                logger.warning(f"⚠️ Session 不存在: {str(e)}")
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=create_error_response(
                        ErrorCode.SESSION_NOT_FOUND, "Session 不存在或已过期"
                    ),
                )
            except AgentNotFoundError as e:
                logger.warning(f"⚠️ Agent 不存在: {str(e)}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=create_error_response(ErrorCode.AGENT_NOT_FOUND, str(e)),
                )
            except AgentExecutionError as e:
                logger.error(f"❌ {operation_name}执行失败: {str(e)}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=create_error_response(ErrorCode.AGENT_ERROR, "对话处理失败，请稍后重试"),
                )
            except ConnectionError as e:
                logger.error(f"❌ {operation_name}连接错误: {str(e)}", exc_info=True)
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=create_error_response(
                        ErrorCode.EXTERNAL_SERVICE_ERROR, "服务暂时不可用，请稍后重试"
                    ),
                )
            except Exception as e:
                logger.error(f"❌ {operation_name}错误: {str(e)}", exc_info=True)
                safe_message = sanitize_error_message(e)
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=create_error_response(ErrorCode.INTERNAL_ERROR, safe_message),
                )

        return wrapper

    return decorator


# ==================== SSE 错误事件生成 ====================


def create_sse_error_event(
    error_type: str, code: str, message: str, message_id: str = "", retryable: bool = False
) -> Dict[str, Any]:
    """
    创建 SSE 错误事件

    Args:
        error_type: 错误类型（business/network/unknown）
        code: 错误码
        message: 错误信息
        message_id: 消息 ID
        retryable: 是否可重试

    Returns:
        SSE 错误事件字典
    """
    return {
        "type": "error",
        "message_id": message_id,
        "timestamp": int(time.time() * 1000),
        "error": {"type": error_type, "code": code, "message": message, "retryable": retryable},
    }


# ==================== 聊天接口 ====================


@router.post("/chat")
async def chat(
    request: ChatRequest,
    background_tasks: BackgroundTasks,
    format: str = Query(
        "zenflux", description="事件输出格式，默认 zenflux"
    ),
):
    """
    统一聊天接口（支持流式和同步两种模式）

    根据 `stream` 参数自动选择返回模式：
    - `stream=true`: 流式模式（SSE），实时推送事件
    - `stream=false`: 同步模式，立即返回 task_id，客户端轮询查询结果

    ---

    ## 请求参数

    | 参数 | 类型 | 必填 | 别名 | 说明 |
    |------|------|------|------|------|
    | **message** | string | ✅ | - | 用户消息内容 |
    | **user_id** | string | ✅ | userId | 用户ID，用于多租户隔离、知识库分区、记忆检索 |
    | **message_id** | string | ❌ | messageId | 消息ID，用于追踪单条消息，前端生成 |
    | **conversation_id** | string | ❌ | conversationId | 对话线程ID，用于多轮对话上下文延续 |
    | **agent_id** | string | ❌ | agentId, intentId | 指定 Agent 实例（对应 instances/ 目录名），不传使用默认 |
    | **stream** | boolean | ❌ | - | 是否使用流式输出，默认 `true` |
    | **background_tasks** | string[] | ❌ | backgroundTasks | 后台任务列表，如 `["title_generation"]` |
    | **files** | FileReference[] | ❌ | - | 文件引用列表，支持 file_id 或 file_url |
    | **variables** | object | ❌ | - | 前端上下文变量，用于个性化响应 |

    ### variables 字段说明

    前端可传入的上下文变量，会注入到 System Prompt 中：

    ```json
    {
      "location": "北京市朝阳区",
      "timezone": "Asia/Shanghai",
      "locale": "zh-CN",
      "device": "mobile",
      "currentTime": "2024-01-15T10:30:00+08:00"
    }
    ```

    ### files 字段说明

    支持两种方式引用文件：

    ```json
    [
      { "file_id": "file_abc123" },
      {
        "file_url": "https://example.com/doc.pdf",
        "file_name": "报告.pdf",
        "file_size": 102400,
        "file_type": "application/pdf"
      }
    ]
    ```

    ---

    ## Query 参数

    | 参数 | 类型 | 默认值 | 说明 |
    |------|------|--------|------|
    | **format** | string | `zenflux` | 事件输出格式，默认 zenflux |

    ---

    ## 模式1：流式模式 (`stream=true`)

    **返回类型**: `text/event-stream` (SSE)

    **使用场景**: 需要实时看到 Agent 的思考过程和执行步骤

    **特点**:
    - Agent 在后台运行，事件写入内存存储
    - SSE 实时读取事件并推送
    - 支持断线重连（从存储补偿丢失的事件）

    ### SSE 事件类型

    | 事件类型 | 说明 |
    |----------|------|
    | `message_start` | 消息开始，包含 session_id、conversation_id |
    | `intent` | 意图识别结果（intent_id, intent_name, complexity） |
    | `content_start` | 内容块开始（text/thinking/tool_use/tool_result） |
    | `content_delta` | 内容增量（流式文本） |
    | `content_stop` | 内容块结束 |
    | `message_stop` | 消息结束，包含完整响应和 usage 统计 |
    | `error` | 错误事件 |

    ### SSE 示例

    ```
    data: {"type":"message_start","seq":1,"session_id":"sess_xxx","conversation_id":"conv_xxx"}

    data: {"type":"intent","seq":2,"content":{"intent_id":1,"intent_name":"信息查询","complexity":"simple"}}

    data: {"type":"content_start","seq":3,"content_type":"text"}

    data: {"type":"content_delta","seq":4,"delta":{"type":"text","text":"你好"}}

    data: {"type":"content_stop","seq":5}

    data: {"type":"message_stop","seq":6,"usage":{"input_tokens":100,"output_tokens":50}}
    ```

    ---

    ## 模式2：同步模式 (`stream=false`)

    **返回类型**: `application/json`

    **使用场景**: 不需要实时反馈，只关心最终结果（适用于异步任务调度）

    **响应示例**:
    ```json
    {
      "code": 200,
      "message": "任务已启动",
      "data": {
        "task_id": "sess_abc123",
        "conversation_id": "conv_xyz",
        "status": "running"
      }
    }
    ```

    ---

    ## 错误码

    | HTTP Status | 错误码 | 说明 |
    |-------------|--------|------|
    | 400 | AGENT_NOT_FOUND | 指定的 Agent 不存在 |
    | 500 | AGENT_ERROR | Agent 执行失败 |
    | 503 | EXTERNAL_SERVICE_ERROR | 外部服务不可用 |
    | 500 | INTERNAL_ERROR | 内部错误 |
    """
    try:
        # 设置日志上下文（用于追踪）
        set_request_context(
            user_id=request.user_id,
            conversation_id=request.conversation_id or "",
            message_id=request.message_id or "",
        )

        # 记录请求信息
        logger.info(
            f"📨 收到{'流式' if request.stream else '同步'}聊天请求: "
            f"agent_id={request.agent_id or '默认'}, "
            f"message={str(request.message)[:50]}..."
        )

        # 记录额外的上下文信息
        if request.variables:
            logger.debug(f"📍 前端变量: {request.variables}")
        if request.files:
            logger.info(f"📎 文件: {len(request.files)} 个")
        if request.background_tasks:
            logger.info(f"⏱️ 后台任务: {request.background_tasks}")

        # ===== 流式模式（默认） =====
        if request.stream:
            return await _handle_stream_chat(request, format)

        # ===== 同步模式 =====
        else:
            return await _handle_sync_chat(request, background_tasks)

    except HTTPException:
        raise
    except AgentNotFoundError as e:
        logger.warning(f"⚠️ Agent 不存在: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=create_error_response(ErrorCode.AGENT_NOT_FOUND, str(e)),
        )
    except AgentExecutionError as e:
        logger.error(f"❌ 对话执行失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=create_error_response(ErrorCode.AGENT_ERROR, "对话处理失败，请稍后重试"),
        )
    except ConnectionError as e:
        logger.error(f"❌ 连接错误: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=create_error_response(
                ErrorCode.EXTERNAL_SERVICE_ERROR, "服务暂时不可用，请稍后重试"
            ),
        )
    except Exception as e:
        logger.error(f"❌ 聊天接口错误: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=create_error_response(ErrorCode.INTERNAL_ERROR, sanitize_error_message(e)),
        )


async def _handle_stream_chat(request: ChatRequest, format: str) -> StreamingResponse:
    """
    处理流式聊天请求

    Args:
        request: 聊天请求
        format: 事件格式

    Returns:
        SSE 流式响应

    注意：
        事件格式转换和 seq 编号已在 EventDispatcher 中完成，
        这里直接输出存储中的事件即可。
    """
    logger.info(f"📋 使用 {format} 格式输出事件")

    async def event_generator():
        """生成 SSE 事件流（直接输出，无需转换）"""
        try:
            async for event in await chat_service.chat(
                message=request.message,
                user_id=request.user_id,
                conversation_id=request.conversation_id,
                message_id=request.message_id,
                stream=True,
                background_tasks=request.background_tasks,
                files=request.files,
                variables=request.variables,
                agent_id=request.agent_id,
                output_format=format,  # 传递给 chat_service，让 EventDispatcher 处理转换
            ):
                # 事件已经是正确的格式（由 EventDispatcher 转换），直接输出
                event_type = event.get("type", "")

                # 事件输出
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

                # 🔧 检测流结束事件，发送 SSE 协议层面的 event: done
                if event_type in ("message_stop", "session.stopped"):
                    yield "event: done\ndata: {}\n\n"
                    # 🔧 修复：收到 done 事件后必须终止循环，防止后续异步事件（如外部计费系统错误）被输出
                    break

        except asyncio.CancelledError:
            logger.debug(f"📡 SSE 连接被客户端断开: user_id={request.user_id}")
            return
        except GeneratorExit:
            logger.debug(f"📡 SSE 生成器关闭: user_id={request.user_id}")
            return
        except AgentExecutionError as e:
            logger.error(f"❌ 流式对话错误: {str(e)}")
            error_event = create_sse_error_event(
                "business",
                "AGENT_ERROR",
                "对话处理失败，请稍后重试",
                request.message_id or "",
                True,
            )
            yield f"data: {json.dumps(error_event, ensure_ascii=False)}\n\n"
        except ConnectionError as e:
            logger.error(f"❌ 连接错误: {str(e)}", exc_info=True)
            error_event = create_sse_error_event(
                "network",
                "CONNECTION_ERROR",
                "服务连接失败，请稍后重试",
                request.message_id or "",
                True,
            )
            yield f"data: {json.dumps(error_event, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.error(f"❌ 流式对话错误: {str(e)}", exc_info=True)
            error_event = create_sse_error_event(
                "unknown",
                "INTERNAL_ERROR",
                sanitize_error_message(e),
                request.message_id or "",
                False,
            )
            yield f"data: {json.dumps(error_event, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


async def _handle_sync_chat(request: ChatRequest, background_tasks: BackgroundTasks) -> APIResponse:
    """
    处理同步聊天请求

    Args:
        request: 聊天请求
        background_tasks: 后台任务

    Returns:
        API 响应（包含 task_id）
    """
    result = await chat_service.chat(
        message=request.message,
        user_id=request.user_id,
        conversation_id=request.conversation_id,
        message_id=request.message_id,
        stream=False,
        background_tasks=request.background_tasks,
        files=request.files,
        variables=request.variables,
        agent_id=request.agent_id,
    )

    # 添加后台清理任务
    background_tasks.add_task(session_service.cleanup_inactive_sessions)

    logger.info(f"✅ 任务已启动: task_id={result['task_id']}")

    return APIResponse(code=200, message=result.get("message", "任务已启动"), data=result)


# ==================== Session 控制接口 ====================


@router.post("/session/{session_id}/stop", response_model=APIResponse[Dict])
@handle_exceptions("停止 Session")
async def stop_session(session_id: str):
    """
    停止正在运行的 Session（用户主动中断）

    ## 参数
    - **session_id**: Session ID

    ## 返回
    ```json
    {
      "session_id": "sess_abc123",
      "status": "stopped",
      "stopped_at": "2023-12-24T12:00:00Z"
    }
    ```

    ## 行为
    - 设置内存停止标志
    - Agent 执行循环会检测到标志并停止
    - 发送 `session_stopped` 事件
    - 保存已生成的部分内容
    """
    logger.info(f"📨 停止 Session 请求: session_id={session_id}")

    result = await session_service.stop_session(session_id)

    logger.info(f"✅ Session 已停止: session_id={session_id}")

    return APIResponse(code=200, message="Session 已停止", data=result)


@router.post("/session/{session_id}/confirm_continue", response_model=APIResponse[Dict])
@handle_exceptions("确认继续长任务")
async def confirm_continue_session(session_id: str):
    """
    用户确认继续长任务（V11 终止策略）

    当执行器发出 long_running_confirm 事件后，前端调用此接口表示用户点击「继续」。
    """
    logger.info(f"📨 长任务确认继续: session_id={session_id}")
    session_service.confirm_long_running(session_id)
    return APIResponse(code=200, message="已确认继续", data={"session_id": session_id})


@router.post("/session/{session_id}/hitl_confirm", response_model=APIResponse[Dict])
@handle_exceptions("HITL 危险操作确认")
async def submit_hitl_confirm(session_id: str, approved: bool = True):
    """
    用户确认/拒绝危险操作（V11.1 HITL 安全保障）

    当执行器检测到危险工具调用（如 delete、overwrite）并发出 hitl_confirm 事件后，
    前端调用此接口提交用户的确认/拒绝决策。

    - approved=True: 用户批准执行危险操作
    - approved=False: 用户拒绝，触发 on_rejection 策略（回滚/停止/询问回滚）
    """
    logger.info(f"📨 HITL 确认: session_id={session_id}, approved={approved}")
    session_service.submit_hitl_confirm(session_id, approved)
    action = "已批准执行" if approved else "已拒绝，触发回退策略"
    return APIResponse(code=200, message=action, data={"session_id": session_id, "approved": approved})


@router.post("/session/{session_id}/backtrack_confirm", response_model=APIResponse[Dict])
@handle_exceptions("回溯耗尽确认")
async def submit_backtrack_confirm(session_id: str, choice: str = "stop"):
    """
    用户提交回溯耗尽后的选择（V12 HITL）

    当执行器回溯次数用尽并发出 backtrack_confirm 事件后，
    前端调用此接口提交用户选择。

    - choice="retry": 重置回溯计数，继续尝试
    - choice="rollback": 触发回滚流程
    - choice="stop": 停止任务
    """
    logger.info(f"📨 回溯确认: session_id={session_id}, choice={choice}")
    session_service.submit_backtrack_confirm(session_id, choice)
    return APIResponse(
        code=200,
        message=f"回溯确认: {choice}",
        data={"session_id": session_id, "choice": choice},
    )


@router.post("/session/{session_id}/cost_confirm", response_model=APIResponse[Dict])
@handle_exceptions("费用确认")
async def submit_cost_confirm(session_id: str, choice: str = "stop"):
    """
    用户提交费用确认选择（V12 HITL 阶梯式提醒）

    当执行器检测到费用超阈值并发出 cost_limit_confirm / cost_urgent_confirm 事件后，
    前端调用此接口提交用户选择。

    - choice="continue": 确认继续执行
    - choice="stop": 停止任务
    """
    logger.info(f"📨 费用确认: session_id={session_id}, choice={choice}")
    session_service.submit_cost_confirm(session_id, choice)
    return APIResponse(
        code=200,
        message=f"费用确认: {choice}",
        data={"session_id": session_id, "choice": choice},
    )


@router.post("/session/{session_id}/intent_clarify", response_model=APIResponse[Dict])
@handle_exceptions("意图澄清")
async def submit_intent_clarify(session_id: str, text: str = ""):
    """
    用户提交意图澄清文本（V12 HITL）

    当执行器无法理解用户意图并发出 intent_clarify_request 事件后，
    前端调用此接口提交澄清内容。
    """
    logger.info(f"📨 意图澄清: session_id={session_id}, text={text[:50]}...")
    session_service.submit_intent_clarify(session_id, text)
    return APIResponse(
        code=200,
        message="意图澄清已提交",
        data={"session_id": session_id},
    )


@router.get("/session/{session_id}/rollback/preview", response_model=APIResponse[Dict])
@handle_exceptions("预览回滚变更")
async def preview_rollback(session_id: str):
    """
    预览回滚将要改变的内容（不执行任何写操作）

    返回每个快照文件与当前磁盘文件的对比：modified / deleted / unchanged。
    前端据此展示 Diff 预览，用户可选择回滚哪些文件。

    ## 参数
    - **session_id**: 会话 ID

    ## 返回
    - **files**: 文件变更列表（含 path / status / current_size / backup_size / selected）
    - **summary**: 变更统计（total / modified / deleted / unchanged）
    """
    state_mgr = session_service.get_state_manager(session_id)
    if not state_mgr:
        raise HTTPException(
            status_code=404,
            detail="无可用快照或会话已结束",
        )

    snapshot_id = state_mgr.get_snapshot_for_task(session_id)
    if not snapshot_id:
        raise HTTPException(
            status_code=404,
            detail="未找到该任务对应的快照",
        )

    preview = state_mgr.preview_rollback(snapshot_id)
    if "error" in preview:
        raise HTTPException(status_code=404, detail=preview["error"])

    return APIResponse(code=200, message="预览成功", data=preview)


@router.post("/session/{session_id}/rollback", response_model=APIResponse[Dict])
@handle_exceptions("回滚会话状态")
async def rollback_session(
    session_id: str,
    file_paths: Optional[list[str]] = Body(default=None, embed=True),
):
    """
    执行状态回滚（V11 状态一致性，支持选择性回滚）

    当任务异常或用户选择回滚时，将文件与环境恢复到任务开始前的快照。
    如果传入 file_paths 则只回滚指定文件，否则回滚全部。

    ## 参数
    - **session_id**: 会话 ID（与 execute 时使用的 session_id 一致）
    - **file_paths**: 可选，要回滚的文件路径列表（body JSON）

    ## 返回
    - **messages**: 回滚结果消息列表（如 "已恢复: /path/to/file"）
    """
    logger.info(
        f"📨 回滚请求: session_id={session_id}, "
        f"selective={file_paths is not None}, "
        f"count={len(file_paths) if file_paths else 'all'}"
    )

    state_mgr = session_service.get_state_manager(session_id)
    if not state_mgr:
        raise HTTPException(
            status_code=404,
            detail="无可用快照或会话已结束，无法回滚",
        )

    snapshot_id = state_mgr.get_snapshot_for_task(session_id)
    if not snapshot_id:
        raise HTTPException(
            status_code=404,
            detail="未找到该任务对应的快照",
        )

    if file_paths is not None:
        messages = state_mgr.rollback_selective(snapshot_id, file_paths)
    else:
        messages = state_mgr.rollback(snapshot_id)

    session_service.unregister_state_manager(session_id)

    logger.info(f"✅ 回滚完成: session_id={session_id}, 结果数={len(messages)}")

    return APIResponse(
        code=200,
        message="回滚完成",
        data={"session_id": session_id, "messages": messages},
    )


# ==================== Session 管理接口 ====================


@router.get("/session/{session_id}", response_model=APIResponse[SessionInfo])
@handle_exceptions("获取会话信息")
async def get_session(session_id: str):
    """
    获取会话信息

    ## 参数
    - **session_id**: 会话ID

    ## 返回
    会话详细信息
    """
    logger.info(f"📨 获取会话信息: session_id={session_id}")

    session_info = await session_service.get_session_info(session_id)

    response = SessionInfo(
        session_id=session_info["session_id"],
        active=session_info.get("status") == "running",
        turns=session_info.get("total_turns", 0),
        message_count=0,
        has_plan=False,
        start_time=session_info.get("start_time"),
    )

    logger.info(f"✅ 会话信息已返回: session_id={session_id}")

    return APIResponse(code=200, message="success", data=response)


@router.delete("/session/{session_id}", response_model=APIResponse[Dict])
@handle_exceptions("结束会话")
async def end_session(session_id: str):
    """
    结束会话

    ## 参数
    - **session_id**: 会话ID

    ## 返回
    会话摘要（包含轮次、消息数量、工具调用次数等）
    """
    logger.info(f"📨 结束会话请求: session_id={session_id}")

    summary = await session_service.end_session(session_id)
    summary = sanitize_for_json(summary)

    logger.info(f"✅ 会话已结束: session_id={session_id}")

    return APIResponse(code=200, message="会话已结束", data=summary)


@router.get("/sessions", response_model=APIResponse[Dict])
@handle_exceptions("列出所有会话")
async def list_sessions():
    """
    列出所有活跃会话

    ## 返回
    包含会话总数和会话列表
    """
    logger.info("📨 列出所有会话")

    sessions = await session_service.list_sessions()

    logger.info(f"✅ 返回 {len(sessions)} 个会话")

    return APIResponse(
        code=200, message="success", data={"total": len(sessions), "sessions": sessions}
    )
