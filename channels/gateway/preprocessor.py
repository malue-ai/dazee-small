"""
消息预处理器

负责：
- 消息去重
- 入站防抖（合并快速连续消息）
- 文本片段合并（长消息拆分后合并）
- 媒体组合并（多图消息合并）
"""

import asyncio
import time
from typing import Dict, Any, Optional, List, Set
from collections import OrderedDict
from dataclasses import dataclass, field
from channels.base.types import InboundMessage, ProcessedMessage
from logger import get_logger

logger = get_logger("channel_preprocessor")


# ===========================================================================
# 消息去重
# ===========================================================================

class MessageDeduper:
    """
    消息去重器
    
    使用 LRU 缓存记录已处理的消息 ID，避免重复处理
    
    Attributes:
        max_size: 缓存最大容量
        ttl_seconds: 缓存过期时间
    """
    
    def __init__(self, max_size: int = 10000, ttl_seconds: int = 300):
        """
        初始化去重器
        
        Args:
            max_size: 缓存最大容量
            ttl_seconds: 缓存过期时间（秒）
        """
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self._cache: OrderedDict[str, float] = OrderedDict()
    
    def is_duplicate(self, message: InboundMessage) -> bool:
        """
        检查消息是否重复
        
        Args:
            message: 入站消息
            
        Returns:
            是否重复
        """
        # 生成去重 key
        key = self._make_key(message)
        now = time.time()
        
        # 清理过期记录
        self._cleanup(now)
        
        # 检查是否存在
        if key in self._cache:
            logger.debug(f"重复消息: {key}")
            return True
        
        # 记录
        self._cache[key] = now
        
        # 保持大小限制
        while len(self._cache) > self.max_size:
            self._cache.popitem(last=False)
        
        return False
    
    def _make_key(self, message: InboundMessage) -> str:
        """生成去重 key"""
        return f"{message.channel_id}:{message.message_id}"
    
    def _cleanup(self, now: float) -> None:
        """清理过期记录"""
        expired = []
        for key, timestamp in self._cache.items():
            if now - timestamp > self.ttl_seconds:
                expired.append(key)
            else:
                break  # OrderedDict 按插入顺序排列
        
        for key in expired:
            del self._cache[key]


# ===========================================================================
# 入站防抖
# ===========================================================================

@dataclass
class PendingMessages:
    """待处理消息组"""
    messages: List[InboundMessage] = field(default_factory=list)
    timer_task: Optional[asyncio.Task] = None
    created_at: float = field(default_factory=time.time)


class InboundDebouncer:
    """
    入站防抖器
    
    合并快速连续发送的消息，避免 Agent 被频繁触发
    
    Attributes:
        debounce_ms: 防抖延迟（毫秒）
        max_messages: 最大合并消息数
        max_wait_ms: 最大等待时间（毫秒）
    """
    
    def __init__(
        self,
        debounce_ms: int = 500,
        max_messages: int = 10,
        max_wait_ms: int = 3000
    ):
        """
        初始化防抖器
        
        Args:
            debounce_ms: 防抖延迟（毫秒）
            max_messages: 最大合并消息数
            max_wait_ms: 最大等待时间（毫秒）
        """
        self.debounce_ms = debounce_ms
        self.max_messages = max_messages
        self.max_wait_ms = max_wait_ms
        
        # chat_id -> PendingMessages
        self._pending: Dict[str, PendingMessages] = {}
        
        # 消息处理回调
        self._callback: Optional[callable] = None
    
    def set_callback(self, callback: callable) -> None:
        """设置消息处理回调"""
        self._callback = callback
    
    async def enqueue(self, message: InboundMessage) -> Optional[ProcessedMessage]:
        """
        将消息加入队列
        
        Args:
            message: 入站消息
            
        Returns:
            合并后的消息（如果触发了处理），否则 None
        """
        key = self._make_key(message)
        
        if key not in self._pending:
            self._pending[key] = PendingMessages()
        
        pending = self._pending[key]
        pending.messages.append(message)
        
        # 取消之前的定时器
        if pending.timer_task and not pending.timer_task.done():
            pending.timer_task.cancel()
        
        # 检查是否需要立即处理
        now = time.time()
        elapsed_ms = (now - pending.created_at) * 1000
        
        if len(pending.messages) >= self.max_messages or elapsed_ms >= self.max_wait_ms:
            return await self._flush(key)
        
        # 设置新的定时器
        pending.timer_task = asyncio.create_task(
            self._delayed_flush(key, self.debounce_ms / 1000)
        )
        
        return None
    
    async def _delayed_flush(self, key: str, delay: float) -> None:
        """延迟刷新"""
        await asyncio.sleep(delay)
        await self._flush(key)
    
    async def _flush(self, key: str) -> Optional[ProcessedMessage]:
        """
        刷新并处理消息
        
        Args:
            key: 聊天 key
            
        Returns:
            合并后的消息
        """
        if key not in self._pending:
            return None
        
        pending = self._pending.pop(key)
        
        if not pending.messages:
            return None
        
        # 合并消息
        merged = self._merge_messages(pending.messages)
        
        logger.debug(
            f"防抖合并: key={key}, count={len(pending.messages)}, "
            f"content_len={len(merged.content)}"
        )
        
        # 调用回调
        if self._callback:
            try:
                await self._callback(merged)
            except Exception as e:
                logger.error(f"消息处理回调失败: {e}", exc_info=True)
        
        return merged
    
    def _make_key(self, message: InboundMessage) -> str:
        """生成聊天 key"""
        return f"{message.channel_id}:{message.account_id}:{message.chat_id}"
    
    def _merge_messages(self, messages: List[InboundMessage]) -> ProcessedMessage:
        """合并多条消息"""
        first = messages[0]
        
        # 合并文本内容
        contents = [m.content for m in messages if m.content]
        merged_content = "\n".join(contents)
        
        # 合并媒体
        merged_media = []
        for m in messages:
            merged_media.extend(m.media)
        
        # 收集原始事件
        raw_events = [m.raw_event for m in messages if m.raw_event]
        
        return ProcessedMessage(
            message_id=first.message_id,
            channel_id=first.channel_id,
            account_id=first.account_id,
            chat_id=first.chat_id,
            chat_type=first.chat_type,
            sender_id=first.sender_id,
            sender_name=first.sender_name,
            content=merged_content,
            msg_type=first.msg_type,
            media=merged_media,
            reply_to=first.reply_to,
            thread_id=first.thread_id,
            mentions=first.mentions,
            timestamp=first.timestamp,
            raw_events=raw_events,
            merged_count=len(messages)
        )


# ===========================================================================
# 文本片段合并
# ===========================================================================

@dataclass
class FragmentBuffer:
    """文本片段缓冲"""
    fragments: List[InboundMessage] = field(default_factory=list)
    timer_task: Optional[asyncio.Task] = None
    created_at: float = field(default_factory=time.time)


class TextFragmentBuffer:
    """
    文本片段合并器
    
    用于合并被拆分的长消息（如 Telegram 的 4096 字符限制）
    
    Attributes:
        threshold: 触发合并的字符阈值
        max_interval_ms: 最大等待间隔（毫秒）
        max_parts: 最大片段数
    """
    
    def __init__(
        self,
        threshold: int = 4000,
        max_interval_ms: int = 1500,
        max_parts: int = 12
    ):
        """
        初始化文本片段合并器
        
        Args:
            threshold: 触发合并的字符阈值
            max_interval_ms: 最大等待间隔（毫秒）
            max_parts: 最大片段数
        """
        self.threshold = threshold
        self.max_interval_ms = max_interval_ms
        self.max_parts = max_parts
        
        # key -> FragmentBuffer
        self._buffers: Dict[str, FragmentBuffer] = {}
    
    async def add(self, message: InboundMessage) -> Optional[InboundMessage]:
        """
        添加文本片段
        
        Args:
            message: 入站消息
            
        Returns:
            合并后的消息（如果完成），否则 None
        """
        key = self._make_key(message)
        
        if key not in self._buffers:
            self._buffers[key] = FragmentBuffer()
        
        buffer = self._buffers[key]
        buffer.fragments.append(message)
        
        # 取消之前的定时器
        if buffer.timer_task and not buffer.timer_task.done():
            buffer.timer_task.cancel()
        
        # 检查是否需要立即合并
        total_length = sum(len(f.content) for f in buffer.fragments)
        
        if len(buffer.fragments) >= self.max_parts or total_length >= self.threshold * 2:
            return self._merge(key)
        
        # 设置新的定时器
        buffer.timer_task = asyncio.create_task(
            self._delayed_merge(key)
        )
        
        return None
    
    async def _delayed_merge(self, key: str) -> None:
        """延迟合并"""
        await asyncio.sleep(self.max_interval_ms / 1000)
        self._merge(key)
    
    def _merge(self, key: str) -> Optional[InboundMessage]:
        """合并文本片段"""
        if key not in self._buffers:
            return None
        
        buffer = self._buffers.pop(key)
        
        if not buffer.fragments:
            return None
        
        first = buffer.fragments[0]
        
        # 合并内容
        merged_content = "".join(f.content for f in buffer.fragments)
        
        logger.debug(
            f"文本片段合并: key={key}, parts={len(buffer.fragments)}, "
            f"total_len={len(merged_content)}"
        )
        
        # 返回合并后的消息
        return InboundMessage(
            message_id=first.message_id,
            channel_id=first.channel_id,
            account_id=first.account_id,
            chat_id=first.chat_id,
            chat_type=first.chat_type,
            sender_id=first.sender_id,
            sender_name=first.sender_name,
            content=merged_content,
            msg_type=first.msg_type,
            media=first.media,
            reply_to=first.reply_to,
            thread_id=first.thread_id,
            mentions=first.mentions,
            timestamp=first.timestamp,
            raw_event=first.raw_event,
            is_fragment=False
        )
    
    def _make_key(self, message: InboundMessage) -> str:
        """生成缓冲 key"""
        return f"{message.channel_id}:{message.account_id}:{message.chat_id}:{message.sender_id}"


# ===========================================================================
# 媒体组合并
# ===========================================================================

@dataclass
class MediaGroupPending:
    """媒体组待处理"""
    messages: List[InboundMessage] = field(default_factory=list)
    timer_task: Optional[asyncio.Task] = None


class MediaGroupBuffer:
    """
    媒体组合并器
    
    用于合并多图消息（同一个 media_group_id 的消息）
    
    Attributes:
        timeout_ms: 等待超时（毫秒）
    """
    
    def __init__(self, timeout_ms: int = 500):
        """
        初始化媒体组合并器
        
        Args:
            timeout_ms: 等待超时（毫秒）
        """
        self.timeout_ms = timeout_ms
        
        # media_group_id -> MediaGroupPending
        self._groups: Dict[str, MediaGroupPending] = {}
    
    async def add(self, message: InboundMessage) -> Optional[InboundMessage]:
        """
        添加媒体组消息
        
        Args:
            message: 入站消息
            
        Returns:
            合并后的消息（如果完成），否则 None
        """
        group_id = message.media_group_id
        if not group_id:
            return message  # 非媒体组，直接返回
        
        if group_id not in self._groups:
            self._groups[group_id] = MediaGroupPending()
        
        pending = self._groups[group_id]
        pending.messages.append(message)
        
        # 取消之前的定时器
        if pending.timer_task and not pending.timer_task.done():
            pending.timer_task.cancel()
        
        # 设置新的定时器
        pending.timer_task = asyncio.create_task(
            self._delayed_flush(group_id)
        )
        
        return None
    
    async def _delayed_flush(self, group_id: str) -> None:
        """延迟刷新"""
        await asyncio.sleep(self.timeout_ms / 1000)
        self._flush(group_id)
    
    def _flush(self, group_id: str) -> Optional[InboundMessage]:
        """刷新媒体组"""
        if group_id not in self._groups:
            return None
        
        pending = self._groups.pop(group_id)
        
        if not pending.messages:
            return None
        
        first = pending.messages[0]
        
        # 合并媒体
        merged_media = []
        for m in pending.messages:
            merged_media.extend(m.media)
        
        # 合并 caption
        captions = [m.content for m in pending.messages if m.content]
        merged_caption = "\n".join(captions) if captions else ""
        
        logger.debug(
            f"媒体组合并: group_id={group_id}, count={len(pending.messages)}, "
            f"media_count={len(merged_media)}"
        )
        
        return InboundMessage(
            message_id=first.message_id,
            channel_id=first.channel_id,
            account_id=first.account_id,
            chat_id=first.chat_id,
            chat_type=first.chat_type,
            sender_id=first.sender_id,
            sender_name=first.sender_name,
            content=merged_caption,
            msg_type="media_group",
            media=merged_media,
            reply_to=first.reply_to,
            thread_id=first.thread_id,
            mentions=first.mentions,
            timestamp=first.timestamp,
            raw_event=first.raw_event,
            media_group_id=group_id
        )


# ===========================================================================
# 统一预处理器
# ===========================================================================

class MessagePreprocessor:
    """
    消息预处理器
    
    整合所有预处理功能：
    1. 去重
    2. 文本片段合并
    3. 媒体组合并
    4. 防抖
    """
    
    def __init__(
        self,
        deduper: MessageDeduper = None,
        debouncer: InboundDebouncer = None,
        fragment_buffer: TextFragmentBuffer = None,
        media_buffer: MediaGroupBuffer = None
    ):
        """
        初始化预处理器
        
        Args:
            deduper: 去重器
            debouncer: 防抖器
            fragment_buffer: 文本片段缓冲
            media_buffer: 媒体组缓冲
        """
        self.deduper = deduper or MessageDeduper()
        self.debouncer = debouncer or InboundDebouncer()
        self.fragment_buffer = fragment_buffer or TextFragmentBuffer()
        self.media_buffer = media_buffer or MediaGroupBuffer()
    
    async def process(self, message: InboundMessage) -> Optional[ProcessedMessage]:
        """
        预处理消息
        
        Args:
            message: 入站消息
            
        Returns:
            预处理后的消息，如果需要等待则返回 None
        """
        # 1. 去重检查
        if self.deduper.is_duplicate(message):
            return None
        
        # 2. 文本片段合并
        if message.is_fragment:
            merged = await self.fragment_buffer.add(message)
            if merged is None:
                return None
            message = merged
        
        # 3. 媒体组合并
        if message.media_group_id:
            merged = await self.media_buffer.add(message)
            if merged is None:
                return None
            message = merged
        
        # 4. 防抖（返回合并后的 ProcessedMessage）
        return await self.debouncer.enqueue(message)
