# Message 表结构升级文档

## 📋 变更概述

### 升级原因

1. **消息 ID**: 从自增 INTEGER 改为 UUID TEXT，便于分布式系统和数据同步
2. **Content 格式**: 支持 Claude API 标准的 content blocks 格式
3. **状态追踪**: 新增 status 和 step_index 字段，支持多步骤任务管理
4. **质量评分**: 新增 score 字段，用于后续的响应质量评估

### 变更内容

| 字段 | 旧版本 | 新版本 | 说明 |
|------|--------|--------|------|
| `id` | `INTEGER PRIMARY KEY AUTOINCREMENT` | `TEXT PRIMARY KEY` | 使用 UUID |
| `content` | `TEXT` | `TEXT (JSON)` | JSON 数组格式 |
| `status` | ❌ 不存在 | `TEXT (JSON)` | 消息状态（JSON 对象）|
| `score` | ❌ 不存在 | `REAL` | 质量评分 |

## 🗂️ 新的表结构

```sql
CREATE TABLE messages (
    id TEXT PRIMARY KEY,                    -- UUID 格式: msg_xxxx
    conversation_id TEXT NOT NULL,           -- 所属对话ID
    role TEXT NOT NULL,                      -- user/assistant/system
    content TEXT NOT NULL,                   -- JSON 数组格式的 content blocks
    status TEXT,                             -- 消息状态（JSON 对象）
    score REAL,                              -- 评分/质量分数 (0.0-1.0)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata TEXT DEFAULT '{}',              -- 其他元数据
    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
);
```

## 📝 Content 格式

### 标准格式（兼容 Claude API）

```json
[
    {
        "type": "thinking",
        "thinking": "让我分析一下这个需求...\n1. 用户想要...",
        "signature": "EqQBCgIYAhIM1gbcDa9GJwZA..."
    },
    {
        "type": "text",
        "text": "用户的问题或 AI 的回复"
    },
    {
        "type": "tool_use",
        "id": "toolu_xxx",
        "name": "web_search",
        "input": {
            "query": "搜索关键词"
        }
    },
    {
        "type": "tool_result",
        "tool_use_id": "toolu_xxx",
        "content": "工具执行结果"
    }
]
```

**⚠️ 重要**: `thinking` 块必须包含 `signature` 字段，这是 Claude Extended Thinking 功能在多轮对话中的必要条件。

### 为什么使用 JSON 数组格式？

1. **兼容 Claude API**: 直接使用 Claude 的 content blocks 格式
2. **支持多模态**: 可以包含 text、tool_use、tool_result 等多种类型
3. **完整保存上下文**: 保留完整的工具调用链
4. **便于重放**: 可以重新构建完整的对话历史

### 简单文本消息示例

```python
# 用户消息
content = json.dumps([{"type": "text", "text": "你好"}])

# AI 回复
content = json.dumps([{"type": "text", "text": "你好！我是 AI 助手"}])
```

### 包含工具调用的消息示例

```python
content = json.dumps([
    {"type": "text", "text": "让我搜索一下"},
    {
        "type": "tool_use",
        "id": "toolu_01A09q90qw90lq917835lq9",
        "name": "web_search",
        "input": {"query": "Python 教程"}
    }
])
```

## 🏷️ Status 字段（JSON 格式）

### 数据结构

```json
{
    "index": 0,              // 步骤索引 (用于排序)
    "action": "think",       // 动作类型
    "description": "分析任务" // 步骤描述
}
```

### Action 类型

- `"think"`: 思考阶段（extended thinking）
- `"action"`: 行动阶段（工具调用）
- `"plan"`: 规划阶段
- `"validate"`: 验证阶段
- `"reflect"`: 反思阶段

### 使用示例

```python
import json

# 保存思考步骤
status = json.dumps({
    "index": 0,
    "action": "think",
    "description": "正在分析用户需求"
})

await conversation_service.add_message(
    conversation_id="conv_xxx",
    role="assistant",
    content=json.dumps([{"type": "text", "text": "让我想想..."}]),
    status=status
)

# 保存工具调用步骤
status = json.dumps({
    "index": 1,
    "action": "action",
    "description": "搜索相关信息"
})

await conversation_service.add_message(
    conversation_id="conv_xxx",
    role="assistant",
    content=json.dumps([
        {
            "type": "tool_use",
            "id": "toolu_xxx",
            "name": "web_search",
            "input": {"query": "Python 教程"}
        }
    ]),
    status=status
)
```

### 查询和排序

```python
# 按步骤顺序查询
messages = await db.execute("""
    SELECT * FROM messages 
    WHERE conversation_id = ? AND status IS NOT NULL
    ORDER BY json_extract(status, '$.index') ASC
""")

# 过滤特定动作类型
messages = await db.execute("""
    SELECT * FROM messages 
    WHERE conversation_id = ?
    AND json_extract(status, '$.action') = 'think'
""")
```

## 📊 完整示例

### 多步骤任务流程

```python
import json
from services.conversation_service import ConversationService

conversation_service = ConversationService()
conversation_id = "conv_xxx"

# 步骤 0: 思考
await conversation_service.add_message(
    conversation_id=conversation_id,
    role="assistant",
    content=json.dumps([
        {"type": "text", "text": "我需要先搜索相关信息..."}
    ]),
    status=json.dumps({
        "index": 0,
        "action": "think",
        "description": "分析任务需求"
    }),
    score=0.9
)

# 步骤 1: 搜索
await conversation_service.add_message(
    conversation_id=conversation_id,
    role="assistant",
    content=json.dumps([
        {
            "type": "tool_use",
            "id": "toolu_001",
            "name": "web_search",
            "input": {"query": "Python 异步编程"}
        }
    ]),
    status=json.dumps({
        "index": 1,
        "action": "action",
        "description": "搜索 Python 异步编程资料"
    })
)

# 步骤 2: 搜索结果
await conversation_service.add_message(
    conversation_id=conversation_id,
    role="assistant",
    content=json.dumps([
        {
            "type": "tool_result",
            "tool_use_id": "toolu_001",
            "content": "找到了相关文档..."
        }
    ]),
    status=json.dumps({
        "index": 2,
        "action": "action",
        "description": "处理搜索结果"
    })
)

# 步骤 3: 最终回复
await conversation_service.add_message(
    conversation_id=conversation_id,
    role="assistant",
    content=json.dumps([
        {"type": "text", "text": "根据搜索结果，Python 异步编程..."}
    ]),
    status=json.dumps({
        "index": 3,
        "action": "respond",
        "description": "生成最终回复"
    }),
    score=0.95
)
```

### 前端显示处理

```javascript
// 获取消息列表
const result = await fetch(`/api/v1/conversations/${convId}/messages`)
const messages = result.data.messages

// 按步骤排序
messages.sort((a, b) => {
    if (!a.status || !b.status) return 0
    const statusA = JSON.parse(a.status)
    const statusB = JSON.parse(b.status)
    return (statusA.index || 0) - (statusB.index || 0)
})

// 显示
messages.forEach(msg => {
    // 解析 content
    const contentBlocks = JSON.parse(msg.content)
    const textBlocks = contentBlocks.filter(b => b.type === 'text')
    const text = textBlocks.map(b => b.text).join('\n')
    
    // 解析 status
    if (msg.status) {
        const status = JSON.parse(msg.status)
        console.log(`步骤 ${status.index}: ${status.action} - ${status.description}`)
    }
    
    console.log(`内容: ${text}`)
})
```

## 🔄 数据迁移

### 执行迁移

```bash
cd /Users/wangkangcheng/projects/zenflux_agent
python migrations/001_update_messages_schema.py
```

### 迁移流程

1. ✅ 检查是否需要迁移
2. ✅ 备份旧表为 `messages_old`
3. ✅ 创建新表结构
4. ✅ 迁移数据（id 转换为 UUID）
5. ✅ 重建索引

### 回滚（如果出错）

```bash
python migrations/001_update_messages_schema.py rollback
```

### 清理备份表（确认无误后）

```sql
DROP TABLE messages_old;
```

## 📌 API 使用示例

### 添加消息（新版）

```python
from services.conversation_service import ConversationService
import json

conversation_service = ConversationService()

# 用户消息（简单文本）
await conversation_service.add_message(
    conversation_id="conv_xxx",
    role="user",
    content=json.dumps([{"type": "text", "text": "你好"}]),
    message_id="msg_user_001"  # 可选，不提供则自动生成
)

# AI 回复（带状态）
await conversation_service.add_message(
    conversation_id="conv_xxx",
    role="assistant",
    content=json.dumps([{"type": "text", "text": "你好！"}]),
    status=json.dumps({
        "index": 0,
        "action": "respond",
        "description": "回复用户问候"
    }),
    metadata={"model": "claude-sonnet-4", "usage": {"tokens": 150}}
)

# AI 回复（包含工具调用）
await conversation_service.add_message(
    conversation_id="conv_xxx",
    role="assistant",
    content=json.dumps([
        {"type": "text", "text": "让我搜索一下"},
        {
            "type": "tool_use",
            "id": "toolu_xxx",
            "name": "web_search",
            "input": {"query": "Python"}
        }
    ]),
    status=json.dumps({
        "index": 1,
        "action": "action",
        "description": "执行网络搜索"
    }),
    score=0.85
)
```

### 查询消息

```python
# 获取对话历史
result = await conversation_service.get_conversation_messages(
    conversation_id="conv_xxx",
    limit=50,
    order="asc"
)

for msg in result["messages"]:
    print(f"ID: {msg['id']}")  # UUID 格式
    print(f"Role: {msg['role']}")
    
    # 解析 status
    if msg['status']:
        status = json.loads(msg['status'])
        print(f"Step: {status['index']}, Action: {status['action']}, Desc: {status['description']}")
    
    # 解析 content
    content_blocks = json.loads(msg['content'])
    for block in content_blocks:
        if block['type'] == 'text':
            print(f"Text: {block['text']}")
        elif block['type'] == 'tool_use':
            print(f"Tool: {block['name']}")
```

## ⚠️ 注意事项

### Content 和 Status 必须是 JSON 字符串

```python
# ✅ 正确
content = json.dumps([{"type": "text", "text": "hello"}])
status = json.dumps({"index": 0, "action": "think", "description": "分析"})

# ❌ 错误
content = "hello"  # 应该是 JSON 数组
status = "think"   # 应该是 JSON 对象
```

### 前端显示处理

```javascript
// 前端解析 content
const message = {
    id: "msg_xxx",
    content: '[{"type":"text","text":"你好"}]',
    status: '{"index":0,"action":"think","description":"思考中"}'
}

// 解析 content
const contentBlocks = JSON.parse(message.content)
const textBlocks = contentBlocks.filter(b => b.type === 'text')
const displayText = textBlocks.map(b => b.text).join('\n')

// 解析 status
if (message.status) {
    const status = JSON.parse(message.status)
    console.log(`步骤 ${status.index}: ${status.description}`)
}
```

## 🎯 后续规划

### Status Action 扩展

已支持的动作类型：
- `"think"`: 思考阶段
- `"action"`: 行动阶段  
- `"plan"`: 规划阶段
- `"validate"`: 验证阶段
- `"reflect"`: 反思阶段
- `"respond"`: 回复阶段

未来可能增加：
- `"research"`: 研究阶段
- `"synthesize"`: 综合阶段
- `"evaluate"`: 评估阶段

### Score 用途

- 自动评估响应质量
- A/B 测试不同提示词
- 用户反馈评分
- 模型性能监控

### 多步骤可视化

利用 status 中的 index 和 description：
- 任务进度追踪界面
- 步骤时间线展示
- 步骤重放和调试
- 性能瓶颈分析

