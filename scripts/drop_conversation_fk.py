"""
删除 conversations 表的 user_id 外键约束

支持多用户访问同一个对话
"""

import asyncio
import os
import sys

# 添加项目根目录到 path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 加载 .env 环境变量
from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import text
from infra.database import AsyncSessionLocal


async def drop_foreign_key():
    """删除 conversations.user_id 的外键约束"""
    
    async with AsyncSessionLocal() as session:
        # 1. 先查询外键名称
        query_fk = text("""
            SELECT conname 
            FROM pg_constraint 
            WHERE conrelid = 'conversations'::regclass 
              AND contype = 'f'
              AND conname LIKE '%user_id%'
        """)
        
        result = await session.execute(query_fk)
        fk_names = [row[0] for row in result.fetchall()]
        
        if not fk_names:
            print("✅ 没有找到 user_id 相关的外键约束，可能已经删除")
            return
        
        print(f"📋 找到外键约束: {fk_names}")
        
        # 2. 删除外键
        for fk_name in fk_names:
            drop_sql = text(f"ALTER TABLE conversations DROP CONSTRAINT IF EXISTS {fk_name}")
            await session.execute(drop_sql)
            print(f"✅ 已删除外键: {fk_name}")
        
        await session.commit()
        print("🎉 外键删除完成！")


async def verify():
    """验证外键是否已删除"""
    
    async with AsyncSessionLocal() as session:
        query = text("""
            SELECT conname, contype
            FROM pg_constraint 
            WHERE conrelid = 'conversations'::regclass
        """)
        
        result = await session.execute(query)
        constraints = result.fetchall()
        
        print("\n📋 conversations 表当前的约束:")
        for name, ctype in constraints:
            type_map = {'p': '主键', 'f': '外键', 'u': '唯一', 'c': '检查'}
            print(f"  - {name} ({type_map.get(ctype, ctype)})")
        
        # 检查是否还有 user_id 外键
        fk_exists = any(c == 'f' and 'user_id' in name for name, c in constraints)
        if fk_exists:
            print("\n⚠️ 仍然存在 user_id 外键")
        else:
            print("\n✅ 没有 user_id 外键，验证通过！")


if __name__ == "__main__":
    print("=" * 50)
    print("删除 conversations.user_id 外键约束")
    print("=" * 50)
    
    asyncio.run(drop_foreign_key())
    asyncio.run(verify())
