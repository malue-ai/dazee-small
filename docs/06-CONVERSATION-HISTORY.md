# Conversation History 历史对话管理

## 概述

本文档说明如何使用 `conversation_id` 来实现**多轮对话上下文延续**，包括历史消息的加载、保存和管理。

## 核心概念

### ID 体系

```
User (用户)
└── Conversation (对话线程)
    ├── conversation_id: "conv_20231227_001"  # 数据库对话ID
    └── Messages (消息列表)
        ├── Message 1: {role: "user", content: "你好"}
        ├── Message 2: {role: "assistant", content: "你好！有什么可以帮助你的吗？"}
        ├── Message 3: {role: "user", content: "帮我生成PPT"}
        └── Message 4: {role: "assistant", content: "好的，我来帮你..."}

Session (运行会话)
└── session_id: "sess_20231227_120000_abc123"  # 临时运行ID
    ├── 关联 conversation_id
    └── 加载历史消息 (Message 1-3)
    └── 执行新消息 (Message 4)
```

### 区别

| 名称 | 作用域 | 生命周期 | 存储位置 |
|------|--------|----------|----------|
| `conversation_id` | 对话线程 | 持久化（数据库） | PostgreSQL/SQLite |
| `session_id` | 运行会话 | 临时（1小时） | Redis + 内存 |

## 数据库设计

### 表结构

```sql
-- 对话表
CREATE TABLE conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    conversation_id TEXT UNIQUE NOT NULL,  -- 对话唯一标识
    title TEXT DEFAULT '新对话',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata TEXT,  -- JSON 格式元数据
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- 消息表
CREATE TABLE messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL,  -- 外键：关联对话
    role TEXT NOT NULL,             -- user/assistant/system
    content TEXT NOT NULL,          -- 消息内容
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata TEXT,                  -- JSON 格式元数据
    FOREIGN KEY (conversation_id) REFERENCES conversations(conversation_id)
);

-- 索引（优化查询性能）
CREATE INDEX idx_messages_conversation ON messages(conversation_id);
CREATE INDEX idx_messages_created_at ON messages(created_at);
CREATE INDEX idx_conversations_user ON conversations(user_id);
```

## 完整流程

### 场景 1: 新建对话（首次）

```
前端                    后端                       数据库
 │                       │                          │
 │ POST /chat            │                          │
 │ {                     │                          │
 │   message: "你好",     │                          │
 │   userId: "user_001", │                          │
 │   conversationId: null  # ← 没有 conversationId  │
 │ }                     │                          │
 │──────────────────────>│                          │
 │                       │                          │
 │                       │ create_session()         │
 │                       │ ├─ conversation_id = null│
 │                       │ └─ 不加载历史消息         │
 │                       │                          │
 │                       │ Agent.stream(message)    │
 │                       │ └─ 执行对话              │
 │                       │                          │
 │                       │ ❌ conversation_id 为空  │
 │                       │    不保存到数据库         │
 │                       │                          │
 │<──────────────────────│                          │
 │  SSE 事件流            │                          │
 │  (session_id 返回)    │                          │
```

**结果**：
- ✅ Agent 执行成功
- ❌ 消息不保存到数据库
- ⚠️ 下次请求无法续接上下文

### 场景 2: 新建对话（提供 conversation_id）

```
前端                    后端                       数据库
 │                       │                          │
 │ POST /chat            │                          │
 │ {                     │                          │
 │   message: "你好",     │                          │
 │   userId: "user_001", │                          │
 │   conversationId: "conv_001"  # ← 前端生成        │
 │ }                     │                          │
 │──────────────────────>│                          │
 │                       │                          │
 │                       │ create_session()         │
 │                       │ └─ _load_conversation_history()
 │                       │    └─ MessageService.get_conversation_messages()
 │                       │       └─────────────────>│
 │                       │          SELECT * FROM messages
 │                       │          WHERE conversation_id = 'conv_001'
 │                       │       <──────────────────│
 │                       │          (空列表)         │
 │                       │                          │
 │                       │ Agent.stream(message)    │
 │                       │                          │
 │                       │ _run_agent_background()  │
 │                       │ ├─ 保存 user 消息        │
 │                       │ │  └─────────────────>  │
 │                       │ │     INSERT INTO messages
 │                       │ │     (conversation_id, role, content)
 │                       │ │     VALUES ('conv_001', 'user', '你好')
 │                       │ │                         │
 │                       │ └─ 保存 assistant 消息   │
 │                       │    └─────────────────>   │
 │                       │       INSERT INTO messages
 │                       │       ('conv_001', 'assistant', '你好！...')
 │                       │                          │
 │<──────────────────────│                          │
 │  SSE 事件流            │                          │
```

**结果**：
- ✅ Agent 执行成功
- ✅ 消息保存到数据库
- ✅ 下次请求可以续接上下文

### 场景 3: 续接对话（多轮）

```
前端                    后端                       数据库
 │                       │                          │
 │ POST /chat            │                          │
 │ {                     │                          │
 │   message: "帮我生成PPT", │                       │
 │   userId: "user_001", │                          │
 │   conversationId: "conv_001"  # ← 相同的 ID     │
 │ }                     │                          │
 │──────────────────────>│                          │
 │                       │                          │
 │                       │ create_session()         │
 │                       │ └─ _load_conversation_history()
 │                       │    └─ MessageService.get_conversation_messages()
 │                       │       └─────────────────>│
 │                       │          SELECT * FROM messages
 │                       │          WHERE conversation_id = 'conv_001'
 │                       │          ORDER BY created_at ASC
 │                       │       <──────────────────│
 │                       │          [                │
 │                       │            {role: "user", content: "你好"},
 │                       │            {role: "assistant", content: "你好！..."}
 │                       │          ]                │
 │                       │                          │
 │                       │ 🎯 Agent.memory.messages = [历史消息]
 │                       │    ├─ Message 1: user "你好"
 │                       │    ├─ Message 2: assistant "你好！..."
 │                       │    └─ Agent 可以理解之前的上下文！
 │                       │                          │
 │                       │ Agent.stream("帮我生成PPT")
 │                       │ └─ LLM 可以看到完整历史    │
 │                       │                          │
 │                       │ 保存新消息               │
 │                       │ ├─────────────────────>  │
 │                       │ │  INSERT (user, "帮我生成PPT")
 │                       │ └─────────────────────>  │
 │                       │    INSERT (assistant, "好的，我来...")
 │                       │                          │
 │<──────────────────────│                          │
 │  SSE 事件流            │                          │
```

**结果**：
- ✅ 历史消息加载成功（2条）
- ✅ Agent 理解上下文
- ✅ 新消息追加到数据库
- ✅ 对话延续顺畅

## 代码实现

### 1. ChatService.create_session()

```python
def create_session(
    self,
    user_id: str,
    message: str,
    conversation_id: Optional[str] = None,
    ...
) -> tuple[str, SimpleAgent]:
    """创建 Session 并加载历史"""
    
    # 1. 生成 session_id
    session_id = self._generate_session_id()
    
    # 2. 创建 Agent
    agent = create_simple_agent(...)
    agent.start_session(session_id)
    
    # 3. 设置元数据
    agent.memory.working.conversation_id = conversation_id
    
    # 4. 🎯 加载历史消息
    if conversation_id:
        self._load_conversation_history(agent, conversation_id)
    
    return session_id, agent
```

### 2. _load_conversation_history()

```python
def _load_conversation_history(
    self,
    agent: SimpleAgent,
    conversation_id: str
) -> None:
    """从数据库加载历史消息到 Agent"""
    
    # 🎯 从数据库查询
    messages = asyncio.run(
        MessageService.get_conversation_messages(conversation_id)
    )
    
    if not messages:
        logger.info(f"没有历史消息")
        return
    
    logger.info(f"加载 {len(messages)} 条历史消息")
    
    # 转换为 Agent 格式
    history_messages = []
    for msg in messages:
        history_messages.append({
            "role": msg.role,        # user/assistant/system
            "content": msg.content
        })
    
    # 🎯 设置到 Agent memory
    if hasattr(agent.memory, 'load_conversation_history'):
        agent.memory.load_conversation_history(history_messages)
    else:
        # 直接追加到 messages
        for msg in history_messages:
            agent.memory.working.messages.append(msg)
```

### 3. _run_agent_background() - 保存消息

```python
async def _run_agent_background(
    self,
    session_id: str,
    agent: SimpleAgent,
    message: str
):
    """后台执行 Agent 并保存消息"""
    
    conversation_id = agent.memory.working.conversation_id
    
    # 🎯 保存用户消息
    if conversation_id:
        await MessageService.create_message(
            conversation_id=conversation_id,
            role="user",
            content=message,
            metadata={"session_id": session_id}
        )
    
    # 执行 Agent
    assistant_content = ""
    async for event in agent.stream(message):
        # ... 处理事件 ...
        
        # 累积 Assistant 回复
        if event["type"] == "content_block_delta":
            delta = event["data"].get("delta", {})
            if delta.get("type") == "text_delta":
                assistant_content += delta.get("text", "")
    
    # 🎯 保存 Assistant 消息
    if conversation_id and assistant_content:
        await MessageService.create_message(
            conversation_id=conversation_id,
            role="assistant",
            content=assistant_content,
            metadata={"session_id": session_id}
        )
```

### 4. MessageService.get_conversation_messages()

```python
@staticmethod
async def get_conversation_messages(
    conversation_id: str,
    limit: Optional[int] = None
) -> List[Message]:
    """获取对话的所有消息"""
    
    async with await db_manager.get_connection() as db:
        query = """
            SELECT * FROM messages 
            WHERE conversation_id = ? 
            ORDER BY created_at ASC
        """
        
        async with db.execute(query, (conversation_id,)) as cursor:
            rows = await cursor.fetchall()
            return [
                Message(
                    id=row[0],
                    conversation_id=row[1],
                    role=row[2],
                    content=row[3],
                    created_at=datetime.fromisoformat(row[4]),
                    metadata=deserialize_metadata(row[5])
                )
                for row in rows
            ]
```

## 前端实现示例

### React 示例

```typescript
import { useState } from 'react';

export function ChatComponent() {
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);

  const sendMessage = async (text: string) => {
    // 1. 🎯 首次对话：生成 conversation_id
    if (!conversationId) {
      const newConvId = `conv_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
      setConversationId(newConvId);
    }

    // 2. 发送请求
    const response = await fetch('/api/v1/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: text,
        userId: 'user_001',
        conversationId: conversationId,  // ← 续接对话
        stream: true
      })
    });

    // 3. 处理 SSE 流
    // ...
  };

  return (
    <div>
      {/* 显示消息列表 */}
      {messages.map(msg => (
        <div key={msg.id}>
          <strong>{msg.role}:</strong> {msg.content}
        </div>
      ))}
      
      {/* 输入框 */}
      <input 
        onSubmit={(text) => sendMessage(text)} 
        placeholder="输入消息..."
      />
    </div>
  );
}
```

### 存储 conversation_id

```typescript
// 方案 1: 存储在 localStorage（持久化）
localStorage.setItem('currentConversationId', conversationId);

// 方案 2: 存储在 sessionStorage（仅当前标签页）
sessionStorage.setItem('currentConversationId', conversationId);

// 方案 3: 存储在 URL（支持分享）
// /chat/conv_20231227_001
```

## 最佳实践

### 1. conversation_id 生成规则

```typescript
// ✅ 推荐：时间戳 + 随机字符
const conversationId = `conv_${Date.now()}_${randomString(8)}`;
// 示例: conv_1703664000000_a3b4c5d6

// ✅ 推荐：UUID
const conversationId = `conv_${uuidv4()}`;
// 示例: conv_550e8400-e29b-41d4-a716-446655440000

// ❌ 不推荐：纯随机（可能冲突）
const conversationId = Math.random().toString();
```

### 2. 首条消息创建对话

```python
# 前端发送首条消息时，同时创建对话
POST /api/v1/chat
{
  "message": "你好",
  "userId": "user_001",
  "conversationId": "conv_001"  # ← 首次提供
}

# 后端：如果数据库中不存在该 conversation_id，自动创建
if conversation_id:
    conv = await ConversationService.get_conversation(conversation_id)
    if not conv:
        await ConversationService.create_conversation(
            user_id=user_id,
            conversation_id=conversation_id,
            title="新对话"
        )
```

### 3. 历史消息分页

对于长对话（100+ 条消息），建议分页加载：

```python
# 方案 1: 只加载最近 N 条消息
messages = await MessageService.get_recent_messages(
    conversation_id=conversation_id,
    limit=20  # 最近 20 条
)

# 方案 2: Token 压缩（避免超出上下文限制）
if len(messages) > 50:
    # 压缩旧消息
    compressed = compress_old_messages(messages[:-20])
    # 保留最近 20 条完整消息
    messages = compressed + messages[-20:]
```

### 4. 对话标题自动生成

```python
# 在首轮对话完成后，自动生成标题
async def _run_agent_background(...):
    # ... 执行 Agent ...
    
    # 首轮对话完成后
    if conversation_id:
        conv = await ConversationService.get_conversation(conversation_id)
        if conv.title == "新对话":
            # 使用 LLM 生成标题
            title = await generate_title_from_message(message)
            await ConversationService.update_conversation_title(
                conversation_id, title
            )
```

## 错误处理

### 1. conversation_id 不存在

```python
# 场景：前端传了一个不存在的 conversation_id
conversation_id = "conv_nonexistent"

# 方案 1: 自动创建（推荐）
if conversation_id:
    conv = await ConversationService.get_conversation(conversation_id)
    if not conv:
        logger.warning(f"对话不存在，自动创建: {conversation_id}")
        await ConversationService.create_conversation(
            user_id=user_id,
            conversation_id=conversation_id
        )

# 方案 2: 返回错误
if conversation_id:
    conv = await ConversationService.get_conversation(conversation_id)
    if not conv:
        raise HTTPException(
            status_code=404,
            detail=f"对话不存在: {conversation_id}"
        )
```

### 2. 历史消息加载失败

```python
def _load_conversation_history(...):
    try:
        messages = await MessageService.get_conversation_messages(conversation_id)
        # ... 加载消息 ...
    except Exception as e:
        # ⚠️ 加载失败不应该阻塞会话创建
        logger.error(f"加载历史失败: {str(e)}")
        # 继续执行，只是没有历史上下文
```

### 3. 数据库保存失败

```python
async def _run_agent_background(...):
    # 保存用户消息
    try:
        await MessageService.create_message(...)
    except Exception as e:
        # ⚠️ 保存失败不应该影响 Agent 执行
        logger.warning(f"保存消息失败: {str(e)}")
    
    # Agent 继续执行
    async for event in agent.stream(message):
        # ...
```

## 监控和日志

### 1. 日志记录

```python
# 加载历史
logger.info(
    f"📚 加载历史消息: conversation_id={conversation_id}, "
    f"消息数={len(messages)}"
)

# 保存消息
logger.debug(
    f"💾 用户消息已保存: conversation_id={conversation_id}, "
    f"session_id={session_id}"
)

# 历史加载失败
logger.error(
    f"⚠️ 加载历史失败: conversation_id={conversation_id}, "
    f"error={str(e)}"
)
```

### 2. 性能监控

```python
import time

# 监控历史加载耗时
start = time.time()
messages = await MessageService.get_conversation_messages(conversation_id)
elapsed = time.time() - start

logger.info(f"⏱️ 历史加载耗时: {elapsed:.2f}s, 消息数={len(messages)}")

# 如果耗时过长，考虑优化
if elapsed > 1.0 and len(messages) > 100:
    logger.warning(
        f"⚠️ 历史加载耗时过长: {elapsed:.2f}s, "
        f"建议添加分页或压缩"
    )
```

## 总结

### conversation_id 的作用

1. **持久化对话**：保存到数据库，支持长期存储
2. **多轮上下文**：加载历史消息，让 Agent 理解之前的对话
3. **对话管理**：用户可以查看、切换、删除对话
4. **分享链接**：通过 URL 分享对话 (`/chat/conv_xxx`)

### 关键流程

```
创建 Session → 加载历史消息 → Agent 执行 → 保存新消息
     ↓              ↓                ↓           ↓
  session_id   conversation_id   Redis 缓冲   数据库持久化
```

### 设计原则

1. **解耦**：`session_id` (临时) 和 `conversation_id` (持久) 分离
2. **容错**：历史加载失败不影响会话创建
3. **性能**：长对话考虑分页/压缩
4. **可观测**：完整的日志记录

这样就实现了一个**生产级的多轮对话系统**！🎉

