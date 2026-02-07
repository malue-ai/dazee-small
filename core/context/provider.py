"""
上下文提供者接口

定义数据源的统一接口
"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, List


class ContextType(str, Enum):
    """
    上下文类型

    注意：只包含需要检索的数据源
    - 历史对话不在这里，由 ChatService 直接管理（messages 数组）
    - 原因：当前会话历史已在 messages 中，跨会话检索太慢
    """

    KNOWLEDGE = "knowledge"  # 知识检索（本地知识检索，后续实现）
    MEMORY = "memory"  # 记忆检索


class ContextProvider(ABC):
    """
    上下文提供者接口

    所有数据源（Knowledge/Mem0/History）都实现此接口，提供统一的检索和更新方法。

    核心理念：
    - Knowledge、Mem0、History 本质相同：都是为 LLM 提供上下文的数据源
    - 统一接口使得系统易于扩展和测试
    - 检索结果格式统一，便于融合和排序
    """

    @property
    @abstractmethod
    def context_type(self) -> ContextType:
        """返回上下文类型"""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """返回提供者名称（用于日志）"""
        pass

    @abstractmethod
    async def retrieve(
        self, query: str, user_id: str, filters: Dict[str, Any] = None, top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """
        检索相关上下文

        Args:
            query: 用户查询
            user_id: 用户ID
            filters: 过滤条件（可选）
            top_k: 返回结果数量

        Returns:
            上下文列表，统一格式：
            [
                {
                    "content": "上下文内容",
                    "score": 0.95,         # 相关性评分 (0-1)
                    "metadata": {...},      # 元数据
                    "source": "knowledge",  # 来源类型
                    "provider": "local"     # 提供者名称
                }
            ]
        """
        pass

    @abstractmethod
    async def update(self, user_id: str, data: Dict[str, Any]) -> bool:
        """
        更新上下文（可选，某些 Provider 不支持）

        Args:
            user_id: 用户ID
            data: 更新数据

        Returns:
            是否成功
        """
        pass

    async def health_check(self) -> bool:
        """
        健康检查（可选实现）

        Returns:
            是否健康
        """
        return True
