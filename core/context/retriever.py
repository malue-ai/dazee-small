"""
上下文检索器（旧版）

⚠️ 废弃警告：
    本模块将在未来版本中被新的 Injector 系统取代。
    推荐使用 core.context.injectors 模块的 Phase-based Injector 模式。

    新架构中，检索逻辑由各个 Phase 2 Injector 处理：
    - UserMemoryInjector: 用户记忆检索

原职责（已由新 Injector 系统承担）：
- 管理多个 ContextProvider → InjectionOrchestrator
- 根据意图决定调用哪些 Provider → 各 Injector 的 should_inject()
- 并发检索，提升性能 → InjectionOrchestrator._execute_phase()
"""

import asyncio
from typing import Any, Dict, List, Optional

from core.context.provider import ContextProvider, ContextType
from core.context.providers import MemoryProvider
from logger import get_logger

logger = get_logger(__name__)


class ContextRetriever:
    """
    上下文检索器

    职责：
    1. 管理多个 ContextProvider（仅需要检索的数据源）
    2. 根据意图决定调用哪些 Provider
    3. 并发检索，提升性能
    4. 错误处理与日志记录

    注意：历史对话不在这里管理，由 ChatService 直接处理
    """

    def __init__(self) -> None:
        # 注册所有 Provider（仅需要检索的数据源）
        self.providers: Dict[ContextType, ContextProvider] = {
            ContextType.MEMORY: MemoryProvider(),
        }
        logger.info(f"ContextRetriever initialized with {len(self.providers)} providers")

    async def retrieve(
        self,
        query: str,
        user_id: str,
        sources: List[ContextType] = None,
        top_k_per_source: int = 5,
        filters: Dict[str, Any] = None,
    ) -> Dict[ContextType, List[Dict[str, Any]]]:
        """
        从多个数据源检索上下文

        Args:
            query: 用户查询
            user_id: 用户ID
            sources: 要查询的数据源列表（None=全部）
            top_k_per_source: 每个数据源返回的结果数量
            filters: 过滤条件

        Returns:
            {
                ContextType.KNOWLEDGE: [...],
                ContextType.MEMORY: [...],
                ContextType.HISTORY: [...]
            }
        """
        # 1. 确定要查询的数据源
        if sources is None:
            sources = list(self.providers.keys())

        logger.info(
            f"ContextRetriever.retrieve: query={query[:50]}, "
            f"user_id={user_id}, sources={[s.value for s in sources]}, "
            f"top_k_per_source={top_k_per_source}"
        )

        # 2. 并发查询所有数据源
        tasks = {}
        for source_type in sources:
            provider = self.providers.get(source_type)
            if provider:
                tasks[source_type] = provider.retrieve(
                    query=query, user_id=user_id, filters=filters, top_k=top_k_per_source
                )

        # 3. 等待所有查询完成
        results = await asyncio.gather(*tasks.values(), return_exceptions=True)

        # 4. 组织结果
        context_map = {}
        for source_type, result in zip(tasks.keys(), results):
            if isinstance(result, Exception):
                logger.error(f"检索失败: {source_type.value}, {str(result)}", exc_info=result)
                context_map[source_type] = []
            else:
                context_map[source_type] = result
                logger.debug(f"检索成功: {source_type.value}, " f"returned {len(result)} contexts")

        return context_map

    async def update(self, user_id: str, source_type: ContextType, data: Dict[str, Any]) -> bool:
        """
        更新上下文数据

        Args:
            user_id: 用户ID
            source_type: 数据源类型
            data: 更新数据

        Returns:
            是否成功
        """
        provider = self.providers.get(source_type)
        if provider:
            try:
                success = await provider.update(user_id, data)
                logger.info(
                    f"ContextRetriever.update: {source_type.value}, "
                    f"user_id={user_id}, success={success}"
                )
                return success
            except Exception as e:
                logger.error(f"更新失败: {source_type.value}, {str(e)}", exc_info=e)
                return False
        else:
            logger.warning(f"Provider not found: {source_type.value}")
            return False

    async def health_check(self) -> Dict[str, bool]:
        """
        健康检查所有 Provider

        Returns:
            {
                "knowledge": True,
                "memory": True,
                "history": True
            }
        """
        health_status = {}
        for source_type, provider in self.providers.items():
            try:
                is_healthy = await provider.health_check()
                health_status[source_type.value] = is_healthy
            except Exception as e:
                logger.error(f"健康检查失败: {source_type.value}, {str(e)}", exc_info=e)
                health_status[source_type.value] = False

        return health_status
