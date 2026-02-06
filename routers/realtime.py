"""
Realtime Router - 实时语音通信 WebSocket 端点

提供与 OpenAI Realtime API 的 WebSocket 中转服务
"""

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from models.realtime import RealtimeConnectionInfo, Voice
from services.realtime_service import RealtimeSession, get_realtime_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/realtime", tags=["realtime"])


# ==================== HTTP 端点（会话管理） ====================


class CreateSessionRequest(BaseModel):
    """创建会话请求"""

    model: str = Field(default="gpt-4o-realtime-preview", description="模型名称")
    voice: Voice = Field(default=Voice.ALLOY, description="语音类型")
    instructions: Optional[str] = Field(default=None, description="系统指令")


class SessionResponse(BaseModel):
    """会话响应"""

    session_id: str
    model: str
    voice: str
    connected: bool
    created_at: str
    websocket_url: str


@router.get("/sessions", response_model=List[SessionResponse])
async def list_sessions():
    """
    列出所有活跃的实时会话

    Returns:
        活跃会话列表
    """
    service = get_realtime_service()
    sessions = service.list_sessions()

    return [
        SessionResponse(
            session_id=s["session_id"],
            model=s["model"],
            voice=s["voice"],
            connected=s["connected"],
            created_at=s["created_at"],
            websocket_url=f"/api/v1/realtime/ws/{s['session_id']}",
        )
        for s in sessions
    ]


@router.delete("/sessions/{session_id}")
async def close_session(session_id: str):
    """
    关闭指定的实时会话

    Args:
        session_id: 会话 ID

    Returns:
        关闭结果
    """
    service = get_realtime_service()
    success = await service.close_session(session_id)

    if not success:
        raise HTTPException(status_code=404, detail=f"会话不存在: {session_id}")

    return {"success": True, "message": f"会话 {session_id} 已关闭"}


# ==================== WebSocket 端点 ====================


@router.websocket("/ws")
async def realtime_websocket(
    websocket: WebSocket,
    model: str = Query(default="gpt-4o-realtime-preview", description="模型名称"),
    voice: str = Query(default="alloy", description="语音类型"),
    instructions: Optional[str] = Query(default=None, description="系统指令"),
):
    """
    实时语音通信 WebSocket 端点

    连接流程：
    1. 客户端连接此 WebSocket
    2. 服务端创建到 OpenAI Realtime API 的连接
    3. 双向转发消息（客户端 ↔ 服务端 ↔ OpenAI）

    客户端可发送的事件类型：
    - input_audio_buffer.append: 发送音频数据 {"type": "input_audio_buffer.append", "audio": "base64..."}
    - input_audio_buffer.commit: 提交音频缓冲区
    - input_audio_buffer.clear: 清空音频缓冲区
    - conversation.item.create: 发送文本消息
    - response.create: 触发响应生成
    - response.cancel: 取消当前响应

    服务端会转发 OpenAI 返回的所有事件
    """
    await websocket.accept()
    logger.info(f"WebSocket 连接已建立，model={model}, voice={voice}")

    service = get_realtime_service()
    session: Optional[RealtimeSession] = None

    try:
        # 解析语音类型
        try:
            voice_enum = Voice(voice.lower())
        except ValueError:
            voice_enum = Voice.ALLOY
            logger.warning(f"无效的语音类型 '{voice}'，使用默认值 alloy")

        # 定义转发回调：将 OpenAI 事件转发给客户端
        async def forward_to_client(event: Dict[str, Any]):
            try:
                await websocket.send_json(event)
            except Exception as e:
                logger.error(f"转发事件到客户端失败: {e}")

        # 创建会话
        session = await service.create_session(
            model=model,
            voice=voice_enum,
            instructions=instructions,
            on_server_event=forward_to_client,
        )

        # 连接到 OpenAI
        connected = await session.connect()
        if not connected:
            await websocket.send_json(
                {
                    "type": "error",
                    "error": {
                        "message": "无法连接到 OpenAI Realtime API",
                        "code": "connection_failed",
                    },
                }
            )
            await websocket.close(code=1011, reason="OpenAI connection failed")
            return

        # 发送连接成功事件
        await websocket.send_json(
            {
                "type": "session.created",
                "session": {
                    "id": session.session_id,
                    "model": session.model,
                    "voice": session.voice.value,
                    "created_at": session.created_at,
                },
            }
        )

        # 主循环：接收客户端消息并转发到 OpenAI
        while True:
            try:
                # 接收客户端消息
                data = await websocket.receive_json()
                event_type = data.get("type", "unknown")

                # 特殊处理：文本消息快捷方式
                if event_type == "text":
                    text = data.get("text", "")
                    if text:
                        await session.send_text(text)
                    continue

                # 特殊处理：音频数据快捷方式
                if event_type == "audio":
                    audio = data.get("audio", "")
                    if audio:
                        await session.send_audio(audio)
                    continue

                # 转发其他事件到 OpenAI
                await session.send_to_openai(data)

            except json.JSONDecodeError as e:
                logger.warning(f"[{session.session_id}] 无效的 JSON: {e}")
                await websocket.send_json(
                    {
                        "type": "error",
                        "error": {
                            "message": "无效的 JSON 格式",
                            "code": "invalid_json",
                        },
                    }
                )

    except WebSocketDisconnect:
        logger.info(f"客户端断开 WebSocket 连接")
    except Exception as e:
        logger.error(f"WebSocket 处理异常: {e}", exc_info=True)
        try:
            await websocket.send_json(
                {
                    "type": "error",
                    "error": {
                        "message": str(e),
                        "code": "internal_error",
                    },
                }
            )
        except Exception:
            pass
    finally:
        # 清理会话
        if session:
            await service.close_session(session.session_id)
        logger.info("WebSocket 连接已关闭")


@router.websocket("/ws/{session_id}")
async def realtime_websocket_reconnect(
    websocket: WebSocket,
    session_id: str,
):
    """
    重连到已存在的实时会话

    用于客户端意外断开后重新连接到同一会话

    Args:
        session_id: 已存在的会话 ID
    """
    await websocket.accept()
    logger.info(f"WebSocket 重连请求: session_id={session_id}")

    service = get_realtime_service()
    session = service.get_session(session_id)

    if not session:
        await websocket.send_json(
            {
                "type": "error",
                "error": {
                    "message": f"会话不存在: {session_id}",
                    "code": "session_not_found",
                },
            }
        )
        await websocket.close(code=4004, reason="Session not found")
        return

    try:
        # 更新回调：将事件转发给新的 WebSocket 连接
        async def forward_to_client(event: Dict[str, Any]):
            try:
                await websocket.send_json(event)
            except Exception as e:
                logger.error(f"转发事件到客户端失败: {e}")

        session.on_server_event = forward_to_client

        # 发送重连成功事件
        await websocket.send_json(
            {
                "type": "session.reconnected",
                "session": {
                    "id": session.session_id,
                    "model": session.model,
                    "voice": session.voice.value,
                    "connected": session.is_connected,
                    "created_at": session.created_at,
                },
            }
        )

        # 主循环
        while True:
            try:
                data = await websocket.receive_json()
                event_type = data.get("type", "unknown")

                if event_type == "text":
                    text = data.get("text", "")
                    if text:
                        await session.send_text(text)
                    continue

                if event_type == "audio":
                    audio = data.get("audio", "")
                    if audio:
                        await session.send_audio(audio)
                    continue

                await session.send_to_openai(data)

            except json.JSONDecodeError as e:
                logger.warning(f"[{session_id}] 无效的 JSON: {e}")

    except WebSocketDisconnect:
        logger.info(f"客户端断开 WebSocket 连接: {session_id}")
    except Exception as e:
        logger.error(f"WebSocket 处理异常: {e}", exc_info=True)
    finally:
        # 注意：重连断开时不关闭会话，允许再次重连
        logger.info(f"WebSocket 重连断开: {session_id}")
