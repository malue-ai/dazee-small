# Event Manager 事件管理器

## 概述

`core/events.py` 提供了统一的 SSE 事件管理系统，负责：

1. ✅ 标准化事件格式
2. ✅ 自动生成事件 ID
3. ✅ 自动写入 Redis 缓冲
4. ✅ 自动更新心跳
5. ✅ 遵循 SSE 事件协议

## 为什么需要 EventManager？

### ❌ 之前的问题

```python
# 手动创建事件（容易出错）
event = {
    "type": "conversation_start",
    "conversation": conversation_data,
    "timestamp": datetime.now().isoformat()
}
event_id = self.redis.generate_event_id(session_id)
event["id"] = event_id
self.redis.buffer_event(session_id=session_id, event_data=event)
self.redis.update_heartbeat(session_id)
```

**问题**：
- 🔴 重复代码多
- 🔴 容易忘记更新心跳
- 🔴 事件格式不统一
- 🔴 难以维护

### ✅ 使用 EventManager

```python
# 简洁、统一
await self.events.emit_conversation_start(
    session_id=session_id,
    conversation=conversation_data
)
```

**优势**：
- ✅ 一行代码完成所有操作
- ✅ 自动处理 ID、缓冲、心跳
- ✅ 类型提示完整
- ✅ 易于测试和维护

## 架构设计

```
ChatService
    │
    ├── EventManager (核心)
    │   ├── emit_conversation_start()
    │   ├── emit_message_start()
    │   ├── emit_content_block_*()
    │   ├── emit_tool_call_*()
    │   └── emit_error()
    │
    └── RedisManager
        ├── generate_event_id()
        ├── buffer_event()
        └── update_heartbeat()
```

## API 参考

### 1. Conversation 级事件

#### `emit_conversation_start()`

```python
await event_manager.emit_conversation_start(
    session_id="sess_123",
    conversation={
        "id": "conv_456",
        "user_id": "user_789",
        "title": "AI技术讨论",
        "created_at": "2025-12-27T10:00:00Z",
        "metadata": {}
    }
)
```

**生成的事件**：
```json
{
  "id": 1,
  "type": "conversation_start",
  "conversation": {
    "id": "conv_456",
    "user_id": "user_789",
    "title": "AI技术讨论",
    "created_at": "2025-12-27T10:00:00Z",
    "metadata": {}
  },
  "timestamp": "2025-12-27T10:00:00.123Z"
}
```

### 2. Message 级事件

#### `emit_message_start()`

```python
await event_manager.emit_message_start(
    session_id="sess_123",
    message_id="msg_001",
    model="claude-sonnet-4-5-20250929"
)
```

**生成的事件**：
```json
{
  "id": 2,
  "type": "message_start",
  "message": {
    "id": "msg_001",
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
  },
  "timestamp": "2025-12-27T10:00:00.234Z"
}
```

#### `emit_message_delta()`

```python
await event_manager.emit_message_delta(
    session_id="sess_123",
    stop_reason="end_turn",
    output_tokens=150
)
```

#### `emit_message_stop()`

```python
await event_manager.emit_message_stop(
    session_id="sess_123"
)
```

### 3. Content Block 级事件

#### `emit_content_block_start()`

```python
await event_manager.emit_content_block_start(
    session_id="sess_123",
    index=0,
    block_type="thinking"  # 或 "text", "tool_use"
)
```

#### `emit_content_block_delta()`

```python
# Text Delta
await event_manager.emit_content_block_delta(
    session_id="sess_123",
    index=0,
    delta_type="text_delta",
    delta_data={"text": "好的，我来帮你"}
)

# Thinking Delta
await event_manager.emit_content_block_delta(
    session_id="sess_123",
    index=0,
    delta_type="thinking_delta",
    delta_data={"thinking": "让我分析一下..."}
)

# Tool Input Delta
await event_manager.emit_content_block_delta(
    session_id="sess_123",
    index=1,
    delta_type="input_json_delta",
    delta_data={"partial_json": '{"query": "AI'}
)
```

#### `emit_content_block_stop()`

```python
await event_manager.emit_content_block_stop(
    session_id="sess_123",
    index=0
)
```

### 4. Tool Call 事件

#### `emit_tool_call_start()`

```python
await event_manager.emit_tool_call_start(
    session_id="sess_123",
    tool_call_id="toolu_abc123",
    tool_name="web_search",
    tool_input={"query": "AI最新发展"}
)
```

#### `emit_tool_call_complete()`

```python
await event_manager.emit_tool_call_complete(
    session_id="sess_123",
    tool_call_id="toolu_abc123",
    tool_name="web_search",
    status="success",
    result={"results_count": 5},
    duration_ms=1250
)
```

### 5. Error 事件

#### `emit_error()`

```python
await event_manager.emit_error(
    session_id="sess_123",
    error_type="network_error",
    error_message="网络请求超时"
)
```

### 6. 自定义事件

#### `emit_custom()`

```python
await event_manager.emit_custom(
    session_id="sess_123",
    event_type="agent_status",
    event_data={
        "status": "intent_analyzing",
        "message": "正在分析用户意图..."
    }
)
```

## 使用示例

### 完整的消息流程

```python
class ChatService:
    def __init__(self):
        self.redis = get_redis_manager()
        self.events = create_event_manager(self.redis)
    
    async def process_message(self, session_id, user_message):
        """处理用户消息的完整流程"""
        
        # 1. 发送 conversation_start
        await self.events.emit_conversation_start(
            session_id=session_id,
            conversation=conversation_data
        )
        
        # 2. 发送 message_start
        await self.events.emit_message_start(
            session_id=session_id,
            message_id=f"msg_{session_id}",
            model="claude-sonnet-4-5-20250929"
        )
        
        # 3. 发送 content_block_start (thinking)
        await self.events.emit_content_block_start(
            session_id=session_id,
            index=0,
            block_type="thinking"
        )
        
        # 4. 发送 thinking delta
        await self.events.emit_content_block_delta(
            session_id=session_id,
            index=0,
            delta_type="thinking_delta",
            delta_data={"thinking": "让我思考一下..."}
        )
        
        # 5. 发送 content_block_stop
        await self.events.emit_content_block_stop(
            session_id=session_id,
            index=0
        )
        
        # 6. 如果需要调用工具
        await self.events.emit_tool_call_start(
            session_id=session_id,
            tool_call_id="toolu_123",
            tool_name="web_search",
            tool_input={"query": "AI"}
        )
        
        # ... 执行工具 ...
        
        await self.events.emit_tool_call_complete(
            session_id=session_id,
            tool_call_id="toolu_123",
            tool_name="web_search",
            status="success",
            result={"results_count": 5},
            duration_ms=1200
        )
        
        # 7. 发送 message_stop
        await self.events.emit_message_stop(
            session_id=session_id
        )
```

### 错误处理

```python
async def process_with_error_handling(self, session_id):
    try:
        # 正常流程
        await self.process_message(session_id, message)
    
    except NetworkError as e:
        # 发送错误事件
        await self.events.emit_error(
            session_id=session_id,
            error_type="network_error",
            error_message=f"网络请求失败: {str(e)}"
        )
    
    except Exception as e:
        # 发送通用错误
        await self.events.emit_error(
            session_id=session_id,
            error_type="internal_error",
            error_message="系统内部错误"
        )
```

## 与 Agent.stream() 的集成

当前系统中，大部分事件（如 `content_block_*`）是由 `Agent.stream()` 直接生成的：

```python
async def _run_agent_background(self, session_id, agent, message, user_id):
    # 1. 手动发送 conversation_start 和 message_start
    await self.events.emit_conversation_start(...)
    await self.events.emit_message_start(...)
    
    # 2. Agent.stream() 自动生成 content_block_* 事件
    async for event in agent.stream(message):
        event_id = self.redis.generate_event_id(session_id)
        event["id"] = event_id
        self.redis.buffer_event(session_id=session_id, event_data=event)
        self.redis.update_heartbeat(session_id)
    
    # 3. 手动发送 message_stop
    await self.events.emit_message_stop(...)
```

**未来优化方向**：
- 可以修改 `Agent.stream()` 返回的事件，通过 EventManager 统一处理
- 或者在 `Agent.stream()` 内部集成 EventManager

## 测试

```python
import pytest
from core.events import create_event_manager
from services.redis_manager import get_redis_manager

@pytest.fixture
def event_manager():
    redis = get_redis_manager()
    return create_event_manager(redis)

async def test_emit_conversation_start(event_manager):
    """测试 conversation_start 事件"""
    event = await event_manager.emit_conversation_start(
        session_id="test_sess_123",
        conversation={"id": "conv_456"}
    )
    
    assert event["type"] == "conversation_start"
    assert event["id"] > 0
    assert "timestamp" in event
    assert event["conversation"]["id"] == "conv_456"

async def test_emit_message_start(event_manager):
    """测试 message_start 事件"""
    event = await event_manager.emit_message_start(
        session_id="test_sess_123",
        message_id="msg_001",
        model="claude-sonnet-4-5-20250929"
    )
    
    assert event["type"] == "message_start"
    assert event["message"]["id"] == "msg_001"
    assert event["message"]["role"] == "assistant"
    assert event["message"]["usage"]["input_tokens"] == 0
```

## 最佳实践

### ✅ 应该做的

1. **使用 EventManager 发送所有自定义事件**

```python
# ✅ 使用 EventManager
await self.events.emit_conversation_start(...)

# ❌ 不要手动构建事件
event = {"type": "conversation_start", ...}
self.redis.buffer_event(...)
```

2. **利用类型提示**

```python
from core.events import EventManager

class ChatService:
    def __init__(self):
        self.events: EventManager = create_event_manager(...)
```

3. **集中管理事件逻辑**

```python
# ✅ 在 Service 层统一使用 EventManager
class ChatService:
    async def send_status_update(self, session_id, status):
        await self.events.emit_custom(
            session_id=session_id,
            event_type="agent_status",
            event_data={"status": status}
        )
```

### ❌ 不应该做的

1. **不要绕过 EventManager**

```python
# ❌ 不要直接操作 Redis
self.redis.buffer_event(...)
```

2. **不要忘记 await**

```python
# ❌ 忘记 await
self.events.emit_message_start(...)  # 不会生效！

# ✅ 正确
await self.events.emit_message_start(...)
```

3. **不要手动设置 event_id**

```python
# ❌ 不要手动生成 ID
event = {"id": 123, "type": "..."}

# ✅ EventManager 自动处理
await self.events.emit_custom(...)
```

## 扩展 EventManager

如果需要添加新的事件类型：

```python
# core/events.py

class EventManager:
    async def emit_plan_created(
        self,
        session_id: str,
        plan: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        发送 conversation_plan_created 事件
        
        Args:
            session_id: Session ID
            plan: 执行计划
            
        Returns:
            事件对象
        """
        event = {
            "type": "conversation_plan_created",
            "plan": plan,
            "timestamp": datetime.now().isoformat()
        }
        
        return await self._send_event(session_id, event)
```

## 总结

EventManager 提供了：

1. ✅ **统一的事件接口**：所有事件通过统一的方法发送
2. ✅ **自动化处理**：ID、缓冲、心跳自动管理
3. ✅ **类型安全**：完整的类型提示
4. ✅ **易于测试**：清晰的职责边界
5. ✅ **可扩展**：易于添加新事件类型

使用 EventManager 让代码更简洁、更可靠、更易维护！🎉

