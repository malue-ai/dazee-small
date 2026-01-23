"""
Session 服务层 - Session Management Service（异步版本）

职责：
1. Session 生命周期管理（创建、获取、结束、清理）
2. Session 状态查询（Redis）
3. Session 事件管理
4. 前后端连接管理（SSE session_id、心跳、超时）

设计原则：
- 单一职责：只管理 Session 状态，不涉及 Agent
- Session 状态存储在 Redis
- 支持多用户并发 Session
- 所有方法都是异步的，避免阻塞事件循环

注意：Agent 的创建和管理由 ChatService 负责
"""

from typing import Dict, Any, Optional, List
from datetime import datetime
from uuid import uuid4

from logger import get_logger
from core.events import create_event_manager
from services.redis_manager import get_redis_manager

logger = get_logger("session_service")


def extract_message_text(message: List[Dict[str, str]]) -> str:
    """
    从消息中提取文本内容（用于日志和预览）
    
    Args:
        message: 消息（Claude API 格式 [{"type": "text", "text": "..."}]）
        
    Returns:
        提取的文本内容
    """
    text_parts = [
        block.get("text", "")
        for block in message
        if isinstance(block, dict) and block.get("type") == "text"
    ]
    return " ".join(text_parts) if text_parts else ""


class SessionServiceError(Exception):
    """Session 服务异常基类"""
    pass


class SessionNotFoundError(SessionServiceError):
    """会话不存在异常"""
    pass


class SessionService:
    """
    Session 服务（异步版本）
    
    职责：管理前后端连接（Session 状态、Redis、事件流）
    注意：不负责 Agent 创建和管理
    """
    
    def __init__(self):
        """
        初始化 Session 服务
        """
        # Redis 管理器
        self.redis = get_redis_manager()
        
        # 事件管理器
        self.events = create_event_manager(self.redis)
    
    # ==================== Session 生命周期 ====================
    
    def _generate_session_id(self) -> str:
        """生成运行会话ID"""
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"sess_{ts}_{uuid4().hex[:8]}"
    
    async def create_session(
        self,
        user_id: str,
        message: List[Dict[str, str]],
        conversation_id: str,
        message_id: Optional[str] = None,
    ) -> str:
        """
        创建 Session（只管理连接状态，不创建 Agent）
        
        Args:
            user_id: 用户 ID
            message: 用户消息（Claude API 格式 [{"type": "text", "text": "..."}]）
            conversation_id: 对话 ID（必填，ChatService 会确保在调用前已创建）
            message_id: 消息 ID（可选）
            
        Returns:
            session_id: 会话 ID
        """
        # 1️⃣ 生成 session_id
        session_id = self._generate_session_id()
        
        logger.info(f"🔨 创建新的 Session: session_id={session_id}, conversation_id={conversation_id}")
        
        # 2️⃣ 提取消息文本用于预览
        message_text = extract_message_text(message)
        
        # 3️⃣ 创建 Redis Session 状态（异步）
        await self.redis.create_session(
            session_id=session_id,
            user_id=user_id,
            conversation_id=conversation_id,
            message_id=message_id,
            message_preview=message_text[:100]
        )
        
        logger.info(
            f"✅ Session 创建完成: session_id={session_id}, "
            f"conversation_id={conversation_id}, user_id={user_id}"
        )
        
        return session_id
    
    async def end_session(self, session_id: str, status: str = "completed") -> Dict[str, Any]:
        """
        结束 Session
        
        Args:
            session_id: Session ID
            status: 最终状态（completed/failed/stopped）
            
        Returns:
            Session 摘要
        """
        # 更新 Redis Session 状态为完成
        await self.redis.complete_session(session_id, status=status)
        
        logger.info(f"✅ Session 已结束: session_id={session_id}, status={status}")
        
        return {
            "session_id": session_id,
            "status": status,
            "end_time": datetime.now().isoformat()
        }
    
    async def stop_session(self, session_id: str) -> Dict[str, Any]:
        """
        停止正在运行的 Session（用户主动中断）
        
        流程：
        1. 设置 Redis 停止标志
        2. chat_service 事件循环检测到标志后会：
           - 发送 billing 事件（message_delta type=billing）
           - 发送 session_stopped 事件
        
        注意：此方法只设置停止标志，不发送事件。
        所有事件（billing、session_stopped）由 chat_service 统一发送，确保正确的事件顺序。
        
        Args:
            session_id: Session ID
            
        Returns:
            停止结果
            
        Raises:
            SessionNotFoundError: Session 不存在
        """
        # 检查 Session 是否存在
        status = await self.redis.get_session_status(session_id)
        if not status:
            raise SessionNotFoundError(f"Session 不存在或已过期: session_id={session_id}")
        
        # 设置停止标志（chat_service 事件循环会检测并发送 billing 和 session_stopped 事件）
        await self.redis.set_stop_flag(session_id)
        
        # 注意：不在这里更新状态和发送事件
        # chat_service 检测到停止标志后会：
        # 1. 发送 billing 事件
        # 2. 发送 session_stopped 事件
        # 3. 调用 end_session() 更新状态
        
        logger.info(f"🛑 已设置停止标志: session_id={session_id}")
        
        return {
            "session_id": session_id,
            "status": "stopping",  # 标记为 stopping，实际 stopped 由 chat_service 设置
            "stopped_at": datetime.now().isoformat()
        }
    
    async def cleanup_inactive_sessions(self) -> int:
        """
        清理不活跃的 Session（带分布式锁，防重入）
        
        Returns:
            清理的 Session 数量，-1 表示未获取到锁
        """
        # 使用带锁的清理方法
        result = await self.redis.cleanup_with_lock()
        
        if result > 0:
            logger.info(f"🧹 清理了 {result} 个超时的 Session")
        elif result == -1:
            logger.debug("⏭️ 清理任务已在运行中，跳过")
        
        return result
    
    # ==================== Session 状态查询 ====================
    
    async def get_session_status(self, session_id: str) -> Dict[str, Any]:
        """
        获取 Session 状态（from Redis）
        
        Args:
            session_id: Session ID
            
        Returns:
            Session 状态
            
        Raises:
            SessionNotFoundError: Session 不存在或已过期
        """
        status = await self.redis.get_session_status(session_id)
        
        if not status:
            raise SessionNotFoundError(f"Session 不存在或已过期: session_id={session_id}")
        
        return status
    
    async def get_session_info(self, session_id: str) -> Dict[str, Any]:
        """
        获取 Session 信息（从 Redis）
        
        Args:
            session_id: Session ID
            
        Returns:
            Session 信息
            
        Raises:
            SessionNotFoundError: Session 不存在
        """
        return await self.get_session_status(session_id)
    
    async def list_sessions(self, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        列出活跃 Session（从 Redis）
        
        Args:
            user_id: 用户 ID（可选，不提供则返回所有）
            
        Returns:
            Session 列表
        """
        if user_id:
            return await self.redis.get_user_sessions_detail(user_id)
        else:
            # 获取所有活跃 Session（从 Redis）
            return await self.redis.list_active_sessions()
    
    # ==================== Session 事件管理 ====================
    
    async def get_session_events(
        self,
        session_id: str,
        after_id: Optional[int] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        获取 Session 的事件列表（用于断线重连）
        
        Args:
            session_id: Session ID
            after_id: 从哪个 event_id 之后开始（可选）
            limit: 最多返回多少个事件
            
        Returns:
            事件列表
            
        Raises:
            SessionNotFoundError: Session 不存在
        """
        # 检查 Session 是否存在
        if not await self.redis.get_session_status(session_id):
            raise SessionNotFoundError(f"Session 不存在: session_id={session_id}")
        
        # 获取事件
        events = await self.redis.get_events(
            session_id=session_id,
            after_id=after_id,
            limit=limit
        )
        
        return events
    
    async def get_user_sessions(self, user_id: str) -> List[Dict[str, Any]]:
        """
        获取用户的所有活跃 Session
        
        Args:
            user_id: 用户 ID
            
        Returns:
            Session 列表（包含详细信息）
        """
        return await self.redis.get_user_sessions_detail(user_id)
    
    # ==================== 辅助方法 ====================
    
    async def log_session_status(self, session_id: str, conversation_id: Optional[str] = None) -> None:
        """
        输出 Session 状态信息
        
        Args:
            session_id: Session ID
            conversation_id: Conversation ID（可选）
        """
        try:
            status = await self.redis.get_session_status(session_id)
            
            if status:
                logger.info(
                    f"📊 Session 状态: session_id={session_id}, conversation_id={conversation_id}, "
                    f"status={status.get('status', 'unknown')}"
                )
            else:
                logger.warning(f"⚠️ Session 不存在: session_id={session_id}")
        except SessionNotFoundError:
            logger.warning(f"⚠️ Session 不存在: session_id={session_id}")


# ==================== 便捷函数 ====================

_default_service: Optional[SessionService] = None


def get_session_service() -> SessionService:
    """获取默认 Session 服务单例"""
    global _default_service
    if _default_service is None:
        _default_service = SessionService()
    return _default_service
