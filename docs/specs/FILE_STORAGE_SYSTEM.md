# 文件存储系统设计文档

版本: V1.0  
日期: 2024-12-30

---

## 📋 目录

1. [系统概述](#系统概述)
2. [架构设计](#架构设计)
3. [数据库设计](#数据库设计)
4. [配置说明](#配置说明)
5. [使用指南](#使用指南)
6. [API 接口](#api-接口)

---

## 系统概述

完整的文件上传、存储、管理系统，支持：
- ✅ AWS S3 云存储
- ✅ 文件元数据管理
- ✅ 多种文件分类
- ✅ 访问控制
- ✅ 预签名 URL
- ✅ 统计和查询

---

## 架构设计

### 分层架构

```
┌─────────────────────────────────────────────────────────────┐
│                        Router 层                              │
│  routers/knowledge.py - 文件上传接口                           │
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────┐
│                       Service 层                              │
│  services/knowledge_service.py - 业务逻辑                      │
└───────────────────────────┬─────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
┌───────▼──────┐  ┌─────────▼─────────┐  ┌────▼──────────┐
│ S3 Uploader  │  │  File Repository  │  │ Ragie Client  │
│              │  │                   │  │               │
│ - S3 上传    │  │ - 数据库 CRUD     │  │ - 知识库集成  │
│ - URL 生成   │  │ - 查询统计        │  │               │
└──────────────┘  └───────────────────┘  └───────────────┘
```

### 核心模块

#### 1. S3 Uploader (`utils/s3_uploader.py`)
- 文件上传到 AWS S3
- 生成预签名 URL
- 批量删除
- 自动路径管理

#### 2. File Repository (`repositories/file_repo.py`)
- 文件记录 CRUD
- 查询和统计
- 状态管理
- 软删除

#### 3. File Models (`models/file.py`)
- 数据模型定义
- API 请求/响应模型
- 枚举类型

---

## 数据库设计

### Files 表结构

```sql
CREATE TABLE files (
    -- 基础信息
    id TEXT PRIMARY KEY,                 -- file_{uuid}
    user_id TEXT NOT NULL,               -- 用户 ID
    filename TEXT NOT NULL,              -- 原始文件名
    file_size INTEGER NOT NULL,          -- 文件大小（字节）
    content_type TEXT NOT NULL,          -- MIME 类型
    
    -- 分类和状态
    category TEXT NOT NULL DEFAULT 'temp',      -- knowledge/avatar/attachment/temp
    status TEXT NOT NULL DEFAULT 'uploading',   -- uploading/uploaded/processing/ready/failed
    
    -- 存储信息
    storage_type TEXT NOT NULL DEFAULT 's3',    -- s3/local/oss/cos
    storage_path TEXT NOT NULL,                 -- S3 Key 或本地路径
    storage_url TEXT,                           -- 完整存储 URL
    bucket_name TEXT,                           -- S3 Bucket 名称
    
    -- 访问控制
    is_public INTEGER DEFAULT 0,                -- 是否公开
    access_url TEXT,                            -- 公开访问 URL
    presigned_url TEXT,                         -- 预签名 URL（临时）
    presigned_expires_at TEXT,                  -- 预签名过期时间
    
    -- 关联信息
    conversation_id TEXT,                       -- 关联对话
    message_id TEXT,                            -- 关联消息
    document_id TEXT,                           -- 关联文档（Ragie）
    
    -- 文件处理信息
    thumbnail_url TEXT,                         -- 缩略图
    duration REAL,                              -- 时长（音视频）
    width INTEGER,                              -- 宽度（图片/视频）
    height INTEGER,                             -- 高度（图片/视频）
    page_count INTEGER,                         -- 页数（PDF）
    
    -- 元数据
    metadata TEXT,                              -- JSON 元数据
    tags TEXT,                                  -- JSON 标签数组
    
    -- 时间戳
    created_at TEXT NOT NULL,
    updated_at TEXT,
    deleted_at TEXT,                            -- 软删除
    
    -- 统计
    download_count INTEGER DEFAULT 0,
    view_count INTEGER DEFAULT 0
);
```

### 索引

```sql
CREATE INDEX idx_files_user_id ON files(user_id);
CREATE INDEX idx_files_category_status ON files(category, status);
CREATE INDEX idx_files_conversation_id ON files(conversation_id);
CREATE INDEX idx_files_created_at ON files(created_at DESC);
CREATE INDEX idx_files_user_category ON files(user_id, category);
```

---

## 配置说明

### 1. 环境变量配置 (`.env`)

```bash
# AWS S3 配置
AWS_ACCESS_KEY_ID=your_access_key_id
AWS_SECRET_ACCESS_KEY=your_secret_access_key
AWS_DEFAULT_REGION=ap-southeast-1
AWS_S3_BUCKET=your-bucket-name
```

### 2. 存储配置 (`config/storage.yaml`)

```yaml
aws:
  access_key_id: ${AWS_ACCESS_KEY_ID}
  secret_access_key: ${AWS_SECRET_ACCESS_KEY}
  region: "ap-southeast-1"
  
  s3:
    bucket_name: "dify-storage-zenflux"
    endpoint_url: null
    
    upload:
      max_file_size: 100  # MB
      allowed_extensions:
        - pdf
        - docx
        - png
        - jpg
        # ...
      
      path_prefix:
        knowledge: "knowledge/{user_id}/{timestamp}/"
        avatar: "avatars/{user_id}/"
        attachment: "attachments/{user_id}/{conversation_id}/"
        temp: "temp/{user_id}/"
    
    acl:
      knowledge: "private"
      avatar: "public-read"
      attachment: "private"
      temp: "private"
```

---

## 使用指南

### 1. 初始化数据库

```bash
# 运行迁移脚本
python migrations/002_create_files_table.py --action upgrade
```

### 2. 测试 S3 配置

```bash
# 测试 S3 连接和上传
python scripts/test_s3_config.py
```

### 3. 代码示例

#### 上传文件

```python
from utils import get_s3_uploader
from repositories import get_file_repo

# 上传到 S3
s3_uploader = get_s3_uploader()
s3_result = await s3_uploader.upload_file(
    file_path="/tmp/document.pdf",
    category="knowledge",
    user_id="user_001",
    filename="产品文档.pdf"
)

# 保存到数据库
file_repo = get_file_repo()
file_record = await file_repo.create(
    user_id="user_001",
    filename="产品文档.pdf",
    file_size=s3_result["file_size"],
    content_type=s3_result["content_type"],
    storage_type=StorageType.S3,
    storage_path=s3_result["s3_key"],
    storage_url=s3_result["s3_url"],
    bucket_name="dify-storage-zenflux",
    category=FileCategory.KNOWLEDGE
)
```

#### 查询文件

```python
# 获取用户的所有文件
files = await file_repo.list_by_user(
    user_id="user_001",
    category=FileCategory.KNOWLEDGE,
    limit=20,
    offset=0
)

# 获取文件统计
stats = await file_repo.get_user_stats("user_001")
print(f"总文件数: {stats['total_files']}")
print(f"总大小: {stats['total_size']} bytes")
```

#### 生成访问 URL

```python
# 生成预签名 URL（24小时有效）
presigned_url = s3_uploader.get_presigned_url(
    s3_key=file_record["storage_path"],
    expires_in=86400
)
```

---

## API 接口

### 1. 文件上传

```http
POST /api/v1/knowledge/upload
Content-Type: multipart/form-data

Parameters:
- file: 文件（必填）
- user_id: 用户ID（必填）
- metadata: JSON 元数据（可选）
- mode: 处理模式（可选）
```

**响应:**
```json
{
  "code": 200,
  "message": "文档上传成功",
  "data": {
    "document_id": "doc_abc123",
    "status": "uploaded",
    "filename": "产品文档.pdf",
    "user_id": "user_001",
    "partition_id": "part_xyz",
    "message": "文档正在处理中"
  }
}
```

### 2. 文件列表查询

```http
GET /api/v1/files?user_id=user_001&category=knowledge&limit=20
```

### 3. 文件详情

```http
GET /api/v1/files/{file_id}
```

### 4. 文件删除

```http
DELETE /api/v1/files/{file_id}
```

### 5. 用户统计

```http
GET /api/v1/files/stats/{user_id}
```

---

## 文件分类说明

| 分类 | 说明 | ACL | 路径前缀 |
|------|------|-----|----------|
| `knowledge` | 知识库文件 | private | `knowledge/{user_id}/{timestamp}/` |
| `avatar` | 用户头像 | public-read | `avatars/{user_id}/` |
| `attachment` | 聊天附件 | private | `attachments/{user_id}/{conversation_id}/` |
| `temp` | 临时文件 | private | `temp/{user_id}/` |
| `export` | 导出文件 | private | `exports/{user_id}/` |
| `media` | 媒体文件 | private | `media/{user_id}/` |

---

## 文件状态流程

```
uploading → uploaded → processing → ready
                                 ↓
                              failed
```

- **uploading**: 上传中
- **uploaded**: 已上传（未处理）
- **processing**: 处理中（OCR、向量化等）
- **ready**: 已就绪（可使用）
- **failed**: 处理失败
- **deleted**: 已删除（软删除）

---

## 安全注意事项

1. **敏感信息**
   - ✅ `.env` 文件已添加到 `.gitignore`
   - ✅ 不要将 AWS 凭证提交到 Git
   - ✅ 使用环境变量管理密钥

2. **访问控制**
   - ✅ 知识库文件默认私有
   - ✅ 预签名 URL 有时效限制
   - ✅ 支持用户级隔离

3. **文件验证**
   - ✅ 文件大小限制（默认 100MB）
   - ✅ 文件类型白名单
   - ✅ 文件名过滤

---

## 性能优化

1. **并发上传**: 批量上传时限制并发数
2. **缓存策略**: 预签名 URL 缓存
3. **索引优化**: 数据库查询索引
4. **异步处理**: 文件处理异步化

---

## 未来扩展

- [ ] 支持阿里云 OSS
- [ ] 支持腾讯云 COS
- [ ] 图片缩略图自动生成
- [ ] 视频转码和预览
- [ ] 文件版本控制
- [ ] 分享链接和权限管理

---

## 相关文档

- [AWS S3 官方文档](https://docs.aws.amazon.com/s3/)
- [Boto3 文档](https://boto3.amazonaws.com/v1/documentation/api/latest/index.html)
- [Ragie API 文档](https://docs.ragie.ai/)

