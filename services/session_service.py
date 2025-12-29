"""
Session 服务层 - Session Management Service

职责：
1. Session 生命周期管理（创建、获取、结束、清理）
2. Session 状态查询
3. Session 事件管理
4. Agent 池管理

设计原则：
- 单一职责：只管理 Session 和 Agent 池
- Session 状态存储在 Redis
- 支持多用户并发 Session
"""

from typing import Dict, Any, Optional, List
from datetime import datetime
from uuid import uuid4

from logger import get_logger
from core.agent import SimpleAgent, create_simple_agent
from core.context import create_context
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
    Session 服务
    
    提供 Session 和 Agent 的生命周期管理
    """
    
    def __init__(
        self,
        default_model: str = "claude-sonnet-4-5-20250929",
        default_workspace: str = "./workspace"
    ):
        """
        初始化 Session 服务
        
        Args:
            default_model: 默认 LLM 模型
            default_workspace: 默认工作目录
        """
        self.default_model = default_model
        self.default_workspace = default_workspace
        
        # Agent 实例池（支持多会话）
        # key: session_id, value: SimpleAgent
        self.agent_pool: Dict[str, SimpleAgent] = {}
        
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
        conversation_id: Optional[str] = None,
        message_id: Optional[str] = None
    ) -> tuple[str, SimpleAgent]:
        """
        创建新的 Session 和 Agent
        
        Args:
            user_id: 用户 ID
            message: 用户消息（Claude API 格式 [{"type": "text", "text": "..."}]）
            conversation_id: 对话 ID（可选，如果提供则加载历史消息）
            message_id: 消息 ID（可选）
            
        Returns:
            (session_id, agent)
        """
        # 1. 生成 session_id
        session_id = self._generate_session_id()
        
        logger.info(f"🔨 创建新的 Session: session_id={session_id}")
        
        # 2. 提取消息文本用于预览
        message_text = extract_message_text(message)
        
        # 3. 创建 Redis Session 状态
        self.redis.create_session(
            session_id=session_id,
            user_id=user_id,
            conversation_id=conversation_id,
            message_id=message_id,
            message_preview=message_text[:100]
        )
        
        # 3. 创建 Agent 实例
        agent = create_simple_agent(
            model=self.default_model,
            workspace_dir=self.default_workspace,
            event_manager=self.events  # ✅ 传递 EventManager (self.events)
        )
        
        # 4. 加入 Agent 池
        self.agent_pool[session_id] = agent
        
        logger.info(
            f"✅ Session 已创建: session_id={session_id}, "
            f"conversation_id={conversation_id}, user_id={user_id}"
        )
        
        return session_id, agent
    
    def get_agent(self, session_id: str) -> SimpleAgent:
        """
        获取指定 Session 的 Agent
        
        Args:
            session_id: Session ID
            
        Returns:
            Agent 实例
            
        Raises:
            SessionNotFoundError: Session 不存在
        """
        if session_id not in self.agent_pool:
            raise SessionNotFoundError(f"Session 不存在: session_id={session_id}")
        
        return self.agent_pool[session_id]
    
    def end_session(self, session_id: str, status: str = "completed") -> Dict[str, Any]:
        """
        结束 Session
        
        Args:
            session_id: Session ID
            status: 最终状态（completed/failed）
            
        Returns:
            Session 摘要
            
        Raises:
            SessionNotFoundError: Session 不存在
        """
        if session_id not in self.agent_pool:
            raise SessionNotFoundError(f"Session 不存在: session_id={session_id}")
        
        # 更新 Redis Session 状态为完成
        self.redis.complete_session(session_id, status=status)
        
        # 从池中移除
        del self.agent_pool[session_id]
        
        logger.info(f"✅ Session 已结束: session_id={session_id}, status={status}")
        
        return {
            "session_id": session_id,
            "status": status,
            "end_time": datetime.now().isoformat()
        }
    
    async def stop_session(self, session_id: str) -> Dict[str, Any]:
        """
        停止正在运行的 Session（用户主动中断）
        
        Args:
            session_id: Session ID
            
        Returns:
            停止结果
            
        Raises:
            SessionNotFoundError: Session 不存在
        """
        # 检查 Session 是否存在
        status = self.redis.get_session_status(session_id)
        if not status:
            raise SessionNotFoundError(f"Session 不存在或已过期: session_id={session_id}")
        
        # 设置停止标志（Agent 会检测并停止执行）
        self.redis.set_stop_flag(session_id)
        
        # 更新 Session 状态为 stopped
        self.redis.update_session_status(
            session_id,
            status="stopped",
            last_heartbeat=datetime.now().isoformat()
        )
        
        # 发送停止事件（通知前端）
        await self.events.session.emit_session_stopped(
            session_id=session_id,
            reason="user_requested"
        )
        
        logger.info(f"🛑 Session 已停止: session_id={session_id}")
        
        return {
            "session_id": session_id,
            "status": "stopped",
            "stopped_at": datetime.now().isoformat()
        }
    
    def cleanup_inactive_sessions(self) -> int:
        """
        清理不活跃的 Session
        
        Returns:
            清理的 Session 数量
        """
        # 清理 Redis 中超时的 Session
        timeout_cleaned = self.redis.cleanup_timeout_sessions()
        
        if timeout_cleaned:
            logger.info(f"🧹 清理了 {timeout_cleaned} 个超时的 Session")
        
        return timeout_cleaned
    
    # ==================== Session 状态查询 ====================
    
    def get_session_status(self, session_id: str) -> Dict[str, Any]:
        """
        获取 Session 状态（from Redis）
        
        Args:
            session_id: Session ID
            
        Returns:
            Session 状态
            
        Raises:
            SessionNotFoundError: Session 不存在或已过期
        """
        status = self.redis.get_session_status(session_id)
        
        if not status:
            raise SessionNotFoundError(f"Session 不存在或已过期: session_id={session_id}")
        
        return status
    
    def get_session_info(self, session_id: str) -> Dict[str, Any]:
        """
        获取 Session 信息（从 Redis）
        
        Args:
            session_id: Session ID
            
        Returns:
            Session 信息
            
        Raises:
            SessionNotFoundError: Session 不存在
        """
        # 直接从 Redis 获取
        return self.get_session_status(session_id)
    
    def list_sessions(self) -> List[Dict[str, Any]]:
        """
        列出所有活跃 Session（从内存池）
        
        Returns:
            Session 列表
        """
        sessions = []
        for session_id in self.agent_pool.keys():
            try:
                status = self.redis.get_session_status(session_id)
                if status:
                    sessions.append({
                        "session_id": session_id,
                        **status
                    })
            except Exception as e:
                logger.warning(f"⚠️ 获取 Session 信息失败: session_id={session_id}, error={str(e)}")
        
        return sessions
    
    # ==================== Session 事件管理 ====================
    
    def get_session_events(
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
        if not self.redis.get_session_status(session_id):
            raise SessionNotFoundError(f"Session 不存在: session_id={session_id}")
        
        # 获取事件
        events = self.redis.get_events(
            session_id=session_id,
            after_id=after_id,
            limit=limit
        )
        
        return events
    
    def get_user_sessions(self, user_id: str) -> List[Dict[str, Any]]:
        """
        获取用户的所有活跃 Session
        
        Args:
            user_id: 用户 ID
            
        Returns:
            Session 列表（包含详细信息）
        """
        return self.redis.get_user_sessions_detail(user_id)
    
    # ==================== 辅助方法 ====================
    
    def log_session_status(self, session_id: str, conversation_id: Optional[str] = None) -> None:
        """
        输出 Session 状态信息
        
        Args:
            session_id: Session ID
            conversation_id: Conversation ID（可选）
        """
        try:
            status = self.redis.get_session_status(session_id)
            
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


def get_session_service(
    default_model: str = "claude-sonnet-4-5-20250929",
    default_workspace: str = "./workspace"
) -> SessionService:
    """获取默认 Session 服务单例"""
    global _default_service
    if _default_service is None:
        _default_service = SessionService(
            default_model=default_model,
            default_workspace=default_workspace
        )
    return _default_service

