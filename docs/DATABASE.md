# 数据库使用文档

## 概述

项目使用 **SQLite** 作为数据库，通过 `aiosqlite` 提供异步支持。

数据库包含 3 个核心表：
- **users**: 用户表
- **conversations**: 对话表
- **messages**: 消息表

## 数据库结构

### 1. users 表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER | 主键，自增 |
| username | TEXT | 用户名（唯一） |
| email | TEXT | 邮箱（可选） |
| created_at | TIMESTAMP | 创建时间 |
| metadata | TEXT | 元数据（JSON 字符串） |

### 2. conversations 表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER | 主键，自增 |
| user_id | INTEGER | 用户ID（外键） |
| conversation_id | TEXT | 对话唯一标识（唯一） |
| title | TEXT | 对话标题 |
| created_at | TIMESTAMP | 创建时间 |
| updated_at | TIMESTAMP | 更新时间 |
| metadata | TEXT | 元数据（JSON 字符串） |

### 3. messages 表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER | 主键，自增 |
| conversation_id | TEXT | 所属对话ID（外键） |
| role | TEXT | 角色: user/assistant/system |
| content | TEXT | 消息内容 |
| created_at | TIMESTAMP | 创建时间 |
| metadata | TEXT | 元数据（JSON 字符串） |

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 初始化数据库

数据库会在应用启动时自动初始化（见 `main.py` 的 `lifespan` 函数）。

数据库文件位置：`workspace/database/zenflux.db`

### 3. 使用示例

运行示例代码：

```bash
python examples/database_example.py
```

## API 使用

### UserService

```python
from utils.db_service import UserService

# 创建用户
user = await UserService.create_user(
    username="alice",
    email="alice@example.com",
    metadata={"plan": "pro", "source": "web"}
)

# 根据ID获取用户
user = await UserService.get_user_by_id(1)

# 根据用户名获取用户
user = await UserService.get_user_by_username("alice")
```

### ConversationService

```python
from utils.db_service import ConversationService

# 创建对话
conversation = await ConversationService.create_conversation(
    user_id=1,
    conversation_id="conv_20241226_abc123",
    title="关于AI的讨论",
    metadata={"topic": "AI", "language": "zh"}
)

# 获取对话
conversation = await ConversationService.get_conversation("conv_20241226_abc123")

# 获取用户的所有对话
conversations = await ConversationService.get_user_conversations(
    user_id=1,
    limit=50
)

# 更新对话标题
await ConversationService.update_conversation_title(
    conversation_id="conv_20241226_abc123",
    title="深入探讨人工智能"
)

# 更新对话时间戳（有新消息时）
await ConversationService.update_conversation_timestamp("conv_20241226_abc123")
```

### MessageService

```python
from utils.db_service import MessageService

# 创建消息
message = await MessageService.create_message(
    conversation_id="conv_20241226_abc123",
    role="user",
    content="什么是人工智能？",
    metadata={"ip": "127.0.0.1", "device": "web"}
)

# 获取对话的所有消息
messages = await MessageService.get_conversation_messages(
    conversation_id="conv_20241226_abc123"
)

# 获取最近的N条消息
recent_messages = await MessageService.get_recent_messages(
    conversation_id="conv_20241226_abc123",
    limit=10
)
```

## 数据模型

### User 模型

```python
from models.database import User

user = User(
    id=1,
    username="alice",
    email="alice@example.com",
    created_at=datetime.now(),
    metadata={"plan": "pro"}
)
```

### Conversation 模型

```python
from models.database import Conversation

conversation = Conversation(
    id=1,
    user_id=1,
    conversation_id="conv_20241226_abc123",
    title="关于AI的讨论",
    created_at=datetime.now(),
    updated_at=datetime.now(),
    metadata={"topic": "AI"}
)
```

### Message 模型

```python
from models.database import Message

message = Message(
    id=1,
    conversation_id="conv_20241226_abc123",
    role="user",
    content="什么是人工智能？",
    created_at=datetime.now(),
    metadata={"ip": "127.0.0.1"}
)
```

## 最佳实践

### 1. 元数据使用

元数据字段可以存储任意 JSON 数据：

```python
# 用户元数据
user_metadata = {
    "plan": "pro",
    "source": "web",
    "preferences": {
        "language": "zh",
        "theme": "dark"
    }
}

# 对话元数据
conversation_metadata = {
    "topic": "AI",
    "tags": ["技术", "讨论"],
    "language": "zh"
}

# 消息元数据
message_metadata = {
    "ip": "127.0.0.1",
    "device": "web",
    "model": "claude-sonnet-4",
    "tokens": 150
}
```

### 2. 错误处理

```python
from utils.db_service import UserService

try:
    user = await UserService.create_user(
        username="alice",
        email="alice@example.com"
    )
except Exception as e:
    logger.error(f"创建用户失败: {str(e)}", exc_info=True)
```

### 3. 事务处理

对于需要原子性的操作，使用数据库连接的事务：

```python
from utils.database import db_manager

async with await db_manager.get_connection() as db:
    try:
        # 开始事务
        await db.execute("BEGIN")
        
        # 执行多个操作
        await db.execute("INSERT INTO users ...")
        await db.execute("INSERT INTO conversations ...")
        
        # 提交事务
        await db.commit()
    except Exception as e:
        # 回滚事务
        await db.rollback()
        raise
```

### 4. 批量操作

```python
# 批量插入消息
async def batch_insert_messages(messages: List[dict]):
    async with await db_manager.get_connection() as db:
        await db.executemany(
            """
            INSERT INTO messages (conversation_id, role, content, metadata)
            VALUES (?, ?, ?, ?)
            """,
            [
                (msg["conversation_id"], msg["role"], msg["content"], 
                 serialize_metadata(msg.get("metadata")))
                for msg in messages
            ]
        )
        await db.commit()
```

## 数据库维护

### 查看数据库

使用 SQLite 命令行工具：

```bash
sqlite3 workspace/database/zenflux.db

# 查看所有表
.tables

# 查看表结构
.schema users

# 查询数据
SELECT * FROM users;
SELECT * FROM conversations WHERE user_id = 1;
SELECT * FROM messages WHERE conversation_id = 'conv_123' ORDER BY created_at;
```

### 备份数据库

```bash
# 备份
cp workspace/database/zenflux.db workspace/database/zenflux_backup.db

# 或使用 SQLite 命令
sqlite3 workspace/database/zenflux.db ".backup workspace/database/backup.db"
```

### 清理数据

```python
# 删除旧对话（保留最近30天）
async def cleanup_old_conversations(days: int = 30):
    async with await db_manager.get_connection() as db:
        await db.execute(
            """
            DELETE FROM messages 
            WHERE conversation_id IN (
                SELECT conversation_id FROM conversations 
                WHERE updated_at < datetime('now', '-' || ? || ' days')
            )
            """,
            (days,)
        )
        await db.execute(
            """
            DELETE FROM conversations 
            WHERE updated_at < datetime('now', '-' || ? || ' days')
            """,
            (days,)
        )
        await db.commit()
```

## 性能优化

### 索引

数据库已创建以下索引：

- `idx_conversations_user_id`: 加速按用户查询对话
- `idx_messages_conversation_id`: 加速按对话查询消息
- `idx_messages_created_at`: 加速按时间排序

### 查询优化

```python
# ✅ 好的做法：限制返回数量
messages = await MessageService.get_recent_messages(
    conversation_id="conv_123",
    limit=50
)

# ❌ 避免：查询所有消息（对话可能很长）
all_messages = await MessageService.get_conversation_messages("conv_123")
```

## 迁移到生产环境

对于生产环境，建议：

1. **使用 PostgreSQL/MySQL**: SQLite 适合开发和小规模部署
2. **添加连接池**: 使用 `asyncpg` (PostgreSQL) 或 `aiomysql` (MySQL)
3. **使用迁移工具**: 如 Alembic 管理数据库版本
4. **添加更多索引**: 根据查询模式优化
5. **定期备份**: 设置自动备份策略

## 故障排查

### 数据库锁定

如果遇到 "database is locked" 错误：

```python
# 增加超时时间
async with aiosqlite.connect(db_path, timeout=30.0) as db:
    ...
```

### 查看日志

```python
import logging
logging.getLogger("aiosqlite").setLevel(logging.DEBUG)
```

## 参考资料

- [aiosqlite 文档](https://aiosqlite.omnilib.dev/)
- [SQLite 文档](https://www.sqlite.org/docs.html)
- [Pydantic 文档](https://docs.pydantic.dev/)

