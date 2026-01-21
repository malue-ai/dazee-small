"""
直接连接线上 PostgreSQL 数据库，添加 status 字段

执行方式：
    python scripts/add_status_column_direct.py
"""

import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()


async def main():
    # 获取数据库连接字符串
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("❌ 未找到 DATABASE_URL 环境变量！")
        return
    
    # 转换为 asyncpg 格式（移除 +asyncpg）
    db_url = database_url.replace("postgresql+asyncpg://", "postgresql://")
    
    print("=" * 60)
    print("🔍 连接线上 PostgreSQL 数据库...")
    print(f"📡 连接到: {db_url[:50]}...")
    print("=" * 60)
    
    try:
        # 连接数据库
        conn = await asyncpg.connect(db_url)
        print("✅ 数据库连接成功！\n")
        
        # 1. 查看当前表结构
        print("📋 检查 conversations 表结构...")
        columns = await conn.fetch("""
            SELECT column_name, data_type, character_maximum_length, 
                   is_nullable, column_default
            FROM information_schema.columns
            WHERE table_schema = 'public' 
            AND table_name = 'conversations'
            ORDER BY ordinal_position;
        """)
        
        if not columns:
            print("❌ conversations 表不存在！")
            await conn.close()
            return
        
        print(f"\n当前字段列表 ({len(columns)} 个):")
        status_exists = False
        for col in columns:
            nullable = "NULL" if col['is_nullable'] == 'YES' else "NOT NULL"
            default = f", default={col['column_default']}" if col['column_default'] else ""
            length = f"({col['character_maximum_length']})" if col['character_maximum_length'] else ""
            print(f"  - {col['column_name']}: {col['data_type']}{length} {nullable}{default}")
            if col['column_name'] == 'status':
                status_exists = True
        
        # 2. 检查 status 字段是否存在
        if status_exists:
            print("\n✅ status 字段已存在，无需添加")
            await conn.close()
            return
        
        print("\n❌ status 字段不存在，准备添加...\n")
        
        # 3. 添加 status 字段
        print("🔧 执行 ALTER TABLE 添加 status 字段...")
        await conn.execute("""
            ALTER TABLE conversations 
            ADD COLUMN status VARCHAR(32) NOT NULL DEFAULT 'active';
        """)
        print("✅ status 字段添加成功！\n")
        
        # 4. 创建索引
        print("🔧 为 status 字段创建索引...")
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_conversations_status 
            ON conversations(status);
        """)
        print("✅ 索引创建成功！\n")
        
        # 5. 验证修改
        print("🔍 验证修改后的表结构...")
        columns = await conn.fetch("""
            SELECT column_name, data_type, character_maximum_length, 
                   is_nullable, column_default
            FROM information_schema.columns
            WHERE table_schema = 'public' 
            AND table_name = 'conversations'
            ORDER BY ordinal_position;
        """)
        
        print(f"\n更新后字段列表 ({len(columns)} 个):")
        for col in columns:
            nullable = "NULL" if col['is_nullable'] == 'YES' else "NOT NULL"
            default = f", default={col['column_default']}" if col['column_default'] else ""
            length = f"({col['character_maximum_length']})" if col['character_maximum_length'] else ""
            marker = "✨ [NEW]" if col['column_name'] == 'status' else ""
            print(f"  - {col['column_name']}: {col['data_type']}{length} {nullable}{default} {marker}")
        
        # 6. 显示数据库中的所有表
        print("\n" + "=" * 60)
        print("📊 数据库中的所有表:")
        tables = await conn.fetch("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
            AND table_type = 'BASE TABLE'
            ORDER BY table_name;
        """)
        for table in tables:
            print(f"  - {table['table_name']}")
        
        print("\n" + "=" * 60)
        print("✅ 数据库迁移完成！")
        print("=" * 60)
        
        # 关闭连接
        await conn.close()
        
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
