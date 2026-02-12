"""
事件管理基类

职责：
1. 定义 EventStorage Protocol（存储接口）
2. 提供 BaseEventManager（所有事件管理器的基类）
3. 统一事件结构和发送逻辑

事件结构：
{
    "event_uuid": str,        # 全局唯一 UUID
    "seq": int,               # Session 内序号（1, 2, 3...）
    "type": str,              # 事件类型
    "session_id": str,        # Session ID
    "conversation_id": str,   # Conversation ID
    "message_id": str,        # Message ID（可选）
    "timestamp": str,         # ISO 时间戳
    "data": dict              # 事件数据
}

架构说明（重构后）：
- 序号（seq）在 storage.buffer_event 中统一自增生成
- EventBroadcaster 是事件发送的统一入口
- 格式转换在 buffer_event 中完成
"""

from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, Optional, Protocol
from uuid import uuid4

from logger import get_logger

logger = get_logger("events.base")


class EventStorage(Protocol):
    """
    事件存储协议（抽象接口）

    所有方法都是异步的。

    当前实现：
    - LocalSessionStore（infra/local_store/session_store.py）
    - InMemoryEventStorage（core/events/storage.py）
    """

    async def get_session_context(self, session_id: str) -> Dict[str, Any]:
        """获取 session 上下文（conversation_id 等）"""
        ...

    async def buffer_event(
        self,
        session_id: str,
        event_data: Dict[str, Any],
        output_format: str = "zenflux",
        adapter: Any = None,
    ) -> Optional[Dict[str, Any]]:
        """
        缓冲事件

        Args:
            session_id: Session ID
            event_data: 事件数据
            output_format: 输出格式，默认 zenflux
            adapter: 格式转换适配器（可选）

        Returns:
            添加了 seq 的事件，如果被过滤则返回 None
        """
        ...

    async def update_heartbeat(self, session_id: str) -> None:
        """更新心跳"""
        ...


class BaseEventManager:
    """
    事件管理器基类

    职责：
    - 创建标准化的事件结构
    - 通过 EventStorage 协议处理存储（解耦具体实现）

    所有具体的事件管理器都继承此类

    注意：
    - 推荐通过 EventBroadcaster 发送事件（统一生成 seq）
    - 直接调用子管理器时，可以传入已生成的 seq 和 event_uuid
    """

    def __init__(self, storage: EventStorage):
        """
        初始化基类

        Args:
            storage: 事件存储实现（实现 EventStorage 协议）
        """
        self.storage = storage

    async def _send_event(
        self,
        session_id: str,
        event: Dict[str, Any],
        conversation_id: str = None,
        message_id: str = None,
        seq: Optional[int] = None,
        event_uuid: Optional[str] = None,
        output_format: str = "zenflux",
        adapter: Any = None,
    ) -> Optional[Dict[str, Any]]:
        """
        发送事件（内部方法）

        处理逻辑：
        - 如果提供了 seq 和 event_uuid，直接使用（来自 EventBroadcaster）
        - 添加通用上下文字段
        - 委托给 storage 处理存储、格式转换和心跳

        Args:
            session_id: Session ID
            event: 事件对象（必须包含 type 和 data）
            conversation_id: Conversation ID（可选，会从 storage 获取）
            message_id: Message ID（可选）
            seq: 事件序号（可选，新架构中由 buffer_event 生成）
            event_uuid: 事件 UUID（可选，来自上层）
            output_format: 输出格式，默认 zenflux
            adapter: 格式转换适配器（可选）

        Returns:
            完整的事件对象，如果被过滤则返回 None
        """
        # 1. 使用提供的 UUID 或生成新的
        if event_uuid is None:
            event_uuid = str(uuid4())

        # 2. 获取上下文信息（如果没有提供）- 异步
        if not conversation_id:
            session_context = await self.storage.get_session_context(session_id)
            conversation_id = session_context.get("conversation_id")

        # 3. 构建统一格式的事件（不在这里设置 seq，由 buffer_event 生成）
        complete_event = {
            # 事件标识
            "event_uuid": event_uuid,
            "type": event["type"],
            # 通用上下文字段
            "session_id": session_id,
            "conversation_id": conversation_id,
            "timestamp": event.get("timestamp", datetime.now().isoformat()),
            # 事件特定数据
            "data": event.get("data", {}),
        }

        # 添加 message_id（如果提供）
        if message_id:
            complete_event["message_id"] = message_id

        # 如果上层提供了 seq（来自 EventBroadcaster），使用它
        if seq is not None:
            complete_event["seq"] = seq

        # 4. 委托给 storage 处理存储（包括格式转换和 seq 生成）
        result = await self.storage.buffer_event(
            session_id=session_id,
            event_data=complete_event,
            output_format=output_format,
            adapter=adapter,
        )

        # 如果事件被过滤（如适配器过滤某些事件），返回 None
        if result is None:
            return None

        # 5. 委托给 storage 更新心跳 - 异步
        await self.storage.update_heartbeat(session_id)

        logger.debug(
            f"📤 已发送事件: type={result.get('type', 'unknown')}, "
            f"seq={result.get('seq')}, session_id={session_id}"
        )

        return result

    def _create_event(self, event_type: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        创建标准事件结构

        Args:
            event_type: 事件类型
            data: 事件数据

        Returns:
            标准化的事件对象
        """
        return {"type": event_type, "data": data, "timestamp": datetime.now().isoformat()}
