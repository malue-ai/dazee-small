"""
Redis Streams 消息队列客户端

实现文档中定义的两阶段持久化机制：
- message_create_stream: 用于创建新消息（占位消息）
- message_update_stream: 用于更新已存在的消息（完整内容）

使用 Redis Streams 实现可靠的异步持久化，解耦应用层和数据库层。
"""

import json
from typing import Dict, Any, Optional, List
from logger import get_logger
from infra.cache.redis import get_redis_client, RedisClient

logger = get_logger("infra.message_queue.streams")


class MessageQueueClient:
    """
    消息队列客户端（Redis Streams）
    
    职责：
    1. 推送消息创建事件到 message_create_stream
    2. 推送消息更新事件到 message_update_stream
    3. 支持消费者组（Consumer Group）机制
    """
    
    # Stream 键名（对齐文档规范）
    CREATE_STREAM_KEY = "agent:message_create_stream"
    UPDATE_STREAM_KEY = "agent:message_update_stream"
    
    def __init__(self, redis_client: Optional[RedisClient] = None):
        """
        初始化消息队列客户端
        
        Args:
            redis_client: Redis 客户端（可选，默认使用单例）
        """
        self._redis_client = redis_client
    
    async def _get_redis(self) -> RedisClient:
        """获取 Redis 客户端"""
        if self._redis_client is None:
            self._redis_client = await get_redis_client()
        return self._redis_client
    
    async def xadd(
        self,
        stream_key: str,
        fields: Dict[str, Any],
        maxlen: Optional[int] = None
    ) -> Optional[str]:
        """
        向 Stream 添加消息
        
        Args:
            stream_key: Stream 键名
            fields: 消息字段（字典）
            maxlen: 最大长度（可选，用于限制 Stream 大小）
            
        Returns:
            消息 ID（如果成功），否则返回 None
        """
        redis = await self._get_redis()
        if not redis.is_connected:
            logger.warning(f"⚠️ Redis 未连接，无法推送消息到 {stream_key}")
            return None
        
        try:
            # 序列化字段值
            serialized_fields = {}
            for key, value in fields.items():
                if isinstance(value, (dict, list)):
                    serialized_fields[key] = json.dumps(value, ensure_ascii=False)
                else:
                    serialized_fields[key] = str(value)
            
            # 调用 Redis Streams XADD 命令
            # 注意：需要直接使用底层 redis 客户端
            if hasattr(redis, '_client') and redis._client:
                message_id = await redis._client.xadd(
                    stream_key,
                    serialized_fields,
                    maxlen=maxlen
                )
                logger.debug(f"✅ 消息已推送到 Stream: {stream_key}, id={message_id}")
                return message_id.decode() if isinstance(message_id, bytes) else str(message_id)
            else:
                logger.warning(f"⚠️ Redis 客户端不可用，无法推送消息")
                return None
                
        except Exception as e:
            logger.error(f"❌ 推送消息到 Stream 失败: {stream_key}, error={str(e)}", exc_info=True)
            return None
    
    async def push_create_event(
        self,
        message_id: str,
        conversation_id: str,
        role: str,
        content: str,
        status: str,
        metadata: Dict[str, Any]
    ) -> Optional[str]:
        """
        推送消息创建事件到 message_create_stream
        
        Args:
            message_id: 消息 ID
            conversation_id: 对话 ID
            role: 消息角色
            content: 消息内容（JSON 字符串）
            status: 消息状态
            metadata: 消息元数据
            
        Returns:
            消息 ID（如果成功）
        """
        fields = {
            "message_id": message_id,
            "conversation_id": conversation_id,
            "role": role,
            "content": content,
            "status": status,
            "metadata": metadata
        }
        
        return await self.xadd(self.CREATE_STREAM_KEY, fields)
    
    async def push_update_event(
        self,
        message_id: str,
        content: Optional[str] = None,
        status: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """
        推送消息更新事件到 message_update_stream
        
        Args:
            message_id: 消息 ID
            content: 消息内容（可选）
            status: 消息状态（可选）
            metadata: 消息元数据（可选）
            
        Returns:
            消息 ID（如果成功）
        """
        fields = {
            "message_id": message_id
        }
        
        if content is not None:
            fields["content"] = content
        if status is not None:
            fields["status"] = status
        if metadata is not None:
            fields["metadata"] = metadata
        
        return await self.xadd(self.UPDATE_STREAM_KEY, fields)
    
    async def create_consumer_group(
        self,
        stream_key: str,
        group_name: str,
        start_id: str = "0"
    ) -> bool:
        """
        创建消费者组
        
        Args:
            stream_key: Stream 键名
            group_name: 消费者组名称
            start_id: 起始消息 ID（默认 "0" 表示从开始）
            
        Returns:
            是否创建成功
        """
        redis = await self._get_redis()
        if not redis.is_connected:
            return False
        
        try:
            if hasattr(redis, '_client') and redis._client:
                await redis._client.xgroup_create(
                    stream_key,
                    group_name,
                    id=start_id,
                    mkstream=True  # 如果 Stream 不存在则创建
                )
                logger.info(f"✅ 消费者组已创建: {stream_key}/{group_name}")
                return True
        except Exception as e:
            # 消费者组可能已存在，这是正常的
            if "BUSYGROUP" in str(e):
                logger.debug(f"消费者组已存在: {stream_key}/{group_name}")
                return True
            logger.warning(f"⚠️ 创建消费者组失败: {stream_key}/{group_name}, error={str(e)}")
            return False
        
        return False
    
    async def get_pending_count(
        self,
        stream_key: str,
        group_name: str
    ) -> int:
        """
        获取待处理消息数量
        
        Args:
            stream_key: Stream 键名
            group_name: 消费者组名称
            
        Returns:
            待处理消息数量
        """
        redis = await self._get_redis()
        if not redis.is_connected:
            return 0
        
        try:
            if hasattr(redis, '_client') and redis._client:
                pending_info = await redis._client.xpending(stream_key, group_name)
                if pending_info:
                    return pending_info.get('pending', 0)
        except Exception as e:
            logger.warning(f"⚠️ 获取待处理消息数量失败: {stream_key}/{group_name}, error={str(e)}")
        
        return 0


# ==================== 单例管理 ====================

_message_queue_client: Optional[MessageQueueClient] = None


async def get_message_queue_client() -> MessageQueueClient:
    """
    获取消息队列客户端（单例）
    
    Returns:
        MessageQueueClient 实例
    """
    global _message_queue_client
    if _message_queue_client is None:
        _message_queue_client = MessageQueueClient()
    return _message_queue_client
