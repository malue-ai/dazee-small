# ZenFlux 前后端通信协议

## 概述

ZenFlux 前后端通过以下方式通信：
- **HTTP REST API**：CRUD 操作、管理接口
- **WebSocket（聊天）**：流式聊天消息（主协议）
- **WebSocket（实时语音）**：语音对话（OpenAI Realtime API 兼容）(不实现)

基础路径：`/api/v1`

---

## 一、统一响应格式

所有 HTTP API 使用统一响应包装：

```json
{
  "code": 200,
  "message": "success",
  "data": { ... }
}
```

错误响应：

```json
{
  "code": 400,
  "message": "错误描述",
  "data": null
}
```

---

## 二、WebSocket 聊天协议（核心）

### 连接地址

```
ws://{host}/api/v1/ws/chat
```

### 帧协议

所有 WebSocket 消息使用 JSON 帧，分三种类型：

#### 1. 请求帧（客户端 → 服务端）

```json
{
  "type": "req",
  "id": "uuid-v4",
  "method": "chat.send | chat.abort",
  "params": { ... }
}
```

**`chat.send` 参数**：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `message` | string | ✅ | 用户消息 |
| `user_id` | string | ✅ | 用户 ID |
| `conversation_id` | string | 否 | 对话 ID（为空则新建） |
| `agent_id` | string | 否 | 指定 Agent |
| `stream` | boolean | 否 | 是否流式（默认 true） |
| `background_tasks` | string[] | 否 | 后台任务列表 |
| `files` | FileReference[] | 否 | 附件列表 |
| `variables` | object | 否 | 前端上下文变量 |

**`chat.abort` 参数**：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `session_id` | string | ✅ | 要中止的会话 ID |

#### 2. 响应帧（服务端 → 客户端）

```json
{
  "type": "res",
  "id": "对应请求的 uuid",
  "ok": true,
  "payload": { ... }
}
```

错误响应：

```json
{
  "type": "res",
  "id": "对应请求的 uuid",
  "ok": false,
  "error": { "code": "ERROR_CODE", "message": "错误描述" }
}
```

#### 3. 事件帧（服务端 → 客户端，流式推送）

```json
{
  "type": "event",
  "event": "事件类型",
  "payload": {
    "type": "SSE 事件类型",
    "data": { ... }
  },
  "seq": 0
}
```

### 事件架构总览

#### 事件层级体系

事件采用 **五层嵌套结构**，每层只有 `start` / `delta` / `stop` 三个核心事件：

```
Session（运行会话）       session_start, session_stopped, session_end, ping
  │
  └── Conversation（对话）  conversation_start, conversation_delta, conversation_stop
        │
        └── Message（消息）   message_start, message_delta, message_stop
              │
              └── Content（内容块）  content_start, content_delta, content_stop

System（系统级）           error, done
```

#### 统一事件信封结构

所有事件在存储/传输层使用统一的信封格式：

```json
{
  "event_uuid": "uuid-v4",
  "seq": 1,
  "type": "content_delta",
  "session_id": "session-xxx",
  "conversation_id": "conv-xxx",
  "message_id": "msg-xxx",
  "timestamp": "2025-01-01T00:00:00.000000",
  "data": { ... }
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `event_uuid` | string | 全局唯一 UUID |
| `seq` | int | Session 内自增序号（1, 2, 3...） |
| `type` | string | 事件类型 |
| `session_id` | string | 所属 Session ID |
| `conversation_id` | string | 所属 Conversation ID |
| `message_id` | string | 所属 Message ID（可选） |
| `timestamp` | string | ISO 8601 时间戳 |
| `data` | object | 事件特定数据（见下文各事件详情） |

#### 事件生命周期（完整聊天流程）

一次完整的聊天流程产生以下事件序列：

```
seq=1  session_start              ← 会话开始
seq=2    conversation_start       ← 对话开始
seq=3      message_start          ← 消息开始（第 1 轮）
seq=4        content_start        ← 内容块 0 开始（thinking）
seq=5        content_delta        ← 思考增量（重复多次）
seq=N        content_stop         ← 内容块 0 结束
seq=N+1      content_start        ← 内容块 1 开始（text）
seq=N+2      content_delta        ← 文本增量（重复多次）
seq=M        content_stop         ← 内容块 1 结束
seq=M+1      content_start        ← 内容块 2 开始（tool_use，可选）
seq=M+2      content_delta        ← 工具输入增量
seq=M+3      content_stop         ← 内容块 2 结束
seq=M+4    message_delta          ← 消息级元数据（usage/recommended/...）
seq=M+5    message_stop           ← 消息结束
           --- 如果有工具调用，Agent 会自动继续下一轮 ---
seq=M+6    message_start          ← 消息开始（第 2 轮）
seq=M+7      content_start        ← tool_result 内容块
seq=M+8      content_delta        ← 工具结果增量
seq=M+9      content_stop         ← 工具结果结束
seq=...      content_start        ← text 内容块（最终回复）
seq=...      content_delta        ← 文本增量
seq=...      content_stop         ← 文本结束
seq=...    message_delta          ← 消息级元数据
seq=...    message_stop           ← 消息结束（流结束信号）
seq=...  session_end              ← 会话结束
```

---

### 各层事件详细协议

---

### Session 级事件

#### `session_start` — 会话开始（首个事件）

```json
{
  "type": "session_start",
  "data": {
    "session_id": "sess-abc123",
    "user_id": "local",
    "conversation_id": "conv-xyz789",
    "message_id": "msg-001",
    "timestamp": "2025-01-01T00:00:00.000000"
  }
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `session_id` | string | 本次运行会话 ID |
| `user_id` | string | 用户 ID |
| `conversation_id` | string | 对话 ID |
| `message_id` | string | 消息 ID（可选） |
| `timestamp` | string | 时间戳 |

**前端处理**：记录 `session_id`，标记会话状态为 running。

#### `session_stopped` — 用户主动停止

```json
{
  "type": "session_stopped",
  "data": {
    "session_id": "sess-abc123",
    "reason": "user_requested",
    "stopped_at": "2025-01-01T00:01:00.000000"
  }
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `reason` | string | 停止原因：`user_requested` / `timeout` / `error` |
| `stopped_at` | string | 停止时间 |

**前端处理**：标记会话状态为 completed，作为流结束信号之一。

#### `session_end` — 会话结束（正常/失败/取消）

```json
{
  "type": "session_end",
  "data": {
    "session_id": "sess-abc123",
    "status": "completed",
    "duration_ms": 3500
  }
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `status` | string | 最终状态：`completed` / `failed` / `cancelled` |
| `duration_ms` | int | 会话持续时间（毫秒） |

**前端处理**：作为流结束信号之一，清理会话状态。

#### `ping` — 心跳保活

```json
{
  "type": "ping",
  "data": {
    "type": "ping"
  }
}
```

**说明**：SSE 模式下使用。WebSocket 模式下心跳使用独立的 `tick` 帧（见下文）。

---

### Conversation 级事件

#### `conversation_start` — 对话开始

```json
{
  "type": "conversation_start",
  "data": {
    "conversation_id": "conv-xyz789",
    "title": "新对话",
    "created_at": "2025-01-01T00:00:00",
    "updated_at": "2025-01-01T00:00:00",
    "metadata": {}
  }
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `conversation_id` | string | 对话 ID |
| `title` | string | 对话标题 |
| `created_at` | string | 创建时间 |
| `updated_at` | string | 更新时间 |
| `metadata` | object | 对话元数据 |

**前端处理**：确认对话 ID，新对话时更新列表。

#### `conversation_delta` — 对话增量更新

对话增量有多种子类型，通过展开的字段区分：

**标题更新**：

```json
{
  "type": "conversation_delta",
  "data": {
    "conversation_id": "conv-xyz789",
    "title": "AI 帮你写代码"
  }
}
```

**元数据更新**：

```json
{
  "type": "conversation_delta",
  "data": {
    "conversation_id": "conv-xyz789",
    "metadata": { "tags": ["coding"] }
  }
}
```

**上下文压缩通知**：

```json
{
  "type": "conversation_delta",
  "data": {
    "conversation_id": "conv-xyz789",
    "compressed": { "summary": "对话摘要...", "trimmed_count": 5 }
  }
}
```

#### `conversation_stop` — 对话结束

```json
{
  "type": "conversation_stop",
  "data": {
    "conversation_id": "conv-xyz789",
    "final_status": "completed",
    "summary": {}
  }
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `final_status` | string | `completed` / `stopped` / `failed` |
| `summary` | object | 会话摘要（可选） |

---

### Message 级事件

#### `message_start` — 消息开始

```json
{
  "type": "message_start",
  "message": {
    "id": "msg-001",
    "type": "message",
    "role": "assistant",
    "content": [],
    "model": "claude-sonnet-4-5-20250929",
    "stop_reason": null,
    "stop_sequence": null,
    "usage": { "input_tokens": 0, "output_tokens": 0 }
  },
  "timestamp": "2025-01-01T00:00:00.000000"
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `message.id` | string | 消息 ID |
| `message.role` | string | 固定 `"assistant"` |
| `message.model` | string | 使用的模型名称 |
| `message.usage` | object | 初始 token 统计 |

**前端处理**：更新占位消息的 ID，确保和后端 message_id 对齐。

#### `message_delta` — 消息级增量

消息增量采用统一结构 `{"type": "xxx", "content": ...}`，通过 `type` 字段区分子类型：

| delta.type | 说明 | content 结构 |
|---|---|---|
| `usage` | Token 使用统计 | `{"stop_reason": "end_turn"}` |
| `recommended` | 推荐问题 | `{"questions": ["问题1", "问题2"]}` |
| `preface` | 开场白/前言 | `"开场白文本"` |
| `confirmation_request` | HITL 人工确认请求 | `{...HITL 请求对象}` |
| `intent` | 意图分析结果 | `{...意图对象}` |
| `billing` | 计费信息 | `{...计费对象}` |
| `search` | 搜索结果 | `"搜索结果文本"` |
| `knowledge` | 知识检索结果 | `"知识内容"` |

**示例 — usage**：

```json
{
  "type": "message_delta",
  "data": {
    "type": "usage",
    "content": { "stop_reason": "end_turn" }
  }
}
```

**示例 — recommended（推荐问题）**：

```json
{
  "type": "message_delta",
  "data": {
    "type": "recommended",
    "content": "{\"questions\": [\"如何优化性能？\", \"能解释一下原理吗？\"]}"
  }
}
```

**示例 — preface（开场白）**：

```json
{
  "type": "message_delta",
  "data": {
    "type": "preface",
    "content": "让我来帮你分析这个问题..."
  }
}
```

**示例 — confirmation_request（HITL 人工确认）**：

```json
{
  "type": "message_delta",
  "data": {
    "type": "confirmation_request",
    "content": "{\"request_id\": \"req-001\", \"tool_name\": \"file_write\", \"description\": \"写入文件 config.json\", \"options\": [\"approve\", \"reject\"]}"
  }
}
```

**前端处理**：根据 `delta.type` 分发到不同处理逻辑（推荐问题更新 UI、确认请求弹出模态框等）。

#### `message_stop` — 消息结束

```json
{
  "type": "message_stop",
  "data": {}
}
```

**前端处理**：标记当前消息完成。这是**流结束信号**之一，前端收到后结束当前流的读取。

---

### Content 级事件

Content 级事件是最高频的事件，负责传输实际内容（文本、思考、工具调用/结果）。

#### `content_start` — 内容块开始

标记一个新内容块的开始，`content_block` 结构决定了后续 delta 的语义：

**文本块**：

```json
{
  "type": "content_start",
  "data": {
    "index": 0,
    "content_block": {
      "type": "text",
      "text": ""
    }
  }
}
```

**思考块**（Extended Thinking）：

```json
{
  "type": "content_start",
  "data": {
    "index": 0,
    "content_block": {
      "type": "thinking",
      "thinking": ""
    }
  }
}
```

**工具调用块**：

```json
{
  "type": "content_start",
  "data": {
    "index": 2,
    "content_block": {
      "type": "tool_use",
      "id": "toolu_abc123",
      "name": "web_search",
      "input": {}
    }
  }
}
```

**工具结果块**：

```json
{
  "type": "content_start",
  "data": {
    "index": 3,
    "content_block": {
      "type": "tool_result",
      "tool_use_id": "toolu_abc123",
      "content": "",
      "is_error": false
    }
  }
}
```

| content_block.type | 说明 | 关键字段 |
|---|---|---|
| `text` | 文本输出 | `text`: 初始为空 |
| `thinking` | 模型思考过程 | `thinking`: 初始为空 |
| `tool_use` | 工具调用 | `id`, `name`, `input` |
| `tool_result` | 工具结果 | `tool_use_id`, `content`, `is_error` |
| `server_tool_use` | 服务端工具调用 | 同 `tool_use` |

**前端处理**：根据 `content_block.type` 初始化对应类型的内容块对象，追加到当前消息的 `contentBlocks` 数组。

#### `content_delta` — 内容增量

delta 是简化的字符串格式，类型由前序 `content_start` 的 `content_block.type` 决定：

```json
{
  "type": "content_delta",
  "data": {
    "index": 0,
    "delta": "增量字符串"
  }
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `index` | int | 内容块索引，对应 `content_start` 的 `index` |
| `delta` | string | 增量内容（纯字符串） |

**不同内容类型的 delta 含义**：

| content_block.type | delta 含义 | 示例 |
|---|---|---|
| `text` | 文本片段 | `"你好"`, `"，我是"` |
| `thinking` | 思考片段 | `"Let me analyze..."` |
| `tool_use` | JSON 输入片段 | `"{\"query\": \"wea"`, `"ther\"}"` |
| `tool_result` | 工具执行结果片段 | `"搜索结果：..."` |

**前端处理**：根据 `index` 找到对应内容块，追加 delta 到相应字段（`text` / `thinking` / `partialInput` / `content`）。

**节流说明**：WebSocket 层对 `content_delta` 实施 150ms 节流（`DeltaThrottle`），合并同 index 的连续 delta 减少帧数。

#### `content_stop` — 内容块结束

```json
{
  "type": "content_stop",
  "data": {
    "index": 0
  }
}
```

**前端处理**：标记 `index` 对应的内容块为完成状态。如果是 `tool_use` 类型，此时可以解析完整的 JSON 输入。

---

### System 级事件

#### `error` — 错误事件

```json
{
  "type": "error",
  "data": {
    "error": {
      "type": "overloaded_error",
      "message": "服务暂时过载，请稍后重试"
    }
  }
}
```

| error.type | 说明 |
|---|---|
| `network_error` | 网络错误 |
| `timeout_error` | 超时错误 |
| `overloaded_error` | 服务过载 |
| `internal_error` | 内部错误 |
| `validation_error` | 参数验证错误 |

**前端处理**：标记会话状态为 completed，展示错误信息。

#### `done` — 流结束标记

```json
{
  "type": "done",
  "data": {
    "type": "done"
  }
}
```

**说明**：SSE 模式下，在 `message_stop` 之后追加发送 `event: done` 作为 SSE 协议层面的结束信号。

---

### 扩展事件（V11）

#### `rollback_options` — 回滚选项

```json
{
  "type": "rollback_options",
  "data": {
    "task_id": "task-001",
    "options": ["选项1", "选项2"],
    "error": "执行失败原因",
    "reason": "回滚原因"
  }
}
```

**前端处理**：弹出回滚选择模态框。

#### `rollback_completed` — 回滚完成

```json
{
  "type": "rollback_completed",
  "data": {}
}
```

**前端处理**：关闭回滚模态框。

#### `long_running_confirm` — 长任务确认

```json
{
  "type": "long_running_confirm",
  "data": {
    "turn": 15,
    "message": "任务已执行较多轮次，是否继续？"
  }
}
```

**前端处理**：弹出长任务确认模态框，用户可选择继续或停止。

---

### WebSocket 特有的控制帧

以下帧仅在 WebSocket 模式下使用，不属于事件体系：

#### `tick` — WebSocket 心跳

```json
{
  "type": "event",
  "event": "tick",
  "payload": { "ts": 1704067200000 },
  "seq": 0
}
```

- 服务端每 **30s** 发送一次
- 客户端 **60s**（2 倍超时）未收到则断连重连
- 不转发给业务处理器

#### `ping` / `pong` — 客户端探活

```json
// 客户端发送
{ "type": "ping" }

// 服务端回复
{ "type": "pong", "ts": 1704067200000 }
```

---

### 流结束信号汇总

前端通过以下任一事件判断流式读取结束：

| 事件 | 模式 | 说明 |
|------|------|------|
| `message_stop` | SSE + WS | 消息正常结束 |
| `session_stopped` | SSE + WS | 用户主动停止 |
| `session_end` | SSE + WS | 会话结束 |
| `error` | SSE + WS | 错误中断 |
| SSE `event: done` | 仅 SSE | SSE 协议层面结束标记 |

### 连接管理

| 机制 | 说明 |
|------|------|
| 持久化连接 | WebSocket 消息间复用，不断开/重连 |
| 心跳 | 服务端每 30s 发送 `tick` |
| 超时断连 | 60s 未收到 `tick` 则客户端断连重连 |
| 自动重连 | 指数退避：800ms → 15s 上限 |
| Delta 节流 | `content_delta` 事件 150ms 合并节流，减少帧数 |

---

## 三、HTTP API 端点

### 3.1 聊天与会话

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/chat` | 发送聊天消息（SSE 流式/同步） |
| POST | `/api/v1/session/{id}/stop` | 停止会话 |
| POST | `/api/v1/session/{id}/confirm_continue` | 确认继续长任务 |
| POST | `/api/v1/session/{id}/rollback` | 回滚会话状态 |
| GET | `/api/v1/session/{id}` | 获取会话信息 |
| DELETE | `/api/v1/session/{id}` | 结束会话 |
| GET | `/api/v1/sessions` | 列出活跃会话 |

**ChatRequest**：

```json
{
  "message": "用户消息",
  "userId": "local",
  "conversationId": "uuid (可选)",
  "messageId": "uuid (可选)",
  "agentId": "agent-id (可选)",
  "stream": true,
  "backgroundTasks": [],
  "files": [
    {
      "file_url": "https://...",
      "file_name": "文件名",
      "file_type": "application/pdf",
      "file_size": 1024
    }
  ],
  "variables": {}
}
```

### 3.2 对话管理

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/conversations` | 创建对话（query: `user_id`, `title`） |
| GET | `/api/v1/conversations` | 对话列表（query: `user_id`, `limit`, `offset`） |
| GET | `/api/v1/conversations/{id}` | 对话详情 |
| PUT | `/api/v1/conversations/{id}` | 更新标题（query: `title`） |
| DELETE | `/api/v1/conversations/{id}` | 删除对话 |
| GET | `/api/v1/conversations/{id}/messages` | 消息列表（支持游标分页） |
| GET | `/api/v1/conversations/search` | 搜索对话（query: `user_id`, `q`, `limit`） |
| POST | `/api/v1/conversations/{id}/preload` | 预加载会话上下文 |
| GET | `/api/v1/conversations/{id}/summary` | 获取对话摘要 |

**Conversation 对象**：

```json
{
  "id": "uuid",
  "title": "对话标题",
  "user_id": "local",
  "created_at": "2025-01-01T00:00:00Z",
  "updated_at": "2025-01-01T00:00:00Z"
}
```

**Message 对象**：

```json
{
  "id": "uuid",
  "conversation_id": "uuid",
  "role": "user | assistant",
  "content": "文本 或 ContentBlock[]（JSON 数组）",
  "status": "string",
  "created_at": "2025-01-01T00:00:00Z",
  "metadata": {}
}
```

### 3.3 人工确认（HITL）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/human-confirmation/pending` | 获取待确认请求 |
| POST | `/api/v1/human-confirmation/{session_id}` | 提交确认响应 |
| GET | `/api/v1/human-confirmation/{request_id}` | 获取确认详情 |
| DELETE | `/api/v1/human-confirmation/{request_id}` | 取消确认 |

**确认响应**：

```json
{
  "response": "approve | reject | 自定义内容",
  "metadata": {}
}
```

### 3.4 文件上传

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/files/upload` | 上传文件（FormData: `file` + `user_id`） |

**响应**：

```json
{
  "file_id": "uuid",
  "file_name": "example.pdf",
  "file_size": 1024,
  "file_type": "application/pdf",
  "file_url": "https://...",
  "created_at": "2025-01-01T00:00:00Z"
}
```

### 3.5 Agent 管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/agents` | Agent 列表 |
| POST | `/api/v1/agents` | 创建 Agent |
| GET | `/api/v1/agents/{id}` | Agent 详情 |
| PUT | `/api/v1/agents/{id}` | 更新 Agent |
| DELETE | `/api/v1/agents/{id}` | 删除 Agent |
| GET | `/api/v1/agents/templates` | Agent 模板列表 |
| POST | `/api/v1/agents/validate` | 校验 Agent 配置 |
| POST | `/api/v1/agents/reload` | 热重载所有 Agent |
| POST | `/api/v1/agents/{id}/reload` | 热重载单个 Agent |
| GET | `/api/v1/agents/{id}/prompt` | 获取 Agent Prompt |

**Agent MCP 管理**：

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/agents/{id}/mcp` | 列出 Agent 启用的 MCP |
| POST | `/api/v1/agents/{id}/mcp/{name}` | 为 Agent 启用 MCP |
| PUT | `/api/v1/agents/{id}/mcp/{name}` | 更新 Agent MCP 配置 |
| DELETE | `/api/v1/agents/{id}/mcp/{name}` | 禁用 MCP |
| GET | `/api/v1/agents/{id}/mcp/available` | 可用 MCP 列表 |

### 3.6 Skills 管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/skills/global` | 全局 Skills 列表 |
| GET | `/api/v1/skills/instance/{agent_id}` | 实例已安装 Skills |
| POST | `/api/v1/skills/install` | 安装 Skill |
| POST | `/api/v1/skills/uninstall` | 卸载 Skill |
| POST | `/api/v1/skills/toggle` | 启用/禁用 Skill |
| POST | `/api/v1/skills/update_content` | 更新 Skill 内容 |
| GET | `/api/v1/skills/detail/{name}` | Skill 详情 |
| GET | `/api/v1/skills/file/{name}/{type}/{file}` | Skill 文件内容 |
| POST | `/api/v1/skills/upload` | 上传新 Skill |

### 3.7 工具管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/tools` | 工具列表（支持分页过滤） |
| GET | `/api/v1/tools/{name}` | 工具详情 |
| POST | `/api/v1/tools/register` | 注册工具 |
| DELETE | `/api/v1/tools/{name}` | 注销工具 |
| POST | `/api/v1/tools/execute` | 执行工具 |
| POST | `/api/v1/tools/{name}/invoke` | 调用指定工具 |
| GET | `/api/v1/tools/schemas` | Claude API 格式 Schema |

**MCP 服务器管理**：

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/tools/mcp/register` | 注册 MCP 服务器 |
| GET | `/api/v1/tools/mcp` | MCP 列表 |
| GET | `/api/v1/tools/mcp/{name}` | MCP 详情 |
| PUT | `/api/v1/tools/mcp/{name}` | 更新 MCP |
| DELETE | `/api/v1/tools/mcp/{name}` | 删除 MCP |

### 3.8 模型管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/models` | 模型列表（query: `type`, `provider`） |

### 3.9 设置

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/settings` | 获取配置 |
| PUT | `/api/v1/settings` | 更新配置 |
| GET | `/api/v1/settings/status` | 配置状态 |
| GET | `/api/v1/settings/schema` | 配置项 Schema |

### 3.10 记忆管理（Mem0）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/mem0/search` | 搜索记忆 |
| GET | `/api/v1/mem0/user/{user_id}` | 用户记忆列表 |
| POST | `/api/v1/mem0/add` | 添加记忆 |
| POST | `/api/v1/mem0/batch-update` | 批量更新记忆 |
| DELETE | `/api/v1/mem0/memory/{id}` | 删除单条 |
| DELETE | `/api/v1/mem0/user/{user_id}` | 重置用户记忆 |

### 3.11 任务调度

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/tasks` | 任务列表 |
| GET | `/api/v1/tasks/{name}` | 任务详情 |
| POST | `/api/v1/tasks/{name}/run` | 手动触发 |
| POST | `/api/v1/tasks/{name}/batch` | 批量触发 |
| GET | `/api/v1/tasks/scheduled/config` | 定时配置 |
| GET | `/api/v1/tasks/scheduled/status` | 调度器状态 |

### 3.12 文档浏览

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/docs/structure` | 文档目录结构 |
| GET | `/api/v1/docs/content/{path}` | 文档内容 |

### 3.13 健康检查

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查 |
| GET | `/health/live` | 存活探针 |
| GET | `/health/metrics` | 系统指标 |

---

## 四、WebSocket 实时语音协议

### 连接地址

```
ws://{host}/api/v1/realtime/ws?model=gpt-4o-realtime-preview&voice=alloy&instructions=...
```

重连：`ws://{host}/api/v1/realtime/ws/{session_id}`

### 客户端 → 服务端

```json
// 文本消息
{ "type": "text", "text": "你好" }

// 追加音频缓冲（Base64 PCM16）
{ "type": "input_audio_buffer.append", "audio": "base64..." }

// 提交音频
{ "type": "input_audio_buffer.commit" }

// 清空音频缓冲
{ "type": "input_audio_buffer.clear" }
```

### 服务端 → 客户端

```json
// 会话创建
{ "type": "session.created", "session": { ... } }

// 会话重连
{ "type": "session.reconnected", "session": { ... } }

// 音频增量（Base64 PCM16）
{ "type": "response.audio.delta", "delta": "base64..." }

// 文本增量
{ "type": "response.text.delta", "delta": "文本..." }

// 语音转录增量
{ "type": "response.audio_transcript.delta", "delta": "文本..." }

// 响应完成
{ "type": "response.done" }

// 语音活动检测
{ "type": "input_audio_buffer.speech_started" }
{ "type": "input_audio_buffer.speech_stopped" }

// 错误
{ "type": "error", "error": { "message": "...", "code": "..." } }
```

### 配套 HTTP 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/realtime/sessions` | 活跃语音会话列表 |
| DELETE | `/api/v1/realtime/sessions/{id}` | 关闭语音会话 |

---

## 五、内容块类型（ContentBlock）

消息内容可包含多种类型的内容块：

| 类型 | 说明 | 关键字段 |
|------|------|----------|
| `text` | 文本 | `text: string` |
| `thinking` | 思考过程 | `thinking: string`, `signature: string` |
| `tool_use` | 工具调用 | `id`, `name`, `input: object` |
| `tool_result` | 工具结果 | `tool_use_id`, `content`, `is_error` |
| `image` | 图片 | `source: { type, media_type, data }` |

---

## 六、前端环境适配

| 环境 | HTTP 基础 URL | WebSocket 地址 |
|------|-------------|---------------|
| Tauri 桌面 | `http://127.0.0.1:18900/api` | `ws://127.0.0.1:18900/api/v1/ws/chat` |
| 浏览器开发 | `/api`（Vite Proxy） | `ws://{host}/api/v1/ws/chat` |

---

## 七、关键数据模型速查

### FileReference（文件附件）

```json
{
  "file_id": "string (可选)",
  "file_url": "string (可选)",
  "file_name": "string",
  "file_type": "MIME type",
  "file_size": 1024
}
```

### UsageResponse（Token 使用统计）

```json
{
  "prompt_tokens": 100,
  "completion_tokens": 200,
  "thinking_tokens": 50,
  "cache_read_tokens": 30,
  "cache_write_tokens": 10,
  "total_tokens": 390,
  "latency": 1.5,
  "llm_calls": 3,
  "model": "claude-sonnet-4-5-20250929"
}
```

### SessionInfo（会话信息）

```json
{
  "session_id": "string",
  "active": true,
  "turns": 5,
  "message_count": 10,
  "has_plan": true,
  "start_time": "2025-01-01T00:00:00Z"
}
```
