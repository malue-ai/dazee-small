#!/usr/bin/env python3
"""
缓存预加载 API 端到端测试

通过 FastAPI TestClient 验证 HTTP 接口：
1. POST /api/v1/conversations/{id}/preload
"""

import sys
import asyncio
import uuid
from pathlib import Path

# 添加项目根目录到 Python 路径
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from httpx import AsyncClient, ASGITransport
from logger import get_logger
from infra.database.crud.user import get_or_create_user
from infra.database.engine import AsyncSessionLocal
from services.conversation_service import get_conversation_service

logger = get_logger("test_cache_preload_api")


async def ensure_test_user(user_id: str) -> None:
    """确保测试用户存在"""
    async with AsyncSessionLocal() as session:
        await get_or_create_user(session, user_id)


async def test_preload_api():
    """测试预加载 API 接口"""
    print("\n" + "=" * 60)
    print("🚀 缓存预加载 API 测试")
    print("=" * 60)
    
    # 动态导入 app 以避免循环引用
    from main import app
    
    conversation_service = get_conversation_service()
    
    # 创建测试数据
    user_id = f"test_user_{uuid.uuid4().hex[:8]}"
    await ensure_test_user(user_id)
    
    conv = await conversation_service.create_conversation(
        user_id=user_id,
        title="API 预加载测试"
    )
    conv_id = conv.id
    print(f"  ✅ 创建测试对话: {conv_id}")
    
    passed = 0
    failed = 0
    
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as client:
        
        # 测试 1: 正常预加载（冷启动）
        print("\n🧪 测试 1: 正常预加载（冷启动）")
        response = await client.post(
            f"/api/v1/conversations/{conv_id}/preload",
            params={"limit": 50, "force": False}
        )
        
        if response.status_code == 200:
            data = response.json()
            if data["code"] == 200 and data["data"]["conversation_id"] == conv_id:
                print(f"  ✅ 状态码: {response.status_code}")
                print(f"  ✅ cache_hit: {data['data']['cache_hit']}")
                print(f"  ✅ message_count: {data['data']['message_count']}")
                passed += 1
            else:
                print(f"  ❌ 响应格式错误: {data}")
                failed += 1
        else:
            print(f"  ❌ 状态码: {response.status_code}")
            print(f"  ❌ 响应: {response.text}")
            failed += 1
        
        # 测试 2: 缓存命中（重复预加载）
        print("\n🧪 测试 2: 缓存命中（重复预加载）")
        response = await client.post(
            f"/api/v1/conversations/{conv_id}/preload",
            params={"limit": 50, "force": False}
        )
        
        if response.status_code == 200:
            data = response.json()
            if data["data"]["cache_hit"] == True:
                print(f"  ✅ cache_hit: {data['data']['cache_hit']}")
                passed += 1
            else:
                print(f"  ❌ 预期 cache_hit=True，实际: {data['data']['cache_hit']}")
                failed += 1
        else:
            print(f"  ❌ 状态码: {response.status_code}")
            failed += 1
        
        # 测试 3: 强制刷新
        print("\n🧪 测试 3: 强制刷新")
        response = await client.post(
            f"/api/v1/conversations/{conv_id}/preload",
            params={"limit": 50, "force": True}
        )
        
        if response.status_code == 200:
            data = response.json()
            if data["data"]["cache_hit"] == False:
                print(f"  ✅ cache_hit: {data['data']['cache_hit']} (force=True)")
                passed += 1
            else:
                print(f"  ❌ 预期 cache_hit=False，实际: {data['data']['cache_hit']}")
                failed += 1
        else:
            print(f"  ❌ 状态码: {response.status_code}")
            failed += 1
        
        # 测试 4: 不存在的对话
        print("\n🧪 测试 4: 不存在的对话")
        fake_conv_id = "conv_nonexistent_12345"
        response = await client.post(
            f"/api/v1/conversations/{fake_conv_id}/preload",
            params={"limit": 50}
        )
        
        if response.status_code == 404:
            print(f"  ✅ 状态码: 404 (预期)")
            passed += 1
        else:
            print(f"  ❌ 预期 404，实际: {response.status_code}")
            failed += 1
        
        # 测试 5: limit 参数验证
        print("\n🧪 测试 5: limit 参数范围")
        response = await client.post(
            f"/api/v1/conversations/{conv_id}/preload",
            params={"limit": 200}  # 最大 200
        )
        
        if response.status_code == 200:
            data = response.json()
            # effective_limit 应该受 max_context_size 限制
            print(f"  ✅ effective_limit: {data['data']['effective_limit']}")
            passed += 1
        else:
            print(f"  ❌ 状态码: {response.status_code}")
            failed += 1
    
    # 清理
    await conversation_service.delete_conversation(conv_id)
    print(f"\n🧹 清理测试对话: {conv_id}")
    
    # 汇总
    total = passed + failed
    print("\n" + "=" * 60)
    print(f"测试结果: {passed}/{total} 通过")
    print("=" * 60)
    
    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(test_preload_api())
    sys.exit(0 if success else 1)
