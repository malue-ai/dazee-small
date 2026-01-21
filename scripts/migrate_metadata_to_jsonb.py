#!/usr/bin/env python3
"""
数据库迁移脚本：将 metadata 字段从 TEXT 转换为 JSONB

问题：线上数据库的 metadata 字段是 TEXT 类型，存储的是 JSON 字符串
目标：将其转换为 JSONB 类型，让 SQLAlchemy 自动序列化/反序列化

使用方法：
    python scripts/migrate_metadata_to_jsonb.py --check     # 检查当前状态
    python scripts/migrate_metadata_to_jsonb.py --migrate   # 执行迁移
    python scripts/migrate_metadata_to_jsonb.py --rollback  # 回滚（如果需要）
"""

import asyncio
import argparse
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 加载 .env 文件
from dotenv import load_dotenv
env_path = project_root / ".env"
load_dotenv(env_path)

from sqlalchemy import text
from infra.database import AsyncSessionLocal


async def check_schema():
    """检查当前数据库表结构"""
    print("=" * 60)
    print("检查数据库表结构")
    print("=" * 60)
    
    # 需要检查的表和字段（期望类型）
    jsonb_fields = [
        ("users", "metadata", "jsonb"),
        ("conversations", "metadata", "jsonb"),
        ("messages", "metadata", "jsonb"),
        ("messages", "content", "jsonb"),
    ]
    
    # 这些表使用 TEXT 存储 JSON（设计如此，不需要迁移）
    text_json_fields = [
        ("agent_instances", "metadata"),
        ("skill_instances", "metadata"),
        ("mcp_servers", "metadata"),
        ("mcp_servers", "registered_tools"),
        ("sandboxes", "metadata"),
        ("knowledge", "metadata"),
    ]
    
    async with AsyncSessionLocal() as session:
        print("\n【需要 JSONB 类型的字段】")
        for table, column, expected in jsonb_fields:
            result = await session.execute(text(f"""
                SELECT column_name, data_type, udt_name
                FROM information_schema.columns
                WHERE table_name = '{table}' AND column_name = '{column}';
            """))
            row = result.fetchone()
            if row:
                status = "✅" if row.udt_name == expected else "⚠️  需要迁移"
                print(f"  {table}.{column}: {row.udt_name} {status}")
            else:
                print(f"  {table}.{column}: ❓ 字段不存在")
        
        print("\n【TEXT 类型存储 JSON 的字段（设计如此）】")
        for table, column in text_json_fields:
            result = await session.execute(text(f"""
                SELECT column_name, data_type, udt_name
                FROM information_schema.columns
                WHERE table_name = '{table}' AND column_name = '{column}';
            """))
            row = result.fetchone()
            if row:
                print(f"  {table}.{column}: {row.udt_name}")
            else:
                print(f"  {table}.{column}: ❓ 字段/表不存在")
        
        # 检查示例数据
        print("\n" + "=" * 60)
        print("检查示例数据")
        print("=" * 60)
        
        for table, column, _ in jsonb_fields[:2]:  # 只检查前两个
            try:
                result = await session.execute(text(f"""
                    SELECT id, pg_typeof({column}) as type, {column}
                    FROM {table}
                    LIMIT 2;
                """))
                rows = result.fetchall()
                print(f"\n{table} 示例数据 ({len(rows)} 行):")
                for row in rows:
                    print(f"  id={str(row.id)[:16]}...")
                    print(f"    pg_typeof: {row.type}")
                    print(f"    python type: {type(row[2])}")
            except Exception as e:
                print(f"\n{table}: 查询失败 - {e}")


async def migrate_to_jsonb():
    """执行迁移：将 TEXT 类型的 metadata 转换为 JSONB"""
    print("=" * 60)
    print("开始迁移 metadata 字段到 JSONB 类型")
    print("=" * 60)
    
    # 需要迁移的字段列表：(表名, 字段名, 默认值)
    migrations = [
        ("users", "metadata", "'{}'::jsonb"),
        ("conversations", "metadata", "'{}'::jsonb"),
        ("messages", "metadata", "'{}'::jsonb"),
        ("messages", "content", "'[]'::jsonb"),
    ]
    
    async with AsyncSessionLocal() as session:
        step = 1
        for table, column, default_value in migrations:
            # 检查字段类型
            result = await session.execute(text(f"""
                SELECT udt_name FROM information_schema.columns
                WHERE table_name = '{table}' AND column_name = '{column}';
            """))
            row = result.fetchone()
            
            if not row:
                print(f"\n{step}. {table}.{column} 字段不存在，跳过")
                step += 1
                continue
            
            if row.udt_name != 'jsonb':
                print(f"\n{step}. 迁移 {table}.{column}...")
                try:
                    # 转换为 JSONB
                    await session.execute(text(f"""
                        ALTER TABLE {table} 
                        ALTER COLUMN {column} TYPE JSONB 
                        USING COALESCE({column}::jsonb, {default_value});
                    """))
                    await session.commit()
                    print(f"   ✅ {table}.{column} 迁移成功")
                except Exception as e:
                    await session.rollback()
                    print(f"   ❌ 迁移失败: {e}")
                    step += 1
                    continue
            else:
                print(f"\n{step}. {table}.{column} 已经是 JSONB，跳过")
            
            step += 1
        
        # 设置默认值
        print(f"\n{step}. 设置 JSONB 字段的默认值...")
        for table, column, default_value in migrations:
            try:
                await session.execute(text(f"""
                    ALTER TABLE {table} 
                    ALTER COLUMN {column} SET DEFAULT {default_value};
                """))
                await session.commit()
            except Exception as e:
                await session.rollback()
                # 忽略已存在的默认值错误
        print("   ✅ 默认值设置完成")
        
        print("\n" + "=" * 60)
        print("迁移完成！")
        print("=" * 60)
        return True


async def rollback():
    """回滚：将 JSONB 转回 TEXT（紧急情况使用）"""
    print("=" * 60)
    print("⚠️  警告：即将回滚 JSONB 到 TEXT 类型")
    print("=" * 60)
    
    confirm = input("确认回滚？这将丢失 JSONB 的优势 (yes/no): ")
    if confirm.lower() != 'yes':
        print("已取消")
        return
    
    async with AsyncSessionLocal() as session:
        try:
            await session.execute(text("""
                ALTER TABLE conversations 
                ALTER COLUMN metadata TYPE TEXT 
                USING metadata::text;
            """))
            await session.execute(text("""
                ALTER TABLE messages 
                ALTER COLUMN metadata TYPE TEXT 
                USING metadata::text;
            """))
            await session.execute(text("""
                ALTER TABLE messages 
                ALTER COLUMN content TYPE TEXT 
                USING content::text;
            """))
            await session.commit()
            print("✅ 回滚成功")
        except Exception as e:
            await session.rollback()
            print(f"❌ 回滚失败: {e}")


def main():
    parser = argparse.ArgumentParser(description='迁移 metadata 字段到 JSONB 类型')
    parser.add_argument('--check', action='store_true', help='检查当前状态')
    parser.add_argument('--migrate', action='store_true', help='执行迁移')
    parser.add_argument('--rollback', action='store_true', help='回滚到 TEXT 类型')
    
    args = parser.parse_args()
    
    if args.check:
        asyncio.run(check_schema())
    elif args.migrate:
        asyncio.run(migrate_to_jsonb())
    elif args.rollback:
        asyncio.run(rollback())
    else:
        # 默认显示帮助
        parser.print_help()
        print("\n示例：")
        print("  python scripts/migrate_metadata_to_jsonb.py --check     # 检查当前状态")
        print("  python scripts/migrate_metadata_to_jsonb.py --migrate   # 执行迁移")


if __name__ == "__main__":
    main()
