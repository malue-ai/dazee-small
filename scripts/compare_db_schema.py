#!/usr/bin/env python3
"""
对比 staging 和 production 数据库表结构
"""

import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

# 数据库连接（从 .env 文件复制）
STAGING_URL = "postgresql+asyncpg://postgres:924Ff8O5kfEWOvzj3nN1ricrWVTIHSy8@zen0-backend-staging-postgresql.cz0gu26m8g6c.ap-southeast-1.rds.amazonaws.com:5432/zen0_staging_pg"
PRODUCTION_URL = "postgresql+asyncpg://postgres:hwcUu5D19KByzbKagzI0V4KoSzCwZy4p@zen0-backend-production-postgresql.cz0gu26m8g6c.ap-southeast-1.rds.amazonaws.com:5432/zen0_production_pg"


async def get_tables(engine) -> list[str]:
    """获取所有表名"""
    query = text("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_type = 'BASE TABLE'
        ORDER BY table_name
    """)
    async with engine.connect() as conn:
        result = await conn.execute(query)
        return [row[0] for row in result.fetchall()]


async def get_columns(engine, table_name: str) -> list[dict]:
    """获取表的所有列信息"""
    query = text("""
        SELECT 
            column_name,
            data_type,
            is_nullable,
            column_default,
            character_maximum_length,
            numeric_precision
        FROM information_schema.columns
        WHERE table_schema = 'public'
        AND table_name = :table_name
        ORDER BY ordinal_position
    """)
    async with engine.connect() as conn:
        result = await conn.execute(query, {"table_name": table_name})
        return [
            {
                "name": row[0],
                "type": row[1],
                "nullable": row[2],
                "default": row[3],
                "max_length": row[4],
                "precision": row[5],
            }
            for row in result.fetchall()
        ]


async def get_indexes(engine, table_name: str) -> list[dict]:
    """获取表的所有索引"""
    query = text("""
        SELECT
            indexname,
            indexdef
        FROM pg_indexes
        WHERE schemaname = 'public'
        AND tablename = :table_name
        ORDER BY indexname
    """)
    async with engine.connect() as conn:
        result = await conn.execute(query, {"table_name": table_name})
        return [{"name": row[0], "definition": row[1]} for row in result.fetchall()]


def format_column(col: dict) -> str:
    """格式化列信息"""
    type_str = col["type"]
    if col["max_length"]:
        type_str += f"({col['max_length']})"
    nullable = "NULL" if col["nullable"] == "YES" else "NOT NULL"
    return f"{col['name']}: {type_str} {nullable}"


async def compare_schemas():
    """对比两个数据库的 schema"""
    staging_engine = create_async_engine(STAGING_URL)
    production_engine = create_async_engine(PRODUCTION_URL)

    print("=" * 80)
    print("数据库表结构对比: STAGING vs PRODUCTION")
    print("=" * 80)

    # 获取表列表
    staging_tables = set(await get_tables(staging_engine))
    production_tables = set(await get_tables(production_engine))

    print("\n📋 表列表对比:")
    print("-" * 40)

    # 只在 staging 存在的表
    only_staging = staging_tables - production_tables
    if only_staging:
        print(f"\n⚠️  仅 STAGING 存在的表: {only_staging}")

    # 只在 production 存在的表
    only_production = production_tables - staging_tables
    if only_production:
        print(f"\n⚠️  仅 PRODUCTION 存在的表: {only_production}")

    # 两边都有的表
    common_tables = staging_tables & production_tables
    print(f"\n✅ 共同存在的表: {sorted(common_tables)}")

    # 对比每个共同表的列
    print("\n" + "=" * 80)
    print("📊 表结构详细对比:")
    print("=" * 80)

    for table in sorted(common_tables):
        staging_cols = await get_columns(staging_engine, table)
        production_cols = await get_columns(production_engine, table)

        staging_col_names = {c["name"]: c for c in staging_cols}
        production_col_names = {c["name"]: c for c in production_cols}

        has_diff = False
        diff_output = []

        # 只在 staging 的列
        only_in_staging = set(staging_col_names.keys()) - set(production_col_names.keys())
        if only_in_staging:
            has_diff = True
            for col_name in only_in_staging:
                diff_output.append(f"  ➕ STAGING 独有列: {format_column(staging_col_names[col_name])}")

        # 只在 production 的列
        only_in_production = set(production_col_names.keys()) - set(staging_col_names.keys())
        if only_in_production:
            has_diff = True
            for col_name in only_in_production:
                diff_output.append(f"  ➕ PRODUCTION 独有列: {format_column(production_col_names[col_name])}")

        # 类型不一致的列
        common_cols = set(staging_col_names.keys()) & set(production_col_names.keys())
        for col_name in common_cols:
            s_col = staging_col_names[col_name]
            p_col = production_col_names[col_name]
            
            diffs = []
            if s_col["type"] != p_col["type"]:
                diffs.append(f"类型: {s_col['type']} vs {p_col['type']}")
            if s_col["nullable"] != p_col["nullable"]:
                diffs.append(f"nullable: {s_col['nullable']} vs {p_col['nullable']}")
            if s_col["max_length"] != p_col["max_length"]:
                diffs.append(f"长度: {s_col['max_length']} vs {p_col['max_length']}")
            
            if diffs:
                has_diff = True
                diff_output.append(f"  ⚠️  列 {col_name} 不一致: {', '.join(diffs)}")

        if has_diff:
            print(f"\n❌ 表 {table} 有差异:")
            for line in diff_output:
                print(line)
        else:
            print(f"\n✅ 表 {table} 结构一致")

    # 对比索引
    print("\n" + "=" * 80)
    print("🔍 索引对比:")
    print("=" * 80)

    for table in sorted(common_tables):
        staging_indexes = await get_indexes(staging_engine, table)
        production_indexes = await get_indexes(production_engine, table)

        staging_idx_names = {i["name"] for i in staging_indexes}
        production_idx_names = {i["name"] for i in production_indexes}

        only_in_staging = staging_idx_names - production_idx_names
        only_in_production = production_idx_names - staging_idx_names

        if only_in_staging or only_in_production:
            print(f"\n表 {table}:")
            if only_in_staging:
                print(f"  ➕ STAGING 独有索引: {only_in_staging}")
            if only_in_production:
                print(f"  ➕ PRODUCTION 独有索引: {only_in_production}")

    await staging_engine.dispose()
    await production_engine.dispose()

    print("\n" + "=" * 80)
    print("对比完成")
    print("=" * 80)


async def get_table_ddl(table_name: str):
    """获取 staging 中表的完整结构"""
    staging_engine = create_async_engine(STAGING_URL)
    
    cols = await get_columns(staging_engine, table_name)
    indexes = await get_indexes(staging_engine, table_name)
    
    print(f"\n表 {table_name} 结构:")
    print("-" * 40)
    for col in cols:
        print(f"  {format_column(col)}")
    
    print(f"\n索引:")
    for idx in indexes:
        print(f"  {idx['name']}: {idx['definition']}")
    
    await staging_engine.dispose()


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--table":
        asyncio.run(get_table_ddl(sys.argv[2]))
    else:
        asyncio.run(compare_schemas())
