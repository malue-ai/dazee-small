"""
批量写入器

将多个写操作合并成批量操作，减少数据库往返次数
"""

import asyncio
from typing import Callable, Any, List, Dict, Optional
from dataclasses import dataclass, field
from datetime import datetime
import time

from logger import get_logger

logger = get_logger(__name__)


@dataclass
class BatchConfig:
    """批量配置"""
    max_batch_size: int = 100        # 最大批量大小
    max_wait_time: float = 5.0       # 最大等待时间（秒）
    min_batch_size: int = 10         # 最小批量大小（低于此值不强制刷新）


@dataclass
class BatchItem:
    """批量项"""
    data: Any
    added_at: float = field(default_factory=time.time)
    retries: int = 0


class BatchWriter:
    """
    批量写入器
    
    特性：
    - 自动批量合并（达到大小或时间阈值）
    - 智能刷新策略
    - 失败重试
    - 性能统计
    
    使用示例:
        async def batch_save(items: List[Any]):
            # 批量保存到数据库
            await db.bulk_insert(items)
        
        writer = BatchWriter(batch_save, config=BatchConfig(max_batch_size=100))
        await writer.start()
        
        # 添加项（自动批量）
        await writer.add(message1)
        await writer.add(message2)
        
        # 手动刷新
        await writer.flush()
        
        # 关闭
        await writer.shutdown()
    """
    
    def __init__(
        self,
        batch_operation: Callable[[List[Any]], Any],
        config: Optional[BatchConfig] = None
    ):
        self.batch_operation = batch_operation
        self.config = config or BatchConfig()
        
        # 批量缓冲区
        self.buffer: List[BatchItem] = []
        self.buffer_lock = asyncio.Lock()
        
        # 定时刷新任务
        self.flush_task: Optional[asyncio.Task] = None
        self.running = False
        
        # 统计信息
        self.stats = {
            "items_added": 0,
            "batches_flushed": 0,
            "items_flushed": 0,
            "flush_errors": 0,
            "last_flush_time": None,
            "last_flush_size": 0,
        }
    
    async def start(self):
        """启动批量写入器"""
        if self.running:
            logger.warning("BatchWriter 已经在运行")
            return
        
        self.running = True
        
        # 启动定时刷新任务
        self.flush_task = asyncio.create_task(self._auto_flush_loop())
        
        logger.info(
            f"✅ BatchWriter 已启动，配置: "
            f"batch_size={self.config.max_batch_size}, "
            f"wait_time={self.config.max_wait_time}s"
        )
    
    async def add(self, data: Any) -> bool:
        """
        添加项到批量缓冲区
        
        Args:
            data: 要添加的数据
            
        Returns:
            是否触发了自动刷新
        """
        if not self.running:
            raise RuntimeError("BatchWriter 未启动")
        
        async with self.buffer_lock:
            item = BatchItem(data=data)
            self.buffer.append(item)
            self.stats["items_added"] += 1
            
            # 检查是否达到批量大小
            if len(self.buffer) >= self.config.max_batch_size:
                logger.debug(
                    f"🚀 BatchWriter 达到批量大小 ({len(self.buffer)})，触发刷新"
                )
                # 异步刷新（不阻塞）
                asyncio.create_task(self.flush())
                return True
        
        return False
    
    async def flush(self) -> int:
        """
        刷新批量缓冲区（执行批量操作）
        
        Returns:
            刷新的项数
        """
        if not self.running:
            return 0
        
        async with self.buffer_lock:
            if not self.buffer:
                return 0
            
            # 取出所有项
            items_to_flush = self.buffer.copy()
            self.buffer.clear()
        
        # 提取数据
        data_list = [item.data for item in items_to_flush]
        
        try:
            # 执行批量操作
            start_time = time.time()
            
            if asyncio.iscoroutinefunction(self.batch_operation):
                await self.batch_operation(data_list)
            else:
                self.batch_operation(data_list)
            
            duration = time.time() - start_time
            
            # 更新统计
            self.stats["batches_flushed"] += 1
            self.stats["items_flushed"] += len(data_list)
            self.stats["last_flush_time"] = datetime.now().isoformat()
            self.stats["last_flush_size"] = len(data_list)
            
            logger.debug(
                f"✅ BatchWriter 刷新成功: {len(data_list)} 项, "
                f"耗时 {duration:.2f}s"
            )
            
            return len(data_list)
        
        except Exception as e:
            self.stats["flush_errors"] += 1
            logger.error(
                f"❌ BatchWriter 刷新失败: {str(e)}, "
                f"影响项数: {len(data_list)}"
            )
            
            # 重试逻辑：将失败的项重新加入缓冲区
            async with self.buffer_lock:
                for item in items_to_flush:
                    if item.retries < 3:
                        item.retries += 1
                        self.buffer.append(item)
                    else:
                        logger.error(f"❌ 项最终失败，放弃重试: {item.data}")
            
            raise
    
    async def _auto_flush_loop(self):
        """自动刷新循环（定时任务）"""
        logger.info("🚀 BatchWriter 自动刷新循环启动")
        
        while self.running:
            try:
                await asyncio.sleep(self.config.max_wait_time)
                
                # 检查缓冲区是否有数据
                async with self.buffer_lock:
                    buffer_size = len(self.buffer)
                    
                    if buffer_size == 0:
                        continue
                    
                    # 检查是否应该刷新
                    should_flush = False
                    
                    # 条件1：达到最小批量大小
                    if buffer_size >= self.config.min_batch_size:
                        should_flush = True
                    
                    # 条件2：最早的项已等待超过 max_wait_time
                    elif self.buffer:
                        oldest_item = min(self.buffer, key=lambda x: x.added_at)
                        wait_time = time.time() - oldest_item.added_at
                        if wait_time >= self.config.max_wait_time:
                            should_flush = True
                    
                    if should_flush:
                        logger.debug(
                            f"⏰ BatchWriter 定时刷新: {buffer_size} 项"
                        )
                        await self.flush()
            
            except Exception as e:
                logger.error(
                    f"❌ BatchWriter 自动刷新循环异常: {str(e)}",
                    exc_info=True
                )
                await asyncio.sleep(1.0)
        
        logger.info("🛑 BatchWriter 自动刷新循环停止")
    
    async def shutdown(self, force: bool = False):
        """
        关闭批量写入器
        
        Args:
            force: 是否强制关闭（不刷新缓冲区）
        """
        if not self.running:
            return
        
        logger.info("🛑 BatchWriter 正在关闭...")
        
        # 刷新剩余数据
        if not force:
            remaining = len(self.buffer)
            if remaining > 0:
                logger.info(f"🔄 刷新剩余数据: {remaining} 项")
                try:
                    await self.flush()
                except Exception as e:
                    logger.error(f"❌ 最终刷新失败: {str(e)}")
        
        # 停止定时任务
        self.running = False
        
        if self.flush_task:
            self.flush_task.cancel()
            try:
                await self.flush_task
            except asyncio.CancelledError:
                pass
        
        logger.info(
            f"✅ BatchWriter 已关闭，统计: "
            f"添加={self.stats['items_added']}, "
            f"批次={self.stats['batches_flushed']}, "
            f"刷新={self.stats['items_flushed']}, "
            f"错误={self.stats['flush_errors']}"
        )
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            **self.stats,
            "buffer_size": len(self.buffer),
            "running": self.running,
        }
    
    def get_buffer_info(self) -> Dict[str, Any]:
        """获取缓冲区信息"""
        if not self.buffer:
            return {
                "size": 0,
                "oldest_age": 0,
                "average_age": 0,
            }
        
        current_time = time.time()
        ages = [current_time - item.added_at for item in self.buffer]
        
        return {
            "size": len(self.buffer),
            "oldest_age": max(ages),
            "average_age": sum(ages) / len(ages),
            "items_with_retries": sum(1 for item in self.buffer if item.retries > 0),
        }
