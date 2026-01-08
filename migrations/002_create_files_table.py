#!/usr/bin/env python3
"""
数据库迁移脚本 - 创建 files 表

版本: 002
日期: 2024-12-30
作者: ZenFlux Team

功能：
1. 创建 files 表
2. 创建相关索引
3. 兼容 SQLite 和 PostgreSQL
"""

import asyncio
import sys
import aiosqlite
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from logger import get_logger

logger = get_logger("migration_002")

# 文件表 SQL（历史迁移脚本，表结构现由 infra/database/models/file.py 管理）
FILES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS files (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    filename TEXT NOT NULL,
    file_size INTEGER NOT NULL,
    content_type TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'temp',
    status TEXT NOT NULL DEFAULT 'uploading',
    storage_type TEXT NOT NULL DEFAULT 's3',
    storage_path TEXT NOT NULL,
    storage_url TEXT,
    bucket_name TEXT,
    is_public INTEGER DEFAULT 0,
    access_url TEXT,
    presigned_url TEXT,
    presigned_expires_at TEXT,
    conversation_id TEXT,
    message_id TEXT,
    document_id TEXT,
    thumbnail_url TEXT,
    duration REAL,
    width INTEGER,
    height INTEGER,
    page_count INTEGER,
    metadata TEXT,
    tags TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT,
    deleted_at TEXT,
    download_count INTEGER DEFAULT 0,
    view_count INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_files_user_id ON files(user_id);
CREATE INDEX IF NOT EXISTS idx_files_category_status ON files(category, status);
CREATE INDEX IF NOT EXISTS idx_files_conversation_id ON files(conversation_id);
CREATE INDEX IF NOT EXISTS idx_files_created_at ON files(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_files_user_category ON files(user_id, category);
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
            # 执行创建表的 SQL
            await db.executescript(FILES_TABLE_SQL)
            await db.commit()
        
        logger.info("✅ files 表创建成功")
        logger.info("✅ 索引创建成功")
        
        # 验证表是否创建
        async with aiosqlite.connect(db_path) as db:
            async with db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='files'"
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    logger.info(f"✅ 验证成功: files 表存在")
                else:
                    raise Exception("files 表创建失败")
        
        return True
    
    except Exception as e:
        logger.error(f"❌ 升级失败: {str(e)}", exc_info=True)
        return False


async def downgrade_sqlite(db_path: str = "workspace/database/zenflux.db"):
    """
    降级 SQLite 数据库（删除 files 表）
    
    Args:
        db_path: 数据库路径
    """
    logger.info(f"🔄 开始降级 SQLite 数据库: {db_path}")
    
    try:
        async with aiosqlite.connect(db_path) as db:
            # 删除表
            await db.execute("DROP TABLE IF EXISTS files")
            await db.commit()
        
        logger.info("✅ files 表已删除")
        return True
    
    except Exception as e:
        logger.error(f"❌ 降级失败: {str(e)}", exc_info=True)
        return False


async def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="数据库迁移：创建 files 表")
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
    
    print("=" * 60)
    print("数据库迁移 - 002: 创建 files 表")
    print("=" * 60)
    
    if args.action == "upgrade":
        success = await upgrade_sqlite(args.db_path)
    else:
        success = await downgrade_sqlite(args.db_path)
    
    if success:
        print("\n✅ 迁移成功！")
        sys.exit(0)
    else:
        print("\n❌ 迁移失败，请检查日志")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())

