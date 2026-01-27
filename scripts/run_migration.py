#!/usr/bin/env python3
"""
执行 Production 数据库迁移脚本

用法：
    python scripts/run_migration.py --dry-run   # 仅显示将要执行的 SQL
    python scripts/run_migration.py --execute   # 实际执行迁移
"""

import asyncio
import sys
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

# Production 数据库连接
PRODUCTION_URL = "postgresql+asyncpg://postgres:hwcUu5D19KByzbKagzI0V4KoSzCwZy4p@zen0-backend-production-postgresql.cz0gu26m8g6c.ap-southeast-1.rds.amazonaws.com:5432/zen0_production_pg"

# 迁移 SQL 文件路径
MIGRATION_SQL_PATH = Path(__file__).parent / "migrate_production.sql"


async def dry_run():
    """仅显示将要执行的 SQL"""
    print("=" * 80)
    print("🔍 DRY RUN - 以下是将要执行的迁移 SQL:")
    print("=" * 80)
    
    sql_content = MIGRATION_SQL_PATH.read_text()
    print(sql_content)
    
    print("=" * 80)
    print("⚠️  以上 SQL 未实际执行。使用 --execute 参数来执行迁移。")
    print("=" * 80)


async def execute_migration():
    """执行迁移"""
    print("=" * 80)
    print("🚀 开始执行 Production 数据库迁移...")
    print("=" * 80)
    
    # 直接定义 SQL 语句（按正确顺序）
    statements = [
        # 1. 创建 fc_function_pool 表
        """
        CREATE TABLE IF NOT EXISTS fc_function_pool (
            id VARCHAR(64) PRIMARY KEY,
            function_name VARCHAR(128) NOT NULL,
            http_trigger_url VARCHAR(512) NULL,
            session_id VARCHAR(128) NULL,
            status INTEGER NOT NULL DEFAULT 0,
            conversation_id VARCHAR(64) NULL,
            user_id VARCHAR(64) NULL,
            oss_bucket_path VARCHAR(256) NULL,
            oss_mount_dir VARCHAR(256) NULL,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            allocated_at TIMESTAMP NULL,
            session_expire_at TIMESTAMP NULL,
            last_active_at TIMESTAMP NULL,
            metadata TEXT NOT NULL DEFAULT '{}'
        )
        """,
        # fc_function_pool 索引
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_fc_function_pool_function_name ON fc_function_pool(function_name)",
        "CREATE INDEX IF NOT EXISTS ix_fc_function_pool_status ON fc_function_pool(status)",
        "CREATE INDEX IF NOT EXISTS ix_fc_function_pool_session_id ON fc_function_pool(session_id)",
        "CREATE INDEX IF NOT EXISTS ix_fc_function_pool_conversation_id ON fc_function_pool(conversation_id)",
        "CREATE INDEX IF NOT EXISTS ix_fc_pool_conversation ON fc_function_pool(conversation_id)",
        "CREATE INDEX IF NOT EXISTS ix_fc_pool_status_created ON fc_function_pool(status, created_at)",
        
        # 2. sandboxes 表添加缺失的列
        "ALTER TABLE sandboxes ADD COLUMN IF NOT EXISTS active_project_path VARCHAR(256) NULL",
        "ALTER TABLE sandboxes ADD COLUMN IF NOT EXISTS active_project_stack VARCHAR(32) NULL",
        
        # 3. conversations 表索引
        "CREATE INDEX IF NOT EXISTS idx_conversations_status ON conversations(status)",
        "CREATE INDEX IF NOT EXISTS ix_conversations_updated_at ON conversations(updated_at)",
        
        # 4. messages 表索引
        "CREATE INDEX IF NOT EXISTS idx_messages_status ON messages(status)",
        "CREATE INDEX IF NOT EXISTS ix_messages_created_at ON messages(created_at)",
    ]
    
    print(f"📝 将执行 {len(statements)} 条 SQL 语句")
    
    # 连接数据库并执行
    engine = create_async_engine(PRODUCTION_URL)
    
    async with engine.begin() as conn:
        for i, stmt in enumerate(statements, 1):
            # 跳过 psql 元命令
            if stmt.strip().startswith('\\'):
                continue
                
            try:
                print(f"\n[{i}/{len(statements)}] 执行:")
                print(f"  {stmt[:100]}..." if len(stmt) > 100 else f"  {stmt}")
                
                await conn.execute(text(stmt))
                print(f"  ✅ 成功")
                
            except Exception as e:
                error_msg = str(e)
                # 忽略 "已存在" 类型的错误
                if "already exists" in error_msg.lower() or "已存在" in error_msg:
                    print(f"  ⏭️  跳过（已存在）")
                else:
                    print(f"  ❌ 失败: {error_msg}")
                    raise
    
    await engine.dispose()
    
    print("\n" + "=" * 80)
    print("✅ 迁移完成！")
    print("=" * 80)


async def verify_migration():
    """验证迁移结果"""
    print("\n" + "=" * 80)
    print("🔍 验证迁移结果...")
    print("=" * 80)
    
    engine = create_async_engine(PRODUCTION_URL)
    
    checks = [
        ("fc_function_pool 表", "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'fc_function_pool'"),
        ("sandboxes.active_project_path 列", "SELECT COUNT(*) FROM information_schema.columns WHERE table_name = 'sandboxes' AND column_name = 'active_project_path'"),
        ("sandboxes.active_project_stack 列", "SELECT COUNT(*) FROM information_schema.columns WHERE table_name = 'sandboxes' AND column_name = 'active_project_stack'"),
        ("idx_conversations_status 索引", "SELECT COUNT(*) FROM pg_indexes WHERE indexname = 'idx_conversations_status'"),
        ("idx_messages_status 索引", "SELECT COUNT(*) FROM pg_indexes WHERE indexname = 'idx_messages_status'"),
    ]
    
    async with engine.connect() as conn:
        for name, query in checks:
            result = await conn.execute(text(query))
            count = result.scalar()
            status = "✅" if count > 0 else "❌"
            print(f"  {status} {name}: {'存在' if count > 0 else '不存在'}")
    
    await engine.dispose()


def main():
    if len(sys.argv) < 2:
        print("用法:")
        print("  python scripts/run_migration.py --dry-run   # 仅显示将要执行的 SQL")
        print("  python scripts/run_migration.py --execute   # 实际执行迁移")
        print("  python scripts/run_migration.py --verify    # 验证迁移结果")
        sys.exit(1)
    
    arg = sys.argv[1]
    
    if arg == "--dry-run":
        asyncio.run(dry_run())
    elif arg == "--execute":
        confirm = input("⚠️  确定要在 PRODUCTION 数据库执行迁移吗？(输入 yes 确认): ")
        if confirm.lower() == "yes":
            asyncio.run(execute_migration())
            asyncio.run(verify_migration())
        else:
            print("已取消")
    elif arg == "--verify":
        asyncio.run(verify_migration())
    else:
        print(f"未知参数: {arg}")
        sys.exit(1)


if __name__ == "__main__":
    main()
