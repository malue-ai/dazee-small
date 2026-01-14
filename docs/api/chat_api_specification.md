# ZenFlux Agent Chat API 规范

## 概述

ZenFlux Agent Chat API 提供了一套统一、标准化的聊天接口，支持多模态输入、历史消息上下文、文件附件处理以及丰富的配置选项。

**版本**: v1.0  
**基础 URL**: `/api/v1`  
**协议**: HTTP/HTTPS  
**认证**: Bearer Token（可选）  

---

## 目录

1. [快速开始](#快速开始)
2. [数据模型](#数据模型)
3. [接口说明](#接口说明)
4. [使用示例](#使用示例)
5. [错误处理](#错误处理)
6. [最佳实践](#最佳实践)

---

## 快速开始

### 最简单的请求

```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "你好，请介绍一下自己",
    "userId": "user_001"
  }'
```

### 流式请求

```bash
curl -X POST http://localhost:8000/api/v1/chat/stream \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{
    "message": "你好",
    "userId": "user_001"
  }'
```

---

## 数据模型

### 1. EnhancedChatRequest

完整的聊天请求模型。

#### 基础字段

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `message` | `string` 或 `Message` | ✅ | 用户消息 |
| `userId` | `string` | ✅ | 用户ID |
| `conversationId` | `string` | ❌ | 对话线程ID（多轮对话必填） |
| `messageId` | `string` | ❌ | 消息ID（用于追踪） |
| `agentId` | `string` | ❌ | 指定 Agent 实例 ID |

#### 高级字段

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `history` | `List[Message]` | ❌ | 历史消息列表（最多50条） |
| `attachments` | `List[AttachmentFile]` | ❌ | 文件附件列表（最多20个） |
| `context` | `UserContext` | ❌ | 用户上下文变量 |
| `options` | `ChatOptions` | ❌ | 聊天选项 |

### 2. Message

消息模型，支持文本和多模态内容。

```json
{
  "role": "user",  // "user" 或 "assistant"
  "content": "这是一条文本消息",
  "timestamp": "2024-01-14T12:00:00Z",
  "message_id": "msg_001"
}
```

或者（多模态）：

```json
{
  "role": "user",
  "content": [
    {"type": "text", "text": "请分析这张图片"},
    {
      "type": "image",
      "source": {
        "type": "url",
        "url": "https://example.com/image.png"
      }
    }
  ]
}
```

### 3. AttachmentFile

文件附件模型，支持多种文件来源。

```json
{
  "file_id": "file_abc123",           // 方式1：文件ID
  "file_name": "报告.pdf",
  "file_size": 1048576,
  "file_type": "pdf",
  "source": "upload",
  "extract_text": true,
  "max_pages": 50
}
```

或者：

```json
{
  "file_url": "https://example.com/doc.pdf",  // 方式2：外部URL
  "file_name": "文档.pdf",
  "file_type": "pdf",
  "source": "url"
}
```

#### 支持的文件类型

| 类型 | 说明 | 扩展名 |
|------|------|--------|
| `pdf` | PDF 文档 | `.pdf` |
| `word` | Word 文档 | `.doc`, `.docx` |
| `excel` | Excel 表格 | `.xls`, `.xlsx` |
| `image` | 图片 | `.jpg`, `.png`, `.gif`, `.webp` |
| `text` | 文本文件 | `.txt`, `.md`, `.csv` |
| `audio` | 音频文件 | `.mp3`, `.wav`, `.m4a` |
| `video` | 视频文件 | `.mp4`, `.avi`, `.mov` |

### 4. UserContext

用户上下文变量，用于个性化响应。

```json
{
  "location": "北京市朝阳区",
  "coordinates": {"lat": 39.9, "lng": 116.4},
  "timezone": "Asia/Shanghai",
  "locale": "zh-CN",
  "current_time": "2024-01-14T12:00:00+08:00",
  "device": "mobile",
  "os": "iOS",
  "browser": "Safari",
  "is_authenticated": true,
  "subscription_tier": "pro",
  "custom_fields": {
    "company": "Acme Inc.",
    "department": "Engineering"
  }
}
```

### 5. ChatOptions

聊天选项，用于控制行为。

```json
{
  "stream": true,
  "event_format": "zeno",
  "temperature": 0.7,
  "max_tokens": 4096,
  "enable_thinking": true,
  "enable_memory": true,
  "enable_plan": true,
  "enable_tools": true,
  "background_tasks": ["title_generation", "mem0_update"],
  "max_turns": 20,
  "timeout": 120
}
```

---

## 接口说明

### POST /api/v1/chat

同步聊天接口（等待完整响应）。

**请求头**:
```
Content-Type: application/json
Authorization: Bearer <token>  // 可选
```

**请求体**:
```json
{
  "message": "你好",
  "userId": "user_001",
  "options": {
    "stream": false
  }
}
```

**响应** (200 OK):
```json
{
  "conversation_id": "conv_001",
  "session_id": "session_001",
  "content": "你好！我是ZenFlux智能助手...",
  "status": "success",
  "turns": 1,
  "invocation_stats": {
    "llm_calls": 1,
    "tool_calls": 0
  }
}
```

### POST /api/v1/chat/stream

流式聊天接口（SSE 流式响应）。

**请求头**:
```
Content-Type: application/json
Accept: text/event-stream
```

**请求体**:
```json
{
  "message": "你好",
  "userId": "user_001",
  "options": {
    "stream": true,
    "event_format": "zeno"
  }
}
```

**响应** (200 OK, SSE):
```
event: session_start
data: {"session_id": "session_001"}

event: thinking
data: {"content": "让我思考一下..."}

event: content_delta
data: {"delta": "你好"}

event: content_delta
data: {"delta": "！"}

event: session_end
data: {"status": "completed"}
```

---

## 使用示例

### 示例 1: 简单对话

```python
import requests

response = requests.post(
    "http://localhost:8000/api/v1/chat",
    json={
        "message": "今天天气怎么样？",
        "userId": "user_001"
    }
)

print(response.json()["content"])
```

### 示例 2: 多轮对话

```python
# 第一轮
response1 = requests.post(
    "http://localhost:8000/api/v1/chat",
    json={
        "message": "北京今天天气怎么样？",
        "userId": "user_001",
        "conversationId": "conv_001"
    }
)

# 第二轮（带历史）
response2 = requests.post(
    "http://localhost:8000/api/v1/chat",
    json={
        "message": "那明天呢？",
        "userId": "user_001",
        "conversationId": "conv_001",
        "history": [
            {"role": "user", "content": "北京今天天气怎么样？"},
            {"role": "assistant", "content": response1.json()["content"]}
        ]
    }
)
```

### 示例 3: 文件分析

```python
# 先上传文件
upload_response = requests.post(
    "http://localhost:8000/api/v1/files/upload",
    files={"file": open("report.pdf", "rb")}
)
file_id = upload_response.json()["file_id"]

# 分析文件
response = requests.post(
    "http://localhost:8000/api/v1/chat",
    json={
        "message": "请总结这份报告的要点",
        "userId": "user_001",
        "attachments": [
            {
                "file_id": file_id,
                "file_name": "report.pdf",
                "file_type": "pdf",
                "source": "upload",
                "extract_text": True
            }
        ]
    }
)
```

### 示例 4: 流式对话（Python）

```python
import requests
import json

response = requests.post(
    "http://localhost:8000/api/v1/chat/stream",
    json={
        "message": "写一首关于春天的诗",
        "userId": "user_001",
        "options": {"stream": True}
    },
    stream=True
)

for line in response.iter_lines():
    if line:
        line = line.decode('utf-8')
        if line.startswith('data: '):
            data = json.loads(line[6:])
            if data.get("type") == "content_delta":
                print(data["delta"], end="", flush=True)
```

### 示例 5: 流式对话（JavaScript）

```javascript
const eventSource = new EventSource(
  'http://localhost:8000/api/v1/chat/stream',
  {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      message: '写一首关于春天的诗',
      userId: 'user_001',
      options: { stream: true }
    })
  }
);

eventSource.onmessage = (event) => {
  const data = JSON.parse(event.data);
  if (data.type === 'content_delta') {
    console.log(data.delta);
  }
};

eventSource.onerror = (error) => {
  console.error('Error:', error);
  eventSource.close();
};
```

### 示例 6: 带上下文的个性化对话

```python
response = requests.post(
    "http://localhost:8000/api/v1/chat",
    json={
        "message": "推荐附近的餐厅",
        "userId": "user_001",
        "context": {
            "location": "北京市朝阳区",
            "coordinates": {"lat": 39.9, "lng": 116.4},
            "timezone": "Asia/Shanghai",
            "locale": "zh-CN",
            "device": "mobile",
            "current_time": "2024-01-14T12:00:00+08:00"
        },
        "options": {
            "enable_tools": True,
            "temperature": 0.7
        }
    }
)
```

---

## 错误处理

### 错误响应格式

```json
{
  "code": "ERROR_CODE",
  "message": "用户可见的错误信息",
  "timestamp": "2024-01-14T12:00:00Z"
}
```

### 常见错误码

| HTTP 状态码 | 错误码 | 说明 | 解决方案 |
|-------------|--------|------|----------|
| 400 | `VALIDATION_ERROR` | 请求参数验证失败 | 检查请求格式和必填字段 |
| 404 | `SESSION_NOT_FOUND` | 会话不存在 | 检查 session_id 是否正确 |
| 404 | `AGENT_NOT_FOUND` | Agent 不存在 | 检查 agent_id 是否正确 |
| 500 | `AGENT_ERROR` | Agent 执行错误 | 查看日志，联系管理员 |
| 503 | `EXTERNAL_SERVICE_ERROR` | 外部服务错误（LLM、Redis等） | 稍后重试 |
| 500 | `INTERNAL_ERROR` | 内部错误 | 查看日志，联系管理员 |

### 错误处理示例

```python
try:
    response = requests.post(
        "http://localhost:8000/api/v1/chat",
        json={"message": "你好", "userId": "user_001"}
    )
    response.raise_for_status()
    result = response.json()
except requests.exceptions.HTTPError as e:
    error = e.response.json()
    print(f"错误: {error['code']} - {error['message']}")
except requests.exceptions.RequestException as e:
    print(f"请求失败: {str(e)}")
```

---

## 最佳实践

### 1. 使用 conversationId 实现多轮对话

**推荐**：
```python
conversation_id = "conv_" + str(uuid.uuid4())

# 第一轮
response1 = chat(message="你好", conversation_id=conversation_id)

# 第二轮（自动加载历史）
response2 = chat(message="继续", conversation_id=conversation_id)
```

**不推荐**：
```python
# 每次都不传 conversationId，无法保持上下文
response1 = chat(message="你好")
response2 = chat(message="继续")  # ❌ 无法理解"继续"指什么
```

### 2. 文件处理

**推荐**：
```python
# 先上传，获取 file_id
file_id = upload_file("report.pdf")

# 使用 file_id 引用
chat(
    message="总结这份报告",
    attachments=[{"file_id": file_id, "file_type": "pdf"}]
)
```

**不推荐**：
```python
# 每次都重新上传Base64数据
chat(
    message="总结这份报告",
    attachments=[{"file_data": base64_data}]  # ❌ 浪费带宽
)
```

### 3. 流式响应处理

**推荐**：
```python
# 使用 SSE 客户端处理流式响应
for event in stream_chat(message="写一首诗"):
    if event["type"] == "content_delta":
        print(event["delta"], end="", flush=True)
```

**不推荐**：
```python
# 等待完整响应（用户体验差）
response = chat(message="写一首诗", stream=False)
print(response["content"])  # ❌ 等待时间长
```

### 4. 错误重试

**推荐**：
```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10)
)
def chat_with_retry(message, user_id):
    return requests.post(
        "http://localhost:8000/api/v1/chat",
        json={"message": message, "userId": user_id}
    ).json()
```

### 5. 超时控制

**推荐**：
```python
response = requests.post(
    "http://localhost:8000/api/v1/chat",
    json={"message": "你好", "userId": "user_001"},
    timeout=30  # 30秒超时
)
```

### 6. 使用 context 提供个性化服务

**推荐**：
```python
chat(
    message="推荐餐厅",
    context={
        "location": "北京市朝阳区",
        "timezone": "Asia/Shanghai",
        "locale": "zh-CN"
    }
)
```

**不推荐**：
```python
# 在消息中硬编码上下文信息
chat(message="推荐北京市朝阳区的餐厅，我在中国，用中文回复")  # ❌ 浪费 tokens
```

---

## 附录

### A. 完整的 TypeScript 类型定义

```typescript
interface EnhancedChatRequest {
  message: string | Message;
  userId: string;
  conversationId?: string;
  messageId?: string;
  agentId?: string;
  history?: Message[];
  attachments?: AttachmentFile[];
  context?: UserContext;
  options?: ChatOptions;
}

interface Message {
  role: 'user' | 'assistant';
  content: string | ContentBlock[];
  timestamp?: string;
  message_id?: string;
}

interface AttachmentFile {
  file_id?: string;
  file_url?: string;
  file_name: string;
  file_size?: number;
  file_type: FileType;
  source: FileSource;
  extract_text?: boolean;
  max_pages?: number;
}

interface UserContext {
  location?: string;
  coordinates?: { lat: number; lng: number };
  timezone?: string;
  locale?: string;
  current_time?: string;
  device?: string;
  os?: string;
  browser?: string;
  is_authenticated?: boolean;
  subscription_tier?: string;
  custom_fields?: Record<string, any>;
}

interface ChatOptions {
  stream?: boolean;
  event_format?: 'zeno' | 'zenflux';
  temperature?: number;
  max_tokens?: number;
  enable_thinking?: boolean;
  enable_memory?: boolean;
  enable_plan?: boolean;
  enable_tools?: boolean;
  background_tasks?: string[];
  max_turns?: number;
  timeout?: number;
}
```

### B. OpenAPI Specification

API 的完整 OpenAPI 规范可通过以下地址访问：
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- OpenAPI JSON: http://localhost:8000/openapi.json

---

**文档版本**: 1.0  
**最后更新**: 2024-01-14  
**维护者**: ZenFlux Agent Team
