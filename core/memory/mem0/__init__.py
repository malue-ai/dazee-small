"""
Mem0 记忆模块

基于 Mem0 框架的用户记忆层，支持：
- 用户画像存储与检索
- 跨 Session 的长期记忆
- 个性化信息注入

核心组件：
- Mem0MemoryPool: 全局缓存池（单例）
- format_memories_for_prompt: 格式化函数
- Mem0Config: 配置管理

使用示例：
    from core.memory.mem0 import get_mem0_pool, format_memories_for_prompt
    
    # 搜索用户相关记忆
    pool = get_mem0_pool()
    memories = pool.search(user_id="user_123", query="用户偏好")
    
    # 格式化为 Prompt 片段
    user_profile = format_memories_for_prompt(memories)
    
    # 注入到 System Prompt
    system_prompt = base_prompt + user_profile
"""

# 配置
from .config import (
    Mem0Config,
    QdrantConfig,
    EmbedderConfig,
    LLMConfig,
    get_mem0_config,
    set_mem0_config,
)

# 缓存池
from .pool import (
    Mem0MemoryPool,
    get_mem0_pool,
    reset_mem0_pool,
)

# 格式化
from .formatter import (
    format_memories_for_prompt,
    format_memories_as_context,
    format_single_memory,
    format_memories_by_category,
    create_user_profile_section,
)


__all__ = [
    # 配置
    "Mem0Config",
    "QdrantConfig",
    "EmbedderConfig",
    "LLMConfig",
    "get_mem0_config",
    "set_mem0_config",
    # 缓存池
    "Mem0MemoryPool",
    "get_mem0_pool",
    "reset_mem0_pool",
    # 格式化
    "format_memories_for_prompt",
    "format_memories_as_context",
    "format_single_memory",
    "format_memories_by_category",
    "create_user_profile_section",
]

