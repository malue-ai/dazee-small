"""
WebSocket 路由层 - 聊天流式通信

职责：
- WebSocket 连接管理
- 帧协议解析（req/res/event）
- 心跳保活（tick 30s）
- Delta 节流（150ms）
- 背压控制

帧协议：
- 请求帧：{"type": "req", "id": "uuid", "method": "chat.send|chat.abort", "params": {...}}
- 响应帧：{"type": "res", "id": "uuid", "ok": true|false, "payload|error": {...}}
- 事件帧：{"type": "event", "event": "content_delta|...", "payload": {...}, "seq": N}
"""

# ==================== 标准库 ====================
import asyncio
import json
import time
from typing import Any, Dict, List, Optional
from uuid import uuid4

# ==================== 第三方库 ====================
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

# ==================== 本地模块 ====================
from logger import clear_request_context, get_logger, set_request_context
from services import get_chat_service, get_session_service
from services.agent_registry import AgentNotFoundError

# ==================== 配置初始化 ====================

logger = get_logger("ws_router")

router = APIRouter(
    prefix="/api/v1",
    tags=["websocket"],
)

# ==================== 常量 ====================

# 心跳间隔（秒）
HEARTBEAT_INTERVAL_S = 30

# Delta 节流间隔（毫秒）
DELTA_THROTTLE_MS = 150


# ==================== Delta 节流器 ====================


class DeltaThrottle:
    """
    内容增量节流器

    合并 150ms 内的 content_delta 事件，减少 WebSocket 帧数量。
    非 content_delta 事件会触发缓冲区刷新，保证事件顺序正确。

    使用示例：
        throttle = DeltaThrottle()

        # 节流 delta 事件
        if throttle.should_throttle(event):
            merged = throttle.buffer(event)
            if merged is None:
                continue  # 节流中，等待
            event = merged
        else:
            # 非 delta 事件，先刷新缓冲区
            for buffered in throttle.flush_all():
                await send(buffered)
    """

    def __init__(self, interval_ms: int = DELTA_THROTTLE_MS):
        self.interval_ms = interval_ms
        # index -> {"text": 累积文本, "delta_key": 字段名, "base": 原始事件}
        self._buffers: Dict[int, Dict[str, Any]] = {}
        self._last_sent_at: float = 0

    def should_throttle(self, event: Dict) -> bool:
        """判断事件是否需要节流"""
        return event.get("type") == "content_delta"

    def buffer(self, event: Dict) -> Optional[Dict]:
        """
        缓冲 delta 事件

        Args:
            event: content_delta 事件

        Returns:
            合并后的事件（达到节流间隔时），否则 None
        """
        data = event.get("data", {})
        if not isinstance(data, dict):
            return event

        index = data.get("index", 0)
        delta = data.get("delta", {})

        # 提取 delta 文本和类型
        delta_text, delta_key = self._extract_delta(delta)
        if not delta_text:
            return event  # 无法合并，直接返回

        # 累积到 buffer
        if index not in self._buffers:
            self._buffers[index] = {
                "text": delta_text,
                "delta_key": delta_key,
                "base": event,
            }
        else:
            self._buffers[index]["text"] += delta_text

        # 检查节流间隔
        now = time.time() * 1000
        if now - self._last_sent_at >= self.interval_ms:
            return self._pop(index)

        return None

    def flush_all(self) -> List[Dict]:
        """刷新所有缓冲区，返回待发送事件列表"""
        events = []
        for index in list(self._buffers.keys()):
            ev = self._pop(index)
            if ev:
                events.append(ev)
        return events

    def _extract_delta(self, delta: Any) -> tuple:
        """
        提取 delta 文本和字段名

        Returns:
            (delta_text, delta_key) 元组
        """
        if isinstance(delta, str):
            return delta, "text"
        if isinstance(delta, dict):
            for key in ("text", "thinking", "partial_json"):
                if key in delta:
                    return delta[key], key
        return "", ""

    def _pop(self, index: int) -> Optional[Dict]:
        """弹出指定 index 的缓冲事件，构建合并后的事件"""
        buf = self._buffers.pop(index, None)
        if not buf:
            return None

        self._last_sent_at = time.time() * 1000

        # 构建合并后的事件
        event = buf["base"].copy()
        data = event.get("data", {})
        if isinstance(data, dict):
            data = data.copy()
            delta_key = buf["delta_key"]
            original_delta = data.get("delta", {})

            if isinstance(original_delta, dict):
                data["delta"] = {
                    "type": original_delta.get("type", delta_key),
                    delta_key: buf["text"],
                }
            elif isinstance(original_delta, str):
                data["delta"] = buf["text"]

            event["data"] = data

        return event


# ==================== WebSocket 端点 ====================


@router.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    """
    WebSocket 聊天端点

    支持的方法：
    - chat.send: 发送聊天消息（触发流式事件推送）
    - chat.abort: 中止当前聊天

    事件类型（沿用 SSE 事件格式）：
    - session_start, conversation_start, message_start
    - content_start, content_delta, content_stop
    - message_delta, message_stop
    - session_end, error
    - tick（心跳，30s 间隔）
    """
    await websocket.accept()
    conn_id = str(uuid4())[:8]

    logger.info("WebSocket 已连接", extra={"conn_id": conn_id})

    # 连接状态
    closed = False
    active_stream_task: Optional[asyncio.Task] = None

    # ==================== 内部发送方法 ====================

    async def safe_send(data: Dict) -> bool:
        """安全发送 JSON 数据"""
        nonlocal closed
        if closed:
            return False
        try:
            await websocket.send_json(data)
            return True
        except Exception as e:
            logger.debug("发送失败", extra={"conn_id": conn_id, "error": str(e)})
            closed = True
            return False

    async def send_response(req_id: str, ok: bool, payload: Any = None, error: Dict = None):
        """发送响应帧"""
        frame: Dict[str, Any] = {"type": "res", "id": req_id, "ok": ok}
        if ok:
            frame["payload"] = payload or {}
        else:
            frame["error"] = error or {"code": "UNKNOWN", "message": "未知错误"}
        await safe_send(frame)

    async def send_event(event_name: str, payload: Any, seq: int):
        """发送事件帧"""
        await safe_send({
            "type": "event",
            "event": event_name,
            "payload": payload,
            "seq": seq,
        })

    # ==================== 启动心跳 ====================

    heartbeat_task = asyncio.create_task(
        _heartbeat_loop(safe_send, lambda: closed)
    )

    # ==================== 主循环 ====================

    try:
        while not closed:
            try:
                raw = await websocket.receive_text()
            except WebSocketDisconnect:
                break
            except Exception:
                break

            # 解析帧
            try:
                frame = json.loads(raw)
            except json.JSONDecodeError as e:
                logger.warning("JSON 解析失败", extra={"conn_id": conn_id, "error": str(e)})
                continue

            frame_type = frame.get("type")

            if frame_type == "req":
                method = frame.get("method", "")
                req_id = frame.get("id", str(uuid4()))
                params = frame.get("params", {})

                if method == "chat.send":
                    # 取消之前的流任务
                    if active_stream_task and not active_stream_task.done():
                        active_stream_task.cancel()
                        try:
                            await active_stream_task
                        except (asyncio.CancelledError, Exception):
                            pass

                    active_stream_task = asyncio.create_task(
                        _handle_chat_send(
                            conn_id, req_id, params,
                            send_response, send_event,
                        )
                    )

                elif method == "chat.abort":
                    await _handle_chat_abort(
                        conn_id, req_id, params, send_response
                    )

                else:
                    await send_response(req_id, False, error={
                        "code": "METHOD_NOT_FOUND",
                        "message": f"未知方法: {method}",
                    })

            elif frame_type == "ping":
                await safe_send({"type": "pong", "ts": int(time.time() * 1000)})

    except Exception as e:
        logger.error(
            "WebSocket 错误", extra={"conn_id": conn_id, "error": str(e)}, exc_info=True
        )

    finally:
        closed = True
        heartbeat_task.cancel()

        # 取消活跃的流任务
        if active_stream_task and not active_stream_task.done():
            active_stream_task.cancel()
            try:
                await active_stream_task
            except (asyncio.CancelledError, Exception):
                pass

        logger.info("WebSocket 已断开", extra={"conn_id": conn_id})


# ==================== 心跳 ====================


async def _heartbeat_loop(safe_send, is_closed):
    """
    心跳保活循环（每 30s 发送 tick 事件）

    Args:
        safe_send: 安全发送方法
        is_closed: 判断连接是否已关闭的函数
    """
    try:
        while not is_closed():
            await asyncio.sleep(HEARTBEAT_INTERVAL_S)
            if is_closed():
                break
            await safe_send({
                "type": "event",
                "event": "tick",
                "payload": {"ts": int(time.time() * 1000)},
                "seq": 0,
            })
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.debug("心跳循环异常", extra={"error": str(e)})


# ==================== 请求处理 ====================


async def _handle_chat_send(
    conn_id: str,
    req_id: str,
    params: Dict,
    send_response,
    send_event,
):
    """
    处理 chat.send 请求

    流程：
    1. 验证参数
    2. 调用 ChatService.chat() 获取事件流
    3. 发送确认响应
    4. 流式转发事件（带 Delta 节流）

    Args:
        conn_id: 连接标识
        req_id: 请求 ID
        params: 请求参数
        send_response: 发送响应帧方法
        send_event: 发送事件帧方法
    """
    chat_service = get_chat_service()

    # 参数提取
    message = params.get("message", "")
    user_id = params.get("user_id", "")
    conversation_id = params.get("conversation_id")
    message_id = params.get("message_id")
    agent_id = params.get("agent_id")
    background_tasks = params.get("background_tasks")
    files = params.get("files")
    variables = params.get("variables")

    if not message or not user_id:
        await send_response(req_id, False, error={
            "code": "VALIDATION_ERROR",
            "message": "message 和 user_id 为必填参数",
        })
        return

    # 日志上下文
    set_request_context(
        user_id=user_id,
        conversation_id=conversation_id or "",
        message_id=message_id or "",
    )

    logger.info(
        "收到 chat.send",
        extra={
            "conn_id": conn_id,
            "user_id": user_id,
            "agent_id": agent_id or "默认",
            "message_preview": str(message)[:50],
        },
    )

    try:
        # 立即确认请求已接收（不让前端干等 Agent 初始化）
        await send_response(req_id, True, payload={"status": "streaming"})

        # 调用 ChatService（返回异步生成器，可能涉及 Agent 加载/意图分析）
        event_stream = await chat_service.chat(
            message=message,
            user_id=user_id,
            conversation_id=conversation_id,
            message_id=message_id,
            stream=True,
            background_tasks=background_tasks,
            files=files,
            variables=variables,
            agent_id=agent_id,
            output_format="zenflux",
        )

        # 流式转发事件
        throttle = DeltaThrottle()
        seq = 0

        async for event in event_stream:
            event_type = event.get("type", "")
            seq += 1

            # Delta 节流
            if throttle.should_throttle(event):
                merged = throttle.buffer(event)
                if merged is None:
                    continue  # 节流中，等待下次发送
                event = merged
            else:
                # 非 delta 事件，先刷新缓冲区
                for buffered in throttle.flush_all():
                    await send_event(
                        buffered.get("type", "content_delta"), buffered, seq
                    )
                    seq += 1

            # 发送事件帧
            await send_event(event_type, event, seq)

            # 流结束
            if event_type in ("message_stop", "session.stopped"):
                # 刷新剩余缓冲
                for buffered in throttle.flush_all():
                    seq += 1
                    await send_event(
                        buffered.get("type", "content_delta"), buffered, seq
                    )
                break

        logger.info("chat.send 流式完成", extra={"conn_id": conn_id})

    except AgentNotFoundError as e:
        await send_response(req_id, False, error={
            "code": "AGENT_NOT_FOUND",
            "message": str(e),
        })
    except asyncio.CancelledError:
        logger.info("chat.send 流被取消", extra={"conn_id": conn_id})
    except Exception as e:
        logger.error(
            "chat.send 失败",
            extra={"conn_id": conn_id, "error": str(e)},
            exc_info=True,
        )
        await send_response(req_id, False, error={
            "code": "INTERNAL_ERROR",
            "message": "对话处理失败，请稍后重试",
        })
    finally:
        clear_request_context()


async def _handle_chat_abort(
    conn_id: str,
    req_id: str,
    params: Dict,
    send_response,
):
    """
    处理 chat.abort 请求

    Args:
        conn_id: 连接标识
        req_id: 请求 ID
        params: 请求参数（需包含 session_id）
        send_response: 发送响应帧方法
    """
    session_id = params.get("session_id", "")

    if not session_id:
        await send_response(req_id, False, error={
            "code": "VALIDATION_ERROR",
            "message": "session_id 为必填参数",
        })
        return

    try:
        session_service = get_session_service()
        result = await session_service.stop_session(session_id)

        logger.info("chat.abort 成功", extra={"conn_id": conn_id, "session_id": session_id})
        await send_response(req_id, True, payload=result)

    except Exception as e:
        logger.error(
            "chat.abort 失败",
            extra={"conn_id": conn_id, "error": str(e)},
            exc_info=True,
        )
        await send_response(req_id, False, error={
            "code": "INTERNAL_ERROR",
            "message": "停止失败",
        })
