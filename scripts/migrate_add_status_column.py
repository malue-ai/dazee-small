"""
添加 conversations.status 字段到线上数据库

执行方式：
    python scripts/migrate_add_status_column.py
"""

import asyncio
import os
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
from sqlalchemy import text
from infra.database import engine

load_dotenv()


async def check_and_add_status_column():
    """检查并添加 status 字段"""
    
    print("=" * 60)
    print("🔍 检查线上数据库 conversations 表结构...")
    print("=" * 60)
    
    async with engine.begin() as conn:
        # 1. 检查表是否存在
        result = await conn.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'conversations'
            );
        """))
        table_exists = result.scalar()
        
        if not table_exists:
            print("❌ conversations 表不存在！")
            return
        
        print("✅ conversations 表存在")
        
        # 2. 查看当前表结构
        result = await conn.execute(text("""
            SELECT column_name, data_type, character_maximum_length, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_schema = 'public' 
            AND table_name = 'conversations'
            ORDER BY ordinal_position;
        """))
        
        columns = result.fetchall()
        print(f"\n📋 当前字段列表 ({len(columns)} 个):")
        for col in columns:
            nullable = "NULL" if col[3] == 'YES' else "NOT NULL"
            default = f", default={col[4]}" if col[4] else ""
            length = f"({col[2]})" if col[2] else ""
            print(f"  - {col[0]}: {col[1]}{length} {nullable}{default}")
        
        # 3. 检查 status 字段是否存在
        status_exists = any(col[0] == 'status' for col in columns)
        
        if status_exists:
            print("\n✅ status 字段已存在，无需添加")
            return
        
        print("\n❌ status 字段不存在，准备添加...")
        
        # 4. 添加 status 字段
        print("\n🔧 执行 ALTER TABLE 添加 status 字段...")
        await conn.execute(text("""
            ALTER TABLE conversations 
            ADD COLUMN status VARCHAR(32) NOT NULL DEFAULT 'active';
        """))
        
        print("✅ status 字段添加成功！")
        
        # 5. 创建索引（如果需要）
        print("\n🔧 检查是否需要为 status 字段创建索引...")
        result = await conn.execute(text("""
            SELECT indexname 
            FROM pg_indexes 
            WHERE tablename = 'conversations' 
            AND indexdef LIKE '%status%';
        """))
        status_indexes = result.fetchall()
        
        if not status_indexes:
            print("📝 创建 status 字段索引...")
            await conn.execute(text("""
                CREATE INDEX idx_conversations_status ON conversations(status);
            """))
            print("✅ 索引创建成功！")
        else:
            print(f"✅ status 索引已存在: {[idx[0] for idx in status_indexes]}")
        
        # 6. 验证修改
        print("\n🔍 验证修改后的表结构...")
        result = await conn.execute(text("""
            SELECT column_name, data_type, character_maximum_length, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_schema = 'public' 
            AND table_name = 'conversations'
            ORDER BY ordinal_position;
        """))
        
        columns = result.fetchall()
        print(f"\n📋 更新后字段列表 ({len(columns)} 个):")
        for col in columns:
            nullable = "NULL" if col[3] == 'YES' else "NOT NULL"
            default = f", default={col[4]}" if col[4] else ""
            length = f"({col[2]})" if col[2] else ""
            marker = "✨ [NEW]" if col[0] == 'status' else ""
            print(f"  - {col[0]}: {col[1]}{length} {nullable}{default} {marker}")
        
        print("\n" + "=" * 60)
        print("✅ 数据库迁移完成！")
        print("=" * 60)


async def check_other_tables():
    """检查其他表是否也需要更新"""
    print("\n🔍 检查其他表结构...")
    
    async with engine.begin() as conn:
        # 检查所有表
        result = await conn.execute(text("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
            AND table_type = 'BASE TABLE'
            ORDER BY table_name;
        """))
        
        tables = [row[0] for row in result.fetchall()]
        print(f"\n📋 数据库中的表 ({len(tables)} 个):")
        for table in tables:
            print(f"  - {table}")


if __name__ == "__main__":
    print("🚀 开始数据库迁移...")
    print(f"📡 连接到: {os.getenv('DATABASE_URL', 'Not set')[:50]}...")
    
    asyncio.run(check_and_add_status_column())
    asyncio.run(check_other_tables())
    
    print("\n✅ 所有操作完成！")
