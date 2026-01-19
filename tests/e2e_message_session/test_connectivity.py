"""
服务器连通性测试

测试 PostgreSQL 和 Redis 连接是否正常。
"""

import os
import asyncio
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# 导入测试配置（自动设置环境变量）
# 注意：必须在导入其他模块之前设置环境变量
# 由于 config.py 在同一目录，可以直接导入
import sys
import importlib.util
config_path = Path(__file__).parent / "config.py"
spec = importlib.util.spec_from_file_location("config", config_path)
config = importlib.util.module_from_spec(spec)
spec.loader.exec_module(config)
TestConfig = config.TestConfig

from logger import get_logger
from infra.database.engine import AsyncSessionLocal, init_database
from infra.database.models import User, Conversation, Message
from infra.cache.redis import get_redis_client, create_redis_client
from sqlalchemy import text, inspect

logger = get_logger("test_connectivity")


async def test_postgresql_connection():
    """测试 PostgreSQL 连接"""
    print("\n" + "=" * 60)
    print("📊 PostgreSQL 连接测试")
    print("=" * 60)
    
    try:
        async with AsyncSessionLocal() as session:
            # 1. 基本连接测试
            print("\n1️⃣ 测试基本连接...")
            result = await session.execute(text("SELECT 1"))
            value = result.scalar()
            assert value == 1, "数据库查询失败"
            print("   ✅ 基本连接成功")
            
            # 2. 测试数据库版本
            print("\n2️⃣ 测试数据库版本...")
            result = await session.execute(text("SELECT version()"))
            version = result.scalar()
            print(f"   ✅ PostgreSQL 版本: {version[:50]}...")
            
            # 3. 测试表是否存在
            print("\n3️⃣ 测试表是否存在...")
            # 对于异步引擎，需要使用 sync_engine 或直接查询
            result = await session.execute(
                text("""
                    SELECT table_name 
                    FROM information_schema.tables 
                    WHERE table_schema = 'public'
                """)
            )
            tables = [row[0] for row in result.fetchall()]
            
            required_tables = ["users", "conversations", "messages"]
            for table_name in required_tables:
                if table_name in tables:
                    print(f"   ✅ 表 '{table_name}' 存在")
                else:
                    print(f"   ❌ 表 '{table_name}' 不存在")
                    raise Exception(f"表 '{table_name}' 不存在")
            
            # 4. 测试表结构
            print("\n4️⃣ 测试表结构...")
            for table_name in required_tables:
                result = await session.execute(
                    text("""
                        SELECT column_name, data_type 
                        FROM information_schema.columns 
                        WHERE table_schema = 'public' AND table_name = :table_name
                        LIMIT 3
                    """),
                    {"table_name": table_name}
                )
                columns = result.fetchall()
                print(f"   📋 表 '{table_name}' 有字段（显示前3个）:")
                for col_name, col_type in columns:
                    print(f"      - {col_name}: {col_type}")
            
            print("\n✅ PostgreSQL 连接测试通过")
            return True
            
    except Exception as e:
        print(f"\n❌ PostgreSQL 连接测试失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


async def test_redis_connection():
    """测试 Redis 连接"""
    print("\n" + "=" * 60)
    print("🔴 Redis 连接测试")
    print("=" * 60)
    
    try:
        # 1. 基本连接测试
        print("\n1️⃣ 测试基本连接...")
        redis = await get_redis_client()
        
        if not redis.is_connected:
            print("   ❌ Redis 未连接")
            return False
        
        # 2. 测试 PING 命令
        print("\n2️⃣ 测试 PING 命令...")
        ping_result = await redis.ping()
        if ping_result:
            print("   ✅ PING 成功")
        else:
            print("   ❌ PING 失败")
            return False
        
        # 3. 测试基本操作
        print("\n3️⃣ 测试基本操作...")
        test_key = "test_connectivity_key"
        test_value = "test_value_123"
        
        await redis.set(test_key, test_value, ttl=10)
        retrieved_value = await redis.get(test_key)
        
        if retrieved_value == test_value:
            print("   ✅ SET/GET 操作成功")
        else:
            print(f"   ❌ SET/GET 操作失败: 期望 '{test_value}', 得到 '{retrieved_value}'")
            return False
        
        # 清理测试键
        await redis.delete(test_key)
        
        # 4. 测试 Streams 操作
        print("\n4️⃣ 测试 Streams 操作...")
        if hasattr(redis, '_client') and redis._client:
            stream_key = "test:connectivity:stream"
            
            # XADD
            message_id = await redis._client.xadd(
                stream_key,
                {"test": "value", "timestamp": "1234567890"}
            )
            print(f"   ✅ XADD 成功: message_id={message_id}")
            
            # XREAD
            messages = await redis._client.xread({stream_key: "0"}, count=1)
            if messages:
                print(f"   ✅ XREAD 成功: 读取到 {len(messages)} 条消息")
            else:
                print("   ⚠️ XREAD 未读取到消息")
            
            # 清理测试 Stream
            await redis._client.delete(stream_key)
            print("   ✅ 测试 Stream 已清理")
        else:
            print("   ⚠️ 无法访问底层 Redis 客户端，跳过 Streams 测试")
        
        print("\n✅ Redis 连接测试通过")
        return True
        
    except Exception as e:
        print(f"\n❌ Redis 连接测试失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


async def test_database_initialization():
    """测试数据库初始化"""
    print("\n" + "=" * 60)
    print("🗄️ 数据库初始化测试")
    print("=" * 60)
    
    try:
        print("\n1️⃣ 初始化数据库表...")
        await init_database()
        print("   ✅ 数据库表初始化成功")
        
        # 验证表是否创建
        async with AsyncSessionLocal() as session:
            from sqlalchemy import text
            result = await session.execute(
                text("""
                    SELECT table_name 
                    FROM information_schema.tables 
                    WHERE table_schema = 'public'
                """)
            )
            tables = [row[0] for row in result.fetchall()]
            
            required_tables = ["users", "conversations", "messages"]
            missing_tables = [t for t in required_tables if t not in tables]
            
            if missing_tables:
                print(f"   ⚠️ 缺少表: {missing_tables}")
                print("   💡 提示: 表可能已存在，或需要手动创建")
            else:
                print("   ✅ 所有必需的表都存在")
        
        print("\n✅ 数据库初始化测试通过")
        return True
        
    except Exception as e:
        print(f"\n❌ 数据库初始化测试失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """主测试函数"""
    print("\n" + "=" * 60)
    print("🚀 开始服务器连通性测试")
    print("=" * 60)
    
    results = []
    
    # 1. PostgreSQL 连接测试
    pg_result = await test_postgresql_connection()
    results.append(("PostgreSQL", pg_result))
    
    # 2. Redis 连接测试
    redis_result = await test_redis_connection()
    results.append(("Redis", redis_result))
    
    # 3. 数据库初始化测试
    init_result = await test_database_initialization()
    results.append(("Database Initialization", init_result))
    
    # 汇总结果
    print("\n" + "=" * 60)
    print("📊 测试结果汇总")
    print("=" * 60)
    
    for name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{name:30s} {status}")
    
    all_passed = all(result for _, result in results)
    
    if all_passed:
        print("\n🎉 所有连通性测试通过！")
        return 0
    else:
        print("\n⚠️ 部分测试失败，请检查连接配置")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
