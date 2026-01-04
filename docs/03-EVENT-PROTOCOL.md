# 统一事件协议

> 📅 **最后更新**: 2025-12-30  
> 🎯 **适用版本**: V4.0  
> ✅ **实现状态**: 已完成

## 1. 概述

本文档定义了 Zenflux Agent 的**统一事件协议**，适用于：

- **SSE (Server-Sent Events)**: 单向实时推送
- **WebSocket**: 双向实时通信

### 1.1 设计目标

| 目标 | 说明 |
|------|------|
| **统一格式** | SSE 和 WebSocket 使用相同的事件结构 |
| **分层清晰** | 5 层事件架构，职责明确 |
| **可扩展** | 易于添加新事件类型 |
| **可靠性** | 支持断线重连、事件去重 |
| **Claude 兼容** | 核心事件与 Claude Streaming API 一致 |

### 1.2 架构层级

```
Session（运行会话）
├── User（用户）
│   └── Conversation（对话会话）- plan, title, context
│       └── Message（消息/Turn）
│           └── Content（内容块）- thinking, text, tool_use
└── System（系统）- error, ping, done
```

---

## 2. 传输协议

### 2.1 SSE 格式

```
event: <event_type>
data: <json_payload>

```

**注意**: 每个事件后必须有一个空行（`\n\n`）作为分隔符。

**示例**:
```
event: content_delta
data: {"event_uuid":"a1b2c3","seq":5,"type":"content_delta","session_id":"sess_123","conversation_id":"conv_456","timestamp":"2025-12-30T10:00:00Z","data":{"index":0,"delta":{"type":"text","text":"好的"}}}

```

### 2.2 WebSocket 格式

WebSocket 使用纯 JSON 格式，每条消息是一个完整的事件对象：

```json
{
  "event_uuid": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "seq": 5,
  "type": "content_delta",
  "session_id": "sess_123",
  "conversation_id": "conv_456",
  "timestamp": "2025-12-30T10:00:00Z",
  "data": {
    "index": 0,
    "delta": {
      "type": "text",
      "text": "好的"
    }
  }
}
```

### 2.3 统一事件结构

无论使用哪种传输协议，所有事件都遵循统一结构：

```typescript
interface Event {
  // === 事件标识 ===
  event_uuid: string;        // 全局唯一 UUID
  seq: number;               // Session 内序号（1, 2, 3...）
  type: string;              // 事件类型
  
  // === 通用上下文 ===
  session_id: string;        // Session ID（必选）
  conversation_id?: string;  // Conversation ID（可选）
  timestamp: string;         // ISO 8601 时间戳
  
  // === 事件数据 ===
  data: object;              // 事件特定数据
}
```

**字段说明**:

| 字段 | 类型 | 必选 | 说明 |
|------|------|------|------|
| `event_uuid` | string | ✅ | 全局唯一标识符，用于去重 |
| `seq` | number | ✅ | Session 内递增序号（1, 2, 3...），用于断线重连 |
| `type` | string | ✅ | 事件类型名称 |
| `session_id` | string | ✅ | 当前运行会话 ID |
| `conversation_id` | string | ⚪ | 对话会话 ID（Conversation 级及以下事件必选）|
| `timestamp` | string | ✅ | ISO 8601 格式时间戳 |
| `data` | object | ✅ | 事件特定数据 |

---

## 3. 事件类型定义

### 3.1 事件分类总览

| 层级 | 事件类型 | 说明 |
|------|----------|------|
| **Session** | `session_start`, `session_stopped`, `session_end`, `ping` | 运行会话生命周期 |
| **User** | `user_action`, `user_preference_update` | 用户行为追踪 |
| **Conversation** | `conversation_start`, `conversation_delta`, `conversation_plan_*`, `conversation_context_compressed`, `conversation_stop` | 对话会话管理 |
| **Message** | `message_start`, `message_delta`, `message_stop`, `tool_call_*`, `plan_step_*` | 消息轮次管理 |
| **Content** | `content_start`, `content_delta`, `content_stop` | 内容块流式传输 |
| **System** | `error`, `done`, `agent_status`, `plan_update` | 系统级事件 |

---

### 3.2 Session 级事件

#### `session_start`

Session 开始，首个事件。

```json
{
  "type": "session_start",
  "data": {
    "session_id": "sess_123",
    "user_id": "user_456",
    "conversation_id": "conv_789",
    "timestamp": "2025-12-30T10:00:00Z"
  }
}
```

#### `session_stopped`

Session 被用户主动停止。

```json
{
  "type": "session_stopped",
  "data": {
    "session_id": "sess_123",
    "reason": "user_requested",
    "stopped_at": "2025-12-30T10:05:00Z"
  }
}
```

**reason 枚举**: `user_requested` | `timeout` | `error`

#### `session_end`

Session 正常结束。

```json
{
  "type": "session_end",
  "data": {
    "session_id": "sess_123",
    "status": "completed",
    "duration_ms": 30000
  }
}
```

**status 枚举**: `completed` | `failed` | `cancelled`

#### `ping`

心跳事件，保持连接活跃。

```json
{
  "type": "ping",
  "data": {
    "type": "ping"
  }
}
```

---

### 3.3 Conversation 级事件

#### `conversation_start`

对话会话开始。

```json
{
  "type": "conversation_start",
  "data": {
    "conversation_id": "conv_789",
    "title": "新对话",
    "created_at": "2025-12-30T10:00:00Z",
    "metadata": {
      "plan": null,
      "context": {
        "compressed_text": null,
        "compressed_message_ids": [],
        "total_messages": 0
      }
    }
  }
}
```

#### `conversation_delta`

对话会话增量更新（如标题更新）。

```json
{
  "type": "conversation_delta",
  "data": {
    "conversation_id": "conv_789",
    "delta": {
      "title": "AI技术讨论",
      "summary": {
        "total_turns": 5,
        "total_messages": 10,
        "tool_calls": 8
      }
    }
  }
}
```

#### `conversation_plan_created`

执行计划创建（首次创建 plan 时触发）。

```json
{
  "type": "conversation_plan_created",
  "data": {
    "conversation_id": "conv_789",
    "plan": {
      "goal": "生成一个关于AI技术的专业PPT",
      "required_capabilities": ["ppt_generation"],
      "steps": [
        {
          "index": 0,
          "action": "分析用户需求",
          "capability": "task_planning",
          "status": "pending",
          "result": null
        },
        {
          "index": 1,
          "action": "调用 SlideSpeak API",
          "capability": "api_calling",
          "status": "pending",
          "result": null
        }
      ],
      "current_step": 0,
      "progress": 0.0
    }
  }
}
```

#### `conversation_plan_updated`

执行计划更新（步骤完成/失败时触发）。

```json
{
  "type": "conversation_plan_updated",
  "data": {
    "conversation_id": "conv_789",
    "plan_delta": {
      "steps": {
        "0": {
          "status": "completed",
          "result": "已确定PPT主题和结构"
        },
        "1": {
          "status": "in_progress"
        }
      },
      "current_step": 1,
      "progress": 0.33
    }
  }
}
```

#### `conversation_context_compressed`

上下文压缩完成（tokens 过多时自动触发）。

```json
{
  "type": "conversation_context_compressed",
  "data": {
    "conversation_id": "conv_789",
    "context": {
      "compressed_text": "之前讨论了AI技术PPT生成...",
      "compressed_message_ids": ["msg_001", "msg_002", "msg_003"],
      "compression_ratio": 0.25,
      "original_tokens": 2500,
      "compressed_tokens": 625
    },
    "retained_messages": ["msg_004", "msg_005"]
  }
}
```

#### `conversation_stop`

对话会话结束。

```json
{
  "type": "conversation_stop",
  "data": {
    "conversation_id": "conv_789",
    "final_status": "completed",
    "summary": {
      "total_turns": 8,
      "tool_calls": 5
    }
  }
}
```

---

### 3.4 Message 级事件

#### `message_start`

消息开始（符合 Claude API 标准）。

```json
{
  "type": "message_start",
  "data": {
    "message": {
      "id": "msg_abc123",
      "type": "message",
      "role": "assistant",
      "content": [],
      "model": "claude-sonnet-4-5-20250929",
      "stop_reason": null,
      "stop_sequence": null,
      "usage": {
        "input_tokens": 0,
        "output_tokens": 0
      }
    }
  }
}
```

#### `message_delta`

消息级增量更新。

```json
{
  "type": "message_delta",
  "data": {
    "delta": {
      "stop_reason": "end_turn"
    },
    "usage": {
      "output_tokens": 250
    }
  }
}
```

**⚠️ 注意**: `usage.output_tokens` 是**累积值**，不是增量！

#### `message_stop`

消息结束。

```json
{
  "type": "message_stop",
  "data": {}
}
```

#### `tool_call_start`

工具调用开始。

```json
{
  "type": "tool_call_start",
  "data": {
    "tool_call_id": "toolu_123",
    "tool_name": "web_search",
    "input": {
      "query": "AI最新发展趋势"
    }
  }
}
```

#### `tool_call_complete`

工具调用完成。

```json
{
  "type": "tool_call_complete",
  "data": {
    "tool_call_id": "toolu_123",
    "tool_name": "web_search",
    "status": "success",
    "result": {
      "results_count": 5,
      "preview": "找到5条相关结果..."
    },
    "duration_ms": 1250
  }
}
```

#### `tool_call_error`

工具调用失败。

```json
{
  "type": "tool_call_error",
  "data": {
    "tool_call_id": "toolu_123",
    "tool_name": "web_search",
    "error": {
      "type": "network_error",
      "message": "网络请求超时"
    }
  }
}
```

#### `plan_step_start`

计划步骤开始执行。

```json
{
  "type": "plan_step_start",
  "data": {
    "step_index": 1,
    "action": "调用 SlideSpeak API",
    "capability": "api_calling",
    "message_id": "msg_005"
  }
}
```

#### `plan_step_complete`

计划步骤执行完成。

```json
{
  "type": "plan_step_complete",
  "data": {
    "step_index": 1,
    "status": "completed",
    "result": "成功生成PPT",
    "message_id": "msg_005"
  }
}
```

---

### 3.5 Content 级事件

Content 级事件用于**流式传输**内容块，与 Claude Streaming API 完全兼容。

#### `content_start`

内容块开始。

```json
{
  "type": "content_start",
  "data": {
    "index": 0,
    "type": "thinking"
  }
}
```

**Content Block 类型**:
- `thinking`: Extended Thinking 思考内容
- `text`: 普通文本回复
- `tool_use`: 工具调用
- `tool_result`: 工具执行结果

#### `content_delta`

内容块增量更新。

**Thinking Delta**:
```json
{
  "type": "content_delta",
  "data": {
    "index": 0,
    "delta": {
      "type": "thinking",
      "text": "让我分析一下这个需求..."
    }
  }
}
```

**Text Delta**:
```json
{
  "type": "content_delta",
  "data": {
    "index": 1,
    "delta": {
      "type": "text",
      "text": "好的，我来帮你生成"
    }
  }
}
```

**Tool Input Delta**:
```json
{
  "type": "content_delta",
  "data": {
    "index": 2,
    "delta": {
      "type": "input_json_delta",
      "partial_json": "{\"topic\": \"AI"
    }
  }
}
```

**Signature Delta (Extended Thinking)**:
```json
{
  "type": "content_delta",
  "data": {
    "index": 0,
    "delta": {
      "type": "signature_delta",
      "signature": "EqQBCgIYAhIM1gbcDa9GJwZA..."
    }
  }
}
```

#### `content_stop`

内容块结束。

```json
{
  "type": "content_stop",
  "data": {
    "index": 0
  }
}
```

---

### 3.6 System 级事件

#### `error`

错误事件。

```json
{
  "type": "error",
  "data": {
    "error": {
      "type": "overloaded_error",
      "message": "服务器过载，请稍后重试"
    }
  }
}
```

**错误类型枚举**:
- `network_error`: 网络错误
- `timeout_error`: 超时错误
- `overloaded_error`: 服务过载
- `internal_error`: 内部错误
- `validation_error`: 参数验证错误

#### `done`

流结束标记（最后一个事件）。

```json
{
  "type": "done",
  "data": {
    "type": "done"
  }
}
```

#### `agent_status`

Agent 状态更新。

```json
{
  "type": "agent_status",
  "data": {
    "status": "intent_analyzing",
    "message": "正在分析用户意图..."
  }
}
```

**status 枚举**:
- `intent_analyzing`: 分析意图
- `tool_selecting`: 选择工具
- `planning`: 制定计划
- `executing`: 执行中
- `completed`: 已完成

#### `plan_update`

计划更新事件（内部使用，通知 ChatService）。

```json
{
  "type": "plan_update",
  "data": {
    "plan": {
      "goal": "...",
      "steps": [...],
      "current_step": 1,
      "progress": 0.5
    }
  }
}
```

---

## 4. 完整事件流示例

### 4.1 简单对话流程

```
event: session_start
data: {"event_uuid":"uuid-1","seq":1,"type":"session_start","session_id":"sess_123",...}

event: conversation_start
data: {"event_uuid":"uuid-2","seq":2,"type":"conversation_start",...}

event: message_start
data: {"event_uuid":"uuid-3","seq":3,"type":"message_start",...}

event: content_start
data: {"event_uuid":"uuid-4","seq":4,"type":"content_start","data":{"index":0,"type":"text"}}

event: content_delta
data: {"event_uuid":"uuid-5","seq":5,"type":"content_delta","data":{"index":0,"delta":{"type":"text","text":"好的"}}}

event: content_delta
data: {"event_uuid":"uuid-6","seq":6,"type":"content_delta","data":{"index":0,"delta":{"type":"text","text":"，我来"}}}

event: content_delta
data: {"event_uuid":"uuid-7","seq":7,"type":"content_delta","data":{"index":0,"delta":{"type":"text","text":"帮你处理"}}}

event: content_stop
data: {"event_uuid":"uuid-8","seq":8,"type":"content_stop","data":{"index":0}}

event: message_delta
data: {"event_uuid":"uuid-9","seq":9,"type":"message_delta","data":{"delta":{"stop_reason":"end_turn"},"usage":{"output_tokens":15}}}

event: message_stop
data: {"event_uuid":"uuid-10","seq":10,"type":"message_stop","data":{}}

event: done
data: {"event_uuid":"uuid-11","seq":11,"type":"done","data":{"type":"done"}}

```

### 4.2 工具调用流程

```
event: message_start
data: {...}

event: content_start
data: {"data":{"index":0,"type":"thinking"}}

event: content_delta
data: {"data":{"index":0,"delta":{"type":"thinking","text":"需要搜索相关资料..."}}}

event: content_stop
data: {"data":{"index":0}}

event: content_start
data: {"data":{"index":1,"content_block":{"type":"tool_use","id":"toolu_123","name":"web_search","input":{}}}}

event: content_delta
data: {"data":{"index":1,"delta":{"type":"input_json_delta","partial_json":"{\"query\": \"AI技术\"}"}}}

event: content_stop
data: {"data":{"index":1}}

event: tool_call_start
data: {"data":{"tool_call_id":"toolu_123","tool_name":"web_search","input":{"query":"AI技术"}}}

event: tool_call_complete
data: {"data":{"tool_call_id":"toolu_123","tool_name":"web_search","status":"success","result":{...},"duration_ms":1200}}

event: content_start
data: {"data":{"index":2,"content_block":{"type":"tool_result","tool_use_id":"toolu_123"}}}

event: content_stop
data: {"data":{"index":2}}

event: message_delta
data: {"data":{"delta":{"stop_reason":"tool_use"}}}

event: message_stop
data: {...}

```

### 4.3 Plan 执行流程（多轮）

```
# === 第1轮：创建 Plan ===

event: conversation_start
data: {...}

event: message_start
data: {...}

event: content_start
data: {"data":{"index":0,"content_block":{"type":"tool_use","id":"toolu_plan","name":"plan_todo",...}}}

event: content_delta
data: {"data":{"index":0,"delta":{"type":"input_json_delta","partial_json":"{\"operation\":\"create_plan\",...}"}}}

event: content_stop
data: {...}

event: conversation_plan_created
data: {"data":{"conversation_id":"conv_789","plan":{"goal":"生成PPT","steps":[...],"progress":0}}}

event: message_stop
data: {...}

# === 第2轮：执行步骤 ===

event: message_start
data: {...}

event: plan_step_start
data: {"data":{"step_index":0,"action":"分析需求",...}}

event: content_start
data: {"data":{"index":0,"type":"text"}}

event: content_delta
data: {"data":{"index":0,"delta":{"type":"text","text":"我已分析完需求..."}}}

event: content_stop
data: {...}

event: plan_step_complete
data: {"data":{"step_index":0,"status":"completed","result":"需求分析完成"}}

event: conversation_plan_updated
data: {"data":{"plan_delta":{"current_step":1,"progress":0.5,"steps":{"0":{"status":"completed"}}}}}

event: message_stop
data: {...}

```

---

## 5. 事件顺序规则

### 5.1 必须遵守的规则

#### Session 层面
1. ✅ `session_start` 必须是**第一个事件**
2. ✅ `done` 必须是**最后一个事件**

#### Conversation 层面
1. ✅ `conversation_start` 必须在 `message_start` **之前**
2. ✅ `conversation_plan_created` **只能发送一次**（首轮创建 plan 时）
3. ✅ `conversation_stop` 必须在所有 `message_stop` **之后**

#### Message 层面
1. ✅ `message_start` 必须在任何 `content_*` **之前**
2. ✅ `message_stop` 必须在所有 `content_stop` **之后**
3. ✅ `message_delta`（含 stop_reason）必须在 `message_stop` **之前**

#### Content 层面
1. ✅ 每个 content block 必须有完整的 `start` → `delta` → `stop` 序列
2. ✅ `index` 必须从 0 开始连续递增
3. ✅ Extended Thinking 的 `thinking` block 必须是 **index=0**

### 5.2 规范的事件流

```
session_start
  │
  └── conversation_start
      │
      ├── [conversation_plan_created] (可选，首轮)
      ├── [conversation_delta] (可选)
      │
      └── message_start (第1轮)
          ├── [agent_status] (可选)
          ├── content_start (index=0)
          │   └── content_delta (多次)
          │   └── content_stop
          ├── content_start (index=1)
          │   └── ...
          ├── [tool_call_start] (可选)
          ├── [tool_call_complete] (可选)
          ├── [conversation_plan_updated] (可选)
          ├── message_delta
          └── message_stop
      │
      └── message_start (第2轮)
          └── ...
      │
      ├── [conversation_context_compressed] (可选)
      │
      └── conversation_stop
  │
  └── done
```

### 5.3 错误处理

- 发生错误时，发送 `error` 事件，然后发送 `done` 结束
- 部分完成的 content block 可以跳过 `content_stop`，直接发送 `error`

---

## 6. 断线重连机制

### 6.1 重连流程

```
┌──────────────────────────────────────────────────────────┐
│                     断线重连流程                           │
├──────────────────────────────────────────────────────────┤
│                                                          │
│  1. 客户端检测到连接断开                                   │
│     ↓                                                    │
│  2. 记录最后收到的事件 seq                                 │
│     ↓                                                    │
│  3. 尝试重新连接                                          │
│     ↓                                                    │
│  4. 请求：GET /api/v1/chat/stream/{session_id}?after=N   │
│     ↓                                                    │
│  5. 服务端从 Redis 获取 seq > N 的事件                    │
│     ↓                                                    │
│  6. 发送错过的事件 → 继续实时流                            │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

### 6.2 客户端实现

```typescript
class EventStreamClient {
  private lastSeq: number = 0;
  private sessionId: string;
  private eventSource: EventSource | null = null;
  
  connect(sessionId: string, afterSeq?: number) {
    this.sessionId = sessionId;
    const url = afterSeq 
      ? `/api/v1/chat/stream/${sessionId}?after=${afterSeq}`
      : `/api/v1/chat/stream/${sessionId}`;
    
    this.eventSource = new EventSource(url);
    
    this.eventSource.onmessage = (event) => {
      const data = JSON.parse(event.data);
      
      // 更新 lastSeq（用于重连）
      if (data.seq) {
        this.lastSeq = Math.max(this.lastSeq, data.seq);
      }
      
      // 去重（防止重复事件）
      if (data.seq <= this.lastSeq && !this.isFirstConnect) {
        console.log(`跳过重复事件: seq=${data.seq}`);
        return;
      }
      
      this.handleEvent(data);
    };
    
    this.eventSource.onerror = () => {
      console.log('连接断开，尝试重连...');
      setTimeout(() => this.reconnect(), 1000);
    };
  }
  
  reconnect() {
    // 从最后一个 seq 之后重新获取
    this.connect(this.sessionId, this.lastSeq);
  }
}
```

### 6.3 服务端实现

```python
@router.get("/stream/{session_id}")
async def stream_events(
    session_id: str,
    after: Optional[int] = Query(None, description="从哪个 seq 之后开始")
):
    """
    SSE 事件流端点
    
    支持断线重连：传入 after 参数获取错过的事件
    """
    async def event_generator():
        # 1. 如果有 after 参数，先发送错过的事件
        if after is not None:
            missed_events = redis.get_events(session_id, after_id=after)
            for event in missed_events:
                yield format_sse_event(event)
        
        # 2. 继续实时流
        async for event in redis.stream_events(session_id, after_id=after):
            yield format_sse_event(event)
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream"
    )
```

---

## 7. 代码实现

### 7.1 文件结构

```
core/events/
├── __init__.py              # 模块入口
├── base.py                  # BaseEventManager + EventStorage Protocol
├── manager.py               # EventManager（统一入口）
├── session_events.py        # SessionEventManager
├── user_events.py           # UserEventManager
├── conversation_events.py   # ConversationEventManager
├── message_events.py        # MessageEventManager
├── content_events.py        # ContentEventManager
└── system_events.py         # SystemEventManager
```

### 7.2 EventStorage 协议

```python
class EventStorage(Protocol):
    """事件存储协议（抽象接口）"""
    
    def generate_session_seq(self, session_id: str) -> int:
        """生成 session 内的事件序号（从 1 开始）"""
        ...
    
    def get_session_context(self, session_id: str) -> Dict[str, Any]:
        """获取 session 上下文（conversation_id 等）"""
        ...
    
    def buffer_event(self, session_id: str, event_data: Dict[str, Any]) -> None:
        """缓冲事件"""
        ...
    
    def update_heartbeat(self, session_id: str) -> None:
        """更新心跳"""
        ...
```

**支持的实现**:
- `RedisSessionManager`: 生产环境，使用 Redis 存储
- `MemoryEventStorage`: 测试环境，内存存储
- `WebSocketEventStorage`: 未来扩展，WebSocket 直接推送

### 7.3 使用示例

```python
from core.events import create_event_manager
from services.redis_manager import get_redis_manager

# 1. 创建 EventManager
redis = get_redis_manager()
events = create_event_manager(redis)

# 2. 发送各层级事件
async def process_message(session_id: str, conversation_id: str):
    # Session 级
    await events.session.emit_session_start(
        session_id=session_id,
        user_id="user_123",
        conversation_id=conversation_id
    )
    
    # Conversation 级
    await events.conversation.emit_conversation_start(
        session_id=session_id,
        conversation={"id": conversation_id, "title": "新对话"}
    )
    
    # Message 级
    await events.message.emit_message_start(
        session_id=session_id,
        message_id="msg_001",
        model="claude-sonnet-4-5-20250929"
    )
    
    # Content 级（流式）
    await events.content.emit_content_start(
        session_id=session_id,
        index=0,
        block_type="text"
    )
    
    await events.content.emit_text_delta(
        session_id=session_id,
        index=0,
        text="好的，我来帮你处理"
    )
    
    await events.content.emit_content_stop(
        session_id=session_id,
        index=0
    )
    
    # Message 结束
    await events.message.emit_message_delta(
        session_id=session_id,
        stop_reason="end_turn",
        output_tokens=15
    )
    
    await events.message.emit_message_stop(session_id=session_id)
    
    # System 级
    await events.system.emit_done(session_id=session_id)
```

---

## 8. WebSocket 扩展（规划中）

### 8.1 双向通信设计

```
┌─────────────────────────────────────────────────────────┐
│                    WebSocket 协议                        │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  客户端 → 服务端（请求）                                  │
│  ┌─────────────────────────────────────────────────┐   │
│  │ { "action": "send_message",                      │   │
│  │   "payload": { "content": "生成PPT" } }          │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
│  服务端 → 客户端（事件流）                               │
│  ┌─────────────────────────────────────────────────┐   │
│  │ { "event_uuid": "...", "seq": 1,                 │   │
│  │   "type": "content_delta", "data": {...} }       │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

### 8.2 客户端发送消息格式

```json
{
  "action": "send_message",
  "payload": {
    "content": "用户消息内容",
    "conversation_id": "conv_789",
    "attachments": []
  }
}
```

```json
{
  "action": "stop_session",
  "payload": {
    "session_id": "sess_123"
  }
}
```

### 8.3 实现优先级

| 优先级 | 功能 | 状态 |
|--------|------|------|
| P0 | SSE 单向推送 | ✅ 已完成 |
| P1 | WebSocket 单向推送 | ⏳ 规划中 |
| P2 | WebSocket 双向通信 | ⏳ 规划中 |

---

## 9. 最佳实践

### 9.1 ✅ 应该做的

```python
# 1. 使用 EventManager 统一发送事件
await events.content.emit_text_delta(session_id, index=0, text="...")

# 2. 利用便捷方法
await events.content.emit_thinking_delta(session_id, index=0, thinking_text="...")
await events.content.emit_tool_use(session_id, index=1, tool_id="...", tool_name="...", tool_input={})

# 3. 在 Service 层集中管理事件逻辑
class ChatService:
    async def send_status(self, session_id: str, status: str):

# 4. 使用类型提示
from core.events import EventManager
events: EventManager = create_event_manager(redis)
```

### 9.2 ❌ 不应该做的

```python
# 1. 不要绕过 EventManager 直接操作 Redis
redis.buffer_event(...)  # ❌

# 2. 不要忘记 await
events.content.emit_text_delta(...)  # ❌ 不会生效

# 3. 不要手动构建事件
event = {"type": "content_delta", ...}  # ❌
redis.buffer_event(event)

# 4. 不要在循环中发送过多事件（批量发送）
for char in text:
    await events.content.emit_text_delta(session_id, index, char)  # ❌ 性能差

# 应该累积后批量发送
await events.content.emit_text_delta(session_id, index, text)  # ✅
```

### 9.3 性能优化

| 策略 | 说明 |
|------|------|
| **批量发送** | 累积 50-100ms 内容后再发送 |
| **事件压缩** | 启用 gzip 压缩大量数据 |
| **心跳间隔** | 15-30 秒发送一次 ping |
| **事件缓冲** | Redis 只保留最近 1000 个事件 |
| **TTL 管理** | Session 完成后 60 秒自动清理 |

---

## 10. 与 Claude API 的映射

### 10.1 核心事件映射

| Claude 事件 | Zenflux 事件 | 层级 |
|------------|--------------|------|
| `message_start` | `message_start` | Message |
| `content_block_start` | `content_start` | Content |
| `content_block_delta` | `content_delta` | Content |
| `content_block_stop` | `content_stop` | Content |
| `message_delta` | `message_delta` | Message |
| `message_stop` | `message_stop` | Message |
| `ping` | `ping` | System |
| `error` | `error` | System |

### 10.2 Zenflux 扩展事件

| 事件 | 层级 | Claude 无 |
|------|------|-----------|
| `session_start/stop/end` | Session | ✅ |
| `conversation_*` | Conversation | ✅ |
| `user_*` | User | ✅ |
| `tool_call_*` | Message | ✅ |
| `plan_step_*` | Message | ✅ |
| `agent_status` | System | ✅ |
| `plan_update` | System | ✅ |

---

## 11. 版本历史

- **v2.0** (2025-12-30):
  - 🔄 合并 `07-EVENT-MANAGER.md` 和 `03-SSE-EVENT-PROTOCOL.md`
  - 🆕 统一 SSE 和 WebSocket 事件格式
  - 🆕 添加 `event_uuid` 和 `seq` 双标识符
  - 🆕 完善断线重连机制
  - 🆕 添加 WebSocket 扩展规划
  - 📝 完善代码实现章节

- **v1.2** (2025-12-28):
  - 重构事件触发机制
  - 添加 5 层事件架构

- **v1.0** (2025-12-25):
  - 初始版本

---

## 12. 相关文档

| 文档 | 说明 |
|------|------|
| [00-ARCHITECTURE-V4.md](./00-ARCHITECTURE-V4.md) | V4.0 完整架构 |
| [01-MEMORY-PROTOCOL.md](./01-MEMORY-PROTOCOL.md) | Memory-First 协议 |
| [04-SSE-CONNECTION-MANAGEMENT.md](./04-SSE-CONNECTION-MANAGEMENT.md) | SSE 连接管理与断线重连 |

