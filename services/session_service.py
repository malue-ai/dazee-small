"""
Session 服务层 - Session Management Service（异步版本）

职责：
1. Session 生命周期管理（创建、获取、结束、清理）
2. Session 状态查询
3. Session 事件管理
4. Agent 池管理

设计原则：
- 单一职责：只管理 Session 和 Agent 池
- Session 状态存储在 Redis
- 支持多用户并发 Session
- 所有方法都是异步的，避免阻塞事件循环
"""

from typing import Dict, Any, Optional, List
from datetime import datetime
from uuid import uuid4

from logger import get_logger
from core.agent import SimpleAgent, create_simple_agent
from core.context import create_context
from core.events import create_event_manager
from core.workspace_manager import WorkspaceManager
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
        self.workspace_manager = WorkspaceManager(base_dir=default_workspace)
        
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
        conversation_id: str,
        message_id: Optional[str] = None,
        conversation_service=None
    ) -> tuple[str, SimpleAgent]:
        """
        =====================================================================
        阶段 1: Session/Agent 初始化
        =====================================================================
        （参考 docs/00-ARCHITECTURE-V4.md L1701-1722）
        
        1️⃣ 检查 Agent 池是否已有该 session 的 Agent
        2️⃣ 如果没有，调用 AgentFactory 创建 AgentSchema
        3️⃣ 初始化核心组件：
           • CapabilityRegistry.load("capabilities.yaml")
           • IntentAnalyzer(llm_model="claude-haiku-4-5-20251001")
           • ToolSelector(registry, schema.tools)
           • ToolExecutor(tools_dir="tools/")
           • EventBroadcaster(event_manager)
           • E2EPipelineTracer(session_id, conversation_id)
        4️⃣ 启用已注册的 Claude Skills
        
        Args:
            user_id: 用户 ID
            message: 用户消息（Claude API 格式 [{"type": "text", "text": "..."}]）
            conversation_id: 对话 ID（必填，ChatService 会确保在调用前已创建）
            message_id: 消息 ID（可选）
            conversation_service: ConversationService 实例（用于消息持久化）
            
        Returns:
            (session_id, agent)
        """
        # 1️⃣ 生成 session_id
        session_id = self._generate_session_id()
        
        logger.info(f"🔨 创建新的 Session: session_id={session_id}, conversation_id={conversation_id}")
        
        # 1.1 提取消息文本用于预览
        message_text = extract_message_text(message)
        
        # 1.2 创建 Redis Session 状态（异步）
        await self.redis.create_session(
            session_id=session_id,
            user_id=user_id,
            conversation_id=conversation_id,
            message_id=message_id,
            message_preview=message_text[:100]
        )
        
        # 2️⃣ 创建 Agent 实例（完成所有核心组件初始化）
        # 按 conversation_id 隔离工作区，保证每个 Agent 只能在该对话目录下工作
        workspace_dir = str(self.workspace_manager.get_workspace_root(conversation_id))

        # create_simple_agent 内部会初始化：
        # • CapabilityRegistry（加载 capabilities.yaml）
        # • IntentAnalyzer（使用 Haiku 4.5）
        # • ToolSelector, ToolExecutor
        # • EventBroadcaster, E2EPipelineTracer
        # • Context Engineering Manager
        # • 启用已注册的 Claude Skills
        agent = create_simple_agent(
            model=self.default_model,
            workspace_dir=workspace_dir,
            event_manager=self.events,
            conversation_service=conversation_service
        )
        
        # 3️⃣ 加入 Agent 池（支持 Session 复用）
        self.agent_pool[session_id] = agent
        
        logger.info(
            f"✅ 阶段 1 完成: session_id={session_id}, "
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
    
    async def end_session(self, session_id: str, status: str = "completed") -> Dict[str, Any]:
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
        await self.redis.complete_session(session_id, status=status)
        
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
        status = await self.redis.get_session_status(session_id)
        if not status:
            raise SessionNotFoundError(f"Session 不存在或已过期: session_id={session_id}")
        
        # 设置停止标志（Agent 会检测并停止执行）
        await self.redis.set_stop_flag(session_id)
        
        # 更新 Session 状态为 stopped
        await self.redis.update_session_status(
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
    
    async def list_sessions(self) -> List[Dict[str, Any]]:
        """
        列出所有活跃 Session（从内存池）
        
        Returns:
            Session 列表
        """
        sessions = []
        for session_id in self.agent_pool.keys():
            try:
                status = await self.redis.get_session_status(session_id)
                if status:
                    sessions.append({
                        "session_id": session_id,
                        **status
                    })
            except Exception as e:
                logger.warning(f"⚠️ 获取 Session 信息失败: session_id={session_id}, error={str(e)}")
        
        return sessions
    
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
