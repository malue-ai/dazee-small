# 数据库使用文档

> ⚠️ **版本说明**: 本文档已更新为新架构（基于 SQLAlchemy ORM）  
> 旧版本使用 `utils/database.py` (已废弃) → 新版本使用 `infra/database/`

---

## 概述

项目使用 **SQLAlchemy ORM** 作为数据库层，统一使用 **PostgreSQL** 作为数据库：
- **开发环境**: 本地 PostgreSQL（Docker 或原生安装）
- **生产环境**: AWS RDS PostgreSQL

### 核心特性
✅ 异步数据库操作（`asyncio` + `SQLAlchemy 2.0`）  
✅ 自动表结构管理（ORM Models）  
✅ CRUD 操作封装（Repository 模式）  
✅ 支持数据库迁移  

---

## 数据库结构

### 核心表

#### 1. **users** - 用户表
```python
# infra/database/models/user.py
class User(Base):
    id: str                    # 用户ID (主键)
    username: str              # 用户名
    email: str                 # 邮箱
    avatar_url: str            # 头像URL
    created_at: datetime       # 创建时间
    updated_at: datetime       # 更新时间
    metadata: dict             # 元数据 (JSON)
```

#### 2. **conversations** - 对话表
```python
# infra/database/models/conversation.py
class Conversation(Base):
    id: str                    # 对话ID (主键)
    user_id: str               # 用户ID (外键)
    title: str                 # 对话标题
    created_at: datetime       # 创建时间
    updated_at: datetime       # 更新时间
    metadata: dict             # 元数据 (JSON)
```

#### 3. **messages** - 消息表
```python
# infra/database/models/message.py
class Message(Base):
    id: str                    # 消息ID (主键)
    conversation_id: str       # 对话ID (外键)
    role: str                  # 角色: user/assistant/system
    content: str               # 消息内容
    status: str                # 状态: pending/completed/failed
    score: float               # 评分
    created_at: datetime       # 创建时间
    metadata: dict             # 元数据 (JSON)
```

#### 4. **files** - 文件表
```python
# infra/database/models/file.py
class File(Base):
    id: str                    # 文件ID (主键)
    user_id: str               # 用户ID (外键)
    filename: str              # 文件名
    file_size: int             # 文件大小
    content_type: str          # MIME类型
    category: str              # 分类: knowledge/avatar/attachment/temp
    status: str                # 状态: uploading/uploaded/ready
    storage_type: str          # 存储类型: s3/local
    storage_path: str          # 存储路径
    storage_url: str           # 访问URL
    created_at: datetime       # 创建时间
    metadata: dict             # 元数据
```

#### 5. **knowledge_bases** - 知识库表
```python
# infra/database/models/knowledge.py
class KnowledgeBase(Base):
    id: str                    # 知识库ID (主键)
    name: str                  # 知识库名称
    description: str           # 描述
    owner_id: str              # 所有者ID
    visibility: str            # 可见性: private/public/unlisted
    document_count: int        # 文档数量
    ragie_partition_id: str    # Ragie分区ID (用于RAG)
    created_at: datetime       # 创建时间
```

#### 6. **sandboxes** - 沙箱表
```python
# infra/database/models/sandbox.py
class Sandbox(Base):
    id: str                    # 沙箱ID (主键)
    e2b_sandbox_id: str        # E2B沙箱ID
    session_id: str            # 会话ID
    user_id: str               # 用户ID
    status: str                # 状态: creating/ready/running/stopped
    created_at: datetime       # 创建时间
    metadata: dict             # 元数据
```

---

## 快速开始

### 1. 环境配置

```bash
# .env 文件

# PostgreSQL (开发和生产环境)
# 开发环境：使用本地 PostgreSQL
DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/zenflux

# 生产环境：使用 AWS RDS PostgreSQL (通过 SSM Parameter Store 管理)
# 在 AWS 环境中，DATABASE_URL 通过 SSM Parameter Store 自动注入
# 配置路径: /copilot/zen0-backend/staging/secrets/DATABASE_URL
```

### 2. 初始化数据库

数据库会在应用启动时自动初始化：

```python
# main.py
from infra.database import init_database

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时初始化数据库
    await init_database()
    yield
```

### 3. 数据库配置说明

#### 开发环境
- 使用本地 PostgreSQL（推荐使用 Docker 部署）
- 配置方式：在 `.env` 文件中设置 `DATABASE_URL`

**快速启动 PostgreSQL（Docker）：**
```bash
docker run -d \
  --name zenflux-postgres \
  -e POSTGRES_PASSWORD=password \
  -e POSTGRES_DB=zenflux \
  -p 5432:5432 \
  postgres:15
```

#### 生产环境（staging）
- 使用 AWS RDS PostgreSQL
- 数据库凭证通过 AWS SSM Parameter Store 管理
- 配置路径: `/copilot/zen0-backend/staging/secrets/DATABASE_URL`
- 部署时自动注入到容器环境变量

---

## 使用示例

### 方式 1: 使用 CRUD 服务（推荐）

```python
from infra.database import get_async_session
from infra.database.crud import UserCRUD, ConversationCRUD, MessageCRUD

async def example():
    async with get_async_session() as session:
        # 创建用户
        user = await UserCRUD.create(
            session,
            id="user_123",
            username="alice",
            email="alice@example.com"
        )
        
        # 创建对话
        conversation = await ConversationCRUD.create(
            session,
            id="conv_456",
            user_id=user.id,
            title="关于AI的讨论"
        )
        
        # 创建消息
        message = await MessageCRUD.create(
            session,
            id="msg_789",
            conversation_id=conversation.id,
            role="user",
            content="你好！"
        )
        
        # 查询对话历史
        messages = await MessageCRUD.get_conversation_messages(
            session,
            conversation_id=conversation.id
        )
        
        # 更新对话标题
        await ConversationCRUD.update_title(
            session,
            conversation_id=conversation.id,
            title="新标题"
        )
```

### 方式 2: FastAPI 依赖注入

```python
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from infra.database import get_async_session
from infra.database.crud import UserCRUD

router = APIRouter()

@router.get("/users/{user_id}")
async def get_user(
    user_id: str,
    session: AsyncSession = Depends(get_async_session)
):
    """获取用户信息"""
    user = await UserCRUD.get_by_id(session, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    return user

@router.post("/users")
async def create_user(
    username: str,
    email: str,
    session: AsyncSession = Depends(get_async_session)
):
    """创建用户"""
    user = await UserCRUD.create(
        session,
        id=f"user_{uuid4()}",
        username=username,
        email=email
    )
    return user
```

---

## CRUD 操作详解

### UserCRUD

```python
from infra.database.crud import UserCRUD

# 创建用户
user = await UserCRUD.create(session, id="user_123", username="alice")

# 根据ID获取
user = await UserCRUD.get_by_id(session, "user_123")

# 根据用户名获取
user = await UserCRUD.get_by_username(session, "alice")

# 更新用户
await UserCRUD.update(session, "user_123", email="new@example.com")

# 删除用户
await UserCRUD.delete(session, "user_123")
```

### ConversationCRUD

```python
from infra.database.crud import ConversationCRUD

# 创建对话
conv = await ConversationCRUD.create(
    session,
    id="conv_123",
    user_id="user_123",
    title="新对话"
)

# 获取用户的所有对话
conversations = await ConversationCRUD.get_user_conversations(
    session,
    user_id="user_123"
)

# 更新对话标题
await ConversationCRUD.update_title(
    session,
    conversation_id="conv_123",
    title="更新后的标题"
)

# 删除对话
await ConversationCRUD.delete(session, "conv_123")
```

### MessageCRUD

```python
from infra.database.crud import MessageCRUD

# 创建消息
message = await MessageCRUD.create(
    session,
    id="msg_123",
    conversation_id="conv_123",
    role="user",
    content="你好！"
)

# 获取对话的所有消息
messages = await MessageCRUD.get_conversation_messages(
    session,
    conversation_id="conv_123"
)

# 更新消息状态
await MessageCRUD.update_status(
    session,
    message_id="msg_123",
    status="completed"
)

# 删除消息
await MessageCRUD.delete(session, "msg_123")
```

### FileCRUD

```python
from infra.database.crud import FileCRUD

# 创建文件记录
file = await FileCRUD.create(
    session,
    id="file_123",
    user_id="user_123",
    filename="document.pdf",
    file_size=1024000,
    content_type="application/pdf",
    storage_path="s3://bucket/file_123.pdf"
)

# 获取用户的所有文件
files = await FileCRUD.get_user_files(
    session,
    user_id="user_123",
    category="knowledge"
)

# 更新文件状态
await FileCRUD.update_status(
    session,
    file_id="file_123",
    status="ready"
)
```

### KnowledgeCRUD

```python
from infra.database.crud import KnowledgeCRUD

# 创建知识库
kb = await KnowledgeCRUD.create_knowledge_base(
    session,
    id="kb_123",
    name="技术文档",
    owner_id="user_123",
    description="技术相关的文档集合"
)

# 添加文档到知识库
doc = await KnowledgeCRUD.create_document(
    session,
    id="doc_123",
    kb_id="kb_123",
    file_id="file_123",
    name="API文档",
    original_filename="api.pdf"
)

# 获取知识库的所有文档
documents = await KnowledgeCRUD.get_kb_documents(
    session,
    kb_id="kb_123"
)
```

---

## 架构说明

### 目录结构

```
infra/database/
├── __init__.py              # 导出接口
├── base.py                  # ORM Base类
├── engine.py                # 数据库引擎和会话管理
├── models/                  # ORM Models
│   ├── user.py
│   ├── conversation.py
│   ├── message.py
│   ├── file.py
│   ├── knowledge.py
│   └── sandbox.py
└── crud/                    # CRUD 操作
    ├── base.py              # Base CRUD
    ├── user.py
    ├── conversation.py
    ├── message.py
    ├── file.py
    ├── knowledge.py
    └── sandbox.py
```

### 设计模式

1. **Repository 模式**: CRUD 层封装所有数据库操作
2. **依赖注入**: FastAPI 路由使用 `Depends(get_async_session)`
3. **异步优先**: 所有操作都是异步的
4. **类型安全**: 使用 Pydantic 和 SQLAlchemy 类型提示

---

## 数据库迁移

迁移脚本位于 `migrations/` 目录：

```bash
migrations/
├── 001_update_messages_schema.py
├── 002_create_files_table.py
├── 003_create_knowledge_tables.py
├── 004_add_missing_file_columns.py
├── 005_add_mime_type_column.py
└── 006_create_sandboxes_table.py
```

运行迁移：

```bash
python migrations/001_update_messages_schema.py
```

---

## 最佳实践

### ✅ 应该做的

```python
# 1. 使用异步上下文管理器
async with get_async_session() as session:
    user = await UserCRUD.get_by_id(session, user_id)

# 2. 使用 CRUD 层（不直接操作 ORM）
user = await UserCRUD.create(session, ...)  # ✅
user = User(...)  # ❌ 不推荐

# 3. 使用事务
async with session.begin():
    await UserCRUD.create(...)
    await ConversationCRUD.create(...)

# 4. 添加索引优化查询
# models 中已经定义了常用索引
```

### ❌ 不应该做的

```python
# 1. 不要在循环中执行单条查询
for user_id in user_ids:
    user = await UserCRUD.get_by_id(session, user_id)  # ❌ N+1 问题

# 2. 不要忘记关闭 session
session = AsyncSessionLocal()
# ... 操作 ...
# ❌ 忘记 await session.close()

# 3. 不要在同步代码中调用异步方法
user = UserCRUD.get_by_id(session, user_id)  # ❌ 缺少 await

# 4. 不要硬编码 SQL
await session.execute("SELECT * FROM users")  # ❌ 使用 ORM
```

---

## 性能优化

### 1. 批量操作

```python
# 批量插入
users = [
    User(id=f"user_{i}", username=f"user{i}")
    for i in range(100)
]
session.add_all(users)
await session.commit()
```

### 2. 预加载关联数据

```python
from sqlalchemy.orm import selectinload

# 一次查询加载对话和消息
stmt = select(Conversation).options(
    selectinload(Conversation.messages)
).where(Conversation.user_id == user_id)

result = await session.execute(stmt)
conversations = result.scalars().all()
```

### 3. 分页查询

```python
# 获取第2页，每页20条
messages = await MessageCRUD.get_conversation_messages(
    session,
    conversation_id=conv_id,
    limit=20,
    offset=20
)
```

---

## 故障排查

### 问题 1: 数据库锁定

```python
# PostgreSQL 支持高并发读写
# 解决方案：使用 PostgreSQL（生产环境）
DATABASE_URL=postgresql+asyncpg://...
```

### 问题 2: 连接池耗尽

```python
# 检查是否正确关闭 session
async with get_async_session() as session:
    # 操作完成后自动关闭
    pass
```

### 问题 3: 迁移冲突

```bash
# PostgreSQL 环境下重建数据库（开发环境）
# 方法1：使用 psql
psql -U postgres -c "DROP DATABASE zenflux;"
psql -U postgres -c "CREATE DATABASE zenflux;"

# 方法2：使用 Python 脚本
python -c "from infra.database import init_database; import asyncio; asyncio.run(init_database())"
```

---

## 相关文档

- 📖 [数据存储架构](../architecture/08-DATA_STORAGE_ARCHITECTURE.md)
- 📖 [PostgreSQL 消息存储方案](../architecture/20-POSTGRESQL_MESSAGE_SCHEMA_DESIGN.md)
- 📖 [SQLAlchemy 官方文档](https://docs.sqlalchemy.org/)
- 📖 [asyncpg 文档](https://magicstack.github.io/asyncpg/)
- 📖 [PostgreSQL 官方文档](https://www.postgresql.org/docs/)
