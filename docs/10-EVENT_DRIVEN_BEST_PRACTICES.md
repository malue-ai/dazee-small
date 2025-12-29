# 事件驱动架构最佳实践

## 🎯 核心特点：完全事件驱动

你的观察非常准确！这个项目的**核心架构特点**就是**事件驱动（Event-Driven Architecture）**。

### 当前的事件流

```
┌─────────────┐
│   Agent     │ 生成事件
└──────┬──────┘
       │ emit_event()
       ↓
┌─────────────┐
│ EventManager│ 标准化事件
└──────┬──────┘
       │ buffer_event()
       ↓
┌─────────────┐
│   Redis     │ 事件缓冲
└──────┬──────┘
       │
       ├─→ SSE Stream → 前端（实时显示）
       │
       └─→ Event Listener → 数据库（持久化）
```

### 关键特点

1. **Agent 不直接操作数据库** - 只发送事件
2. **数据库更新基于事件** - 监听特定事件类型触发
3. **解耦生产者和消费者** - Redis 作为中间层
4. **支持多种消费者** - SSE、数据库、日志、监控等

---

## ⚠️ 事件驱动架构的核心挑战

### 1. **事件顺序性（Event Ordering）**

#### 问题
```python
# 事件可能乱序到达
Event 1: content_delta (seq=5)
Event 2: content_delta (seq=3)  # ❌ 乱序
Event 3: content_delta (seq=4)
```

#### 解决方案
```python
# ✅ 当前实现
{
    "event_uuid": "xxx",  # 全局唯一ID
    "seq": 5,             # Session 内严格递增序号
    "timestamp": "..."    # 时间戳
}

# 消费者按 seq 排序
events.sort(key=lambda e: e["seq"])
```

#### 最佳实践
- ✅ 使用 `seq` 字段保证顺序
- ✅ 消费者在处理前排序
- ✅ 断线重连时用 `seq` 填补缺失事件

---

### 2. **事件幂等性（Idempotency）**

#### 问题
```python
# 同一个事件可能被处理多次（网络重试、断线重连）
save_message(content="Hello")  # 第1次
save_message(content="Hello")  # 第2次（重复）
```

#### 解决方案
```python
# ✅ 使用 event_uuid 作为幂等键
async def save_message_from_event(event):
    event_uuid = event["event_uuid"]
    
    # 检查是否已处理过
    if await redis.exists(f"processed:{event_uuid}"):
        logger.info(f"事件已处理，跳过: {event_uuid}")
        return
    
    # 处理事件
    await db.save_message(...)
    
    # 标记为已处理（7天过期）
    await redis.setex(f"processed:{event_uuid}", 604800, "1")
```

#### 最佳实践
- ✅ 每个事件必须有全局唯一ID
- ✅ 数据库操作前检查是否已处理
- ✅ 使用 Redis 存储已处理事件ID
- ✅ 设置合理的过期时间（避免内存泄漏）

---

### 3. **事件完整性（Event Completeness）**

#### 问题
```python
# 某些关键事件丢失
content_start → content_delta → ❌ (missing content_stop)

# 数据库无法判断消息是否完整
```

#### 解决方案（当前实现）
```python
# ✅ 在 chat_service.py
message_saved = False

async for event in agent.chat(...):
    if event_type == "content_delta":
        assistant_content += text
    
    # 🎯 关键：在特定事件触发数据库保存
    if event_type in ["complete", "message_stop", "session_end"]:
        if not message_saved:
            await save_to_database(assistant_content)
            message_saved = True

# 🎯 兜底机制：循环结束仍未保存
if not message_saved and assistant_content:
    logger.warning("事件流不完整，执行兜底保存")
    await save_to_database(assistant_content)
```

#### 最佳实践
- ✅ 定义明确的"完成"事件（`complete`, `message_stop`）
- ✅ 实现兜底机制（fallback）
- ✅ 记录不完整的事件流（监控告警）
- ✅ 超时检测（如果 N 秒没有新事件，强制完成）

---

### 4. **事件重放（Event Replay）**

#### 问题
```python
# 用户刷新页面，需要恢复之前的事件
# 数据库中已有完整消息，但前端需要事件流
```

#### 解决方案
```python
# ✅ 断线重连机制
async def reconnect_sse(session_id: str, last_seq: int):
    # 1. 检查 session 状态
    status = await redis.get_session_status(session_id)
    
    # 2. 获取丢失的事件
    missing_events = await redis.get_events(
        session_id=session_id,
        after_seq=last_seq  # 使用 seq 而不是 event_uuid
    )
    
    # 3. 重放事件
    for event in missing_events:
        yield event
    
    # 4. 如果 session 已完成，发送 done
    if status["status"] == "completed":
        yield {"type": "done"}
```

#### 最佳实践
- ✅ Redis 保留最近 1000 个事件
- ✅ 使用 `seq` 字段定位缺失事件
- ✅ 提供 `/session/{id}/events?after_seq=N` 接口
- ✅ 设置合理的 TTL（事件过期后从数据库读取）

---

### 5. **事件版本控制（Event Versioning）**

#### 问题
```python
# 事件结构变更导致消费者崩溃
# 旧版本
{"type": "content_delta", "text": "hello"}

# 新版本
{"type": "content_delta", "delta": {"type": "text", "text": "hello"}}
```

#### 解决方案
```python
# ✅ 在事件中添加版本字段
{
    "event_uuid": "xxx",
    "seq": 1,
    "version": "2.0",  # 事件结构版本
    "type": "content_delta",
    "data": {...}
}

# 消费者处理
def handle_content_delta(event):
    version = event.get("version", "1.0")
    
    if version == "1.0":
        # 兼容旧版本
        text = event["text"]
    elif version == "2.0":
        # 新版本
        text = event["data"]["delta"]["text"]
    else:
        raise UnsupportedVersionError(f"不支持版本 {version}")
```

#### 最佳实践
- ✅ 在事件中包含 `version` 字段
- ✅ 保持向后兼容（至少 N 个版本）
- ✅ 消费者检查版本，优雅降级
- ✅ 版本变更记录在文档中

---

### 6. **事件死信队列（Dead Letter Queue）**

#### 问题
```python
# 某些事件处理失败，被丢弃
try:
    await handle_event(event)
except Exception:
    pass  # ❌ 事件丢失
```

#### 解决方案
```python
# ✅ 实现死信队列
async def handle_event_with_dlq(event):
    max_retries = 3
    retry_count = event.get("retry_count", 0)
    
    try:
        await handle_event(event)
    except Exception as e:
        logger.error(f"事件处理失败: {e}")
        
        if retry_count < max_retries:
            # 重试
            event["retry_count"] = retry_count + 1
            await redis.lpush("event_retry_queue", json.dumps(event))
        else:
            # 放入死信队列
            await redis.lpush("event_dlq", json.dumps(event))
            # 发送告警
            await send_alert(f"事件处理失败 {max_retries} 次: {event['event_uuid']}")
```

#### 最佳实践
- ✅ 实现重试机制（指数退避）
- ✅ 设置最大重试次数
- ✅ 失败事件进入死信队列
- ✅ 监控 DLQ 大小，及时告警

---

### 7. **事件溯源（Event Sourcing）**

#### 问题
```python
# 只存储最终状态，无法追溯过程
messages = [{"role": "assistant", "content": "最终回复"}]
# ❌ 无法知道 AI 经历了哪些步骤
```

#### 解决方案（当前实现）
```python
# ✅ 使用 status 字段记录步骤
await conversation_service.add_message(
    conversation_id="conv_xxx",
    role="assistant",
    content=json.dumps([{"type": "text", "text": "..."}]),
    status=json.dumps({
        "index": 0,
        "action": "think",
        "description": "分析任务"
    })
)

# 每个步骤都是独立的消息
await conversation_service.add_message(
    status=json.dumps({
        "index": 1,
        "action": "action",
        "description": "执行搜索"
    })
)
```

#### 最佳实践
- ✅ 每个重要步骤记录为独立消息
- ✅ 使用 `status.index` 排序步骤
- ✅ 保留完整的工具调用链（content blocks）
- ✅ 可以重放整个过程（调试和审计）

---

## 📋 事件驱动架构检查清单

### ✅ 当前已实现

- [x] **事件标准化**: 统一的事件结构（event_uuid, seq, type, data）
- [x] **事件排序**: 使用 `seq` 保证顺序
- [x] **事件缓冲**: Redis 缓冲最近 1000 个事件
- [x] **断线重连**: 支持从 `after_seq` 获取缺失事件
- [x] **数据库触发**: 在 `complete` 等事件触发持久化
- [x] **兜底机制**: Agent 循环结束时强制保存
- [x] **事件溯源**: 使用 status 记录多步骤过程

### ⚠️ 需要加强

- [ ] **事件幂等性**: 添加已处理事件检查
- [ ] **事件版本控制**: 添加 `version` 字段
- [ ] **死信队列**: 处理失败事件的重试机制
- [ ] **超时检测**: 长时间无事件时强制完成
- [ ] **事件监控**: Prometheus 指标（事件速率、延迟、失败率）
- [ ] **事件审计**: 记录所有事件到日志系统

---

## 🏗️ 推荐的事件处理模式

### 模式 1: 事件监听器（Event Listener）

```python
# event_listeners.py
class MessageCompletionListener:
    """监听消息完成事件，触发数据库保存"""
    
    async def on_event(self, event: Dict[str, Any]):
        if event["type"] in ["complete", "message_stop", "session_end"]:
            await self.save_to_database(event)
    
    async def save_to_database(self, event: Dict[str, Any]):
        session_id = event["session_id"]
        
        # 从 Redis 获取累积的内容
        content = await redis.get(f"session:{session_id}:content")
        thinking = await redis.get(f"session:{session_id}:thinking")
        
        # 保存到数据库
        await conversation_service.add_message(
            conversation_id=event["conversation_id"],
            role="assistant",
            content=content,
            status=json.dumps({
                "index": event.get("turn", 0),
                "action": "respond",
                "description": "最终回复"
            })
        )
```

### 模式 2: 事件聚合器（Event Aggregator）

```python
# event_aggregator.py
class ContentAggregator:
    """聚合 content_delta 事件为完整内容"""
    
    def __init__(self):
        self.buffers = {}  # {session_id: {"content": "", "thinking": ""}}
    
    async def on_content_delta(self, event: Dict[str, Any]):
        session_id = event["session_id"]
        delta_type = event["data"]["delta"]["type"]
        text = event["data"]["delta"]["text"]
        
        if session_id not in self.buffers:
            self.buffers[session_id] = {"content": "", "thinking": ""}
        
        if delta_type == "text":
            self.buffers[session_id]["content"] += text
        elif delta_type == "thinking":
            self.buffers[session_id]["thinking"] += text
        
        # 同步到 Redis（供其他消费者使用）
        await redis.set(
            f"session:{session_id}:content",
            self.buffers[session_id]["content"]
        )
    
    async def on_complete(self, event: Dict[str, Any]):
        session_id = event["session_id"]
        
        # 获取完整内容
        content = self.buffers.get(session_id, {}).get("content", "")
        thinking = self.buffers.get(session_id, {}).get("thinking", "")
        
        # 清理缓冲区
        del self.buffers[session_id]
        
        return {"content": content, "thinking": thinking}
```

### 模式 3: 事件投影器（Event Projector）

```python
# event_projector.py
class SessionProgressProjector:
    """将事件流投影为 Session 进度视图"""
    
    async def project(self, session_id: str) -> Dict[str, Any]:
        events = await redis.get_events(session_id)
        
        progress = {
            "total_events": len(events),
            "turns": 0,
            "tool_calls": 0,
            "thinking_blocks": 0,
            "text_blocks": 0,
            "status": "running"
        }
        
        for event in events:
            if event["type"] == "turn_progress":
                progress["turns"] += 1
            elif event["type"] == "tool_call_start":
                progress["tool_calls"] += 1
            elif event["type"] == "content_start":
                if event["data"]["block_type"] == "thinking":
                    progress["thinking_blocks"] += 1
                elif event["data"]["block_type"] == "text":
                    progress["text_blocks"] += 1
            elif event["type"] in ["complete", "session_end"]:
                progress["status"] = "completed"
        
        return progress
```

---

## 🎯 实践建议

### 1. **明确事件边界**
```python
# ✅ 好的事件设计
{
    "type": "message_complete",
    "data": {
        "message_id": "msg_xxx",
        "content": "完整内容",
        "turn": 1,
        "final": True
    }
}

# ❌ 坏的事件设计
{
    "type": "update",  # 太模糊
    "data": {...}      # 不知道更新了什么
}
```

### 2. **事件不应该太大**
```python
# ❌ 避免
{
    "type": "history_loaded",
    "data": {
        "messages": [...1000条消息...]  # 太大
    }
}

# ✅ 改为
{
    "type": "history_loaded",
    "data": {
        "message_count": 1000,
        "summary": "..."
    }
}
# 实际数据从 API 获取
```

### 3. **事件应该是不可变的**
```python
# ❌ 避免修改已发送的事件
event["data"]["content"] = "modified"  # 不要这样做

# ✅ 发送新事件
await emit_event({
    "type": "content_updated",
    "data": {"new_content": "..."}
})
```

### 4. **使用事件类型命名约定**
```python
# ✅ 推荐的命名模式
"entity_action"       # session_start, message_stop
"entity_state"        # session_completed, message_saved
"entity_action_phase" # content_delta, tool_call_start
```

---

## 📊 监控指标

```python
# 关键指标
- event_rate: 每秒事件数
- event_latency: 事件从生成到处理的延迟
- event_failure_rate: 事件处理失败率
- buffer_size: Redis 缓冲区大小
- dlq_size: 死信队列大小
- session_duration: Session 平均持续时间
```

---

## 🎓 总结

事件驱动架构的核心是**解耦**和**可追溯**。你的项目做得很好：

1. ✅ **Agent 专注于生成事件**，不关心谁消费
2. ✅ **数据库基于事件更新**，而不是直接调用
3. ✅ **支持多种消费者**（SSE、数据库、监控）
4. ✅ **可以重放事件流**（断线重连、调试）

需要注意的关键点：
- ⚠️ **事件顺序** - 使用 `seq`
- ⚠️ **事件幂等性** - 避免重复处理
- ⚠️ **事件完整性** - 兜底机制
- ⚠️ **事件溯源** - 保留完整历史

继续保持这个架构，它会让系统非常灵活和可维护！🎉

