# 消息会话管理架构

> **版本**: v1.0  
> **更新时间**: 2026-01-19  
> **状态**: 生产就绪

---

## 目录

1. [概述](#概述)
2. [核心设计理念](#核心设计理念)
3. [系统架构](#系统架构)
4. [数据模型](#数据模型)
5. [持久化机制](#持久化机制)
6. [内存缓存机制](#内存缓存机制)
7. [分页加载机制](#分页加载机制)
8. [API 接口设计](#api-接口设计)
9. [性能优化](#性能优化)
10. [可靠性保障](#可靠性保障)
11. [部署与运维](#部署与运维)
12. [实施状态](#实施状态)

---

## 概述

消息会话管理是 ZenFlux Agent 的核心基础设施，负责：

- ✅ **消息生命周期管理**：创建、更新、查询、删除
- ✅ **流式消息处理**：两阶段持久化，保证可靠性
- ✅ **高性能读取**：内存缓存 + 会话粘性，实现纳秒级访问
- ✅ **异步写入**：Redis Streams 解耦，不阻塞 API 响应
- ✅ **分页加载**：游标分页，支持长会话历史查询
- ✅ **计费集成**：合并写入，原子性更新

### 核心特性

| 特性 | 说明 | 技术实现 |
|------|------|---------|
| **两阶段持久化** | 占位消息 + 完整更新 | Redis Streams + Workers |
| **异步写入** | 不阻塞 API 响应 | Redis Streams 队列 |
| **内存缓存** | 纳秒级读取 | SessionCacheService |
| **会话粘性** | 同一会话路由到同一服务器 | 负载均衡一致性哈希 |
| **游标分页** | 高效加载历史消息 | `before_cursor` 参数 |
| **合并写入** | 减少数据库操作 | 计费信息合并到最终更新 |

---

## 核心设计理念

### 设计原则

1. **会话粘性 + 内存缓存**
   - 假设负载均衡层保证会话粘性
   - 应用层内存缓存实现极致读取性能
   - 冷启动时从数据库回源

2. **异步持久化**
   - 所有写入通过 Redis Streams 异步处理
   - API 层不直接写数据库
   - 后台 Workers 消费并持久化

3. **两阶段持久化**
   - 流式消息采用占位 + 完整更新
   - 保证服务崩溃时数据不丢失
   - 支持故障恢复

4. **合并写入优化**
   - 计费信息与最终消息合并写入
   - 减少 50% 数据库操作
   - 提升数据一致性

---

## 系统架构

### 整体架构图

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        消息会话管理架构                                    │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │                    协议入口层（平级）                               │ │
│  │  ┌──────────────┐                    ┌──────────────┐              │ │
│  │  │  routers/   │  HTTP/SSE          │    grpc/     │  gRPC        │ │
│  │  │ conversation│ ◄────────────      │ conversation │ ◄──────      │ │
│  │  └──────┬───────┘                    └──────┬───────┘              │ │
│  │         │                                   │                      │ │
│  │         └─────────────┬─────────────────────┘                      │ │
│  │                       ▼                                             │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│                       │                                                   │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │                    services/ 业务逻辑层                             │ │
│  │  ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐     │ │
│  │  │ chat_service    │ │ conversation    │ │ session_cache   │     │ │
│  │  │ • 消息发送      │ │ • 对话管理      │ │ • 内存缓存      │     │ │
│  │  │ • 流式处理      │ │ • 消息查询      │ │ • 分页加载      │     │ │
│  │  └─────────────────┘ └─────────────────┘ └─────────────────┘     │ │
│  └────────────────────────────────┬──────────────────────────────────┘ │
│                                   │                                     │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │                    core/events/ 事件层                              │ │
│  │  ┌──────────────────────────────────────────────────────────────┐   │ │
│  │  │ EventBroadcaster                                             │   │ │
│  │  │ • 内容累积 (ContentAccumulator)                              │   │ │
│  │  │ • 占位消息创建                                                │   │ │
│  │  │ • 最终消息更新（合并 usage）                                  │   │ │
│  │  └──────────────────────────────────────────────────────────────┘   │ │
│  └────────────────────────────────┬──────────────────────────────────┘ │
│                                   │                                     │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │                    infra/ 基础设施层                                │ │
│  │  ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐     │ │
│  │  │ message_queue/  │ │ database/       │ │ cache/          │     │ │
│  │  │ • Redis Streams │ │ • PostgreSQL    │ │ • Redis         │     │ │
│  │  │ • Workers       │ │ • Models        │ │ • SessionCache  │     │ │
│  │  └─────────────────┘ └─────────────────┘ └─────────────────┘     │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 核心组件

| 组件 | 职责 | 文件位置 |
|------|------|----------|
| **ChatService** | 消息发送入口，流式处理 | `services/chat_service.py` |
| **ConversationService** | 对话和消息 CRUD | `services/conversation_service.py` |
| **SessionCacheService** | 内存会话上下文缓存 | `services/session_cache_service.py` |
| **EventBroadcaster** | 内容累积和持久化触发 | `core/events/broadcaster.py` |
| **MessageQueueClient** | Redis Streams 客户端 | `infra/message_queue/streams.py` |
| **InsertWorker** | 消费创建事件，执行 INSERT | `infra/message_queue/workers.py` |
| **UpdateWorker** | 消费更新事件，执行 UPDATE | `infra/message_queue/workers.py` |

---

## 数据模型

### 数据库 Schema

#### conversations 表

```sql
CREATE TABLE conversations (
    id              VARCHAR(64) PRIMARY KEY,
    user_id         VARCHAR(64) NOT NULL,
    title           VARCHAR(255) DEFAULT '新对话',
    status          VARCHAR(32) DEFAULT 'active',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata        JSONB DEFAULT '{}'
);

-- 索引
CREATE INDEX idx_conversations_user_updated 
ON conversations(user_id, updated_at DESC);
```

#### messages 表

```sql
CREATE TABLE messages (
    id              VARCHAR(64) PRIMARY KEY,
    conversation_id VARCHAR(64) NOT NULL,
    role            VARCHAR(20) NOT NULL,
    content         TEXT NOT NULL,
    status          VARCHAR(32) DEFAULT 'completed',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata        JSONB DEFAULT '{}'
);

-- 外键
ALTER TABLE messages 
ADD CONSTRAINT fk_conversation 
FOREIGN KEY (conversation_id) REFERENCES conversations(id) 
ON DELETE CASCADE;

-- 索引
CREATE INDEX idx_messages_conv_created 
ON messages(conversation_id, created_at ASC);

CREATE INDEX idx_messages_status 
ON messages(status) WHERE status = 'streaming';
```

### ORM 模型

#### Message 模型

```python
class Message(Base):
    __tablename__ = "messages"
    
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[Optional[str]] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    _metadata: Mapped[dict] = mapped_column(
        "metadata",
        JSONB if not IS_SQLITE else JSON,
        default=lambda: {},
        nullable=False
    )
```

### 消息状态流转

```
pending → streaming → completed
              ↓
           failed
```

| 状态 | 说明 | 使用场景 |
|------|------|---------|
| `pending` | 待处理 | 消息创建但未开始处理 |
| `streaming` | 流式传输中 | 占位消息，正在生成内容 |
| `completed` | 已完成 | 消息生成完成，包含完整内容 |
| `failed` | 已失败 | 消息生成失败，包含错误信息 |

---

## 持久化机制

### 两阶段持久化流程

#### 阶段一：创建占位消息

```
用户请求
  ↓
ChatService 创建占位消息
  ├─ status='streaming'
  ├─ content='[]' (空)
  └─ metadata={stream: {phase: 'placeholder'}}
  ↓
推送到 message_create_stream (Redis Streams)
  ↓
InsertWorker 消费
  ↓
INSERT 到 PostgreSQL (status='streaming')
  ↓
更新 SessionCacheService 内存缓存
```

**代码位置**：
- `services/chat_service.py:441-449` - 创建占位消息
- `infra/message_queue/streams.py:97-129` - 推送创建事件
- `infra/message_queue/workers.py:22-166` - InsertWorker 消费

#### 流式传输循环

```
LLM 返回 chunk
  ↓
EventBroadcaster 累积 (ContentAccumulator)
  ↓
SSE 发送给前端
  ↓
Checkpoint (可选，每个 content_stop 后)
  ↓
返回 chunk (循环)
```

**代码位置**：
- `core/events/broadcaster.py` - 内容累积和 SSE 发送

#### 阶段二：更新完整消息（合并写入）

```
流式传输结束
  ↓
EventBroadcaster._finalize_message()
  ├─ 合并 content (完整内容)
  ├─ 合并 usage (计费信息)
  └─ 合并 stream.phase='final'
  ↓
推送到 message_update_stream (Redis Streams)
  ↓
UpdateWorker 消费
  ↓
UPDATE PostgreSQL (content + status='completed' + metadata)
  ↓
更新 SessionCacheService 内存缓存
```

**代码位置**：
- `core/events/broadcaster.py:733-784` - 最终消息更新
- `infra/message_queue/streams.py:131-161` - 推送更新事件
- `infra/message_queue/workers.py:169-311` - UpdateWorker 消费

### Redis Streams 配置

#### Stream 键名

```python
class MessageQueueClient:
    CREATE_STREAM_KEY = "agent:message_create_stream"
    UPDATE_STREAM_KEY = "agent:message_update_stream"
```

#### 消费者组

```python
# InsertWorker
group_name = "insert_workers"
consumer_name = "insert_worker_{id}"

# UpdateWorker
group_name = "update_workers"
consumer_name = "update_worker_{id}"
```

### Workers 机制

#### InsertWorker

- **职责**：消费 `message_create_stream`，执行 INSERT
- **处理逻辑**：
  1. 从 Stream 读取消息（XREADGROUP）
  2. 解析字段（message_id, conversation_id, role, content, status, metadata）
  3. 执行 INSERT 到 PostgreSQL
  4. ACK 消息（XACK）

#### UpdateWorker

- **职责**：消费 `message_update_stream`，执行 UPDATE
- **处理逻辑**：
  1. 从 Stream 读取消息（XREADGROUP）
  2. 解析字段（message_id, content, status, metadata）
  3. 执行 UPDATE（深度合并 metadata）
  4. ACK 消息（XACK）

---

## 内存缓存机制

### SessionCacheService 设计

#### 核心数据结构

```python
@dataclass
class MessageContext:
    """消息上下文（内存中的简化版本）"""
    id: str
    role: str
    content: str  # JSON 字符串
    created_at: datetime
    metadata: dict

@dataclass
class ConversationContext:
    """会话上下文（内存缓存）"""
    conversation_id: str
    messages: List[MessageContext]  # 最近 N 条消息
    oldest_cursor: Optional[str]  # 用于分页加载
    last_updated: datetime
```

#### 内存窗口控制

```python
class SessionCacheService:
    def __init__(self, max_context_size: int = 100):
        self._max_context_size = max_context_size  # 默认保留最近 100 条
    
    async def append_message(self, conversation_id: str, message: MessageContext):
        """追加消息，控制内存窗口"""
        context = await self.get_context(conversation_id)
        context.messages.append(message)
        
        # 超过窗口大小时，裁剪并记录游标
        if len(context.messages) > self._max_context_size:
            context.oldest_cursor = context.messages[0].id
            context.messages = context.messages[-self._max_context_size:]
```

### 冷启动机制

```python
async def get_context(self, conversation_id: str) -> ConversationContext:
    """获取会话上下文，如果内存中不存在，则从数据库冷启动"""
    if conversation_id not in self._active_sessions:
        self._active_sessions[conversation_id] = await self._load_from_db(
            conversation_id,
            limit=50  # 加载最近 50 条
        )
    return self._active_sessions[conversation_id]
```

### 缓存更新策略

| 操作 | 缓存更新时机 | 说明 |
|------|------------|------|
| **消息创建** | 推送到 Redis Streams 后立即更新 | 保证读取一致性 |
| **消息更新** | 推送到 Redis Streams 后立即更新 | 合并 usage 和 content |
| **消息查询** | 优先从缓存读取 | 缓存未命中时从数据库加载 |

---

## 分页加载机制

### 游标分页策略

#### 初始加载

```
GET /api/v1/conversations/{id}/messages?limit=50&order=desc
  ↓
从数据库查询最近 50 条消息
  ↓
返回 messages + has_more + next_cursor
```

#### 向上滚动加载

```
GET /api/v1/conversations/{id}/messages?limit=50&before_cursor={message_id}
  ↓
根据 before_cursor 查询更早的消息
  ↓
返回 messages + has_more + next_cursor
```

### 实现细节

```python
async def list_messages_before_cursor(
    session: AsyncSession,
    conversation_id: str,
    before_cursor: str,
    limit: int = 50
) -> List[Message]:
    """基于游标的分页查询"""
    # 1. 获取游标消息的创建时间
    cursor_msg = await session.get(Message, before_cursor)
    
    # 2. 查询更早的消息
    query = select(Message).where(
        Message.conversation_id == conversation_id,
        Message.created_at < cursor_msg.created_at
    ).order_by(Message.created_at.desc()).limit(limit + 1)
    
    # 3. 判断是否有更多
    messages = (await session.execute(query)).scalars().all()
    has_more = len(messages) > limit
    
    return messages[:limit] if has_more else messages
```

---

## API 接口设计

### 接口列表

| 方法 | 路径 | 描述 |
| :--- | :--- | :--- |
| `POST` | `/api/v1/conversations` | 创建新会话 |
| `GET` | `/api/v1/conversations` | 获取会话列表 |
| `GET` | `/api/v1/conversations/{id}` | 获取会话详情 |
| `DELETE` | `/api/v1/conversations/{id}` | 删除会话 |
| `POST` | `/api/v1/conversations/{id}/messages` | 发送消息（核心对话，SSE） |
| `GET` | `/api/v1/conversations/{id}/messages` | 分页获取历史消息 |

### 核心接口：发送消息（SSE）

**接口**: `POST /api/v1/conversations/{conversation_id}/messages`

**特性**：
- ✅ 流式响应（Server-Sent Events）
- ✅ 两阶段持久化（占位消息 + 完整更新）
- ✅ 异步写入（不阻塞响应）
- ✅ 内存缓存自动更新

**SSE 事件类型**：

| 事件类型 | 说明 | 数据格式 |
|---------|------|---------|
| `message_start` | 消息开始 | `{"message_id": "...", "model": "..."}` |
| `content_start` | 内容块开始 | `{"index": 0, "type": "text"}` |
| `content_delta` | 内容增量 | `{"index": 0, "delta": "..."}` |
| `content_stop` | 内容块结束 | `{"index": 0}` |
| `message_stop` | 消息结束 | `{"message_id": "...", "status": "completed"}` |
| `usage` | 计费信息 | `{"prompt_tokens": ..., "total_price": ...}` |

### 核心接口：分页获取历史消息

**接口**: `GET /api/v1/conversations/{conversation_id}/messages`

**查询参数**：

| 参数 | 类型 | 说明 |
|------|------|------|
| `limit` | `integer` | 每页数量（默认：50，最大：200） |
| `offset` | `integer` | 偏移量（默认：0，当 `before_cursor` 为 None 时使用） |
| `order` | `string` | 排序方式：`asc`（时间正序）/ `desc`（时间倒序） |
| `before_cursor` | `string` | 游标（message_id），用于分页加载更早的消息 |

**分页策略**：
- **初始加载**：不传 `before_cursor`，使用 `offset` 分页
- **向上滚动加载**：传 `before_cursor`，获取更早的消息

---

## 性能优化

### 优化策略

#### 1. 合并写入优化

**优化前**：
```
Step 1: accumulate_usage() → 推送 usage 到 message_update_stream
Step 2: _finalize_message() → 推送 stream.phase 到 message_update_stream
结果：两次数据库 UPDATE 操作
```

**优化后**：
```
Step 1: accumulate_usage() → 累积到内存（不推送）
Step 2: _finalize_message() → 合并 usage + stream.phase，一次性推送
结果：一次数据库 UPDATE 操作（减少 50%）
```

**性能提升**：
- ✅ 数据库写入减少 50%
- ✅ 网络请求减少 50%
- ✅ 数据一致性提升（原子性写入）

#### 2. JSONB 直接使用

**优化前**：
```python
# 需要手动序列化/反序列化
metadata_json = json.dumps(metadata)
msg.extra_data = json.loads(metadata_json)
```

**优化后**：
```python
# 直接读写 dict
msg._metadata = metadata  # SQLAlchemy 自动处理
metadata = msg._metadata  # 直接返回 dict
```

**优势**：
- ✅ 代码更简洁
- ✅ 性能更好（无需序列化开销）
- ✅ PostgreSQL 自动优化查询

#### 3. 复合索引优化

```sql
-- 消息表复合索引（分页查询必需）
CREATE INDEX idx_messages_conv_created 
ON messages(conversation_id, created_at ASC);

-- 对话表复合索引（对话列表查询优化）
CREATE INDEX idx_conversations_user_updated 
ON conversations(user_id, updated_at DESC);

-- 消息表 status 索引（查询流式消息）
CREATE INDEX idx_messages_status 
ON messages(status) WHERE status = 'streaming';
```

**性能提升**：
- ✅ 分页查询性能提升 10-100x
- ✅ 对话列表查询优化
- ✅ 流式消息查询优化

---

## 可靠性保障

### 故障场景与保障机制

| 故障场景 | 保障机制 | 实现位置 |
|---------|---------|---------|
| **流式过程中服务崩溃** | 数据库中已存在 `status='streaming'` 的占位消息 | `chat_service.py:441-449` |
| **应用服务器崩溃** | 内存上下文丢失，但消息已进入 Redis Streams | `infra/message_queue/streams.py` |
| **Worker 崩溃** | Redis Streams 消费者组机制，未 ACK 消息重新分配 | `infra/message_queue/workers.py` |
| **Redis 崩溃** | 启用 Redis AOF 持久化，重启后恢复 Streams | Redis 配置 |
| **PostgreSQL 崩溃** | Worker 暂停消费，消息积压在 Redis Streams | `workers.py` |

### 数据一致性

#### 最终一致性模型

```
API 层写入 → Redis Streams → Workers → PostgreSQL
     ↓
SessionCacheService (内存缓存)
     ↓
读取时优先从缓存，缓存未命中时从数据库回源
```

**一致性保证**：
- ✅ 写入路径：Redis Streams 保证消息不丢失
- ✅ 读取路径：内存缓存 + 数据库回源，保证数据可用
- ✅ 会话粘性：保证同一会话在同一服务器，避免缓存不一致

---

## 部署与运维

### 部署环境区分

系统支持两种部署环境，通过 `DEPLOYMENT_ENV` 环境变量控制：

| 环境类型 | 环境变量值 | 用途 | Redis 配置 | PostgreSQL 配置 |
|---------|----------|------|-----------|---------------|
| **本地测试环境** | `local` 或 `development` | 本地开发、功能验证 | 本地 Redis (`redis://localhost:6379/0`) | AWS RDS（共享） |
| **AWS 生产部署环境** | `aws` 或 `production` | 生产环境部署 | AWS MemoryDB（带 TLS，需 VPN） | AWS RDS（共享） |

#### 本地测试环境

**特点**：
- ✅ 无需 VPN，可直接连接本地 Redis
- ✅ 适合本地开发和功能验证
- ✅ 快速启动，无网络延迟

**配置方式**：
```bash
export DEPLOYMENT_ENV=local
# 或
export DEPLOYMENT_ENV=development
```

**Redis 连接**：
```
redis://localhost:6379/0
```

#### AWS 生产部署环境

**特点**：
- ⚠️ **需要 VPN 连接**才能访问 AWS MemoryDB
- ✅ 生产环境部署，高可用性
- ✅ 支持 TLS 加密连接

**配置方式**：
```bash
export DEPLOYMENT_ENV=aws
# 或
export DEPLOYMENT_ENV=production
```

**Redis 连接（AWS MemoryDB）**：
```
rediss://agentuser:****@clustercfg.zen0-backend-staging-memorydb.w9tdej.memorydb.ap-southeast-1.amazonaws.com:6379
```

**⚠️ VPN 访问要求**：
- AWS MemoryDB 位于 AWS VPC 内部，**必须通过 VPN 连接**才能访问
- 访问地址：https://ap-southeast-2.console.aws.amazon.com/memorydb/home?region=ap-southeast-2#/
- 如果连接失败，请检查：
  1. VPN 连接状态
  2. MemoryDB 安全组配置（允许来源 IP/安全组）
  3. 网络路由配置

### 部署架构

#### 本地测试环境架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    本地测试环境部署架构                                   │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  应用服务器 (本地开发)                                                    │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │  FastAPI Server                                                  │   │
│  │  ├─ SessionCacheService (内存缓存)                               │   │
│  │  └─ ChatService / ConversationService                            │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                       ↓                                                   │
│  消息队列层 (本地 Redis)                                                  │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │  Redis (localhost:6379)                                          │   │
│  │  ├─ message_create_stream                                        │   │
│  │  └─ message_update_stream                                        │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                       ↓                                                   │
│  Workers 层 (本地后台进程)                                                │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │  InsertWorker / UpdateWorker (本地进程)                            │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                       ↓                                                   │
│  数据库层 (AWS RDS - 共享)                                                │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │  PostgreSQL (AWS RDS)                                             │   │
│  │  ├─ conversations 表                                               │   │
│  │  └─ messages 表                                                    │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

#### AWS 生产部署环境架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│                  AWS 生产部署环境架构                                      │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  负载均衡层 (Nginx/K8s Ingress)                                          │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │  一致性哈希路由 (基于 user_id 或 conversation_id)                │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                       ↓                                                   │
│  应用服务器层 (AWS ECS/EKS)                                               │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │  Server 1: SessionCacheService (内存缓存)                         │   │
│  │  Server 2: SessionCacheService (内存缓存)                         │   │
│  │  Server N: SessionCacheService (内存缓存)                         │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                       ↓                                                   │
│  ⚠️ VPN 连接 (必须)                                                      │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │  VPN Gateway → AWS VPC                                            │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                       ↓                                                   │
│  消息队列层 (AWS MemoryDB - VPC 内部)                                     │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │  MemoryDB Cluster (TLS 加密)                                      │   │
│  │  ├─ message_create_stream                                        │   │
│  │  └─ message_update_stream                                        │   │
│  │  Endpoint: clustercfg.zen0-backend-staging-memorydb...          │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                       ↓                                                   │
│  Workers 层 (AWS ECS Tasks)                                              │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │  InsertWorker × N (消费 message_create_stream)                     │   │
│  │  UpdateWorker × N (消费 message_update_stream)                     │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                       ↓                                                   │
│  数据库层 (AWS RDS)                                                      │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │  PostgreSQL (AWS RDS)                                             │   │
│  │  ├─ conversations 表                                               │   │
│  │  └─ messages 表                                                    │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

**关键区别**：
- ✅ **本地环境**：Redis 在本地，无需 VPN
- ⚠️ **AWS 环境**：MemoryDB 在 VPC 内部，**必须通过 VPN 连接**

### 启动 Workers

```bash
# 启动消息处理 Workers
python scripts/start_message_workers.py
```

**Workers 配置**：

```python
# 可配置参数
batch_size: int = 10        # 批量处理大小
block_time: int = 5000     # 阻塞等待时间（毫秒）
group_name: str = "insert_workers"  # 消费者组名称
```

### 监控指标

| 指标 | 说明 | 告警阈值 |
|------|------|---------|
| **Redis Streams 积压** | 待处理消息数量 | > 1000 |
| **Worker 处理延迟** | 消息从推送到处理完成的时间 | > 5s |
| **内存缓存命中率** | SessionCacheService 缓存命中率 | < 80% |
| **数据库连接池** | 活跃连接数 | > 80% |
| **VPN 连接状态** | AWS MemoryDB VPN 连接状态（仅 AWS 环境） | 断开 |

### 环境切换指南

#### 从本地切换到 AWS 环境

```bash
# 1. 建立 VPN 连接（必须）
# 连接到 AWS VPC

# 2. 设置环境变量
export DEPLOYMENT_ENV=aws

# 3. 验证连接
python tests/e2e_message_session/test_connectivity.py

# 4. 启动服务
python scripts/start_message_workers.py
```

#### 从 AWS 切换到本地环境

```bash
# 1. 设置环境变量
export DEPLOYMENT_ENV=local

# 2. 确保本地 Redis 已启动
redis-cli ping

# 3. 验证连接
python tests/e2e_message_session/test_connectivity.py

# 4. 启动服务
python scripts/start_message_workers.py
```

### 故障排查

#### AWS MemoryDB 连接失败

**常见原因**：
1. ❌ VPN 未连接或已断开
2. ❌ MemoryDB 安全组未允许来源 IP
3. ❌ 网络路由配置错误
4. ❌ TLS 证书配置错误

**排查步骤**：
```bash
# 1. 检查 VPN 连接
ping clustercfg.zen0-backend-staging-memorydb.w9tdej.memorydb.ap-southeast-1.amazonaws.com

# 2. 检查环境变量
echo $DEPLOYMENT_ENV  # 应该是 "aws" 或 "production"

# 3. 运行连接测试
DEPLOYMENT_ENV=aws python tests/e2e_message_session/test_connectivity.py

# 4. 查看详细日志
# 检查 infra/cache/redis.py 中的连接日志
```

**解决方案**：
- ✅ 建立 VPN 连接（参考 AWS 控制台：https://ap-southeast-2.console.aws.amazon.com/memorydb/home?region=ap-southeast-2#/）
- ✅ 检查 MemoryDB 安全组配置
- ✅ 验证 TLS 配置（`ssl_cert_reqs=ssl.CERT_NONE`，`ssl_check_hostname=False`）
- ✅ 如果 VPN 不可用，切换到本地环境：`export DEPLOYMENT_ENV=local`

---

## 实施状态

### 已完成功能

| 功能 | 状态 | 文件位置 |
|------|------|----------|
| **两阶段持久化** | ✅ 已完成 | `chat_service.py`, `broadcaster.py` |
| **Redis Streams 客户端** | ✅ 已完成 | `infra/message_queue/streams.py` |
| **InsertWorker** | ✅ 已完成 | `infra/message_queue/workers.py` |
| **UpdateWorker** | ✅ 已完成 | `infra/message_queue/workers.py` |
| **SessionCacheService** | ✅ 已完成 | `services/session_cache_service.py` |
| **游标分页** | ✅ 已完成 | `conversation_service.py`, `routers/conversation.py` |
| **合并写入优化** | ✅ 已完成 | `broadcaster.py:733-784` |
| **JSONB 直接使用** | ✅ 已完成 | `infra/database/models/message.py` |
| **数据库索引优化** | ✅ 已完成 | `scripts/add_message_indexes.sql` |
| **API 接口文档** | ✅ 已完成 | `docs/api/message-session-api-specification.md` |

### 验证状态

| 验证项 | 状态 | 说明 |
|--------|------|------|
| **流程验证** | ✅ 100% 符合 | 两阶段持久化流程完全对齐文档 |
| **数据库 Schema** | ✅ 完全符合 | 支持 status、JSONB、索引优化 |
| **内存缓存** | ✅ 完全符合 | SessionCacheService 实现完整 |
| **分页加载** | ✅ 完全符合 | 游标分页实现正确 |
| **合并写入** | ✅ 优化完成 | 减少 50% 数据库操作 |

---

## 相关文档

| 文档 | 说明 |
|------|------|
| [消息会话设计文档](../zenflux-message-session-design.md) | 完整设计文档 |
| [流程验证报告](../flow-verification-report.md) | 流程验证结果 |
| [API 接口规范](../api/message-session-api-specification.md) | API 接口文档 |
| [计费集成优化](../billing-integration-optimization.md) | 合并写入优化说明 |
| [数据库优化结果](../database-optimization-results.md) | 索引优化结果 |

---

**文档版本**: v1.0  
**最后更新**: 2026-01-19  
**维护者**: ZenFlux Agent Team
