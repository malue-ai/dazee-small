"""
Tools 基类定义

继承自 core.tool.types.BaseTool，统一接口：execute(params, context)
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from core.tool.types import BaseTool as CoreBaseTool
from core.tool.types import ToolContext


@dataclass
class ToolDefinition:
    """工具定义"""

    name: str
    description: str
    parameters: Dict[str, Any]
    required_params: List[str]


class BaseTool(CoreBaseTool, ABC):
    """工具基类（对齐 core.tool.types.BaseTool）"""

    @property
    @abstractmethod
    def name(self) -> str:
        """工具名称"""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """工具描述"""
        pass

    @property
    @abstractmethod
    def parameters(self) -> Dict[str, Any]:
        """工具参数定义"""
        pass

    @abstractmethod
    async def execute(
        self, params: Dict[str, Any], context: Optional[ToolContext] = None
    ) -> Dict[str, Any]:
        """
        执行工具

        Args:
            params: 工具参数
            context: 工具上下文（可选）

        Returns:
            执行结果
        """
        pass

    def to_definition(self) -> ToolDefinition:
        """转换为工具定义"""
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters=self.parameters,
            required_params=self.parameters.get("required", []),
        )


class ToolManager:
    """
    工具管理器
    管理工具的注册、检索和执行

    MVP版本：简化实现
    后续版本：将支持动态工具加载
    """

    def __init__(self) -> None:
        """初始化工具管理器"""
        self._tools: Dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """
        注册工具

        Args:
            tool: 工具实例
        """
        self._tools[tool.name] = tool

    def unregister(self, name: str) -> bool:
        """
        注销工具

        Args:
            name: 工具名称

        Returns:
            是否注销成功
        """
        if name in self._tools:
            del self._tools[name]
            return True
        return False

    def get(self, name: str) -> Optional[BaseTool]:
        """
        获取工具

        Args:
            name: 工具名称

        Returns:
            工具实例
        """
        return self._tools.get(name)

    def list_tools(self) -> List[ToolDefinition]:
        """
        列出所有工具

        Returns:
            工具定义列表
        """
        return [tool.to_definition() for tool in self._tools.values()]

    async def execute(self, name: str, **kwargs) -> Dict[str, Any]:
        """
        执行工具

        Args:
            name: 工具名称
            **kwargs: 工具参数

        Returns:
            执行结果
        """
        tool = self.get(name)
        if not tool:
            return {"error": f"Tool '{name}' not found"}

        try:
            # 统一新版接口：params + context
            return await tool.execute(params=kwargs, context=ToolContext())
        except Exception as e:
            return {"error": str(e)}

    def search_tools(self, query: str) -> List[ToolDefinition]:
        """
        搜索工具

        Args:
            query: 搜索查询

        Returns:
            匹配的工具定义列表
        """
        results = []
        query_lower = query.lower()

        for tool in self._tools.values():
            if query_lower in tool.name.lower() or query_lower in tool.description.lower():
                results.append(tool.to_definition())

        return results
