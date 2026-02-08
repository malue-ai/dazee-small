"""
工具加载器 - 统一管理工具的加载逻辑

职责：
1. 加载通用工具（从 capabilities.yaml，根据 enabled_capabilities 过滤）
2. 加载 Claude Skills
3. 提供统一的工具列表给 Agent

设计原则：
- 封装复杂性：对外提供简单的加载接口
- 统一管理：工具统一加载和注册
- 类别化配置：支持工具组配置（如 document_skills）
- 核心工具自动启用：Level 1 工具始终可用
- 完全异步化：所有配置加载都是异步的
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from core.tool.registry_config import get_core_tools, get_tool_categories
from logger import get_logger

from .registry import CapabilityRegistry
from .types import Capability

logger = get_logger(__name__)


# 工具类别定义和核心工具（懒加载，异步获取）
_tool_categories_cache: Optional[Dict[str, List[str]]] = None
_core_tools_cache: Optional[List[str]] = None


async def get_tool_categories_cached() -> Dict[str, List[str]]:
    """获取工具类别（带缓存）"""
    global _tool_categories_cache
    if _tool_categories_cache is None:
        _tool_categories_cache = await get_tool_categories()
    return _tool_categories_cache


async def get_core_tools_cached() -> List[str]:
    """获取核心工具（带缓存）"""
    global _core_tools_cache
    if _core_tools_cache is None:
        _core_tools_cache = await get_core_tools()
    return _core_tools_cache


@dataclass
class ToolLoadResult:
    """工具加载结果"""

    generic_tools: List[Capability]  # 通用工具（从 capabilities.yaml）
    generic_count: int
    skills: List[Dict[str, Any]]  # Claude Skills
    skills_count: int
    total_count: int
    enabled_tools: List[str]  # 启用的工具名称列表
    disabled_tools: List[str]  # 未启用的工具名称列表


class ToolLoader:
    """
    统一工具加载器

    管理工具的加载：
    1. 通用工具（TOOL/SKILL/CODE）- 从 capabilities.yaml
    2. Claude Skills - 从 skill_registry.yaml

    特性：
    - 类别化配置：document_skills 等自动展开
    - 核心工具自动启用：Level 1 工具无需用户配置

    示例:
        loader = ToolLoader(global_registry)
        result = loader.load_tools(
            enabled_capabilities={"web_search": True, "document_skills": True},
            skills=[SkillConfig(...)]
        )
        print(f"加载了 {result.total_count} 个工具")
    """

    def __init__(self, global_registry: CapabilityRegistry):
        """
        初始化工具加载器

        Args:
            global_registry: 全局能力注册表
        """
        self.global_registry = global_registry
        self._all_tool_names = set(global_registry.capabilities.keys())
        logger.info(f"ToolLoader 初始化: 注册表中有 {len(self._all_tool_names)} 个工具")

    async def _expand_category_config(
        self, enabled_capabilities: Dict[str, bool]
    ) -> Dict[str, bool]:
        """
        展开类别配置为具体工具配置（异步）

        将类别配置展开为具体工具配置
        """
        expanded = {}
        tool_categories = await get_tool_categories_cached()

        for key, value in enabled_capabilities.items():
            if key in tool_categories:
                # 这是一个类别，展开为具体工具
                category_tools = tool_categories[key]
                is_enabled = bool(value)

                logger.debug(f"展开类别 {key} → {len(category_tools)} 个工具")

                for tool_name in category_tools:
                    if tool_name in self._all_tool_names:
                        expanded[tool_name] = is_enabled
                    else:
                        logger.warning(f"工具 {tool_name} 不在注册表中，跳过（类别: {key}）")
            else:
                expanded[key] = bool(value)

        return expanded

    async def _add_core_tools(self, enabled_map: Dict[str, bool]) -> Dict[str, bool]:
        """
        自动添加核心工具（Level 1 工具始终启用）（异步）
        """
        result = enabled_map.copy()
        core_tools = await get_core_tools_cached()

        added_core_tools = []
        for tool_name in core_tools:
            if tool_name in self._all_tool_names:
                if tool_name not in result or not result[tool_name]:
                    result[tool_name] = True
                    added_core_tools.append(tool_name)

        if added_core_tools:
            logger.info(f"自动启用核心工具: {', '.join(added_core_tools)}")

        return result

    async def load_tools(
        self,
        enabled_capabilities: Dict[str, bool],
        skills: Optional[List[Any]] = None,
    ) -> ToolLoadResult:
        """
        加载所有工具（异步）

        Args:
            enabled_capabilities: 启用的通用工具配置 {"tool_name": True/False}
            skills: Claude Skills 配置列表（可选）

        Returns:
            ToolLoadResult 包含加载结果和统计信息
        """
        logger.info("开始加载工具...")

        # 1. 加载通用工具（过滤）
        generic_tools, enabled_names, disabled_names = await self._load_generic_tools(
            enabled_capabilities
        )

        # 2. 准备 Skills 配置
        skills_list = skills or []
        enabled_skills = [s for s in skills_list if getattr(s, "enabled", False)]

        # 3. 统计
        total_count = len(generic_tools) + len(enabled_skills)

        result = ToolLoadResult(
            generic_tools=generic_tools,
            generic_count=len(generic_tools),
            skills=enabled_skills,
            skills_count=len(enabled_skills),
            total_count=total_count,
            enabled_tools=enabled_names,
            disabled_tools=disabled_names,
        )

        self._print_load_summary(result)
        return result

    async def _load_generic_tools(
        self, enabled_capabilities: Dict[str, bool]
    ) -> tuple[List[Capability], List[str], List[str]]:
        """
        加载通用工具（从 capabilities.yaml，根据配置过滤）（异步）

        特性：
        - 自动展开类别配置
        - 自动启用核心工具（Level 1）

        Args:
            enabled_capabilities: 启用配置（支持类别）

        Returns:
            (工具列表, 启用的工具名列表, 未启用的工具名列表)
        """
        if not enabled_capabilities:
            logger.info("未配置工具过滤，使用全部通用工具")
            all_tools = list(self.global_registry.capabilities.values())
            all_names = list(self.global_registry.capabilities.keys())
            return all_tools, all_names, []

        # 1. 展开类别配置（异步）
        expanded_config = await self._expand_category_config(enabled_capabilities)

        # 2. 自动添加核心工具（异步）
        final_config = await self._add_core_tools(expanded_config)

        # 3. 过滤工具
        enabled_tools = []
        enabled_names = []
        disabled_names = []

        for name, cap in self.global_registry.capabilities.items():
            if final_config.get(name, False):
                enabled_tools.append(cap)
                enabled_names.append(name)
            else:
                disabled_names.append(name)

        logger.info(f"已启用 {len(enabled_tools)} 个通用工具")
        logger.debug(f"启用: {', '.join(enabled_names)}")
        logger.debug(f"禁用: {', '.join(disabled_names)}")

        return enabled_tools, enabled_names, disabled_names

    def _print_load_summary(self, result: ToolLoadResult):
        """打印加载摘要"""
        logger.info("=" * 60)
        logger.info("工具加载摘要")
        logger.info("=" * 60)
        logger.info(f"  通用工具: {result.generic_count} 个")
        if result.enabled_tools:
            logger.info(f"    启用: {', '.join(result.enabled_tools)}")

        logger.info(f"  Claude Skills: {result.skills_count} 个")
        if result.skills:
            skill_names = [getattr(s, "name", "unknown") for s in result.skills]
            logger.info(f"    列表: {', '.join(skill_names)}")

        logger.info(f"  总计: {result.total_count} 个工具")
        logger.info("=" * 60)

    def create_filtered_registry(self, enabled_capabilities: Dict[str, bool]) -> CapabilityRegistry:
        """
        创建过滤后的工具注册表

        用于在 Agent 初始化时创建过滤后的注册表。

        特性：
        - 自动展开类别配置
        - 自动启用核心工具

        Args:
            enabled_capabilities: 启用配置（支持类别）

        Returns:
            过滤后的 CapabilityRegistry 实例
        """
        if not enabled_capabilities:
            logger.info("未配置工具过滤，返回全局注册表")
            return self.global_registry

        # 1. 展开类别配置
        expanded_config = self._expand_category_config(enabled_capabilities)

        # 2. 自动添加核心工具
        final_config = self._add_core_tools(expanded_config)

        # 3. 创建过滤后的注册表
        filtered_registry = self.global_registry.filter_by_enabled(final_config)
        logger.info(f"已创建过滤后的注册表，包含 {len(filtered_registry.capabilities)} 个工具")

        return filtered_registry

    def get_tool_statistics(self, enabled_capabilities: Dict[str, bool]) -> Dict[str, Any]:
        """
        获取工具统计信息

        Args:
            enabled_capabilities: 启用配置

        Returns:
            统计信息字典
        """
        _, enabled_names, disabled_names = self._load_generic_tools(enabled_capabilities)

        return {
            "total_available": len(self._all_tool_names),
            "enabled_count": len(enabled_names),
            "disabled_count": len(disabled_names),
            "enabled_tools": enabled_names,
            "disabled_tools": disabled_names,
        }


def create_tool_loader(global_registry: Optional[CapabilityRegistry] = None) -> ToolLoader:
    """
    创建工具加载器

    Args:
        global_registry: 全局注册表（可选，默认使用单例）

    Returns:
        ToolLoader 实例
    """
    if global_registry is None:
        from .registry import get_capability_registry

        global_registry = get_capability_registry()

    return ToolLoader(global_registry)
