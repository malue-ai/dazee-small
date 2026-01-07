#!/usr/bin/env python3
"""
数据库迁移脚本 - 添加 mime_type 列

版本: 005
日期: 2026-01-06
作者: ZenFlux Team

功能：
1. 添加 mime_type 列
2. 从 content_type 复制数据到 mime_type
"""

import asyncio
import sys
import aiosqlite
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from logger import get_logger

logger = get_logger("migration_005")


async def column_exists(db: aiosqlite.Connection, table: str, column: str) -> bool:
    """检查列是否存在"""
    async with db.execute(f"PRAGMA table_info({table})") as cursor:
        columns = await cursor.fetchall()
        column_names = [col[1] for col in columns]
        return column in column_names


async def upgrade_sqlite(db_path: str = "workspace/database/zenflux.db"):
    """
    升级 SQLite 数据库 - 添加 mime_type 列
    
    Args:
        db_path: 数据库路径
    """
    logger.info(f"🔄 开始升级 SQLite 数据库: {db_path}")
    
    try:
        async with aiosqlite.connect(db_path) as db:
            # 检查表是否存在
            async with db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='files'"
            ) as cursor:
                if not await cursor.fetchone():
                    logger.warning("⚠️ files 表不存在，跳过迁移")
                    return True
            
            # 1. 添加 mime_type 列
            if not await column_exists(db, "files", "mime_type"):
                logger.info("➕ 添加 mime_type 列...")
                await db.execute(
                    "ALTER TABLE files ADD COLUMN mime_type TEXT"
                )
                logger.info("✅ mime_type 列已添加")
                
                # 如果 content_type 存在，复制数据
                if await column_exists(db, "files", "content_type"):
                    logger.info("🔄 从 content_type 复制数据到 mime_type...")
                    await db.execute(
                        "UPDATE files SET mime_type = content_type WHERE mime_type IS NULL"
                    )
                    logger.info("✅ 数据复制完成")
            else:
                logger.info("⏭️ mime_type 列已存在，跳过")
            
            await db.commit()
        
        logger.info("✅ 数据库升级完成")
        return True
    
    except Exception as e:
        logger.error(f"❌ 升级失败: {str(e)}", exc_info=True)
        return False


async def downgrade_sqlite(db_path: str = "workspace/database/zenflux.db"):
    """
    降级 SQLite 数据库
    
    注意：SQLite 不支持 DROP COLUMN，需要重建表
    """
    logger.warning("⚠️ SQLite 不支持删除列，跳过降级")
    return True


async def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="数据库迁移：添加 mime_type 列")
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
    print("数据库迁移 - 005: 添加 mime_type 列")
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

