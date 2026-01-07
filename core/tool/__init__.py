"""
Tool 核心模块

提供工具管理的完整功能：
- capability/: 能力管理子包（Registry、Router、InvocationSelector、SkillLoader）
- ToolSelector: 工具选择器（根据能力需求选择工具）
- ToolExecutor: 工具执行器（动态加载和执行工具）
- ResultCompactor: 结果精简器（Context Engineering 优化）

目录结构：
- capability/: 能力管理子包
- selector.py: 工具选择逻辑
- executor.py: 工具执行逻辑
- result_compactor.py: 结果精简（上下文工程原则）

注意：具体工具实现在 tools/ 目录下
"""

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

# 🆕 结果精简器（Context Engineering 优化）
from core.tool.result_compactor import (
    ResultCompactor,
    CompactionStrategy,
    CompactionRule,
    create_result_compactor,
)

# 🆕 从 capability 子包导出核心组件
from core.tool.capability import (
    # 类型
    Capability,
    CapabilityType,
    CapabilitySubtype,
    # Registry
    CapabilityRegistry,
    create_capability_registry,
    # Router
    CapabilityRouter,
    RoutingResult,
    create_capability_router,
    extract_keywords,
    # Invocation
    InvocationSelector,
    InvocationType,
    InvocationStrategy,
    create_invocation_selector,
    # Skill Loader
    SkillLoader,
    SkillInfo,
    create_skill_loader,
)

__all__ = [
    # 选择器
    "ToolSelector",
    "ToolSelectionResult",
    "create_tool_selector",
    # 执行器
    "ToolExecutor",
    "create_tool_executor",
    # 🆕 结果精简器（Context Engineering）
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
]

