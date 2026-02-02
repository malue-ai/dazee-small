"""
User Memory 模块 - 用户级记忆

用户级记忆按 user_id 隔离，包含：
- EpisodicMemory: 用户历史经验
- PreferenceMemory: 用户偏好（预留）
- E2BMemory: E2B 沙箱记忆（用户的云端计算环境）
- PlanMemory: 任务计划持久化（🆕 V4.3 长时运行支持）
"""

from .episodic import EpisodicMemory, create_episodic_memory, create_episodic_memory_async
from .preference import PreferenceMemory, create_preference_memory, create_preference_memory_async
from .e2b import E2BSandboxSession, E2BMemory, create_e2b_memory
from .plan import PlanMemory, create_plan_memory

__all__ = [
    # 历史经验
    "EpisodicMemory",
    "create_episodic_memory",
    "create_episodic_memory_async",
    # 用户偏好
    "PreferenceMemory",
    "create_preference_memory",
    "create_preference_memory_async",
    # E2B 沙箱
    "E2BSandboxSession",
    "E2BMemory",
    "create_e2b_memory",
    # 🆕 任务计划持久化
    "PlanMemory",
    "create_plan_memory",
]
