#!/usr/bin/env python3
"""
数据库迁移脚本 - 创建 sandboxes 表

版本: 006
日期: 2026-01-07
作者: ZenFlux Team

功能：
1. 创建 sandboxes 表，存储 E2B 沙盒与 conversation 的映射关系
2. 支持沙盒生命周期管理（pause/resume）
"""

import asyncio
import sys
import aiosqlite
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from logger import get_logger

logger = get_logger("migration_006")


async def table_exists(db: aiosqlite.Connection, table: str) -> bool:
    """检查表是否存在"""
    async with db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,)
    ) as cursor:
        return await cursor.fetchone() is not None


async def upgrade_sqlite(db_path: str = "workspace/database/zenflux.db"):
    """
    升级 SQLite 数据库 - 创建 sandboxes 表
    
    Args:
        db_path: 数据库路径
    """
    logger.info(f"🔄 开始升级 SQLite 数据库: {db_path}")
    
    try:
        async with aiosqlite.connect(db_path) as db:
            # 检查表是否已存在
            if await table_exists(db, "sandboxes"):
                logger.info("⏭️ sandboxes 表已存在，跳过创建")
                return True
            
            # 创建 sandboxes 表
            logger.info("➕ 创建 sandboxes 表...")
            await db.execute("""
                CREATE TABLE sandboxes (
                    -- 主键
                    id TEXT PRIMARY KEY,
                    
                    -- 关联关系（一个 conversation 对应一个沙盒）
                    conversation_id TEXT NOT NULL UNIQUE,
                    user_id TEXT NOT NULL,
                    
                    -- E2B 沙盒信息
                    e2b_sandbox_id TEXT,
                    status TEXT DEFAULT 'creating',
                    stack TEXT,
                    preview_url TEXT,
                    
                    -- 元数据
                    metadata TEXT DEFAULT '{}',
                    
                    -- 时间戳
                    created_at TEXT NOT NULL,
                    updated_at TEXT,
                    last_active_at TEXT,
                    paused_at TEXT
                )
            """)
            logger.info("✅ sandboxes 表创建成功")
            
            # 创建索引
            logger.info("➕ 创建索引...")
            await db.execute(
                "CREATE INDEX idx_sandboxes_conversation ON sandboxes(conversation_id)"
            )
            await db.execute(
                "CREATE INDEX idx_sandboxes_user ON sandboxes(user_id)"
            )
            await db.execute(
                "CREATE INDEX idx_sandboxes_status ON sandboxes(status)"
            )
            await db.execute(
                "CREATE INDEX idx_sandboxes_e2b_id ON sandboxes(e2b_sandbox_id)"
            )
            logger.info("✅ 索引创建成功")
            
            await db.commit()
        
        logger.info("✅ 数据库升级完成")
        return True
    
    except Exception as e:
        logger.error(f"❌ 升级失败: {str(e)}", exc_info=True)
        return False


async def downgrade_sqlite(db_path: str = "workspace/database/zenflux.db"):
    """
    降级 SQLite 数据库 - 删除 sandboxes 表
    
    Args:
        db_path: 数据库路径
    """
    logger.info(f"🔄 开始降级 SQLite 数据库: {db_path}")
    
    try:
        async with aiosqlite.connect(db_path) as db:
            # 检查表是否存在
            if not await table_exists(db, "sandboxes"):
                logger.info("⏭️ sandboxes 表不存在，跳过删除")
                return True
            
            # 删除表
            logger.info("🗑️ 删除 sandboxes 表...")
            await db.execute("DROP TABLE IF EXISTS sandboxes")
            await db.commit()
            
            logger.info("✅ sandboxes 表已删除")
        
        logger.info("✅ 数据库降级完成")
        return True
    
    except Exception as e:
        logger.error(f"❌ 降级失败: {str(e)}", exc_info=True)
        return False


async def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="数据库迁移：创建 sandboxes 表")
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
    print("数据库迁移 - 006: 创建 sandboxes 表")
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

