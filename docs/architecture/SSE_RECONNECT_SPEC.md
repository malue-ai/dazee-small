# SSE 断点重连规范

> 本文档详细描述 ZenFlux Agent 的 SSE 断点重连机制，包括架构设计、接口规范、实现细节和最佳实践。

## 目录

- [架构概览](#架构概览)
- [核心组件](#核心组件)
- [接口规范](#接口规范)
- [事件存储机制](#事件存储机制)
- [重连流程](#重连流程)
- [前端实现](#前端实现)
- [错误处理](#错误处理)
- [最佳实践](#最佳实践)

---

## 架构概览

### 整体架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              前端 (Vue/Pinia)                            │
│  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐     │
│  │   ChatStore     │    │   ChatView      │    │   SSE Client    │     │
│  │  - sessionId    │    │  - 重连弹窗     │    │  - lastEventId  │     │
│  │  - lastEventId  │    │  - 状态恢复     │    │  - 指数退避     │     │
│  └─────────────────┘    └─────────────────┘    └─────────────────┘     │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ HTTP/SSE
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                           后端 (FastAPI)                                 │
│  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐     │
│  │  chat.py        │    │  session_service│    │  redis_manager  │     │
│  │  - POST /chat   │    │  - 状态管理     │    │  - 事件存储     │     │
│  │  - GET /chat/   │    │  - 事件查询     │    │  - Pub/Sub      │     │
│  │    {session_id} │    │                 │    │                 │     │
│  └─────────────────┘    └─────────────────┘    └─────────────────┘     │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ Redis Protocol
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                              Redis                                       │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  session:{session_id}:events   → List (事件持久存储)             │   │
│  │  session:{session_id}:seq      → Counter (seq 原子递增)          │   │
│  │  session:{session_id}:stream   → Pub/Sub Channel (实时推送)      │   │
│  │  session:{session_id}          → Hash (Session 状态)             │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

### 设计目标

| 目标 | 实现方式 |
|------|----------|
| **不丢事件** | 所有事件存入 Redis List，支持按 seq 回溯 |
| **低延迟** | 使用 Redis Pub/Sub 实时推送 |
| **无感重连** | 前端自动重连 + 事件补偿，用户无感知 |
| **可扩展** | 水平扩展：多实例共享 Redis |

---

## 核心组件

### 1. Redis Manager (`services/redis_manager.py`)

负责事件的存储、检索和实时推送。

**关键方法：**

```python
async def buffer_event(self, session_id: str, event_data: dict) -> dict:
    """
    缓冲事件到 Redis 并通过 Pub/Sub 发布
    
    处理流程：
    1. 生成 seq（Redis INCR，原子操作）
    2. 存入 Redis List
    3. 通过 Pub/Sub 发布
    """

async def get_events(self, session_id: str, after_id: int, limit: int) -> list:
    """
    获取事件列表（用于断线补偿）
    """

async def subscribe_events(self, session_id: str, after_id: int, timeout: int):
    """
    使用 Pub/Sub 订阅实时事件流
    
    相比轮询的优势：
    - 延迟更低（毫秒级 vs 100ms）
    - 资源消耗更少（无空轮询）
    """
```

### 2. Session Service (`services/session_service.py`)

管理 Session 生命周期和状态。

**关键方法：**

```python
async def create_session(self, user_id: str, message: list, conversation_id: str) -> str:
    """创建 Session，返回 session_id"""

async def get_session_status(self, session_id: str) -> dict:
    """获取 Session 状态（用于重连前判断）"""

async def get_session_events(self, session_id: str, after_id: int, limit: int) -> list:
    """获取 Session 事件列表（用于断线重连）"""

async def stop_session(self, session_id: str) -> dict:
    """停止正在运行的 Session（用户主动中断）"""
```

### 3. Event Broadcaster (`core/events/broadcaster.py`)

事件广播器，管理内容累积和持久化。

**持久化策略：**

```python
class PersistenceStrategy(str, Enum):
    REALTIME = "realtime"   # 每个 content_stop 都 checkpoint（断点恢复能力强）
    DEFERRED = "deferred"   # 只在 message_stop 时保存（减少 DB 写入）
```

---

## 接口规范

### 接口总览

| 接口 | 方法 | 路径 | 功能 |
|------|------|------|------|
| 聊天入口 | POST | `/api/v1/chat` | 发起聊天，建立 SSE 连接 |
| SSE 重连 | GET | `/api/v1/chat/{session_id}` | 断线后重新连接 SSE 流 |
| Session 状态 | GET | `/api/v1/session/{session_id}/status` | 查询 Session 是否还在运行 |
| 获取事件 | GET | `/api/v1/session/{session_id}/events` | 获取丢失的事件 |
| 用户 Sessions | GET | `/api/v1/user/{user_id}/sessions` | 获取用户所有活跃 Session |
| 停止 Session | POST | `/api/v1/session/{session_id}/stop` | 主动停止运行中的 Session |

---

### 1. POST /api/v1/chat

**功能**：发起聊天，建立 SSE 连接

**请求参数：**

```json
{
  "message": "用户消息内容",
  "user_id": "user_001",           // 必填
  "message_id": "msg_xxx",          // 可选，前端生成
  "conversation_id": "conv_xxx",    // 可选，多轮对话用
  "agent_id": "dazee_agent",        // 可选，指定 Agent
  "stream": true,                   // 默认 true
  "variables": {},                  // 前端上下文变量
  "files": []                       // 文件引用
}
```

**Query 参数：**

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `format` | `zeno` | 事件格式：`zeno`（标准规范）或 `zenflux`（原始格式） |

**返回（流式模式）：**

```
data: {"type":"message_start","seq":1,"session_id":"sess_xxx","conversation_id":"conv_xxx"}

data: {"type":"content_start","seq":2,"content_type":"text"}

data: {"type":"content_delta","seq":3,"delta":{"type":"text","text":"你好"}}

data: {"type":"content_stop","seq":4}

data: {"type":"message_stop","seq":5,"usage":{"input_tokens":100,"output_tokens":50}}
```

---

### 2. GET /api/v1/chat/{session_id}

**功能**：断线后重新连接 SSE 流（**核心重连接口**）

**路径参数：**

| 参数 | 说明 |
|------|------|
| `session_id` | 要重连的 Session ID |

**Query 参数：**

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `after_seq` | `null` | 从哪个序号之后开始（断点位置） |
| `format` | `zeno` | 事件格式 |

**返回状态码：**

| 状态码 | 含义 |
|--------|------|
| `200` | 成功，返回 SSE 流 |
| `404` | Session 不存在 |
| `410 Gone` | Session 已结束 |

**返回流程：**

```
1️⃣ 首先发送 reconnect_info 事件（重连上下文）
   ↓
2️⃣ 推送历史事件（after_seq 之后的所有事件）
   ↓
3️⃣ 订阅实时事件流（继续接收新产生的事件）
   ↓
4️⃣ 发送 done 事件表示结束
```

**SSE 输出示例：**

```
event: reconnect_info
data: {"type":"reconnect_info","data":{"session_id":"sess_xxx","conversation_id":"conv_xxx","last_event_seq":123,"status":"running"}}

data: {"type":"content_delta","seq":124,"delta":{"type":"text","text":"继续"}}

data: {"type":"content_delta","seq":125,"delta":{"type":"text","text":"输出"}}

data: {"type":"message_stop","seq":126}

event: done
data: {}
```

---

### 3. GET /api/v1/session/{session_id}/status

**功能**：查询 Session 状态（重连前先调用此接口判断）

**返回示例：**

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "session_id": "sess_20240115_143022_abc123",
    "user_id": "user_001",
    "conversation_id": "conv_xyz",
    "status": "running",
    "last_event_seq": 250,
    "start_time": "2024-01-15T14:30:22Z",
    "message_preview": "请帮我分析这个数据..."
  }
}
```

**状态说明：**

| 状态 | 含义 | 是否可重连 |
|------|------|-----------|
| `running` | 正在执行 | ✅ 是 |
| `completed` | 已完成 | ❌ 否 |
| `failed` | 执行失败 | ❌ 否 |
| `timeout` | 超时 | ❌ 否 |
| `stopped` | 用户停止 | ❌ 否 |

---

### 4. GET /api/v1/session/{session_id}/events

**功能**：获取指定 Session 的事件列表（断线补偿）

**Query 参数：**

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `after_id` | `null` | 从哪个事件 ID 之后开始 |
| `limit` | `100` | 最多返回多少个事件（最大 1000） |

**返回示例：**

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "session_id": "sess_xxx",
    "events": [
      {"type": "content_delta", "seq": 101, "delta": {"type": "text", "text": "你好"}},
      {"type": "content_delta", "seq": 102, "delta": {"type": "text", "text": "世界"}},
      {"type": "content_stop", "seq": 103}
    ],
    "total": 3,
    "has_more": false,
    "last_event_id": 103
  }
}
```

---

### 5. GET /api/v1/user/{user_id}/sessions

**功能**：获取用户所有活跃 Session（用于显示重连提示）

**返回示例：**

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "user_id": "user_001",
    "sessions": [
      {
        "session_id": "sess_20240115_143022_abc123",
        "conversation_id": "conv_xyz",
        "status": "running",
        "start_time": "2024-01-15T14:30:22Z",
        "message_preview": "请帮我分析这个数据..."
      }
    ],
    "total": 1
  }
}
```

---

### 6. POST /api/v1/session/{session_id}/stop

**功能**：主动停止运行中的 Session

**返回示例：**

```json
{
  "code": 200,
  "message": "Session 已停止",
  "data": {
    "session_id": "sess_xxx",
    "status": "stopped",
    "stopped_at": "2024-01-15T14:35:00Z"
  }
}
```

**行为：**

1. 在 Redis 中设置停止标志
2. Agent 执行循环检测到标志并优雅停止
3. 发送 `session_stopped` 事件通知前端
4. 保存已生成的部分内容到数据库

---

## 事件存储机制

### Redis 数据结构

```
session:{session_id}          → Hash    (Session 元数据)
session:{session_id}:events   → List    (事件持久存储，LPUSH)
session:{session_id}:seq      → String  (seq 原子计数器)
session:{session_id}:stream   → Channel (Pub/Sub 实时推送)
```

### 事件存储流程

```python
async def buffer_event(self, session_id: str, event_data: dict) -> dict:
    # 1. 生成 seq（Redis INCR，原子操作）
    seq_key = f"session:{session_id}:seq"
    seq = await client.incr(seq_key)
    event["seq"] = seq
    
    # 2. 存入 Redis List（LPUSH，最新的在前面）
    await client.lpush(f"session:{session_id}:events", event_json)
    
    # 3. 通过 Pub/Sub 发布（实时推送）
    channel = f"session:{session_id}:stream"
    await client.publish(channel, event_json)
    
    # 4. 更新 Session 的 last_event_seq
    await self.update_session_status(session_id, last_event_seq=seq)
    
    return event
```

### 事件订阅流程

```python
async def subscribe_events(self, session_id: str, after_id: int, timeout: int):
    # 1. 先读取积压的事件（断线补偿）
    if after_id is not None:
        backlog_events = await self.get_events(session_id, after_id, limit=1000)
        for event in backlog_events:
            yield event
    
    # 2. 订阅 Pub/Sub 频道（实时推送）
    pubsub = client.pubsub()
    await pubsub.subscribe(f"session:{session_id}:stream")
    
    # 3. 监听新事件
    async for message in pubsub.listen():
        if message["type"] == "message":
            event = json.loads(message["data"])
            yield event
```

---

## 重连流程

### 完整时序图

```
┌────────────────┐          ┌────────────────┐          ┌────────────────┐
│    前端         │          │    后端         │          │    Redis       │
└───────┬────────┘          └───────┬────────┘          └───────┬────────┘
        │                           │                           │
        │  ══════ 用户断线/刷新 ══════                           │
        │                           │                           │
        │  GET /user/{id}/sessions  │                           │
        │ ─────────────────────────>│                           │
        │                           │  SMEMBERS user:sessions   │
        │                           │ ─────────────────────────>│
        │                           │<─────────────────────────│
        │<─────────────────────────│                           │
        │  [活跃 Session 列表]      │                           │
        │                           │                           │
        │  GET /session/{id}/status │                           │
        │ ─────────────────────────>│                           │
        │                           │  HGETALL session:{id}     │
        │                           │ ─────────────────────────>│
        │                           │<─────────────────────────│
        │<─────────────────────────│                           │
        │  {status: "running"}      │                           │
        │                           │                           │
        │  GET /chat/{id}?after_seq │                           │
        │ ─────────────────────────>│                           │
        │                           │                           │
        │  SSE: reconnect_info      │                           │
        │<─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─│                           │
        │                           │  LRANGE events (历史)     │
        │                           │ ─────────────────────────>│
        │                           │<─────────────────────────│
        │  SSE: 历史事件...          │                           │
        │<─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─│                           │
        │                           │  SUBSCRIBE stream (实时)  │
        │                           │ ─────────────────────────>│
        │                           │                           │
        │  SSE: 实时事件...          │  PUBLISH (Agent 产生)     │
        │<─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─│<─────────────────────────│
        │                           │                           │
        │  SSE: done                │                           │
        │<─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─│                           │
        │                           │                           │
```

### 前端重连逻辑

```javascript
async _handleSSEReconnect(onEvent, resolve, reject) {
    // 1️⃣ 检查是否有 session_id
    if (!this.sessionId) {
        reject(new Error('无法重连：缺少 session_id'))
        return
    }
    
    // 2️⃣ 检查重连次数（最大重试限制）
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
        reject(new Error('达到最大重连次数'))
        return
    }
    
    this.reconnectAttempts++
    
    // 3️⃣ 指数退避延迟（1s, 2s, 4s, 8s... 最大 10s）
    const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts - 1), 10000)
    await new Promise(r => setTimeout(r, delay))
    
    // 4️⃣ 检查 Session 状态
    const sessionStatus = await this.getSessionStatus(this.sessionId)
    if (['completed', 'failed'].includes(sessionStatus.status)) {
        resolve('')  // 已完成，不需要重连
        return
    }
    
    // 5️⃣ 建立重连（带上 after_seq 参数）
    const reconnectUrl = `/api/v1/chat/${this.sessionId}?after_seq=${this.lastEventId}&format=zenflux`
    const response = await fetch(reconnectUrl, {
        method: 'GET',
        headers: { 'Accept': 'text/event-stream' }
    })
    
    // 6️⃣ 处理 SSE 流...
}
```

---

## 错误处理

### 错误码定义

| 错误码 | HTTP 状态 | 含义 |
|--------|-----------|------|
| `SESSION_NOT_FOUND` | 404 | Session 不存在或已过期 |
| `AGENT_NOT_FOUND` | 400 | 指定的 Agent 不存在 |
| `AGENT_ERROR` | 500 | Agent 执行失败 |
| `EXTERNAL_SERVICE_ERROR` | 503 | 外部服务不可用 |
| `INTERNAL_ERROR` | 500 | 内部错误 |

### SSE 错误事件格式

```json
{
  "type": "message.assistant.error",
  "message_id": "msg_xxx",
  "timestamp": 1705312200000,
  "error": {
    "type": "business",
    "code": "AGENT_ERROR",
    "message": "对话处理失败，请稍后重试",
    "retryable": true
  }
}
```

### 前端错误处理策略

| 错误类型 | 处理方式 |
|----------|----------|
| 网络断开 | 自动重连（指数退避） |
| 410 Gone | Session 已结束，从数据库加载历史 |
| 404 | Session 不存在，停止重连 |
| 达到最大重连次数 | 提示用户手动刷新 |

---

## 最佳实践

### 前端

1. **保存 lastEventId**：每收到一个事件，更新 `lastEventId`
2. **指数退避**：重连间隔 1s → 2s → 4s → 8s → 10s（上限）
3. **最大重试次数**：建议 5 次
4. **状态检查**：重连前先调用 `/session/{id}/status` 判断是否需要重连
5. **用户提示**：显示重连状态，让用户知道正在恢复

### 后端

1. **事件持久化**：所有事件存入 Redis List，保留足够长时间
2. **原子 seq**：使用 Redis INCR 保证 seq 唯一递增
3. **Pub/Sub + 轮询**：Pub/Sub 为主，轮询作为备选
4. **超时设置**：合理设置 Session 超时（默认 30 分钟）
5. **清理策略**：Session 完成后设置 TTL 自动过期

### Redis

1. **事件 TTL**：Session 完成后 1 小时自动过期
2. **事件数量限制**：超过 10000 条时截断（防止内存爆炸）
3. **Pub/Sub 超时**：监听 30 分钟后自动断开

---

## 相关文件

| 文件 | 功能 |
|------|------|
| `routers/chat.py` | 后端 API 路由，重连接口实现 |
| `services/session_service.py` | Session 状态管理 |
| `services/redis_manager.py` | Redis 事件存储和订阅 |
| `core/events/broadcaster.py` | 事件广播和持久化 |
| `frontend/src/stores/chat.js` | 前端 SSE 重连逻辑 |
| `frontend/src/views/chat/ChatView.vue` | 前端重连 UI |

---

## 更新日志

| 版本 | 日期 | 变更 |
|------|------|------|
| v1.0 | 2024-01-15 | 初始版本 |
