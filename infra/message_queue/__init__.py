"""
消息队列模块

提供 Redis Streams 消息队列客户端，用于异步持久化。
"""

from infra.message_queue.streams import (
    MessageQueueClient,
    get_message_queue_client,
    MessageQueueClient as MQClient
)

__all__ = [
    "MessageQueueClient",
    "get_message_queue_client",
    "MQClient"
]
