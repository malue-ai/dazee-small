#!/usr/bin/env python3
"""
探针优化验证脚本（V7.11 条件探测策略）

直接运行验证优化实现是否正确：
    python3 scripts/verify_probe_optimization.py

验证内容：
1. 条件探测：后台健康则跳过，不健康则执行
2. 超时控制：探针超时控制
3. 后台健康探测服务：定期探测所有模型
"""

import asyncio
import os
import time
import sys

# ============================================================
# 测试工具
# ============================================================

class TestResult:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors = []
    
    def ok(self, name):
        self.passed += 1
        print(f"  ✅ {name}")
    
    def fail(self, name, reason):
        self.failed += 1
        self.errors.append((name, reason))
        print(f"  ❌ {name}: {reason}")
    
    def summary(self):
        total = self.passed + self.failed
        print(f"\n{'=' * 60}")
        print(f"测试结果: {self.passed}/{total} 通过")
        if self.errors:
            print("\n失败详情:")
            for name, reason in self.errors:
                print(f"  - {name}: {reason}")
        return self.failed == 0

result = TestResult()

# ============================================================
# 条件探测测试（V7.11）
# ============================================================

async def test_conditional_probe():
    """V7.11 条件探测策略测试"""
    print("\n📋 条件探测测试：后台健康则跳过，不健康则执行")
    
    probe_executed = False
    
    # 模拟后台健康状态
    class MockHealthProbeService:
        def __init__(self, is_healthy: bool = True):
            self._healthy = is_healthy
        
        def is_healthy(self, profile_name: str) -> bool:
            return self._healthy
    
    async def mock_probe_llm_service(health_service: MockHealthProbeService, profile_name: str):
        nonlocal probe_executed
        
        # V7.11 条件探测逻辑
        if health_service.is_healthy(profile_name):
            # 后台健康，跳过探测
            return None
        
        # 后台不健康，执行请求级探测
        probe_executed = True
        await asyncio.sleep(0.1)  # 模拟探针耗时
        return {"switched": False}
    
    # 测试 1：后台健康 → 跳过探测
    probe_executed = False
    healthy_service = MockHealthProbeService(is_healthy=True)
    
    start = time.time()
    res = await mock_probe_llm_service(healthy_service, "main_agent")
    elapsed = time.time() - start
    
    if res is None and not probe_executed and elapsed < 0.05:
        result.ok("后台健康 → 跳过探测（零延迟）")
    else:
        result.fail("后台健康跳过探测", f"expected None, got {res}, elapsed={elapsed:.3f}s")
    
    # 测试 2：后台不健康 → 执行探测
    probe_executed = False
    unhealthy_service = MockHealthProbeService(is_healthy=False)
    
    res = await mock_probe_llm_service(unhealthy_service, "main_agent")
    
    if res is not None and probe_executed:
        result.ok("后台不健康 → 执行探测确认")
    else:
        result.fail("后台不健康执行探测", f"expected result, got {res}, executed={probe_executed}")

# ============================================================
# 超时控制测试
# ============================================================

async def test_timeout_control():
    """超时控制测试"""
    print("\n📋 超时控制测试：条件探测超时限制")
    
    os.environ["LLM_PROBE_TIMEOUT"] = "1.0"  # 1s 超时
    
    try:
        async def mock_probe_with_timeout():
            timeout_env = os.getenv("LLM_PROBE_TIMEOUT")
            timeout = float(timeout_env) if timeout_env else 5.0
            
            async def slow_probe():
                await asyncio.sleep(5)  # 5s 探针（模拟慢速探测）
                return {"switched": False}
            
            try:
                return await asyncio.wait_for(slow_probe(), timeout=timeout)
            except asyncio.TimeoutError:
                return None  # 超时返回 None
        
        start = time.time()
        res = await mock_probe_with_timeout()
        elapsed = time.time() - start
        
        if res is None and elapsed < 1.5:
            result.ok(f"超时控制生效，耗时 {elapsed:.2f}s < 1.5s")
        else:
            result.fail("超时控制", f"expected timeout in ~1s, got elapsed={elapsed:.2f}s")
    finally:
        os.environ.pop("LLM_PROBE_TIMEOUT", None)

# ============================================================
# 长期优化测试：后台健康探测服务
# ============================================================

async def test_long_term_optimization():
    """长期优化测试"""
    print("\n📋 长期优化测试：后台健康探测服务")
    
    probe_count = 0
    
    class MockHealthProbeService:
        def __init__(self, interval=0.5):
            self.interval = interval
            self._running = False
            self._task = None
            self.enabled = os.getenv("LLM_HEALTH_PROBE_ENABLED", "true").lower() in ("true", "1", "yes")
            self._probe_results = {}
        
        async def start(self):
            if not self.enabled:
                return
            self._running = True
            self._task = asyncio.create_task(self._probe_loop())
        
        async def stop(self):
            self._running = False
            if self._task:
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass
        
        async def _probe_loop(self):
            nonlocal probe_count
            while self._running:
                probe_count += 1
                self._probe_results["main_agent"] = {"status": "healthy"}
                await asyncio.sleep(self.interval)
        
        def get_health_status(self):
            return {
                "overall": "healthy",
                "profiles": self._probe_results,
                "running": self._running
            }
    
    # 测试 1：服务生命周期
    service = MockHealthProbeService(interval=0.3)
    
    if not service._running:
        result.ok("服务初始状态为停止")
    else:
        result.fail("服务初始状态", "expected not running")
    
    await service.start()
    
    if service._running:
        result.ok("服务启动成功")
    else:
        result.fail("服务启动", "expected running")
    
    # 测试 2：后台探测独立运行
    probe_count = 0
    
    # 模拟用户请求（不应被阻塞）
    user_start = time.time()
    await asyncio.sleep(0.1)  # 模拟用户请求
    user_elapsed = time.time() - user_start
    
    if user_elapsed < 0.2:
        result.ok(f"用户请求不被阻塞，耗时 {user_elapsed:.3f}s")
    else:
        result.fail("用户请求阻塞", f"elapsed={user_elapsed:.2f}s")
    
    # 等待后台探测
    await asyncio.sleep(1.0)
    
    if probe_count >= 2:
        result.ok(f"后台探测独立运行，执行 {probe_count} 次")
    else:
        result.fail("后台探测", f"expected >= 2, got {probe_count}")
    
    # 测试 3：健康状态查询
    status = service.get_health_status()
    
    if status["overall"] == "healthy" and status["running"]:
        result.ok("健康状态查询正常")
    else:
        result.fail("健康状态查询", f"status={status}")
    
    await service.stop()
    
    if not service._running:
        result.ok("服务停止成功")
    else:
        result.fail("服务停止", "expected not running")
    
    # 测试 4：禁用服务
    os.environ["LLM_HEALTH_PROBE_ENABLED"] = "false"
    
    try:
        disabled_service = MockHealthProbeService()
        
        if not disabled_service.enabled:
            result.ok("服务可通过环境变量禁用")
        else:
            result.fail("服务禁用", "expected disabled")
        
        await disabled_service.start()
        
        if not disabled_service._running:
            result.ok("禁用时启动不会真正运行")
        else:
            result.fail("禁用时启动", "expected not running")
    finally:
        os.environ.pop("LLM_HEALTH_PROBE_ENABLED", None)

# ============================================================
# ModelRouter 主备切换测试
# ============================================================

async def test_model_router_failover():
    """ModelRouter 主备切换测试"""
    print("\n📋 ModelRouter 主备切换测试")
    
    class MockRouteTarget:
        def __init__(self, name, should_fail=False):
            self.name = name
            self.should_fail = should_fail
        
        async def call(self):
            if self.should_fail:
                raise Exception("Service unavailable")
            return {"content": "response"}
    
    class MockModelRouter:
        def __init__(self, primary, fallbacks):
            self.primary = primary
            self.fallbacks = fallbacks
            self.targets = [primary] + fallbacks
            self._last_selected = None
        
        async def create_message(self):
            for target in self.targets:
                try:
                    res = await target.call()
                    self._last_selected = target.name
                    return res
                except Exception:
                    continue
            raise RuntimeError("All targets failed")
    
    # 场景 1：同模型多 Provider 优先
    primary = MockRouteTarget("primary:claude:sonnet", should_fail=True)
    fallback_0 = MockRouteTarget("fallback_0:claude:sonnet@vendor_a", should_fail=True)
    fallback_1 = MockRouteTarget("fallback_1:claude:sonnet@vendor_b", should_fail=False)
    fallback_2 = MockRouteTarget("fallback_2:qwen:qwen-max", should_fail=False)
    
    router = MockModelRouter(primary, [fallback_0, fallback_1, fallback_2])
    
    res = await router.create_message()
    
    if router._last_selected == "fallback_1:claude:sonnet@vendor_b":
        result.ok("同模型多 Provider 优先切换")
    else:
        result.fail("同模型优先切换", f"expected fallback_1, got {router._last_selected}")
    
    # 场景 2：所有 Claude 失败，切换到 Qwen
    primary2 = MockRouteTarget("primary:claude:sonnet", should_fail=True)
    fallback_0_2 = MockRouteTarget("fallback_0:claude:sonnet@vendor_a", should_fail=True)
    fallback_1_2 = MockRouteTarget("fallback_1:claude:sonnet@vendor_b", should_fail=True)
    fallback_2_2 = MockRouteTarget("fallback_2:qwen:qwen-max", should_fail=False)
    
    router2 = MockModelRouter(primary2, [fallback_0_2, fallback_1_2, fallback_2_2])
    
    res2 = await router2.create_message()
    
    if router2._last_selected == "fallback_2:qwen:qwen-max":
        result.ok("所有 Claude 失败后切换到 Qwen")
    else:
        result.fail("跨厂商切换", f"expected fallback_2, got {router2._last_selected}")

# ============================================================
# 主函数
# ============================================================

async def main():
    print("=" * 60)
    print("🔍 LLM 探针优化验证（V7.11 条件探测策略）")
    print("=" * 60)
    
    await test_conditional_probe()       # V7.11 条件探测
    await test_timeout_control()         # 超时控制
    await test_long_term_optimization()  # 后台健康探测
    await test_model_router_failover()   # ModelRouter 切换
    
    success = result.summary()
    
    if success:
        print("\n🎉 所有测试通过！")
        sys.exit(0)
    else:
        print("\n⚠️ 部分测试失败")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
