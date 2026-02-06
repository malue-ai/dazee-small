# Infrastructure 基础设施层

> 提供本地存储和基础设施的统一抽象层

## 目录结构

```
infra/
├── README.md               # 本文档
├── __init__.py             # 统一导出
├── local_store/            # 本地存储（SQLite + FTS5 + sqlite-vec）
│   ├── engine.py           #   异步引擎（aiosqlite + WAL）
│   ├── models.py           #   ORM 模型（会话 / 消息 / Skills 缓存 / 定时任务）
│   ├── fts.py              #   FTS5 全文索引
│   ├── vector.py           #   sqlite-vec 可选向量搜索
│   ├── skills_cache.py     #   Skills 延迟加载缓存
│   ├── workspace.py        #   Workspace 管理器（统一入口）
│   ├── session_store.py    #   Session 内存存储
│   ├── pools.py            #   本地资源池
│   └── crud/               #   CRUD 操作层
│       ├── conversation.py
│       ├── message.py
│       └── scheduled_task.py
├── resilience/             # 弹性机制（熔断、重试）
└── storage/                # 文件存储（本地）
```

## 架构图

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           应用层 (services/)                             │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         infra/ 基础设施层                                │
│                                                                          │
│  ┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐         │
│  │  local_store/    │ │  session_store   │ │  storage/        │         │
│  │  SQLite + FTS5   │ │  内存 Session    │ │  File I/O        │         │
│  │                  │ │                  │ │                  │         │
│  │  • ORM 模型     │ │  • Session 状态  │ │  • 本地存储      │         │
│  │  • CRUD 操作    │ │  • 事件订阅      │ │  • 工具结果      │         │
│  │  • 全文索引     │ │  • 会话管理      │ │                  │         │
│  └──────────────────┘ └──────────────────┘ └──────────────────┘         │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                           本地存储系统                                   │
│              SQLite (WAL)    │    文件系统    │    内存                  │
└─────────────────────────────────────────────────────────────────────────┘
```

## 使用示例

### LocalWorkspace（推荐入口）

```python
from infra.local_store import get_workspace

# 获取 Workspace 实例
workspace = await get_workspace("xiaodazi")

# 会话操作
conv = await workspace.create_conversation(user_id="u1")
msg = await workspace.create_message(conv.id, "user", "你好")

# 全文搜索
results = await workspace.search("你好")
```

### Session 管理

```python
from infra.local_store.session_store import get_local_session_store

store = get_local_session_store()

# 创建 Session
await store.create_session(session_id="s1", user_id="u1", conversation_id="c1")

# 订阅事件流
async for event in store.subscribe_events(session_id="s1"):
    print(event)
```

### 文件存储

```python
from infra.storage import LocalStorage

storage = LocalStorage(base_dir="./workspace/storage")

# 保存文件
path = await storage.save(file, "uploads/doc.pdf")

# 读取文件
content = await storage.get("uploads/doc.pdf")
```

## 模块状态

| 模块 | 状态 | 后端支持 |
|------|------|----------|
| local_store | ✅ 已实现 | SQLite + FTS5 + sqlite-vec |
| session_store | ✅ 已实现 | 内存 |
| storage | ✅ 已实现 | 本地文件系统 |
| resilience | ✅ 已实现 | 熔断器 + 重试 |

## 设计原则

1. **100% 本地**：零外部依赖，无需网络连接
2. **异步优先**：所有 I/O 操作都是异步的
3. **单例管理**：全局单例，避免重复创建连接
4. **优雅降级**：可选功能（如 sqlite-vec）不可用时不影响主流程
