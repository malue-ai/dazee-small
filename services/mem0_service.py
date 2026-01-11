"""
Mem0 服务层 - 用户记忆管理

职责：
- 封装 Mem0 Pool 操作
- 提供记忆的增删改查
- 复用 BackgroundTaskService 进行批量更新

设计原则：
- 单例模式
- 业务逻辑集中处理
- 异常统一包装
"""

from typing import List, Dict, Any, Optional
from logger import get_logger

from models.mem0 import (
    MemoryItem,
    UpdateResult,
    BatchUpdateResult,
    HealthCheckResult,
    MemoryAddResult,
)

logger = get_logger("mem0_service")


class Mem0ServiceError(Exception):
    """Mem0 服务异常基类"""
    pass


class Mem0NotInstalledError(Mem0ServiceError):
    """Mem0 模块未安装"""
    pass


class Mem0Service:
    """
    Mem0 服务
    
    使用方法：
        service = get_mem0_service()
        
        # 搜索记忆
        memories = await service.search(user_id, query, limit=10)
        
        # 添加记忆
        result = await service.add(user_id, messages)
        
        # 批量更新
        result = await service.batch_update(since_hours=24)
    """
    
    _instance: Optional["Mem0Service"] = None
    
    def __init__(self):
        self._pool = None
        self._background_service = None
    
    @classmethod
    def get_instance(cls) -> "Mem0Service":
        """获取单例实例"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def _get_pool(self):
        """获取 Mem0 Pool（懒加载）"""
        if self._pool is None:
            try:
                from core.memory.mem0 import get_mem0_pool
                self._pool = get_mem0_pool()
            except ImportError as e:
                raise Mem0NotInstalledError("mem0 模块未安装") from e
        return self._pool
    
    def _get_background_service(self):
        """获取后台任务服务（懒加载）"""
        if self._background_service is None:
            from utils.background_tasks import get_background_task_service
            self._background_service = get_background_task_service()
        return self._background_service
    
    # ==================== 搜索 ====================
    
    async def search(
        self,
        user_id: str,
        query: str,
        limit: int = 10
    ) -> List[MemoryItem]:
        """
        搜索用户相关记忆
        
        Args:
            user_id: 用户 ID
            query: 搜索查询
            limit: 返回数量限制
            
        Returns:
            记忆列表
            
        Raises:
            Mem0NotInstalledError: mem0 模块未安装
            Mem0ServiceError: 其他错误
        """
        try:
            pool = self._get_pool()
            memories = pool.search(
                user_id=user_id,
                query=query,
                limit=limit
            )
            
            items = [
                MemoryItem(
                    id=m.get("id", ""),
                    memory=m.get("memory", ""),
                    score=m.get("score"),
                    user_id=m.get("user_id"),
                    created_at=m.get("created_at"),
                    metadata=m.get("metadata")
                )
                for m in memories
            ]
            
            logger.info(f"🔍 记忆搜索: user_id={user_id}, 结果数={len(items)}")
            return items
            
        except Mem0NotInstalledError:
            raise
        except Exception as e:
            logger.error(f"记忆搜索失败: {e}")
            raise Mem0ServiceError(f"记忆搜索失败: {e}") from e
    
    async def search_with_rerank(
        self,
        user_id: str,
        query: str,
        limit: int = 5,
        candidate_limit: int = 30
    ) -> List[MemoryItem]:
        """
        搜索并重排序用户记忆（提升召回精度）
        
        流程:
        1. 向量检索召回更多候选（默认 30 条）
        2. LLM 重排序，选出最相关的 Top-K（默认 5 条）
        
        Args:
            user_id: 用户 ID
            query: 搜索查询
            limit: 最终返回数量（默认 5）
            candidate_limit: 候选召回数量（默认 30）
            
        Returns:
            重排序后的记忆列表
            
        Raises:
            Mem0NotInstalledError: mem0 模块未安装
            Mem0ServiceError: 其他错误
        """
        try:
            # 1. 召回更多候选
            pool = self._get_pool()
            candidates = pool.search(
                user_id=user_id,
                query=query,
                limit=candidate_limit
            )
            
            if not candidates:
                return []
            
            # 2. LLM 重排序
            from core.memory.mem0.reranker import get_reranker
            reranker = get_reranker()
            reranked = await reranker.rerank(
                query=query,
                memories=candidates,
                top_k=limit
            )
            
            # 3. 转换为 MemoryItem
            items = [
                MemoryItem(
                    id=m.get("id", ""),
                    memory=m.get("memory", ""),
                    score=m.get("rerank_score", m.get("score")),
                    user_id=m.get("user_id"),
                    created_at=m.get("created_at"),
                    metadata={
                        **(m.get("metadata") or {}),
                        "rerank_reason": m.get("rerank_reason", "")
                    }
                )
                for m in reranked
            ]
            
            logger.info(
                f"🔍 记忆搜索(重排序): user_id={user_id}, "
                f"候选={len(candidates)}, 结果={len(items)}"
            )
            return items
            
        except Mem0NotInstalledError:
            raise
        except Exception as e:
            logger.error(f"记忆搜索(重排序)失败: {e}")
            raise Mem0ServiceError(f"记忆搜索(重排序)失败: {e}") from e
    
    async def get_all(
        self,
        user_id: str,
        limit: int = 50
    ) -> List[MemoryItem]:
        """
        获取用户所有记忆
        
        Args:
            user_id: 用户 ID
            limit: 返回数量限制
            
        Returns:
            记忆列表
        """
        try:
            pool = self._get_pool()
            memories = pool.get_all(user_id=user_id, limit=limit)
            
            items = [
                MemoryItem(
                    id=m.get("id", ""),
                    memory=m.get("memory", ""),
                    score=m.get("score"),
                    user_id=m.get("user_id"),
                    created_at=m.get("created_at"),
                    metadata=m.get("metadata")
                )
                for m in memories
            ]
            
            logger.info(f"📋 获取用户记忆: user_id={user_id}, 数量={len(items)}")
            return items
            
        except Mem0NotInstalledError:
            raise
        except Exception as e:
            logger.error(f"获取用户记忆失败: {e}")
            raise Mem0ServiceError(f"获取用户记忆失败: {e}") from e
    
    # ==================== 添加 ====================
    
    async def add(
        self,
        user_id: str,
        messages: List[Dict[str, str]],
        metadata: Optional[Dict[str, Any]] = None
    ) -> MemoryAddResult:
        """
        添加用户记忆
        
        Args:
            user_id: 用户 ID
            messages: 消息列表 [{"role": "user", "content": "..."}, ...]
            metadata: 元数据
            
        Returns:
            添加结果
        """
        try:
            pool = self._get_pool()
            result = pool.add(
                user_id=user_id,
                messages=messages,
                metadata=metadata
            )
            
            memories_added = len(result.get("results", []))
            logger.info(f"➕ 添加记忆: user_id={user_id}, 新增={memories_added}")
            
            return MemoryAddResult(
                memories_added=memories_added,
                results=result.get("results", [])
            )
            
        except Mem0NotInstalledError:
            raise
        except Exception as e:
            logger.error(f"添加记忆失败: {e}")
            raise Mem0ServiceError(f"添加记忆失败: {e}") from e
    
    # ==================== 删除 ====================
    
    async def delete(self, memory_id: str) -> bool:
        """
        删除单条记忆
        
        Args:
            memory_id: 记忆 ID
            
        Returns:
            是否删除成功
        """
        try:
            pool = self._get_pool()
            success = pool.delete(memory_id=memory_id)
            
            logger.info(f"🗑️ 删除记忆: memory_id={memory_id}, success={success}")
            return success
            
        except Mem0NotInstalledError:
            raise
        except Exception as e:
            logger.error(f"删除记忆失败: {e}")
            raise Mem0ServiceError(f"删除记忆失败: {e}") from e
    
    async def reset_user(self, user_id: str) -> bool:
        """
        重置用户所有记忆
        
        ⚠️ 警告：此操作不可逆
        
        Args:
            user_id: 用户 ID
            
        Returns:
            是否重置成功
        """
        try:
            pool = self._get_pool()
            success = pool.reset_user(user_id=user_id)
            
            logger.warning(f"🗑️ 重置用户记忆: user_id={user_id}, success={success}")
            return success
            
        except Mem0NotInstalledError:
            raise
        except Exception as e:
            logger.error(f"重置用户记忆失败: {e}")
            raise Mem0ServiceError(f"重置用户记忆失败: {e}") from e
    
    # ==================== 批量更新 ====================
    
    async def batch_update(
        self,
        since_hours: int = 24,
        max_concurrent: int = 5
    ) -> BatchUpdateResult:
        """
        批量更新所有用户记忆
        
        复用 BackgroundTaskService 实现
        
        Args:
            since_hours: 处理过去多少小时的会话
            max_concurrent: 最大并发数
            
        Returns:
            批量更新结果
        """
        try:
            service = self._get_background_service()
            
            logger.info(
                f"🚀 触发批量更新: since={since_hours}h, max_concurrent={max_concurrent}"
            )
            
            result = await service.batch_update_all_memories(
                since_hours=since_hours,
                max_concurrent=max_concurrent
            )
            
            return BatchUpdateResult(
                total_users=result.total_users,
                successful=result.successful,
                failed=result.failed,
                duration_seconds=result.duration_seconds,
                results=[
                    UpdateResult(
                        user_id=r.user_id,
                        success=r.success,
                        memories_added=r.memories_added,
                        error=r.error,
                        duration_ms=r.duration_ms
                    )
                    for r in result.results
                ]
            )
            
        except Exception as e:
            logger.error(f"批量更新失败: {e}")
            raise Mem0ServiceError(f"批量更新失败: {e}") from e
    
    async def update_user(
        self,
        user_id: str,
        since_hours: int = 24
    ) -> UpdateResult:
        """
        更新单个用户的记忆
        
        Args:
            user_id: 用户 ID
            since_hours: 处理过去多少小时的会话
            
        Returns:
            更新结果
        """
        try:
            service = self._get_background_service()
            
            result = await service.update_user_memories(
                user_id=user_id,
                since_hours=since_hours
            )
            
            return UpdateResult(
                user_id=result.user_id,
                success=result.success,
                memories_added=result.memories_added,
                error=result.error,
                duration_ms=result.duration_ms
            )
            
        except Exception as e:
            logger.error(f"更新用户记忆失败: {e}")
            raise Mem0ServiceError(f"更新用户记忆失败: {e}") from e
    
    # ==================== 健康检查 ====================
    
    async def health_check(self) -> HealthCheckResult:
        """
        健康检查
        
        Returns:
            健康检查结果
        """
        try:
            pool = self._get_pool()
            
            # 尝试一个简单的操作来验证连接
            # 这里可以根据实际 Pool 的 API 调整
            pool_info = {
                "type": type(pool).__name__,
                "available": True
            }
            
            return HealthCheckResult(
                service="mem0",
                status="healthy",
                pool=pool_info
            )
            
        except Mem0NotInstalledError as e:
            return HealthCheckResult(
                service="mem0",
                status="unavailable",
                error=str(e)
            )
        except Exception as e:
            return HealthCheckResult(
                service="mem0",
                status="unhealthy",
                error=str(e)
            )


# ==================== 便捷函数 ====================

def get_mem0_service() -> Mem0Service:
    """获取 Mem0 服务单例"""
    return Mem0Service.get_instance()

