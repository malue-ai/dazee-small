"""
Tool 核心模块

模块结构：
- types.py: 统一类型定义（Capability, ToolContext, BaseTool 等）
- registry.py: 统一注册表（CapabilityRegistry, InstanceRegistry）
- selector.py: 工具选择器（含路由和 Skill Fallback）
- executor.py: 工具执行器（含调用策略选择）
- loader.py: 工具加载器
- capability/skill_loader.py: Skill 内容加载器

工具结果压缩：使用 core.context.compaction.tool_result.ToolResultCompressor

具体工具实现在 tools/ 目录下
"""

# ==================== Skill 加载器 ====================
from core.tool.capability.skill_loader import (
    SkillInfo,
    SkillLoader,
    create_skill_loader,
)

# ==================== 工具执行器 ====================
from core.tool.executor import (
    ToolExecutor,
    create_tool_executor,
)

# ==================== 工具加载器 ====================
from core.tool.loader import (
    ToolLoader,
    ToolLoadResult,
    create_tool_loader,
    get_core_tools_cached,
    get_tool_categories_cached,
)

# ==================== 注册表 ====================
from core.tool.registry import (  # 全局注册表; 实例注册表
    CapabilityRegistry,
    InstanceRegistry,
    InstanceTool,
    InstanceToolType,
    create_capability_registry,
    create_instance_registry,
    get_capability_registry,
)

# ==================== 工具选择器 ====================
from core.tool.selector import (
    RoutingResult,
    ToolSelectionResult,
    ToolSelector,
    create_tool_selector,
)

# ==================== 核心类型 ====================
from core.tool.types import (  # 枚举类型; 数据类; 基类; 工厂函数
    BaseTool,
    Capability,
    CapabilitySubtype,
    CapabilityType,
    InvocationStrategy,
    InvocationType,
    LegacyToolAdapter,
    ToolCharacteristics,
    ToolContext,
    ToolResult,
    create_tool_context,
)

# ==================== 导出列表 ====================
__all__ = [
    # 类型
    "CapabilityType",
    "CapabilitySubtype",
    "InvocationType",
    "ToolContext",
    "ToolResult",
    "Capability",
    "InvocationStrategy",
    "ToolCharacteristics",
    "BaseTool",
    "LegacyToolAdapter",
    "create_tool_context",
    # 注册表
    "CapabilityRegistry",
    "get_capability_registry",
    "create_capability_registry",
    "InstanceRegistry",
    "InstanceTool",
    "InstanceToolType",
    "create_instance_registry",
    # 选择器
    "ToolSelector",
    "ToolSelectionResult",
    "RoutingResult",
    "create_tool_selector",
    # 执行器
    "ToolExecutor",
    "create_tool_executor",
    # Skill 加载器
    "SkillLoader",
    "SkillInfo",
    "create_skill_loader",
    # 工具加载器
    "ToolLoader",
    "ToolLoadResult",
    "create_tool_loader",
    "get_tool_categories_cached",
    "get_core_tools_cached",
]
