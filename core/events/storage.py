"""
事件存储 - EventStorage

提供事件存储的内存实现。

设计说明：
- InMemoryEventStorage 作为轻量内存实现
- seq 生成统一在 buffer_event 时完成
- 桌面端主要使用 LocalSessionStore（infra/local_store/session_store.py）
"""

# 1. 标准库
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional

# 3. 本地模块
from logger import get_logger

# 2. 第三方库（无）


logger = get_logger("events.storage")


class InMemoryEventStorage:
    """
    内存事件存储

    实现 EventStorage 协议，使用内存存储。
    适用于单实例环境。
    """

    def __init__(self, max_events: int = 1000):
        """初始化内存存储"""
        self.max_events = max_events

        # 存储结构
        self._seq: Dict[str, int] = defaultdict(int)
        self._context: Dict[str, Dict[str, Any]] = {}
        self._events: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self._heartbeat: Dict[str, str] = {}

    @property
    def is_available(self) -> bool:
        """内存存储始终可用"""
        return True

    # ==================== EventStorage Protocol ====================

    async def get_session_context(self, session_id: str) -> Dict[str, Any]:
        """获取 Session 上下文"""
        return self._context.get(session_id, {})

    async def set_session_context(
        self, session_id: str, conversation_id: str = None, user_id: str = None, **extra
    ) -> None:
        """设置 Session 上下文"""
        context = self._context.get(session_id, {})
        if conversation_id:
            context["conversation_id"] = conversation_id
        if user_id:
            context["user_id"] = user_id
        context.update(extra)
        self._context[session_id] = context

    async def buffer_event(
        self,
        session_id: str,
        event_data: Dict[str, Any],
        output_format: str = "zenflux",
        adapter=None,
    ) -> Dict[str, Any]:
        """
        缓冲事件（内存版本）

        Args:
            session_id: Session ID
            event_data: 事件数据
            output_format: 输出格式
            adapter: 适配器（可选）

        Returns:
            添加了 seq 的事件
        """
        event = event_data.copy() if event_data else {}

        # 格式转换（如果需要）
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
        events = self._events[session_id]
        events.append(event)

        # 限制数量
        if len(events) > self.max_events:
            self._events[session_id] = events[-self.max_events :]

        return event

    async def update_heartbeat(self, session_id: str) -> None:
        """更新心跳"""
        self._heartbeat[session_id] = datetime.now().isoformat()

    # ==================== 扩展方法 ====================

    async def get_events_since(self, session_id: str, last_seq: int) -> List[Dict[str, Any]]:
        """获取指定序号之后的所有事件"""
        events = self._events.get(session_id, [])
        return [e for e in events if e.get("seq", 0) > last_seq]

    async def get_latest_events(self, session_id: str, count: int = 50) -> List[Dict[str, Any]]:
        """获取最近的 N 个事件"""
        events = self._events.get(session_id, [])
        return events[-count:]

    async def get_current_seq(self, session_id: str) -> int:
        """获取当前序号"""
        return self._seq.get(session_id, 0)

    async def cleanup_session(self, session_id: str) -> None:
        """清理 Session 数据"""
        self._seq.pop(session_id, None)
        self._context.pop(session_id, None)
        self._events.pop(session_id, None)
        self._heartbeat.pop(session_id, None)
        logger.info(f"🧹 Session 内存数据已清理: session_id={session_id}")


# ==================== 工厂函数 ====================

_default_storage: Optional[InMemoryEventStorage] = None


def get_memory_storage() -> InMemoryEventStorage:
    """
    获取内存存储实例（单例）

    Returns:
        InMemoryEventStorage 实例
    """
    global _default_storage
    if _default_storage is None:
        _default_storage = InMemoryEventStorage()
    return _default_storage
