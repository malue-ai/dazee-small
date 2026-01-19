"""
验证数据库索引

检查索引是否创建成功，并显示索引信息。
"""

import asyncio
import os
import sys
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


async def verify_indexes():
    """验证索引"""
    print("=" * 60)
    print("🔍 验证数据库索引")
    print("=" * 60)
    print(f"数据库类型: {'SQLite' if IS_SQLITE else 'PostgreSQL'}")
    print("")
    
    if IS_SQLITE:
        sql = """
            SELECT name, tbl_name, sql 
            FROM sqlite_master 
            WHERE type='index' AND tbl_name IN ('messages', 'conversations')
            ORDER BY tbl_name, name
        """
    else:
        sql = """
            SELECT 
                indexname,
                tablename,
                indexdef
            FROM pg_indexes 
            WHERE tablename IN ('messages', 'conversations')
            ORDER BY tablename, indexname
        """
    
    try:
        async with engine.begin() as conn:
            result = await conn.execute(text(sql))
            rows = result.fetchall()
            
            if not rows:
                print("⚠️ 未找到索引")
                return
            
            print(f"📊 找到 {len(rows)} 个索引：\n")
            
            current_table = None
            for row in rows:
                if IS_SQLITE:
                    index_name, table_name, index_sql = row
                else:
                    index_name, table_name, index_sql = row
                
                if current_table != table_name:
                    if current_table is not None:
                        print("")
                    print(f"📋 表: {table_name}")
                    current_table = table_name
                
                # 检查是否为关键索引
                is_key = index_name in [
                    "idx_messages_conv_created",
                    "idx_conversations_user_updated",
                    "idx_messages_status"
                ]
                marker = "⭐" if is_key else "  "
                
                print(f"{marker} {index_name}")
                if index_sql:
                    # 显示索引定义的前 80 个字符
                    sql_preview = index_sql[:80] + "..." if len(index_sql) > 80 else index_sql
                    print(f"   {sql_preview}")
            
            print("")
            print("=" * 60)
            print("✅ 索引验证完成")
            print("=" * 60)
            
    except Exception as e:
        print(f"❌ 验证失败: {str(e)}", exc_info=True)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(verify_indexes())
