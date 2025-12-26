# SSE 事件流协议设计

## 概述

本文档定义了 Zenflux Agent 的 Server-Sent Events (SSE) 事件流协议,用于实时推送 Agent 执行过程中的各类事件。

## SSE 基础格式

SSE 使用以下标准格式:

```
event: <event_type>
data: <json_payload>

```

**注意**: 每个事件后必须有一个空行(`\n\n`)作为分隔符。

## 架构层级

```
User (用户级)
└── Conversation (会话级)
    ├── plan: 执行计划 (跨多轮持久化)
    ├── title: 会话标题
    ├── context: 上下文压缩管理
    └── Message (消息级 - Turn)
        └── Content (内容级 - Block)
```

### 层级说明

1. **User**: 用户身份层,对应一个用户账号
2. **Conversation**: 会话层,对应一个完整的对话会话 (session_id)
   - **plan**: 模型的执行计划,跨多轮持久化 (最多 20 轮)
   - **title**: 会话标题,用于识别和检索
   - **context**: 上下文压缩结果,记录已压缩的 message_id
3. **Message**: 消息层,对应一个对话轮次 (turn),包含 user message 和 assistant message
4. **Content**: 内容层,对应消息内的具体内容块 (thinking, text, tool_use 等)

### Conversation 层面设计原则

#### 1. Plan 管理
- **为什么在 Conversation 层面?** 
  - 一个复杂任务的 plan 可能需要 20 轮对话才能完成
  - Plan 应该跨轮次持久化,避免在每个 message 中重复传递
  - Agent 可以在多轮中逐步执行和更新 plan
  
#### 2. Context 压缩
- **为什么需要?** 
  - 长对话导致 tokens 过多
  - 需要压缩历史消息,保留关键信息
  
- **工作机制**:
  ```
  Original Messages:
  [msg_001, msg_002, msg_003, msg_004, msg_005]
  
  After Compression:
  context: {
    compressed_text: "之前讨论了...",
    message_ids: ["msg_001", "msg_002", "msg_003"]
  }
  
  Next Request:
  [compressed_context] + [msg_004, msg_005] + [new_message]
  ```

## 事件类型定义

### 1. Conversation 级事件

#### 1.1 `conversation_start`
会话开始 (包含初始状态)

```json
{
  "event": "conversation_start",
  "data": {
    "conversation_id": "session_123",
    "user_id": "user_456",
    "title": null,  // 初始为空,首轮后自动生成
    "plan": null,   // 初始为空,需要时创建
    "context": {
      "compressed_text": null,
      "compressed_message_ids": [],
      "total_messages": 0
    },
    "max_turns": 20,
    "timestamp": "2025-12-25T10:00:00Z"
  }
}
```

#### 1.2 `conversation_delta`
会话状态更新 (增量更新)

```json
{
  "event": "conversation_delta",
  "data": {
    "conversation_id": "session_123",
    "delta": {
      "title": "AI技术PPT生成任务",  // 可选: 更新标题
      "summary": {
        "total_turns": 5,
        "total_messages": 10,
        "tool_calls": 8,
        "duration_seconds": 120.5
      }
    },
    "timestamp": "2025-12-25T10:02:00Z"
  }
}
```

#### 1.3 `conversation_plan_created`
🆕 执行计划创建

```json
{
  "event": "conversation_plan_created",
  "data": {
    "conversation_id": "session_123",
    "plan": {
      "goal": "生成一个关于AI技术的专业PPT",
      "required_capabilities": ["ppt_generation", "api_calling"],
      "steps": [
        {
          "index": 0,
          "action": "分析用户需求,确定PPT主题和结构",
          "capability": "task_planning",
          "status": "completed",
          "result": "已确定主题为'AI技术',包含5-7页"
        },
        {
          "index": 1,
          "action": "调用 SlideSpeak API 生成PPT",
          "capability": "api_calling",
          "status": "in_progress",
          "result": null
        },
        {
          "index": 2,
          "action": "下载并返回生成的PPT",
          "capability": "file_operations",
          "status": "pending",
          "result": null
        }
      ],
      "current_step": 1,
      "progress": 0.33
    },
    "timestamp": "2025-12-25T10:00:08Z"
  }
}
```

**说明**:
- Plan 存储在 conversation 层面,跨多轮持久化
- 可能需要 20 轮对话才能完成整个 plan
- 每轮只执行 plan 的一部分步骤

#### 1.4 `conversation_plan_updated`
🆕 执行计划更新

```json
{
  "event": "conversation_plan_updated",
  "data": {
    "conversation_id": "session_123",
    "plan_delta": {
      "steps": {
        "1": {
          "status": "completed",
          "result": "成功调用 SlideSpeak API,task_id: task_abc123"
        },
        "2": {
          "status": "in_progress"
        }
      },
      "current_step": 2,
      "progress": 0.67
    },
    "timestamp": "2025-12-25T10:00:25Z"
  }
}
```

#### 1.5 `conversation_context_compressed`
🆕 上下文压缩完成

```json
{
  "event": "conversation_context_compressed",
  "data": {
    "conversation_id": "session_123",
    "context": {
      "compressed_text": "之前的对话中,用户请求生成一个关于AI技术的PPT,包含机器学习、深度学习等内容。Agent 已完成需求分析,确定了PPT结构。",
      "compressed_message_ids": ["msg_001", "msg_002", "msg_003", "msg_004"],
      "compression_ratio": 0.25,  // 压缩后 tokens 占原始的 25%
      "original_tokens": 2500,
      "compressed_tokens": 625
    },
    "retained_messages": ["msg_005", "msg_006"],  // 保留的最近消息
    "timestamp": "2025-12-25T10:01:30Z"
  }
}
```

**说明**:
- 当上下文过长时自动触发压缩
- 压缩结果保存在 conversation.context
- 后续请求使用: `[compressed_context] + [retained_messages] + [new_message]`
- `compressed_message_ids` 中的消息已被压缩,不再单独发送


### 2. Message 级事件

#### 2.1 `message_start`
消息开始 (包含空的 content 数组)

```json
{
  "event": "message_start",
  "data": {
    "type": "message",
    "id": "msg_abc123",
    "role": "assistant",
    "model": "claude-sonnet-4-5-20250929",
    "content": [],
    "usage": {
      "input_tokens": 1500,
      "output_tokens": 0
    }
  }
}
```

#### 2.2 `message_delta`
消息级更新 (usage, stop_reason 等)

```json
{
  "event": "message_delta",
  "data": {
    "type": "message_delta",
    "delta": {
      "stop_reason": "end_turn",
      "stop_sequence": null
    },
    "usage": {
      "output_tokens": 250
    }
  }
}
```

**⚠️ 重要**: `usage` 中的 token 计数是**累积值**,不是增量!

#### 2.3 `message_stop`
消息结束

```json
{
  "event": "message_stop",
  "data": {
    "type": "message_stop"
  }
}
```

### 3. Content Block 级事件

#### 3.1 `content_block_start`
内容块开始

```json
{
  "event": "content_block_start",
  "data": {
    "type": "content_block_start",
    "index": 0,
    "content_block": {
      "type": "thinking",  // 或 "text", "tool_use"
      "thinking": ""       // 初始为空
    }
  }
}
```

#### 3.2 `content_block_delta`
内容块增量更新

**Thinking Delta:**
```json
{
  "event": "content_block_delta",
  "data": {
    "type": "content_block_delta",
    "index": 0,
    "delta": {
      "type": "thinking_delta",
      "thinking": "让我分析一下这个需求:\n1. "
    }
  }
}
```

**Text Delta:**
```json
{
  "event": "content_block_delta",
  "data": {
    "type": "content_block_delta",
    "index": 1,
    "delta": {
      "type": "text_delta",
      "text": "好的,我来帮你生成"
    }
  }
}
```

**Tool Input JSON Delta:**
```json
{
  "event": "content_block_delta",
  "data": {
    "type": "content_block_delta",
    "index": 2,
    "delta": {
      "type": "input_json_delta",
      "partial_json": "{\"topic\": \"AI"
    }
  }
}
```

**Signature Delta (Extended Thinking):**
```json
{
  "event": "content_block_delta",
  "data": {
    "type": "content_block_delta",
    "index": 0,
    "delta": {
      "type": "signature_delta",
      "signature": "EqQBCgIYAhIM1gbcDa9GJwZA..."
    }
  }
}
```

#### 3.3 `content_block_stop`
内容块结束

```json
{
  "event": "content_block_stop",
  "data": {
    "type": "content_block_stop",
    "index": 0
  }
}
```

### 4. Agent 自定义事件

#### 4.1 `agent_status`
Agent 状态更新

```json
{
  "event": "agent_status",
  "data": {
    "status": "intent_analyzing",  // intent_analyzing, tool_selecting, planning, executing, completed
    "message": "正在分析用户意图...",
    "timestamp": "2025-12-25T10:00:05Z"
  }
}
```

#### 4.2 `intent_analysis`
意图识别结果

```json
{
  "event": "intent_analysis",
  "data": {
    "intent": "create_ppt",
    "confidence": 0.95,
    "entities": {
      "topic": "AI技术",
      "pages": 10,
      "style": "professional"
    },
    "keywords": ["ppt", "生成", "AI"],
    "timestamp": "2025-12-25T10:00:06Z"
  }
}
```

#### 4.3 `tool_selection`
工具筛选结果

```json
{
  "event": "tool_selection",
  "data": {
    "selected_tools": [
      {
        "name": "slidespeak-generator",
        "score": 276,
        "reason": "专业PPT生成需求"
      },
      {
        "name": "web_search",
        "score": 180,
        "reason": "可能需要搜索相关资料"
      }
    ],
    "total_available": 15,
    "timestamp": "2025-12-25T10:00:07Z"
  }
}
```

#### 4.4 `plan_step_start`
🆕 步骤开始执行 (Message 级事件)

```json
{
  "event": "plan_step_start",
  "data": {
    "step_index": 1,
    "action": "调用 SlideSpeak API 生成PPT",
    "capability": "api_calling",
    "message_id": "msg_005",
    "timestamp": "2025-12-25T10:00:20Z"
  }
}
```

**说明**: 
- 这是 message 级事件,表示当前轮次正在执行哪个 plan 步骤
- 与 `conversation_plan_updated` 配合使用

#### 4.5 `plan_step_complete`
🆕 步骤执行完成 (Message 级事件)

```json
{
  "event": "plan_step_complete",
  "data": {
    "step_index": 1,
    "status": "completed",
    "result": "成功调用 SlideSpeak API,task_id: task_abc123",
    "message_id": "msg_005",
    "timestamp": "2025-12-25T10:00:25Z"
  }
}
```

#### 4.6 `tool_call_start`
工具调用开始 (扩展)

```json
{
  "event": "tool_call_start",
  "data": {
    "tool_call_id": "toolu_123",
    "tool_name": "web_search",
    "input": {
      "query": "AI最新发展趋势"
    },
    "timestamp": "2025-12-25T10:00:10Z"
  }
}
```

#### 4.7 `tool_call_complete`
工具调用完成 (扩展)

```json
{
  "event": "tool_call_complete",
  "data": {
    "tool_call_id": "toolu_123",
    "tool_name": "web_search",
    "status": "success",
    "result": {
      "results_count": 5,
      "preview": "找到5条相关搜索结果..."
    },
    "duration_ms": 1250,
    "timestamp": "2025-12-25T10:00:11.25Z"
  }
}
```

#### 4.8 `tool_call_error`
工具调用失败

```json
{
  "event": "tool_call_error",
  "data": {
    "tool_call_id": "toolu_123",
    "tool_name": "web_search",
    "error": {
      "type": "network_error",
      "message": "网络请求超时"
    },
    "timestamp": "2025-12-25T10:00:11Z"
  }
}
```

### 5. 系统事件

#### 5.1 `ping`
心跳事件 (保持连接)

```json
{
  "event": "ping",
  "data": {
    "type": "ping"
  }
}
```

#### 5.2 `error`
错误事件

```json
{
  "event": "error",
  "data": {
    "type": "error",
    "error": {
      "type": "overloaded_error",
      "message": "服务器过载,请稍后重试"
    }
  }
}
```

#### 5.3 `done`
流结束标记

```json
{
  "event": "done",
  "data": {
    "type": "done",
    "timestamp": "2025-12-25T10:02:00Z"
  }
}
```

## 完整事件流示例

### 场景: 用户请求生成一个PPT (多轮交互)

#### 第1轮: 创建 Plan

```
event: conversation_start
data: {"conversation_id": "session_123", "title": null, "plan": null, "context": {...}, "timestamp": "2025-12-25T10:00:00Z"}

event: message_start
data: {"id": "msg_001", "role": "assistant", "content": [], "usage": {"input_tokens": 1500, "output_tokens": 0}}

event: agent_status
data: {"status": "intent_analyzing", "message": "正在分析用户意图..."}

event: intent_analysis
data: {"intent": "create_ppt", "keywords": ["ppt", "生成", "AI"]}

event: tool_selection
data: {"selected_tools": [{"name": "slidespeak-generator", "score": 276}, {"name": "api_calling", "score": 180}]}

event: conversation_plan_created
data: {"plan": {"goal": "生成AI技术PPT", "steps": [...], "current_step": 0}, "timestamp": "..."}

event: conversation_delta
data: {"delta": {"title": "AI技术PPT生成任务"}}

event: plan_step_start
data: {"step_index": 0, "action": "分析用户需求", "message_id": "msg_001"}

event: content_block_start
data: {"index": 0, "content_block": {"type": "thinking", "thinking": ""}}

event: content_block_delta
data: {"index": 0, "delta": {"type": "thinking_delta", "thinking": "用户想要生成PPT,需要:\n1. 分析需求\n2. 调用API\n3. 下载文件"}}

event: content_block_stop
data: {"index": 0}

event: plan_step_complete
data: {"step_index": 0, "status": "completed", "result": "需求分析完成"}

event: conversation_plan_updated
data: {"plan_delta": {"steps": {"0": {"status": "completed"}}, "current_step": 1, "progress": 0.33}}

event: message_stop
data: {"type": "message_stop"}

```

#### 第2轮: 调用 API (异步任务)

```
event: message_start
data: {"id": "msg_002", "role": "assistant", ...}

event: plan_step_start
data: {"step_index": 1, "action": "调用 SlideSpeak API", "capability": "api_calling"}

event: content_block_start
data: {"index": 0, "content_block": {"type": "tool_use", "id": "toolu_123", "name": "api_calling"}}

event: tool_call_start
data: {"tool_call_id": "toolu_123", "tool_name": "api_calling"}

event: content_block_delta
data: {"index": 0, "delta": {"type": "input_json_delta", "partial_json": "{\"url\": \"https://api.slidespeak.co/...\""}}

event: content_block_stop
data: {"index": 0}

event: tool_call_complete
data: {"tool_call_id": "toolu_123", "status": "success", "result": {"task_id": "task_abc123"}, "duration_ms": 2500}

event: plan_step_complete
data: {"step_index": 1, "status": "completed", "result": "API调用成功,task_id: task_abc123"}

event: conversation_plan_updated
data: {"plan_delta": {"steps": {"1": {"status": "completed"}}, "current_step": 2, "progress": 0.67}}

event: message_stop
data: {"type": "message_stop"}

```

#### 第5轮: 上下文压缩 (自动触发)

```
event: conversation_context_compressed
data: {
  "context": {
    "compressed_text": "之前讨论了AI技术PPT生成,已完成需求分析和API调用...",
    "compressed_message_ids": ["msg_001", "msg_002", "msg_003", "msg_004"],
    "compression_ratio": 0.25
  },
  "retained_messages": ["msg_005"],
  "timestamp": "2025-12-25T10:01:30Z"
}

```

#### 第8轮: Plan 完成,会话结束

```
event: plan_step_complete
data: {"step_index": 2, "status": "completed", "result": "PPT已下载到本地"}

event: conversation_plan_updated
data: {"plan_delta": {"current_step": 3, "progress": 1.0, "status": "completed"}}

event: message_stop
data: {"type": "message_stop"}

event: conversation_stop
data: {"conversation_id": "session_123", "final_status": "completed", "summary": {...}}

event: done
data: {"type": "done", "timestamp": "2025-12-25T10:03:00Z"}

```

## 事件顺序规则

### 1. 基本流程

```
conversation_start (包含 title, plan, context)
  │
  ├── [conversation_plan_created] (可选,首轮创建)
  ├── [conversation_delta] (可选,更新 title)
  │
  └── message_start (第1轮)
      ├── [agent_status, intent_analysis, tool_selection] (可选)
      ├── [plan_step_start] (可选,执行某个步骤)
      ├── content_block_start (index=0)
      │   └── content_block_delta (多次)
      │   └── content_block_stop
      ├── content_block_start (index=1)
      │   └── content_block_delta (多次)
      │   └── content_block_stop
      ├── ... (更多 content blocks)
      ├── [plan_step_complete] (可选)
      ├── [conversation_plan_updated] (可选)
      ├── message_delta
      └── message_stop
  │
  └── message_start (第2轮)
      ├── [plan_step_start] (继续执行 plan)
      ├── ...
      └── message_stop
  │
  ├── [conversation_context_compressed] (上下文过长时)
  │
  └── ... (最多 20 轮)
  │
  └── conversation_stop
```

### 2. 规则约束

#### Conversation 层面规则:
1. ✅ **必须**在流开始时发送 `conversation_start` (包含 title, plan, context)
2. ✅ `conversation_plan_created` **只能**发送一次 (首轮创建 plan 时)
3. ✅ `conversation_plan_updated` 可以在任意轮次发送 (更新 plan 进度)
4. ✅ `conversation_context_compressed` 在上下文过长时自动触发
5. ✅ `conversation_delta` 可以在任意时刻更新 title 等元数据
6. ✅ **必须**在流结束时发送 `conversation_stop`

#### Message 层面规则:
1. ✅ **必须**先发送 `message_start`,再发送任何 `content_block_*` 事件
2. ✅ **必须**为每个 content block 发送完整的 `start` → `delta` → `stop` 序列
3. ✅ **必须**在 `message_stop` 前发送 `message_delta` (包含 stop_reason)
4. ✅ `content_block` 的 `index` **必须**从 0 开始连续递增
5. ✅ Extended Thinking 开启时,`thinking` block **必须**是第一个 (index=0)
6. ✅ `tool_use` block **必须**包含 `id` 和 `name`
7. ✅ `thinking` block **必须**包含有效的 `signature` 字段

#### Plan 执行规则:
1. ✅ `plan_step_start` 和 `plan_step_complete` 成对出现
2. ✅ 一个 message 可以执行 plan 的一个或多个步骤
3. ✅ Plan 可以跨多轮 (最多 20 轮) 逐步完成
4. ✅ 每次 `plan_step_complete` 后应该发送 `conversation_plan_updated`

#### 其他规则:
1. ⚠️ `ping` 事件可以在流的任意位置出现
2. ⚠️ Agent 自定义事件 (agent_status, intent_analysis 等) 通常在 `message_start` 之后, 第一个 `content_block_start` 之前

### 3. 错误处理

- 如果在流中间发生错误,发送 `error` 事件,然后发送 `done` 事件结束流
- 部分完成的 content block 可以不发送 `content_block_stop`,直接跳到 `error`

## 客户端实现建议

### JavaScript/TypeScript 示例

```typescript
const eventSource = new EventSource('/api/v1/chat/stream');

// 监听各类事件
eventSource.addEventListener('message_start', (e) => {
  const data = JSON.parse(e.data);
  console.log('消息开始:', data);
});

eventSource.addEventListener('content_block_delta', (e) => {
  const data = JSON.parse(e.data);
  
  if (data.delta.type === 'thinking_delta') {
    // 显示思考过程
    appendThinking(data.delta.thinking);
  } else if (data.delta.type === 'text_delta') {
    // 显示回复文本
    appendContent(data.delta.text);
  } else if (data.delta.type === 'input_json_delta') {
    // 累积工具输入 JSON
    accumulateToolInput(data.delta.partial_json);
  }
});

eventSource.addEventListener('tool_call_complete', (e) => {
  const data = JSON.parse(e.data);
  console.log(`工具 ${data.tool_name} 执行完成, 耗时 ${data.duration_ms}ms`);
});

eventSource.addEventListener('done', (e) => {
  console.log('流结束');
  eventSource.close();
});

eventSource.addEventListener('error', (e) => {
  const data = JSON.parse(e.data);
  console.error('发生错误:', data.error.message);
  eventSource.close();
});
```

### Python 示例

```python
import requests
import json

response = requests.post(
    'http://localhost:8000/api/v1/chat',
    json={'message': '生成一个PPT', 'stream': True},
    stream=True
)

for line in response.iter_lines():
    if line:
        line = line.decode('utf-8')
        if line.startswith('event: '):
            event_type = line[7:]
        elif line.startswith('data: '):
            data = json.loads(line[6:])
            print(f'{event_type}: {data}')
```

## 性能优化建议

### 1. 批量发送

对于频繁的 `content_block_delta` 事件,可以考虑:
- 累积 50-100ms 的内容后再发送
- 或累积 10-20 个字符后再发送
- 平衡实时性和网络开销

### 2. 压缩

对于大量数据:
- 启用 gzip 压缩
- 减少 JSON 中的冗余字段

### 3. 心跳

- `ping` 事件建议每 15-30 秒发送一次
- 防止连接被中间代理关闭

## 与 Claude API 的映射关系

| Claude 事件 | Zenflux 事件 | 层级 | 说明 |
|------------|-------------|------|------|
| `message_start` | `message_start` | Message | 直接映射 |
| `content_block_start` | `content_block_start` | Content | 直接映射 |
| `content_block_delta` | `content_block_delta` | Content | 直接映射,保留所有 delta 类型 |
| `content_block_stop` | `content_block_stop` | Content | 直接映射 |
| `message_delta` | `message_delta` | Message | 直接映射 |
| `message_stop` | `message_stop` | Message | 直接映射 |
| `ping` | `ping` | System | 直接映射 |
| `error` | `error` | System | 直接映射 |
| - | `conversation_start` | **Conversation** | Zenflux 扩展 (会话开始,包含 plan/title/context) |
| - | `conversation_delta` | **Conversation** | Zenflux 扩展 (会话状态更新) |
| - | `conversation_plan_created` | **Conversation** | Zenflux 扩展 (执行计划创建) |
| - | `conversation_plan_updated` | **Conversation** | Zenflux 扩展 (执行计划更新) |
| - | `conversation_context_compressed` | **Conversation** | Zenflux 扩展 (上下文压缩) |
| - | `conversation_stop` | **Conversation** | Zenflux 扩展 (会话结束) |
| - | `agent_status` | Agent | Zenflux 扩展 (Agent 状态) |
| - | `intent_analysis` | Agent | Zenflux 扩展 (意图识别) |
| - | `tool_selection` | Agent | Zenflux 扩展 (工具筛选) |
| - | `plan_step_start` | Agent | Zenflux 扩展 (步骤开始) |
| - | `plan_step_complete` | Agent | Zenflux 扩展 (步骤完成) |
| - | `tool_call_start` | Agent | Zenflux 扩展 (工具执行开始) |
| - | `tool_call_complete` | Agent | Zenflux 扩展 (工具执行完成) |
| - | `tool_call_error` | Agent | Zenflux 扩展 (工具执行失败) |
| - | `done` | System | Zenflux 扩展 (流结束标记) |

## 最佳实践

### 1. Conversation 状态管理

**服务端实现**:
```python
class ConversationState:
    def __init__(self, conversation_id):
        self.conversation_id = conversation_id
        self.title = None
        self.plan = None
        self.context = {
            "compressed_text": None,
            "compressed_message_ids": [],
            "total_messages": 0
        }
        self.messages = []
        self.max_turns = 20
    
    def should_compress_context(self):
        """判断是否需要压缩上下文"""
        # 策略: 超过 10 条消息或 tokens > 10000
        return len(self.messages) > 10 or self.total_tokens() > 10000
    
    def compress_context(self):
        """压缩上下文"""
        # 保留最近 3 条消息
        retained_count = 3
        to_compress = self.messages[:-retained_count]
        retained = self.messages[-retained_count:]
        
        # 使用 LLM 压缩
        compressed_text = llm.summarize(to_compress)
        compressed_ids = [msg.id for msg in to_compress]
        
        self.context = {
            "compressed_text": compressed_text,
            "compressed_message_ids": compressed_ids,
            "total_messages": len(self.messages)
        }
        
        return {
            "context": self.context,
            "retained_messages": [msg.id for msg in retained]
        }
    
    def build_llm_messages(self, new_user_message):
        """构建发送给 LLM 的消息列表"""
        messages = []
        
        # 1. 添加压缩的上下文 (如果有)
        if self.context["compressed_text"]:
            messages.append({
                "role": "user",
                "content": f"[上下文摘要] {self.context['compressed_text']}"
            })
        
        # 2. 添加未压缩的消息
        compressed_ids = set(self.context["compressed_message_ids"])
        for msg in self.messages:
            if msg.id not in compressed_ids:
                messages.append(msg)
        
        # 3. 添加新消息
        messages.append(new_user_message)
        
        return messages
```

**客户端实现**:
```typescript
class ConversationManager {
  private conversationState = {
    id: null,
    title: null,
    plan: null,
    context: null,
    messages: []
  };
  
  handleConversationStart(data) {
    this.conversationState = {
      id: data.conversation_id,
      title: data.title,
      plan: data.plan,
      context: data.context,
      messages: []
    };
  }
  
  handleConversationPlanCreated(data) {
    this.conversationState.plan = data.plan;
    this.updatePlanUI();
  }
  
  handleConversationPlanUpdated(data) {
    // 合并 plan_delta
    Object.assign(this.conversationState.plan, data.plan_delta);
    this.updatePlanUI();
  }
  
  handleConversationContextCompressed(data) {
    this.conversationState.context = data.context;
    // 从 UI 中移除被压缩的消息
    const compressedIds = new Set(data.context.compressed_message_ids);
    this.conversationState.messages = this.conversationState.messages.filter(
      msg => !compressedIds.has(msg.id)
    );
    // 显示压缩提示
    this.showContextCompressedBanner(data.context.compression_ratio);
  }
}
```

### 2. Plan 跨轮执行

```python
async def execute_plan_step(conversation_state, step_index):
    """执行 plan 的某个步骤"""
    step = conversation_state.plan["steps"][step_index]
    
    # 发送步骤开始事件
    yield sse_event("plan_step_start", {
        "step_index": step_index,
        "action": step["action"],
        "capability": step["capability"]
    })
    
    # 执行步骤 (可能调用多个工具)
    result = await execute_step_logic(step)
    
    # 发送步骤完成事件
    yield sse_event("plan_step_complete", {
        "step_index": step_index,
        "status": "completed" if result.success else "failed",
        "result": result.summary
    })
    
    # 更新 conversation 层面的 plan
    conversation_state.plan["steps"][step_index]["status"] = "completed"
    conversation_state.plan["current_step"] = step_index + 1
    conversation_state.plan["progress"] = (step_index + 1) / len(conversation_state.plan["steps"])
    
    yield sse_event("conversation_plan_updated", {
        "plan_delta": {
            "steps": {
                str(step_index): {"status": "completed", "result": result.summary}
            },
            "current_step": step_index + 1,
            "progress": conversation_state.plan["progress"]
        }
    })
```

## 版本历史

- **v1.1** (2025-12-26): 
  - 🆕 添加 Conversation 层面的 plan, title, context 管理
  - 🆕 添加 `conversation_plan_created/updated` 事件
  - 🆕 添加 `conversation_context_compressed` 事件
  - 🆕 添加 `plan_step_start/complete` 事件
  - 📝 更新完整事件流示例
  - 📝 添加最佳实践和实现建议

- **v1.0** (2025-12-25): 初始版本,定义核心事件协议

## 参考资料

- [Claude Streaming Messages](https://platform.claude.com/docs/en/build-with-claude/streaming)
- [MDN: Server-sent events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events)
- [SSE Specification](https://html.spec.whatwg.org/multipage/server-sent-events.html)

