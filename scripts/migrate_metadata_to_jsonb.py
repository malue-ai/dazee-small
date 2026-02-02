"""
迁移 metadata 字段为 JSONB（PostgreSQL 长期优化）

⚠️ 警告：此操作会修改表结构，需要：
1. 备份数据
2. 在维护窗口执行
3. 验证数据完整性

使用方法：
    python scripts/migrate_metadata_to_jsonb.py --dry-run  # 预览
    python scripts/migrate_metadata_to_jsonb.py --execute # 执行
"""

import asyncio
import os
import sys
import argparse
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

# 从环境变量获取数据库 URL
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:924Ff8O5kfEWOvzj3nN1ricrWVTIHSy8@zen0-backend-staging-postgresql.cz0gu26m8g6c.ap-southeast-1.rds.amazonaws.com:5432/zen0_staging_pg"
)

IS_SQLITE = DATABASE_URL.startswith("sqlite")
engine = create_async_engine(DATABASE_URL, echo=False, pool_pre_ping=True)


async def check_metadata_type():
    """检查 metadata 字段类型"""
    if IS_SQLITE:
        print("⚠️ SQLite 不支持 JSONB，跳过迁移")
        return None
    
    sql = """
        SELECT 
            table_name,
            column_name,
            data_type
        FROM information_schema.columns
        WHERE table_name IN ('messages', 'conversations')
        AND column_name = 'metadata'
        ORDER BY table_name
    """
    
    async with engine.begin() as conn:
        result = await conn.execute(text(sql))
        rows = result.fetchall()
        
        return {row[0]: row[2] for row in rows}


async def migrate_metadata_to_jsonb(dry_run: bool = True):
    """迁移 metadata 为 JSONB"""
    if IS_SQLITE:
        print("⚠️ SQLite 不支持 JSONB，跳过迁移")
        return
    
    print("=" * 60)
    print("🔄 迁移 metadata 字段为 JSONB")
    print("=" * 60)
    print(f"模式: {'预览（dry-run）' if dry_run else '执行'}")
    print("")
    
    # 检查当前类型
    print("🔍 检查当前 metadata 类型...")
    types = await check_metadata_type()
    if not types:
        print("❌ 未找到 metadata 字段")
        return
    
    for table, current_type in types.items():
        print(f"  {table}.metadata: {current_type}")
        if current_type == "jsonb":
            print(f"  ✅ {table}.metadata 已经是 JSONB，无需迁移")
        elif current_type in ("text", "character varying"):
            print(f"  ⚠️ {table}.metadata 需要迁移为 JSONB")
    
    print("")
    
    if dry_run:
        print("📋 预览迁移 SQL（不会执行）：")
        print("")
        for table in ["messages", "conversations"]:
            if types.get(table) in ("text", "character varying"):
                print(f"-- 迁移 {table}.metadata")
                print(f"ALTER TABLE {table} ALTER COLUMN metadata TYPE JSONB USING metadata::jsonb;")
                print("")
        print("=" * 60)
        print("💡 使用 --execute 参数执行迁移")
        print("=" * 60)
        return
    
    # 执行迁移
    print("🔨 执行迁移...")
    migrations = []
    
    for table in ["messages", "conversations"]:
        if types.get(table) in ("text", "character varying"):
            migrations.append(table)
    
    if not migrations:
        print("✅ 所有 metadata 字段已经是 JSONB，无需迁移")
        return
    
    try:
        async with engine.begin() as conn:
            for table in migrations:
                print(f"  迁移 {table}.metadata...")
                sql = f"ALTER TABLE {table} ALTER COLUMN metadata TYPE JSONB USING metadata::jsonb;"
                await conn.execute(text(sql))
                print(f"  ✅ {table}.metadata 迁移成功")
        
        print("")
        print("🔨 创建 GIN 索引...")
        async with engine.begin() as conn:
            # 创建 usage 索引
            sql = """
                CREATE INDEX IF NOT EXISTS idx_messages_metadata_usage 
                ON messages USING GIN ((metadata->'usage'));
            """
            await conn.execute(text(sql))
            print("  ✅ idx_messages_metadata_usage 创建成功")
            
            # 创建 stream 索引
            sql = """
                CREATE INDEX IF NOT EXISTS idx_messages_metadata_stream 
                ON messages USING GIN ((metadata->'stream'));
            """
            await conn.execute(text(sql))
            print("  ✅ idx_messages_metadata_stream 创建成功")
        
        print("")
        print("=" * 60)
        print("✅ 迁移完成")
        print("=" * 60)
        
    except Exception as e:
        print(f"❌ 迁移失败: {str(e)}", exc_info=True)
        raise
    finally:
        await engine.dispose()


async def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="迁移 metadata 为 JSONB")
    parser.add_argument("--dry-run", action="store_true", help="预览模式（不执行）")
    parser.add_argument("--execute", action="store_true", help="执行迁移")
    
    args = parser.parse_args()
    
    if not args.execute and not args.dry_run:
        print("⚠️ 请指定 --dry-run 或 --execute")
        parser.print_help()
        return
    
    await migrate_metadata_to_jsonb(dry_run=not args.execute)


if __name__ == "__main__":
    asyncio.run(main())
