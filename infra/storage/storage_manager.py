"""
存储管理器

统一管理存储层组件（AsyncWriter + BatchWriter + Cache）
"""

import asyncio
from typing import Optional, Dict, Any, Callable
from datetime import datetime, timedelta

from logger import get_logger
from infra.storage.async_writer import AsyncWriter
from infra.storage.batch_writer import BatchWriter, BatchConfig

logger = get_logger(__name__)


class StorageManager:
    """
    存储管理器
    
    职责：
    - 管理 AsyncWriter 和 BatchWriter 实例
    - 提供统一的存储接口
    - 生命周期管理（启动/关闭）
    - 统计信息收集
    
    使用示例:
        manager = StorageManager()
        await manager.start()
        
        # 异步写入（单条）
        await manager.async_write("conversation", save_conversation, conv_id, data)
        
        # 批量写入（多条）
        await manager.batch_write("messages", message_data)
        
        # 关闭
        await manager.shutdown()
    """
    
    def __init__(
        self,
        async_writer_config: Optional[Dict[str, Any]] = None,
        batch_writer_configs: Optional[Dict[str, BatchConfig]] = None
    ):
        # AsyncWriter（全局单例）
        self.async_writer: Optional[AsyncWriter] = None
        self.async_writer_config = async_writer_config or {
            "max_queue_size": 10000,
            "worker_count": 5,
            "max_retries": 3
        }
        
        # BatchWriter（按类型分组）
        self.batch_writers: Dict[str, BatchWriter] = {}
        self.batch_writer_configs = batch_writer_configs or {}
        
        self.running = False
    
    async def start(self):
        """启动存储管理器"""
        if self.running:
            logger.warning("StorageManager 已经在运行")
            return
        
        logger.info("🚀 StorageManager 启动中...")
        
        # 启动 AsyncWriter
        self.async_writer = AsyncWriter(**self.async_writer_config)
        await self.async_writer.start()
        
        self.running = True
        logger.info("✅ StorageManager 已启动")
    
    async def async_write(
        self,
        category: str,
        operation: Callable,
        *args,
        **kwargs
    ) -> str:
        """
        异步写入（单条）
        
        Args:
            category: 分类（如 "conversation", "message"）
            operation: 写入操作
            *args: 操作参数
            **kwargs: 操作关键字参数
            
        Returns:
            任务ID
        """
        if not self.running or self.async_writer is None:
            raise RuntimeError("StorageManager 未启动")
        
        task_id = await self.async_writer.submit(
            operation,
            *args,
            task_id=f"{category}_{int(datetime.now().timestamp() * 1000)}",
            **kwargs
        )
        
        return task_id
    
    def register_batch_writer(
        self,
        writer_name: str,
        batch_operation: Callable,
        config: Optional[BatchConfig] = None
    ):
        """
        注册批量写入器
        
        Args:
            writer_name: 写入器名称（如 "messages", "events"）
            batch_operation: 批量操作函数
            config: 批量配置
        """
        if writer_name in self.batch_writers:
            logger.warning(f"⚠️ BatchWriter '{writer_name}' 已存在，将被覆盖")
        
        writer = BatchWriter(
            batch_operation=batch_operation,
            config=config or self.batch_writer_configs.get(writer_name)
        )
        
        self.batch_writers[writer_name] = writer
        
        # 如果 Manager 已启动，立即启动 Writer
        if self.running:
            asyncio.create_task(writer.start())
        
        logger.info(f"✅ BatchWriter '{writer_name}' 已注册")
    
    async def batch_write(self, writer_name: str, data: Any) -> bool:
        """
        批量写入（添加到批量缓冲区）
        
        Args:
            writer_name: 写入器名称
            data: 要写入的数据
            
        Returns:
            是否触发了自动刷新
        """
        if not self.running:
            raise RuntimeError("StorageManager 未启动")
        
        writer = self.batch_writers.get(writer_name)
        if writer is None:
            raise ValueError(f"BatchWriter '{writer_name}' 不存在")
        
        return await writer.add(data)
    
    async def flush_batch(self, writer_name: str) -> int:
        """
        手动刷新批量缓冲区
        
        Args:
            writer_name: 写入器名称
            
        Returns:
            刷新的项数
        """
        writer = self.batch_writers.get(writer_name)
        if writer is None:
            raise ValueError(f"BatchWriter '{writer_name}' 不存在")
        
        return await writer.flush()
    
    async def shutdown(self, timeout: float = 30.0):
        """
        关闭存储管理器
        
        Args:
            timeout: 等待超时时间（秒）
        """
        if not self.running:
            return
        
        logger.info("🛑 StorageManager 正在关闭...")
        
        # 关闭所有 BatchWriters
        close_tasks = []
        for name, writer in self.batch_writers.items():
            logger.info(f"🔄 关闭 BatchWriter: {name}")
            close_tasks.append(writer.shutdown())
        
        if close_tasks:
            await asyncio.gather(*close_tasks, return_exceptions=True)
        
        # 关闭 AsyncWriter
        if self.async_writer:
            await self.async_writer.shutdown(timeout=timeout)
        
        self.running = False
        logger.info("✅ StorageManager 已关闭")
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        stats = {
            "running": self.running,
            "async_writer": None,
            "batch_writers": {},
        }
        
        # AsyncWriter 统计
        if self.async_writer:
            stats["async_writer"] = self.async_writer.get_stats()
        
        # BatchWriters 统计
        for name, writer in self.batch_writers.items():
            stats["batch_writers"][name] = {
                **writer.get_stats(),
                "buffer_info": writer.get_buffer_info(),
            }
        
        return stats


# 全局实例
_storage_manager: Optional[StorageManager] = None


def get_storage_manager() -> StorageManager:
    """获取全局存储管理器实例"""
    global _storage_manager
    
    if _storage_manager is None:
        _storage_manager = StorageManager()
    
    return _storage_manager


async def init_storage_manager(
    async_writer_config: Optional[Dict[str, Any]] = None,
    batch_writer_configs: Optional[Dict[str, BatchConfig]] = None
):
    """
    初始化并启动存储管理器
    
    Args:
        async_writer_config: AsyncWriter 配置
        batch_writer_configs: BatchWriter 配置字典
    """
    global _storage_manager
    
    if _storage_manager is not None and _storage_manager.running:
        logger.warning("StorageManager 已初始化")
        return _storage_manager
    
    _storage_manager = StorageManager(
        async_writer_config=async_writer_config,
        batch_writer_configs=batch_writer_configs
    )
    
    await _storage_manager.start()
    
    return _storage_manager


async def cleanup_storage_manager():
    """清理存储管理器"""
    global _storage_manager
    
    if _storage_manager is not None:
        await _storage_manager.shutdown()
        _storage_manager = None
