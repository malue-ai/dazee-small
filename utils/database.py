"""
SQLite 数据库管理模块

提供：
1. 数据库初始化和连接管理
2. 所有表结构定义（Users, Conversations, Messages, Files, Knowledge）
3. 序列化/反序列化工具函数
"""

import aiosqlite
import json
import logging
from pathlib import Path
from typing import Optional
from datetime import datetime

logger = logging.getLogger(__name__)


# ============================================================================
#                           表结构定义 - SQL
# ============================================================================

# ==================== 用户表 ====================
USERS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    username TEXT,
    email TEXT,
    avatar_url TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP,
    metadata TEXT DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
"""

# ==================== 对话表 ====================
CONVERSATIONS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    title TEXT DEFAULT '新对话',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata TEXT DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_conversations_user_id ON conversations(user_id);
CREATE INDEX IF NOT EXISTS idx_conversations_updated_at ON conversations(updated_at DESC);
"""

# ==================== 消息表 ====================
MESSAGES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    status TEXT,
    score REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata TEXT DEFAULT '{}',
    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
);

CREATE INDEX IF NOT EXISTS idx_messages_conversation_id ON messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_messages_created_at ON messages(created_at);
"""

# ==================== 文件表 ====================
FILES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS files (
    -- 基础信息
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    filename TEXT NOT NULL,
    file_size INTEGER NOT NULL,
    content_type TEXT NOT NULL,
    
    -- 分类和状态
    category TEXT NOT NULL DEFAULT 'temp',    -- knowledge/avatar/attachment/temp/export/media
    status TEXT NOT NULL DEFAULT 'uploading', -- uploading/uploaded/processing/ready/failed/deleted
    
    -- 存储信息
    storage_type TEXT NOT NULL DEFAULT 's3',
    storage_path TEXT NOT NULL,
    storage_url TEXT,
    bucket_name TEXT,
    
    -- 访问控制
    is_public INTEGER DEFAULT 0,
    access_url TEXT,
    presigned_url TEXT,
    presigned_expires_at TEXT,
    
    -- 关联信息
    conversation_id TEXT,
    message_id TEXT,
    document_id TEXT,
    
    -- 文件处理信息
    thumbnail_url TEXT,
    duration REAL,
    width INTEGER,
    height INTEGER,
    page_count INTEGER,
    
    -- 元数据
    metadata TEXT,
    tags TEXT,
    
    -- 时间戳
    created_at TEXT NOT NULL,
    updated_at TEXT,
    deleted_at TEXT,
    
    -- 统计
    download_count INTEGER DEFAULT 0,
    view_count INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_files_user_id ON files(user_id);
CREATE INDEX IF NOT EXISTS idx_files_category_status ON files(category, status);
CREATE INDEX IF NOT EXISTS idx_files_conversation_id ON files(conversation_id);
CREATE INDEX IF NOT EXISTS idx_files_created_at ON files(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_files_user_category ON files(user_id, category);
"""

# ==================== 知识库表 ====================
KNOWLEDGE_BASES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS knowledge_bases (
    -- 基础信息
    id TEXT PRIMARY KEY,                      -- kb_{uuid}
    name TEXT NOT NULL,                       -- 知识库名称
    description TEXT,                         -- 描述
    icon TEXT DEFAULT '📚',                  -- 图标
    color TEXT DEFAULT '#667eea',            -- 颜色标识
    
    -- 所有者和权限
    owner_id TEXT NOT NULL,                  -- 所有者用户 ID
    visibility TEXT NOT NULL DEFAULT 'private', -- private/public/unlisted
    is_shared INTEGER DEFAULT 0,             -- 是否已分享给他人
    
    -- 统计信息
    document_count INTEGER DEFAULT 0,        -- 文档数量
    folder_count INTEGER DEFAULT 0,          -- 文件夹数量
    total_size INTEGER DEFAULT 0,            -- 总大小（字节）
    
    -- Ragie 集成
    ragie_partition_id TEXT,                 -- Ragie 分区 ID（用于 RAG）
    
    -- 配置
    settings TEXT,                            -- JSON 配置
    
    -- 时间戳
    created_at TEXT NOT NULL,
    updated_at TEXT,
    deleted_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_kb_owner_id ON knowledge_bases(owner_id);
CREATE INDEX IF NOT EXISTS idx_kb_visibility ON knowledge_bases(visibility);
CREATE INDEX IF NOT EXISTS idx_kb_created_at ON knowledge_bases(created_at DESC);
"""

# ==================== 知识库文件夹表 ====================
KNOWLEDGE_FOLDERS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS knowledge_folders (
    -- 基础信息
    id TEXT PRIMARY KEY,                      -- folder_{uuid}
    name TEXT NOT NULL,                       -- 文件夹名称
    description TEXT,                         -- 描述
    icon TEXT DEFAULT '📁',                  -- 图标
    
    -- 层级关系
    kb_id TEXT NOT NULL,                     -- 所属知识库 ID
    parent_id TEXT,                           -- 父文件夹 ID（NULL 表示根目录）
    path TEXT NOT NULL,                       -- 完整路径（如 /docs/api/）
    level INTEGER DEFAULT 0,                  -- 层级深度
    
    -- 统计
    document_count INTEGER DEFAULT 0,        -- 文档数量
    subfolder_count INTEGER DEFAULT 0,       -- 子文件夹数量
    
    -- 排序
    sort_order INTEGER DEFAULT 0,
    
    -- 时间戳
    created_at TEXT NOT NULL,
    updated_at TEXT,
    deleted_at TEXT,
    
    FOREIGN KEY (kb_id) REFERENCES knowledge_bases(id),
    FOREIGN KEY (parent_id) REFERENCES knowledge_folders(id)
);

CREATE INDEX IF NOT EXISTS idx_folder_kb_id ON knowledge_folders(kb_id);
CREATE INDEX IF NOT EXISTS idx_folder_parent_id ON knowledge_folders(parent_id);
CREATE INDEX IF NOT EXISTS idx_folder_path ON knowledge_folders(path);
"""

# ==================== 知识库文档表 ====================
KNOWLEDGE_DOCUMENTS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS knowledge_documents (
    -- 基础信息
    id TEXT PRIMARY KEY,                      -- doc_{uuid}
    kb_id TEXT NOT NULL,                     -- 所属知识库 ID
    folder_id TEXT,                           -- 所属文件夹 ID（NULL = 根目录）
    file_id TEXT NOT NULL,                   -- 关联的文件 ID（files 表）
    
    -- 文档信息（冗余存储，提高查询效率）
    name TEXT NOT NULL,                       -- 文档名称（可自定义）
    original_filename TEXT NOT NULL,          -- 原始文件名
    file_size INTEGER NOT NULL,              -- 文件大小
    content_type TEXT,                        -- 文件类型
    
    -- 处理状态（与 Ragie 同步）
    status TEXT NOT NULL DEFAULT 'pending',  -- pending/processing/indexed/failed
    ragie_document_id TEXT,                   -- Ragie 文档 ID（用于 RAG 检索）
    
    -- 元数据
    tags TEXT,                                -- JSON 标签数组
    metadata TEXT,                            -- JSON 自定义元数据
    summary TEXT,                             -- AI 生成的摘要
    
    -- 统计
    view_count INTEGER DEFAULT 0,
    reference_count INTEGER DEFAULT 0,       -- 被引用次数
    
    -- 排序
    sort_order INTEGER DEFAULT 0,
    is_pinned INTEGER DEFAULT 0,             -- 是否置顶
    
    -- 时间戳
    created_at TEXT NOT NULL,
    updated_at TEXT,
    deleted_at TEXT,
    
    FOREIGN KEY (kb_id) REFERENCES knowledge_bases(id),
    FOREIGN KEY (folder_id) REFERENCES knowledge_folders(id),
    FOREIGN KEY (file_id) REFERENCES files(id)
);

CREATE INDEX IF NOT EXISTS idx_doc_kb_id ON knowledge_documents(kb_id);
CREATE INDEX IF NOT EXISTS idx_doc_folder_id ON knowledge_documents(folder_id);
CREATE INDEX IF NOT EXISTS idx_doc_file_id ON knowledge_documents(file_id);
CREATE INDEX IF NOT EXISTS idx_doc_status ON knowledge_documents(status);
CREATE INDEX IF NOT EXISTS idx_doc_ragie_id ON knowledge_documents(ragie_document_id);
CREATE INDEX IF NOT EXISTS idx_doc_created_at ON knowledge_documents(created_at DESC);
"""

# ==================== 知识库分享表 ====================
KNOWLEDGE_SHARES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS knowledge_shares (
    -- 基础信息
    id TEXT PRIMARY KEY,                      -- share_{uuid}
    kb_id TEXT NOT NULL,                     -- 知识库 ID
    share_type TEXT NOT NULL,                -- link/user/public
    
    -- 分享者和接收者
    shared_by TEXT NOT NULL,                 -- 分享者用户 ID
    shared_to TEXT,                           -- 接收者用户 ID
    
    -- 分享链接
    share_link TEXT,                          -- 分享链接 token
    link_password TEXT,                       -- 链接密码（可选）
    
    -- 权限
    permission TEXT NOT NULL DEFAULT 'read', -- read/write/admin
    
    -- 有效期
    expires_at TEXT,                          -- 过期时间
    
    -- 统计
    access_count INTEGER DEFAULT 0,
    last_accessed_at TEXT,
    
    -- 时间戳
    created_at TEXT NOT NULL,
    revoked_at TEXT,
    
    FOREIGN KEY (kb_id) REFERENCES knowledge_bases(id)
);

CREATE INDEX IF NOT EXISTS idx_share_kb_id ON knowledge_shares(kb_id);
CREATE INDEX IF NOT EXISTS idx_share_link ON knowledge_shares(share_link);
CREATE INDEX IF NOT EXISTS idx_share_to ON knowledge_shares(shared_to);
"""

# ==================== 知识库成员表 ====================
KNOWLEDGE_MEMBERS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS knowledge_members (
    -- 基础信息
    id TEXT PRIMARY KEY,                      -- member_{uuid}
    kb_id TEXT NOT NULL,                     -- 知识库 ID
    user_id TEXT NOT NULL,                   -- 成员用户 ID
    
    -- 角色和权限
    role TEXT NOT NULL DEFAULT 'viewer',     -- owner/editor/viewer
    permissions TEXT,                         -- JSON 详细权限
    
    -- 邀请信息
    invited_by TEXT NOT NULL,                -- 邀请者用户 ID
    invitation_status TEXT DEFAULT 'accepted', -- pending/accepted/declined
    
    -- 统计
    contribution_count INTEGER DEFAULT 0,
    last_active_at TEXT,
    
    -- 时间戳
    created_at TEXT NOT NULL,
    updated_at TEXT,
    removed_at TEXT,
    
    FOREIGN KEY (kb_id) REFERENCES knowledge_bases(id),
    UNIQUE(kb_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_member_kb_id ON knowledge_members(kb_id);
CREATE INDEX IF NOT EXISTS idx_member_user_id ON knowledge_members(user_id);
"""


# ============================================================================
#                           数据库管理器
# ============================================================================

class DatabaseManager:
    """
    数据库管理器
    
    统一管理所有表的创建和数据库连接
    """
    
    def __init__(self, db_path: str = "workspace/database/zenflux.db"):
        """
        初始化数据库管理器
        
        Args:
            db_path: 数据库文件路径
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
    
    async def init_database(self):
        """初始化所有数据库表"""
        async with aiosqlite.connect(self.db_path) as db:
            # 按依赖顺序创建表
            tables = [
                ("users", USERS_TABLE_SQL),
                ("conversations", CONVERSATIONS_TABLE_SQL),
                ("messages", MESSAGES_TABLE_SQL),
                ("files", FILES_TABLE_SQL),
                ("knowledge_bases", KNOWLEDGE_BASES_TABLE_SQL),
                ("knowledge_folders", KNOWLEDGE_FOLDERS_TABLE_SQL),
                ("knowledge_documents", KNOWLEDGE_DOCUMENTS_TABLE_SQL),
                ("knowledge_shares", KNOWLEDGE_SHARES_TABLE_SQL),
                ("knowledge_members", KNOWLEDGE_MEMBERS_TABLE_SQL),
            ]
            
            for table_name, sql in tables:
                try:
                    await db.executescript(sql)
                    logger.debug(f"✅ 表 {table_name} 已创建/检查")
                except Exception as e:
                    logger.error(f"❌ 创建表 {table_name} 失败: {e}")
                    raise
            
            await db.commit()
            logger.info(f"✅ 数据库初始化完成: {self.db_path}")
            logger.info(f"   - 共 {len(tables)} 张表")
    
    def get_connection(self) -> aiosqlite.Connection:
        """
        获取数据库连接
        
        注意：返回的是未启动的连接对象，需要配合 async with 使用
        
        Returns:
            数据库连接对象
        """
        return aiosqlite.connect(self.db_path)


# ============================================================================
#                           全局实例和工具函数
# ============================================================================

# 全局数据库管理器实例
db_manager = DatabaseManager()


async def init_db():
    """初始化数据库（启动时调用）"""
    await db_manager.init_database()


def serialize_metadata(metadata: Optional[dict]) -> str:
    """序列化元数据为 JSON 字符串"""
    if metadata is None:
        return "{}"
    return json.dumps(metadata, ensure_ascii=False)


def deserialize_metadata(metadata_str: str) -> dict:
    """反序列化 JSON 字符串为元数据字典"""
    try:
        return json.loads(metadata_str)
    except (json.JSONDecodeError, TypeError):
        return {}


def serialize_list(items: Optional[list]) -> str:
    """序列化列表为 JSON 字符串"""
    if items is None:
        return "[]"
    return json.dumps(items, ensure_ascii=False)


def deserialize_list(items_str: str) -> list:
    """反序列化 JSON 字符串为列表"""
    try:
        return json.loads(items_str)
    except (json.JSONDecodeError, TypeError):
        return []


# ============================================================================
#                           表结构汇总（便于查看）
# ============================================================================

"""
📊 数据库表结构汇总

┌─────────────────────────────────────────────────────────────────────────────┐
│                              ZenFlux Database                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────┐    ┌─────────────────┐    ┌─────────────┐                 │
│  │   users     │◄───│  conversations  │───►│  messages   │                 │
│  │             │    │                 │    │             │                 │
│  │ - id        │    │ - id            │    │ - id        │                 │
│  │ - username  │    │ - user_id       │    │ - conv_id   │                 │
│  │ - email     │    │ - title         │    │ - role      │                 │
│  │ - metadata  │    │ - metadata      │    │ - content   │                 │
│  └─────────────┘    └─────────────────┘    └─────────────┘                 │
│         │                                                                   │
│         │                                                                   │
│         ▼                                                                   │
│  ┌─────────────┐                           ┌─────────────────────────────┐ │
│  │   files     │◄──────────────────────────│   knowledge_documents       │ │
│  │             │         file_id           │                             │ │
│  │ - id        │                           │ - id                        │ │
│  │ - user_id   │                           │ - kb_id                     │ │
│  │ - filename  │                           │ - folder_id                 │ │
│  │ - storage   │                           │ - ragie_document_id  ◄──┐   │ │
│  │ - category  │                           │ - status                 │   │ │
│  └─────────────┘                           └─────────────────────────│───┘ │
│                                                      ▲               │     │
│                                                      │               │     │
│  ┌─────────────────┐    ┌──────────────────┐    ┌───┴───────────┐   │     │
│  │ knowledge_bases │───►│ knowledge_folders│───►│    Ragie      │◄──┘     │
│  │                 │    │                  │    │  (Vector DB)  │         │
│  │ - id            │    │ - id             │    │               │         │
│  │ - owner_id      │    │ - kb_id          │    │ 文档向量化    │         │
│  │ - visibility    │    │ - parent_id      │    │ RAG 检索      │         │
│  │ - ragie_part_id │    │ - path           │    └───────────────┘         │
│  └────────┬────────┘    └──────────────────┘                              │
│           │                                                                │
│           ├────────────────┬────────────────┐                              │
│           ▼                ▼                ▼                              │
│  ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐              │
│  │ knowledge_shares│ │knowledge_members│ │   (权限控制)    │              │
│  │                 │ │                 │ │                 │              │
│  │ - share_link    │ │ - role          │ │ private/public  │              │
│  │ - permission    │ │ - permissions   │ │ /unlisted       │              │
│  │ - expires_at    │ │ - invited_by    │ │                 │              │
│  └─────────────────┘ └─────────────────┘ └─────────────────┘              │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
"""
