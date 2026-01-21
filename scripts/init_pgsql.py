"""
PostgreSQL 数据库初始化脚本

用法：
    # 设置环境变量
    export DATABASE_URL="postgresql+asyncpg://postgres:924Ff8O5kfEWOvzj3nN1ricrWVTIHSy8@zen0-backend-staging-postgresql.cz0gu26m8g6c.ap-southeast-1.rds.amazonaws.com:5432/zen0_staging_pg"
    
    # 运行脚本
    python scripts/init_pgsql.py
    
    # 或者带参数运行（会删除现有表）
    python scripts/init_pgsql.py --drop-all
"""

import asyncio
import argparse
import sys
import os

# 添加项目根目录到 path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def init_database(drop_all: bool = False):
    """初始化数据库"""
    from infra.database.engine import engine, DATABASE_URL
    from infra.database.base import Base
    
    # 导入所有模型（确保它们被注册到 Base.metadata）
    from infra.database.models import (
        User, Conversation, Message, 
        Knowledge, File, Sandbox
    )
    
    print(f"📦 数据库连接: {DATABASE_URL[:50]}...")
    print(f"📋 已注册的表: {list(Base.metadata.tables.keys())}")
    
    async with engine.begin() as conn:
        if drop_all:
            print("⚠️  删除所有表...")
            await conn.run_sync(Base.metadata.drop_all)
            print("✅ 表已删除")
        
        print("🔧 创建所有表...")
        await conn.run_sync(Base.metadata.create_all)
        print("✅ 表已创建")
    
    # 验证表结构
    print("\n📊 验证表结构:")
    async with engine.connect() as conn:
        from sqlalchemy import text
        
        # 检查 messages 表的 content 和 metadata 列类型
        result = await conn.execute(text("""
            SELECT column_name, data_type, udt_name 
            FROM information_schema.columns 
            WHERE table_name = 'messages' 
            AND column_name IN ('content', 'metadata')
        """))
        rows = result.fetchall()
        
        for row in rows:
            print(f"  - messages.{row[0]}: {row[2]}")
        
        # 检查 conversations 表的 metadata 列类型
        result = await conn.execute(text("""
            SELECT column_name, data_type, udt_name 
            FROM information_schema.columns 
            WHERE table_name = 'conversations' 
            AND column_name = 'metadata'
        """))
        rows = result.fetchall()
        
        for row in rows:
            print(f"  - conversations.{row[0]}: {row[2]}")
    
    print("\n✅ 数据库初始化完成！")


def main():
    parser = argparse.ArgumentParser(description="初始化 PostgreSQL 数据库")
    parser.add_argument(
        "--drop-all", 
        action="store_true",
        help="删除所有表后重建（会丢失所有数据！）"
    )
    args = parser.parse_args()
    
    if args.drop_all:
        confirm = input("⚠️  确定要删除所有表吗？输入 'yes' 确认: ")
        if confirm.lower() != 'yes':
            print("已取消")
            return
    
    asyncio.run(init_database(drop_all=args.drop_all))


if __name__ == "__main__":
    main()
