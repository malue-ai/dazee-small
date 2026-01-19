"""
消息队列 Worker（后台消费者）

实现文档中定义的异步持久化机制：
- InsertWorker: 消费 message_create_stream，执行 INSERT 操作
- UpdateWorker: 消费 message_update_stream，执行 UPDATE 操作

使用 Redis Streams 消费者组机制，确保消息可靠处理。
"""

import json
import asyncio
from typing import Dict, Any, Optional
from logger import get_logger
from infra.cache.redis import get_redis_client, RedisClient
from infra.message_queue.streams import MessageQueueClient
from infra.database import AsyncSessionLocal, crud

logger = get_logger("infra.message_queue.workers")


class InsertWorker:
    """
    插入消息 Worker
    
    消费 message_create_stream，执行 INSERT 操作到 PostgreSQL
    """
    
    def __init__(
        self,
        group_name: str = "insert_workers",
        consumer_name: str = None,
        batch_size: int = 10,
        block_time: int = 5000
    ):
        """
        初始化 Insert Worker
        
        Args:
            group_name: 消费者组名称
            consumer_name: 消费者名称（可选，默认自动生成）
            batch_size: 批量处理大小
            block_time: 阻塞等待时间（毫秒）
        """
        self.group_name = group_name
        self.consumer_name = consumer_name or f"insert_worker_{id(self)}"
        self.batch_size = batch_size
        self.block_time = block_time
        self.mq_client = MessageQueueClient()
        self._running = False
    
    async def start(self) -> None:
        """启动 Worker"""
        self._running = True
        
        # 创建消费者组
        await self.mq_client.create_consumer_group(
            MessageQueueClient.CREATE_STREAM_KEY,
            self.group_name
        )
        
        logger.info(f"✅ InsertWorker 已启动: {self.consumer_name}")
        
        # 开始消费循环
        while self._running:
            try:
                await self._process_batch()
            except Exception as e:
                logger.error(f"❌ InsertWorker 处理失败: {str(e)}", exc_info=True)
                await asyncio.sleep(1)  # 错误后等待 1 秒再继续
    
    async def stop(self) -> None:
        """停止 Worker"""
        self._running = False
        logger.info(f"🛑 InsertWorker 已停止: {self.consumer_name}")
    
    async def _process_batch(self) -> None:
        """处理一批消息"""
        redis = await get_redis_client()
        if not redis.is_connected:
            await asyncio.sleep(1)
            return
        
        try:
            if hasattr(redis, '_client') and redis._client:
                # 从 Stream 读取消息（使用消费者组）
                messages = await redis._client.xreadgroup(
                    self.group_name,
                    self.consumer_name,
                    {MessageQueueClient.CREATE_STREAM_KEY: ">"},
                    count=self.batch_size,
                    block=self.block_time
                )
                
                if not messages:
                    return
                
                # 处理每条消息
                for stream_key, stream_messages in messages:
                    for message_id, fields in stream_messages:
                        await self._process_message(message_id, fields)
                        
        except Exception as e:
            logger.error(f"❌ 读取消息失败: {str(e)}", exc_info=True)
            raise
    
    async def _process_message(
        self,
        message_id: str,
        fields: Dict[bytes, bytes]
    ) -> None:
        """
        处理单条消息
        
        Args:
            message_id: Stream 消息 ID
            fields: 消息字段（字节格式）
        """
        try:
            # 解码字段
            decoded_fields = {}
            for key, value in fields.items():
                key_str = key.decode() if isinstance(key, bytes) else key
                value_str = value.decode() if isinstance(value, bytes) else value
                decoded_fields[key_str] = value_str
            
            # 解析字段
            msg_id = decoded_fields.get("message_id")
            conversation_id = decoded_fields.get("conversation_id")
            role = decoded_fields.get("role")
            content = decoded_fields.get("content", "[]")
            status = decoded_fields.get("status", "processing")
            
            # 解析 metadata
            metadata_str = decoded_fields.get("metadata", "{}")
            try:
                metadata = json.loads(metadata_str) if metadata_str else {}
            except json.JSONDecodeError:
                metadata = {}
            
            # 执行 INSERT 操作
            async with AsyncSessionLocal() as session:
                await crud.create_message(
                    session=session,
                    conversation_id=conversation_id,
                    role=role,
                    content=content,
                    message_id=msg_id,
                    status=status,
                    metadata=metadata
                )
            
            # ACK 消息（标记为已处理）
            redis = await get_redis_client()
            if redis.is_connected and hasattr(redis, '_client') and redis._client:
                await redis._client.xack(
                    MessageQueueClient.CREATE_STREAM_KEY,
                    self.group_name,
                    message_id
                )
            
            logger.debug(f"✅ 消息已插入: message_id={msg_id}, status={status}")
            
        except Exception as e:
            logger.error(f"❌ 处理消息失败: message_id={message_id}, error={str(e)}", exc_info=True)
            # 注意：不 ACK，让消息重新被处理


class UpdateWorker:
    """
    更新消息 Worker
    
    消费 message_update_stream，执行 UPDATE 操作到 PostgreSQL
    """
    
    def __init__(
        self,
        group_name: str = "update_workers",
        consumer_name: str = None,
        batch_size: int = 10,
        block_time: int = 5000
    ):
        """
        初始化 Update Worker
        
        Args:
            group_name: 消费者组名称
            consumer_name: 消费者名称（可选，默认自动生成）
            batch_size: 批量处理大小
            block_time: 阻塞等待时间（毫秒）
        """
        self.group_name = group_name
        self.consumer_name = consumer_name or f"update_worker_{id(self)}"
        self.batch_size = batch_size
        self.block_time = block_time
        self.mq_client = MessageQueueClient()
        self._running = False
    
    async def start(self) -> None:
        """启动 Worker"""
        self._running = True
        
        # 创建消费者组
        await self.mq_client.create_consumer_group(
            MessageQueueClient.UPDATE_STREAM_KEY,
            self.group_name
        )
        
        logger.info(f"✅ UpdateWorker 已启动: {self.consumer_name}")
        
        # 开始消费循环
        while self._running:
            try:
                await self._process_batch()
            except Exception as e:
                logger.error(f"❌ UpdateWorker 处理失败: {str(e)}", exc_info=True)
                await asyncio.sleep(1)  # 错误后等待 1 秒再继续
    
    async def stop(self) -> None:
        """停止 Worker"""
        self._running = False
        logger.info(f"🛑 UpdateWorker 已停止: {self.consumer_name}")
    
    async def _process_batch(self) -> None:
        """处理一批消息"""
        redis = await get_redis_client()
        if not redis.is_connected:
            await asyncio.sleep(1)
            return
        
        try:
            if hasattr(redis, '_client') and redis._client:
                # 从 Stream 读取消息（使用消费者组）
                messages = await redis._client.xreadgroup(
                    self.group_name,
                    self.consumer_name,
                    {MessageQueueClient.UPDATE_STREAM_KEY: ">"},
                    count=self.batch_size,
                    block=self.block_time
                )
                
                if not messages:
                    return
                
                # 处理每条消息
                for stream_key, stream_messages in messages:
                    for message_id, fields in stream_messages:
                        await self._process_message(message_id, fields)
                        
        except Exception as e:
            logger.error(f"❌ 读取消息失败: {str(e)}", exc_info=True)
            raise
    
    async def _process_message(
        self,
        message_id: str,
        fields: Dict[bytes, bytes]
    ) -> None:
        """
        处理单条消息（执行 UPDATE 操作）
        
        Args:
            message_id: Stream 消息 ID
            fields: 消息字段（字节格式）
        """
        try:
            # 解码字段
            decoded_fields = {}
            for key, value in fields.items():
                key_str = key.decode() if isinstance(key, bytes) else key
                value_str = value.decode() if isinstance(value, bytes) else value
                decoded_fields[key_str] = value_str
            
            # 解析字段
            msg_id = decoded_fields.get("message_id")
            content = decoded_fields.get("content")
            status = decoded_fields.get("status")
            
            # 解析 metadata（用于深度合并）
            metadata_str = decoded_fields.get("metadata", "{}")
            metadata = None
            if metadata_str:
                try:
                    metadata = json.loads(metadata_str)
                except json.JSONDecodeError:
                    metadata = None
            
            # 执行 UPDATE 操作
            async with AsyncSessionLocal() as session:
                await crud.update_message(
                    session=session,
                    message_id=msg_id,
                    content=content,
                    status=status,
                    metadata=metadata  # crud.update_message 会处理深度合并
                )
            
            # ACK 消息（标记为已处理）
            redis = await get_redis_client()
            if redis.is_connected and hasattr(redis, '_client') and redis._client:
                await redis._client.xack(
                    MessageQueueClient.UPDATE_STREAM_KEY,
                    self.group_name,
                    message_id
                )
            
            logger.debug(f"✅ 消息已更新: message_id={msg_id}, status={status}")
            
        except Exception as e:
            logger.error(f"❌ 处理消息失败: message_id={message_id}, error={str(e)}", exc_info=True)
            # 注意：不 ACK，让消息重新被处理


async def start_workers() -> None:
    """
    启动所有 Worker（用于独立进程或后台任务）
    
    使用示例：
        # 在独立进程中运行
        import asyncio
        asyncio.run(start_workers())
    """
    insert_worker = InsertWorker()
    update_worker = UpdateWorker()
    
    # 并发启动两个 Worker
    await asyncio.gather(
        insert_worker.start(),
        update_worker.start()
    )
