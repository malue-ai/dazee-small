"""
事件存储 - EventStorage

提供事件存储的内存实现，用于开发/测试环境。

生产环境使用 RedisSessionManager（services/redis_manager.py）

设计说明：
- 生产环境：RedisSessionManager 实现 EventStorage 协议
- 开发环境：InMemoryEventStorage 作为内存降级方案
- seq 生成统一在 buffer_event 时通过 Redis INCR 完成
"""

# 1. 标准库
from collections import defaultdict
from datetime import datetime
from typing import Dict, Any, List, Optional

# 2. 第三方库（无）

# 3. 本地模块
from logger import get_logger

logger = get_logger("events.storage")


class InMemoryEventStorage:
    """
    内存事件存储（无 Redis 时的降级方案）
    
    实现 EventStorage 协议，使用内存存储
    
    注意：
    - 不支持跨进程/跨实例
    - 不支持持久化
    - 适用于单实例开发环境
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
    
    async def generate_session_seq(self, session_id: str) -> int:
        """
        生成 Session 内的事件序号
        
        注意：新架构中 seq 在 buffer_event 中由 Redis INCR 生成
        此方法保留以向后兼容
        """
        self._seq[session_id] += 1
        return self._seq[session_id]
    
    async def get_session_context(self, session_id: str) -> Dict[str, Any]:
        """获取 Session 上下文"""
        return self._context.get(session_id, {})
    
    async def set_session_context(
        self,
        session_id: str,
        conversation_id: str = None,
        user_id: str = None,
        **extra
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
        adapter=None
    ) -> Dict[str, Any]:
        """
        缓冲事件（内存版本）
        
        Args:
            session_id: Session ID
            event_data: 事件数据
            output_format: 输出格式（兼容 Redis 版本）
            adapter: 适配器（兼容 Redis 版本）
            
        Returns:
            添加了 seq 的事件
        """
        event = event_data.copy() if event_data else {}
        
        # 格式转换（如果需要）
        if output_format == "zeno" and adapter is not None:
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
            self._events[session_id] = events[-self.max_events:]
        
        return event
    
    async def update_heartbeat(self, session_id: str) -> None:
        """更新心跳"""
        self._heartbeat[session_id] = datetime.now().isoformat()
    
    # ==================== 扩展方法 ====================
    
    async def get_events_since(
        self,
        session_id: str,
        last_seq: int
    ) -> List[Dict[str, Any]]:
        """获取指定序号之后的所有事件"""
        events = self._events.get(session_id, [])
        return [e for e in events if e.get("seq", 0) > last_seq]
    
    async def get_latest_events(
        self,
        session_id: str,
        count: int = 50
    ) -> List[Dict[str, Any]]:
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
    
    用于开发/测试环境，生产环境使用 RedisSessionManager
    
    Returns:
        InMemoryEventStorage 实例
    """
    global _default_storage
    if _default_storage is None:
        _default_storage = InMemoryEventStorage()
    return _default_storage

