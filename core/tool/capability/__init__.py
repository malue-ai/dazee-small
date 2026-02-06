"""
Capability 子包

仅保留：
- skill_loader.py: Skill 内容加载器

其他功能已合并到上级模块，请直接从 core.tool 导入：
- types → core.tool.types
- registry → core.tool.registry
- selector → core.tool.selector
- executor → core.tool.executor
"""

from .skill_loader import (
    SkillInfo,
    SkillLoader,
    create_skill_loader,
)

__all__ = [
    "SkillLoader",
    "SkillInfo",
    "create_skill_loader",
]
