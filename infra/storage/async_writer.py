"""
异步写入器

实现 Write-Behind 模式，将写操作异步化，避免阻塞主流程
"""

import asyncio
from typing import Callable, Any, Optional, Dict
from dataclasses import dataclass
from datetime import datetime
from collections import deque
import time

from logger import get_logger

logger = get_logger(__name__)


@dataclass
class WriteTask:
    """写入任务"""
    task_id: str
    operation: Callable  # 写入操作（async函数）
    args: tuple = ()
    kwargs: Dict[str, Any] = None
    created_at: float = None
    retries: int = 0
    max_retries: int = 3
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = time.time()
        if self.kwargs is None:
            self.kwargs = {}


class AsyncWriter:
    """
    异步写入器
    
    特性：
    - 异步写入，不阻塞主流程
    - 自动重试（失败时）
    - 队列积压监控
    - 优雅关闭（确保所有任务完成）
    
    使用示例:
        writer = AsyncWriter()
        await writer.start()
        
        # 提交写入任务
        await writer.submit(save_to_db, conversation_id, message)
        
        # 关闭
        await writer.shutdown()
    """
    
    def __init__(
        self,
        max_queue_size: int = 10000,
        worker_count: int = 5,
        max_retries: int = 3
    ):
        self.max_queue_size = max_queue_size
        self.worker_count = worker_count
        self.max_retries = max_retries
        
        # 队列和工作者
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=max_queue_size)
        self.workers: list[asyncio.Task] = []
        self.running = False
        
        # 统计信息
        self.stats = {
            "submitted": 0,
            "completed": 0,
            "failed": 0,
            "retried": 0,
        }
    
    async def start(self):
        """启动异步写入器"""
        if self.running:
            logger.warning("AsyncWriter 已经在运行")
            return
        
        self.running = True
        
        # 启动工作者
        for i in range(self.worker_count):
            worker = asyncio.create_task(self._worker(f"worker-{i}"))
            self.workers.append(worker)
        
        logger.info(f"✅ AsyncWriter 已启动，工作者数量: {self.worker_count}")
    
    async def submit(
        self,
        operation: Callable,
        *args,
        task_id: Optional[str] = None,
        **kwargs
    ) -> str:
        """
        提交写入任务
        
        Args:
            operation: 写入操作（async函数）
            *args: 操作参数
            task_id: 任务ID（可选，用于追踪）
            **kwargs: 操作关键字参数
            
        Returns:
            任务ID
            
        Raises:
            asyncio.QueueFull: 队列已满
        """
        if not self.running:
            raise RuntimeError("AsyncWriter 未启动")
        
        # 生成任务ID
        if task_id is None:
            task_id = f"task_{int(time.time() * 1000)}_{self.stats['submitted']}"
        
        # 创建任务
        task = WriteTask(
            task_id=task_id,
            operation=operation,
            args=args,
            kwargs=kwargs,
            max_retries=self.max_retries
        )
        
        # 入队（非阻塞）
        try:
            self.queue.put_nowait(task)
            self.stats["submitted"] += 1
            
            # 检查队列积压
            queue_size = self.queue.qsize()
            if queue_size > self.max_queue_size * 0.8:
                logger.warning(
                    f"⚠️ AsyncWriter 队列积压: {queue_size}/{self.max_queue_size}"
                )
            
            return task_id
        except asyncio.QueueFull:
            logger.error("❌ AsyncWriter 队列已满，写入任务被拒绝")
            raise
    
    async def _worker(self, worker_name: str):
        """工作者协程"""
        logger.info(f"🚀 AsyncWriter 工作者启动: {worker_name}")
        
        while self.running:
            try:
                # 获取任务（超时1秒）
                try:
                    task = await asyncio.wait_for(
                        self.queue.get(),
                        timeout=1.0
                    )
                except asyncio.TimeoutError:
                    continue
                
                # 执行任务
                try:
                    if asyncio.iscoroutinefunction(task.operation):
                        await task.operation(*task.args, **task.kwargs)
                    else:
                        task.operation(*task.args, **task.kwargs)
                    
                    self.stats["completed"] += 1
                    
                except Exception as e:
                    logger.error(
                        f"❌ AsyncWriter 任务执行失败: {task.task_id}, "
                        f"错误: {str(e)}"
                    )
                    
                    # 重试
                    if task.retries < task.max_retries:
                        task.retries += 1
                        self.stats["retried"] += 1
                        
                        logger.info(
                            f"🔄 重试任务: {task.task_id} "
                            f"(第 {task.retries}/{task.max_retries} 次)"
                        )
                        
                        # 指数退避
                        await asyncio.sleep(0.5 * (2 ** task.retries))
                        
                        # 重新入队
                        await self.queue.put(task)
                    else:
                        self.stats["failed"] += 1
                        logger.error(
                            f"❌ 任务最终失败: {task.task_id} "
                            f"(已重试 {task.max_retries} 次)"
                        )
                
                finally:
                    self.queue.task_done()
            
            except Exception as e:
                logger.error(f"❌ AsyncWriter 工作者异常: {str(e)}", exc_info=True)
                await asyncio.sleep(1.0)
        
        logger.info(f"🛑 AsyncWriter 工作者停止: {worker_name}")
    
    async def shutdown(self, timeout: float = 30.0):
        """
        关闭异步写入器
        
        Args:
            timeout: 等待队列清空的超时时间（秒）
        """
        if not self.running:
            return
        
        logger.info("🛑 AsyncWriter 正在关闭...")
        
        # 等待队列清空
        try:
            await asyncio.wait_for(self.queue.join(), timeout=timeout)
            logger.info("✅ AsyncWriter 队列已清空")
        except asyncio.TimeoutError:
            remaining = self.queue.qsize()
            logger.warning(
                f"⚠️ AsyncWriter 队列未清空完成，剩余任务: {remaining}"
            )
        
        # 停止工作者
        self.running = False
        
        # 等待所有工作者停止
        for worker in self.workers:
            worker.cancel()
        
        await asyncio.gather(*self.workers, return_exceptions=True)
        
        logger.info(
            f"✅ AsyncWriter 已关闭，统计: "
            f"提交={self.stats['submitted']}, "
            f"完成={self.stats['completed']}, "
            f"失败={self.stats['failed']}, "
            f"重试={self.stats['retried']}"
        )
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            **self.stats,
            "queue_size": self.queue.qsize(),
            "running": self.running,
            "worker_count": len(self.workers),
        }
