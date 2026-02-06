"""
Infrastructure 层 - 基础设施服务（桌面版）

┌─────────────────────────────────────────────────────────────┐
│                        infra/                               │
├─────────────────────────────────────────────────────────────┤
│  local_store/ │ 本地存储 (SQLite + FTS5 + sqlite-vec)       │
│               │ 会话/消息/Skills 缓存/全文搜索/向量搜索       │
├─────────────────────────────────────────────────────────────┤
│  storage/     │ 文件存储 (本地文件系统)                       │
│               │ 异步写入优化 (AsyncWriter + BatchWriter)      │
├─────────────────────────────────────────────────────────────┤
│  resilience/  │ 弹性机制 (重试/熔断/超时/降级)               │
│               │ LLM 调用保护                                 │
└─────────────────────────────────────────────────────────────┘
"""

# ==================== Local Store (SQLite) ====================
from infra.local_store import (
    LocalWorkspace,
    get_workspace,
    close_all_workspaces,
    LocalConversation,
    LocalMessage,
    LocalSkillCache,
    FTSResult,
    search_messages,
)

# ==================== Storage ====================
from infra.storage.base import StorageBackend
from infra.storage.local import LocalStorage

# ==================== Resilience ====================
from infra.resilience import (
    with_retry,
    with_timeout,
    CircuitBreaker,
    get_circuit_breaker,
)

__all__ = [
    # Local Store
    "LocalWorkspace",
    "get_workspace",
    "close_all_workspaces",
    "LocalConversation",
    "LocalMessage",
    "LocalSkillCache",
    "FTSResult",
    "search_messages",

    # Storage
    "StorageBackend",
    "LocalStorage",

    # Resilience
    "with_retry",
    "with_timeout",
    "CircuitBreaker",
    "get_circuit_breaker",
]
