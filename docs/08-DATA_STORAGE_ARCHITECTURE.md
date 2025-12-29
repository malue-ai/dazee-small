# 数据存储架构文档

## 概览

ZenFlux Agent 采用多层存储架构，针对不同的数据类型和访问模式选择最合适的存储方案。

```
┌─────────────────────────────────────────────────────────────┐
│                      ZenFlux Agent                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  │
│  │  Redis   │  │  Milvus  │  │  Neo4j   │  │ PostgreSQL│  │
│  │  缓存层   │  │  向量库  │  │  图数据库│  │ 关系型DB  │  │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘  │
│                                                             │
│  ┌──────────────────────────┐  ┌──────────────────────┐   │
│  │      Workspace           │  │         OSS          │   │
│  │    本地文件系统           │  │      云对象存储       │   │
│  └──────────────────────────┘  └──────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 1. Redis（缓存与实时数据）

### 🎯 核心定位
**高性能缓存层 + 实时会话管理**

### 主要用途

#### 1.1 SSE 事件缓冲
```python
# 事件流缓冲（支持断线重连）
session:{session_id}:events          # 事件列表（List）
session:{session_id}:seq_counter     # Session 内事件序号
```

**特点**：
- 支持 SSE 断线重连
- 事件按序存储
- TTL 自动过期（60秒）

#### 1.2 Session 状态管理
```python
# Session 状态
session:{session_id}:status          # Hash 结构
  - status: running/completed/failed
  - conversation_id: 对话ID
  - user_id: 用户ID
  - last_event_id: 最后事件ID
  - progress: 进度
  - total_turns: 轮次数
```

**特点**：
- 实时查询 Session 状态
- 心跳检测（60秒 TTL）
- 自动清理过期 Session

#### 1.3 用户活跃会话
```python
user:{user_id}:sessions              # Set 结构
```

**特点**：
- 快速查询用户所有活跃 Session
- 自动移除完成的 Session

#### 1.4 Agent 运行时状态
```python
# Agent 实例池（内存 + Redis 备份）
agent_pool[session_id] = agent       # 内存
session:{session_id}:agent_state     # Redis 备份
```

### 性能优势
- ⚡ 毫秒级读写
- 🔥 支持高并发
- 🔄 自动过期清理
- 📡 Pub/Sub 实时通知

### 数据生命周期
```
创建 Session
    ↓
写入 Redis (status, events)
    ↓
Agent 执行（60秒内持续更新心跳）
    ↓
完成后 TTL=60s
    ↓
60秒后自动清理
```

---

## 2. PostgreSQL（关系型数据持久化）

### 🎯 核心定位
**结构化数据的持久存储**

### 数据模型

#### 2.1 用户表（users）
```sql
CREATE TABLE users (
    id TEXT PRIMARY KEY,
    username TEXT,
    email TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB DEFAULT '{}'
);
```

**用途**：
- 用户身份管理
- 用户配置和偏好

#### 2.2 对话表（conversations）
```sql
CREATE TABLE conversations (
    id TEXT PRIMARY KEY,              -- conv_xxx
    user_id TEXT NOT NULL,
    title TEXT DEFAULT '新对话',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB DEFAULT '{}',
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE INDEX idx_conversations_user_id ON conversations(user_id);
```

**用途**：
- 对话线程管理
- 对话历史查询
- 对话标题和摘要

#### 2.3 消息表（messages）
```sql
CREATE TABLE messages (
    id SERIAL PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    role TEXT NOT NULL,               -- user/assistant/system
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB DEFAULT '{}',      -- session_id, thinking, usage
    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
);

CREATE INDEX idx_messages_conversation_id ON messages(conversation_id);
CREATE INDEX idx_messages_created_at ON messages(created_at);
```

**metadata 字段示例**：
```json
{
  "session_id": "sess_xxx",
  "thinking": "用户在询问...",
  "model": "claude-sonnet-4-5",
  "usage": {
    "input_tokens": 100,
    "output_tokens": 50
  }
}
```

### 查询场景
- 📜 对话历史加载
- 🔍 对话列表分页
- 📊 用户统计分析
- 🕒 时间范围查询

---

## 3. Milvus（向量数据库）

### 🎯 核心定位
**多模态语义检索**

### 主要用途

#### 3.1 RAG 知识检索
```python
# Collection 结构
collection = "knowledge_base"
fields = [
    "id",              # 文档块 ID
    "user_id",         # 用户分区
    "content",         # 文本内容
    "vector",          # Embedding 向量（1536维）
    "metadata",        # 元数据（文件名、页码等）
    "chunk_type"       # text/image/table
]
```

**特点**：
- 支持文本、图片、表格多模态检索
- 用户数据隔离（partition by user_id）
- 相似度搜索（余弦相似度）

#### 3.2 对话历史语义检索
```python
# Collection: conversation_history
fields = [
    "message_id",
    "conversation_id",
    "content_vector",
    "timestamp",
    "metadata"
]
```

**用途**：
- 跨对话语义搜索
- 相关对话推荐
- 上下文补全

#### 3.3 工具使用记忆
```python
# Collection: tool_usage_memory
fields = [
    "tool_name",
    "usage_pattern_vector",  # 使用模式向量
    "success_rate",
    "context"
]
```

**用途**：
- 相似场景下工具推荐
- 工具使用模式学习

### 性能指标
- 🚀 百万级向量秒级检索
- 📈 支持水平扩展
- 🎯 ANN 近似最近邻算法（HNSW）

### 检索流程
```
用户查询
    ↓
Embedding (API)
    ↓
Milvus 向量检索 (Top-K)
    ↓
重排序（Rerank）
    ↓
返回最相关的结果
```

---

## 4. Neo4j（图数据库）

### 🎯 核心定位
**关系与知识图谱管理**

### 主要用途

#### 4.1 Tool Graph（工具依赖图）
```cypher
// 节点类型
(Tool {name, category, description})
(Capability {name})

// 关系类型
(Tool)-[:REQUIRES]->(Tool)           // 工具依赖
(Tool)-[:PROVIDES]->(Capability)     // 提供能力
(Tool)-[:CONFLICTS_WITH]->(Tool)     // 冲突关系
```

**用途**：
- 工具依赖分析
- 能力推理
- 工具组合推荐

**查询示例**：
```cypher
// 查找完成某任务需要的所有工具
MATCH path = (start:Tool)-[:REQUIRES*]->(end:Tool)
WHERE start.name = 'generate_ppt'
RETURN path
```

#### 4.2 用户画像图
```cypher
// 节点类型
(User {id, name})
(Interest {name, category})
(Skill {name, level})
(Preference {type, value})

// 关系类型
(User)-[:INTERESTED_IN {weight}]->(Interest)
(User)-[:HAS_SKILL {proficiency}]->(Skill)
(User)-[:PREFERS]->(Preference)
```

**用途**：
- 个性化推荐
- 用户行为分析
- 偏好学习

#### 4.3 知识图谱
```cypher
// 节点类型
(Concept {name, definition})
(Entity {name, type})
(Document {id, title})

// 关系类型
(Concept)-[:IS_A]->(Concept)          // 上下位关系
(Concept)-[:RELATED_TO]->(Concept)    // 关联关系
(Entity)-[:MENTIONED_IN]->(Document)  // 实体提及
```

**用途**：
- 知识推理
- 概念关联
- 实体链接

#### 4.4 对话记忆图
```cypher
// 节点类型
(Conversation {id, title})
(Topic {name})
(Entity {name, type})

// 关系类型
(Conversation)-[:DISCUSSES]->(Topic)
(Conversation)-[:MENTIONS]->(Entity)
(Conversation)-[:FOLLOWS]->(Conversation)  // 对话延续
```

**用途**：
- 跨对话上下文
- 主题追踪
- 记忆关联

### 查询优势
- 🔗 多跳关系查询
- 🌐 复杂路径分析
- 💡 知识推理
- 📊 图算法（PageRank、社区发现）

### 典型场景
```cypher
// 场景1：推荐相关工具
MATCH (t1:Tool {name: 'web_search'})-[:PROVIDES]->(c:Capability)<-[:PROVIDES]-(t2:Tool)
WHERE t1 <> t2
RETURN t2.name, count(c) as common_capabilities
ORDER BY common_capabilities DESC

// 场景2：查找用户最感兴趣的领域
MATCH (u:User {id: $user_id})-[r:INTERESTED_IN]->(i:Interest)
RETURN i.name, i.category, r.weight
ORDER BY r.weight DESC
LIMIT 5
```

---

## 5. Workspace（本地文件系统）

### 🎯 核心定位
**Agent 工作目录与文件操作**

### 目录结构
```
workspace/
├── sessions/                    # 会话工作目录
│   ├── sess_xxx/
│   │   ├── input/              # 输入文件
│   │   ├── output/             # 输出文件
│   │   ├── temp/               # 临时文件
│   │   └── logs/               # 执行日志
├── shared/                      # 共享资源
│   ├── templates/              # PPT/文档模板
│   ├── assets/                 # 静态资源
│   └── cache/                  # 本地缓存
├── database/                    # SQLite 数据库
│   └── zenflux.db
└── knowledge/                   # 知识库文件
    └── documents/
```

### 主要用途

#### 5.1 文件工具操作
```python
# 文件读写
FileReadTool.execute()          # 读取文件
FileWriteTool.execute()         # 写入文件
FileEditTool.execute()          # 编辑文件

# 支持的操作
- 文本文件读写
- 代码文件编辑
- 配置文件修改
- 日志文件追加
```

#### 5.2 代码执行环境
```python
# Bash 工具执行目录
working_dir = f"workspace/sessions/{session_id}"

# Python 代码执行
CodeExecutionTool.execute(
    code=code,
    working_dir=working_dir
)
```

#### 5.3 临时文件管理
```python
# 生成文件（PPT、Excel、图片等）
output_file = f"workspace/sessions/{session_id}/output/presentation.pptx"

# 自动清理
# - Session 完成后 24 小时清理
# - 临时文件立即清理
```

#### 5.4 模板资源
```python
# PPT 模板
template_path = "workspace/shared/templates/business.pptx"

# 图片资源
asset_path = "workspace/shared/assets/logo.png"
```

### 文件生命周期
```
Session 开始
    ↓
创建 workspace/sessions/{session_id}
    ↓
Agent 操作文件（读/写/编辑）
    ↓
生成输出文件
    ↓
上传到 OSS（获取访问 URL）
    ↓
Session 结束后 24 小时清理本地文件
```

### 安全机制
- 🔒 沙箱隔离（每个 Session 独立目录）
- 🚫 路径遍历防护
- 📏 文件大小限制
- 🗑️ 自动清理机制

---

## 6. OSS（对象存储服务）

### 🎯 核心定位
**文件持久化与 CDN 分发**

### 存储结构
```
bucket: zenflux-agent
├── uploads/                     # 用户上传文件
│   └── {user_id}/
│       └── {date}/
│           └── {filename}
├── outputs/                     # Agent 生成文件
│   └── {session_id}/
│       ├── presentations/      # PPT 文件
│       ├── reports/            # 报告文件
│       ├── images/             # 生成的图片
│       └── exports/            # 导出文件
├── knowledge/                   # 知识库文档
│   └── {user_id}/
│       └── {document_id}/
│           └── {filename}
└── public/                      # 公共资源
    ├── templates/
    └── assets/
```

### 主要用途

#### 6.1 用户文件上传
```python
# 上传流程
用户上传文件
    ↓
临时保存到 workspace
    ↓
上传到 OSS (uploads/{user_id}/{date}/{filename})
    ↓
生成访问 URL
    ↓
保存 URL 到数据库
    ↓
删除临时文件
```

**特点**：
- 支持断点续传
- 自动生成缩略图（图片）
- CDN 加速访问

#### 6.2 Agent 生成文件
```python
# 典型场景：生成 PPT
Agent 调用 PPT 工具
    ↓
生成 workspace/sessions/{session_id}/output/demo.pptx
    ↓
上传到 OSS (outputs/{session_id}/presentations/demo.pptx)
    ↓
获取 CDN URL
    ↓
通过事件返回给前端
```

**URL 示例**：
```
https://cdn.zenflux.com/outputs/sess_xxx/presentations/demo.pptx
```

#### 6.3 知识库文档存储
```python
# Ragie 处理后的文档
原始文档 → OSS (knowledge/{user_id}/{doc_id}/original.pdf)
处理后文档 → OSS (knowledge/{user_id}/{doc_id}/processed/)
```

#### 6.4 静态资源 CDN
```python
# 公共模板和资源
templates → OSS (public/templates/)
assets → OSS (public/assets/)
```

### 访问控制

#### 公开访问
```python
# 生成的文件（有时效）
url = generate_presigned_url(
    key=f"outputs/{session_id}/demo.pptx",
    expires_in=3600  # 1小时有效
)
```

#### 私有访问
```python
# 用户私有文件
url = generate_presigned_url(
    key=f"uploads/{user_id}/document.pdf",
    expires_in=86400  # 24小时有效
)
```

### 性能优化
- 🌍 CDN 全球加速
- 🗜️ 自动压缩（图片、视频）
- 📦 分片上传（大文件）
- 🔄 版本控制

---

## 数据流转图

### 完整的消息处理流程

```
┌────────────────────────────────────────────────────────────┐
│ 1. 用户发送消息                                              │
└────────────────┬───────────────────────────────────────────┘
                 │
                 ▼
┌────────────────────────────────────────────────────────────┐
│ 2. PostgreSQL: 保存用户消息                                 │
│    - conversations 表                                       │
│    - messages 表 (role=user)                                │
└────────────────┬───────────────────────────────────────────┘
                 │
                 ▼
┌────────────────────────────────────────────────────────────┐
│ 3. Redis: 创建 Session                                      │
│    - session:{id}:status                                    │
│    - session:{id}:events (空)                               │
└────────────────┬───────────────────────────────────────────┘
                 │
                 ▼
┌────────────────────────────────────────────────────────────┐
│ 4. Milvus: 检索相关知识                                      │
│    - 查询 knowledge_base collection                         │
│    - 查询 conversation_history collection                   │
└────────────────┬───────────────────────────────────────────┘
                 │
                 ▼
┌────────────────────────────────────────────────────────────┐
│ 5. Neo4j: 工具选择                                           │
│    - 查询 Tool Graph                                        │
│    - 查询用户偏好                                            │
└────────────────┬───────────────────────────────────────────┘
                 │
                 ▼
┌────────────────────────────────────────────────────────────┐
│ 6. Agent 执行                                                │
│    ├─ Workspace: 文件操作                                   │
│    ├─ Redis: 实时写入事件                                    │
│    └─ OSS: 上传生成的文件                                    │
└────────────────┬───────────────────────────────────────────┘
                 │
                 ▼
┌────────────────────────────────────────────────────────────┐
│ 7. 监听 complete 事件                                        │
│    └─ PostgreSQL: 保存 Assistant 消息                       │
│       - messages 表 (role=assistant)                        │
│       - metadata 包含 thinking、usage                       │
└────────────────┬───────────────────────────────────────────┘
                 │
                 ▼
┌────────────────────────────────────────────────────────────┐
│ 8. 后处理                                                    │
│    ├─ Milvus: 更新对话向量                                  │
│    ├─ Neo4j: 更新知识图谱                                   │
│    └─ Redis: 标记 Session 完成（TTL=60s）                   │
└────────────────────────────────────────────────────────────┘
```

---

## 存储选型对比

| 存储类型 | 数据类型 | 访问模式 | 持久化 | 性能 | 使用场景 |
|---------|---------|---------|--------|------|---------|
| **Redis** | KV/List/Set | 读写频繁 | ❌ 临时 | ⚡ 毫秒级 | Session、缓存、实时数据 |
| **PostgreSQL** | 结构化 | CRUD | ✅ 持久 | 📊 百ms级 | 对话、消息、用户数据 |
| **Milvus** | 向量 | 相似度搜索 | ✅ 持久 | 🚀 秒级 | RAG、语义检索 |
| **Neo4j** | 图 | 关系查询 | ✅ 持久 | 🔗 毫秒级 | 知识图谱、工具依赖 |
| **Workspace** | 文件 | 读写编辑 | ⏱️ 24小时 | 💾 微秒级 | 临时文件、代码执行 |
| **OSS** | 对象 | HTTP访问 | ✅ 持久 | 🌍 CDN加速 | 文件存储、CDN分发 |

---

## 数据一致性策略

### 最终一致性
```
Redis (实时) → PostgreSQL (异步写入)
```

**场景**：Session 状态
- Redis 实时更新
- PostgreSQL 延迟写入（或不写入）

### 强一致性
```
PostgreSQL → Milvus/Neo4j (事务后更新)
```

**场景**：对话消息
- 先写 PostgreSQL（持久化）
- 再更新 Milvus 向量
- 最后更新 Neo4j 图谱

### 补偿机制
```
OSS 上传失败 → 保留 Workspace 文件 → 后台重试
```

---

## 备份与恢复

### PostgreSQL
- 📅 每日全量备份
- 📝 WAL 日志归档
- 🔄 主从复制

### Milvus
- 📦 Collection 快照
- 💾 向量数据备份
- 🔄 增量同步

### Neo4j
- 📊 图数据导出
- 🔐 事务日志备份
- 🔄 集群复制

### OSS
- ✅ 自动多副本
- 📂 版本控制
- 🌍 跨区域复制

---

## 监控指标

### Redis
- 内存使用率
- 命中率
- 连接数
- 慢查询

### PostgreSQL
- 连接池状态
- 查询性能
- 表大小
- 索引效率

### Milvus
- 向量检索延迟
- 相似度分数分布
- Collection 大小

### Neo4j
- 图查询性能
- 节点/关系数量
- 缓存命中率

### Workspace
- 磁盘使用率
- 文件数量
- 清理任务状态

### OSS
- 存储用量
- 带宽使用
- 请求QPS
- CDN 命中率

---

## 未来扩展

### 短期（1-3个月）
- [ ] Redis Cluster（高可用）
- [ ] PostgreSQL 读写分离
- [ ] Milvus 分片优化
- [ ] Workspace 自动清理优化

### 中期（3-6个月）
- [ ] Neo4j 因果集群
- [ ] OSS 智能分层存储
- [ ] 跨存储查询优化
- [ ] 数据湖集成

### 长期（6-12个月）
- [ ] 实时数据仓库
- [ ] 向量索引优化
- [ ] 知识图谱推理引擎
- [ ] 多租户数据隔离

---

## 总结

六层存储架构各司其职：

1. **Redis** - ⚡ 实时缓存，Session 管理
2. **PostgreSQL** - 📊 持久化存储，结构化数据
3. **Milvus** - 🔍 语义检索，多模态向量
4. **Neo4j** - 🔗 关系推理，知识图谱
5. **Workspace** - 💾 临时文件，Agent 工作目录
6. **OSS** - 🌍 持久存储，CDN 分发

这种多层架构确保了：
- ✅ **性能**：热数据在 Redis，冷数据在 PostgreSQL
- ✅ **灵活性**：根据数据特点选择最优存储
- ✅ **可扩展性**：每层独立扩展
- ✅ **可靠性**：多副本、备份机制
- ✅ **成本优化**：按需使用，自动清理

🎉 **设计理念：Right Data, Right Place, Right Time**
