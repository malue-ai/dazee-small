"""
数据库索引优化脚本

添加消息会话管理框架所需的复合索引，优化分页查询性能。

使用方法：
    python scripts/add_message_indexes.py
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

# 判断是否为 SQLite
IS_SQLITE = DATABASE_URL.startswith("sqlite")

# 创建数据库引擎
engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
)

# 索引定义
INDEXES = [
    {
        "name": "idx_messages_conv_created",
        "table": "messages",
        "columns": ["conversation_id", "created_at ASC"],
        "description": "消息表复合索引（分页查询必需）"
    },
    {
        "name": "idx_conversations_user_updated",
        "table": "conversations",
        "columns": ["user_id", "updated_at DESC"],
        "description": "对话表复合索引（对话列表查询优化）"
    },
    {
        "name": "idx_messages_status",
        "table": "messages",
        "columns": ["status"],
        "description": "消息表 status 索引（查询流式消息）",
        "where_clause": "WHERE status = 'streaming'" if not IS_SQLITE else None
    }
]


async def create_index(index_def: dict) -> bool:
    """
    创建索引
    
    Args:
        index_def: 索引定义字典
        
    Returns:
        是否创建成功
    """
    name = index_def["name"]
    table = index_def["table"]
    columns = ", ".join(index_def["columns"])
    where_clause = index_def.get("where_clause", "")
    
    if IS_SQLITE:
        # SQLite 不支持 IF NOT EXISTS，需要先检查
        sql = f"CREATE INDEX IF NOT EXISTS {name} ON {table}({columns})"
    else:
        # PostgreSQL 支持部分索引
        sql = f"CREATE INDEX IF NOT EXISTS {name} ON {table}({columns}) {where_clause}"
    
    try:
        async with engine.begin() as conn:
            await conn.execute(text(sql))
        print(f"✅ 索引创建成功: {name} ({index_def['description']})")
        return True
    except Exception as e:
        print(f"❌ 索引创建失败: {name}, error={str(e)}")
        return False


async def check_index_exists(index_name: str) -> bool:
    """
    检查索引是否存在
    
    Args:
        index_name: 索引名称
        
    Returns:
        是否存在
    """
    try:
        if IS_SQLITE:
            # SQLite 查询索引
            sql = """
                SELECT name FROM sqlite_master 
                WHERE type='index' AND name=:index_name
            """
        else:
            # PostgreSQL 查询索引
            sql = """
                SELECT indexname FROM pg_indexes 
                WHERE indexname = :index_name
            """
        
        async with engine.begin() as conn:
            result = await conn.execute(text(sql), {"index_name": index_name})
            return result.fetchone() is not None
    except Exception as e:
        print(f"⚠️ 检查索引失败: {index_name}, error={str(e)}")
        return False


async def main():
    """主函数"""
    print("=" * 60)
    print("📊 数据库索引优化")
    print("=" * 60)
    print(f"数据库类型: {'SQLite' if IS_SQLITE else 'PostgreSQL'}")
    print("")
    
    # 检查现有索引
    print("🔍 检查现有索引...")
    existing_indices = []
    for index_def in INDEXES:
        exists = await check_index_exists(index_def["name"])
        if exists:
            existing_indices.append(index_def["name"])
            print(f"  ✅ {index_def['name']} 已存在")
        else:
            print(f"  ⚠️ {index_def['name']} 不存在")
    print("")
    
    # 创建缺失的索引
    print("🔨 创建缺失的索引...")
    success_count = 0
    for index_def in INDEXES:
        if index_def["name"] not in existing_indices:
            success = await create_index(index_def)
            if success:
                success_count += 1
        else:
            print(f"⏭️  跳过已存在的索引: {index_def['name']}")
    
    print("")
    print("=" * 60)
    print(f"✅ 完成: 成功创建 {success_count} 个索引")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
