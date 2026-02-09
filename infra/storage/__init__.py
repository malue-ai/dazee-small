"""
存储层抽象

提供统一的存储接口和异步写入优化
"""

# 存储后端接口
from infra.storage.base import StorageBackend
from infra.storage.local import LocalStorage

# 异步写入优化
from infra.storage.async_writer import AsyncWriter, WriteTask
from infra.storage.batch_writer import BatchWriter, BatchConfig
from infra.storage.storage_manager import StorageManager, get_storage_manager

__all__ = [
    # 存储后端
    "StorageBackend",
    "LocalStorage",
    # 异步写入
    "AsyncWriter",
    "WriteTask",
    "BatchWriter",
    "BatchConfig",
    "StorageManager",
    "get_storage_manager",
]
