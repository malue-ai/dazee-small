"""
Memory 模块 - 统一记忆管理

模块结构：
```
core/memory/
├── base.py               # 基类和通用类型
├── working.py            # WorkingMemory（会话级短期记忆）
├── user/                 # 用户级记忆
│   ├── episodic.py       # 用户历史经验
│   ├── preference.py     # 用户偏好（预留）
│   └── e2b.py            # E2B 沙箱记忆（用户的云端计算环境）
├── system/               # 系统级记忆
│   ├── skill.py          # SkillMemory（本地工作流技能缓存）
│   └── cache.py          # 系统缓存（预留）
└── manager.py            # MemoryManager
```

术语说明：
- Skill: 本地工作流技能（skills/library/，对齐 clawdbot 机制）

层级说明：
- 会话级（Session）：WorkingMemory - 当前会话的消息和工具调用
- 用户级（User）：EpisodicMemory, PreferenceMemory, E2BMemory - 跨会话保留
- 系统级（System）：SkillMemory, CacheMemory - 全局共享

使用示例：
```python
from core.memory import MemoryManager, create_memory_manager

# 创建记忆管理器
memory = create_memory_manager(user_id="user_123", storage_dir="./data")

# 会话级记忆
memory.working.add_message("user", "Hello")
memory.working.add_tool_call("web_search", {"query": "AI"})

# E2B 沙箱记忆（用户级）
memory.e2b.set_session(sandbox_session)
memory.e2b.add_execution(code, result, duration)
memory.e2b.add_persistent_sandbox(session, name="数据分析环境")

# 用户级记忆
memory.episodic.add_episode(task_id, user_intent, result)
memory.preference.set_preference("theme", "dark")

# 系统级记忆
memory.skill.register_skill("ppt_gen", "/path/to/skill")
memory.cache.set("key", value, ttl_seconds=3600)
```
"""

# 基础类型
from .base import (
    MemoryScope,
    StorageBackend,
    MemoryConfig,
    BaseMemory,
    BaseScopedMemory,
    MemoryEntry,
)

# 会话级记忆
from .working import (
    WorkingMemory,
    create_working_memory,
)

# 用户级记忆（包括 E2B）
from .user import (
    EpisodicMemory,
    create_episodic_memory,
    PreferenceMemory,
    create_preference_memory,
    E2BSandboxSession,
    E2BMemory,
    create_e2b_memory,
)

# 系统级记忆
from .system import (
    SkillMemory,
    create_skill_memory,
    CacheMemory,
    create_cache_memory,
)

# 统一管理器
from .manager import (
    MemoryManager,
    create_memory_manager,
    create_user_memory_manager,
)


__all__ = [
    # 基础类型
    "MemoryScope",
    "StorageBackend",
    "MemoryConfig",
    "BaseMemory",
    "BaseScopedMemory",
    "MemoryEntry",
    
    # 会话级记忆
    "WorkingMemory",
    "create_working_memory",
    
    # 用户级记忆
    "EpisodicMemory",
    "create_episodic_memory",
    "PreferenceMemory",
    "create_preference_memory",
    "E2BSandboxSession",
    "E2BMemory",
    "create_e2b_memory",
    
    # 系统级记忆（Skill = 本地工作流技能）
    "SkillMemory",
    "create_skill_memory",
    "CacheMemory",
    "create_cache_memory",
    
    # 统一管理器
    "MemoryManager",
    "create_memory_manager",
    "create_user_memory_manager",
]
