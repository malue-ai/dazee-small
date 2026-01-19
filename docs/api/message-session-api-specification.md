# ZenFlux Agent 消息会话管理 API 规范

> **版本**: v1.0  
> **更新时间**: 2026-01-19  
> **基础 URL**: `/api/v1`  
> **协议**: HTTP/HTTPS  
> **认证**: Bearer Token（可选）

---

## 目录

1. [概述](#概述)
2. [数据模型](#数据模型)
3. [接口列表](#接口列表)
4. [接口详情](#接口详情)
5. [错误处理](#错误处理)
6. [使用示例](#使用示例)
7. [最佳实践](#最佳实践)

---

## 概述

ZenFlux Agent 消息会话管理 API 提供了一套完整的对话和消息管理接口，支持：

- ✅ **对话 CRUD**：创建、查询、更新、删除对话
- ✅ **消息管理**：发送消息（流式响应）、分页查询历史消息
- ✅ **异步持久化**：基于 Redis Streams 的两阶段持久化机制
- ✅ **内存缓存**：支持会话粘性，实现低延迟读取
- ✅ **分页加载**：基于游标的分页，支持长会话

### 核心特性

1. **两阶段持久化**：流式消息采用占位消息 + 完整更新的两阶段机制
2. **异步写入**：所有消息写入通过 Redis Streams 异步处理，不阻塞 API 响应
3. **内存缓存**：活跃会话上下文缓存在内存中，实现纳秒级访问
4. **游标分页**：支持 `before_cursor` 参数，高效加载历史消息

---

## 数据模型

### 1. Conversation（对话）

```json
{
  "id": "conv_abc123",
  "user_id": "user_001",
  "title": "讨论Python编程",
  "status": "active",
  "created_at": "2024-01-01T12:00:00Z",
  "updated_at": "2024-01-01T15:30:00Z",
  "metadata": {
    "message_count": 50,
    "last_message_at": "2024-01-01T15:30:00Z"
  }
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | `string` | 对话唯一 ID（ULID） |
| `user_id` | `string` | 用户 ID |
| `title` | `string` | 对话标题 |
| `status` | `string` | 对话状态：`active` / `archived` / `deleted` |
| `created_at` | `datetime` | 创建时间（ISO 8601） |
| `updated_at` | `datetime` | 更新时间（ISO 8601） |
| `metadata` | `object` | 对话元数据（JSONB） |

### 2. Message（消息）

```json
{
  "id": "msg_xyz789",
  "conversation_id": "conv_abc123",
  "role": "assistant",
  "content": "[{\"type\": \"text\", \"text\": \"你好！有什么可以帮助你的吗？\"}]",
  "status": "completed",
  "created_at": "2024-01-01T12:00:00Z",
  "metadata": {
    "stream": {
      "phase": "final",
      "chunk_count": 5
    },
    "usage": {
      "prompt_tokens": 1234,
      "completion_tokens": 567,
      "total_tokens": 1801,
      "total_price": 0.048,
      "llm_call_details": [...]
    }
  }
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | `string` | 消息唯一 ID（ULID） |
| `conversation_id` | `string` | 对话 ID |
| `role` | `string` | 消息角色：`user` / `assistant` / `system` / `tool` |
| `content` | `string` | 消息内容（JSON 格式的 content blocks） |
| `status` | `string` | 消息状态：`pending` / `streaming` / `completed` / `failed` |
| `created_at` | `datetime` | 创建时间（ISO 8601） |
| `metadata` | `object` | 消息元数据（JSONB），包含 `stream`、`usage` 等 |

### 3. Content Blocks（内容块）

消息 `content` 字段是 JSON 字符串，解析后为内容块数组：

```json
[
  {
    "type": "text",
    "text": "这是文本内容"
  },
  {
    "type": "thinking",
    "thinking": "这是思考过程"
  },
  {
    "type": "tool_use",
    "id": "toolu_xxx",
    "name": "web_search",
    "input": {"query": "Python 教程"}
  },
  {
    "type": "tool_result",
    "tool_use_id": "toolu_xxx",
    "content": "搜索结果..."
  }
]
```

### 4. APIResponse（统一响应格式）

所有接口返回统一的响应格式：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    // 实际数据
  }
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `code` | `integer` | HTTP 状态码（200=成功） |
| `message` | `string` | 响应消息 |
| `data` | `any` | 响应数据（根据接口不同而不同） |

---

## 接口列表

| 方法 | 路径 | 描述 |
| :--- | :--- | :--- |
| `POST` | `/api/v1/conversations` | 创建新会话 |
| `GET` | `/api/v1/conversations` | 获取会话列表 |
| `GET` | `/api/v1/conversations/{id}` | 获取会话详情 |
| `DELETE` | `/api/v1/conversations/{id}` | 删除会话 |
| `POST` | `/api/v1/conversations/{id}/messages` | 发送消息（核心对话，SSE） |
| `GET` | `/api/v1/conversations/{id}/messages` | 分页获取历史消息 |

---

## 接口详情

### 1. 创建新会话

**接口**: `POST /api/v1/conversations`

**描述**: 创建一个新的对话会话

**请求参数**:

| 参数 | 类型 | 位置 | 必填 | 说明 |
|------|------|------|------|------|
| `user_id` | `string` | Query | ✅ | 用户 ID |
| `title` | `string` | Query | ❌ | 对话标题（默认："新对话"） |

**请求示例**:

```bash
curl -X POST "http://localhost:8000/api/v1/conversations?user_id=user_001&title=讨论Python编程" \
  -H "Content-Type: application/json"
```

**响应示例**:

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "id": "conv_abc123",
    "user_id": "user_001",
    "title": "讨论Python编程",
    "status": "active",
    "created_at": "2024-01-01T12:00:00Z",
    "updated_at": "2024-01-01T12:00:00Z",
    "metadata": {}
  }
}
```

**错误响应**:

```json
{
  "code": 500,
  "message": "创建对话失败: 数据库连接错误",
  "data": null
}
```

---

### 2. 获取会话列表

**接口**: `GET /api/v1/conversations`

**描述**: 获取当前用户的会话列表，按更新时间倒序

**请求参数**:

| 参数 | 类型 | 位置 | 必填 | 说明 |
|------|------|------|------|------|
| `user_id` | `string` | Query | ✅ | 用户 ID |
| `limit` | `integer` | Query | ❌ | 每页数量（默认：20，最大：100） |
| `offset` | `integer` | Query | ❌ | 偏移量（默认：0） |

**请求示例**:

```bash
curl -X GET "http://localhost:8000/api/v1/conversations?user_id=user_001&limit=20&offset=0" \
  -H "Content-Type: application/json"
```

**响应示例**:

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "conversations": [
      {
        "id": "conv_abc123",
        "user_id": "user_001",
        "title": "讨论Python编程",
        "status": "active",
        "created_at": "2024-01-01T12:00:00Z",
        "updated_at": "2024-01-01T15:30:00Z",
        "message_count": 50,
        "last_message": "好的，我理解了",
        "last_message_at": "2024-01-01T15:30:00Z"
      },
      {
        "id": "conv_def456",
        "user_id": "user_001",
        "title": "讨论机器学习",
        "status": "active",
        "created_at": "2024-01-01T10:00:00Z",
        "updated_at": "2024-01-01T14:20:00Z",
        "message_count": 30,
        "last_message": "让我帮你分析一下",
        "last_message_at": "2024-01-01T14:20:00Z"
      }
    ],
    "total": 50,
    "limit": 20,
    "offset": 0
  }
}
```

---

### 3. 获取会话详情

**接口**: `GET /api/v1/conversations/{conversation_id}`

**描述**: 获取指定会话的详细信息

**路径参数**:

| 参数 | 类型 | 说明 |
|------|------|------|
| `conversation_id` | `string` | 对话 ID |

**请求示例**:

```bash
curl -X GET "http://localhost:8000/api/v1/conversations/conv_abc123" \
  -H "Content-Type: application/json"
```

**响应示例**:

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "id": "conv_abc123",
    "user_id": "user_001",
    "title": "讨论Python编程",
    "status": "active",
    "created_at": "2024-01-01T12:00:00Z",
    "updated_at": "2024-01-01T15:30:00Z",
    "metadata": {
      "message_count": 50,
      "last_message_at": "2024-01-01T15:30:00Z"
    }
  }
}
```

**错误响应**:

```json
{
  "code": 404,
  "message": "对话不存在: conv_abc123",
  "data": null
}
```

---

### 4. 删除会话

**接口**: `DELETE /api/v1/conversations/{conversation_id}`

**描述**: 删除指定会话及其所有消息（软删除）

**路径参数**:

| 参数 | 类型 | 说明 |
|------|------|------|
| `conversation_id` | `string` | 对话 ID |

**请求示例**:

```bash
curl -X DELETE "http://localhost:8000/api/v1/conversations/conv_abc123" \
  -H "Content-Type: application/json"
```

**响应示例**:

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "conversation_id": "conv_abc123",
    "deleted": true,
    "deleted_messages": 50
  }
}
```

**注意**: 
- 删除会话会同时删除该会话下的所有消息（CASCADE）
- 实际执行的是软删除（`status='deleted'`），数据仍保留在数据库中

---

### 5. 发送消息（核心对话，SSE）

**接口**: `POST /api/v1/conversations/{conversation_id}/messages`

**描述**: 发送一条新消息，并获取流式响应（Server-Sent Events）

**核心特性**:
- ✅ **流式响应**：使用 SSE（Server-Sent Events）实时返回 AI 回复
- ✅ **两阶段持久化**：占位消息 + 完整更新，保证可靠性
- ✅ **异步写入**：消息通过 Redis Streams 异步持久化，不阻塞响应
- ✅ **内存缓存**：自动更新 SessionCacheService，实现低延迟读取

**路径参数**:

| 参数 | 类型 | 说明 |
|------|------|------|
| `conversation_id` | `string` | 对话 ID |

**请求体**:

```json
{
  "message": "你好，请介绍一下自己",
  "user_id": "user_001",
  "agent_id": "default",
  "stream": true,
  "files": [
    {
      "file_id": "file_xxx",
      "file_url": "https://example.com/file.pdf"
    }
  ],
  "variables": {
    "location": "北京",
    "timezone": "Asia/Shanghai"
  }
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `message` | `string` | ✅ | 用户消息内容 |
| `user_id` | `string` | ✅ | 用户 ID |
| `agent_id` | `string` | ❌ | Agent 实例 ID（默认：`default`） |
| `stream` | `boolean` | ❌ | 是否流式输出（默认：`true`） |
| `files` | `array` | ❌ | 文件附件列表 |
| `variables` | `object` | ❌ | 前端上下文变量 |

**请求示例**:

```bash
curl -X POST "http://localhost:8000/api/v1/conversations/conv_abc123/messages" \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{
    "message": "你好，请介绍一下自己",
    "user_id": "user_001",
    "stream": true
  }'
```

**响应格式**（SSE）:

```
event: message_start
data: {"message_id": "msg_xxx", "model": "claude-sonnet-4.5"}

event: content_start
data: {"index": 0, "type": "text"}

event: content_delta
data: {"index": 0, "delta": "你好"}

event: content_delta
data: {"index": 0, "delta": "！"}

event: content_stop
data: {"index": 0}

event: message_stop
data: {"message_id": "msg_xxx", "status": "completed"}

event: usage
data: {
  "prompt_tokens": 1234,
  "completion_tokens": 567,
  "total_tokens": 1801,
  "total_price": 0.048,
  "llm_call_details": [...]
}
```

**SSE 事件类型**:

| 事件类型 | 说明 | 数据格式 |
|---------|------|---------|
| `message_start` | 消息开始 | `{"message_id": "...", "model": "..."}` |
| `content_start` | 内容块开始 | `{"index": 0, "type": "text"}` |
| `content_delta` | 内容增量 | `{"index": 0, "delta": "..."}` |
| `content_stop` | 内容块结束 | `{"index": 0}` |
| `message_stop` | 消息结束 | `{"message_id": "...", "status": "completed"}` |
| `usage` | 计费信息 | `{"prompt_tokens": ..., "total_price": ...}` |
| `error` | 错误事件 | `{"error_type": "...", "error_message": "..."}` |

**持久化流程**:

1. **阶段一（占位消息）**：
   - API 服务创建 `status='streaming'` 的占位消息
   - 推送到 `message_create_stream`（Redis Streams）
   - InsertWorker 消费并 INSERT 到 PostgreSQL
   - 更新 SessionCacheService 内存缓存

2. **流式传输**：
   - LLM 返回 chunk → broadcaster 累积 → SSE 发送给前端

3. **阶段二（完整消息）**：
   - 流式结束后，合并 `content` + `status='completed'` + `metadata`（含 `usage`）
   - 推送到 `message_update_stream`（Redis Streams）
   - UpdateWorker 消费并 UPDATE PostgreSQL
   - 更新 SessionCacheService 内存缓存

**错误响应**:

```json
{
  "code": 500,
  "message": "发送消息失败: LLM 调用超时",
  "data": null
}
```

---

### 6. 分页获取历史消息

**接口**: `GET /api/v1/conversations/{conversation_id}/messages`

**描述**: 获取对话的历史消息，支持基于游标的分页（对齐文档规范）

**路径参数**:

| 参数 | 类型 | 说明 |
|------|------|------|
| `conversation_id` | `string` | 对话 ID |

**查询参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `limit` | `integer` | ❌ | 每页数量（默认：50，最大：200） |
| `offset` | `integer` | ❌ | 偏移量（默认：0，当 `before_cursor` 为 None 时使用） |
| `order` | `string` | ❌ | 排序方式：`asc`（时间正序）/ `desc`（时间倒序，默认） |
| `before_cursor` | `string` | ❌ | 游标（message_id），用于分页加载更早的消息（对齐文档规范） |

**分页策略**:

1. **初始加载**：不传 `before_cursor`，使用 `offset` 分页
2. **向上滚动加载**：传 `before_cursor`，获取更早的消息（对齐文档规范）

**请求示例**:

```bash
# 初始加载（最近 50 条）
curl -X GET "http://localhost:8000/api/v1/conversations/conv_abc123/messages?limit=50&order=desc" \
  -H "Content-Type: application/json"

# 向上滚动加载（更早的消息）
curl -X GET "http://localhost:8000/api/v1/conversations/conv_abc123/messages?limit=50&before_cursor=msg_yyy&order=desc" \
  -H "Content-Type: application/json"
```

**响应示例**:

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "conversation_id": "conv_abc123",
    "messages": [
      {
        "id": "msg_xxx",
        "conversation_id": "conv_abc123",
        "role": "user",
        "content": "[{\"type\": \"text\", \"text\": \"你好\"}]",
        "status": "completed",
        "created_at": "2024-01-01T12:00:00Z",
        "metadata": {}
      },
      {
        "id": "msg_yyy",
        "conversation_id": "conv_abc123",
        "role": "assistant",
        "content": "[{\"type\": \"text\", \"text\": \"你好！有什么可以帮助你的吗？\"}]",
        "status": "completed",
        "created_at": "2024-01-01T12:00:05Z",
        "metadata": {
          "stream": {
            "phase": "final",
            "chunk_count": 5
          },
          "usage": {
            "prompt_tokens": 1234,
            "completion_tokens": 567,
            "total_tokens": 1801,
            "total_price": 0.048
          }
        }
      }
    ],
    "total": 100,
    "limit": 50,
    "offset": 0,
    "has_more": true,
    "next_cursor": "msg_zzz"
  }
}
```

**响应字段说明**:

| 字段 | 类型 | 说明 |
|------|------|------|
| `messages` | `array` | 消息列表 |
| `total` | `integer` | 总消息数 |
| `limit` | `integer` | 每页数量 |
| `offset` | `integer` | 当前偏移量 |
| `has_more` | `boolean` | 是否还有更多消息 |
| `next_cursor` | `string` | 下一个游标（用于下次分页，当使用 `before_cursor` 时） |

**使用场景**:

- **初始加载**：前端首次进入会话，加载最近 50 条消息
- **向上滚动加载**：用户向上滚动，需要查看更早的历史记录
- **搜索历史消息**：根据关键词搜索历史消息

---

## 错误处理

### 错误码

| HTTP 状态码 | 说明 | 示例 |
|------------|------|------|
| `200` | 成功 | 正常响应 |
| `400` | 请求参数错误 | 缺少必填参数、参数格式错误 |
| `404` | 资源不存在 | 对话不存在、消息不存在 |
| `500` | 服务器内部错误 | 数据库连接失败、LLM 调用失败 |

### 错误响应格式

```json
{
  "code": 404,
  "message": "对话不存在: conv_abc123",
  "data": null
}
```

### 常见错误

| 错误码 | 错误信息 | 解决方案 |
|--------|---------|---------|
| `400` | 缺少必填参数: user_id | 检查请求参数 |
| `404` | 对话不存在: conv_abc123 | 确认对话 ID 是否正确 |
| `500` | 数据库连接失败 | 检查数据库服务状态 |
| `500` | LLM 调用超时 | 检查 LLM 服务状态，重试 |

---

## 使用示例

### 完整对话流程

```python
import requests
import json

BASE_URL = "http://localhost:8000/api/v1"

# 1. 创建新会话
response = requests.post(
    f"{BASE_URL}/conversations",
    params={"user_id": "user_001", "title": "讨论Python编程"}
)
conversation = response.json()["data"]
conversation_id = conversation["id"]
print(f"✅ 会话创建成功: {conversation_id}")

# 2. 发送消息（流式）
response = requests.post(
    f"{BASE_URL}/conversations/{conversation_id}/messages",
    json={
        "message": "你好，请介绍一下自己",
        "user_id": "user_001",
        "stream": True
    },
    headers={"Accept": "text/event-stream"},
    stream=True
)

# 处理 SSE 流
for line in response.iter_lines():
    if line:
        line_str = line.decode('utf-8')
        if line_str.startswith('data:'):
            data = json.loads(line_str[5:].strip())
            print(f"📨 {data}")

# 3. 获取历史消息
response = requests.get(
    f"{BASE_URL}/conversations/{conversation_id}/messages",
    params={"limit": 50, "order": "desc"}
)
messages = response.json()["data"]["messages"]
print(f"✅ 获取到 {len(messages)} 条消息")

# 4. 向上滚动加载（使用游标）
if messages:
    last_message_id = messages[-1]["id"]
    response = requests.get(
        f"{BASE_URL}/conversations/{conversation_id}/messages",
        params={
            "limit": 50,
            "before_cursor": last_message_id,
            "order": "desc"
        }
    )
    older_messages = response.json()["data"]["messages"]
    print(f"✅ 加载到更早的 {len(older_messages)} 条消息")
```

### JavaScript 示例（SSE）

```javascript
const conversationId = 'conv_abc123';
const eventSource = new EventSource(
  `http://localhost:8000/api/v1/conversations/${conversationId}/messages`,
  {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      message: '你好，请介绍一下自己',
      user_id: 'user_001',
      stream: true
    })
  }
);

eventSource.addEventListener('message_start', (event) => {
  const data = JSON.parse(event.data);
  console.log('消息开始:', data);
});

eventSource.addEventListener('content_delta', (event) => {
  const data = JSON.parse(event.data);
  console.log('内容增量:', data.delta);
  // 更新 UI
});

eventSource.addEventListener('message_stop', (event) => {
  const data = JSON.parse(event.data);
  console.log('消息结束:', data);
  eventSource.close();
});

eventSource.addEventListener('usage', (event) => {
  const data = JSON.parse(event.data);
  console.log('计费信息:', data);
});
```

---

## 最佳实践

### 1. 会话管理

- ✅ **创建会话**：用户首次对话时创建新会话
- ✅ **复用会话**：同一主题的对话复用同一个会话 ID
- ✅ **清理会话**：定期清理长时间未使用的会话（软删除）

### 2. 消息发送

- ✅ **使用流式响应**：默认启用 `stream=true`，提升用户体验
- ✅ **错误处理**：监听 `error` 事件，处理异常情况
- ✅ **超时控制**：设置合理的超时时间（建议 60 秒）

### 3. 分页加载

- ✅ **初始加载**：首次加载最近 50 条消息
- ✅ **向上滚动**：使用 `before_cursor` 加载更早的消息
- ✅ **内存管理**：前端只保留可见区域的消息，避免内存溢出

### 4. 性能优化

- ✅ **会话粘性**：利用负载均衡的一致性哈希，保证同一会话路由到同一服务器
- ✅ **内存缓存**：活跃会话缓存在内存中，实现低延迟读取
- ✅ **异步写入**：消息通过 Redis Streams 异步持久化，不阻塞 API 响应

### 5. 错误处理

- ✅ **重试机制**：网络错误时自动重试（指数退避）
- ✅ **降级策略**：Redis 不可用时，直接写数据库（降级）
- ✅ **监控告警**：监控 Redis Streams 积压数量，及时告警

---

## 附录

### A. 消息状态说明

| 状态 | 说明 | 使用场景 |
|------|------|---------|
| `pending` | 待处理 | 消息创建但未开始处理 |
| `streaming` | 流式传输中 | 占位消息，正在流式生成内容 |
| `completed` | 已完成 | 消息生成完成，包含完整内容 |
| `failed` | 已失败 | 消息生成失败，包含错误信息 |

### B. 元数据字段说明

#### stream（流式信息）

```json
{
  "stream": {
    "phase": "final",
    "chunk_count": 5
  }
}
```

- `phase`: 流式阶段（`placeholder` / `streaming` / `final`）
- `chunk_count`: 内容块数量

#### usage（计费信息）

```json
{
  "usage": {
    "prompt_tokens": 1234,
    "completion_tokens": 567,
    "thinking_tokens": 120,
    "total_tokens": 1921,
    "total_price": 0.048,
    "llm_call_details": [...]
  }
}
```

- `prompt_tokens`: 输入 tokens
- `completion_tokens`: 输出 tokens
- `thinking_tokens`: 思考 tokens
- `total_tokens`: 总 tokens
- `total_price`: 总价格（USD）
- `llm_call_details`: LLM 调用明细

### C. 相关文档

- [消息会话设计文档](../zenflux-message-session-design.md)
- [流程验证报告](../flow-verification-report.md)
- [计费集成优化](../billing-integration-optimization.md)

---

**文档版本**: v1.0  
**最后更新**: 2026-01-19  
**维护者**: ZenFlux Agent Team
