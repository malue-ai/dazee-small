# Message Status 和 Metadata 字段规范

## 📋 目录

1. [概述](#概述)
2. [Status 字段](#status-字段)
3. [Metadata 字段](#metadata-字段)
4. [更新时机和位置](#更新时机和位置)
5. [完整示例](#完整示例)

---

## 概述

Message 表包含两个重要的字段：

| 字段 | 类型 | 说明 |
|-----|------|------|
| `status` | 字符串 | **消息状态**（processing/completed/stopped/failed） |
| `metadata` | JSON 对象 | **元数据**（completed_at、usage） |

### 核心原则

```
content:  存储消息的实际内容（thinking + text + tool_use + tool_result）
status:   消息的当前状态（字符串）
metadata: 存储元数据（时间戳、token 统计）
```

---

## Status 字段

### 1. Status 的作用

`status` 字段是一个 **简单字符串**，用于标记消息的完成状态。

### 2. Status 枚举值

| 状态 | 说明 | 更新时机 |
|-----|------|---------|
| `processing` | 🔄 生成中 | 消息创建后，Agent 开始生成 |
| `completed` | ✅ 正常完成 | Agent 执行完成，消息已完整保存 |
| `stopped` | 🛑 用户停止 | 用户手动停止生成 |
| `failed` | ❌ 执行失败 | Agent 执行过程中发生错误 |

### 3. Status 更新位置

```python
# services/chat_service.py:585

status = "completed"  # 简化为字符串
```

### 4. Status 使用示例

```python
# 查询已完成的消息
completed_messages = await db.query(Message).filter(
    Message.status == "completed"
).all()

# 查询失败的消息
failed_messages = await db.query(Message).filter(
    Message.status == "failed"
).all()

# 查询正在生成的消息
processing_messages = await db.query(Message).filter(
    Message.status == "processing"
).all()
```

---

## Metadata 字段

### 1. Metadata 的作用

`metadata` 是一个 JSON 对象，用于存储：
- ✅ 时间信息（completed_at）
- ✅ Token 使用统计（usage）

### 2. Metadata 的结构

```json
{
  // === 时间信息 ===
  "completed_at": "2024-01-05T12:34:56.789Z",
  
  // === Token 使用统计 ===
  "usage": {
    "input_tokens": 1500,
    "output_tokens": 800
  }
}
```

### 3. Metadata 字段说明

| 字段 | 类型 | 说明 | 必填 |
|-----|------|------|------|
| `completed_at` | string (ISO 8601) | 消息完成时间 | ✅ |
| `usage` | object | Token 使用统计 | ✅ |
| `usage.input_tokens` | int | 输入 tokens | ✅ |
| `usage.output_tokens` | int | 输出 tokens | ✅ |

### 4. Metadata 更新位置

```python
# services/chat_service.py:591-600

# 构建 metadata（只保留核心信息）
metadata = {
    "completed_at": datetime.now().isoformat(),
}

# 提取 usage 统计
if agent:
    if hasattr(agent, 'llm') and hasattr(agent.llm, 'usage_stats'):
        llm_stats = agent.llm.usage_stats
        if llm_stats:
            metadata["usage"] = {
                "input_tokens": llm_stats.get("total_input_tokens", 0),
                "output_tokens": llm_stats.get("total_output_tokens", 0)
            }

# 保存消息
await self.conversation_service.update_message(
    message_id=message_id,
    content=content_json,
    status=status,
    metadata=metadata  # ← 在这里更新
)
```

### 5. Metadata 合并策略

当更新消息时，metadata 会**合并更新**（不是覆盖）：

```python
# services/conversation_service.py:409-420

# 合并 metadata
existing_metadata = db_msg.extra_data or {}
if metadata:
    existing_metadata.update(metadata)  # ← 合并，不覆盖

# 更新消息
updated_msg = await crud.update_message(
    session=session,
    message_id=message_id,
    content=content,
    status=status,
    metadata=existing_metadata  # ← 使用合并后的 metadata
)
```

---

## 更新时机和位置

### 1. 完整生命周期

```
┌─────────────────────────────────────────────────────────────┐
│ 1. 创建 Assistant 消息（空消息）                              │
│    Location: services/chat_service.py:269-279               │
│    - content: []                                            │
│    - status: null                                           │
│    - metadata: {}                                           │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ 2. Agent 执行（流式累积内容）                                │
│    Location: services/chat_service.py:398-436               │
│    - ContentAccumulator 累积 content blocks                 │
│    - 实时发送 SSE 事件到前端                                │
│    - status 可选更新为 "processing"                         │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ 3. 保存完整消息（message_stop 或循环结束）                   │
│    Location: services/chat_service.py:554-615               │
│                                                             │
│    ✅ 更新 content:                                         │
│       - 从 accumulator 构建 content_blocks                  │
│       - 序列化为 JSON                                       │
│                                                             │
│    ✅ 更新 status:                                          │
│       status = "completed"  # 字符串                        │
│                                                             │
│    ✅ 更新 metadata:                                        │
│       metadata = {                                          │
│         "completed_at": "2024-01-05T12:34:56Z",            │
│         "usage": {                                          │
│           "input_tokens": 1500,                             │
│           "output_tokens": 800                              │
│         }                                                   │
│       }                                                     │
└─────────────────────────────────────────────────────────────┘
```

### 2. 关键代码位置汇总

| 操作 | 文件 | 行号 | 说明 |
|-----|------|------|------|
| 创建空消息 | `services/chat_service.py` | 269-279 | 创建 Assistant 消息占位符 |
| 累积内容 | `services/chat_service.py` | 398-436 | 通过 ContentAccumulator 累积 |
| **设置 status** | `services/chat_service.py` | 585 | status = "completed" |
| **构建 metadata** | `services/chat_service.py` | 591-600 | 提取 usage 统计 |
| **保存消息** | `services/chat_service.py` | 610-615 | 调用 update_message 保存 |
| 合并 metadata | `services/conversation_service.py` | 409-420 | 合并现有 metadata |
| 数据库更新 | `infra/database/crud/message.py` | 56-80 | 更新数据库字段 |

### 3. 更新时机

#### ✅ 正常完成

```python
# services/chat_service.py:432-435

elif event_type == "message_stop" or event_type == "session_end":
    # 🎯 message_stop：保存消息到数据库
    await self._save_assistant_message(
        accumulator, assistant_message_id, agent
    )
    is_finalized = True
```

状态：
- `status` = `"completed"`
- `metadata.completed_at` = 当前时间

#### ⚠️ 用户停止

```python
# services/chat_service.py:405-411

if await redis.is_stopped(session_id):
    logger.warning(f"🛑 检测到停止标志: session_id={session_id}")
    await self._save_assistant_message(
        accumulator, assistant_message_id, agent
    )
    is_finalized = True
    await self.session_service.end_session(session_id, status="stopped")
    break
```

状态：
- `status` = `"stopped"`
- 保存当前已生成的内容

#### ❌ 执行失败

```python
# services/chat_service.py:495-549

except Exception as e:
    logger.error(f"❌ Agent 执行失败: {str(e)}", exc_info=True)
    
    # 发送错误事件
    await self.session_service.events.system.emit_error(...)
    
    # 更新 Session 状态
    await self.session_service.end_session(session_id, status="failed")
```

状态：
- `status` = `"failed"`
- 可能没有 content（如果完全失败）

---

## 完整示例

### 示例 1：简单对话

```json
{
  "id": "msg_abc123",
  "conversation_id": "conv_xyz789",
  "role": "assistant",
  
  // Content: 实际内容
  "content": [
    {
      "type": "text",
      "text": "你好！我是 AI 助手，有什么可以帮助你的吗？"
    }
  ],
  
  // Status: 简单字符串
  "status": "completed",
  
  // Metadata: 核心信息
  "metadata": {
    "completed_at": "2024-01-05T12:34:56.789Z",
    "usage": {
      "input_tokens": 100,
      "output_tokens": 50
    }
  }
}
```

### 示例 2：带 Thinking 的回复

```json
{
  "id": "msg_def456",
  "conversation_id": "conv_xyz789",
  "role": "assistant",
  
  // Content: thinking + text
  "content": [
    {
      "type": "thinking",
      "thinking": "用户问了一个关于 Python 的问题，我需要提供准确的代码示例...",
      "signature": "EqQBCgIYAhIM1gbcDa9GJwZA..."
    },
    {
      "type": "text",
      "text": "这是一个 Python 列表推导式的示例：\n```python\nsquares = [x**2 for x in range(10)]\n```"
    }
  ],
  
  // Status
  "status": "completed",
  
  // Metadata
  "metadata": {
    "completed_at": "2024-01-05T12:35:30.123Z",
    "usage": {
      "input_tokens": 500,
      "output_tokens": 200
    }
  }
}
```

### 示例 3：工具调用

```json
{
  "id": "msg_ghi789",
  "conversation_id": "conv_xyz789",
  "role": "assistant",
  
  // Content: thinking + tool_use + tool_result + text
  "content": [
    {
      "type": "thinking",
      "thinking": "用户想要执行 Python 代码，我需要使用 execute_code 工具...",
      "signature": "EqQBCgIYAhIM..."
    },
    {
      "type": "tool_use",
      "id": "toolu_01A",
      "name": "execute_code",
      "input": {
        "code": "print('Hello, World!')"
      }
    },
    {
      "type": "tool_result",
      "tool_use_id": "toolu_01A",
      "content": "{\"success\": true, \"output\": \"Hello, World!\\n\"}",
      "is_error": false
    },
    {
      "type": "text",
      "text": "代码执行成功！输出为：Hello, World!"
    }
  ],
  
  // Status
  "status": "completed",
  
  // Metadata
  "metadata": {
    "completed_at": "2024-01-05T12:36:45.456Z",
    "usage": {
      "input_tokens": 2500,
      "output_tokens": 1200
    }
  }
}
```

### 示例 4：用户停止生成

```json
{
  "id": "msg_jkl012",
  "conversation_id": "conv_xyz789",
  "role": "assistant",
  
  // Content: 只有部分内容（被中断）
  "content": [
    {
      "type": "text",
      "text": "这是一个关于机器学习的详细解释..."
    }
  ],
  
  // Status: 标记为 stopped
  "status": "stopped",
  
  // Metadata: 仍包含统计信息
  "metadata": {
    "completed_at": "2024-01-05T12:37:20.789Z",
    "usage": {
      "input_tokens": 300,
      "output_tokens": 100
    }
  }
}
```

### 示例 5：执行失败

```json
{
  "id": "msg_mno345",
  "conversation_id": "conv_xyz789",
  "role": "assistant",
  
  // Content: 可能为空或部分内容
  "content": [],
  
  // Status: 标记为 failed
  "status": "failed",
  
  // Metadata: 包含错误信息
  "metadata": {
    "completed_at": "2024-01-05T12:38:00.000Z",
    "error": "API request failed: 429 Rate Limit"
  }
}
```

---

## 最佳实践

### ✅ 应该做的

1. **使用简单字符串作为 status**
   ```python
   status = "completed"  # 不是 JSON 对象
   ```

2. **始终更新 completed_at**
   ```python
   metadata["completed_at"] = datetime.now().isoformat()
   ```

3. **提取 usage 统计**
   ```python
   if agent and hasattr(agent.llm, 'usage_stats'):
       metadata["usage"] = {
           "input_tokens": llm_stats.get("total_input_tokens", 0),
           "output_tokens": llm_stats.get("total_output_tokens", 0)
       }
   ```

4. **根据实际情况设置 status**
   ```python
   # 正常完成
   status = "completed"
   
   # 用户停止
   if was_stopped:
       status = "stopped"
   
   # 执行失败
   except Exception:
       status = "failed"
   ```

### ❌ 不应该做的

1. **不要使用 JSON 对象作为 status**
   ```python
   # ❌ 错误
   status = json.dumps({"action": "completed"})
   
   # ✅ 正确
   status = "completed"
   ```

2. **不要遗漏 usage 统计**
   ```python
   # ❌ 错误：没有提取 usage
   metadata = {"completed_at": "..."}
   
   # ✅ 正确
   metadata = {
       "completed_at": "...",
       "usage": {...}
   }
   ```

3. **不要硬编码 status**
   ```python
   # ❌ 错误：总是 completed
   status = "completed"
   
   # ✅ 正确：根据实际情况设置
   status = "stopped" if was_stopped else "completed"
   ```

---

## 总结

### Status 字段（简化）

- **4 种状态**：`processing`、`completed`、`stopped`、`failed`
- **数据类型**：字符串（不是 JSON 对象）
- **更新位置**：`services/chat_service.py:585`

### Metadata 字段（精简）

- **核心字段**：`completed_at`、`usage`
- **不再包含**：`invocation_stats`（已移除）
- **更新位置**：`services/chat_service.py:591-600`
- **合并策略**：`services/conversation_service.py:409-420`

### 数据流

```
ContentAccumulator
    ↓
_save_assistant_message()
    ↓ status = "completed"
    ↓ metadata = {completed_at, usage}
ConversationService.update_message()
    ↓ 合并 metadata
crud.update_message()
    ↓ 更新数据库
✅ 保存完成
```

相关文档：
- [消息模型](../models/database.py)
- [事件协议](03-EVENT-PROTOCOL.md)
- [数据库架构](08-DATA_STORAGE_ARCHITECTURE.md)
