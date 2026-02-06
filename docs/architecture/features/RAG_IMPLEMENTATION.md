# ZenFlux Agent RAG 实现文档

## 目录

1. [架构概览](#架构概览)
2. [核心组件](#核心组件)
3. [数据流程](#数据流程)
4. [技术实现](#技术实现)
5. [API 接口](#api-接口)
6. [使用指南](#使用指南)
7. [配置说明](#配置说明)
8. [最佳实践](#最佳实践)

---

## 架构概览

### 设计理念

ZenFlux Agent 的 RAG（Retrieval-Augmented Generation）系统基于 **Ragie API**，提供企业级的知识库管理和语义检索能力。

**核心特性**：

- 🔍 **语义检索**：基于向量相似度的智能检索
- 📚 **多格式支持**：PDF/DOCX/PPTX/MD/TXT/PNG/JPG/MP3/MP4 等
- 🔒 **多租户隔离**：每个用户有独立的知识空间
- ☁️ **双存储架构**：S3 存储原始文件 + Ragie 向量索引
- 🚀 **异步处理**：文档索引异步进行，不阻塞响应
- 📊 **引用追溯**：自动生成引用标记，保证信息可追溯

### 架构分层

```
┌─────────────────────────────────────────────────────────────────┐
│                        API 层 (routers/)                         │
│  - 文档上传、删除、查询                                          │
│  - 知识库检索                                                    │
│  - 统计信息                                                      │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                     Service 层 (services/)                       │
│  - KnowledgeService: 业务逻辑封装                               │
│  - 调用 RagieClient 和本地存储                                  │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                    存储层 (infra/utils)                          │
│  ┌─────────────┐  ┌─────────────┐  ┌──────────────┐           │
│  │ RagieClient │  │ S3Uploader  │  │KnowledgeStore│           │
│  │ (向量检索)  │  │ (文件存储)  │  │  (元数据)    │           │
│  └─────────────┘  └─────────────┘  └──────────────┘           │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                   上下文注入 (core/context)                      │
│  - KnowledgeInjector: 自动检索并注入知识上下文                  │
│  - KnowledgeSearchTool: 作为 Agent 工具主动检索                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 核心组件

### 1. RagieClient (`utils/ragie_client.py`)

**职责**：与 Ragie API 交互的客户端封装

**核心方法**：

```python
class RagieClient:
    # 文档创建
    async def create_document_from_file(file_path, partition, metadata, mode) -> Dict
    async def create_document_from_url(url, partition, metadata, mode) -> Dict
    async def create_document_from_raw(content, name, partition, metadata) -> Dict
    
    # 文档管理
    async def get_document(document_id) -> Dict
    async def list_documents(partition, limit, cursor, filter) -> Dict
    async def delete_document(document_id) -> Dict
    async def patch_document_metadata(document_id, metadata) -> Dict
    
    # 文档内容
    async def get_document_content(document_id) -> Dict
    async def get_document_chunks(document_id, limit, cursor) -> Dict
    async def get_document_source(document_id) -> bytes
    
    # 检索
    async def retrieve(query, partition, top_k, filters) -> Dict
```

**关键特性**：

- 异步 HTTP 调用（基于 `aiohttp`）
- 自动错误处理和重试
- 支持分页查询
- Metadata 过滤（用于多租户隔离）

**配置**：

```python
# 环境变量
RAGIE_API_KEY=xxx

# 初始化
client = RagieClient(api_key=os.getenv("RAGIE_API_KEY"))
```

---

### 2. KnowledgeService (`services/knowledge_service.py`)

**职责**：知识库业务逻辑封装，连接 API 层和存储层

**核心方法**：

#### 文档上传

```python
async def upload_document_from_file(
    file_path: str,
    user_id: str,
    filename: str,
    metadata: Optional[Dict] = None,
    mode: str = "hi_res"
) -> Dict[str, Any]
```

**处理流程**：
1. 确保用户记录存在
2. 构建 metadata（包含 `user_id`、`filename`、`uploaded_at`）
3. 调用 Ragie API 创建文档（使用 default partition）
4. 存储到本地 `KnowledgeStore`（JSON 文件）

**返回**：

```python
{
    "document_id": "doc_xxx",
    "status": "pending",  # 文档状态
    "filename": "xxx.pdf",
    "user_id": "user_123",
    "partition_id": "default"
}
```

#### 文档检索

```python
async def retrieve_from_knowledge_base(
    user_id: str,
    query: str,
    top_k: int = 5,
    filters: Optional[Dict] = None
) -> Dict[str, Any]
```

**处理流程**：
1. 确认用户存在
2. 构建 metadata 过滤器（`user_id: {"$eq": "xxx"}`）
3. 调用 Ragie `retrieve` API
4. 转换为 `ChunkInfo` 模型

**返回**：

```python
{
    "query": "如何使用 Python?",
    "user_id": "user_123",
    "partition_id": "default",
    "total": 5,
    "chunks": [
        {
            "text": "Python 是...",
            "score": 0.92,
            "document_id": "doc_xxx",
            "document_name": "Python教程.pdf",
            "chunk_id": "chunk_xxx",
            "metadata": {...}
        }
    ]
}
```

#### 文档管理

```python
# 列出用户文档
async def list_user_documents(user_id, status_filter, limit, offset, refresh)

# 获取文档状态（支持刷新）
async def get_document_status(user_id, document_id, refresh)

# 更新元数据
async def update_document_metadata(user_id, document_id, metadata)

# 删除文档（Ragie + S3 + 本地缓存）
async def delete_document(user_id, document_id)

# 获取文档内容/分块
async def get_document_content(user_id, document_id)
async def get_document_chunks(user_id, document_id, limit)

# S3 预签名 URL（用于下载）
async def get_s3_download_url(user_id, document_id, expiration=3600)
```

---

### 3. KnowledgeStore (`utils/knowledge_store.py`)

**职责**：本地元数据存储（JSON 文件），用于缓存和快速查询

**存储结构**：

```json
{
  "users": {
    "user_123": {
      "user_id": "user_123",
      "partition_id": "partition_user_123",
      "created_at": "2026-01-01T00:00:00",
      "last_seen_at": "2026-01-02T00:00:00",
      "documents": [
        {
          "document_id": "doc_xxx",
          "filename": "Python教程.pdf",
          "status": "ready",
          "metadata": {
            "user_id": "user_123",
            "s3_key": "knowledge/user_123/xxx.pdf",
            "file_size": 1024000
          },
          "created_at": "2026-01-01T00:00:00",
          "updated_at": "2026-01-01T00:00:00"
        }
      ]
    }
  },
  "conversations": {...}
}
```

**核心方法**：

```python
# 用户管理
def get_or_create_user(user_id) -> Dict
def get_user(user_id) -> Optional[Dict]

# 文档管理
def add_document(user_id, document_id, filename, status, metadata)
def get_user_documents(user_id) -> List[Dict]
def get_document(user_id, document_id) -> Optional[Dict]
def update_document_status(user_id, document_id, status)
def update_document_metadata(user_id, document_id, metadata)
def delete_document(user_id, document_id)
```

**存储位置**：

- 开发环境：`/tmp/zenflux_knowledge/knowledge_store.json`
- 生产环境：可配置 `data_dir` 参数

---

### 4. KnowledgeSearchTool (`tools/knowledge_search.py`)

**职责**：作为 Agent 的工具，供 LLM 主动调用检索知识库

**工具定义**：

```yaml
# config/capabilities.yaml
- id: knowledge_search
  name: knowledge_search
  category: knowledge_base
  description: "从用户的个人知识库检索相关内容（RAG）"
  mcp_server: null
  tool_config:
    input_schema:
      type: object
      properties:
        query:
          type: string
          description: "检索查询文本"
        top_k:
          type: integer
          description: "返回结果数量"
          default: 5
        metadata_filter:
          type: object
          description: "元数据过滤条件"
```

**执行流程**：

1. 从 `ToolContext` 获取 `user_id`
2. 检查用户是否有文档
3. 构建 metadata 过滤器（`user_id: {"$eq": "xxx"}`）
4. 调用 Ragie `retrieve` API
5. 质量过滤（`score >= 0.1`）
6. 格式化为带引用标记的结构化结果

**返回格式**：

```python
{
    "success": True,
    "message": "✅ 找到 3 个相关片段（已按相关性排序）",
    "total": 3,
    "chunks": [
        {
            "citation_id": 1,  # 引用编号 [1]
            "text": "Python 是...",
            "score": 0.92,
            "document_id": "doc_xxx",
            "document_name": "Python教程.pdf",
            "metadata": {...}
        }
    ],
    "rag_context": "## 📚 检索到的相关内容\n\n...",  # 供 LLM 使用的格式化上下文
    "summary": "[1] Python教程.pdf\nPython 是...",
    "instructions": "📌 使用说明：..."
}
```

**RAG 上下文格式**：

```markdown
## 📚 检索到的相关内容

**用户查询**：「如何使用 Python 进行数据分析?」

---

### [1] 来源：Python数据分析教程.pdf
**相关性评分**：0.92

**内容**：
Python 是数据分析的首选语言...

---

### [2] 来源：数据分析实战.md
**相关性评分**：0.87

**内容**：
使用 pandas 库可以高效处理数据...

---

## 📋 回答要求

1. ✅ **必须基于以上检索内容回答**，禁止编造
2. ✅ **包含引用标记**：如「根据文档[1]，Python 是...」
3. ✅ **综合多个来源**：如果多个文档都提到相关内容，综合引用
4. ✅ **明确来源**：让用户知道信息来自哪份文档
5. ❌ **不要编造**：如果检索结果不足，明确告知「检索到的内容中未提及...」
```

---

### 5. KnowledgeInjector (`core/context/injectors/phase2/knowledge.py`)

**职责**：在构建提示词时自动注入知识库上下文

**配置**：

- **Phase**: Phase 2 - User Context Message
- **Priority**: 80（在用户记忆之后）
- **Cache Strategy**: DYNAMIC（每次检索结果可能不同，不缓存）

**注入时机**：

```python
async def should_inject(context: InjectionContext) -> bool:
    # 1. 有预加载的知识结果
    if context.get("knowledge_results"):
        return True
    
    # 2. 有用户查询
    return bool(context.user_query)
```

**注入格式**：

```xml
<knowledge_base>
## 相关文档

**文档1: API 设计规范** (相关度: 0.92)
RESTful API 应该使用标准 HTTP 方法...

**文档2: 数据库设计指南** (相关度: 0.87)
数据库表设计应该遵循第三范式...
</knowledge_base>
```

---

## 数据流程

### 文档上传流程

```
用户上传文件
    ↓
API 层 (routers/knowledge.py)
    ├─ 验证文件格式和大小
    ├─ 保存到临时文件
    ├─ 上传到 S3（可选，增强功能）
    │   └─ 生成 s3_key, s3_url
    └─ 调用 KnowledgeService
          ↓
Service 层 (services/knowledge_service.py)
    ├─ 确保用户存在
    ├─ 构建 metadata（user_id, filename, s3_key）
    ├─ 调用 RagieClient.create_document_from_file()
    │   └─ Ragie API 处理文档（异步）
    │       ├─ pending → partitioning → partitioned
    │       ├─ refined → chunked → indexed
    │       └─ summary_indexed → keyword_indexed → ready
    └─ 存储到 KnowledgeStore（本地缓存）
          ↓
返回 DocumentUploadResponse
    - document_id
    - status: "pending"
    - message: "文档正在处理中..."
```

### 文档检索流程

```
用户发起查询
    ↓
Agent 决策：需要检索知识库
    ├─ 方式1: 自动注入（KnowledgeInjector）
    │   └─ 在构建提示词时自动调用
    └─ 方式2: 主动调用（KnowledgeSearchTool）
          └─ LLM 判断需要检索，调用工具
                ↓
Service 层 (KnowledgeService.retrieve_from_knowledge_base)
    ├─ 确认用户存在
    ├─ 构建 metadata 过滤器（user_id: {"$eq": "xxx"}）
    └─ 调用 RagieClient.retrieve()
          ↓
Ragie API 处理
    ├─ 向量检索（基于语义相似度）
    ├─ 应用 metadata 过滤器
    └─ 返回 scored_chunks
          ↓
质量控制
    ├─ 过滤低相关性结果（score < 0.1）
    └─ 格式化为带引用标记的结果
          ↓
返回给 Agent/LLM
    ├─ 结构化 JSON（API 响应）
    └─ RAG 上下文（Markdown 格式）
```

### 多租户隔离机制

**设计说明**：
- Ragie 免费账户限制：无法创建自定义 Partition
- 解决方案：使用 metadata 过滤实现多租户隔离

**实现方式**：

```python
# 1. 上传文档时，在 metadata 中标记 user_id
doc_metadata = {
    "user_id": user_id,  # 关键：用于过滤
    "filename": "xxx.pdf",
    "uploaded_at": "2026-01-01T00:00:00"
}

await ragie_client.create_document_from_file(
    file_path=file_path,
    partition=None,  # 使用 default partition
    metadata=doc_metadata
)

# 2. 检索时，通过 metadata 过滤只返回该用户的文档
filters = {
    "user_id": {"$eq": user_id}  # Ragie metadata 过滤语法
}

await ragie_client.retrieve(
    query=query,
    partition=None,  # 使用 default partition
    top_k=top_k,
    filters=filters
)
```

**优势**：
- ✅ 不依赖 Partition，适用于免费账户
- ✅ 灵活的过滤条件（支持多维度过滤）
- ✅ 代码统一，易于维护

---

## 技术实现

### 文档处理状态机

```
pending           # 初始状态，文档已创建
    ↓
partitioning      # 正在分段
    ↓
partitioned       # 分段完成
    ↓
refined           # 内容精炼
    ↓
chunked           # 分块完成
    ↓
indexed           # 向量索引完成
    ↓
summary_indexed   # 摘要索引完成
    ↓
keyword_indexed   # 关键词索引完成
    ↓
ready             # 就绪，可检索
```

**失败状态**：`failed`（处理失败，无法检索）

**状态查询**：

```python
# 列出文档时，可选择刷新状态
result = await knowledge_service.list_user_documents(
    user_id=user_id,
    refresh=True  # 从 Ragie 刷新处理中文档的状态
)

# 检查是否有处理中的文档
if result["has_processing"]:
    print("部分文档仍在处理中...")
```

### 向量检索评分

**Ragie 评分范围**：通常在 `0.1 - 0.3` 之间（不是 0-1）

**质量控制**：

```python
# 1. 过滤低相关性结果
min_score = 0.1
filtered_chunks = [
    chunk for chunk in scored_chunks 
    if chunk.get("score", 0) >= min_score
]

# 2. 按评分排序（Ragie 已排序，无需再排）
# chunks 已按 score 降序排列

# 3. 限制返回数量
top_chunks = filtered_chunks[:top_k]
```

### S3 文件存储

**设计目标**：增强功能，支持原始文件下载

**存储流程**：

1. 上传文档时，同时上传到 S3
2. S3 返回 `s3_key`（永久路径）和 `s3_url`
3. 将 `s3_key` 存储在 metadata 中

**下载流程**：

1. 从 metadata 获取 `s3_key`
2. 生成预签名 URL（临时，有效期 1 小时）
3. 返回给前端，支持直接下载

```python
# 生成预签名 URL
presigned_url = await knowledge_service.get_s3_download_url(
    user_id=user_id,
    document_id=document_id,
    expiration=3600  # 1小时有效期
)

# 前端可直接访问
# https://xxx.s3.amazonaws.com/xxx?X-Amz-Signature=xxx
```

---

## API 接口

### 1. 文档上传

**端点**：`POST /api/v1/knowledge/upload`

**请求**（multipart/form-data）：

```
files: List[UploadFile]  # 必填，支持批量上传（最多 20 个）
user_id: str             # 必填
metadata: str            # 可选，JSON 字符串
mode: str                # 可选，"fast" | "hi_res"，默认 "hi_res"
```

**响应**：

```json
{
  "code": 200,
  "message": "文档上传成功",
  "data": {
    "document_id": "doc_xxx",
    "status": "pending",
    "filename": "Python教程.pdf",
    "user_id": "user_123",
    "partition_id": "default",
    "message": "文档正在处理中，状态为 'ready' 后可检索"
  }
}
```

**批量上传响应**：

```json
{
  "code": 200,
  "message": "批量上传完成",
  "data": {
    "total": 10,
    "succeeded": 8,
    "failed": 2,
    "results": [
      {
        "filename": "doc1.pdf",
        "status": "success",
        "document_id": "doc_xxx",
        "message": "上传成功"
      },
      {
        "filename": "doc2.pdf",
        "status": "failed",
        "error": "文件格式不支持"
      }
    ]
  }
}
```

### 2. 从 URL 上传

**端点**：`POST /api/v1/knowledge/upload/url`

**请求体**：

```json
{
  "url": "https://example.com/doc.pdf",
  "user_id": "user_123",
  "name": "示例文档",
  "metadata": {"category": "tutorial"},
  "mode": "hi_res"
}
```

### 3. 从文本创建文档

**端点**：`POST /api/v1/knowledge/upload/text`

**请求体**：

```json
{
  "text": "文档内容...",
  "name": "API 设计规范",
  "user_id": "user_123",
  "metadata": {"category": "guide"}
}
```

### 4. 列出文档

**端点**：`GET /api/v1/knowledge/documents`

**查询参数**：

```
user_id: str               # 必填
status: str                # 可选，过滤状态（ready/pending/failed）
limit: int = 100           # 可选，每页数量
offset: int = 0            # 可选，偏移量
refresh: bool = false      # 可选，是否从 Ragie 刷新状态
```

**响应**：

```json
{
  "code": 200,
  "message": "查询成功",
  "data": {
    "user_id": "user_123",
    "total": 10,
    "documents": [
      {
        "document_id": "doc_xxx",
        "filename": "Python教程.pdf",
        "status": "ready",
        "user_id": "user_123",
        "partition_id": "default",
        "metadata": {
          "s3_key": "knowledge/user_123/xxx.pdf",
          "s3_presigned_url": "https://xxx.s3.amazonaws.com/..."
        },
        "created_at": "2026-01-01T00:00:00",
        "updated_at": "2026-01-01T00:00:00"
      }
    ],
    "has_processing": false
  }
}
```

### 5. 检索知识库

**端点**：`POST /api/v1/knowledge/retrieve`

**请求体**：

```json
{
  "user_id": "user_123",
  "query": "如何使用 Python 进行数据分析?",
  "top_k": 5,
  "metadata_filter": {"category": "tutorial"}
}
```

**响应**：

```json
{
  "code": 200,
  "message": "检索成功",
  "data": {
    "query": "如何使用 Python 进行数据分析?",
    "user_id": "user_123",
    "partition_id": "default",
    "total": 3,
    "chunks": [
      {
        "text": "Python 是数据分析的首选语言...",
        "score": 0.92,
        "document_id": "doc_xxx",
        "document_name": "Python教程.pdf",
        "chunk_id": "chunk_xxx",
        "metadata": {"category": "tutorial"}
      }
    ]
  }
}
```

### 6. 删除文档

**端点**：`DELETE /api/v1/knowledge/documents/{document_id}`

**查询参数**：

```
user_id: str  # 必填
```

**响应**：

```json
{
  "code": 200,
  "message": "文档删除成功",
  "data": {
    "document_id": "doc_xxx",
    "deleted_from": ["ragie", "s3", "local_cache"]
  }
}
```

### 7. 获取文档统计

**端点**：`GET /api/v1/knowledge/stats`

**查询参数**：

```
user_id: str  # 必填
```

**响应**：

```json
{
  "code": 200,
  "message": "查询成功",
  "data": {
    "user_id": "user_123",
    "total_documents": 10,
    "ready_documents": 8,
    "processing_documents": 1,
    "failed_documents": 1,
    "total_size": 10240000
  }
}
```

---

## 使用指南

### 快速开始

#### 1. 配置环境变量

```bash
# .env
RAGIE_API_KEY=your_ragie_api_key_here
AWS_ACCESS_KEY_ID=xxx  # S3 配置（可选）
AWS_SECRET_ACCESS_KEY=xxx
AWS_S3_BUCKET=your-bucket-name
```

#### 2. 上传文档

```python
import httpx

# 上传单个文件
async with httpx.AsyncClient() as client:
    with open("document.pdf", "rb") as f:
        response = await client.post(
            "http://localhost:8000/api/v1/knowledge/upload",
            files={"files": ("document.pdf", f, "application/pdf")},
            data={
                "user_id": "user_123",
                "metadata": json.dumps({"category": "tutorial"}),
                "mode": "hi_res"
            }
        )
    
    result = response.json()
    document_id = result["data"]["document_id"]
    print(f"文档ID: {document_id}")
```

#### 3. 等待文档处理完成

```python
import asyncio

async def wait_for_ready(user_id: str, document_id: str):
    async with httpx.AsyncClient() as client:
        while True:
            response = await client.get(
                f"http://localhost:8000/api/v1/knowledge/documents/{document_id}/status",
                params={"user_id": user_id, "refresh": True}
            )
            
            status = response.json()["data"]["status"]
            print(f"文档状态: {status}")
            
            if status == "ready":
                print("✅ 文档就绪，可以检索了")
                break
            elif status == "failed":
                print("❌ 文档处理失败")
                break
            
            await asyncio.sleep(5)  # 每 5 秒检查一次

await wait_for_ready("user_123", document_id)
```

#### 4. 检索知识库

```python
async with httpx.AsyncClient() as client:
    response = await client.post(
        "http://localhost:8000/api/v1/knowledge/retrieve",
        json={
            "user_id": "user_123",
            "query": "如何使用 Python 进行数据分析?",
            "top_k": 5
        }
    )
    
    result = response.json()
    for chunk in result["data"]["chunks"]:
        print(f"[{chunk['score']:.2f}] {chunk['document_name']}")
        print(f"  {chunk['text'][:100]}...")
```

### Agent 集成

#### 方式1：自动注入（推荐）

```python
from core.context.injectors.phase2.knowledge import KnowledgeInjector

# 在构建提示词时自动注入知识库上下文
injector = KnowledgeInjector(max_results=5, max_chars=2000)

# InjectionOrchestrator 会自动调用
```

#### 方式2：主动调用工具

```python
# Agent 配置中启用知识库检索能力
agent_config = {
    "capabilities": [
        "knowledge_base"  # 启用知识库检索
    ]
}

# LLM 判断需要检索时，会自动调用 knowledge_search 工具
```

**LLM 调用示例**：

```json
{
  "tool_calls": [
    {
      "name": "knowledge_search",
      "params": {
        "query": "Python 数据分析教程",
        "top_k": 5
      }
    }
  ]
}
```

**工具返回**：

```python
{
    "success": True,
    "message": "✅ 找到 3 个相关片段",
    "total": 3,
    "chunks": [...],
    "rag_context": "## 📚 检索到的相关内容\n\n...",
    "instructions": "📌 使用说明：..."
}
```

---

## 配置说明

### 1. Capability 配置 (`config/capabilities.yaml`)

```yaml
# 能力类别定义
capability_categories:
  - id: knowledge_base
    category: business
    name: "知识库检索（RAG）"
    description: "从用户的个人知识库检索相关内容"
    tools:
      - knowledge_search
    mcp_server: null

# 工具定义
tools:
  - id: knowledge_search
    name: knowledge_search
    category: knowledge_base
    description: "从用户的个人知识库检索相关内容（RAG）"
    tool_config:
      input_schema:
        type: object
        properties:
          query:
            type: string
            description: "检索查询文本"
          top_k:
            type: integer
            description: "返回结果数量"
            default: 5
          metadata_filter:
            type: object
            description: "元数据过滤条件"
        required: ["query"]
```

### 2. Task Type 映射

```yaml
task_type_mappings:
  information_query:
    - knowledge_base  # 信息查询任务默认启用知识库检索
```

### 3. Context Injector 配置

```python
# core/context/injectors/phase2/knowledge.py
class KnowledgeInjector(BaseInjector):
    def __init__(self, max_results: int = 5, max_chars: int = 2000):
        self.max_results = max_results  # 最大检索结果数
        self.max_chars = max_chars      # 每个结果最大字符数
    
    @property
    def phase(self) -> InjectionPhase:
        return InjectionPhase.USER_CONTEXT  # Phase 2
    
    @property
    def priority(self) -> int:
        return 80  # 在用户记忆之后
```

---

## 最佳实践

### 1. 文档管理

#### ✅ 推荐做法

```python
# 1. 上传时添加结构化 metadata
metadata = {
    "category": "tutorial",       # 文档分类
    "language": "zh-CN",          # 语言
    "tags": ["python", "data"],   # 标签
    "author": "张三",              # 作者
    "version": "1.0"              # 版本
}

# 2. 使用 hi_res 模式获得更好的解析质量（耗时更长）
mode = "hi_res"  # vs "fast"

# 3. 批量上传使用并发控制
max_concurrent = 5  # 限制并发数，避免 API 限流

# 4. 定期清理过期文档
await knowledge_service.delete_document(user_id, old_document_id)
```

#### ❌ 避免的做法

```python
# ❌ 不要在 metadata 中存储敏感信息
metadata = {
    "password": "xxx",  # 禁止
    "api_key": "xxx"    # 禁止
}

# ❌ 不要上传过大的文件（建议 < 50MB）
file_size_mb = file_size / (1024 * 1024)
if file_size_mb > 50:
    return {"error": "文件过大，请分割后上传"}

# ❌ 不要频繁刷新文档状态（增加 API 调用成本）
# 推荐：仅在必要时刷新，或使用 webhook
```

### 2. 检索优化

#### ✅ 提升检索质量

```python
# 1. 使用精确的查询
query = "Python pandas DataFrame 数据清洗方法"  # ✅ 具体
# vs
query = "数据处理"  # ❌ 模糊

# 2. 合理设置 top_k
top_k = 5   # 一般情况
top_k = 10  # 复杂问题，需要更多上下文

# 3. 使用 metadata 过滤缩小范围
filters = {
    "category": {"$eq": "tutorial"},
    "language": {"$eq": "zh-CN"}
}

# 4. 检索后进行二次质量过滤
filtered_chunks = [
    chunk for chunk in chunks
    if chunk["score"] >= 0.15  # 提高阈值
]
```

#### ✅ 引用标记规范

```python
# LLM 生成回答时，必须包含引用标记
response = """
根据文档[1]《Python数据分析教程》，pandas 是最常用的数据分析库。
具体来说，DataFrame[2] 是 pandas 的核心数据结构...
"""

# 前端渲染时，可以将 [1] 转换为可点击链接
```

### 3. 多租户管理

#### ✅ 用户隔离

```python
# 1. 所有操作必须包含 user_id
user_id = context.user_id  # 从请求上下文获取

# 2. 上传时自动标记 user_id
doc_metadata = {
    "user_id": user_id,  # 关键：用于过滤
    **custom_metadata
}

# 3. 检索时自动过滤
filters = {
    "user_id": {"$eq": user_id}  # 只返回该用户的文档
}
```

#### ✅ 配额管理

```python
# 1. 限制每个用户的文档数量
user_docs = await knowledge_service.list_user_documents(user_id)
if len(user_docs["documents"]) >= MAX_DOCUMENTS_PER_USER:
    return {"error": f"文档数量已达上限（{MAX_DOCUMENTS_PER_USER}）"}

# 2. 限制文档大小
if file_size > MAX_FILE_SIZE:
    return {"error": f"文件过大（最大 {MAX_FILE_SIZE} MB）"}
```

### 4. 错误处理

#### ✅ 优雅降级

```python
try:
    # 尝试检索知识库
    result = await knowledge_service.retrieve_from_knowledge_base(
        user_id=user_id,
        query=query
    )
except Exception as e:
    logger.error(f"知识库检索失败: {e}", exc_info=True)
    
    # 降级：不使用知识库，直接用 LLM 回答
    result = None

# 继续处理（即使知识库不可用）
if result and result["total"] > 0:
    # 使用 RAG 结果
    context = result["rag_context"]
else:
    # 直接用 LLM 生成
    context = None
```

#### ✅ 友好的错误提示

```python
# 1. 文档不存在
raise DocumentNotFoundError(f"文档不存在: document_id={document_id}")

# 2. 用户不存在
raise UserNotFoundError(f"用户不存在: user_id={user_id}")

# 3. 处理失败
raise DocumentProcessingError(f"文档处理失败: {error_message}")

# 4. API 层转换为 HTTP 响应
@router.exception_handler(DocumentNotFoundError)
async def document_not_found_handler(request, exc):
    return JSONResponse(
        status_code=404,
        content={"code": 404, "message": str(exc)}
    )
```

### 5. 性能优化

#### ✅ 缓存策略

```python
# 1. 本地元数据缓存（KnowledgeStore）
# 避免频繁调用 Ragie API 查询文档列表

# 2. 检索结果不缓存（DYNAMIC）
# 因为每次查询可能不同

# 3. 状态查询：优先使用本地缓存
doc = await knowledge_service.get_document_status(
    user_id=user_id,
    document_id=document_id,
    refresh=False  # 使用本地缓存
)
```

#### ✅ 并发控制

```python
# 批量操作使用 Semaphore 限流
semaphore = asyncio.Semaphore(max_concurrent)

async def upload_one(file):
    async with semaphore:
        return await knowledge_service.upload_document_from_file(...)

tasks = [upload_one(file) for file in files]
results = await asyncio.gather(*tasks)
```

---

## 总结

ZenFlux Agent 的 RAG 实现基于以下核心设计：

1. **三层架构**：API 层（routers） → Service 层 → 存储层（Ragie + S3 + 本地缓存）
2. **多租户隔离**：通过 metadata 过滤实现用户隔离
3. **双存储架构**：Ragie 向量索引 + S3 原始文件
4. **两种注入方式**：自动注入（KnowledgeInjector） + 主动调用（KnowledgeSearchTool）
5. **引用追溯**：结构化引用标记，保证信息可追溯

**技术栈**：
- Ragie API：向量检索和文档处理
- AWS S3：原始文件存储
- JSON 文件：本地元数据缓存
- FastAPI：REST API
- aiohttp/httpx：异步 HTTP 客户端

**适用场景**：
- ✅ 企业知识库管理
- ✅ 个人文档助手
- ✅ 客服问答系统
- ✅ 技术文档检索
- ✅ 法律/医疗专业文档查询
