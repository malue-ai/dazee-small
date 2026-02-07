"""
本地存储层（100% 本地，零外部依赖）

桌面端实例使用 SQLite 作为本地存储：

┌───────────────────────────────────────────────────────────────────────┐
│                    存储层（100% 本地）                                  │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐      │
│  │ SQLite      │ │ SQLite FTS5 │ │ sqlite-vec  │ │ Skills 缓存 │      │
│  │ (消息/会话) │ │ (全文索引)   │ │ (可选向量)  │ │ (延迟加载)  │      │
│  └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘      │
└───────────────────────────────────────────────────────────────────────┘

使用入口：
    from infra.local_store import LocalWorkspace, get_workspace

    workspace = await get_workspace("dazee_agent")
    conv = await workspace.create_conversation(user_id="u1")
    msg = await workspace.create_message(conv.id, "user", "你好")
    results = await workspace.search("你好")
"""

# Workspace 管理器（统一入口）
from infra.local_store.workspace import (
    LocalWorkspace,
    close_all_workspaces,
    get_workspace,
)

# 引擎（高级用法 / 测试）
from infra.local_store.engine import (
    close_local_engine,
    create_local_engine,
    get_local_engine,
    get_local_session,
    is_vec_available,
)

# 模型
from infra.local_store.models import (
    LocalBase,
    LocalConversation,
    LocalIndexedFile,
    LocalMessage,
    LocalScheduledTask,
    LocalSkillCache,
)

# FTS5 全文搜索（消息专用）
from infra.local_store.fts import (
    FTSResult,
    rebuild_fts_index,
    search_messages,
    search_messages_count,
)

# 通用 FTS5 引擎（知识检索 + 记忆索引）
from infra.local_store.generic_fts import (
    FTS5Hit,
    FTS5TableConfig,
    GenericFTS5,
)

# 向量搜索（可选）
from infra.local_store.vector import (
    VectorSearchResult,
    create_vector_table,
    search_vectors,
)

# Skills 缓存
from infra.local_store.skills_cache import (
    cleanup_stale_cache,
    get_cached_skill,
    invalidate_skill_cache,
)

# CRUD
from infra.local_store import crud

__all__ = [
    # Workspace（推荐入口）
    "LocalWorkspace",
    "get_workspace",
    "close_all_workspaces",
    # 引擎
    "create_local_engine",
    "get_local_engine",
    "get_local_session",
    "close_local_engine",
    "is_vec_available",
    # 模型
    "LocalBase",
    "LocalConversation",
    "LocalMessage",
    "LocalScheduledTask",
    "LocalSkillCache",
    "LocalIndexedFile",
    # FTS5（消息专用）
    "FTSResult",
    "search_messages",
    "search_messages_count",
    "rebuild_fts_index",
    # 通用 FTS5（知识检索 + 记忆索引）
    "GenericFTS5",
    "FTS5TableConfig",
    "FTS5Hit",
    # 向量
    "VectorSearchResult",
    "create_vector_table",
    "search_vectors",
    # Skills
    "get_cached_skill",
    "invalidate_skill_cache",
    "cleanup_stale_cache",
    # CRUD
    "crud",
]
