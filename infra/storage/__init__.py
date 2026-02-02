"""
存储层抽象

提供统一的存储接口和异步写入优化
"""

# 旧的存储接口（兼容）
from infra.storage.base import StorageBackend
from infra.storage.local import LocalStorage

# 新的存储优化组件
from infra.storage.async_writer import AsyncWriter, WriteTask
from infra.storage.batch_writer import BatchWriter, BatchConfig
from infra.storage.storage_manager import StorageManager, get_storage_manager

__all__ = [
    # 旧接口
    "StorageBackend",
    "LocalStorage",
    # 新组件
    "AsyncWriter",
    "WriteTask",
    "BatchWriter",
    "BatchConfig",
    "StorageManager",
    "get_storage_manager",
]
