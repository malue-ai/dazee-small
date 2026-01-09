# Zenflux Agent 输入输出格式规范

> 📅 **版本**: v1.0 | **更新**: 2025-01-06 | **状态**: 评审中

---

## 目录

1. [概述](#1-概述)
2. [快速开始](#2-快速开始)
3. [API 接口](#3-api-接口)
4. [SSE 事件协议](#4-sse-事件协议)
5. [数据模型](#5-数据模型)
6. [ZenO 兼容指南](#6-zeno-兼容指南)
7. [错误处理](#7-错误处理)
8. [附录](#8-附录)

---

## 1. 概述

### 1.1 文档用途

- **智能体对接**：第三方系统集成 Zenflux Agent
- **前端对接**：ZenO 等前端应用接收 SSE 事件流
- **协议评审**：团队内部对齐输入输出格式

### 1.2 核心设计

| 特性 | 说明 |
|------|------|
| **Claude 兼容** | 事件结构与 Claude Streaming API 一致 |
| **分层架构** | Session → Conversation → Message → Content |
| **可扩展** | 新增业务类型只需扩展 delta.type |

---

## 2. 快速开始

### 2.1 最简请求

```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "你好", "userId": "user_001"}'
```

### 2.2 完整请求示例

```json
{
  "message": "帮我生成一个关于AI的PPT",
  "userId": "user_001",
  "conversationId": "conv_abc123",
  "stream": true,
  "backgroundTasks": ["title_generation", "recommended_questions"],
  "files": [
    {
      "type": "document",
      "file_id": "file_abc123"
    },
    {
      "type": "image",
      "url": "https://example.com/image.png"
    }
  ],
  "variables": {
    "location": "北京",
    "timezone": "Asia/Shanghai"
  }
}
```

### 2.3 SSE 响应流示例

每个事件都包含完整的上下文字段：

```
event: session_start
data: {"event_uuid":"uuid-001","seq":1,"type":"session_start","session_id":"sess_123","conversation_id":"conv_456","timestamp":"2025-01-06T10:00:00Z","data":{}}

event: message_start
data: {"event_uuid":"uuid-002","seq":2,"type":"message_start","session_id":"sess_123","conversation_id":"conv_456","message_id":"msg_001","timestamp":"2025-01-06T10:00:01Z","data":{"message":{"id":"msg_001","role":"assistant","content":[]}}}

event: content_delta
data: {"event_uuid":"uuid-003","seq":3,"type":"content_delta","session_id":"sess_123","conversation_id":"conv_456","message_id":"msg_001","timestamp":"2025-01-06T10:00:02Z","data":{"index":0,"delta":{"type":"text_delta","text":"你好！"}}}

event: message_stop
data: {"event_uuid":"uuid-004","seq":4,"type":"message_stop","session_id":"sess_123","conversation_id":"conv_456","message_id":"msg_001","timestamp":"2025-01-06T10:00:03Z","data":{}}

event: done
data: {"event_uuid":"uuid-005","seq":5,"type":"done","session_id":"sess_123","conversation_id":"conv_456","timestamp":"2025-01-06T10:00:04Z","data":{}}
```

---

## 3. API 接口

### 3.1 Chat 接口

#### POST /api/v1/chat

统一聊天入口，支持流式和同步两种模式。

**请求参数**：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `message` | string | ✅ | 用户消息 |
| `userId` | string | 推荐 | 用户ID（多租户隔离） |
| `conversationId` | string | 可选 | 对话ID（延续上下文） |
| `stream` | boolean | 可选 | 流式输出（默认 true） |
| `backgroundTasks` | string[] | 可选 | 后台任务：`title_generation`, `recommended_questions` |
| `files` | object[] | 可选 | 附件列表（见下方详细说明） |
| `variables` | object | 可选 | 前端上下文变量（位置、时区等） |

**files 字段结构**：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `files[].type` | enum | ✅ | 文件类型：`document`(TXT/MD/PDF), `image`(JPG/PNG), `audio`(MP3/WAV), `video`(MP4/MOV), `custom`(其他) |
| `files[].file_id` | string\<uuid\> | 二选一 | 上传文件 ID（通过 `/files/upload` 获得） |
| `files[].url` | string\<url\> | 二选一 | 外部文件 URL |

> **说明**：`file_id` 和 `url` 二选一，推荐使用 `file_id`（本地上传方式）

**流式响应** (stream=true)：`text/event-stream` SSE 事件流

**同步响应** (stream=false)：

```json
{
  "code": 200,
  "message": "任务已启动",
  "data": {
    "task_id": "sess_abc123",
    "conversation_id": "conv_xyz",
    "message_id": "mes_123",
    "status": "running"
  }
}
```

---

### 3.2 Session 管理接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/v1/chat/{session_id}` | GET | SSE 重连（断线续传） |
| `/api/v1/session/{session_id}/status` | GET | 查询 Session 状态 |
| `/api/v1/session/{session_id}/events` | GET | 获取历史事件 |
| `/api/v1/session/{session_id}/stop` | POST | 停止 Session |
| `/api/v1/user/{user_id}/sessions` | GET | 获取用户所有活跃 Session |

#### GET /api/v1/session/{session_id}/status

```json
{
  "code": 200,
  "data": {
    "session_id": "sess_abc123",
    "user_id": "user_001",
    "conversation_id": "conv_abc",
    "status": "running",       // running | completed | failed | stopped
    "progress": 0.6,
    "last_event_id": 150
  }
}
```

#### GET /api/v1/chat/{session_id}?after_seq=100

断线重连，首先返回 `reconnect_info` 事件：

```json
{
  "type": "reconnect_info",
  "data": {
    "session_id": "sess_123",
    "conversation_id": "conv_456",
    "status": "running",
    "last_event_seq": 150
  }
}
```

---

### 3.3 文件管理接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/v1/files/upload` | POST | 上传文件（限制 50MB） |
| `/api/v1/files/{file_id}/url` | GET | 获取访问 URL |
| `/api/v1/files/{file_id}/download` | GET | 获取下载 URL |
| `/api/v1/files` | GET | 获取文件列表 |
| `/api/v1/files/{file_id}` | GET | 获取文件详情 |
| `/api/v1/files/{file_id}` | DELETE | 删除文件 |

#### POST /api/v1/files/upload

```
Content-Type: multipart/form-data

file: (binary)
user_id: user_001
```

**响应**：

```json
{
  "code": 200,
  "data": {
    "file_id": "file_abc123",
    "filename": "document.pdf",
    "file_size": 1024000,
    "mime_type": "application/pdf",
    "created_at": "2025-01-06T10:00:00Z"
  }
}
```

---

## 4. SSE 事件协议

### 4.1 事件格式

```
event: <event_type>
data: <json_payload>

```

### 4.2 事件结构

```typescript
interface Event {
  event_uuid: string;          // 全局唯一 UUID
  seq: number;                 // Session 内序号
  type: string;                // 事件类型
  session_id: string;          // Session ID
  conversation_id?: string;    // Conversation ID
  message_id?: string;         // Message ID
  timestamp: string;           // ISO 8601
  data: object;                // 事件数据
}
```

### 4.3 事件类型总览

```
Session 级
├── session_start          首个事件
├── session_end            正常结束
└── session_stopped        用户中断

Conversation 级
├── conversation_start     对话开始
├── conversation_delta     对话更新
└── conversation_stop      对话结束

Message 级
├── message_start          消息开始 → ZenO: message.assistant.created
├── message_delta          消息增量 → ZenO: message.assistant.delta
└── message_stop           消息结束 → ZenO: message.assistant.done

Content 级
├── content_start          内容块开始
├── content_delta          内容块增量
└── content_stop           内容块结束

System 级
├── error                  错误 → ZenO: message.assistant.error
├── done                   流结束
└── ping                   心跳
```

### 4.4 核心事件详解

> **重要**：每个事件都包含以下上下文字段：
> - `event_uuid`: 全局唯一 UUID
> - `seq`: Session 内递增序号（从 1 开始）
> - `session_id`: Session ID
> - `conversation_id`: Conversation ID
> - `message_id`: Message ID（Message 级事件）
> - `timestamp`: ISO 8601 时间戳

#### message_start

```json
{
  "event_uuid": "evt_uuid_001",
  "seq": 5,
  "type": "message_start",
  "session_id": "sess_abc123",
  "conversation_id": "conv_xyz789",
  "message_id": "msg_001",
  "timestamp": "2025-01-06T10:00:00Z",
  "data": {
    "message": {
      "id": "msg_001",
      "role": "assistant",
      "model": "claude-sonnet-4-5-20250929",
      "content": [],
      "usage": {"input_tokens": 0, "output_tokens": 0}
    }
  }
}
```

#### message_delta

用于传输业务数据，格式统一为 `{type, content}`：

| delta.type | 说明 | 处理模式 |
|------------|------|---------|
| `intent` | 意图识别 | 整体替换 |
| `plan` | 任务进度 | 整体替换 |
| `recommended` | 推荐问题 | 整体替换 |

```json
{
  "event_uuid": "evt_uuid_010",
  "seq": 10,
  "type": "message_delta",
  "session_id": "sess_abc123",
  "conversation_id": "conv_xyz789",
  "message_id": "msg_001",
  "timestamp": "2025-01-06T10:00:05Z",
  "data": {
    "type": "intent",
    "content": "{\"task_type\":\"code_generation\",\"confidence\":0.95}"
  }
}
```

#### content_start / content_delta / content_stop

用于流式传输内容块：

**Content Block 类型**：

| type | 说明 |
|------|------|
| `text` | 文本回复 |
| `thinking` | 思考过程 |
| `tool_use` | 工具调用 |
| `tool_result` | 工具结果 |

**文本流式**（每个事件都包含完整上下文）：

```json
// content_start
{
  "event_uuid": "evt_011", "seq": 11,
  "type": "content_start",
  "session_id": "sess_123", "conversation_id": "conv_456", "message_id": "msg_001",
  "timestamp": "2025-01-06T10:00:01Z",
  "data": {"index": 0, "content_block": {"type": "text", "text": ""}}
}

// content_delta
{
  "event_uuid": "evt_012", "seq": 12,
  "type": "content_delta",
  "session_id": "sess_123", "conversation_id": "conv_456", "message_id": "msg_001",
  "timestamp": "2025-01-06T10:00:02Z",
  "data": {"index": 0, "delta": {"type": "text_delta", "text": "你好"}}
}

// content_stop
{
  "event_uuid": "evt_013", "seq": 13,
  "type": "content_stop",
  "session_id": "sess_123", "conversation_id": "conv_456", "message_id": "msg_001",
  "timestamp": "2025-01-06T10:00:03Z",
  "data": {"index": 0}
}
```

**工具调用**：

```json
// tool_use
{
  "event_uuid": "evt_014", "seq": 14,
  "type": "content_start",
  "session_id": "sess_123", "conversation_id": "conv_456", "message_id": "msg_001",
  "timestamp": "2025-01-06T10:00:04Z",
  "data": {"index": 1, "content_block": {"type": "tool_use", "id": "toolu_123", "name": "web_search", "input": {"query": "AI"}}}
}

// tool_result
{
  "event_uuid": "evt_015", "seq": 15,
  "type": "content_start",
  "session_id": "sess_123", "conversation_id": "conv_456", "message_id": "msg_001",
  "timestamp": "2025-01-06T10:00:05Z",
  "data": {"index": 2, "content_block": {"type": "tool_result", "tool_use_id": "toolu_123", "content": "搜索结果...", "is_error": false}}
}
```

---

## 5. 数据模型

### 5.1 Content Block

```typescript
// 文本
interface TextBlock {
  type: "text";
  text: string;
}

// 思考过程
interface ThinkingBlock {
  type: "thinking";
  thinking: string;
  signature?: string;
}

// 工具调用
interface ToolUseBlock {
  type: "tool_use";
  id: string;
  name: string;
  input: object;
}

// 工具结果
interface ToolResultBlock {
  type: "tool_result";
  tool_use_id: string;
  content: string;
  is_error: boolean;
}

// 图片
interface ImageBlock {
  type: "image";
  source: { type: "base64" | "url"; data?: string; url?: string; media_type?: string; };
}
```

### 5.2 消息存储格式

数据库 `content` 字段为 JSON 数组：

```json
[
  {"type": "thinking", "thinking": "让我分析一下..."},
  {"type": "text", "text": "好的，我来帮你处理。"},
  {"type": "tool_use", "id": "toolu_123", "name": "web_search", "input": {"query": "AI"}},
  {"type": "tool_result", "tool_use_id": "toolu_123", "content": "搜索结果...", "is_error": false}
]
```

### 5.3 统一响应格式

```typescript
interface APIResponse<T> {
  code: number;     // 200=成功
  message: string;
  data?: T;
}
```

---

## 6. ZenO 兼容指南

### 6.1 事件映射

| Zenflux 事件 | ZenO 事件 |
|-------------|----------|
| `message_start` | `message.assistant.created` |
| `content_start (text)` | `message.assistant.start` |
| `content_delta (text_delta)` | `message.assistant.delta (type: response)` |
| `content_delta (thinking_delta)` | `message.assistant.delta (type: thinking)` |
| `message_delta` | `message.assistant.delta` |
| `message_stop` | `message.assistant.done` |
| `error` | `message.assistant.error` |

### 6.2 Delta 类型兼容

> 💡 ZenO 的 `mind`、`files`、`clue` 等本质上都是**工具调用结果**，只需实现对应工具即可自动兼容。

| ZenO delta.type | Zenflux 实现 | 状态 |
|-----------------|-------------|------|
| `intent` | message_delta | ✅ 已实现 |
| `thinking` | content_delta | ✅ 已实现 |
| `response` | content_delta | ✅ 已实现 |
| `progress` | message_delta (plan) | ✅ 已实现 |
| `recommended` | message_delta | ✅ 已实现 |
| `mind` | mermaid_generator 工具 | 🔧 待实现 |
| `files` | file_generator 工具 | 🔧 待实现 |
| `clue` | clue_generator 工具 | 🔧 待实现 |
| `sql/data/chart` | 对应工具 | 🔧 待实现 |

### 6.3 前端适配代码

```typescript
class ZenfluxAdapter {
  private content = '';
  
  handleEvent(event: ZenfluxEvent) {
    switch (event.type) {
      case 'message_start':
        this.onMessageCreated(event.data.message);
        break;
        
      case 'content_delta':
        if (event.data.delta.type === 'text_delta') {
          this.content += event.data.delta.text;
          this.onResponseDelta(event.data.delta.text);
        }
        break;
        
      case 'message_delta':
        // intent, plan, recommended 等直接透传
        this.onDelta(event.data.type, JSON.parse(event.data.content));
        break;
        
      case 'message_stop':
        this.onMessageDone();
        break;
    }
  }
}
```

---

## 7. 错误处理

### 7.1 错误码

| 错误码 | 说明 | HTTP |
|--------|------|------|
| `VALIDATION_ERROR` | 参数验证失败 | 400 |
| `SESSION_NOT_FOUND` | Session 不存在 | 404 |
| `AGENT_ERROR` | Agent 执行错误 | 500 |
| `EXTERNAL_SERVICE` | 外部服务错误 | 503 |
| `INTERNAL_ERROR` | 内部错误 | 500 |

### 7.2 错误事件

```json
{
  "type": "error",
  "data": {
    "error": {
      "type": "rate_limit",
      "message": "请求频率过高，请稍后重试"
    }
  }
}
```

| error.type | 说明 | 可重试 |
|------------|------|--------|
| `network_error` | 网络错误 | ✅ |
| `timeout_error` | 超时 | ✅ |
| `rate_limit` | 限流 | ✅ |
| `permission_denied` | 权限错误 | ❌ |
| `internal_error` | 内部错误 | ⚠️ |

---

## 8. 附录

### 8.1 完整事件流示例

```
# 带工具调用的对话

event: session_start
data: {"type":"session_start","session_id":"sess_123",...}

event: message_start
data: {"type":"message_start","data":{"message":{"id":"msg_001",...}}}

# 意图识别
event: message_delta
data: {"type":"message_delta","data":{"type":"intent","content":"{...}"}}

# 思考过程
event: content_start
data: {"data":{"index":0,"content_block":{"type":"thinking","thinking":""}}}

event: content_delta
data: {"data":{"index":0,"delta":{"type":"thinking_delta","thinking":"需要搜索..."}}}

event: content_stop
data: {"data":{"index":0}}

# 工具调用
event: content_start
data: {"data":{"index":1,"content_block":{"type":"tool_use","id":"toolu_123","name":"web_search","input":{}}}}

event: content_stop
data: {"data":{"index":1}}

# 工具结果
event: content_start
data: {"data":{"index":2,"content_block":{"type":"tool_result","tool_use_id":"toolu_123","content":"..."}}}

event: content_stop
data: {"data":{"index":2}}

# 搜索结果（message_delta）
event: message_delta
data: {"type":"message_delta","data":{"type":"search","content":"..."}}

# 最终回复
event: content_start
data: {"data":{"index":3,"content_block":{"type":"text","text":""}}}

event: content_delta
data: {"data":{"index":3,"delta":{"type":"text_delta","text":"根据搜索结果..."}}}

event: content_stop
data: {"data":{"index":3}}

# 推荐问题
event: message_delta
data: {"type":"message_delta","data":{"type":"recommended","content":"{...}"}}

event: message_stop
data: {}

event: session_end
data: {"status":"completed"}

event: done
data: {}
```

### 8.2 扩展新 Delta 类型

```python
# 后端：注册工具映射
from core.events.broadcaster import EventBroadcaster
EventBroadcaster.register_tool_delta_type("mermaid_generator", "mind")

# 工具执行完成后自动发送：
# {"type": "message_delta", "data": {"type": "mind", "content": "..."}}
```

