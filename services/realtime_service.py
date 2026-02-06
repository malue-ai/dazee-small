"""
Realtime Service - 实时语音通信服务

作为中间层连接客户端和 OpenAI Realtime API
负责 WebSocket 消息转发和音频流处理
"""

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime
from typing import Any, Callable, Dict, Optional

import websockets
from websockets.client import WebSocketClientProtocol

from models.realtime import (
    RealtimeEventType,
    SessionConfig,
    Voice,
)

logger = logging.getLogger(__name__)


class RealtimeSession:
    """
    单个实时会话管理器

    负责维护与 OpenAI Realtime API 的 WebSocket 连接，
    并在客户端和 OpenAI 之间转发消息
    """

    OPENAI_REALTIME_URL = "wss://api.openai.com/v1/realtime"

    def __init__(
        self,
        session_id: str,
        model: str = "gpt-4o-realtime-preview",
        voice: Voice = Voice.ALLOY,
        instructions: Optional[str] = None,
        on_server_event: Optional[Callable[[Dict[str, Any]], None]] = None,
    ):
        """
        初始化实时会话

        Args:
            session_id: 会话 ID
            model: 模型名称
            voice: 语音类型
            instructions: 系统指令
            on_server_event: 服务端事件回调（用于转发给客户端）
        """
        self.session_id = session_id
        self.model = model
        self.voice = voice
        self.instructions = instructions
        self.on_server_event = on_server_event

        self._openai_ws: Optional[WebSocketClientProtocol] = None
        self._receive_task: Optional[asyncio.Task] = None
        self._connected = False
        self._closed = False
        self.created_at = datetime.utcnow().isoformat()

        # 从环境变量获取 API Key
        self._api_key = os.getenv("OPENAI_API_KEY")
        if not self._api_key:
            raise ValueError("OPENAI_API_KEY 环境变量未设置")

    @property
    def is_connected(self) -> bool:
        """是否已连接到 OpenAI"""
        return self._connected and self._openai_ws is not None

    async def connect(self) -> bool:
        """
        连接到 OpenAI Realtime API

        Returns:
            是否连接成功
        """
        if self._connected:
            logger.warning(f"[{self.session_id}] 会话已连接")
            return True

        try:
            url = f"{self.OPENAI_REALTIME_URL}?model={self.model}"

            # 建立 WebSocket 连接
            self._openai_ws = await websockets.connect(
                url,
                additional_headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "OpenAI-Beta": "realtime=v1",
                },
                ping_interval=30,
                ping_timeout=10,
            )

            self._connected = True
            logger.info(f"[{self.session_id}] 已连接到 OpenAI Realtime API")

            # 启动接收任务
            self._receive_task = asyncio.create_task(self._receive_loop())

            # 发送初始配置
            await self._send_session_config()

            return True

        except Exception as e:
            logger.error(f"[{self.session_id}] 连接 OpenAI 失败: {e}", exc_info=True)
            self._connected = False
            return False

    async def _send_session_config(self) -> None:
        """发送会话配置到 OpenAI"""
        config = {
            "type": "session.update",
            "session": {
                "modalities": ["text", "audio"],
                "voice": self.voice.value,
                "input_audio_format": "pcm16",
                "output_audio_format": "pcm16",
                "input_audio_transcription": {"model": "whisper-1"},
                "turn_detection": {
                    "type": "server_vad",
                    "threshold": 0.5,
                    "prefix_padding_ms": 300,
                    "silence_duration_ms": 500,
                },
            },
        }

        if self.instructions:
            config["session"]["instructions"] = self.instructions

        await self.send_to_openai(config)

    async def _receive_loop(self) -> None:
        """
        接收 OpenAI 消息的循环

        将收到的消息转发给客户端
        """
        if not self._openai_ws:
            return

        try:
            async for message in self._openai_ws:
                if self._closed:
                    break

                try:
                    event = json.loads(message)
                    event_type = event.get("type", "unknown")

                    # 记录重要事件
                    if event_type not in [
                        "response.audio.delta",
                        "response.audio_transcript.delta",
                        "input_audio_buffer.speech_started",
                        "input_audio_buffer.speech_stopped",
                    ]:
                        logger.debug(f"[{self.session_id}] OpenAI 事件: {event_type}")

                    # 转发给客户端
                    if self.on_server_event:
                        await self._safe_callback(event)

                except json.JSONDecodeError as e:
                    logger.error(f"[{self.session_id}] JSON 解析失败: {e}")

        except websockets.exceptions.ConnectionClosed as e:
            logger.info(f"[{self.session_id}] OpenAI 连接关闭: {e}")
        except Exception as e:
            logger.error(f"[{self.session_id}] 接收消息异常: {e}", exc_info=True)
        finally:
            self._connected = False

    async def _safe_callback(self, event: Dict[str, Any]) -> None:
        """安全调用回调函数"""
        try:
            if asyncio.iscoroutinefunction(self.on_server_event):
                await self.on_server_event(event)
            else:
                self.on_server_event(event)
        except Exception as e:
            logger.error(f"[{self.session_id}] 回调执行失败: {e}", exc_info=True)

    async def send_to_openai(self, event: Dict[str, Any]) -> bool:
        """
        发送事件到 OpenAI

        Args:
            event: 要发送的事件

        Returns:
            是否发送成功
        """
        if not self._openai_ws or not self._connected:
            logger.warning(f"[{self.session_id}] 未连接，无法发送消息")
            return False

        try:
            message = json.dumps(event)
            await self._openai_ws.send(message)

            event_type = event.get("type", "unknown")
            if event_type != "input_audio_buffer.append":
                logger.debug(f"[{self.session_id}] 发送到 OpenAI: {event_type}")

            return True

        except Exception as e:
            logger.error(f"[{self.session_id}] 发送消息失败: {e}", exc_info=True)
            return False

    async def send_audio(self, audio_base64: str) -> bool:
        """
        发送音频数据到 OpenAI

        Args:
            audio_base64: Base64 编码的音频数据

        Returns:
            是否发送成功
        """
        event = {
            "type": "input_audio_buffer.append",
            "audio": audio_base64,
        }
        return await self.send_to_openai(event)

    async def send_text(self, text: str, role: str = "user") -> bool:
        """
        发送文本消息到 OpenAI

        Args:
            text: 文本内容
            role: 角色（user/assistant）

        Returns:
            是否发送成功
        """
        event = {
            "type": "conversation.item.create",
            "item": {
                "type": "message",
                "role": role,
                "content": [
                    {
                        "type": "input_text",
                        "text": text,
                    }
                ],
            },
        }
        success = await self.send_to_openai(event)

        if success:
            # 触发响应生成
            await self.send_to_openai({"type": "response.create"})

        return success

    async def commit_audio(self) -> bool:
        """提交音频缓冲区"""
        return await self.send_to_openai({"type": "input_audio_buffer.commit"})

    async def clear_audio(self) -> bool:
        """清空音频缓冲区"""
        return await self.send_to_openai({"type": "input_audio_buffer.clear"})

    async def cancel_response(self) -> bool:
        """取消当前响应"""
        return await self.send_to_openai({"type": "response.cancel"})

    async def close(self) -> None:
        """关闭会话"""
        self._closed = True
        self._connected = False

        # 取消接收任务
        if self._receive_task and not self._receive_task.done():
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass

        # 关闭 WebSocket 连接
        if self._openai_ws:
            try:
                await self._openai_ws.close()
            except Exception as e:
                logger.warning(f"[{self.session_id}] 关闭连接时出错: {e}")
            finally:
                self._openai_ws = None

        logger.info(f"[{self.session_id}] 会话已关闭")


class RealtimeService:
    """
    实时通信服务

    管理多个 RealtimeSession，提供会话的创建、查询、关闭等功能
    """

    def __init__(self):
        self._sessions: Dict[str, RealtimeSession] = {}
        self._lock = asyncio.Lock()

    async def create_session(
        self,
        model: str = "gpt-4o-realtime-preview",
        voice: Voice = Voice.ALLOY,
        instructions: Optional[str] = None,
        on_server_event: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> RealtimeSession:
        """
        创建新的实时会话

        Args:
            model: 模型名称
            voice: 语音类型
            instructions: 系统指令
            on_server_event: 服务端事件回调

        Returns:
            RealtimeSession 实例
        """
        session_id = f"rt_{uuid.uuid4().hex[:12]}"

        session = RealtimeSession(
            session_id=session_id,
            model=model,
            voice=voice,
            instructions=instructions,
            on_server_event=on_server_event,
        )

        async with self._lock:
            self._sessions[session_id] = session

        logger.info(f"创建实时会话: {session_id}")
        return session

    def get_session(self, session_id: str) -> Optional[RealtimeSession]:
        """获取会话"""
        return self._sessions.get(session_id)

    async def close_session(self, session_id: str) -> bool:
        """
        关闭并移除会话

        Args:
            session_id: 会话 ID

        Returns:
            是否成功关闭
        """
        async with self._lock:
            session = self._sessions.pop(session_id, None)

        if session:
            await session.close()
            logger.info(f"关闭实时会话: {session_id}")
            return True

        return False

    def list_sessions(self) -> list:
        """列出所有活跃会话"""
        return [
            {
                "session_id": s.session_id,
                "model": s.model,
                "voice": s.voice.value,
                "connected": s.is_connected,
                "created_at": s.created_at,
            }
            for s in self._sessions.values()
        ]

    async def cleanup(self) -> None:
        """清理所有会话"""
        async with self._lock:
            sessions = list(self._sessions.values())
            self._sessions.clear()

        for session in sessions:
            try:
                await session.close()
            except Exception as e:
                logger.error(f"清理会话 {session.session_id} 失败: {e}")

        logger.info("所有实时会话已清理")


# ==================== 单例 ====================

_realtime_service: Optional[RealtimeService] = None


def get_realtime_service() -> RealtimeService:
    """获取 RealtimeService 单例"""
    global _realtime_service
    if _realtime_service is None:
        _realtime_service = RealtimeService()
    return _realtime_service
