
> **版本**: 6.0.0 (最终版)
> **更新时间**: 2026-01-19
> **作者**: Manus AI

---

## 一、背景与需求分析

### 1.1 项目背景

为支撑智能体业务从原型到生产的演进，我们需要构建一个能够应对未来大规模用户增长，同时保证对话体验流畅、数据安全可靠的生产级消息系统架构。

### 1.2 核心需求

| 需求编号 | 需求描述 | 设计原则 |
| :---: | :--- | :--- |
| **R1** | 可靠性：消息不丢失 | 采用消息队列实现可靠的异步持久化 |
| **R2** | 低延迟：对话历史加载、会话内响应快 | 充分利用会话粘性，引入内存缓存和分页加载 |
| **R3** | 扩展性：数据结构支持未来分析与长记忆 | 设计丰富的 metadata 字段，涵盖 token、延迟、工具调用等 |
| **R4** | 高并发：系统能从容应对大规模读写请求 | 采用 CQRS 架构，读写分离 |

---

## 二、核心架构设计

### 2.1 设计理念：会话粘性 + 内存缓存 + 异步持久化

经过深入讨论，我们决定采用一种**高度优化的简化架构**，其核心思想是：

> **在保证会话粘性 (Session Affinity) 的前提下，以应用层内存缓存为核心，实现极致的读取性能；同时保留消息队列，保证写入操作的可靠性和高性能。**

- **会话粘性**: 假设外部的负载均衡层（如 Nginx, K8s Ingress）能通过**一致性哈希**（基于 `user_id` 或 `conversation_id`）等策略，保证同一用户在会话期间的请求始终被路由到**同一台应用服务器**。
- **内存缓存**: 读取操作的核心。每个应用服务器在内存中维护其负责的活跃会话上下文，实现纳秒级访问。
- **异步持久化**: 写入操作通过消息队列解耦，实现流量削峰和快速响应，保证核心服务不被数据库性能拖累。

### 2.2 核心分层架构

我们聚焦于应用本身的核心分层，将协议层和负载均衡层视为外部依赖。

![核心分层架构图](https://private-us-east-1.manuscdn.com/sessionFile/ZTKeaQ0eMp0LTSlGPAd3M1/sandbox/9pNlbJEX7vqt7yGR6kMNUP-images_1768803396546_na1fn_L2hvbWUvdWJ1bnR1L3NpbXBsaWZpZWRfYXJjaA.png?Policy=eyJTdGF0ZW1lbnQiOlt7IlJlc291cmNlIjoiaHR0cHM6Ly9wcml2YXRlLXVzLWVhc3QtMS5tYW51c2Nkbi5jb20vc2Vzc2lvbkZpbGUvWlRLZWFRMGVNcDBMVFNsR1BBZDNNMS9zYW5kYm94LzlwTmxiSkVYN3ZxdDd5R1I2a01OVVAtaW1hZ2VzXzE3Njg4MDMzOTY1NDZfbmExZm5fTDJodmJXVXZkV0oxYm5SMUwzTnBiWEJzYVdacFpXUmZZWEpqYUEucG5nIiwiQ29uZGl0aW9uIjp7IkRhdGVMZXNzVGhhbiI6eyJBV1M6RXBvY2hUaW1lIjoxNzk4NzYxNjAwfX19XX0_&Key-Pair-Id=K2HSFNDJXOU9YS&Signature=v6FLL56EKnlDlBsovRZWZO292I63CeNnYno4~Up31nRWUdXpjOAKy94wjxAbpErsl-uw3T8nsW~-Ykt~hU8ziiZYA1j5Wxrsc~eeXkdHheB0ylzWUNBN8qylZ-MMsFTMTWHEv7GRQ~lV-sD5jT6iKS7ct8wXYQ4UbtYgiocsQ~Lf7GkfZL1YMpbb-66kMzDV7zpWBQkmM17n62913sk3uPJRV4ZMKIS5xOziX~aCJWnNJqpXCu9FLi4B5knFAmNs7JIf-vk4zAnkfjx5WWPBBggMZthBv5VWtnQ0Ptiv3gHdDcOVZlKAWFYlzv9TAWnC~79rMqCeaaqbR8XqAzAfPw__)

| 核心层级 | 技术选型 | 核心职责 |
| :--- | :--- | :--- |
| **外部依赖层** | Nginx / K8s Ingress + gRPC / Streaming HTTP | 负载均衡 (一致性哈希) + 协议处理 |
| **会话管理层** | FastAPI / gRPC + Python Dict | 管理内存会话上下文、实现分页加载、处理业务逻辑 |
| **持久化层** | Redis Streams + PostgreSQL | **写入**：通过消息队列异步持久化<br/>**读取**：作为内存缓存的回源（冷启动或降级时） |

---

## 三、会话管理层详解 (读取路径)

### 3.1 内存会话上下文 (In-Memory Session Context)

这是实现低延迟读取的核心。每个应用服务器实例都会有一个 `SessionManager` 对象。

```python
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime

@dataclass
class Message:
    id: str
    role: str
    content: str
    created_at: datetime
    metadata: dict = field(default_factory=dict)

@dataclass
class ConversationContext:
    conversation_id: str
    messages: List[Message] = field(default_factory=list)
    oldest_cursor: Optional[str] = None  # 用于分页加载更早的消息

class SessionManager:
    """
    会话管理器：管理应用服务器内存中的活跃会话上下文。
    """
    def __init__(self, db_client, mq_client, max_context_size: int = 100):
        self._active_sessions: Dict[str, ConversationContext] = {}
        self._db = db_client
        self._mq = mq_client
        self._max_context_size = max_context_size  # 内存中保留的最大消息数

    async def get_context(self, conversation_id: str) -> ConversationContext:
        """获取会话上下文，如果内存中不存在，则从数据库冷启动"""
        if conversation_id not in self._active_sessions:
            self._active_sessions[conversation_id] = await self._load_from_db(conversation_id)
        return self._active_sessions[conversation_id]

    async def append_message(self, conversation_id: str, message: Message, stream_key: str):
        """向会话追加新消息，并触发异步持久化"""
        context = await self.get_context(conversation_id)
        context.messages.append(message)
        # 控制内存窗口大小
        if len(context.messages) > self._max_context_size:
            context.oldest_cursor = context.messages[0].id
            context.messages = context.messages[-self._max_context_size:]
        # 推送到消息队列进行异步持久化
        await self._mq.xadd(stream_key, message.to_dict())

    async def _load_from_db(self, conversation_id: str, limit: int = 50) -> ConversationContext:
        """从数据库加载最近的 N 条消息"""
        messages = await self._db.fetch_messages(conversation_id, limit=limit)
        return ConversationContext(
            conversation_id=conversation_id,
            messages=messages,
            oldest_cursor=messages[0].id if messages else None
        )
```

### 3.2 长会话分页加载机制

对于长会话，一次性加载所有历史记录是不现实的。我们采用**基于游标的分页 (Cursor-based Pagination)** 策略。

**读取流程**：

1.  **初始加载 (冷启动)**：当用户首次进入会话时，`SessionManager` 从数据库加载**最近的 N 条**消息（例如 50 条）到内存中。
2.  **向上滚动加载**：当用户在前端页面向上滚动，需要查看更早的历史记录时，前端发起请求。
3.  **分页 API**：前端请求携带当前最旧一条消息的 ID 或时间戳作为**游标**。
    ```
    GET /api/v1/conversations/{id}/messages?limit=50&before_cursor={message_id}
    ```
4.  **数据库查询**：后端根据游标查询更早的 N 条消息，并返回给前端。这些按需加载的历史消息**不一定**需要追加到核心的内存上下文中，可以仅供前端展示。

**内存中的上下文始终只保留一个有限的窗口**（例如最近 100 条），用于作为 LLM 的 Prompt，以控制 Token 成本和推理延迟。

### 3.3 粘性失效时的降级

在服务器重启、扩缩容等导致会话粘性失效的场景下，用户的请求会被路由到一台新的服务器。此时：

1.  新服务器的 `SessionManager` 中没有该会话的上下文。
2.  触发**冷启动**流程，从数据库加载初始页。
3.  对用户而言，体验是无缝的，仅有一次略高的延迟。

---

## 四、持久化层详解 (写入路径)

### 4.1 写入流程：常规消息 vs 流式消息

为兼顾性能、可靠性与数据一致性，我们对常规消息和流式消息采用两种不同的写入策略。

#### 4.1.1 常规消息写入 (如用户消息)

采用简单的**一步异步持久化**。

1.  **同步双写**: API 服务接收到消息后，立即将其追加到**内存缓存**并推送到 **Redis Streams (`message_create_stream`)**。
2.  **快速响应**: API 服务立即响应用户。
3.  **后台持久化**: Worker 从 `message_create_stream` 中消费消息并 `INSERT` 到数据库。

#### 4.1.2 流式消息写入 (如助手回答) - **v6.0 核心改进**

为防止在流式传输过程中因服务崩溃导致消息丢失，我们采用**两阶段持久化**策略，确保消息记录的原子性。

1.  **阶段一：创建占位消息 (Placeholder)**
    -   在调用 LLM 开始流式传输**之前**，立即创建一个 `status` 为 `streaming`、`content` 为空的助手消息。
    -   将这个**占位消息**同步推送到 `message_create_stream`。
    -   后台 Worker 消费后，会向数据库 `INSERT` 一条 `streaming` 状态的记录。这确保了即使服务崩溃，该次助手的“尝试回答”也被记录了下来。

2.  **阶段二：更新完整消息**
    -   LLM 流式传输**结束后**，API 服务将完整的消息 `content` 和 `metadata` (如 token 消耗) 连同 `message_id`，作为一个**更新事件**推送到一个**独立的 Redis Stream (`message_update_stream`)**。
    -   一个专门的 **Update Worker** 消费该更新事件，并根据 `message_id` 对数据库中的消息执行 `UPDATE` 操作，将 `status` 修改为 `completed` 并填入完整内容。

![流式消息写入流程图](https://private-us-east-1.manuscdn.com/sessionFile/ZTKeaQ0eMp0LTSlGPAd3M1/sandbox/9pNlbJEX7vqt7yGR6kMNUP-images_1768803396547_na1fn_L2hvbWUvdWJ1bnR1L3N0cmVhbWluZ193cml0ZV9mbG93.png?Policy=eyJTdGF0ZW1lbnQiOlt7IlJlc291cmNlIjoiaHR0cHM6Ly9wcml2YXRlLXVzLWVhc3QtMS5tYW51c2Nkbi5jb20vc2Vzc2lvbkZpbGUvWlRLZWFRMGVNcDBMVFNsR1BBZDNNMS9zYW5kYm94LzlwTmxiSkVYN3ZxdDd5R1I2a01OVVAtaW1hZ2VzXzE3Njg4MDMzOTY1NDdfbmExZm5fTDJodmJXVXZkV0oxYm5SMUwzTjBjbVZoYldsdVoxOTNjbWwwWlY5bWJHOTMucG5nIiwiQ29uZGl0aW9uIjp7IkRhdGVMZXNzVGhhbiI6eyJBV1M6RXBvY2hUaW1lIjoxNzk4NzYxNjAwfX19XX0_&Key-Pair-Id=K2HSFNDJXOU9YS&Signature=QMfQTxjXQFmcUcAXQZ-mfpN1ENCsNNz7SWtrEZc~bn~xEt0F7NKjgDfVujhwMNn5nzikvN2o4aKyY9Gkzz6s~ChZqGse7TH8nIc7VCiYVpW0YA6tGMOocmxAAdJXvm3meBwHbdBt-89WICQ6wGSbuAYYmGXN-tP-JRKFTcE1MbdPeid94KmeoDain9Pu1D85XvCmRasVCIxiykalwsnrtOcvLosk1I5zSY~Lb6Utln1kykD7t3UaUp1G1s9YeEkFY7EVZ8r~Fy32ZEH~jp~jQDnhzrlF0ouwPb2aEvnrYWScZoBAYEg0S8xybga0Pjlv2qQQxSALJHmVZmF4boafKw__)

### 4.2 Redis Streams 配置

需要两个独立的 Stream 和消费者组：

-   **`agent:message_create_stream`**: 用于创建新消息，由 `InsertWorker` 消费。
-   **`agent:message_update_stream`**: 用于更新已存在的消息，由 `UpdateWorker` 消费。

```python
import redis.asyncio as redis

class MessageQueueClient:
    CREATE_STREAM_KEY = "agent:message_create_stream"
    UPDATE_STREAM_KEY = "agent:message_update_stream"
    # ... (实现 XADD, XREADGROUP 等方法)
```

---

## 五、数据库设计与选型

### 5.1 数据库选型：PostgreSQL

我们推荐并基于 **PostgreSQL** 进行设计，主要原因如下：

| 优势 | 说明 |
| :--- | :--- |
| **强大的 JSONB 支持** | `metadata` 字段使用 JSONB 类型，可以高效地存储、索引和查询半结构化数据，为未来的数据分析和长记忆功能提供极大灵活性。 |
| **成熟可靠** | PostgreSQL 以其数据一致性、稳定性和强大的事务支持而闻名，是生产环境的可靠选择。 |
| **开源生态** | 拥有丰富的扩展（如 PostGIS, TimescaleDB, pgvector）和活跃的社区，便于解决问题和功能拓展。 |
| **可扩展性** | 支持多种复制和分区策略，能够随着业务增长进行水平扩展。 |

### 5.2 数据库 Schema 设计

#### 5.2.1 枚举类型定义

```sql
-- 消息角色枚举
CREATE TYPE message_role AS ENUM (
    'user', 
    'assistant', 
    'system', 
    'tool'
);

-- 消息状态枚举 (v6.0 新增)
CREATE TYPE message_status AS ENUM (
    'pending',      -- 待处理
    'streaming',    -- 流式传输中
    'completed',    -- 已完成
    'failed'        -- 已失败
);
```

#### 5.2.2 `conversations` 表

```sql
CREATE TABLE conversations (
    id              VARCHAR(64) PRIMARY KEY,      -- 会话唯一 ID (推荐 ULID)
    user_id         VARCHAR(64) NOT NULL,         -- 用户 ID
    title           VARCHAR(255) DEFAULT '新对话',
    status          VARCHAR(32) DEFAULT 'active', -- 会话状态: active, archived, deleted
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata        JSONB DEFAULT '{}'            -- 会话级元数据
);

-- 索引：按用户ID和更新时间查询会话列表
CREATE INDEX idx_conv_user_updated ON conversations(user_id, updated_at DESC);
```

#### 5.2.3 `messages` 表

```sql
CREATE TABLE messages (
    id              VARCHAR(64) PRIMARY KEY,            -- 消息唯一 ID (推荐 ULID)
    conversation_id VARCHAR(64) NOT NULL,               -- 外键，关联 conversations(id)
    role            message_role NOT NULL,              -- 角色: user, assistant, system, tool
    content         TEXT,                               -- 消息文本内容
    status          message_status DEFAULT 'completed', -- 消息状态 (v6.0 关键字段)
    parent_id       VARCHAR(64),                        -- 父消息ID (用于追问/重试场景)
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata        JSONB DEFAULT '{}'                  -- 消息级元数据
);

-- 核心索引：按会话ID和创建时间查询消息列表 (分页加载)
CREATE INDEX idx_msg_conv_created ON messages(conversation_id, created_at ASC);
```

### 5.3 关联配置与 ORM (SQLAlchemy 2.0)

```sql
-- 外键关联
ALTER TABLE messages 
ADD CONSTRAINT fk_conversation 
FOREIGN KEY (conversation_id) REFERENCES conversations(id) 
ON DELETE CASCADE;
```

```python
from sqlalchemy import ForeignKey, String, Text, Enum, DateTime, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship, DeclarativeBase
from typing import List, Optional
from datetime import datetime
import enum

class Base(DeclarativeBase):
    pass

class MessageRole(enum.Enum):
    user = "user"
    assistant = "assistant"
    system = "system"
    tool = "tool"

class MessageStatus(enum.Enum):
    pending = "pending"
    streaming = "streaming"
    completed = "completed"
    failed = "failed"

class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), default="新对话")
    status: Mapped[str] = mapped_column(String(32), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    metadata: Mapped[dict] = mapped_column(JSONB, default={})

    # 关联关系
    messages: Mapped[List["Message"]] = relationship(
        back_populates="conversation", 
        cascade="all, delete-orphan",
        order_by="Message.created_at"
    )

class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[MessageRole] = mapped_column(Enum(MessageRole), nullable=False)
    content: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[MessageStatus] = mapped_column(Enum(MessageStatus), default=MessageStatus.completed)
    parent_id: Mapped[Optional[str]] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    metadata: Mapped[dict] = mapped_column(JSONB, default={})

    # 关联关系
    conversation: Mapped["Conversation"] = relationship(back_populates="messages")
```

### 5.4 连接池配置

```python
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

# 创建异步引擎
engine = create_async_engine(
    "postgresql+asyncpg://user:password@host:5432/dbname",
    pool_size=20,         # 连接池大小，根据应用负载调整
    max_overflow=10,      # 允许临时超出的连接数
    pool_timeout=30,      # 获取连接的超时时间 (秒)
    pool_recycle=1800,    # 连接回收时间 (秒)，防止连接失效
    echo=False,           # 生产环境关闭 SQL 日志
)

# 创建异步 Session 工厂
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    autoflush=False,
)

# 依赖注入 (FastAPI)
async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
```

---

## 六、API 接口封装建议

### 6.1 数据模型 (Pydantic)

```python
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum

# --- 枚举 ---
class MessageRoleEnum(str, Enum):
    user = "user"
    assistant = "assistant"
    system = "system"
    tool = "tool"

# --- 请求模型 ---
class CreateConversationRequest(BaseModel):
    title: Optional[str] = "新对话"
    initial_message: Optional[str] = None

class SendMessageRequest(BaseModel):
    content: str
    parent_id: Optional[str] = None  # 用于追问/重试

# --- 响应模型 ---
class MessageResponse(BaseModel):
    id: str
    role: MessageRoleEnum
    content: Optional[str]
    status: str
    created_at: datetime
    metadata: Dict[str, Any] = {}

    class Config:
        from_attributes = True

class ConversationResponse(BaseModel):
    id: str
    title: str
    status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class ConversationDetailResponse(ConversationResponse):
    messages: List[MessageResponse] = []

class PaginatedMessagesResponse(BaseModel):
    messages: List[MessageResponse]
    has_more: bool
    next_cursor: Optional[str] = None
```

### 6.2 会话接口 (Conversations)

```python
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api/v1/conversations", tags=["Conversations"])

@router.post("", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    request: CreateConversationRequest,
    user_id: str = Depends(get_current_user_id),  # 从认证中获取
    db: AsyncSession = Depends(get_db),
):
    """创建一个新的会话"""
    conversation = Conversation(
        id=generate_ulid(),
        user_id=user_id,
        title=request.title,
    )
    db.add(conversation)
    await db.commit()
    return conversation

@router.get("", response_model=List[ConversationResponse])
async def list_conversations(
    user_id: str = Depends(get_current_user_id),
    limit: int = 20,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    """获取当前用户的会话列表，按更新时间倒序"""
    result = await db.execute(
        select(Conversation)
        .where(Conversation.user_id == user_id, Conversation.status != "deleted")
        .order_by(Conversation.updated_at.desc())
        .limit(limit).offset(offset)
    )
    return result.scalars().all()

@router.get("/{conversation_id}", response_model=ConversationDetailResponse)
async def get_conversation(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
    session_mgr: SessionManager = Depends(get_session_manager),
):
    """获取会话详情，包含最近的消息"""
    # 优先从内存缓存获取
    context = await session_mgr.get_context(conversation_id)
    # ... 组装响应
    pass

@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
):
    """删除一个会话及其所有消息 (软删除)"""
    await db.execute(
        update(Conversation)
        .where(Conversation.id == conversation_id)
        .values(status="deleted")
    )
    await db.commit()
```

### 6.3 消息接口 (Messages)

```python
from fastapi.responses import StreamingResponse

@router.post("/{conversation_id}/messages")
async def send_message(
    conversation_id: str,
    request: SendMessageRequest,
    session_mgr: SessionManager = Depends(get_session_manager),
    mq_client: MessageQueueClient = Depends(get_mq_client),
):
    """
    发送一条新消息，并获取流式响应 (SSE)。
    采用两阶段持久化保证流式消息的可靠性。
    """
    # 1. 持久化用户消息 (一步到位)
    user_message = Message(id=generate_ulid(), role='user', ...)
    await session_mgr.append_message(conversation_id, user_message, mq_client.CREATE_STREAM_KEY)

    # 2. 【阶段一】创建并持久化一个'占位'助手消息
    assistant_message_id = generate_ulid()
    placeholder_message = Message(
        id=assistant_message_id,
        conversation_id=conversation_id,
        role=MessageRole.assistant,
        content='',  # 内容为空
        status='streaming', # 状态为流式
    )
    await session_mgr.append_message(conversation_id, placeholder_message, mq_client.CREATE_STREAM_KEY)

    # 3. 调用 LLM 并流式返回
    async def generate_stream():
        full_content = ''
        try:
            async for chunk in call_llm_streaming(session_mgr, conversation_id):
                full_content += chunk
                yield f'data: {json.dumps({'type': 'chunk', 'content': chunk})}\n\n'
            
            # 4. 【阶段二】流式成功结束后，推送'更新'事件
            update_event = {
                'message_id': assistant_message_id,
                'payload': {
                    'content': full_content,
                    'status': 'completed',
                    'metadata': { ... } # 最终的 token 消耗等
                }
            }
            await mq_client.xadd(mq_client.UPDATE_STREAM_KEY, update_event)
            yield f'data: {json.dumps({'type': 'end', 'message_id': assistant_message_id})}\n\n'

        except Exception as e:
            # 5. 异常处理：推送状态为'failed'的更新事件
            error_update_event = {
                'message_id': assistant_message_id,
                'payload': {'status': 'failed', 'metadata': {'error': str(e)}}
            }
            await mq_client.xadd(mq_client.UPDATE_STREAM_KEY, error_update_event)
            yield f'data: {json.dumps({'type': 'error', 'message': 'An error occurred'})}\n\n'

    return StreamingResponse(generate_stream(), media_type="text/event-stream")

@router.get("/{conversation_id}/messages", response_model=PaginatedMessagesResponse)
async def list_messages(
    conversation_id: str,
    limit: int = 50,
    before_cursor: Optional[str] = None,  # message_id 作为游标
    db: AsyncSession = Depends(get_db),
):
    """分页加载指定会话的历史消息 (用于向上滚动加载)"""
    query = select(Message).where(Message.conversation_id == conversation_id)
    
    if before_cursor:
        # 获取游标消息的创建时间
        cursor_msg = await db.get(Message, before_cursor)
        if cursor_msg:
            query = query.where(Message.created_at < cursor_msg.created_at)
    
    query = query.order_by(Message.created_at.desc()).limit(limit + 1)  # 多取一条判断 has_more
    result = await db.execute(query)
    messages = list(result.scalars().all())
    
    has_more = len(messages) > limit
    if has_more:
        messages = messages[:limit]
    
    # 反转为正序
    messages.reverse()
    
    return PaginatedMessagesResponse(
        messages=messages,
        has_more=has_more,
        next_cursor=messages[0].id if messages and has_more else None
    )
```

### 6.4 API 接口汇总

| 方法 | 路径 | 描述 |
| :--- | :--- | :--- |
| `POST` | `/api/v1/conversations` | 创建新会话 |
| `GET` | `/api/v1/conversations` | 获取会话列表 |
| `GET` | `/api/v1/conversations/{id}` | 获取会话详情 |
| `DELETE` | `/api/v1/conversations/{id}` | 删除会话 |
| `POST` | `/api/v1/conversations/{id}/messages` | 发送消息 (核心对话, SSE) |
| `GET` | `/api/v1/conversations/{id}/messages` | 分页获取历史消息 |

---

## 七、可靠性与实施

### 7.1 可靠性保障 (v6.0 增强)

| 故障场景 | 保障机制 |
| :--- | :--- |
| **流式过程中服务崩溃** | 数据库中已存在一条 `status='streaming'` 的消息。用户刷新后，前端可根据此状态提示“上次回答未完成”，或后台任务可进行清理。**数据记录不丢失**。 |
| **应用服务器崩溃** | 内存上下文丢失。但已发送的消息已进入 Redis Streams。用户重连后，请求被路由到新服务器，触发冷启动，从数据库恢复上下文。 |
| **Worker 崩溃** | Redis Streams 消费者组机制确保未被 ACK 的消息会被重新分配给其他 Worker 处理。 |
| **Redis 崩溃** | 启用 Redis AOF 持久化策略。重启后可从磁盘恢复 Streams 数据。 |
| **PostgreSQL 崩溃** | Worker 的消息消费会暂停，消息积压在 Redis Streams 中。数据库恢复后，Worker 会继续处理。 |

### 7.2 实施建议

1.  **基础设施**：确保负载均衡层支持并配置了基于 `user_id` 或 `conversation_id` 的一致性哈希路由。
2.  **应用开发**：实现 `SessionManager`，处理内存缓存、分页加载和冷启动逻辑。
3.  **消息队列**：部署 Redis 和 Worker 进程，实现异步持久化流程。
4.  **监控**：重点监控 Redis Streams 的积压数量 (Pending Messages) 和应用服务器的内存使用率。

---

## 八、总结

本方案 (v6.0) 在 v5.0 的基础上，吸收了外部文档对**流式更新场景**的重视，引入了**两阶段持久化**机制。这一核心改进显著提升了流式消息的可靠性，有效防止了因服务在流式过程中崩溃而导致的数据丢失问题，使整个系统架构更加健壮和完善。

**最终架构的优势**：

- **极致性能**：会话内交互为纯内存操作，延迟极低。
- **架构简化**：减少了 Redis 分布式缓存的维护成本和复杂度。
- **高可靠性**：异步写入机制确保消息不丢失，两阶段持久化保障流式消息的原子性。
- **良好扩展性**：应用服务器可水平扩展，通过一致性哈希路由保证粘性。
- **完整的数据库设计**：包含 ORM 模型、连接池配置和关联关系。
- **清晰的 API 封装**：提供完整的 RESTful API 设计和代码示例。

这个设计在性能、可靠性和架构简洁性之间取得了出色的平衡，能够有力支撑智能体消息系统的长期发展。
