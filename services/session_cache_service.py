"""
会话缓存服务 - SessionCacheService

实现文档中定义的内存会话上下文缓存机制：
- 内存会话上下文管理
- 分页加载支持
- 内存窗口控制

设计原则：
- 在保证会话粘性的前提下，以应用层内存缓存为核心
- 实现极致的读取性能（纳秒级访问）
"""

import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from datetime import datetime
from logger import get_logger
from services.conversation_service import ConversationService, get_conversation_service

logger = get_logger("session_cache_service")


@dataclass
class MessageContext:
    """消息上下文（内存中的简化版本）"""
    id: str
    role: str
    content: str  # JSON 字符串
    created_at: datetime
    metadata: dict = field(default_factory=dict)


@dataclass
class ConversationContext:
    """会话上下文（内存缓存）"""
    conversation_id: str
    messages: List[MessageContext] = field(default_factory=list)
    oldest_cursor: Optional[str] = None  # 用于分页加载更早的消息
    last_updated: datetime = field(default_factory=datetime.now)


class SessionCacheService:
    """
    会话缓存服务
    
    管理应用服务器内存中的活跃会话上下文，实现低延迟读取。
    
    设计原则：
    - 内存中的上下文始终只保留一个有限的窗口（例如最近 100 条）
    - 用于作为 LLM 的 Prompt，以控制 Token 成本和推理延迟
    - 支持冷启动（从数据库加载）和分页加载（向上滚动）
    """
    
    def __init__(
        self,
        conversation_service: Optional[ConversationService] = None,
        max_context_size: int = 100
    ):
        """
        初始化会话缓存服务
        
        Args:
            conversation_service: 对话服务（可选，默认使用单例）
            max_context_size: 内存中保留的最大消息数（默认 100）
        """
        self.conversation_service = conversation_service or get_conversation_service()
        self._active_sessions: Dict[str, ConversationContext] = {}
        self._max_context_size = max_context_size
        
        logger.info(
            f"✅ SessionCacheService 已初始化: max_context_size={max_context_size}"
        )
    
    async def get_context(
        self,
        conversation_id: str
    ) -> ConversationContext:
        """
        获取会话上下文，如果内存中不存在，则从数据库冷启动
        
        Args:
            conversation_id: 对话 ID
            
        Returns:
            会话上下文
        """
        if conversation_id not in self._active_sessions:
            self._active_sessions[conversation_id] = await self._load_from_db(
                conversation_id
            )
            logger.debug(f"📚 会话上下文已加载（冷启动）: conversation_id={conversation_id}")
        
        return self._active_sessions[conversation_id]
    
    async def append_message(
        self,
        conversation_id: str,
        message: MessageContext
    ) -> None:
        """
        向会话追加新消息，并控制内存窗口大小
        
        Args:
            conversation_id: 对话 ID
            message: 消息上下文
        """
        context = await self.get_context(conversation_id)
        context.messages.append(message)
        
        # 控制内存窗口大小（对齐文档规范）
        if len(context.messages) > self._max_context_size:
            # 记录最旧消息的 ID 作为游标
            context.oldest_cursor = context.messages[0].id
            # 只保留最近 N 条
            context.messages = context.messages[-self._max_context_size:]
            logger.debug(
                f"✂️ 内存窗口已裁剪: conversation_id={conversation_id}, "
                f"保留 {len(context.messages)} 条消息"
            )
        
        context.last_updated = datetime.now()
    
    async def _load_from_db(
        self,
        conversation_id: str,
        limit: int = 50
    ) -> ConversationContext:
        """
        从数据库加载最近的 N 条消息（冷启动）
        
        Args:
            conversation_id: 对话 ID
            limit: 加载数量（默认 50）
            
        Returns:
            会话上下文
        """
        # 调用 ConversationService 获取消息
        result = await self.conversation_service.get_conversation_messages(
            conversation_id=conversation_id,
            limit=limit,
            order="desc"  # 从新到旧
        )
        
        messages_data = result.get("messages", [])
        
        # 转换为 MessageContext
        message_contexts = []
        for msg_data in messages_data:
            # 解析 content（可能是 JSON 字符串或已解析的列表）
            content = msg_data.get("content", "[]")
            if isinstance(content, list):
                content = json.dumps(content, ensure_ascii=False)
            elif not isinstance(content, str):
                content = json.dumps(content, ensure_ascii=False)
            
            # 解析 created_at
            created_at_str = msg_data.get("created_at")
            if isinstance(created_at_str, str):
                try:
                    created_at = datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
                except:
                    created_at = datetime.now()
            else:
                created_at = datetime.now()
            
            message_contexts.append(
                MessageContext(
                    id=msg_data.get("id", ""),
                    role=msg_data.get("role", "user"),
                    content=content,
                    created_at=created_at,
                    metadata=msg_data.get("metadata", {})
                )
            )
        
        # 反转为正序（从旧到新）
        message_contexts.reverse()
        
        return ConversationContext(
            conversation_id=conversation_id,
            messages=message_contexts,
            oldest_cursor=message_contexts[0].id if message_contexts else None
        )
    
    async def get_messages_for_llm(
        self,
        conversation_id: str
    ) -> List[Dict[str, Any]]:
        """
        获取用于 LLM 的消息列表（从内存缓存）
        
        返回格式：Claude API 标准格式
        [
            {"role": "user", "content": [...]},
            {"role": "assistant", "content": [...]}
        ]
        
        Args:
            conversation_id: 对话 ID
            
        Returns:
            消息列表（Claude API 格式）
        """
        context = await self.get_context(conversation_id)
        
        # 转换为 Claude API 格式
        llm_messages = []
        for msg_ctx in context.messages:
            # 解析 content（JSON 字符串 -> 列表）
            try:
                content_blocks = json.loads(msg_ctx.content) if msg_ctx.content else []
            except json.JSONDecodeError:
                # 兼容旧格式（纯文本）
                content_blocks = [{"type": "text", "text": msg_ctx.content}]
            
            llm_messages.append({
                "role": msg_ctx.role,
                "content": content_blocks
            })
        
        return llm_messages
    
    def clear_context(self, conversation_id: str) -> None:
        """
        清除会话上下文（用于内存管理）
        
        Args:
            conversation_id: 对话 ID
        """
        if conversation_id in self._active_sessions:
            del self._active_sessions[conversation_id]
            logger.debug(f"🧹 会话上下文已清除: conversation_id={conversation_id}")
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """
        获取缓存统计信息
        
        Returns:
            统计信息字典
        """
        total_sessions = len(self._active_sessions)
        total_messages = sum(
            len(ctx.messages) for ctx in self._active_sessions.values()
        )
        
        return {
            "total_sessions": total_sessions,
            "total_messages": total_messages,
            "max_context_size": self._max_context_size,
            "memory_usage_mb": total_messages * 0.001  # 粗略估算（每条消息约 1KB）
        }


# ==================== 单例管理 ====================

_default_cache_service: Optional[SessionCacheService] = None


def get_session_cache_service() -> SessionCacheService:
    """
    获取会话缓存服务（单例）
    
    Returns:
        SessionCacheService 实例
    """
    global _default_cache_service
    if _default_cache_service is None:
        _default_cache_service = SessionCacheService()
    return _default_cache_service
