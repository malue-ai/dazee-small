"""
System Memory 模块 - 系统级记忆

系统级记忆是全局共享的，包含：
- SkillMemory: 已加载的 Skills 缓存（本地工作流技能）
- CacheMemory: 系统缓存（预留）

术语说明：
- Skill: 本地工作流技能（skills/library/，对齐 clawdbot 机制）
"""

from .cache import CacheMemory, create_cache_memory
from .skill import SkillMemory, create_skill_memory, create_skill_memory_async

__all__ = [
    "SkillMemory",
    "create_skill_memory",
    "create_skill_memory_async",
    "CacheMemory",
    "create_cache_memory",
]
