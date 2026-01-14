"""
Infrastructure 层 - 基础设施服务

提供与外部系统交互的统一抽象层：

┌─────────────────────────────────────────────────────────────┐
│                        infra/                               │
├─────────────────────────────────────────────────────────────┤
│  database/   │ 关系型数据库 (SQLite/PostgreSQL)             │
│              │ SQLAlchemy 2.0 ORM + CRUD 操作               │
├─────────────────────────────────────────────────────────────┤
│  cache/      │ 缓存层 (Redis)                               │
│              │ Session 缓存、分布式锁、Pub/Sub              │
├─────────────────────────────────────────────────────────────┤
│  storage/    │ 文件存储 (本地/S3/OSS)                       │
│              │ 用户上传文件、生成文件存储                    │
├─────────────────────────────────────────────────────────────┤
│  vector/     │ 向量数据库 (Milvus/Qdrant/Pinecone)          │
│              │ RAG 检索、语义搜索、长期记忆                  │
├─────────────────────────────────────────────────────────────┤
│  graph/      │ 图数据库 (Neo4j/ArangoDB)                    │
│              │ 知识图谱、实体关系、关联查询                  │
├─────────────────────────────────────────────────────────────┤
│  sandbox/    │ 沙盒执行环境 (E2B/Docker)                    │
│              │ 代码执行、文件操作、多用户隔离                │
└─────────────────────────────────────────────────────────────┘

设计原则：
1. 抽象接口：每个模块提供统一的抽象基类
2. 工厂模式：通过环境变量配置后端实现
3. 优雅降级：未配置时返回 None，不影响主流程
4. 单例管理：全局单例，避免重复创建连接
"""

# ==================== Database ====================
from infra.database import (
    get_async_session,
    init_database,
    AsyncSessionLocal,
    engine,
)

# ==================== Cache ====================
from infra.cache import (
    RedisClient,
    create_redis_client,
    get_redis_client,
)

# ==================== Storage ====================
from infra.storage.base import StorageBackend
from infra.storage.local import LocalStorage

# ==================== Vector (预留) ====================
from infra.vector import (
    VectorStore,
    VectorSearchResult,
    create_vector_store,
    get_vector_store,
)

# ==================== Graph (预留) ====================
from infra.graph import (
    GraphStore,
    Node,
    Relationship,
    GraphQueryResult,
    create_graph_store,
    get_graph_store,
)

# ==================== Sandbox ====================
from infra.sandbox import (
    SandboxProvider,
    SandboxInfo,
    SandboxStatus,
    CommandResult,
    CodeResult,
    SandboxError,
    SandboxNotFoundError,
    SandboxNotAvailableError,
    create_sandbox_provider,
    get_sandbox_provider,
    sandbox_run_command,
    sandbox_read_file,
    sandbox_write_file,
    sandbox_list_dir,
    sandbox_run_project,
)


__all__ = [
    # Database
    "get_async_session",
    "init_database",
    "AsyncSessionLocal",
    "engine",
    
    # Cache
    "RedisClient",
    "create_redis_client",
    "get_redis_client",
    
    # Storage
    "StorageBackend",
    "LocalStorage",
    
    # Vector
    "VectorStore",
    "VectorSearchResult",
    "create_vector_store",
    "get_vector_store",
    
    # Graph
    "GraphStore",
    "Node",
    "Relationship",
    "GraphQueryResult",
    "create_graph_store",
    "get_graph_store",
    
    # Sandbox
    "SandboxProvider",
    "SandboxInfo",
    "SandboxStatus",
    "CommandResult",
    "CodeResult",
    "SandboxError",
    "SandboxNotFoundError",
    "SandboxNotAvailableError",
    "create_sandbox_provider",
    "get_sandbox_provider",
    "sandbox_run_command",
    "sandbox_read_file",
    "sandbox_write_file",
    "sandbox_list_dir",
    "sandbox_run_project",
]
