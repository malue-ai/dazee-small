"""
事件管理基类

提供所有事件管理器的共享逻辑
"""

from typing import Dict, Any, Protocol
from datetime import datetime
from uuid import uuid4
from logger import get_logger

logger = get_logger("events.base")


class EventStorage(Protocol):
    """
    事件存储协议（抽象接口）
    
    所有方法都是异步的，支持异步 Redis 客户端
    """
    
    async def generate_session_seq(self, session_id: str) -> int:
        """生成 session 内的事件序号（从 1 开始）"""
        ...
    
    async def get_session_context(self, session_id: str) -> Dict[str, Any]:
        """获取 session 上下文（conversation_id 等）"""
        ...
    
    async def buffer_event(self, session_id: str, event_data: Dict[str, Any]) -> None:
        """缓冲事件"""
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
    """
    
    def __init__(self, storage: EventStorage):
        """
        初始化基类
        
        Args:
            storage: 事件存储实现（可以是 Redis、内存、文件等）
        """
        self.storage = storage
    
    async def _send_event(
        self,
        session_id: str,
        event: Dict[str, Any],
        conversation_id: str = None
    ) -> Dict[str, Any]:
        """
        发送事件（内部方法）
        
        自动处理：
        - 生成 UUID（全局唯一事件标识符）
        - 生成 session 内序号 seq（从 1 开始递增）
        - 添加通用上下文字段
        - 委托给 storage 处理存储和心跳
        
        统一事件结构：
        {
          // 事件标识
          "event_uuid": str,             // 全局唯一 UUID（例如：550e8400-e29b-41d4-a716-446655440000）
          "seq": int,                    // Session 内序号（1, 2, 3...）
          "type": str,                   // 事件类型
          
          // 通用上下文字段（所有事件都有）
          "session_id": str,             // Session ID
          "conversation_id": str,        // Conversation ID
          "timestamp": str,              // ISO 时间戳
          
          // 事件特定数据
          "data": dict                   // 事件数据
        }
        
        Args:
            session_id: Session ID
            event: 事件对象（必须包含 type 和 data）
            conversation_id: Conversation ID（可选，会从 Redis 获取）
            
        Returns:
            完整的事件对象
        """
        # 1. 生成全局唯一 UUID
        event_uuid = str(uuid4())
        
        # 2. 生成 session 内序号（从 1 开始）- 异步
        seq = await self.storage.generate_session_seq(session_id)
        
        # 3. 获取上下文信息（如果没有提供）- 异步
        if not conversation_id:
            session_context = await self.storage.get_session_context(session_id)
            conversation_id = conversation_id or session_context.get("conversation_id")
        
        # 4. 构建统一格式的事件
        complete_event = {
            # 事件标识
            "event_uuid": event_uuid,
            "seq": seq,
            "type": event["type"],
            
            # 通用上下文字段
            "session_id": session_id,
            "conversation_id": conversation_id,
            "timestamp": event.get("timestamp", datetime.now().isoformat()),
            
            # 事件特定数据
            "data": event.get("data", {})
        }
        
        # 5. 委托给 storage 处理存储 - 异步
        await self.storage.buffer_event(
            session_id=session_id,
            event_data=complete_event
        )
        
        # 6. 委托给 storage 更新心跳 - 异步
        await self.storage.update_heartbeat(session_id)
        
        logger.debug(
            f"📤 已发送事件: type={complete_event['type']}, "
            f"seq={seq}, session_id={session_id}"
        )
        
        return complete_event
    
    def _create_event(
        self,
        event_type: str,
        data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        创建标准事件结构
        
        Args:
            event_type: 事件类型
            data: 事件数据
            
        Returns:
            标准化的事件对象
        """
        return {
            "type": event_type,
            "data": data,
            "timestamp": datetime.now().isoformat()
        }
