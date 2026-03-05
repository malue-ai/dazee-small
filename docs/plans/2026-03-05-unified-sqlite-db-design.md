# 统一 SQLite 数据库设计

> 日期: 2026-03-05
> 状态: 已批准，待实施

## 目标

将项目中散落的 7+ 个 SQLite 数据库文件合并为单一 `zenflux.db`，同时确保已有用户的数据无损迁移。

## 问题

当前每个功能模块各自创建独立的 SQLite 文件：

| DB 文件 | 位置 | 数量 |
|---|---|---|
| `zenflux.db` | `data/db/` | 1（全局） |
| `instance_config.db` | `db/` | 1（全局） |
| `memory_fts.db` | `data/instances/{name}/store/` | N（每实例） |
| `fragments.db` | `data/instances/{name}/store/` | N（每实例） |
| `mem0_vectors_{tag}.db` | `data/instances/{name}/store/` | N*M（每实例*每模型） |
| `mem0_history.db` | `data/instances/{name}/store/` | N（每实例） |
| `playbook_vectors.db` | `data/instances/{name}/store/` | N（每实例） |

3 个实例 + 2 种 embedding 模型 = 20+ 个 DB 文件。

**核心问题：**

1. 各模块独立管理引擎/连接，运维复杂
2. `instance_config_store.py` 使用同步 `sqlite3.connect()`，违反异步优先规则
3. 备份/迁移需同时处理多个文件
4. 跨库查询不可能

## 方案：全量合并到 zenflux.db

### 表结构

**已有表（保持不变）：**

- `conversations` — 会话记录
- `messages` — 消息内容
- `scheduled_tasks` — 定时任务（已有 `instance_id`）
- `skills_cache` — Skill 缓存（已有 `instance_id`）
- `indexed_files` — 文件索引（需加 `instance_id`）
- `cloud_tasks` — 云端任务
- `messages_fts` — FTS5 虚拟表

**迁入表：**

| 原 DB | 新表名 | 变更 |
|---|---|---|
| `instance_config.db` | `instance_config` | 原样迁入，代码改为异步 |
| `memory_fts.db` | `memory_fts` | 加 `instance_id` UNINDEXED 列 |
| `fragments.db` | `fragments` | 加 `instance_id` 列 |
| `mem0_vectors_{tag}.db` | `mem0_vec_{tag}` | sqlite-vec 虚拟表，按模型隔离 |
| `mem0_history.db` | `mem0_history` | 加 `instance_id` 列 |
| `playbook_vectors.db` | `playbook_vec` | sqlite-vec 虚拟表 |

### 实例隔离

所有实例级数据通过 `instance_id` 列区分。不同 embedding 模型的向量通过表名后缀区分（如 `mem0_vec_text_embedding_3_small`）。

### 连接管理

合并后只有一个全局 AsyncEngine（已有），所有模块共用：

- 主 CRUD 操作：通过 `get_local_session()` 获取异步 session
- Mem0 sqlite-vec：保持同步 `sqlite3.connect()` 连接同一 DB 文件（WAL 模式支持并发）
- FTS5 操作：通过 `GenericFTS5` 使用主引擎

## 已有用户数据迁移

### 迁移时机

应用启动时，在 `_init_local_store()` 中执行（与现有 `auto_migrate` 模式一致）。

### 迁移流程

```
应用启动
  → get_local_engine()：初始化 zenflux.db（create_all 建新表）
  → auto_migrate_to_unified_db()：检测旧 DB 文件
    → 对每个旧 DB：
      1. 检查 marker（.migrated_to_unified_db）→ 存在则跳过
      2. 打开旧 DB，逐表读取
      3. 写入 zenflux.db（INSERT OR IGNORE 幂等）
      4. 写入 marker
  → 完成（旧文件保留不删）
```

### 安全保障

- **幂等**：`INSERT OR IGNORE`，重复执行不重复插入
- **原子**：每个旧 DB 的迁移在一个事务内
- **可回滚**：旧文件保留，出问题可回退旧版本
- **marker 文件**：`.migrated_to_unified_db`，防止重复迁移

### Mem0 向量数据特殊处理

`mem0_vectors_{tag}.db` 使用 sqlite-vec 扩展，不能简单 SQL 复制：

1. 通过 sqlite-vec API 读取旧库中的向量数据和 payload
2. 在 zenflux.db 中创建对应的 `mem0_vec_{tag}` 虚拟表
3. 逐条写入新表
4. sqlite-vec 不可用时跳过向量迁移（向量可重建）

## 代码改动范围

| 模块 | 改动 | 复杂度 |
|---|---|---|
| `infra/local_store/engine.py` | `init_local_database` 中创建所有新表 | 低 |
| `infra/local_store/models.py` | 新增 `instance_config`、`fragments`、`mem0_history` ORM 模型 | 中 |
| `infra/local_store/instance_config_store.py` | 同步 sqlite3 → 异步 SQLAlchemy | 高 |
| `core/memory/fragment_store.py` | 移除独立引擎，改用主引擎 | 中 |
| `core/memory/instance_memory.py` | memory_fts 改用主引擎 | 中 |
| `core/memory/mem0/sqlite_vec_store.py` | 连接同一 DB 文件 | 高 |
| `core/memory/mem0/pool.py` | 移除独立 DB 路径逻辑 | 中 |
| `core/memory/mem0/config.py` | 移除 `db_path`/`history_db_name` | 低 |
| `scripts/migrate_to_unified_db.py` | 新增统一迁移脚本 | 高 |
| `main.py` | 调用新迁移 | 低 |

## 风险与缓解

| 风险 | 缓解 |
|---|---|
| Mem0 sqlite_vec_store 同步连接与主引擎异步冲突 | 同步连接同一 DB 文件，WAL 模式支持并发读写 |
| instance_config_store 同步→异步，调用链需全部改为 await | 逐一排查调用方 |
| 单文件 DB 体积增大 | 桌面端数据量有限（<10万行），SQLite 完全能承受 |
| 迁移中途崩溃 | marker + INSERT OR IGNORE 保证可安全重试 |
| 用户回退旧版本 | 旧 DB 文件保留不删，旧版本仍可正常使用 |

## 验证标准

1. 所有现有测试通过
2. 新旧版本数据迁移 E2E 测试
3. 多实例场景下数据隔离正确
4. Mem0 向量搜索功能正常
5. FTS5 全文搜索功能正常
6. `instance_config_store` 异步化后所有调用方正常
