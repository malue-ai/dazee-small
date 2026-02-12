"""
本地 Session 存储
"""

import asyncio
from collections import defaultdict
from datetime import datetime
from typing import Any, AsyncIterator, Dict, List, Optional

from logger import get_logger

logger = get_logger("local_store.session_store")


class LocalSessionStore:
    """
    本地 Session 存储

    Session 管理，纯内存操作
    """

    def __init__(self):
        # session_id -> session metadata
        self._sessions: Dict[str, Dict[str, Any]] = {}
        # user_id -> set of active session_ids
        self._user_sessions: Dict[str, set] = defaultdict(set)
        # session_id -> context
        self._context: Dict[str, Dict[str, Any]] = {}
        # session_id -> list of events
        self._events: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        # session_id -> list of subscriber queues
        self._subscribers: Dict[str, List[asyncio.Queue]] = defaultdict(list)
        # session_id -> seq counter
        self._seq: Dict[str, int] = defaultdict(int)

    @property
    def is_available(self) -> bool:
        """内存存储始终可用"""
        return True

    # ==================== Session 生命周期 ====================

    async def create_session(
        self,
        session_id: str,
        user_id: str,
        conversation_id: str,
        message_id: Optional[str] = None,
        message_preview: str = "",
    ) -> None:
        """创建 Session"""
        self._sessions[session_id] = {
            "session_id": session_id,
            "user_id": user_id,
            "conversation_id": conversation_id,
            "message_id": message_id,
            "message_preview": message_preview,
            "status": "running",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }
        self._user_sessions[user_id].add(session_id)
        logger.debug("Session 已创建", extra={"session_id": session_id})

    async def complete_session(self, session_id: str, status: str = "completed") -> None:
        """标记 Session 完成"""
        if session_id in self._sessions:
            self._sessions[session_id]["status"] = status
            self._sessions[session_id]["updated_at"] = datetime.now().isoformat()

            # 通知所有订阅者结束
            for queue in self._subscribers.get(session_id, []):
                await queue.put(None)  # sentinel

            logger.debug("Session 已完成", extra={"session_id": session_id, "status": status})

    async def get_session_status(self, session_id: str) -> Optional[Dict[str, Any]]:
        """获取 Session 状态"""
        return self._sessions.get(session_id)

    # ==================== Session 上下文 ====================

    async def set_session_context(
        self,
        session_id: str,
        conversation_id: str = None,
        user_id: str = None,
        **extra,
    ) -> None:
        """设置 Session 上下文"""
        context = self._context.get(session_id, {})
        if conversation_id:
            context["conversation_id"] = conversation_id
        if user_id:
            context["user_id"] = user_id
        context.update(extra)
        self._context[session_id] = context

    async def get_session_context(self, session_id: str) -> Dict[str, Any]:
        """获取 Session 上下文"""
        return self._context.get(session_id, {})

    # ==================== 事件系统 ====================

    async def buffer_event(
        self,
        session_id: str,
        event_data: Dict[str, Any],
        output_format: str = "zenflux",
        adapter=None,
    ) -> Optional[Dict[str, Any]]:
        """缓冲事件并通知订阅者"""
        event = event_data.copy() if event_data else {}

        # 格式转换
        if adapter is not None:
            transformed = adapter.transform(event)
            if transformed is None:
                return None
            event = transformed

        # 生成 seq
        if "seq" not in event or event.get("seq") is None:
            self._seq[session_id] += 1
            event["seq"] = self._seq[session_id]

        # 存储
        self._events[session_id].append(event)

        # 通知所有订阅者
        for queue in self._subscribers.get(session_id, []):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning("事件队列已满，丢弃事件", extra={"session_id": session_id})

        return event

    async def subscribe_events(
        self,
        session_id: str,
        after_id: int = 0,
        timeout: int = 1800,
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        订阅事件流（asyncio.Queue 实现）

        Args:
            session_id: Session ID
            after_id: 从哪个 seq 之后开始
            timeout: 超时秒数

        Yields:
            事件字典
        """
        queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self._subscribers.setdefault(session_id, []).append(queue)

        try:
            # 先发送已有的历史事件
            for event in self._events.get(session_id, []):
                if event.get("seq", 0) > after_id:
                    yield event

            # 然后监听新事件
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=timeout)
                    if event is None:
                        # sentinel：session 已结束
                        break
                    yield event
                except asyncio.TimeoutError:
                    logger.info("事件订阅超时", extra={"session_id": session_id})
                    break
        finally:
            # 移除订阅者
            subs = self._subscribers.get(session_id, [])
            if queue in subs:
                subs.remove(queue)

    async def update_heartbeat(self, session_id: str) -> None:
        """更新心跳"""
        if session_id in self._sessions:
            self._sessions[session_id]["updated_at"] = datetime.now().isoformat()

    # ==================== 查询方法 ====================

    async def get_events(
        self,
        session_id: str,
        after_id: Optional[int] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """获取事件列表"""
        events = self._events.get(session_id, [])
        if after_id is not None:
            events = [e for e in events if e.get("seq", 0) > after_id]
        return events[-limit:]

    async def get_user_sessions_detail(self, user_id: str) -> List[Dict[str, Any]]:
        """获取用户的所有活跃 Session 详情"""
        session_ids = self._user_sessions.get(user_id, set())
        return [
            self._sessions[sid]
            for sid in session_ids
            if sid in self._sessions and self._sessions[sid].get("status") == "active"
        ]

    async def list_active_sessions(self) -> List[Dict[str, Any]]:
        """列出所有活跃 Session"""
        return [
            info for info in self._sessions.values()
            if info.get("status") == "active"
        ]

    async def cleanup_with_lock(self) -> int:
        """清理不活跃 Session（内存版本，无需分布式锁）"""
        cleaned = 0
        # Keep sessions that are actively running
        active_statuses = {"active", "running"}
        expired_ids = [
            sid for sid, info in self._sessions.items()
            if info.get("status") not in active_statuses
        ]
        for sid in expired_ids:
            await self._cleanup_session(sid)
            cleaned += 1
        return cleaned

    async def _cleanup_session(self, session_id: str) -> None:
        """清理单个 Session 的所有数据"""
        info = self._sessions.pop(session_id, None)
        if info:
            user_id = info.get("user_id")
            if user_id and user_id in self._user_sessions:
                self._user_sessions[user_id].discard(session_id)
                if not self._user_sessions[user_id]:
                    del self._user_sessions[user_id]

        self._context.pop(session_id, None)
        self._events.pop(session_id, None)
        self._seq.pop(session_id, None)
        self._subscribers.pop(session_id, None)


# ==================== 单例 ====================

_default_store: Optional[LocalSessionStore] = None


def get_local_session_store() -> LocalSessionStore:
    """获取 LocalSessionStore 单例"""
    global _default_store
    if _default_store is None:
        _default_store = LocalSessionStore()
    return _default_store
