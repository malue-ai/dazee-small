"""
存储层抽象

提供统一的存储接口和异步写入优化
"""

from core.storage.async_writer import AsyncWriter, WriteTask
from core.storage.batch_writer import BatchWriter, BatchConfig
from core.storage.storage_manager import StorageManager, get_storage_manager

__all__ = [
    "AsyncWriter",
    "WriteTask",
    "BatchWriter",
    "BatchConfig",
    "StorageManager",
    "get_storage_manager",
]
