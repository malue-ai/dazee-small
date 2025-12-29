# SSE 断线重连机制

## 核心设计原则

**Agent 执行独立于 SSE 连接**

### 问题
原始设计中，Agent 的 `stream()` 方法直接通过 `yield` 推送事件给 SSE。如果 SSE 连接断开（用户刷新页面），`yield` 会抛出异常，导致 **Agent 执行中断**。

### 解决方案
**Agent 在后台任务中运行，所有事件写入 Redis，SSE 从 Redis 读取事件流。**

## 架构设计

```
用户请求 → POST /api/v1/chat (stream=true)
    │
    ├─ 创建 Session (Redis)
    │
    ├─ 启动后台任务: _run_agent_background()
    │   ├─ Agent.stream(message)
    │   ├─ 每个事件 → Redis.buffer_event()
    │   ├─ 更新心跳 → Redis.update_heartbeat()
    │   └─ 完成后 → Redis.end_session(status="completed")
    │
    └─ 返回 SSE 流: chat_stream()
        ├─ 轮询 Redis.get_events(after_id=...)
        ├─ yield 事件给前端
        └─ 检查 Session 状态（completed/failed）
```

### 关键点

1. **后台任务**：`asyncio.create_task(_run_agent_background())`
   - Agent 在独立的任务中运行
   - 不受 SSE 连接状态影响

2. **事件缓冲**：所有事件写入 Redis
   - `session:{session_id}:events` 列表（最多 1000 个）
   - 每个事件包含全局递增的 `id` 字段

3. **SSE 轮询**：从 Redis 读取事件
   - `get_events(after_id=...)` 获取新事件
   - 每 100ms 轮询一次
   - 当 Session 状态为 `completed/failed` 时停止

## 代码实现

### 1. ChatService.chat_stream()

```python
async def chat_stream(self, message: str, user_id: str, ...) -> AsyncGenerator:
    # 创建 Session
    session_id, agent = self.create_session(...)
    
    # 🎯 启动后台任务（独立执行）
    agent_task = asyncio.create_task(
        self._run_agent_background(session_id, agent, message)
    )
    
    # 🎯 从 Redis 读取事件流
    last_event_id = 0
    while True:
        # 获取新事件
        events = self.redis.get_events(session_id, after_id=last_event_id)
        
        # 推送事件
        for event in events:
            yield event
            last_event_id = event["id"]
        
        # 检查是否完成
        status = self.redis.get_session_status(session_id)
        if status.get("status") in ["completed", "failed"]:
            break
        
        # 等待 100ms
        await asyncio.sleep(0.1)
```

### 2. ChatService._run_agent_background()

```python
async def _run_agent_background(self, session_id: str, agent: Agent, message: str):
    """后台运行 Agent，独立于 SSE 连接"""
    try:
        # 流式执行 Agent
        async for event in agent.stream(message):
            # 生成事件 ID
            event_id = self.redis.generate_event_id(session_id)
            event["id"] = event_id
            
            # 🎯 写入 Redis（确保事件被持久化）
            self.redis.buffer_event(session_id=session_id, event_data=event)
            
            # 更新心跳
            self.redis.update_heartbeat(session_id)
        
        # 完成
        self.end_session(session_id, status="completed")
    
    except Exception as e:
        logger.error(f"Agent 执行失败: {e}")
        self.end_session(session_id, status="failed")
```

### 3. RedisManager.buffer_event()

```python
def buffer_event(self, session_id: str, event_data: Dict[str, Any]):
    """缓冲事件到 Redis"""
    # 写入事件列表
    self.client.lpush(
        f"session:{session_id}:events",
        json.dumps(event_data, ensure_ascii=False)
    )
    
    # 只保留最近 1000 个事件
    self.client.ltrim(f"session:{session_id}:events", 0, 999)
    
    # 更新 last_event_id
    self.update_session_status(session_id, last_event_id=event_data["id"])
```

## 断线重连流程

### 场景 1: 用户刷新页面（SSE 断开）

```
时间线:
0s  - 用户发起请求，SSE 连接建立
1s  - Agent 产生事件 1-50
2s  - 用户刷新页面，SSE 连接断开 ❌
2s  - Agent 继续执行（不受影响） ✅
3s  - Agent 产生事件 51-100
4s  - 用户重新连接 SSE
4s  - 前端查询状态: GET /api/v1/session/{session_id}/status
4s  - 前端获取丢失事件: GET /api/v1/session/{session_id}/events?after_id=50
4s  - 前端重新连接: GET /api/v1/chat/stream?session_id={id}&after_id=100
5s  - Agent 继续产生事件 101-150
6s  - Agent 完成，Session 状态 → "completed"
```

### 场景 2: 首次连接（正常流程）

```
时间线:
0s  - POST /api/v1/chat (stream=true)
0s  - 创建 Session，启动后台 Agent 任务
0s  - 开始 SSE 流，推送 session_start 事件
1s  - Agent 产生事件，写入 Redis
1s  - SSE 轮询读取事件，推送给前端
2s  - Agent 产生更多事件...
10s - Agent 完成，Session 状态 → "completed"
10s - SSE 推送最后的事件，发送 "done"，关闭连接
```

### 场景 3: 网络抖动（短暂断线）

```
时间线:
0s  - SSE 连接建立
1s  - Agent 产生事件 1-50，前端接收
2s  - 网络抖动，SSE 连接断开 ❌
2s  - 前端自动重连（保存 last_event_id = 50）
2.5s - 重连成功: GET /api/v1/chat/stream?session_id={id}&after_id=50
2.5s - 推送事件 51-100（补偿丢失的事件）
3s  - 继续推送新事件...
```

## Redis 数据结构

### Session 状态
```
Key: session:{session_id}:status
Type: Hash
TTL: 1 小时（running）/ 1 分钟（completed）

Fields:
- session_id: "sess_xxx"
- user_id: "user_001"
- conversation_id: "conv_abc"
- message_id: "msg_xyz"
- status: "running" | "completed" | "failed"
- start_time: "2023-12-27T10:00:00Z"
- last_heartbeat: "2023-12-27T10:05:30Z"
- last_event_id: 150
- total_turns: 5
- message_preview: "帮我生成PPT..."
```

### 事件缓冲
```
Key: session:{session_id}:events
Type: List（LPUSH 左进，最新的在前）
TTL: 跟随 Session 状态

Elements: (JSON strings)
[
  {"id": 150, "type": "tool_call_complete", "data": {...}, "timestamp": "..."},
  {"id": 149, "type": "content_block_delta", "data": {...}, "timestamp": "..."},
  ...
  {"id": 1, "type": "session_start", "data": {...}, "timestamp": "..."}
]

最多保留: 1000 个事件
```

### 用户 Session 列表
```
Key: user:{user_id}:sessions
Type: Set
TTL: 无（成员自动删除）

Members:
- sess_abc123
- sess_def456
- sess_ghi789
```

## 心跳机制

### 目的
判断 Agent 是否还在运行，避免僵尸 Session。

### 实现
```python
# Agent 每产生一个事件，更新心跳
self.redis.update_heartbeat(session_id)

# Redis 存储
hset session:{session_id}:status last_heartbeat "2023-12-27T10:05:30Z"

# 清理超时 Session（定时任务）
def cleanup_timeout_sessions():
    for session_id in all_sessions:
        last_heartbeat = get_last_heartbeat(session_id)
        if now - last_heartbeat > 60s:
            # 超时，标记为 timeout
            update_session_status(session_id, status="timeout")
```

## API 端点

### 1. POST /api/v1/chat (stream=true)
**首次连接，创建 Session 并返回 SSE 流**

```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "帮我生成PPT",
    "user_id": "user_001",
    "stream": true
  }'
```

Response: `text/event-stream`
```
data: {"id": 1, "type": "session_start", "data": {"session_id": "sess_abc"}, ...}

data: {"id": 2, "type": "message_start", "data": {...}, ...}

...

data: {"type": "done", "data": {}, ...}
```

### 2. GET /api/v1/session/{session_id}/status
**查询 Session 状态（用于断线后判断）**

```bash
curl http://localhost:8000/api/v1/session/sess_abc123/status
```

Response:
```json
{
  "code": 200,
  "message": "success",
  "data": {
    "session_id": "sess_abc123",
    "user_id": "user_001",
    "status": "running",
    "last_event_id": 150,
    "start_time": "2023-12-27T10:00:00Z",
    "last_heartbeat": "2023-12-27T10:05:30Z",
    "total_turns": 5
  }
}
```

### 3. GET /api/v1/session/{session_id}/events
**获取丢失的事件（用于断线补偿）**

```bash
curl "http://localhost:8000/api/v1/session/sess_abc123/events?after_id=100&limit=50"
```

Response:
```json
{
  "code": 200,
  "message": "success",
  "data": {
    "session_id": "sess_abc123",
    "events": [
      {"id": 101, "type": "thinking", "data": {...}, "timestamp": "..."},
      {"id": 102, "type": "tool_call", "data": {...}, "timestamp": "..."},
      ...
    ],
    "total": 50,
    "has_more": false,
    "last_event_id": 150
  }
}
```

### 4. GET /api/v1/chat/stream (重连)
**重新连接到已有 Session**

```bash
curl "http://localhost:8000/api/v1/chat/stream?session_id=sess_abc123&after_id=150"
```

Response: `text/event-stream`（只推送 id > 150 的事件）

## 前端实现示例

### React + EventSource

```typescript
import { useState, useEffect, useRef } from 'react';

interface Message {
  id: number;
  type: string;
  data: any;
  timestamp: string;
}

export function useAgentStream(message: string, userId: string) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [status, setStatus] = useState<'connecting' | 'streaming' | 'completed' | 'error'>('connecting');
  const lastEventIdRef = useRef<number>(0);
  const eventSourceRef = useRef<EventSource | null>(null);

  const connect = async () => {
    try {
      // 如果有 sessionId，先查询状态
      if (sessionId) {
        const statusResp = await fetch(`/api/v1/session/${sessionId}/status`);
        const statusData = await statusResp.json();
        
        if (statusData.data.status === 'completed') {
          setStatus('completed');
          return;
        }
        
        // 获取丢失的事件
        if (lastEventIdRef.current > 0) {
          const eventsResp = await fetch(
            `/api/v1/session/${sessionId}/events?after_id=${lastEventIdRef.current}`
          );
          const eventsData = await eventsResp.json();
          
          setMessages(prev => [...prev, ...eventsData.data.events]);
          lastEventIdRef.current = eventsData.data.last_event_id;
        }
      }

      // 建立 SSE 连接
      const url = sessionId
        ? `/api/v1/chat/stream?session_id=${sessionId}&after_id=${lastEventIdRef.current}`
        : `/api/v1/chat/stream?message=${encodeURIComponent(message)}&user_id=${userId}`;
      
      const eventSource = new EventSource(url);
      eventSourceRef.current = eventSource;
      
      eventSource.onopen = () => {
        console.log('SSE 连接已建立');
        setStatus('streaming');
      };
      
      eventSource.onmessage = (e) => {
        const event: Message = JSON.parse(e.data);
        
        // 保存 session_id（第一个事件）
        if (event.type === 'session_start' && event.data.session_id) {
          setSessionId(event.data.session_id);
        }
        
        // 更新 last_event_id
        if (event.id) {
          lastEventIdRef.current = event.id;
        }
        
        // 添加消息
        setMessages(prev => [...prev, event]);
        
        // 完成
        if (event.type === 'done') {
          eventSource.close();
          setStatus('completed');
        }
      };
      
      eventSource.onerror = () => {
        console.error('SSE 连接错误，尝试重连...');
        eventSource.close();
        
        // 3 秒后重连
        setTimeout(() => connect(), 3000);
      };
    } catch (error) {
      console.error('连接失败:', error);
      setStatus('error');
    }
  };

  useEffect(() => {
    connect();
    
    return () => {
      eventSourceRef.current?.close();
    };
  }, []);

  return { messages, status, sessionId };
}
```

## 测试场景

### 1. 正常流程
```bash
# 发起请求
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "帮我生成PPT", "user_id": "user_001", "stream": true}'

# 应该看到事件流持续推送，直到完成
```

### 2. 模拟断线重连
```bash
# 1. 发起请求，记录 session_id（从第一个事件获取）
curl -X POST ... | tee output.txt
# Ctrl+C 中断连接

# 2. 查询状态
curl http://localhost:8000/api/v1/session/{session_id}/status

# 3. 获取丢失的事件
curl "http://localhost:8000/api/v1/session/{session_id}/events?after_id=50"

# 4. 重新连接
curl "http://localhost:8000/api/v1/chat/stream?session_id={session_id}&after_id=100"
```

### 3. 模拟页面刷新
```javascript
// 前端保存 sessionId 和 lastEventId 到 sessionStorage
sessionStorage.setItem('sessionId', sessionId);
sessionStorage.setItem('lastEventId', lastEventId.toString());

// 页面刷新后恢复
const savedSessionId = sessionStorage.getItem('sessionId');
const savedLastEventId = parseInt(sessionStorage.getItem('lastEventId') || '0');

if (savedSessionId) {
  // 重连到已有 Session
  reconnect(savedSessionId, savedLastEventId);
}
```

## 优势

### ✅ 容错性强
- SSE 断开不影响 Agent 执行
- 用户可以随时刷新页面
- 网络抖动自动恢复

### ✅ 可观测性好
- 所有事件持久化到 Redis
- 可以查询历史事件
- 可以查询 Session 状态

### ✅ 性能优化
- 事件缓冲避免过度推送
- 轮询间隔可调（默认 100ms）
- 心跳机制及时清理僵尸 Session

### ✅ 扩展性强
- 支持多用户并发
- 支持水平扩展（Redis 集群）
- 支持长时间运行的任务

## 注意事项

### ⚠️ 内存管理
- Redis 事件列表最多保留 1000 个
- Session 完成后 1 分钟自动清理
- 定期清理超时 Session（60 秒无心跳）

### ⚠️ 并发控制
- 一个用户可以有多个并发 Session
- 每个 Session 独立运行，互不影响

### ⚠️ 异常处理
- Agent 异常会标记 Session 为 "failed"
- SSE 断开不会标记为异常（正常情况）
- 超时会标记为 "timeout"

## 总结

通过将 **Agent 执行** 和 **SSE 推送** 解耦，我们实现了：
1. 用户可以随时刷新页面，不影响任务执行
2. 断线后可以无缝重连，补偿丢失的事件
3. 所有事件持久化，支持历史回溯
4. 多用户并发，水平扩展

这是一个 **生产级** 的 SSE 断线重连方案。

