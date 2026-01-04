#!/usr/bin/env python3
"""
数据库迁移脚本 - 创建知识库相关表

版本: 003
日期: 2024-12-30
作者: ZenFlux Team

功能：
1. 创建 knowledge_bases 表（知识库）
2. 创建 knowledge_folders 表（文件夹）
3. 创建 knowledge_documents 表（文档）
4. 创建 knowledge_shares 表（分享）
5. 创建 knowledge_members 表（协作成员）
"""

import asyncio
import sys
import aiosqlite
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from logger import get_logger

logger = get_logger("migration_003")

# 知识库相关表 SQL（从 utils/database.py 复制）
KNOWLEDGE_TABLES_SQL = """
-- 知识库表
CREATE TABLE IF NOT EXISTS knowledge_bases (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    icon TEXT DEFAULT '📚',
    color TEXT DEFAULT '#667eea',
    owner_id TEXT NOT NULL,
    visibility TEXT NOT NULL DEFAULT 'private',
    is_shared INTEGER DEFAULT 0,
    document_count INTEGER DEFAULT 0,
    folder_count INTEGER DEFAULT 0,
    total_size INTEGER DEFAULT 0,
    ragie_partition_id TEXT,
    settings TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT,
    deleted_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_kb_owner_id ON knowledge_bases(owner_id);
CREATE INDEX IF NOT EXISTS idx_kb_visibility ON knowledge_bases(visibility);
CREATE INDEX IF NOT EXISTS idx_kb_created_at ON knowledge_bases(created_at DESC);

-- 文件夹表
CREATE TABLE IF NOT EXISTS knowledge_folders (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    icon TEXT DEFAULT '📁',
    kb_id TEXT NOT NULL,
    parent_id TEXT,
    path TEXT NOT NULL,
    level INTEGER DEFAULT 0,
    document_count INTEGER DEFAULT 0,
    subfolder_count INTEGER DEFAULT 0,
    sort_order INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT,
    deleted_at TEXT,
    FOREIGN KEY (kb_id) REFERENCES knowledge_bases(id),
    FOREIGN KEY (parent_id) REFERENCES knowledge_folders(id)
);
CREATE INDEX IF NOT EXISTS idx_folder_kb_id ON knowledge_folders(kb_id);
CREATE INDEX IF NOT EXISTS idx_folder_parent_id ON knowledge_folders(parent_id);
CREATE INDEX IF NOT EXISTS idx_folder_path ON knowledge_folders(path);

-- 文档表
CREATE TABLE IF NOT EXISTS knowledge_documents (
    id TEXT PRIMARY KEY,
    kb_id TEXT NOT NULL,
    folder_id TEXT,
    file_id TEXT NOT NULL,
    name TEXT NOT NULL,
    original_filename TEXT NOT NULL,
    file_size INTEGER NOT NULL,
    content_type TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    ragie_document_id TEXT,
    tags TEXT,
    metadata TEXT,
    summary TEXT,
    view_count INTEGER DEFAULT 0,
    reference_count INTEGER DEFAULT 0,
    sort_order INTEGER DEFAULT 0,
    is_pinned INTEGER DEFAULT 0,
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

-- 分享表
CREATE TABLE IF NOT EXISTS knowledge_shares (
    id TEXT PRIMARY KEY,
    kb_id TEXT NOT NULL,
    share_type TEXT NOT NULL,
    shared_by TEXT NOT NULL,
    shared_to TEXT,
    share_link TEXT,
    link_password TEXT,
    permission TEXT NOT NULL DEFAULT 'read',
    expires_at TEXT,
    access_count INTEGER DEFAULT 0,
    last_accessed_at TEXT,
    created_at TEXT NOT NULL,
    revoked_at TEXT,
    FOREIGN KEY (kb_id) REFERENCES knowledge_bases(id)
);
CREATE INDEX IF NOT EXISTS idx_share_kb_id ON knowledge_shares(kb_id);
CREATE INDEX IF NOT EXISTS idx_share_link ON knowledge_shares(share_link);
CREATE INDEX IF NOT EXISTS idx_share_to ON knowledge_shares(shared_to);

-- 成员表
CREATE TABLE IF NOT EXISTS knowledge_members (
    id TEXT PRIMARY KEY,
    kb_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'viewer',
    permissions TEXT,
    invited_by TEXT NOT NULL,
    invitation_status TEXT DEFAULT 'accepted',
    contribution_count INTEGER DEFAULT 0,
    last_active_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT,
    removed_at TEXT,
    FOREIGN KEY (kb_id) REFERENCES knowledge_bases(id),
    UNIQUE(kb_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_member_kb_id ON knowledge_members(kb_id);
CREATE INDEX IF NOT EXISTS idx_member_user_id ON knowledge_members(user_id);
"""


async def upgrade_sqlite(db_path: str = "workspace/database/zenflux.db"):
    """
    升级 SQLite 数据库
    
    Args:
        db_path: 数据库路径
    """
    logger.info(f"🔄 开始升级 SQLite 数据库: {db_path}")
    
    try:
        async with aiosqlite.connect(db_path) as db:
            # 执行创建所有知识库表的 SQL
            await db.executescript(KNOWLEDGE_TABLES_SQL)
            await db.commit()
        
        logger.info("✅ knowledge_bases 表创建成功")
        logger.info("✅ knowledge_folders 表创建成功")
        logger.info("✅ knowledge_documents 表创建成功")
        logger.info("✅ knowledge_shares 表创建成功")
        logger.info("✅ knowledge_members 表创建成功")
        logger.info("✅ 所有索引创建成功")
        
        # 验证表是否创建
        async with aiosqlite.connect(db_path) as db:
            tables = [
                'knowledge_bases',
                'knowledge_folders',
                'knowledge_documents',
                'knowledge_shares',
                'knowledge_members'
            ]
            
            for table in tables:
                async with db.execute(
                    f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}'"
                ) as cursor:
                    row = await cursor.fetchone()
                    if row:
                        logger.info(f"✅ 验证成功: {table} 表存在")
                    else:
                        raise Exception(f"{table} 表创建失败")
        
        return True
    
    except Exception as e:
        logger.error(f"❌ 升级失败: {str(e)}", exc_info=True)
        return False


async def downgrade_sqlite(db_path: str = "workspace/database/zenflux.db"):
    """
    降级 SQLite 数据库（删除知识库相关表）
    
    Args:
        db_path: 数据库路径
    """
    logger.info(f"🔄 开始降级 SQLite 数据库: {db_path}")
    
    try:
        async with aiosqlite.connect(db_path) as db:
            # 按照依赖顺序删除表（先删除依赖表）
            await db.execute("DROP TABLE IF EXISTS knowledge_members")
            await db.execute("DROP TABLE IF EXISTS knowledge_shares")
            await db.execute("DROP TABLE IF EXISTS knowledge_documents")
            await db.execute("DROP TABLE IF EXISTS knowledge_folders")
            await db.execute("DROP TABLE IF EXISTS knowledge_bases")
            await db.commit()
        
        logger.info("✅ 所有知识库表已删除")
        return True
    
    except Exception as e:
        logger.error(f"❌ 降级失败: {str(e)}", exc_info=True)
        return False


async def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="数据库迁移：创建知识库相关表")
    parser.add_argument(
        "--action",
        choices=["upgrade", "downgrade"],
        default="upgrade",
        help="迁移操作（upgrade/downgrade）"
    )
    parser.add_argument(
        "--db-path",
        default="workspace/database/zenflux.db",
        help="数据库路径"
    )
    
    args = parser.parse_args()
    
    print("=" * 70)
    print("数据库迁移 - 003: 创建知识库相关表")
    print("=" * 70)
    print()
    print("📋 将创建以下表：")
    print("  1. knowledge_bases     - 知识库表")
    print("  2. knowledge_folders   - 文件夹表（支持多级嵌套）")
    print("  3. knowledge_documents - 文档表")
    print("  4. knowledge_shares    - 分享表")
    print("  5. knowledge_members   - 协作成员表")
    print()
    print("🎯 功能特性：")
    print("  ✓ 用户隔离（每个用户独立的知识库）")
    print("  ✓ 文件夹组织（多级嵌套目录结构）")
    print("  ✓ 权限控制（私有/公开/分享）")
    print("  ✓ 协作功能（多人协作编辑）")
    print("  ✓ 分享链接（临时分享、密码保护）")
    print()
    print("=" * 70)
    print()
    
    if args.action == "upgrade":
        success = await upgrade_sqlite(args.db_path)
    else:
        confirm = input("⚠️  确定要删除所有知识库表吗？这将删除所有知识库数据！(yes/no): ")
        if confirm.lower() != 'yes':
            print("❌ 操作已取消")
            sys.exit(0)
        success = await downgrade_sqlite(args.db_path)
    
    print()
    if success:
        print("✅ 迁移成功！")
        sys.exit(0)
    else:
        print("❌ 迁移失败，请检查日志")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())

