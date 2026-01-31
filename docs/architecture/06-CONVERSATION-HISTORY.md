# Conversation History 对话历史管理

## 概述

本文档说明 Zenflux Agent 如何管理**多轮对话上下文**，包括历史消息的加载、保存和切换。

## ID 体系

```
User (用户)
└── user_id: "user_1766974073604"

Conversation (对话 - 持久化)
└── conversation_id: "conv_20250104_abc123"
    ├── 存储位置: SQLite 数据库
    ├── 生命周期: 永久
    └── Messages (消息列表)
        ├── {role: "user", content: [...]}
        ├── {role: "assistant", content: [...]}
        └── ...

Session (会话 - 临时)
└── session_id: "sess_20250104_150000_abc123"
    ├── 存储位置: Redis
    ├── 生命周期: 1小时
    ├── 关联: conversation_id
    └── 用途: SSE 事件推送、Agent 运行状态
```

### ID 对比

| 属性 | `conversation_id` | `session_id` |
|------|-------------------|--------------|
| **作用域** | 对话线程 | 单次执行 |
| **生命周期** | 持久化 | 临时（1小时） |
| **存储位置** | SQLite | Redis |
| **用途** | 历史消息、上下文 | SSE 事件、状态追踪 |
| **生成时机** | 首次发消息 | 每次请求 |

## 数据库设计

### 表结构

```sql
-- 对话表
CREATE TABLE conversations (
    id TEXT PRIMARY KEY,           -- UUID 格式
    user_id TEXT NOT NULL,
    title TEXT DEFAULT '新对话',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    extra_data TEXT                -- JSON: {compression: {...}, ...}
);

-- 消息表
CREATE TABLE messages (
    id TEXT PRIMARY KEY,           -- msg_xxxxxxxx 格式
    conversation_id TEXT NOT NULL,
    role TEXT NOT NULL,            -- user/assistant/system
    content TEXT NOT NULL,         -- JSON 数组格式
    status TEXT,                   -- JSON: {action, has_thinking, ...}
    score REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    extra_data TEXT,               -- JSON 元数据
    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
);

-- 索引
CREATE INDEX idx_messages_conversation ON messages(conversation_id);
CREATE INDEX idx_conversations_user ON conversations(user_id);
```

### Content 存储格式

消息 `content` 字段使用 JSON 数组，完整保存所有内容块：

```json
[
  {"type": "thinking", "thinking": "让我思考一下...", "signature": "xxx"},
  {"type": "text", "text": "这是回复内容"},
  {"type": "tool_use", "id": "toolu_xxx", "name": "web_search", "input": {...}},
  {"type": "tool_result", "tool_use_id": "toolu_xxx", "content": "搜索结果..."}
]
```

## 核心流程

### 1. 完整请求流程

```
前端                     ChatService              SessionService           Agent
 │                           │                          │                    │
 │ POST /chat               │                          │                    │
 │ {message, userId,        │                          │                    │
 │  conversationId}         │                          │                    │
 │─────────────────────────>│                          │                    │
 │                          │                          │                    │
 │                          │ 1. 确保 Conversation 存在 │                    │
 │                          │    (无则创建)             │                    │
 │                          │                          │                    │
 │                          │ 2. create_session()     │                    │
 │                          │─────────────────────────>│                    │
 │                          │                          │ 创建 Redis Session │
 │                          │                          │ 创建 Agent 实例    │
 │                          │<─────────────────────────│                    │
 │                          │   (session_id, agent)   │                    │
 │                          │                          │                    │
 │                          │ 3. 保存用户消息到数据库   │                    │
 │                          │                          │                    │
 │                          │ 4. Context.load_messages()                   │
 │                          │    (从数据库加载历史)     │                    │
 │                          │                          │                    │
 │                          │ 5. agent.chat()         │                    │
 │                          │───────────────────────────────────────────────>│
 │                          │                          │                    │
 │<─ SSE 事件流 ─────────────│<──────────────────────────────────────────────│
 │                          │                          │                    │
 │                          │ 6. ChatEventHandler.finalize()               │
 │                          │    (保存 assistant 消息)  │                    │
```

### 2. 关键代码路径

```python
# ChatService._chat_stream()

# 1. 确保 Conversation 存在
if not conversation_id:
    conv = await crud.create_conversation(session, user_id, "新对话")
    conversation_id = conv.id

# 2. 创建 Session
session_id, agent = await self.session_service.create_session(
    user_id=user_id,
    message=normalized_message,
    conversation_id=conversation_id
)

# 3. 保存用户消息
await crud.create_message(
    session, conversation_id, role="user", content=content_json
)

# 4. 加载历史消息（核心！）
context = Context(
    conversation_id=conversation_id,
    conversation_service=self.conversation_service
)
history_messages = await context.load_messages()

# 5. 调用 Agent
# messages 已包含当前用户消息（ChatService 先保存再加载）
async for event in agent.chat(
    messages=history_messages,
    session_id=session_id
):
    await handler.handle(event)

# 6. 保存 assistant 消息
await handler.finalize(agent)
```

## Context 模块

`Context` 是上下文管理的核心模块，负责：

1. **加载历史消息** - 从数据库读取并转换格式
2. **清理无效内容** - 移除 thinking、修复 tool_use/tool_result 配对
3. **Token 计数** - 使用 tiktoken 精确计算
4. **双阈值压缩** - 80% 预检查 / 92% 运行中压缩

### 消息格式转换

```python
# 数据库格式 → Agent 格式
def _convert_to_agent_format(self, db_messages):
    for msg in db_messages:
        content = json.loads(msg.content)  # JSON 数组
        
        # 清理 content 块
        content = self._clean_content_blocks(content, msg.role)
        
        agent_messages.append({
            "role": msg.role,
            "content": content
        })
    
    # 确保 tool_use/tool_result 配对
    return self._ensure_tool_pairs(agent_messages)
```

### 内容清理规则

| 块类型 | 处理 |
|--------|------|
| `thinking` | **全部移除**（历史消息不需要，避免 signature 问题） |
| `tool_use` | 只保留有配对 `tool_result` 的 |
| `tool_result` | 只保留有配对 `tool_use` 的 |
| `text` | 保留 |

## 前端实现

### Pinia Store 状态

```javascript
// stores/chat.js
export const useChatStore = defineStore('chat', {
  state: () => ({
    userId: null,
    conversationId: null,    // 当前对话 ID
    sessionId: null,         // 当前会话 ID（临时）
    messages: [],
    isConnected: false,
    sseConnection: null
  }),
  
  actions: {
    // 发送消息（流式）
    async sendMessageStream(content, conversationId, onEvent) {
      const requestBody = {
        message: content,
        user_id: this.userId,
        stream: true
      }
      
      if (conversationId) {
        requestBody.conversation_id = conversationId
      }
      
      // ... SSE 处理
    }
  }
})
```

### 会话切换

```javascript
// views/ChatView.vue
async function loadConversation(conversationId) {
  // 1. 断开当前 SSE（避免事件错乱）
  if (chatStore.isConnected) {
    chatStore.disconnectSSE()
  }
  
  // 2. 重置状态
  isLoading.value = false
  currentSessionId.value = null
  messages.value = []
  
  // 3. 设置新的 conversationId
  chatStore.conversationId = conversationId
  
  // 4. 加载历史消息
  const result = await chatStore.getConversationMessages(conversationId)
  messages.value = result.messages.map(msg => ({
    id: msg.id,
    role: msg.role,
    content: extractTextFromContent(msg.content),
    thinking: extractThinkingFromContent(msg.content),
    contentBlocks: parseContentBlocks(msg.content)
  }))
}
```

## 事件与消息关系

### SSE 事件流

```
session_start          → 会话开始
conversation_start     → 对话创建（新对话时）
message_start          → 消息开始
content_start          → 内容块开始（thinking/text/tool_use）
content_delta          → 内容增量
content_stop           → 内容块结束
tool_result            → 工具结果
message_stop           → 消息结束 → 触发数据库保存
session_end            → 会话结束
```

### 消息保存时机

| 角色 | 保存时机 |
|------|---------|
| `user` | Agent 执行前立即保存 |
| `assistant` | `message_stop` 事件时保存（ChatEventHandler.finalize） |

## 最佳实践

### 1. conversation_id 管理

```javascript
// ✅ 前端不生成 ID，由后端创建
// 首次发消息时不传 conversationId，后端自动创建
const result = await chatStore.sendMessageStream(content, null, onEvent)

// 收到 conversation_start 事件后保存
if (event.type === 'conversation_start') {
  chatStore.conversationId = event.data.conversation_id
  router.push({ name: 'conversation', params: { conversationId } })
}
```

### 2. 会话切换安全

```javascript
// ✅ 切换前断开 SSE
async function loadConversation(newConversationId) {
  // 必须先断开，避免事件错乱
  chatStore.disconnectSSE()
  
  // 然后切换
  chatStore.conversationId = newConversationId
  await loadHistory()
}
```

### 3. 历史消息分页

```python
# 长对话场景（100+ 条消息）
messages = await context.load_messages(limit=50)  # 只加载最近 50 条

# 或使用 Token 压缩
if context.check_threshold(0.80):
    await context.compress_if_needed()
```

## 错误处理

### 1. conversation_id 不存在

```python
# ChatService 自动创建
if not conversation_id:
    conv = await crud.create_conversation(session, user_id, "新对话")
    conversation_id = conv.id
```

### 2. 历史加载失败

```python
# Context.load_messages() 失败不阻塞执行
try:
    messages = await context.load_messages()
except Exception as e:
    logger.warning(f"⚠️ 加载历史失败: {e}")
    messages = []  # 继续执行，只是没有历史
```

### 3. 消息保存失败

```python
# 保存失败不影响 Agent 执行
try:
    await crud.create_message(...)
except Exception as e:
    logger.warning(f"⚠️ 保存消息失败: {e}")
# 继续执行 Agent
```

## 监控日志

```python
# 关键日志点
logger.info(f"✅ 新对话已创建: id={conversation_id}")
logger.info(f"📚 历史消息已加载: {len(messages)} 条")
logger.info(f"💾 用户消息已保存")
logger.info(f"✅ Assistant 消息已保存: id={message_id}")

# 警告日志
logger.warning(f"⚠️ 发现未配对的 tool_use，将移除")
logger.warning(f"⚠️ Token 使用率超过 80%，建议压缩")
```

## 总结

### 核心设计

1. **ID 分离**：`conversation_id`（持久）+ `session_id`（临时）
2. **消息完整保存**：JSON 数组格式，包含 thinking/text/tool_use/tool_result
3. **历史加载清理**：移除 thinking，修复 tool 配对
4. **切换安全**：切换对话前断开 SSE

### 数据流

```
用户发消息 → 创建 Session → 保存 user 消息 → 加载历史 → Agent 执行 → 保存 assistant 消息
                                    ↓
                              Context 模块
                              (清理 + 转换)
```
