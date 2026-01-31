"""
Capability 能力管理子包

作为 core/tool/ 的子包，提供能力管理的完整功能：
- Registry: 能力发现 + 元数据管理
- Router: 智能评分 + 最佳推荐
- InvocationSelector: 调用策略选择
- SkillLoader: Skill 内容加载（对齐 clawdbot 机制）

术语说明：
- Skill: 本地工作流技能（skills/library/，对齐 clawdbot）
- 通过 SKILL.md 文件声明，系统提示词注入

使用方式：
    # 方式1: 从子包导入
    from core.tool.capability import (
        CapabilityRegistry,
        CapabilityRouter,
        InvocationSelector,
        SkillLoader
    )
    
    # 方式2: 导入具体模块
    from core.tool.capability.registry import CapabilityRegistry
    from core.tool.capability.router import CapabilityRouter
    
    # 方式3: 导入类型
    from core.tool.capability.types import Capability, CapabilityType
"""

# 类型定义
from .types import (
    Capability,
    CapabilityType,
    CapabilitySubtype
)

# Registry
from .registry import (
    CapabilityRegistry,
    create_capability_registry,
    get_capability_registry  # 🆕 单例访问（推荐）
)

# Router
from .router import (
    CapabilityRouter,
    RoutingResult,
    create_capability_router,
    extract_keywords
)

# Invocation Selector
from .invocation import (
    InvocationSelector,
    InvocationType,
    InvocationStrategy,
    ToolCharacteristics,
    create_invocation_selector
)

# Skill Loader（本地工作流技能加载）
from .skill_loader import (
    SkillLoader,
    SkillInfo,
    create_skill_loader
)

__all__ = [
    # 类型
    "Capability",
    "CapabilityType",
    "CapabilitySubtype",
    
    # Registry
    "CapabilityRegistry",
    "create_capability_registry",
    "get_capability_registry",  # 🆕 单例访问
    
    # Router
    "CapabilityRouter",
    "RoutingResult",
    "create_capability_router",
    "extract_keywords",
    
    # Invocation
    "InvocationSelector",
    "InvocationType",
    "InvocationStrategy",
    "ToolCharacteristics",
    "create_invocation_selector",
    
    # Skill Loader（本地工作流技能）
    "SkillLoader",
    "SkillInfo",
    "create_skill_loader",
]

__version__ = "1.0.0"

