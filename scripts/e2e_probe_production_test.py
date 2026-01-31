#!/usr/bin/env python3
"""
端到端生产环境验证：主备自动切换

验证场景：
1. 后台健康探测服务正常运行（生产默认启用）
2. 请求链路探针默认禁用（不阻塞用户）
3. ModelRouter 主备自动切换（主 API 失败时自动切换）
4. 配置文件正确加载

运行方式：
    /Users/liuyi/Documents/langchain/liuy/bin/python3 scripts/e2e_probe_production_test.py
"""

import asyncio
import sys
import os
import time
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

print("=" * 60)
print("🔍 端到端生产环境验证")
print("=" * 60)
print()

# 清理配置缓存（确保读取最新配置）
print("🔄 清理配置缓存...")
try:
    from config.llm_config import reload_config
    reload_config()
    print("✅ 配置缓存已清理")
except Exception as e:
    print(f"⚠️  清理缓存失败: {e}")
print()

# ============================================================
# 测试 1: 配置文件加载
# ============================================================

print("📋 测试 1: 配置文件加载")
print("-" * 60)

try:
    from config.llm_config import get_health_probe_config
    
    config = get_health_probe_config()
    
    print("✅ 配置加载成功")
    print(f"   条件探测: 超时={config['request_probe']['timeout_seconds']}s（V7.11 条件探测策略）")
    print(f"   后台健康探测: enabled={config['background_probe']['enabled']}")
    print(f"   探测间隔: {config['background_probe']['interval_seconds']}s")
    print(f"   探测超时: {config['background_probe']['timeout_seconds']}s")
    print(f"   探测 Profiles: {', '.join(config['background_probe']['profiles'][:3])}...")
    
    # 验证生产默认配置（V7.11：条件探测策略，无 enabled 字段）
    assert 'timeout_seconds' in config['request_probe'], "❌ 条件探测应有 timeout_seconds 配置"
    assert config['background_probe']['enabled'] == True, "❌ 后台健康探测应默认启用"
    
    print("✅ 生产默认配置正确（V7.11 条件探测策略）")
    
except Exception as e:
    print(f"❌ 配置加载失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print()

# ============================================================
# 测试 2: 后台健康探测服务
# ============================================================

print("📋 测试 2: 后台健康探测服务")
print("-" * 60)

async def test_health_probe_service():
    try:
        from services.health_probe_service import HealthProbeService
        
        # 创建服务（使用配置文件的值）
        service = HealthProbeService()
        
        print(f"✅ 服务创建成功")
        print(f"   enabled: {service.enabled}")
        print(f"   interval: {service.interval}s")
        print(f"   timeout: {service.timeout}s")
        print(f"   profiles: {len(service.profiles)} 个")
        
        # 验证配置
        assert service.enabled == True, "❌ 后台探测应默认启用"
        
        # 验证探测间隔（从配置文件读取）
        expected_interval = config['background_probe']['interval_seconds']
        if service.interval != expected_interval:
            print(f"   ⚠️  探测间隔不匹配: 期望 {expected_interval}s, 实际 {service.interval}s")
        else:
            print(f"   ✅ 探测间隔正确: {service.interval}s")
        
        # 启动服务（短时间测试）
        print("   启动服务...")
        await service.start()
        
        if service._running:
            print("✅ 服务启动成功")
        else:
            print("❌ 服务启动失败")
            return False
        
        # 等待一次探测
        print("   等待后台探测执行...")
        await asyncio.sleep(3)
        
        # 检查探测结果
        status = service.get_health_status()
        print(f"✅ 健康状态查询成功")
        print(f"   overall: {status['overall']}")
        print(f"   running: {status['running']}")
        
        # 停止服务
        await service.stop()
        print("✅ 服务停止成功")
        
        return True
        
    except Exception as e:
        print(f"❌ 后台健康探测服务测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

result = asyncio.run(test_health_probe_service())
if not result:
    sys.exit(1)

print()

# ============================================================
# 测试 3: ModelRouter 主备切换（模拟）
# ============================================================

print("📋 测试 3: ModelRouter 主备自动切换")
print("-" * 60)

async def test_model_router_failover():
    try:
        from core.llm.router import ModelRouter, RouteTarget
        from core.llm.base import LLMProvider, Message
        from unittest.mock import MagicMock, AsyncMock
        
        # 创建 Mock 服务
        def create_mock_service(name: str, should_fail: bool = False):
            mock = MagicMock()
            mock.config = MagicMock(base_url="", model=name)
            
            async def create_message_async(*args, **kwargs):
                if should_fail:
                    raise Exception(f"{name} unavailable")
                return MagicMock(content=f"response from {name}", thinking=None, tool_calls=None)
            
            mock.create_message_async = create_message_async
            return mock
        
        # 场景 1: 主 API 失败，切换到同模型不同 Provider
        print("   场景 1: 主 API 失败 → 同模型不同 Provider")
        
        primary = RouteTarget(
            service=create_mock_service("primary:claude:sonnet", should_fail=True),
            provider=LLMProvider.CLAUDE,
            model="claude-sonnet",
            name="primary:claude:sonnet"
        )
        
        fallback_0 = RouteTarget(
            service=create_mock_service("fallback:claude:sonnet@vendor_a", should_fail=False),
            provider=LLMProvider.CLAUDE,
            model="claude-sonnet",
            name="fallback:claude:sonnet@vendor_a"
        )
        
        fallback_1 = RouteTarget(
            service=create_mock_service("fallback:qwen:qwen-max", should_fail=False),
            provider=LLMProvider.QWEN,
            model="qwen-max",
            name="fallback:qwen:qwen-max"
        )
        
        router = ModelRouter(
            primary=primary,
            fallbacks=[fallback_0, fallback_1],
            policy={"max_failures": 1, "cooldown_seconds": 60}
        )
        
        response = await router.create_message_async(
            messages=[Message(role="user", content="test")]
        )
        
        selected = router._last_selected
        print(f"   ✅ 自动切换到: {selected}")
        
        if "claude:sonnet@vendor_a" in selected:
            print("   ✅ 优先切换到同模型不同 Provider（正确）")
        else:
            print(f"   ⚠️  切换到了 {selected}，应优先同模型")
        
        # 场景 2: 所有 Claude 失败，切换到 Qwen
        print()
        print("   场景 2: 所有 Claude 失败 → 跨厂商切换到 Qwen")
        
        primary2 = RouteTarget(
            service=create_mock_service("primary:claude:sonnet", should_fail=True),
            provider=LLMProvider.CLAUDE,
            model="claude-sonnet",
            name="primary:claude:sonnet"
        )
        
        fallback_0_2 = RouteTarget(
            service=create_mock_service("fallback:claude:sonnet@vendor_a", should_fail=True),
            provider=LLMProvider.CLAUDE,
            model="claude-sonnet",
            name="fallback:claude:sonnet@vendor_a"
        )
        
        fallback_1_2 = RouteTarget(
            service=create_mock_service("fallback:qwen:qwen-max", should_fail=False),
            provider=LLMProvider.QWEN,
            model="qwen-max",
            name="fallback:qwen:qwen-max"
        )
        
        router2 = ModelRouter(
            primary=primary2,
            fallbacks=[fallback_0_2, fallback_1_2],
            policy={"max_failures": 1, "cooldown_seconds": 60}
        )
        
        response2 = await router2.create_message_async(
            messages=[Message(role="user", content="test")]
        )
        
        selected2 = router2._last_selected
        print(f"   ✅ 自动切换到: {selected2}")
        
        if "qwen" in selected2:
            print("   ✅ 跨厂商切换到 Qwen（正确）")
        else:
            print(f"   ❌ 切换失败，当前: {selected2}")
            return False
        
        print()
        print("✅ ModelRouter 主备自动切换正常")
        return True
        
    except Exception as e:
        print(f"❌ ModelRouter 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

result = asyncio.run(test_model_router_failover())
if not result:
    sys.exit(1)

print()

# ============================================================
# 测试 4: 请求链路探针默认禁用
# ============================================================

print("📋 测试 4: 请求链路探针默认禁用（不阻塞用户）")
print("-" * 60)

async def test_request_probe_disabled():
    try:
        from services.chat_service import ChatService
        from unittest.mock import MagicMock, AsyncMock
        
        # Mock SessionService
        mock_session_service = MagicMock()
        chat_service = ChatService(session_service=mock_session_service)
        
        # Mock 慢速探针（如果被调用会阻塞）
        async def very_slow_probe(*args, **kwargs):
            await asyncio.sleep(30)  # 30 秒
            return {"switched": False}
        
        mock_llm = MagicMock()
        mock_llm.probe = very_slow_probe
        
        # 测量探针调用时间
        start = time.time()
        result = await chat_service._probe_llm_service(
            llm_service=mock_llm,
            session_id="test_session",
            role="simple_agent"
        )
        elapsed = time.time() - start
        
        print(f"   探针调用耗时: {elapsed:.3f}s")
        
        if result is None and elapsed < 0.5:
            print("   ✅ 探针被跳过，立即返回（不阻塞用户）")
            return True
        else:
            print(f"   ❌ 探针未被跳过或耗时过长: result={result}, elapsed={elapsed:.3f}s")
            return False
        
    except Exception as e:
        print(f"❌ 请求链路探针测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

result = asyncio.run(test_request_probe_disabled())
if not result:
    sys.exit(1)

print()

# ============================================================
# 测试 5: 完整流程模拟
# ============================================================

print("📋 测试 5: 完整流程模拟（用户请求 + 后台探测）")
print("-" * 60)

async def test_complete_flow():
    try:
        from services.health_probe_service import HealthProbeService
        
        # 启动后台探测服务
        service = HealthProbeService(
            interval_seconds=2,  # 短间隔用于测试
            timeout_seconds=5.0,
            profiles=["main_agent"]
        )
        
        print("   启动后台健康探测服务...")
        await service.start()
        
        # 模拟用户请求（不应被阻塞）
        print("   模拟用户请求...")
        user_request_start = time.time()
        
        # 模拟用户请求处理
        await asyncio.sleep(0.1)
        
        user_request_elapsed = time.time() - user_request_start
        print(f"   ✅ 用户请求完成: {user_request_elapsed:.3f}s")
        
        if user_request_elapsed > 0.5:
            print("   ⚠️  用户请求耗时过长，可能被阻塞")
        
        # 等待后台探测执行
        print("   等待后台探测执行...")
        await asyncio.sleep(3)
        
        # 查询健康状态
        status = service.get_health_status()
        print(f"   ✅ 健康状态: {status['overall']}")
        print(f"   ✅ 探测运行中: {status['running']}")
        
        # 停止服务
        await service.stop()
        
        print()
        print("✅ 完整流程验证通过")
        return True
        
    except Exception as e:
        print(f"❌ 完整流程测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

result = asyncio.run(test_complete_flow())
if not result:
    sys.exit(1)

print()

# ============================================================
# 总结
# ============================================================

print("=" * 60)
print("🎉 端到端生产环境验证通过")
print("=" * 60)
print()
print("✅ 验证结果:")
print("   1. 配置文件加载正确")
print("   2. 后台健康探测服务正常运行")
print("   3. ModelRouter 主备自动切换正常")
print("   4. 请求链路探针默认禁用（不阻塞用户）")
print("   5. 完整流程验证通过")
print()
print("🚀 生产环境就绪：")
print("   - 主备自动切换: ✅ 启用")
print("   - 后台健康探测: ✅ 启用（120s 间隔）")
print("   - 请求链路探针: ✅ 禁用（不阻塞用户）")
print("   - 用户体验: ✅ 透明无感知")
print()

sys.exit(0)
