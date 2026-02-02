"""
Tool 核心模块

提供工具管理的完整功能：
- base.py: 工具基类和上下文定义
- capability/: 能力管理子包（Registry、Router、InvocationSelector、SkillLoader）
- ToolSelector: 工具选择器（根据能力需求选择工具）
- ToolExecutor: 工具执行器（动态加载和执行工具）
- ResultCompactor: 结果精简器（Context Engineering 优化）

目录结构：
- base.py: BaseTool, ToolContext, ToolResult
- capability/: 能力管理子包
- selector.py: 工具选择逻辑
- executor.py: 工具执行逻辑
- result_compactor.py: 结果精简

注意：具体工具实现在 tools/ 目录下
"""

# 工具基类和上下文
from core.tool.base import (
    BaseTool,
    ToolContext,
    ToolResult,
    LegacyToolAdapter,
    create_tool_context,
)

# 工具选择器和执行器
from core.tool.selector import (
    ToolSelector,
    ToolSelectionResult,
    create_tool_selector
)
from core.tool.executor import (
    ToolExecutor,
    create_tool_executor
)

# 结果精简器
from core.tool.result_compactor import (
    ResultCompactor,
    CompactionStrategy,
    CompactionRule,
    create_result_compactor,
)

# Capability 子包
from core.tool.capability import (
    Capability,
    CapabilityType,
    CapabilitySubtype,
    CapabilityRegistry,
    create_capability_registry,
    get_capability_registry,
    CapabilityRouter,
    RoutingResult,
    create_capability_router,
    extract_keywords,
    InvocationSelector,
    InvocationType,
    InvocationStrategy,
    create_invocation_selector,
    SkillLoader,
    SkillInfo,
    create_skill_loader,
)

# 实例级工具注册表
from core.tool.instance_registry import (
    InstanceToolRegistry,
    InstanceTool,
    InstanceToolType,
    create_instance_registry,
)

# 工具加载器
from core.tool.loader import (
    ToolLoader,
    ToolLoadResult,
    create_tool_loader,
    TOOL_CATEGORIES,
    CORE_TOOLS,
)

# 统一工具调用器
from core.tool.unified_tool_caller import (
    UnifiedToolCaller,
    create_unified_tool_caller,
)

__all__ = [
    # 工具基类和上下文
    "BaseTool",
    "ToolContext",
    "ToolResult",
    "LegacyToolAdapter",
    "create_tool_context",
    # 选择器
    "ToolSelector",
    "ToolSelectionResult",
    "create_tool_selector",
    # 执行器
    "ToolExecutor",
    "create_tool_executor",
    # 结果精简器
    "ResultCompactor",
    "CompactionStrategy",
    "CompactionRule",
    "create_result_compactor",
    # Capability 子包
    "Capability",
    "CapabilityType",
    "CapabilitySubtype",
    "CapabilityRegistry",
    "create_capability_registry",
    "get_capability_registry",
    "CapabilityRouter",
    "RoutingResult",
    "create_capability_router",
    "extract_keywords",
    "InvocationSelector",
    "InvocationType",
    "InvocationStrategy",
    "create_invocation_selector",
    "SkillLoader",
    "SkillInfo",
    "create_skill_loader",
    # 实例级工具注册表
    "InstanceToolRegistry",
    "InstanceTool",
    "InstanceToolType",
    "create_instance_registry",
    # 工具加载器
    "ToolLoader",
    "ToolLoadResult",
    "create_tool_loader",
    "TOOL_CATEGORIES",
    "CORE_TOOLS",
    # 统一工具调用器
    "UnifiedToolCaller",
    "create_unified_tool_caller",
]

