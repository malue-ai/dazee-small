# ZenO SSE 数据规范 v2.0.1

## 快速开始

```bash
# 流式聊天（默认 Zeno 格式）
curl -N -X POST "http://localhost:8000/api/v1/chat?format=zeno" \
  -H "Content-Type: application/json" \
  -d '{"message": "你好", "userId": "test_user"}'
```

## 事件类型

| 事件类型 | 说明 |
|---------|------|
| `message.assistant.start` | 消息开始 |
| `message.assistant.delta` | 内容增量（包含 `delta.type`） |
| `message.assistant.done` | 消息完成 |
| `message.assistant.error` | 发生错误 |

## Delta 类型

`message.assistant.delta` 事件中 `delta.type` 的可选值：

| delta.type | 说明 | content 示例 |
|------------|------|-------------|
| `thinking` | 思考过程 | `"让我分析一下..."` |
| `response` | 回复内容 | `"你好！我是..."` |
| `progress` | 任务进度 | `{"title":"生成PPT","current":1,"total":3}` |
| `intent` | 意图识别 | `{"intent_id":1,"intent_name":"通用对话"}` |
| `preface` | 序言 | `"好的，我来帮你..."` |
| `files` | 文件列表 | `[{"name":"output.pptx","url":"..."}]` |
| `clue` | 确认请求 | `{"tasks":[{"id":"1","text":"确认执行?"}]}` |
| `recommended` | 推荐问题 | `["还想了解什么?","继续深入?"]` |
| `sql` | SQL 语句 | `"SELECT * FROM users"` |
| `data` | 查询数据 | `[{"id":1,"name":"张三"}]` |
| `chart` | 图表配置 | `{"type":"bar","data":{...}}` |

## 事件格式示例

### 1. message.assistant.start

```json
{
  "type": "message.assistant.start",
  "message_id": "msg_abc123",
  "conversation_id": "conv_xyz",
  "session_id": "sess_001",
  "seq": 1,
  "timestamp": 1705123456000
}
```

### 2. message.assistant.delta (thinking)

```json
{
  "type": "message.assistant.delta",
  "message_id": "msg_abc123",
  "session_id": "sess_001",
  "seq": 2,
  "timestamp": 1705123456100,
  "delta": {
    "type": "thinking",
    "content": "让我分析一下用户的需求..."
  }
}
```

### 3. message.assistant.delta (response)

```json
{
  "type": "message.assistant.delta",
  "message_id": "msg_abc123",
  "session_id": "sess_001",
  "seq": 3,
  "timestamp": 1705123456200,
  "delta": {
    "type": "response",
    "content": "你好！"
  }
}
```

### 4. message.assistant.delta (progress)

```json
{
  "type": "message.assistant.delta",
  "message_id": "msg_abc123",
  "session_id": "sess_001",
  "seq": 4,
  "timestamp": 1705123456300,
  "delta": {
    "type": "progress",
    "content": "{\"title\":\"生成PPT\",\"status\":\"running\",\"current\":1,\"total\":3,\"subtasks\":[{\"title\":\"分析需求\",\"status\":\"success\"},{\"title\":\"调用API\",\"status\":\"running\"}]}"
  }
}
```

### 5. message.assistant.done

```json
{
  "type": "message.assistant.done",
  "message_id": "msg_abc123",
  "session_id": "sess_001",
  "seq": 10,
  "timestamp": 1705123460000,
  "data": {
    "content": "你好！我是 AI 助手，很高兴为你服务。"
  }
}
```

### 6. message.assistant.error

```json
{
  "type": "message.assistant.error",
  "message_id": "msg_abc123",
  "session_id": "sess_001",
  "seq": 5,
  "timestamp": 1705123456500,
  "error": {
    "type": "network",
    "code": "TIMEOUT_ERROR",
    "message": "请求超时，请稍后重试",
    "retryable": true,
    "userAction": "请稍后重试"
  }
}
```

## 完整 SSE 流示例

```
data: {"type":"message.assistant.start","message_id":"msg_001","session_id":"sess_001","seq":1,"timestamp":1705123456000}

data: {"type":"message.assistant.delta","message_id":"msg_001","seq":2,"timestamp":1705123456100,"delta":{"type":"thinking","content":"让我思考..."}}

data: {"type":"message.assistant.delta","message_id":"msg_001","seq":3,"timestamp":1705123456200,"delta":{"type":"response","content":"你好！"}}

data: {"type":"message.assistant.delta","message_id":"msg_001","seq":4,"timestamp":1705123456300,"delta":{"type":"response","content":"我是AI助手。"}}

data: {"type":"message.assistant.done","message_id":"msg_001","seq":5,"timestamp":1705123460000,"data":{"content":"你好！我是AI助手。"}}

```

## 断线重连

```bash
# 重连到已存在的 Session
curl -N "http://localhost:8000/api/v1/chat/{session_id}?after_seq=5&format=zeno"
```

重连时先收到 `reconnect_info` 事件，然后是补偿的历史事件和实时事件。

## 前端处理示例

```javascript
const eventSource = new EventSource('/api/v1/chat');

eventSource.onmessage = (e) => {
  const event = JSON.parse(e.data);
  
  switch (event.type) {
    case 'message.assistant.start':
      // 开始新消息
      break;
    case 'message.assistant.delta':
      if (event.delta.type === 'thinking') {
        // 显示思考过程
      } else if (event.delta.type === 'response') {
        // 追加回复内容
      } else if (event.delta.type === 'progress') {
        // 更新进度条
      }
      break;
    case 'message.assistant.done':
      // 消息完成
      break;
    case 'message.assistant.error':
      // 处理错误
      if (event.error.retryable) {
        // 可重试
      }
      break;
  }
};
```
