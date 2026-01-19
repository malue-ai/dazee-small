"""
Redis 连接诊断脚本

专门用于诊断和修复 Redis (MemoryDB) TLS 连接问题。
"""

import os
import asyncio
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# 设置环境变量
os.environ["REDIS_URL"] = (
    "rediss://agentuser:y05EtW8goYEBOpMYB52lPh8qHnRZggcc@"
    "clustercfg.zen0-backend-staging-memorydb.w9tdej.memorydb.ap-southeast-1.amazonaws.com:6379"
)

from logger import get_logger
import ssl

logger = get_logger("test_redis_diagnostic")


async def test_redis_connection_methods():
    """测试多种 Redis 连接方式"""
    print("\n" + "=" * 60)
    print("🔍 Redis 连接诊断测试")
    print("=" * 60)
    
    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        print("❌ REDIS_URL 环境变量未设置")
        return
    
    print(f"\n📋 Redis URL: {redis_url[:50]}...")
    
    # 解析 URL
    import re
    match = re.match(r'rediss://([^:]+):([^@]+)@([^:]+):(\d+)', redis_url)
    if not match:
        print("❌ Redis URL 格式不正确")
        return
    
    username, password, host, port = match.groups()
    port = int(port)
    
    print(f"   用户名: {username}")
    print(f"   主机: {host}")
    print(f"   端口: {port}")
    print(f"   TLS: 启用")
    
    # 测试方法 1: from_url 自动识别
    print("\n" + "-" * 60)
    print("方法 1: from_url 自动识别 rediss://")
    print("-" * 60)
    
    try:
        import redis.asyncio as aioredis
        # redis-py 7.x: rediss:// 自动启用 TLS，不需要 ssl=True
        client1 = aioredis.from_url(
            redis_url,
            decode_responses=False,
            socket_connect_timeout=30,
            ssl_cert_reqs=ssl.CERT_NONE,
            ssl_check_hostname=False
        )
        result = await client1.ping()
        print(f"   ✅ 连接成功: PING = {result}")
        await client1.close()
        return True
    except Exception as e:
        print(f"   ❌ 连接失败: {str(e)}")
        import traceback
        traceback.print_exc()
    
    # 测试方法 2: 使用 Redis 构造函数
    print("\n" + "-" * 60)
    print("方法 2: 使用 Redis 构造函数")
    print("-" * 60)
    
    try:
        import redis.asyncio as aioredis
        # redis-py 7.x: 需要明确启用 TLS
        client2 = aioredis.Redis(
            host=host,
            port=port,
            username=username,
            password=password,
            decode_responses=False,
            socket_connect_timeout=30,
            ssl=True,  # Redis 构造函数需要显式设置
            ssl_cert_reqs=ssl.CERT_NONE,
            ssl_check_hostname=False
        )
        result = await client2.ping()
        print(f"   ✅ 连接成功: PING = {result}")
        await client2.close()
        return True
    except Exception as e:
        print(f"   ❌ 连接失败: {str(e)}")
        import traceback
        traceback.print_exc()
    
    # 测试方法 3: 使用 ConnectionPool
    print("\n" + "-" * 60)
    print("方法 3: 使用 ConnectionPool")
    print("-" * 60)
    
    try:
        import redis.asyncio as aioredis
        # redis-py 7.x: from_url 自动识别 rediss://
        pool = aioredis.ConnectionPool.from_url(
            redis_url,
            decode_responses=False,
            socket_connect_timeout=30,
            ssl_cert_reqs=ssl.CERT_NONE,
            ssl_check_hostname=False
        )
        client3 = aioredis.Redis(connection_pool=pool)
        result = await client3.ping()
        print(f"   ✅ 连接成功: PING = {result}")
        await client3.close()
        await pool.aclose()
        return True
    except Exception as e:
        print(f"   ❌ 连接失败: {str(e)}")
        import traceback
        traceback.print_exc()
    
    # 网络连通性测试
    print("\n" + "-" * 60)
    print("网络连通性测试")
    print("-" * 60)
    
    try:
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10)
        result = sock.connect_ex((host, port))
        sock.close()
        if result == 0:
            print(f"   ✅ TCP 连接成功: {host}:{port}")
        else:
            print(f"   ❌ TCP 连接失败: {host}:{port} (错误码: {result})")
            print("   💡 提示: 可能是安全组或网络配置问题")
    except Exception as e:
        print(f"   ❌ 网络测试失败: {str(e)}")
        print("   💡 提示: 可能是 DNS 解析或网络配置问题")
    
    return False


async def main():
    """主函数"""
    print("\n" + "=" * 60)
    print("🚀 Redis 连接诊断")
    print("=" * 60)
    
    success = await test_redis_connection_methods()
    
    if success:
        print("\n✅ Redis 连接诊断成功！")
        return 0
    else:
        print("\n❌ Redis 连接诊断失败")
        print("\n💡 排查建议:")
        print("   1. 检查网络连接（VPN、安全组配置）")
        print("   2. 验证 MemoryDB 集群状态和 endpoint")
        print("   3. 检查用户名和密码是否正确")
        print("   4. 确认 TLS/SSL 配置是否正确")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
