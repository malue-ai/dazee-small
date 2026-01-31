# JSONB 迁移说明

## 一、问题澄清

### 当前实现

**数据库层面**：
- `metadata` 字段类型：`TEXT`（存储 JSON 字符串）
- 存储格式：`'{"key": "value"}'`（字符串）

**应用层面**：
- 通过 `extra_data` 属性自动序列化/反序列化
- 读写方式：应用层使用 `dict`，存储时序列化为 JSON 字符串

```python
# 当前实现（TEXT 类型）
_metadata: Mapped[str] = mapped_column("metadata", Text, default="{}")

@property
def extra_data(self) -> dict:
    return json.loads(self._metadata)  # 手动解析 JSON

@extra_data.setter
def extra_data(self, value: dict):
    self._metadata = json.dumps(value)  # 手动序列化 JSON
```

---

## 二、JSONB vs TEXT 的区别

### TEXT 类型（当前）

**存储**：
- 存储 JSON 字符串：`'{"usage": {"total_tokens": 1000}}'`
- 数据库层面：普通字符串，无法理解 JSON 结构

**查询**：
```sql
-- ❌ 无法高效查询 JSON 字段（需要全表扫描 + JSON 解析）
SELECT * FROM messages WHERE metadata->>'usage'->>'total_tokens'::int > 1000;
-- 性能：O(n)，需要解析每一行的 JSON
```

**更新**：
```sql
-- ❌ 需要整行更新（无法部分更新）
UPDATE messages SET metadata = '{"usage": {...}, "stream": {...}}' WHERE id = ?;
```

---

### JSONB 类型（优化后）

**存储**：
- 存储 JSON 对象：`{"usage": {"total_tokens": 1000}}`
- 数据库层面：原生 JSON 类型，理解 JSON 结构

**查询**：
```sql
-- ✅ 可以使用 GIN 索引，高效查询
SELECT * FROM messages WHERE (metadata->'usage'->>'total_tokens')::int > 1000;
-- 性能：O(log n)，使用 GIN 索引
```

**更新**：
```sql
-- ✅ 支持部分更新（PostgreSQL JSONB 特性）
UPDATE messages SET metadata = jsonb_set(metadata, '{usage,total_tokens}', '2000') WHERE id = ?;
```

---

## 三、应用层直接使用 JSONB（推荐方案）

### ✅ 方案：修改 SQLAlchemy 模型，直接使用 JSONB

**不需要迁移现有数据**，只需要：
1. 修改模型定义（使用 `JSON` 类型，PostgreSQL 自动映射为 JSONB）
2. 移除手动序列化/反序列化代码
3. 应用层直接读写 `dict`

### 修改后的实现

```python
from sqlalchemy import JSON  # PostgreSQL 会自动映射为 JSONB
from sqlalchemy.dialects.postgresql import JSONB  # 或直接使用 JSONB

class Message(Base):
    # 直接使用 JSONB 类型（PostgreSQL）
    metadata: Mapped[dict] = mapped_column(
        JSONB,  # 或 JSON（PostgreSQL 自动映射为 JSONB）
        default={},
        nullable=False
    )
    
    # ✅ 不需要手动序列化/反序列化
    # 应用层直接读写 dict
    msg.metadata = {"usage": {"total_tokens": 1000}}
    usage = msg.metadata["usage"]["total_tokens"]
```

**优势**：
- ✅ 应用层直接读写 `dict`，无需手动序列化
- ✅ 数据库层面自动使用 JSONB
- ✅ 支持高效查询和部分更新
- ✅ 代码更简洁

---

## 四、两种方案对比

### 方案 A：迁移现有数据（不推荐）

**步骤**：
1. 备份数据
2. 执行 `ALTER TABLE` 迁移字段类型
3. 修改模型定义
4. 验证数据完整性

**缺点**：
- ⚠️ 需要维护窗口
- ⚠️ 有数据丢失风险
- ⚠️ 需要停机或锁表

---

### 方案 B：直接修改模型（推荐）✅

**步骤**：
1. 修改 SQLAlchemy 模型定义（使用 `JSONB` 类型）
2. 移除手动序列化代码
3. 重新创建表（开发环境）或使用迁移工具（生产环境）

**优点**：
- ✅ 不需要迁移现有数据
- ✅ 新表直接使用 JSONB
- ✅ 代码更简洁
- ✅ 零风险

**注意**：
- 如果生产环境已有数据，可以使用 Alembic 迁移工具
- 或者：新表用 JSONB，旧数据保持 TEXT（双写兼容）

---

## 五、推荐实施方案

### 5.1 修改模型定义

```python
# infra/database/models/message.py
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import JSON  # 或者使用 JSON（PostgreSQL 自动映射为 JSONB）

class Message(Base):
    # 修改前：TEXT 类型 + 手动序列化
    # _metadata: Mapped[str] = mapped_column("metadata", Text, default="{}")
    
    # 修改后：JSONB 类型，直接读写 dict
    metadata: Mapped[dict] = mapped_column(
        JSONB,  # PostgreSQL JSONB 类型
        default={},
        nullable=False
    )
    
    # ✅ 移除 extra_data 属性（不再需要）
    # @property
    # def extra_data(self) -> dict:
    #     return json.loads(self._metadata)
    
    # 应用层直接使用
    # msg.metadata = {"usage": {"total_tokens": 1000}}
    # usage = msg.metadata["usage"]["total_tokens"]
```

### 5.2 更新应用代码

**修改前**：
```python
# 需要手动序列化
msg.extra_data = {"usage": {"total_tokens": 1000}}
# 实际存储：'{"usage": {"total_tokens": 1000}}'
```

**修改后**：
```python
# 直接使用 dict
msg.metadata = {"usage": {"total_tokens": 1000}}
# 数据库自动处理 JSONB
```

### 5.3 创建 GIN 索引

```sql
-- 创建 GIN 索引（支持高效查询）
CREATE INDEX idx_messages_metadata_usage ON messages USING GIN ((metadata->'usage'));
CREATE INDEX idx_messages_metadata_stream ON messages USING GIN ((metadata->'stream'));
```

---

## 六、总结

### 关键理解

1. **应用层已经在使用 JSON 格式**（通过 `extra_data` 属性）
2. **问题在于数据库字段类型**：TEXT vs JSONB
3. **解决方案**：修改模型定义，直接使用 JSONB 类型
4. **不需要迁移现有数据**：新表直接用 JSONB，代码更简洁

### 推荐做法

✅ **直接修改模型定义**，使用 `JSONB` 类型：
- 应用层直接读写 `dict`
- 数据库自动使用 JSONB
- 支持高效查询和部分更新
- 代码更简洁

❌ **不需要**：
- 迁移现有数据
- 手动序列化/反序列化
- 维护窗口

---

**结论**：你的理解是对的！**可以直接在应用层使用 JSONB 格式**，只需要修改 SQLAlchemy 模型定义即可。
