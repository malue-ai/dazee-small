# SSE 连接管理与断线重连

> 📅 **最后更新**: 2025-12-30  
> 🎯 **适用版本**: V4.0  
> 🔗 **相关文档**: [统一事件协议](./03-EVENT-PROTOCOL.md) | [架构总览](./00-ARCHITECTURE-V4.md)

---

## 1. 概述

### 1.1 核心问题

在长时间运行的 Agent 任务中（如 PPT 生成、数据分析，可能运行 30 分钟），SSE 连接非常容易断开：

| 场景 | 原因 | 影响 |
|------|------|------|
| 用户刷新页面 | 浏览器关闭 SSE 连接 | 看不到后续进度 |
| 网络波动 | TCP 连接中断 | 丢失事件 |
| 移动端切应用 | 浏览器休眠 | 连接超时 |
| 浏览器自动休眠 | 省电策略 | 连接断开 |

**问题**：SSE 断开后，Agent 还在后台运行，但用户看不到进度和结果。

### 1.2 核心需求

> **用户在任何时候刷新页面，都能重新连接到正在运行的 Agent，并看到实时进度和完整的事件流。**

### 1.3 设计目标

| 目标 | 说明 |
|------|------|
| ✅ **无感刷新** | 用户刷新页面后，自动恢复到正在运行的任务 |
| ✅ **断点续传** | 获取断线期间丢失的所有事件 |
| ✅ **状态可查** | 随时可以查询 Agent 运行状态和进度 |
| ✅ **多端同步** | 同一用户在不同设备/标签页都能看到同一任务 |
| ✅ **自动清理** | 完成的 Session 自动过期，节省存储 |

---

## 2. 架构设计

### 2.1 核心原则：Agent 执行独立于 SSE 连接

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          SSE 断线重连架构                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  用户请求 → POST /api/v1/chat (stream=true)                                  │
│      │                                                                      │
│      ├─ 1. 创建 Session (Redis)                                             │
│      │   └─ session:{session_id}:status                                     │
│      │                                                                      │
│      ├─ 2. 启动后台任务: _run_agent_background()                             │
│      │   ├─ Agent.chat(message)                                             │
│      │   ├─ 每个事件 → EventManager → Redis.buffer_event()                  │
│      │   ├─ 更新心跳 → Redis.update_heartbeat()                             │
│      │   └─ 完成后 → Redis.complete_session(status="completed")             │
│      │                                                                      │
│      └─ 3. 返回 SSE 流: chat_stream()                                       │
│          ├─ 轮询 Redis.get_events(after_id=...)                             │
│          ├─ yield 事件给前端                                                │
│          └─ 检查 Session 状态（completed/failed）                            │
│                                                                             │
│  ⭐ 关键：SSE 断开 ≠ Agent 停止                                              │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 数据流图

```
┌────────────────────────────────────────────────────────────────────────────┐
│                           完整数据流                                         │
├────────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│  ┌─────────┐    POST /chat     ┌─────────────┐                             │
│  │         │ ───────────────→ │             │                             │
│  │ 前端    │                   │  ChatRouter │                             │
│  │         │ ←─── SSE 流 ──── │             │                             │
│  └─────────┘                   └──────┬──────┘                             │
│       │                               │                                    │
│       │                               ▼                                    │
│       │                        ┌─────────────┐     后台任务                 │
│       │                        │             │ ──────────────┐             │
│       │                        │ ChatService │               │             │
│       │                        │             │               ▼             │
│       │                        └──────┬──────┘        ┌─────────────┐      │
│       │                               │               │             │      │
│       │          读取事件             │               │ SimpleAgent │      │
│       │      ┌────────────────────────┘               │             │      │
│       │      │                                        └──────┬──────┘      │
│       │      ▼                                               │             │
│       │  ┌─────────┐                                        │             │
│       │  │         │←─────────── 写入事件 ──────────────────┘             │
│       │  │  Redis  │                                                       │
│       │  │         │←─────────── 更新心跳                                  │
│       │  └─────────┘                                                       │
│       │      │                                                             │
│       │      │ session:{id}:status                                         │
│       │      │ session:{id}:events (List)                                  │
│       │      │ session:{id}:heartbeat                                      │
│       │      │ user:{id}:sessions (Set)                                    │
│       │                                                                    │
│       │  ┌─────────┐                                                       │
│       └─→│         │  断线后                                               │
│          │ 断线    │  1. 查询状态: GET /session/{id}/status                 │
│          │ 重连    │  2. 补偿事件: GET /session/{id}/events?after_id=N      │
│          │         │  3. 重连 SSE: GET /chat/stream?session_id={id}&after=N │
│          └─────────┘                                                       │
│                                                                            │
└────────────────────────────────────────────────────────────────────────────┘
```

### 2.3 三层 ID 体系

```
┌─────────────────────────────────────────────────────────────┐
│                        三层 ID 体系                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  user_id          → 用户标识（永久）                         │
│  ├── conversation_id  → 对话线程（数据库持久化）             │
│  │   └── message_id     → 单条消息（数据库持久化）           │
│  └── session_id       → Agent 运行会话（Redis 临时存储）     │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

| ID 类型 | 用途 | 生命周期 | 存储 | 示例 |
|---------|------|----------|------|------|
| `user_id` | 用户标识 | 永久 | Database | `user_001` |
| `conversation_id` | 对话线程 | 永久 | Database | `conv_abc123` |
| `message_id` | 单条消息 | 永久 | Database | `msg_xyz789` |
| `session_id` | Agent 运行会话 | 运行期间 + 1 分钟 | Redis | `sess_20251230_120000_abc` |

---

## 3. Redis 数据结构

### 3.1 完整键设计

```python
# ==================== Session 相关 ====================

# 1. Session 状态（核心）
Key: session:{session_id}:status
Type: Hash
TTL: 运行中无 TTL，完成后 60 秒

Fields:
├── session_id: str              # Session ID
├── user_id: str                 # 用户 ID
├── conversation_id: str         # 关联的对话 ID
├── message_id: str              # 关联的消息 ID
├── status: str                  # running/completed/failed/timeout/stopped
├── last_event_seq: int          # 最后一个事件的序号
├── start_time: str              # ISO 时间戳
├── last_heartbeat: str          # ISO 时间戳
├── progress: float              # 进度 0-1
├── total_turns: int             # 总轮次
└── message_preview: str         # 消息预览（前100字符）

# 2. 事件缓冲队列
Key: session:{session_id}:events
Type: List (LPUSH + LTRIM)
TTL: 与 session:status 同步

存储格式: JSON 字符串数组（最近 1000 个）
[
  '{"event_uuid":"...","seq":1,"type":"session_start","data":{...},"timestamp":"..."}',
  '{"event_uuid":"...","seq":2,"type":"message_start","data":{...},"timestamp":"..."}',
  ...
]

# 3. Session 心跳
Key: session:{session_id}:heartbeat
Type: String
TTL: 60 秒（自动过期）

Value: ISO 时间戳
"2025-12-30T12:05:30Z"

# 4. Session 内事件序号计数器
Key: session:{session_id}:seq_counter
Type: String (数字)
TTL: 与 session:status 同步

Value: 递增序号
"150"

# 5. 停止标志（用户主动中断）
Key: session:{session_id}:stop_flag
Type: String
TTL: 60 秒

Value: "1"

# ==================== 用户相关 ====================

# 6. 用户的活跃 Sessions
Key: user:{user_id}:sessions
Type: Set
TTL: 3600 秒（1小时）

Members:
- sess_abc123
- sess_def456
```

### 3.2 数据结构关系图

```
┌────────────────────────────────────────────────────────────────────────┐
│                        Redis 数据结构关系                               │
├────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│  User (user_001)                                                       │
│  │                                                                     │
│  └─→ user:user_001:sessions (Set)                                      │
│      ├── sess_abc123                                                   │
│      └── sess_def456                                                   │
│          │                                                             │
│          ▼                                                             │
│      Session (sess_def456)                                             │
│      │                                                                 │
│      ├─→ session:sess_def456:status (Hash)                             │
│      │   ├── session_id: sess_def456                                   │
│      │   ├── user_id: user_001                                         │
│      │   ├── conversation_id: conv_002                                 │
│      │   ├── status: running                                           │
│      │   ├── last_event_seq: 150                                       │
│      │   └── progress: 0.6                                             │
│      │                                                                 │
│      ├─→ session:sess_def456:events (List)                             │
│      │   ├── [0] {"seq":150,"type":"content_delta",...}                │
│      │   ├── [1] {"seq":149,"type":"content_delta",...}                │
│      │   └── ... (最多 1000 个)                                        │
│      │                                                                 │
│      ├─→ session:sess_def456:heartbeat (String)                        │
│      │   └── "2025-12-30T12:05:30Z"                                    │
│      │                                                                 │
│      └─→ session:sess_def456:seq_counter (String)                      │
│          └── "150"                                                     │
│                                                                        │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 4. 代码实现详解

### 4.1 核心组件

```
┌─────────────────────────────────────────────────────────────┐
│                     核心组件关系                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌───────────────┐                                          │
│  │   ChatRouter  │  routers/chat.py                         │
│  │   (HTTP 入口) │                                          │
│  └───────┬───────┘                                          │
│          │                                                  │
│          ▼                                                  │
│  ┌───────────────┐                                          │
│  │  ChatService  │  services/chat_service.py                │
│  │  (业务逻辑)   │                                          │
│  └───────┬───────┘                                          │
│          │                                                  │
│     ┌────┴────┐                                             │
│     │         │                                             │
│     ▼         ▼                                             │
│  ┌───────┐ ┌─────────────────┐                              │
│  │Session│ │RedisSessionMgr │  services/redis_manager.py    │
│  │Service│ │(事件缓冲/心跳) │                              │
│  └───────┘ └────────┬────────┘                              │
│                     │                                       │
│                     ▼                                       │
│             ┌───────────────┐                               │
│             │ EventManager  │  core/events/manager.py       │
│             │ (5层事件管理) │                               │
│             └───────────────┘                               │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 ChatService.chat_stream() 实现

```python
# services/chat_service.py

async def chat_stream(
    self,
    message: List[Dict[str, str]],
    user_id: str,
    conversation_id: Optional[str] = None,
    message_id: Optional[str] = None
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    流式对话执行（支持 SSE 断线重连）
    
    设计原则：
    - Session 创建后立即发送 session_start 和 conversation_start 事件
    - Agent 在后台任务中执行，独立于 SSE 连接
    - 所有事件写入 Redis 缓冲区
    - SSE 从 Redis 读取事件流
    - SSE 断开不影响 Agent 执行
    """
    session_id = None
    try:
        # 🎯 第1步：确保 Conversation 存在
        if not conversation_id:
            conv = await self.conversation_service.create_conversation(
                user_id=user_id,
                title="新对话",
                metadata={}
            )
            conversation_id = conv.id
        
        # 🎯 第2步：创建 Session
        session_id, agent = await self.session_service.create_session(
            user_id=user_id,
            message=message,
            conversation_id=conversation_id,
            message_id=message_id
        )
        
        # 🎯 第3步：立即发送初始事件（在启动 Agent 之前）
        redis = self.session_service.redis
        events = self.session_service.events
        
        await events.session.emit_session_start(
            session_id=session_id,
            user_id=user_id,
            conversation_id=conversation_id
        )
        
        await events.conversation.emit_conversation_start(
            session_id=session_id,
            conversation={...}
        )
        
        # 🎯 第4步：启动后台任务执行 Agent
        agent_task = asyncio.create_task(
            self._run_agent_background(
                session_id=session_id,
                agent=agent,
                message=message,
                user_id=user_id,
                conversation_id=conversation_id
            )
        )
        
        # 🎯 第5步：从 Redis 读取事件流并推送给前端
        last_event_id = 0
        
        while True:
            # 从 Redis 获取新事件
            events_list = redis.get_events(
                session_id=session_id,
                after_id=last_event_id,
                limit=100
            )
            
            # 推送事件
            for event in events_list:
                yield event
                last_event_id = event.get("seq", last_event_id)
            
            # 检查 Agent 是否完成
            session_status = redis.get_session_status(session_id)
            if session_status.get("status") in ["completed", "failed"]:
                break
            
            # 等待一小段时间（100ms）
            await asyncio.sleep(0.1)
    
    except asyncio.CancelledError:
        # SSE 连接被取消（用户刷新页面）
        # Agent 继续在后台运行，不抛出异常
        logger.warning(f"SSE 连接已取消，Agent 继续后台运行")
        raise
```

### 4.3 _run_agent_background() 实现

```python
# services/chat_service.py

async def _run_agent_background(
    self,
    session_id: str,
    agent: SimpleAgent,
    message: str,
    user_id: str,
    conversation_id: str
):
    """
    后台运行 Agent，独立于 SSE 连接
    
    架构说明：
    1. 流式模式 (stream=true)：
       - 前端通过 SSE 实时接收事件（从 Redis 读取）
       - chat_stream() 启动此方法后，从 Redis 推送事件到前端
    
    2. 同步模式 (stream=false)：
       - 前端轮询 /session/{id}/status 查询进度
       - 事件仍写入 Redis（但前端不消费）
       - 前端从数据库读取最终结果
    
    核心原则：
    - Agent 执行逻辑完全相同
    - 事件写入 Redis（EventManager）
    - 结果写入数据库（Message 表）
    - 区别只在前端如何获取信息
    """
    try:
        redis = self.session_service.redis
        events = self.session_service.events
        
        # 发送 message_start 事件
        await events.message.emit_message_start(
            session_id=session_id,
            message_id=assistant_message_id,
            model=self.default_model
        )
        
        # 🔑 关键：调用 agent.chat()
        # 所有事件都会通过 EventManager 写入 Redis
        async for event in agent.chat(
            user_input=message,
            history_messages=history_messages,
            session_id=session_id,
            enable_stream=True
        ):
            # 🛑 检查停止标志（用户主动中断）
            if redis.is_stopped(session_id):
                logger.warning(f"检测到停止标志，中断 Agent 执行")
                self.session_service.end_session(session_id, status="stopped")
                break
            
            # ✅ 事件已经由 EventManager 写入 Redis
            # 不需要 yield，因为 SSE 会从 Redis 读取
            
            # 累积内容用于数据库持久化
            # ...
        
        # 执行完成，结束 Session
        self.session_service.end_session(session_id, status="completed")
    
    except Exception as e:
        logger.error(f"Agent 后台任务失败: {str(e)}")
        self.session_service.end_session(session_id, status="failed")
        raise
```

### 4.4 RedisSessionManager 关键方法

```python
# services/redis_manager.py

class RedisSessionManager:
    """Redis Session 管理器"""
    
    def create_session(
        self,
        session_id: str,
        user_id: str,
        conversation_id: Optional[str] = None,
        message_id: Optional[str] = None,
        message_preview: str = ""
    ) -> None:
        """创建新的 Session"""
        session_status = {
            "session_id": session_id,
            "user_id": user_id,
            "conversation_id": conversation_id or "",
            "message_id": message_id or "",
            "status": "running",
            "last_event_seq": "0",
            "start_time": datetime.now().isoformat(),
            "last_heartbeat": datetime.now().isoformat(),
            "progress": "0.0",
            "total_turns": "0",
            "message_preview": message_preview[:100]
        }
        
        # 保存 Session 状态（运行中不设置 TTL）
        self.client.hset(f"session:{session_id}:status", mapping=session_status)
        
        # 添加到用户的活跃 sessions
        self.client.sadd(f"user:{user_id}:sessions", session_id)
        self.client.expire(f"user:{user_id}:sessions", 3600)
        
        # 初始化心跳（60秒 TTL）
        self.update_heartbeat(session_id)
    
    def generate_session_seq(self, session_id: str) -> int:
        """生成 session 内的事件序号（从 1 开始递增）"""
        return self.client.incr(f"session:{session_id}:seq_counter")
    
    def buffer_event(
        self,
        session_id: str,
        event_data: Dict[str, Any]
    ) -> None:
        """缓冲事件到 Redis"""
        # 写入事件列表（LPUSH 左进）
        self.client.lpush(
            f"session:{session_id}:events",
            json.dumps(event_data, ensure_ascii=False)
        )
        
        # 只保留最近 1000 个事件
        self.client.ltrim(f"session:{session_id}:events", 0, 999)
        
        # 更新 last_event_seq
        if "seq" in event_data:
            self.update_session_status(session_id, last_event_seq=event_data["seq"])
    
    def get_events(
        self,
        session_id: str,
        after_id: Optional[int] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """获取事件列表（支持断点续传）"""
        # 读取所有缓冲的事件
        events_json = self.client.lrange(f"session:{session_id}:events", 0, -1)
        
        if not events_json:
            return []
        
        # 解析并反转（LPUSH 是倒序的）
        events = []
        for event_json in reversed(events_json):
            event = json.loads(event_json)
            events.append(event)
        
        # 过滤 after_id（断点续传）
        if after_id is not None:
            events = [e for e in events if e.get("seq", 0) > after_id]
        
        # 限制数量
        return events[:limit] if limit else events
    
    def update_heartbeat(self, session_id: str) -> None:
        """更新心跳（每产生事件时调用）"""
        now = datetime.now().isoformat()
        
        # 更新心跳时间戳（60秒 TTL）
        self.client.set(f"session:{session_id}:heartbeat", now, ex=60)
        
        # 同步更新 status 中的 last_heartbeat
        self.update_session_status(session_id, last_heartbeat=now)
    
    def complete_session(
        self,
        session_id: str,
        status: str = "completed"
    ) -> None:
        """Session 完成（设置 TTL = 60 秒）"""
        # 更新状态
        self.update_session_status(session_id, status=status)
        
        # 设置 TTL = 60 秒（完成后保留 1 分钟）
        self.client.expire(f"session:{session_id}:status", 60)
        self.client.expire(f"session:{session_id}:events", 60)
        self.client.expire(f"session:{session_id}:heartbeat", 60)
        
        # 从用户活跃列表移除
        status_data = self.get_session_status(session_id)
        if status_data:
            user_id = status_data.get("user_id")
            if user_id:
                self.client.srem(f"user:{user_id}:sessions", session_id)
    
    def set_stop_flag(self, session_id: str) -> None:
        """设置停止标志（用户主动中断）"""
        self.client.set(f"session:{session_id}:stop_flag", "1", ex=60)
    
    def is_stopped(self, session_id: str) -> bool:
        """检查 Session 是否被停止"""
        return self.client.get(f"session:{session_id}:stop_flag") == "1"
```

---

## 5. 断线重连流程

### 5.1 场景1：用户刷新页面

```
┌────────────────────────────────────────────────────────────────────────┐
│                      场景1：用户刷新页面                                │
├────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│  时间线                                                                │
│  ──────────────────────────────────────────────────────────────────   │
│                                                                        │
│  10:00:00  用户发起请求，SSE 连接建立                                   │
│      │                                                                 │
│  10:01:00  Agent 产生事件 1-100，前端接收正常                           │
│      │                                                                 │
│  10:02:00  用户刷新页面                                                │
│      │     ├─ SSE 连接断开 ❌                                          │
│      │     └─ Agent 继续后台运行 ✅                                    │
│      │                                                                 │
│  10:02:05  前端重新加载，执行恢复流程：                                  │
│      │                                                                 │
│      │     1️⃣ 从 localStorage 读取 session_id                          │
│      │        └─ session_id = "sess_abc123"                            │
│      │        └─ last_event_id = 100                                   │
│      │                                                                 │
│      │     2️⃣ 查询 Session 状态                                        │
│      │        GET /api/v1/session/{session_id}/status                  │
│      │        └─ Response: {status: "running", last_event_seq: 150}    │
│      │                                                                 │
│      │     3️⃣ 获取丢失的事件                                           │
│      │        GET /api/v1/session/{session_id}/events?after_id=100     │
│      │        └─ Response: {events: [101, 102, ..., 150]}              │
│      │                                                                 │
│      │     4️⃣ 前端渲染历史事件（101-150）                               │
│      │                                                                 │
│      │     5️⃣ 重新连接 SSE                                             │
│      │        GET /api/v1/chat/stream?session_id={id}&after_id=150     │
│      │                                                                 │
│  10:02:10  继续接收新事件（151+）                                       │
│      │                                                                 │
│  10:05:00  Agent 完成，Session 状态 → "completed"                       │
│                                                                        │
└────────────────────────────────────────────────────────────────────────┘
```

### 5.2 场景2：网络抖动（短暂断线）

```
┌────────────────────────────────────────────────────────────────────────┐
│                      场景2：网络抖动                                    │
├────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│  时间线                                                                │
│  ──────────────────────────────────────────────────────────────────   │
│                                                                        │
│  0s   SSE 连接建立                                                     │
│  1s   Agent 产生事件 1-50，前端接收                                    │
│  2s   网络抖动，SSE 连接断开 ❌                                         │
│        └─ 前端自动检测到 onerror 事件                                  │
│        └─ 保存 last_event_id = 50                                      │
│        └─ Agent 继续产生事件 51-80                                     │
│  2.5s 网络恢复，前端自动重连                                           │
│        └─ GET /chat/stream?session_id={id}&after_id=50                 │
│        └─ 服务端推送事件 51-80（补偿丢失的事件）                         │
│  3s   继续推送新事件 81+                                               │
│                                                                        │
│  ⭐ 关键：EventSource 的 onerror 会触发自动重连                         │
│                                                                        │
└────────────────────────────────────────────────────────────────────────┘
```

### 5.3 场景3：Agent 完成后用户刷新

```
┌────────────────────────────────────────────────────────────────────────┐
│                   场景3：Agent 完成后用户刷新                           │
├────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│  时间线                                                                │
│  ──────────────────────────────────────────────────────────────────   │
│                                                                        │
│  10:10:00  Agent 完成                                                  │
│            ├─ Session 状态 → "completed"                               │
│            ├─ TTL = 60 秒                                              │
│            └─ 结果已写入数据库                                         │
│                                                                        │
│  10:10:30  用户刷新页面                                                │
│                                                                        │
│            1️⃣ 查询 Session 状态                                        │
│               GET /api/v1/session/{session_id}/status                  │
│               └─ Response: {status: "completed", last_event_seq: 500}  │
│                                                                        │
│            2️⃣ 判断：Agent 已完成，不需要连接 SSE                        │
│                                                                        │
│            3️⃣ 获取所有事件（可选）                                      │
│               GET /api/v1/session/{session_id}/events?after_id=0       │
│               └─ Response: 所有事件（1-500）                            │
│                                                                        │
│            4️⃣ 或者：从数据库读取最终结果                                │
│               GET /api/v1/conversation/{conversation_id}/messages      │
│                                                                        │
│  10:11:00  Session 自动过期（60 秒 TTL）                                │
│            └─ Redis 数据删除                                           │
│            └─ 数据库数据保留                                           │
│                                                                        │
└────────────────────────────────────────────────────────────────────────┘
```

### 5.4 场景4：Session 超时（Agent 崩溃）

```
┌────────────────────────────────────────────────────────────────────────┐
│                   场景4：Session 超时                                   │
├────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│  时间线                                                                │
│  ──────────────────────────────────────────────────────────────────   │
│                                                                        │
│  10:00:00  Agent 开始运行                                              │
│  10:01:00  心跳正常更新                                                │
│  10:01:30  心跳正常更新                                                │
│  10:02:00  Agent 崩溃 💥                                               │
│            └─ 停止更新心跳                                             │
│  10:03:00  心跳 TTL 过期（60 秒）                                       │
│            └─ 后台清理任务检测到心跳过期                                │
│            └─ Session 状态 → "timeout"                                 │
│                                                                        │
│  10:03:30  用户刷新页面                                                │
│                                                                        │
│            1️⃣ 查询 Session 状态                                        │
│               GET /api/v1/session/{session_id}/status                  │
│               └─ Response: {status: "timeout", last_event_seq: 120}    │
│                                                                        │
│            2️⃣ 前端显示提示                                             │
│               └─ "任务执行超时，建议重新发起"                            │
│                                                                        │
│            3️⃣ 保留已完成的部分结果                                      │
│               └─ 从 Redis 获取事件 1-120                               │
│               └─ 或从数据库获取已保存的内容                             │
│                                                                        │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 6. API 接口

### 6.1 创建聊天并获取 SSE 流

```http
POST /api/v1/chat
Content-Type: application/json

{
  "message": "帮我生成一个关于AI的PPT",
  "user_id": "user_001",
  "conversation_id": "conv_abc123",  // 可选
  "stream": true                     // 流式模式
}
```

**响应**：SSE 事件流

```
id: uuid-1
event: session_start
data: {"event_uuid":"uuid-1","seq":1,"type":"session_start","session_id":"sess_xxx",...}

id: uuid-2
event: conversation_start
data: {"event_uuid":"uuid-2","seq":2,"type":"conversation_start",...}

id: uuid-3
event: message_start
data: {"event_uuid":"uuid-3","seq":3,"type":"message_start",...}

...

event: done
data: {}
```

### 6.2 查询 Session 状态

```http
GET /api/v1/session/{session_id}/status
```

**响应**：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "session_id": "sess_abc123",
    "user_id": "user_001",
    "conversation_id": "conv_abc123",
    "status": "running",
    "last_event_seq": 150,
    "start_time": "2025-12-30T10:00:00Z",
    "last_heartbeat": "2025-12-30T10:05:30Z",
    "progress": 0.6,
    "total_turns": 5,
    "message_preview": "帮我生成一个关于AI的PPT"
  }
}
```

### 6.3 获取历史事件（断线补偿）

```http
GET /api/v1/session/{session_id}/events?after_id=100&limit=100
```

**响应**：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "session_id": "sess_abc123",
    "events": [
      {"event_uuid": "...", "seq": 101, "type": "content_delta", ...},
      {"event_uuid": "...", "seq": 102, "type": "content_delta", ...},
      ...
    ],
    "total": 50,
    "has_more": false,
    "last_event_seq": 150
  }
}
```

### 6.4 重新连接 SSE（断线重连）

```http
GET /api/v1/chat/stream?session_id={session_id}&after_id=150
Accept: text/event-stream
```

**响应**：SSE 事件流（只推送 seq > 150 的事件）

### 6.5 查询用户的活跃 Sessions

```http
GET /api/v1/user/{user_id}/sessions
```

**响应**：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "user_id": "user_001",
    "sessions": [
      {
        "session_id": "sess_abc123",
        "conversation_id": "conv_001",
        "status": "running",
        "progress": 0.6,
        "message_preview": "帮我生成一个关于AI的PPT"
      },
      {
        "session_id": "sess_def456",
        "conversation_id": "conv_002",
        "status": "running",
        "progress": 0.3,
        "message_preview": "分析这个数据集..."
      }
    ],
    "total": 2
  }
}
```

### 6.6 停止 Session

```http
POST /api/v1/session/{session_id}/stop
```

**响应**：

```json
{
  "code": 200,
  "message": "Session 已标记为停止",
  "data": {
    "session_id": "sess_abc123",
    "status": "stopping"
  }
}
```

---

## 7. 前端集成指南

### 7.1 React Hook 示例

```typescript
import { useState, useEffect, useRef, useCallback } from 'react';

interface Event {
  event_uuid: string;
  seq: number;
  type: string;
  data: any;
  timestamp: string;
}

interface UseAgentStreamOptions {
  message: string;
  userId: string;
  conversationId?: string;
}

interface UseAgentStreamResult {
  events: Event[];
  status: 'connecting' | 'streaming' | 'reconnecting' | 'completed' | 'error';
  sessionId: string | null;
  reconnect: () => void;
}

export function useAgentStream(options: UseAgentStreamOptions): UseAgentStreamResult {
  const { message, userId, conversationId } = options;
  
  const [events, setEvents] = useState<Event[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [status, setStatus] = useState<'connecting' | 'streaming' | 'reconnecting' | 'completed' | 'error'>('connecting');
  
  const lastSeqRef = useRef<number>(0);
  const eventSourceRef = useRef<EventSource | null>(null);

  // 保存到 localStorage（用于页面刷新后恢复）
  const saveToStorage = useCallback((sid: string, seq: number) => {
    localStorage.setItem('current_session_id', sid);
    localStorage.setItem('last_event_seq', seq.toString());
  }, []);

  // 从 localStorage 读取
  const loadFromStorage = useCallback(() => {
    return {
      sessionId: localStorage.getItem('current_session_id'),
      lastSeq: parseInt(localStorage.getItem('last_event_seq') || '0')
    };
  }, []);

  // 清除 localStorage
  const clearStorage = useCallback(() => {
    localStorage.removeItem('current_session_id');
    localStorage.removeItem('last_event_seq');
  }, []);

  // 连接 SSE
  const connect = useCallback(async (sid?: string, afterSeq?: number) => {
    try {
      // 如果有 sessionId，先查询状态
      if (sid) {
        const statusResp = await fetch(`/api/v1/session/${sid}/status`);
        
        if (!statusResp.ok) {
          // Session 不存在或已过期
          clearStorage();
          setStatus('error');
          return;
        }
        
        const statusData = await statusResp.json();
        const sessionStatus = statusData.data.status;
        
        if (sessionStatus === 'completed') {
          setStatus('completed');
          return;
        }
        
        if (sessionStatus === 'timeout') {
          setStatus('error');
          return;
        }
        
        // 获取丢失的事件（断线补偿）
        if (afterSeq && afterSeq > 0) {
          setStatus('reconnecting');
          
          const eventsResp = await fetch(
            `/api/v1/session/${sid}/events?after_id=${afterSeq}`
          );
          
          if (eventsResp.ok) {
            const eventsData = await eventsResp.json();
            const missedEvents = eventsData.data.events;
            
            setEvents(prev => [...prev, ...missedEvents]);
            lastSeqRef.current = eventsData.data.last_event_seq;
            saveToStorage(sid, lastSeqRef.current);
          }
        }
      }

      // 建立 SSE 连接
      const url = sid
        ? `/api/v1/chat/stream?session_id=${sid}&after_id=${lastSeqRef.current}`
        : `/api/v1/chat`;
      
      // 首次连接使用 POST
      if (!sid) {
        const resp = await fetch('/api/v1/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            message,
            user_id: userId,
            conversation_id: conversationId,
            stream: true
          })
        });
        
        // 这里实际上会返回 SSE 流，需要用 EventSource 处理
        // 简化示例，实际实现可能需要调整
      }
      
      // EventSource 连接
      const eventSource = new EventSource(
        sid 
          ? `/api/v1/chat/stream?session_id=${sid}&after_id=${lastSeqRef.current}`
          : `/api/v1/chat?message=${encodeURIComponent(message)}&user_id=${userId}&stream=true`
      );
      
      eventSourceRef.current = eventSource;
      
      eventSource.onopen = () => {
        setStatus('streaming');
      };
      
      eventSource.onmessage = (e) => {
        const event: Event = JSON.parse(e.data);
        
        // 保存 session_id（从第一个事件获取）
        if (event.type === 'session_start' && event.data?.session_id) {
          const newSessionId = event.data.session_id;
          setSessionId(newSessionId);
          saveToStorage(newSessionId, event.seq);
        }
        
        // 更新 lastSeq
        if (event.seq) {
          lastSeqRef.current = Math.max(lastSeqRef.current, event.seq);
          if (sessionId) {
            saveToStorage(sessionId, lastSeqRef.current);
          }
        }
        
        // 去重（防止重复事件）
        setEvents(prev => {
          const exists = prev.some(e => e.event_uuid === event.event_uuid);
          if (exists) return prev;
          return [...prev, event];
        });
        
        // 完成
        if (event.type === 'done' || event.type === 'session_end') {
          eventSource.close();
          setStatus('completed');
          clearStorage();
        }
      };
      
      eventSource.onerror = () => {
        eventSource.close();
        
        // 3 秒后自动重连
        if (sessionId) {
          setTimeout(() => {
            connect(sessionId, lastSeqRef.current);
          }, 3000);
        } else {
          setStatus('error');
        }
      };
      
    } catch (error) {
      console.error('连接失败:', error);
      setStatus('error');
    }
  }, [message, userId, conversationId, sessionId, saveToStorage, clearStorage]);

  // 手动重连
  const reconnect = useCallback(() => {
    if (sessionId) {
      connect(sessionId, lastSeqRef.current);
    }
  }, [sessionId, connect]);

  // 初始化：检查是否需要恢复
  useEffect(() => {
    const { sessionId: savedSessionId, lastSeq } = loadFromStorage();
    
    if (savedSessionId) {
      // 有保存的 session，尝试恢复
      setSessionId(savedSessionId);
      lastSeqRef.current = lastSeq;
      connect(savedSessionId, lastSeq);
    } else {
      // 新连接
      connect();
    }
    
    return () => {
      eventSourceRef.current?.close();
    };
  }, []);

  return { events, status, sessionId, reconnect };
}
```

### 7.2 使用示例

```tsx
function ChatComponent() {
  const { events, status, sessionId, reconnect } = useAgentStream({
    message: '帮我生成一个关于AI的PPT',
    userId: 'user_001'
  });

  return (
    <div>
      {/* 状态指示器 */}
      <div className="status-bar">
        {status === 'connecting' && <span>🔄 连接中...</span>}
        {status === 'streaming' && <span>🟢 实时接收中</span>}
        {status === 'reconnecting' && <span>🔄 重新连接中...</span>}
        {status === 'completed' && <span>✅ 已完成</span>}
        {status === 'error' && (
          <span>
            ❌ 连接失败
            <button onClick={reconnect}>重试</button>
          </span>
        )}
      </div>
      
      {/* Session 信息 */}
      {sessionId && <div className="session-info">Session: {sessionId}</div>}
      
      {/* 事件列表 */}
      <div className="events">
        {events.map(event => (
          <EventDisplay key={event.event_uuid} event={event} />
        ))}
      </div>
    </div>
  );
}

function EventDisplay({ event }: { event: Event }) {
  switch (event.type) {
    case 'content_delta':
      const delta = event.data?.delta;
      if (delta?.type === 'text') {
        return <span className="text">{delta.text}</span>;
      }
      if (delta?.type === 'thinking') {
        return <span className="thinking">{delta.text}</span>;
      }
      return null;
      
    case 'tool_call_start':
      return <div className="tool-call">🔧 调用工具: {event.data?.tool_name}</div>;
      
    case 'tool_call_complete':
      return <div className="tool-result">✅ 工具完成</div>;
      
    default:
      return null;
  }
}
```

---

## 8. 心跳机制与超时清理

### 8.1 心跳更新时机

```python
# 每产生一个事件时更新心跳
async for event in agent.chat(...):
    # ... 处理事件 ...
    redis.update_heartbeat(session_id)  # 自动更新
```

### 8.2 心跳检测逻辑

```
┌────────────────────────────────────────────────────────────────────────┐
│                        心跳机制                                         │
├────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│  心跳 Key: session:{session_id}:heartbeat                              │
│  TTL: 60 秒                                                            │
│                                                                        │
│  ┌─────────────┐     每个事件      ┌─────────────┐                      │
│  │   Agent     │ ──────────────→ │   Redis     │                      │
│  │  执行中     │    update_       │  heartbeat  │                      │
│  │             │    heartbeat()   │  TTL=60s    │                      │
│  └─────────────┘                  └─────────────┘                      │
│                                          │                             │
│                                          │ TTL 倒计时                  │
│                                          ▼                             │
│                               ┌──────────────────┐                     │
│                               │  60 秒无更新？   │                     │
│                               └────────┬─────────┘                     │
│                                        │                               │
│                          ┌─────────────┴─────────────┐                 │
│                          │                           │                 │
│                          ▼ 否                        ▼ 是              │
│                    ┌──────────┐              ┌──────────────┐          │
│                    │ 继续运行 │              │ 标记 timeout │          │
│                    └──────────┘              │ 设置 TTL=60s │          │
│                                              │ 清理资源     │          │
│                                              └──────────────┘          │
│                                                                        │
└────────────────────────────────────────────────────────────────────────┘
```

### 8.3 定时清理任务

```python
# 后台任务：清理超时的 Session（每分钟运行一次）

async def cleanup_timeout_sessions():
    """检查并清理超时的 Session"""
    user_keys = redis_client.keys("user:*:sessions")
    
    for user_key in user_keys:
        session_ids = redis_client.smembers(user_key)
        
        for session_id in session_ids:
            # 检查心跳是否存在
            heartbeat = redis_client.get(f"session:{session_id}:heartbeat")
            
            if not heartbeat:
                # 心跳已过期（超过 60 秒）
                logger.warning(f"Session 超时: {session_id}")
                
                # 标记为 timeout
                redis_client.hset(
                    f"session:{session_id}:status",
                    "status",
                    "timeout"
                )
                
                # 设置 TTL（1 分钟后删除）
                redis_client.expire(f"session:{session_id}:status", 60)
                redis_client.expire(f"session:{session_id}:events", 60)
                
                # 从用户活跃列表移除
                redis_client.srem(user_key, session_id)
```

---

## 9. 错误处理

### 9.1 错误类型

| 错误类型 | HTTP 状态码 | 说明 | 处理方式 |
|----------|-------------|------|----------|
| Session 不存在 | 404 | Session 已完成且超过 1 分钟 | 从数据库读取历史记录 |
| Session 超时 | 200 (status=timeout) | Agent 崩溃或心跳停止 | 提示重新发起请求 |
| 并发限制 | 429 | 用户活跃 Session 过多 | 等待完成后再发起 |
| Redis 满了 | 500 | 事件写入失败 | 配置 maxmemory-policy |

### 9.2 并发限制

```python
async def check_user_session_limit(user_id: str, limit: int = 5):
    """检查用户的活跃 Session 数量"""
    active_sessions = redis_client.scard(f"user:{user_id}:sessions")
    
    if active_sessions >= limit:
        raise HTTPException(
            429,
            f"您已有 {active_sessions} 个任务在运行，请等待完成后再发起新任务"
        )
```

### 9.3 Redis 内存管理

```bash
# redis.conf 配置
maxmemory 2gb
maxmemory-policy allkeys-lru  # 自动淘汰旧数据

# 或者使用 volatile-lru（只淘汰有 TTL 的 key）
```

---

## 10. 监控指标

### 10.1 关键指标

| 指标 | 说明 | 告警阈值 |
|------|------|----------|
| 活跃 Session 总数 | 当前正在运行的 Session | > 1000 |
| 每用户 Session 数 | 单用户并发 Session | > 5 |
| Session 平均运行时长 | 从创建到完成的时间 | > 30 分钟 |
| Session 超时率 | timeout / total | > 5% |
| 事件生成速率 | events/sec | - |
| 事件缓冲区大小 | 单 Session 事件数 | > 800 |
| Redis 内存使用率 | used_memory / maxmemory | > 80% |

### 10.2 日志示例

```
2025-12-30 10:00:00 - INFO - 📨 流式对话请求: user_id=user_001
2025-12-30 10:00:00 - INFO - ✅ Session 已创建: sess_abc123
2025-12-30 10:00:00 - INFO - 📤 已发送 session_start 事件
2025-12-30 10:00:00 - INFO - 📤 已发送 conversation_start 事件
2025-12-30 10:00:00 - INFO - 🚀 Agent 后台任务启动: sess_abc123
2025-12-30 10:00:05 - INFO - 📤 已发送 content_delta 事件 (seq=10)
2025-12-30 10:02:00 - WARNING - ⚠️ SSE 连接已取消，Agent 继续后台运行
2025-12-30 10:05:00 - INFO - ✅ Agent 后台任务完成: sess_abc123
2025-12-30 10:05:00 - INFO - 📤 已发送 session_end 事件
```

---

## 11. 最佳实践

### 11.1 ✅ 应该做的

```python
# 1. 每个事件都更新心跳
async for event in agent.chat(...):
    redis.buffer_event(session_id, event)
    redis.update_heartbeat(session_id)  # ✅

# 2. 使用 EventManager 统一管理事件
await events.content.emit_text_delta(session_id, index, text)  # ✅

# 3. 正确处理 SSE 取消
except asyncio.CancelledError:
    logger.warning("SSE 连接已取消，Agent 继续后台运行")
    raise  # ✅ 不吞异常

# 4. 设置合理的并发限制
if active_sessions >= 5:
    raise HTTPException(429, "...")  # ✅
```

### 11.2 ❌ 不应该做的

```python
# 1. 不要在 Agent 中直接 yield 给 SSE
async for event in agent.chat(...):
    yield event  # ❌ 如果 SSE 断开，Agent 会中断

# 2. 不要忘记设置 TTL
self.client.hset(f"session:{session_id}:status", ...)
# ❌ 忘记 expire，Session 永远不会过期

# 3. 不要吞掉 CancelledError
except asyncio.CancelledError:
    pass  # ❌ 会导致资源泄漏

# 4. 不要无限缓冲事件
self.client.lpush(f"session:{session_id}:events", ...)
# ❌ 忘记 ltrim，Redis 内存爆炸
```

### 11.3 前端最佳实践

```typescript
// 1. 保存 sessionId 到 localStorage
localStorage.setItem('current_session_id', sessionId);  // ✅

// 2. 保存 lastSeq 用于断点续传
localStorage.setItem('last_event_seq', lastSeq.toString());  // ✅

// 3. 使用 event_uuid 去重
const exists = events.some(e => e.event_uuid === newEvent.event_uuid);
if (!exists) setEvents(prev => [...prev, newEvent]);  // ✅

// 4. 监听 onerror 自动重连
eventSource.onerror = () => {
  setTimeout(() => reconnect(sessionId, lastSeq), 3000);  // ✅
};

// 5. 完成后清理 localStorage
if (event.type === 'done') {
  localStorage.removeItem('current_session_id');  // ✅
}
```

---

## 12. 总结

### 12.1 核心优势

| 优势 | 说明 |
|------|------|
| ✅ **用户体验无缝** | 随便刷新，任务继续运行 |
| ✅ **断点续传** | 不丢失任何事件 |
| ✅ **状态可查** | 随时知道 Agent 在做什么 |
| ✅ **自动清理** | 不占用过多存储 |
| ✅ **并发支持** | 支持多任务同时运行 |
| ✅ **容错性强** | SSE 断开不影响 Agent 执行 |
| ✅ **可观测性好** | 所有事件持久化，支持历史回溯 |

### 12.2 实现成本

- **Redis**: 需要足够的内存（建议 2GB+）
- **代码改动**: 中等（Session 管理 + 事件缓冲逻辑）
- **测试**: 需要重点测试断线重连场景

### 12.3 架构决策

| 决策 | 选择 | 原因 |
|------|------|------|
| 事件存储 | Redis List | 高性能、支持 LPUSH + LTRIM |
| 心跳机制 | TTL 自动过期 | 简单可靠 |
| 断点续传 | seq 序号 | Session 内唯一、递增 |
| 去重机制 | event_uuid | 全局唯一、防止重复 |

---

## 13. 相关文档

| 文档 | 说明 |
|------|------|
| [00-ARCHITECTURE-V4.md](./00-ARCHITECTURE-V4.md) | V4.0 完整架构 |
| [03-EVENT-PROTOCOL.md](./03-EVENT-PROTOCOL.md) | 统一事件协议 |
| [01-MEMORY-PROTOCOL.md](./01-MEMORY-PROTOCOL.md) | Memory-First 协议 |

---

**这是一个生产级的 SSE 断线重连方案。** 🎉

