# Session 管理与 SSE 重连机制

> 📅 **最后更新**: 2025-12-27  
> 🎯 **版本**: V1.0  
> 🔗 **相关文档**: [SSE 事件流协议](./03-SSE-EVENT-PROTOCOL.md) | [架构总览](./00-ARCHITECTURE-OVERVIEW.md)

---

## 📋 目录

- [核心问题](#核心问题)
- [设计目标](#设计目标)
- [架构设计](#架构设计)
- [数据结构](#数据结构)
- [API 接口](#api-接口)
- [工作流程](#工作流程)
- [实现细节](#实现细节)
- [错误处理](#错误处理)

---

## 🎯 核心问题

### 问题描述

在长时间运行的 Agent 任务中（如 PPT 生成、数据分析，可能运行 30 分钟），SSE 连接非常容易断开：

1. **用户刷新页面** → SSE 连接断开
2. **网络波动** → SSE 连接断开
3. **移动设备切换应用** → SSE 连接断开
4. **浏览器自动休眠** → SSE 连接断开

**问题**: SSE 断开后，Agent 还在后台运行，但用户看不到进度和结果。

### 核心需求

> **用户在任何时候刷新页面，都能重新连接到正在运行的 Agent，并看到实时进度和完整的事件流。**

---

## 🎨 设计目标

### 1. 用户体验目标

- ✅ **无感刷新**: 用户刷新页面后，自动恢复到正在运行的任务
- ✅ **断点续传**: 获取断线期间丢失的所有事件
- ✅ **状态可查**: 随时可以查询 Agent 运行状态和进度
- ✅ **多端同步**: 同一用户在不同设备/标签页都能看到同一任务

### 2. 技术目标

- ✅ **会话持久化**: Session 状态存储在 Redis，独立于 SSE 连接
- ✅ **事件缓冲**: 所有事件缓冲到 Redis，支持回放
- ✅ **自动清理**: 完成的 Session 自动过期，节省存储
- ✅ **并发支持**: 一个用户可以同时运行多个 Session

---

## 🏗️ 架构设计

### 核心概念

```
┌─────────────────────────────────────────────────────────────┐
│                        三层 ID 体系                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  user_id          → 用户标识（主键）                         │
│  ├── conversation_id  → 对话线程（数据库持久化）             │
│  │   └── message_id     → 单条消息（数据库持久化）           │
│  └── session_id       → Agent 运行会话（Redis 临时存储）     │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### ID 职责分离

| ID 类型 | 用途 | 生命周期 | 存储 | 示例 |
|---------|------|----------|------|------|
| `user_id` | 用户标识 | 永久 | Database | `user_001` |
| `conversation_id` | 对话线程 | 永久（或用户删除） | Database | `conv_abc123` |
| `message_id` | 单条消息 | 永久（属于 conversation） | Database | `msg_xyz789` |
| `session_id` | Agent 运行会话 | 运行期间 + 1 分钟 | Redis | `sess_20231224_120000_abc123` |

### 关系图

```
User (user_001)
├── Conversation (conv_001)  [Database]
│   ├── Message (msg_001)
│   ├── Message (msg_002)
│   └── Message (msg_003)
│
├── Conversation (conv_002)  [Database]
│   ├── Message (msg_004)
│   └── Message (msg_005)
│
├── Session (sess_abc)  [Redis, 关联 conv_001 + msg_003]
│   ├── status: running
│   ├── events: [event_1, event_2, ...]
│   └── heartbeat: 2秒前
│
└── Session (sess_def)  [Redis, 关联 conv_002 + msg_005]
    ├── status: running
    ├── events: [event_1, event_2, ...]
    └── heartbeat: 5秒前
```

### 核心设计原则

1. **Session 是临时的，Conversation 是持久的**
   - Session 只在 Agent 运行期间存在
   - 运行结束后，结果保存到 Conversation，Session 删除

2. **SSE 连接和 Session 解耦**
   - SSE 连接断开，Session 继续运行
   - 新的 SSE 连接可以重新订阅同一个 Session

3. **事件 ID 全局递增**
   - 每个事件有唯一的递增 ID
   - 支持 "从 ID N 开始" 的断点续传

4. **心跳机制**
   - Agent 每 30 秒更新心跳
   - 超过 60 秒无心跳，标记为 timeout

---

## 💾 数据结构

### Redis 键设计

```python
# 1. Session 状态
Key: session:{session_id}:status
Type: Hash
TTL: 运行中无 TTL，完成后 60 秒
Value: {
    "session_id": "sess_20231224_120000_abc123",
    "user_id": "user_001",
    "conversation_id": "conv_abc123",        # 关联的对话
    "message_id": "msg_xyz789",              # 关联的消息
    "status": "running",                     # running/completed/failed/timeout
    "last_event_id": 250,                    # 最后一个事件的 ID
    "start_time": "2023-12-24T12:00:00Z",
    "last_heartbeat": "2023-12-24T12:05:30Z",
    "progress": 0.6,                         # 进度 0-1
    "total_turns": 5,                        # 总轮次
    "message_preview": "帮我生成一个关于AI的PPT"  # 消息预览（前100字符）
}

# 2. 事件缓冲队列
Key: session:{session_id}:events
Type: List (左进右出，LPUSH + LTRIM)
TTL: 与 session:status 同步
Value: [
    '{"id": 1, "type": "session_start", "data": {...}, "timestamp": "..."}',
    '{"id": 2, "type": "thinking", "data": {...}, "timestamp": "..."}',
    ...
    '{"id": 250, "type": "content", "data": {...}, "timestamp": "..."}'
]
# 保留最近 1000 个事件，超出则删除旧的

# 3. 用户的活跃 Sessions
Key: user:{user_id}:sessions
Type: Set
TTL: 3600 秒（1小时）
Value: Set["sess_abc123", "sess_def456", ...]
# 用于快速查询用户所有运行中的 Session

# 4. Session 心跳
Key: session:{session_id}:heartbeat
Type: String (ISO 时间戳)
TTL: 60 秒
Value: "2023-12-24T12:05:30Z"
# Agent 每 30 秒更新一次，超过 60 秒未更新则认为超时

# 5. 全局事件 ID 计数器
Key: global:event_id_counter
Type: String (数字)
TTL: 永久
Value: "1234567"
# 使用 INCR 生成全局唯一、递增的事件 ID
```

### 数据库表结构（补充）

```sql
-- Conversations 表（已有，补充字段）
CREATE TABLE conversations (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    conversation_id TEXT UNIQUE NOT NULL,
    title TEXT DEFAULT '新对话',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata JSON,  -- 补充：存储最后的 session_id
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- metadata 示例：
{
    "last_session_id": "sess_abc123",
    "total_turns": 5,
    "total_messages": 10,
    "tags": ["ppt", "ai"]
}

-- Messages 表（已有，补充字段）
CREATE TABLE messages (
    id INTEGER PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    message_id TEXT UNIQUE NOT NULL,
    role TEXT NOT NULL,  -- user/assistant/system
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata JSON,  -- 补充：存储关联的 session_id
    FOREIGN KEY (conversation_id) REFERENCES conversations(conversation_id)
);

-- metadata 示例：
{
    "session_id": "sess_abc123",  -- 哪个 Session 生成的这条消息
    "turn": 3,
    "tokens_used": 1500,
    "tools_called": ["exa_search", "slidespeak_generate"]
}
```

---

## 🔌 API 接口

### 1. 创建聊天（修改现有接口）

**请求**:
```http
POST /api/v1/chat
Content-Type: application/json

{
  "message": "帮我生成一个关于AI的PPT",
  "message_id": "msg_xyz789",        # 可选，前端生成
  "user_id": "user_001",
  "conversation_id": "conv_abc123",  # 可选，新对话则不传
  "stream": false                    # false 时同步返回，不使用 SSE
}
```

**响应**:
```json
{
  "code": 200,
  "message": "success",
  "data": {
    "session_id": "sess_20231224_120000_abc123",
    "conversation_id": "conv_abc123",
    "message_id": "msg_xyz789",
    "stream_url": "/api/v1/chat/stream/sess_20231224_120000_abc123"
  }
}
```

**说明**:
- 返回 `session_id`，前端用于后续查询和重连
- 返回 `stream_url`，前端立即连接 SSE
- `conversation_id` 和 `message_id` 用于数据库关联

### 2. SSE 流式输出（新增 after_id 参数）

**请求**:
```http
GET /api/v1/chat/stream/{session_id}?after_id=100
Accept: text/event-stream
```

**参数**:
- `session_id`: Session ID（必填）
- `after_id`: 从哪个事件 ID 之后开始推送（可选，用于重连）

**响应**:
```
data: {"type": "session_start", "data": {...}, "timestamp": "...", "id": 1}

data: {"type": "thinking", "data": {...}, "timestamp": "...", "id": 2}

data: {"type": "content", "data": {...}, "timestamp": "...", "id": 3}

...

data: {"type": "done", "data": {}, "timestamp": "..."}
```

**说明**:
- 如果不传 `after_id`，从头开始推送所有缓冲的事件
- 如果传 `after_id=100`，只推送 id > 100 的事件
- 断线重连时，前端传入最后收到的 event_id

### 3. 查询 Session 状态（新增）

**请求**:
```http
GET /api/v1/session/{session_id}/status
```

**响应**:
```json
{
  "code": 200,
  "message": "success",
  "data": {
    "session_id": "sess_20231224_120000_abc123",
    "user_id": "user_001",
    "conversation_id": "conv_abc123",
    "message_id": "msg_xyz789",
    "status": "running",           # running/completed/failed/timeout
    "last_event_id": 250,
    "start_time": "2023-12-24T12:00:00Z",
    "last_heartbeat": "2023-12-24T12:05:30Z",
    "last_update": "2秒前",
    "progress": 0.6,
    "total_turns": 5,
    "message_preview": "帮我生成一个关于AI的PPT"
  }
}
```

**说明**:
- 用于检查 Agent 是否还在运行
- 前端刷新后，首先调用此接口判断是否需要重连

### 4. 获取历史事件（新增，用于断线补偿）

**请求**:
```http
GET /api/v1/session/{session_id}/events?after_id=100&limit=100
```

**参数**:
- `after_id`: 从哪个事件 ID 之后开始（必填）
- `limit`: 最多返回多少个事件（可选，默认 100）

**响应**:
```json
{
  "code": 200,
  "message": "success",
  "data": {
    "session_id": "sess_20231224_120000_abc123",
    "events": [
      {"id": 101, "type": "thinking", "data": {...}, "timestamp": "..."},
      {"id": 102, "type": "tool_call_start", "data": {...}, "timestamp": "..."},
      {"id": 103, "type": "tool_call_complete", "data": {...}, "timestamp": "..."},
      ...
      {"id": 150, "type": "content", "data": {...}, "timestamp": "..."}
    ],
    "total": 50,
    "has_more": false,
    "last_event_id": 150
  }
}
```

**说明**:
- 用于补偿断线期间丢失的事件
- 前端先调用此接口获取历史，再连接 SSE

### 5. 查询用户的活跃 Sessions（新增）

**请求**:
```http
GET /api/v1/user/{user_id}/sessions
```

**响应**:
```json
{
  "code": 200,
  "message": "success",
  "data": {
    "user_id": "user_001",
    "sessions": [
      {
        "session_id": "sess_abc123",
        "conversation_id": "conv_001",
        "message_id": "msg_001",
        "status": "running",
        "progress": 0.6,
        "start_time": "2023-12-24T12:00:00Z",
        "message_preview": "帮我生成一个关于AI的PPT"
      },
      {
        "session_id": "sess_def456",
        "conversation_id": "conv_002",
        "message_id": "msg_002",
        "status": "running",
        "progress": 0.3,
        "start_time": "2023-12-24T12:10:00Z",
        "message_preview": "分析这个数据集..."
      }
    ],
    "total": 2
  }
}
```

**说明**:
- 用于恢复用户的所有运行中任务
- 前端刷新时，如果没有保存 session_id，可以通过此接口找回

---

## 🔄 工作流程

### 场景 1：正常流程（无刷新）

```
1. 用户发送消息
   ↓
2. POST /api/v1/chat
   - 创建 conversation_id（如果是新对话）
   - 创建 message_id（保存用户消息到数据库）
   - 创建 session_id（Redis）
   - 启动 Agent 后台任务
   ↓
3. 返回 session_id 和 stream_url
   ↓
4. 前端连接 SSE
   GET /api/v1/chat/stream/{session_id}
   ↓
5. Agent 运行，实时推送事件
   - 每个事件生成全局递增的 event_id
   - 同时缓冲到 Redis
   - 通过 SSE 推送给前端
   ↓
6. Agent 完成
   - 发送 "complete" 事件
   - 保存结果到数据库（conversation + message）
   - Session 状态改为 "completed"
   - 设置 TTL = 60 秒
   ↓
7. 60 秒后，Redis 自动删除 Session 数据
```

### 场景 2：用户刷新页面（第 1 次）

```
Time: 10:00:00 - 用户发送消息，Agent 开始运行
      10:01:00 - 前端连接 SSE，接收事件 1-100
      10:02:00 - 用户刷新页面
                 ↓
                 SSE 连接断开 ❌
                 ↓
                 但 Agent 还在后台运行 ✅
                 产生事件 101-150，写入 Redis
      10:02:05 - 前端重新加载
                 ↓
1. 从 localStorage 读取 session_id
   ↓
2. GET /api/v1/session/{session_id}/status
   Response: {status: "running", last_event_id: 150}
   ↓
3. 判断：Agent 还在运行，需要重连
   ↓
4. GET /api/v1/session/{session_id}/events?after_id=100
   Response: {events: [101-150]}
   ↓
5. 前端渲染历史事件（101-150）
   ↓
6. 重新连接 SSE
   GET /api/v1/chat/stream/{session_id}?after_id=150
   ↓
7. 继续接收新事件（151+）
```

### 场景 3：用户疯狂刷新（第 2-N 次）

```
重复场景 2 的流程：
- 每次都查询 status
- 每次都获取丢失的事件
- 每次都重新连接 SSE

只要 Agent 还在运行，就能无限次重连 ✅
```

### 场景 4：Agent 完成后用户刷新

```
Time: 10:10:00 - Agent 完成
                 - Session 状态改为 "completed"
                 - TTL 设置为 60 秒
      10:10:30 - 用户刷新页面
                 ↓
1. GET /api/v1/session/{session_id}/status
   Response: {status: "completed", last_event_id: 500}
   ↓
2. 判断：Agent 已完成，不需要连接 SSE
   ↓
3. GET /api/v1/session/{session_id}/events?after_id=0
   Response: 所有事件（1-500）
   ↓
4. 前端渲染完整结果
   ↓
5. 或者，从数据库读取最终结果
   GET /api/v1/conversation/{conversation_id}/messages
```

### 场景 5：Session 超时（Agent 崩溃）

```
Time: 10:00:00 - Agent 开始运行
      10:01:00 - 心跳正常
      10:01:30 - 心跳正常
      10:02:00 - Agent 崩溃 💥
                 停止更新心跳
      10:03:00 - 心跳 TTL 过期（60秒）
                 ↓
                 后台任务检测到心跳过期
                 ↓
                 Session 状态改为 "timeout"
      10:03:30 - 用户刷新页面
                 ↓
1. GET /api/v1/session/{session_id}/status
   Response: {status: "timeout", last_event_id: 120}
   ↓
2. 前端显示：任务超时，建议重新发起
```

---

## 🔧 实现细节

### 1. Session 创建

```python
# services/chat_service.py

async def create_session(
    self,
    user_id: str,
    conversation_id: str,
    message_id: str,
    message: str
) -> str:
    """
    创建新的 Session
    
    Returns:
        session_id
    """
    # 1. 生成 session_id
    session_id = self._generate_session_id()
    
    # 2. 初始化 Session 状态
    session_status = {
        "session_id": session_id,
        "user_id": user_id,
        "conversation_id": conversation_id,
        "message_id": message_id,
        "status": "running",
        "last_event_id": 0,
        "start_time": datetime.now().isoformat(),
        "last_heartbeat": datetime.now().isoformat(),
        "progress": 0.0,
        "total_turns": 0,
        "message_preview": message[:100]
    }
    
    # 3. 保存到 Redis
    redis_client.hset(
        f"session:{session_id}:status",
        mapping=session_status
    )
    # 运行中不设置 TTL，完成后再设置
    
    # 4. 添加到用户的活跃 sessions
    redis_client.sadd(f"user:{user_id}:sessions", session_id)
    redis_client.expire(f"user:{user_id}:sessions", 3600)
    
    # 5. 初始化心跳
    redis_client.set(
        f"session:{session_id}:heartbeat",
        datetime.now().isoformat(),
        ex=60  # 60秒 TTL
    )
    
    logger.info(f"✅ Session 已创建: {session_id}")
    return session_id
```

### 2. 事件推送和缓冲

```python
# core/agent.py

async def emit_event(
    self,
    event_type: str,
    event_data: dict
) -> int:
    """
    发送事件（同时推送到 SSE 和缓冲到 Redis）
    
    Returns:
        event_id: 全局唯一的事件 ID
    """
    # 1. 生成全局递增的事件 ID
    event_id = redis_client.incr("global:event_id_counter")
    
    # 2. 构造事件对象
    event = {
        "id": event_id,
        "type": event_type,
        "data": event_data,
        "timestamp": datetime.now().isoformat()
    }
    
    # 3. 缓冲到 Redis（左进右出，保留最近 1000 个）
    redis_client.lpush(
        f"session:{self.session_id}:events",
        json.dumps(event)
    )
    redis_client.ltrim(
        f"session:{self.session_id}:events",
        0,
        999  # 保留最近 1000 个
    )
    
    # 4. 更新 Session 的 last_event_id
    redis_client.hset(
        f"session:{self.session_id}:status",
        "last_event_id",
        event_id
    )
    
    # 5. 推送到 SSE（通过 AsyncGenerator）
    yield event
    
    return event_id
```

### 3. 心跳更新

```python
# core/agent.py

async def update_heartbeat(self):
    """
    更新心跳（每 30 秒调用一次）
    """
    redis_client.set(
        f"session:{self.session_id}:heartbeat",
        datetime.now().isoformat(),
        ex=60  # 60秒 TTL
    )
    
    redis_client.hset(
        f"session:{self.session_id}:status",
        "last_heartbeat",
        datetime.now().isoformat()
    )
```

### 4. Session 完成

```python
# services/chat_service.py

async def complete_session(
    self,
    session_id: str,
    status: str = "completed"  # completed/failed
):
    """
    Session 完成或失败时调用
    """
    # 1. 更新状态
    redis_client.hset(
        f"session:{session_id}:status",
        mapping={
            "status": status,
            "last_heartbeat": datetime.now().isoformat()
        }
    )
    
    # 2. 设置 TTL = 60 秒（完成后保留 1 分钟）
    redis_client.expire(f"session:{session_id}:status", 60)
    redis_client.expire(f"session:{session_id}:events", 60)
    redis_client.expire(f"session:{session_id}:heartbeat", 60)
    
    # 3. 从用户的活跃 sessions 中移除
    user_id = redis_client.hget(f"session:{session_id}:status", "user_id")
    redis_client.srem(f"user:{user_id}:sessions", session_id)
    
    logger.info(f"✅ Session 已完成: {session_id}, status={status}")
```

### 5. SSE 重连处理

```python
# routers/chat.py

@router.get("/chat/stream/{session_id}")
async def stream_chat(
    session_id: str,
    after_id: Optional[int] = Query(None, description="从哪个事件 ID 之后开始")
):
    """
    SSE 流式输出（支持重连）
    """
    # 1. 检查 Session 是否存在
    session_status = redis_client.hgetall(f"session:{session_id}:status")
    if not session_status:
        raise HTTPException(404, "Session 不存在或已过期")
    
    async def event_generator():
        # 2. 如果指定了 after_id，先推送历史事件
        if after_id is not None:
            # 从 Redis 读取缓冲的事件
            events = redis_client.lrange(
                f"session:{session_id}:events",
                0,
                -1
            )
            # 反转（因为 LPUSH 是倒序的）
            events = reversed(events)
            
            # 过滤出 id > after_id 的事件
            for event_json in events:
                event = json.loads(event_json)
                if event["id"] > after_id:
                    yield f"data: {json.dumps(event)}\n\n"
        
        # 3. 继续推送实时事件
        # (Agent 通过 channel 发送新事件)
        async for event in agent_event_stream:
            yield f"data: {json.dumps(event)}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream"
    )
```

---

## ❌ 错误处理

### 1. Session 不存在

```python
GET /api/v1/session/{session_id}/status
→ 404: Session 不存在或已过期

原因：
- Session 已完成且超过 1 分钟
- Redis 数据丢失（服务重启）
- session_id 输入错误

处理：
- 前端提示：任务已完成或过期
- 建议从数据库读取历史记录
```

### 2. Session 超时

```python
GET /api/v1/session/{session_id}/status
→ 200: {status: "timeout", ...}

原因：
- Agent 崩溃
- 服务器重启
- 心跳停止更新超过 60 秒

处理：
- 前端提示：任务执行超时
- 建议重新发起请求
- 保留已完成的部分结果
```

### 3. 事件丢失（Redis 满了）

```python
# 如果 Redis 内存满了，LPUSH 会失败
# 需要配置 Redis maxmemory-policy

# redis.conf
maxmemory 2gb
maxmemory-policy allkeys-lru  # 自动淘汰旧数据

# 或者使用 volatile-lru（只淘汰有 TTL 的 key）
```

### 4. 并发限制

```python
# 限制每个用户最多同时运行 N 个 Session

async def check_user_session_limit(user_id: str, limit: int = 5):
    """检查用户的活跃 Session 数量"""
    active_sessions = redis_client.scard(f"user:{user_id}:sessions")
    
    if active_sessions >= limit:
        raise HTTPException(
            429,
            f"您已有 {active_sessions} 个任务在运行，请等待完成后再发起新任务"
        )
```

---

## 📊 监控和运维

### 1. 监控指标

```python
# 需要监控的关键指标

# Session 相关
- 活跃 Session 总数
- 每个用户的 Session 数量
- Session 平均运行时长
- Session 超时率

# 事件相关
- 事件生成速率（events/sec）
- 事件缓冲区大小
- 事件丢失率

# Redis 相关
- Redis 内存使用率
- Key 数量
- 过期 Key 清理速率
```

### 2. 定期清理任务

```python
# 后台任务：清理超时的 Session

async def cleanup_timeout_sessions():
    """
    每分钟运行一次，检查并清理超时的 Session
    """
    # 1. 获取所有用户
    user_keys = redis_client.keys("user:*:sessions")
    
    for user_key in user_keys:
        # 2. 获取该用户的所有 Session
        session_ids = redis_client.smembers(user_key)
        
        for session_id in session_ids:
            # 3. 检查心跳
            heartbeat = redis_client.get(f"session:{session_id}:heartbeat")
            
            if not heartbeat:
                # 心跳已过期（超过 60 秒）
                logger.warning(f"⚠️ Session 超时: {session_id}")
                
                # 标记为 timeout
                redis_client.hset(
                    f"session:{session_id}:status",
                    "status",
                    "timeout"
                )
                
                # 设置 TTL（1 分钟后删除）
                redis_client.expire(f"session:{session_id}:status", 60)
                redis_client.expire(f"session:{session_id}:events", 60)
                
                # 从用户活跃列表移除
                user_id = redis_client.hget(
                    f"session:{session_id}:status",
                    "user_id"
                )
                redis_client.srem(f"user:{user_id}:sessions", session_id)
```

---

## 🚀 前端集成示例

### 1. 发送消息并连接 SSE

```javascript
// 1. 发送消息
const response = await fetch('/api/v1/chat', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({
    message: '帮我生成一个关于AI的PPT',
    user_id: 'user_001',
    conversation_id: 'conv_abc123',
    stream: false
  })
});

const {data} = await response.json();
const {session_id, stream_url} = data;

// 2. 保存到 localStorage（用于刷新后恢复）
localStorage.setItem('current_session_id', session_id);
localStorage.setItem('last_event_id', '0');

// 3. 连接 SSE
const eventSource = new EventSource(stream_url);
let lastEventId = 0;

eventSource.onmessage = (event) => {
  const data = JSON.parse(event.data);
  
  // 保存最后的 event_id
  if (data.id) {
    lastEventId = data.id;
    localStorage.setItem('last_event_id', lastEventId);
  }
  
  // 渲染事件
  renderEvent(data);
};

eventSource.onerror = () => {
  console.log('SSE 连接断开，尝试重连...');
  reconnect(session_id, lastEventId);
};
```

### 2. 页面刷新后恢复

```javascript
// 页面加载时执行

async function restoreSession() {
  // 1. 从 localStorage 读取
  const session_id = localStorage.getItem('current_session_id');
  if (!session_id) return;
  
  const lastEventId = parseInt(localStorage.getItem('last_event_id') || '0');
  
  // 2. 查询 Session 状态
  const statusRes = await fetch(`/api/v1/session/${session_id}/status`);
  if (!statusRes.ok) {
    // Session 不存在或已过期
    localStorage.removeItem('current_session_id');
    return;
  }
  
  const {data: status} = await statusRes.json();
  
  // 3. 根据状态决定下一步
  if (status.status === 'completed' || status.status === 'failed') {
    // 已完成，获取所有事件并渲染
    await loadCompletedSession(session_id);
    localStorage.removeItem('current_session_id');
    return;
  }
  
  if (status.status === 'timeout') {
    // 超时，提示用户
    alert('任务执行超时，请重新发起');
    localStorage.removeItem('current_session_id');
    return;
  }
  
  // 4. 还在运行，获取丢失的事件
  if (status.last_event_id > lastEventId) {
    const eventsRes = await fetch(
      `/api/v1/session/${session_id}/events?after_id=${lastEventId}`
    );
    const {data: eventsData} = await eventsRes.json();
    
    // 渲染历史事件
    eventsData.events.forEach(renderEvent);
  }
  
  // 5. 重新连接 SSE
  reconnect(session_id, status.last_event_id);
}

function reconnect(session_id, after_id) {
  const url = `/api/v1/chat/stream/${session_id}?after_id=${after_id}`;
  const eventSource = new EventSource(url);
  
  eventSource.onmessage = (event) => {
    const data = JSON.parse(event.data);
    
    if (data.id) {
      localStorage.setItem('last_event_id', data.id);
    }
    
    renderEvent(data);
  };
}

// 页面加载时自动恢复
restoreSession();
```

---

## 🎯 总结

### 核心优势

1. ✅ **用户体验无缝**: 随便刷新，任务继续运行
2. ✅ **断点续传**: 不丢失任何事件
3. ✅ **状态可查**: 随时知道 Agent 在做什么
4. ✅ **自动清理**: 不占用过多存储
5. ✅ **并发支持**: 支持多任务同时运行

### 实现成本

- **Redis**: 需要足够的内存（建议 2GB+）
- **代码改动**: 中等（新增 3 个接口 + 事件缓冲逻辑）
- **测试**: 需要重点测试断线重连场景

### 后续优化

1. **事件压缩**: 对于大量事件，可以考虑压缩存储
2. **持久化**: 对于关键事件，可以同时写入数据库
3. **集群部署**: 使用 Redis Cluster 或 Sentinel 提高可用性
4. **事件回放**: 支持完整的事件回放功能

---

**📖 相关文档**:
- [SSE 事件流协议](./03-SSE-EVENT-PROTOCOL.md)
- [架构总览](./00-ARCHITECTURE-OVERVIEW.md)
- [数据库设计](./DATABASE.md)

