# PostgreSQL 消息存储方案设计

> 版本: 1.0.0  
> 更新时间: 2026-01-19  
> 状态: 📋 方案评审中

## 一、背景

项目已全面采用 PostgreSQL 作为开发和生产环境数据库。本文档对消息存储的三种设计方案进行对比分析。

### 核心使用场景

| 场景 | 操作类型 | 频率 |
|------|---------|------|
| 流式输出 | UPDATE 消息的 content | 高频 |
| 加载历史 | SELECT 获取对话历史 | 中频 |
| 上下文裁剪 | 应用层处理消息列表 | 中频 |

---

## 二、三种方案概述

| 方案 | 描述 | 核心特点 |
|------|------|---------|
| **方案 A** | conversations + messages（每条消息一行） | 规范化设计，传统关系型 |
| **方案 B** | conversations 内嵌 history（JSONB 字典） | 单表设计，消息以 dict 存储 |
| **方案 C** | conversations + messages（每行存储累积历史） | 快照模式，每行包含完整历史 |

---

## 三、方案详解

### 方案 A：规范化设计（每条消息一行）

```sql
-- conversations 表
CREATE TABLE conversations (
    id VARCHAR(64) PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL,
    title VARCHAR(255) DEFAULT '新对话',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- messages 表：每条消息一行
CREATE TABLE messages (
    id VARCHAR(64) PRIMARY KEY,
    conversation_id VARCHAR(64) NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content JSONB NOT NULL,  -- content blocks
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_msg_conv_time ON messages(conversation_id, created_at);
```

#### 数据示例

第一轮对话后：

```
messages 表:
┌────────────┬─────────────────┬───────────┬─────────────────────┐
│ id         │ conversation_id │ role      │ content             │
├────────────┼─────────────────┼───────────┼─────────────────────┤
│ msg_001    │ conv_001        │ user      │ [{"type":"text"...}]│
│ msg_002    │ conv_001        │ assistant │ [{"type":"text"...}]│
└────────────┴─────────────────┴───────────┴─────────────────────┘
```

第二轮对话后：

```
messages 表:
┌────────────┬─────────────────┬───────────┬─────────────────────┐
│ id         │ conversation_id │ role      │ content             │
├────────────┼─────────────────┼───────────┼─────────────────────┤
│ msg_001    │ conv_001        │ user      │ [{"type":"text"...}]│
│ msg_002    │ conv_001        │ assistant │ [{"type":"text"...}]│
│ msg_003    │ conv_001        │ user      │ [{"type":"text"...}]│  ← 新增
│ msg_004    │ conv_001        │ assistant │ [{"type":"text"...}]│  ← 新增
└────────────┴─────────────────┴───────────┴─────────────────────┘
```

#### 查询示例

```sql
-- 加载历史消息
SELECT * FROM messages 
WHERE conversation_id = $1 
ORDER BY created_at ASC;

-- 流式更新单条消息
UPDATE messages SET content = $2 WHERE id = $1;
```

---

### 方案 B：conversation 内嵌 history（JSONB 字典）

```sql
-- conversations 表（包含完整历史）
CREATE TABLE conversations (
    id VARCHAR(64) PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL,
    title VARCHAR(255) DEFAULT '新对话',
    
    -- 核心：history 字段存储所有消息
    history JSONB NOT NULL DEFAULT '{"messages": {}, "currentId": null}',
    
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_conv_user ON conversations(user_id);
CREATE INDEX idx_conv_updated ON conversations(updated_at DESC);
```

#### 数据结构

```json
{
    "messages": {
        "msg_001": {
            "id": "msg_001",
            "role": "user",
            "content": [{"type": "text", "text": "你好"}],
            "timestamp": 1705651200
        },
        "msg_002": {
            "id": "msg_002",
            "role": "assistant",
            "content": [{"type": "text", "text": "你好！有什么可以帮你的？"}],
            "timestamp": 1705651205
        }
    },
    "currentId": "msg_002"
}
```

#### 数据示例

第一轮对话后 `history` 字段：

```json
{
    "messages": {
        "msg_001": {"id": "msg_001", "role": "user", "content": [...]},
        "msg_002": {"id": "msg_002", "role": "assistant", "content": [...]}
    },
    "currentId": "msg_002"
}
```

第二轮对话后 `history` 字段：

```json
{
    "messages": {
        "msg_001": {"id": "msg_001", "role": "user", "content": [...]},
        "msg_002": {"id": "msg_002", "role": "assistant", "content": [...]},
        "msg_003": {"id": "msg_003", "role": "user", "content": [...]},
        "msg_004": {"id": "msg_004", "role": "assistant", "content": [...]}
    },
    "currentId": "msg_004"
}
```

#### 查询示例

```sql
-- 加载整个对话历史
SELECT history->'messages' FROM conversations WHERE id = $1;

-- 更新整个 history（流式更新时）
UPDATE conversations 
SET history = $2, updated_at = NOW()
WHERE id = $1;
```

#### Python 实现示例

```python
async def upsert_message(
    self, 
    conversation_id: str, 
    message_id: str, 
    message: dict
) -> Optional[Conversation]:
    """添加或更新消息到 history"""
    conv = await self.get_conversation(conversation_id)
    if conv is None:
        return None

    history = conv.history or {"messages": {}, "currentId": None}

    # 以 message_id 为键存储/更新消息
    if message_id in history.get("messages", {}):
        history["messages"][message_id] = {
            **history["messages"][message_id],
            **message,  # 合并更新
        }
    else:
        history["messages"][message_id] = message

    history["currentId"] = message_id
    
    return await self.update_conversation(conversation_id, history=history)
```

---

### 方案 C：conversations + messages（累积快照模式）

```sql
-- conversations 表
CREATE TABLE conversations (
    id VARCHAR(64) PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL,
    title VARCHAR(255) DEFAULT '新对话',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- messages 表：每行存储到该轮次为止的完整历史
CREATE TABLE messages (
    id VARCHAR(64) PRIMARY KEY,
    conversation_id VARCHAR(64) NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    turn INT NOT NULL,  -- 轮次编号
    
    -- 核心：history 包含从对话开始到该轮次的所有消息
    history JSONB NOT NULL,
    
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_msg_conv_turn ON messages(conversation_id, turn DESC);
```

#### 数据示例

第一轮对话后：

```
messages 表:
┌────────────┬─────────────────┬──────┬─────────────────────────────────────┐
│ id         │ conversation_id │ turn │ history                             │
├────────────┼─────────────────┼──────┼─────────────────────────────────────┤
│ msg_001    │ conv_001        │ 1    │ {                                   │
│            │                 │      │   "messages": {                     │
│            │                 │      │     "u1": {role: "user", ...},      │
│            │                 │      │     "a1": {role: "assistant", ...}  │
│            │                 │      │   }                                 │
│            │                 │      │ }                                   │
└────────────┴─────────────────┴──────┴─────────────────────────────────────┘
```

第二轮对话后：

```
messages 表:
┌────────────┬─────────────────┬──────┬─────────────────────────────────────┐
│ id         │ conversation_id │ turn │ history                             │
├────────────┼─────────────────┼──────┼─────────────────────────────────────┤
│ msg_001    │ conv_001        │ 1    │ { 2条消息 }                          │
│ msg_002    │ conv_001        │ 2    │ { 4条消息（包含前2条 + 新2条）}       │  ← 新增
└────────────┴─────────────────┴──────┴─────────────────────────────────────┘
```

#### 数据结构详解

turn=1 的 history：
```json
{
    "messages": {
        "u1": {"id": "u1", "role": "user", "content": [{"type": "text", "text": "你好"}]},
        "a1": {"id": "a1", "role": "assistant", "content": [{"type": "text", "text": "你好！"}]}
    },
    "currentId": "a1"
}
```

turn=2 的 history（包含完整历史）：
```json
{
    "messages": {
        "u1": {"id": "u1", "role": "user", "content": [{"type": "text", "text": "你好"}]},
        "a1": {"id": "a1", "role": "assistant", "content": [{"type": "text", "text": "你好！"}]},
        "u2": {"id": "u2", "role": "user", "content": [{"type": "text", "text": "帮我写代码"}]},
        "a2": {"id": "a2", "role": "assistant", "content": [{"type": "text", "text": "好的..."}]}
    },
    "currentId": "a2"
}
```

#### 查询示例

```sql
-- 加载最新历史（只需查最新一行）
SELECT history FROM messages 
WHERE conversation_id = $1 
ORDER BY turn DESC 
LIMIT 1;

-- 回溯到指定轮次
SELECT history FROM messages 
WHERE conversation_id = $1 AND turn = $2;

-- 流式更新当前轮次
UPDATE messages 
SET history = $2
WHERE conversation_id = $1 AND turn = $2;
```

---

## 四、方案对比分析

### 4.1 性能对比

| 操作 | 方案 A | 方案 B | 方案 C |
|------|--------|--------|--------|
| **加载历史** | ⚠️ 多行查询 | ✅ 单行查询 | ✅ 单行查询 |
| **流式更新** | ✅ 单行 UPDATE | ⚠️ 重写整个 JSONB | ⚠️ 重写整个 JSONB |
| **添加消息** | ✅ INSERT 新行 | ⚠️ 更新 JSONB | ⚠️ INSERT + 复制历史 |
| **回溯历史** | ⚠️ 需要 WHERE + 排序 | ❌ 不支持 | ✅ 天然支持 |

### 4.2 存储对比

| 维度 | 方案 A | 方案 B | 方案 C |
|------|--------|--------|--------|
| **存储效率** | ✅ 最优，无冗余 | ✅ 较优 | ❌ 高冗余（N轮 = N份历史） |
| **膨胀风险** | ✅ 正常 | ⚠️ JSONB 更新膨胀 | ⚠️ 每轮存储完整历史 |
| **100轮对话** | 100 行 | 1 个大 JSONB | 100 行，每行递增 |

### 4.3 功能对比

| 功能 | 方案 A | 方案 B | 方案 C |
|------|--------|--------|--------|
| **历史回溯** | ⚠️ 需要额外实现 | ❌ 不支持 | ✅ 天然支持 |
| **消息分支** | ⚠️ 需要 parent_id | ✅ 支持 | ⚠️ 复杂 |
| **单条消息查询** | ✅ 直接查询 | ⚠️ JSONB 路径 | ⚠️ JSONB 路径 |
| **消息搜索** | ✅ 全文索引 | ⚠️ 复杂 | ⚠️ 复杂 |

### 4.4 维护性对比

| 维度 | 方案 A | 方案 B | 方案 C |
|------|--------|--------|--------|
| **Schema 变更** | ✅ ALTER TABLE | ⚠️ 迁移 JSONB | ⚠️ 迁移 JSONB |
| **数据一致性** | ✅ 外键约束 | ⚠️ 应用层保证 | ⚠️ 应用层保证 |
| **调试排查** | ✅ 简单 SQL | ⚠️ JSONB 函数 | ⚠️ JSONB 函数 |

---

## 五、方案选择建议

### 场景匹配

| 场景 | 推荐方案 | 理由 |
|------|---------|------|
| **高频流式更新** | 方案 A | 单行 UPDATE 性能最优 |
| **需要历史回溯** | 方案 C | 天然支持任意轮次回溯 |
| **简单短对话** | 方案 B | 单表设计最简洁 |
| **消息搜索/分析** | 方案 A | 标准 SQL 最灵活 |
| **长对话（100+ 轮）** | 方案 A | 存储效率最优 |

### ZenFlux 项目分析

| 维度 | ZenFlux 需求 | 建议 |
|------|-------------|------|
| **流式更新** | 高频逐 token 更新 | 方案 A 更优 |
| **上下文裁剪** | 服务端裁剪历史 | 方案 A 更灵活 |
| **历史回溯** | 暂不需要 | 方案 A/B 均可 |
| **对话长度** | 可能 100+ 轮 | 方案 A 存储优 |

---

## 六、推荐方案：方案 A（规范化设计）

基于 ZenFlux 的使用场景，**推荐方案 A**。

### 6.1 conversations 表

```sql
CREATE TABLE conversations (
    id VARCHAR(64) PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL,
    title VARCHAR(255) DEFAULT '新对话',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_conv_user ON conversations(user_id);
CREATE INDEX idx_conv_updated ON conversations(updated_at DESC);
```

### 6.2 messages 表

```sql
CREATE TABLE messages (
    id VARCHAR(64) PRIMARY KEY,
    conversation_id VARCHAR(64) NOT NULL 
        REFERENCES conversations(id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL 
        CHECK (role IN ('user', 'assistant', 'system')),
    content JSONB NOT NULL,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_msg_conv_time ON messages(conversation_id, created_at);
```

### 6.3 查询优化

```python
# 加载历史消息
async def get_conversation_messages(session, conversation_id: str):
    stmt = select(Message).where(
        Message.conversation_id == conversation_id
    ).order_by(Message.created_at.asc())
    
    result = await session.execute(stmt)
    return list(result.scalars().all())

# 流式更新
async def update_message_content(session, message_id: str, content: dict):
    stmt = (
        update(Message)
        .where(Message.id == message_id)
        .values(content=content)
    )
    await session.execute(stmt)
    await session.commit()
```

---

## 七、如果选择方案 B 或 C

### 方案 B 实现要点

```python
# 流式更新优化：使用 Redis 缓存
async def stream_update_message(conv_id: str, msg_id: str, delta: str):
    # 1. 流式期间累积到 Redis
    await redis.append(f"stream:{conv_id}:{msg_id}", delta)

# 2. 流式结束后批量写入数据库
async def finalize_stream(conv_id: str, msg_id: str):
    content = await redis.get(f"stream:{conv_id}:{msg_id}")
    
    # 一次性更新 history
    conv = await get_conversation(conv_id)
    conv.history["messages"][msg_id]["content"] = content
    await update_conversation(conv_id, history=conv.history)
    
    await redis.delete(f"stream:{conv_id}:{msg_id}")
```

### 方案 C 实现要点

```python
# 创建新轮次
async def create_turn(conv_id: str, user_msg: dict, assistant_msg: dict):
    # 1. 获取上一轮历史
    prev = await get_latest_message(conv_id)
    prev_history = prev.history if prev else {"messages": {}, "currentId": None}
    
    # 2. 复制并追加新消息
    new_history = copy.deepcopy(prev_history)
    new_history["messages"][user_msg["id"]] = user_msg
    new_history["messages"][assistant_msg["id"]] = assistant_msg
    new_history["currentId"] = assistant_msg["id"]
    
    # 3. 创建新的 message 行
    new_turn = prev.turn + 1 if prev else 1
    await create_message(conv_id, turn=new_turn, history=new_history)
```

---

## 八、总结

| 维度 | 决策 |
|------|------|
| **推荐方案** | 方案 A（规范化设计） |
| **表结构** | conversations + messages |
| **content 字段** | JSONB，支持 content blocks |
| **索引策略** | 复合索引 (conversation_id, created_at) |

### 下一步行动

1. [ ] 评审本方案，确认技术选型
2. [ ] 搭建 PostgreSQL 测试环境
3. [ ] 实现迁移脚本
4. [ ] 性能测试
5. [ ] 更新 ORM Models

---

## 参考资料

- [PostgreSQL JSONB 文档](https://www.postgresql.org/docs/current/datatype-json.html)
- [SQLAlchemy 2.0 异步文档](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html)
- [项目数据库使用文档](../specs/DATABASE.md)
