# Infrastructure 基础设施层

> 提供与外部系统交互的统一抽象层，支持多种后端实现

## 📁 目录结构

```
infra/
├── README.md           # 本文档
├── __init__.py         # 统一导出
├── database/           # 关系型数据库
│   ├── engine.py       # SQLAlchemy 引擎
│   ├── base.py         # 基础模型
│   ├── models/         # ORM 模型定义
│   │   ├── conversation.py
│   │   ├── message.py
│   │   ├── file.py
│   │   ├── knowledge.py
│   │   ├── sandbox.py
│   │   └── user.py
│   └── crud/           # CRUD 操作
│       ├── base.py     # 通用 CRUD
│       ├── conversation.py
│       ├── message.py
│       └── ...
├── cache/              # 缓存层
│   └── redis.py        # Redis 客户端
├── storage/            # 文件存储
│   ├── base.py         # 存储抽象基类
│   └── local.py        # 本地存储实现
├── vector/             # 向量数据库 (预留)
│   ├── base.py         # 向量存储抽象基类
│   └── factory.py      # 工厂函数
└── graph/              # 图数据库 (预留)
    ├── base.py         # 图存储抽象基类
    └── factory.py      # 工厂函数
```

## 🏗️ 架构图

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           应用层 (services/)                             │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         infra/ 基础设施层                                │
│                                                                          │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐                     │
│  │  database/   │ │   cache/     │ │  storage/    │                     │
│  │  SQLAlchemy  │ │   Redis      │ │  File I/O    │                     │
│  │              │ │              │ │              │                     │
│  │  • ORM 模型  │ │  • KV 缓存   │ │  • 本地存储  │                     │
│  │  • CRUD 操作 │ │  • Pub/Sub   │ │  • S3 (TODO) │                     │
│  │  • 事务管理  │ │  • 分布式锁  │ │  • OSS(TODO) │                     │
│  └──────┬───────┘ └──────┬───────┘ └──────┬───────┘                     │
│         │                │                │                              │
│  ┌──────┴────────────────┴────────────────┴──────┐                      │
│  │                  统一抽象接口                   │                      │
│  └───────────────────────────────────────────────┘                      │
│                                                                          │
│  ┌──────────────┐ ┌──────────────┐                                      │
│  │  vector/     │ │   graph/     │  ← 预留模块                          │
│  │  向量数据库  │ │  图数据库    │                                      │
│  │              │ │              │                                      │
│  │  • Milvus    │ │  • Neo4j     │                                      │
│  │  • Qdrant    │ │  • ArangoDB  │                                      │
│  │  • Pinecone  │ │  • Neptune   │                                      │
│  └──────────────┘ └──────────────┘                                      │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                           外部存储系统                                   │
│  SQLite/PostgreSQL │ Redis │ 文件系统/S3 │ Milvus │ Neo4j              │
└─────────────────────────────────────────────────────────────────────────┘
```

## ⚙️ 环境变量配置

### Database (必需)

```bash
# SQLite (开发环境)
DATABASE_URL=sqlite+aiosqlite:///./data/zenflux.db

# PostgreSQL (生产环境)
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/zenflux
```

### Cache (可选)

```bash
# Redis
REDIS_URL=redis://localhost:6379/0
```

### Storage (可选)

```bash
# 本地存储 (默认)
STORAGE_BACKEND=local
STORAGE_BASE_DIR=./workspace/storage

# S3 (TODO)
STORAGE_BACKEND=s3
AWS_ACCESS_KEY_ID=xxx
AWS_SECRET_ACCESS_KEY=xxx
S3_BUCKET=zenflux-files
```

### Vector (预留)

```bash
# Milvus
VECTOR_BACKEND=milvus
MILVUS_HOST=localhost
MILVUS_PORT=19530

# Qdrant
VECTOR_BACKEND=qdrant
QDRANT_HOST=localhost
QDRANT_PORT=6333

# Pinecone
VECTOR_BACKEND=pinecone
PINECONE_API_KEY=xxx
PINECONE_ENVIRONMENT=us-east-1-aws
```

### Graph (预留)

```bash
# Neo4j
GRAPH_BACKEND=neo4j
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=xxx
NEO4J_DATABASE=neo4j
```

## 📖 使用示例

### Database

```python
from infra import get_async_session, init_database
from infra.database.crud import ConversationCRUD

# 初始化数据库
await init_database()

# 使用异步 Session
async with get_async_session() as session:
    crud = ConversationCRUD(session)
    conversation = await crud.create(user_id="user_123", title="新对话")
```

### Cache

```python
from infra import get_redis_client

# 获取 Redis 客户端
redis = await get_redis_client()

# 基础操作
await redis.set("key", "value", ttl=3600)
value = await redis.get("key")

# Hash 操作
await redis.hset("user:123", {"name": "张三", "age": "25"})
data = await redis.hgetall("user:123")
```

### Storage

```python
from infra import LocalStorage

# 创建存储实例
storage = LocalStorage(base_dir="./workspace/storage")

# 保存文件
path = await storage.save(file, "uploads/doc.pdf")

# 读取文件
content = await storage.get("uploads/doc.pdf")

# 获取访问 URL
url = storage.get_url("uploads/doc.pdf")
```

### Vector (预留)

```python
from infra import get_vector_store

# 获取向量存储
vector_store = await get_vector_store()

if vector_store:
    # 创建集合
    await vector_store.create_collection("documents", dimension=1536)
    
    # 插入向量
    ids = await vector_store.insert(
        collection="documents",
        vectors=[[0.1, 0.2, ...]],
        documents=["文档内容"],
        metadata=[{"source": "file.pdf"}]
    )
    
    # 相似度搜索
    results = await vector_store.search(
        collection="documents",
        query_vector=[0.15, 0.25, ...],
        top_k=5
    )
```

### Graph (预留)

```python
from infra import get_graph_store

# 获取图存储
graph_store = await get_graph_store()

if graph_store:
    # 创建节点
    person = await graph_store.create_node(
        labels=["Person"],
        properties={"name": "张三", "age": 30}
    )
    
    company = await graph_store.create_node(
        labels=["Company"],
        properties={"name": "ZenFlux"}
    )
    
    # 创建关系
    await graph_store.create_relationship(
        start_node_id=person.id,
        end_node_id=company.id,
        relationship_type="WORKS_AT",
        properties={"since": "2023-01-01"}
    )
    
    # Cypher 查询
    result = await graph_store.query(
        "MATCH (p:Person)-[:WORKS_AT]->(c:Company) RETURN p, c"
    )
```

## 🔧 扩展指南

### 添加新的存储后端

1. 在对应目录创建实现文件（如 `storage/s3.py`）
2. 继承抽象基类并实现所有方法
3. 在 factory.py 中注册新后端
4. 更新 `__init__.py` 导出

```python
# storage/s3.py
from infra.storage.base import StorageBackend

class S3Storage(StorageBackend):
    def __init__(self, bucket: str, region: str):
        self.bucket = bucket
        self.region = region
        # 初始化 S3 客户端...
    
    async def save(self, file, path, content_type=None) -> str:
        # 实现 S3 上传...
        pass
    
    # 实现其他方法...
```

### 添加新的数据库模型

1. 在 `database/models/` 创建模型文件
2. 在 `database/crud/` 创建对应的 CRUD 类
3. 在 `database/models/__init__.py` 导出模型

```python
# database/models/task.py
from infra.database.base import Base
from sqlalchemy import Column, String, DateTime

class Task(Base):
    __tablename__ = "tasks"
    
    id = Column(String, primary_key=True)
    title = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
```

## 📊 模块状态

| 模块 | 状态 | 后端支持 |
|------|------|----------|
| database | ✅ 已实现 | SQLite, PostgreSQL |
| cache | ✅ 已实现 | Redis |
| storage | ✅ 部分实现 | Local |
| vector | 🔲 预留 | Milvus, Qdrant, Pinecone |
| graph | 🔲 预留 | Neo4j, ArangoDB |

## 🎯 设计原则

1. **抽象优先**：每个模块都有抽象基类，便于切换后端
2. **工厂模式**：通过环境变量配置，自动创建对应实例
3. **优雅降级**：未配置时返回 None，不影响主流程
4. **单例管理**：全局单例，避免重复创建连接
5. **异步优先**：所有 I/O 操作都是异步的

---

**维护者**: ZenFlux Team  
**最后更新**: 2026-01-11

