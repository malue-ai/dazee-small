"""
Fallback 机制测试

测试覆盖范围：
1. infra/resilience/fallback.py - 降级策略框架
2. 默认降级响应函数
3. 装饰器功能
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from infra.resilience.fallback import (
    FallbackStrategy,
    FallbackType,
    register_fallback,
    get_fallback_strategy,
    default_llm_fallback,
    default_tool_fallback,
    default_database_fallback,
)


class TestFallbackType:
    """FallbackType 枚举测试"""
    
    def test_fallback_types_exist(self):
        """测试所有 Fallback 类型存在"""
        assert FallbackType.CACHED_RESPONSE.value == "cached_response"
        assert FallbackType.DEFAULT_RESPONSE.value == "default_response"
        assert FallbackType.SKIP.value == "skip"
        assert FallbackType.SIMPLIFIED.value == "simplified"


class TestFallbackStrategy:
    """FallbackStrategy 类测试"""
    
    def test_register_fallback(self):
        """测试注册降级策略"""
        strategy = FallbackStrategy()
        fallback_func = lambda: {"test": True}
        
        strategy.register("test_service", fallback_func)
        
        registered = strategy.get_fallback("test_service")
        assert registered is not None
        assert registered["func"] == fallback_func
        assert registered["type"] == FallbackType.DEFAULT_RESPONSE
    
    def test_register_fallback_with_type(self):
        """测试注册带有类型的降级策略"""
        strategy = FallbackStrategy()
        fallback_func = lambda: {"cached": True}
        
        strategy.register(
            "cache_service", 
            fallback_func, 
            FallbackType.CACHED_RESPONSE
        )
        
        registered = strategy.get_fallback("cache_service")
        assert registered["type"] == FallbackType.CACHED_RESPONSE
    
    def test_get_unregistered_fallback(self):
        """测试获取未注册的降级策略返回 None"""
        strategy = FallbackStrategy()
        
        result = strategy.get_fallback("nonexistent_service")
        
        assert result is None
    
    @pytest.mark.asyncio
    async def test_with_fallback_success(self):
        """测试装饰器 - 成功情况不触发降级"""
        strategy = FallbackStrategy()
        strategy.register("success_service", lambda: {"fallback": True})
        
        @strategy.with_fallback("success_service")
        async def successful_operation():
            return {"success": True, "data": "result"}
        
        result = await successful_operation()
        
        assert result["success"] is True
        assert result["data"] == "result"
        assert "_fallback" not in result
    
    @pytest.mark.asyncio
    async def test_with_fallback_triggered(self):
        """测试装饰器 - 异常情况触发降级"""
        strategy = FallbackStrategy()
        strategy.register(
            "failing_service", 
            lambda: {"fallback_result": "降级响应"}
        )
        
        @strategy.with_fallback("failing_service")
        async def failing_operation():
            raise Exception("服务不可用")
        
        result = await failing_operation()
        
        assert result["fallback_result"] == "降级响应"
        assert result["_fallback"] is True
        assert result["_fallback_type"] == "default_response"
    
    @pytest.mark.asyncio
    async def test_with_fallback_async_fallback_func(self):
        """测试装饰器 - 异步降级函数"""
        strategy = FallbackStrategy()
        
        async def async_fallback():
            await asyncio.sleep(0.01)  # 模拟异步操作
            return {"async_fallback": True}
        
        strategy.register("async_service", async_fallback)
        
        @strategy.with_fallback("async_service")
        async def failing_async_operation():
            raise Exception("异步服务失败")
        
        result = await failing_async_operation()
        
        assert result["async_fallback"] is True
        assert result["_fallback"] is True
    
    @pytest.mark.asyncio
    async def test_with_fallback_no_strategy_raises(self):
        """测试装饰器 - 无降级策略时抛出原始异常"""
        strategy = FallbackStrategy()
        
        @strategy.with_fallback("unregistered_service")
        async def operation_without_fallback():
            raise ValueError("原始错误")
        
        with pytest.raises(ValueError, match="原始错误"):
            await operation_without_fallback()


class TestDefaultFallbackResponses:
    """默认降级响应测试"""
    
    def test_default_llm_fallback(self):
        """测试 LLM 默认降级响应"""
        result = default_llm_fallback()
        
        assert result["success"] is False
        assert "AI 服务" in result["content"]
        assert result["error"] == "llm_service_unavailable"
    
    def test_default_tool_fallback(self):
        """测试工具默认降级响应"""
        result = default_tool_fallback()
        
        assert result["success"] is False
        assert "工具" in result["error"]
        assert result["skipped"] is True
    
    def test_default_database_fallback(self):
        """测试数据库默认降级响应"""
        result = default_database_fallback()
        
        assert result["success"] is False
        assert "数据库" in result["error"]
        assert result["cached"] is False


class TestGlobalFallbackStrategy:
    """全局降级策略测试"""
    
    def test_get_fallback_strategy_returns_singleton(self):
        """测试获取全局策略返回同一实例"""
        strategy1 = get_fallback_strategy()
        strategy2 = get_fallback_strategy()
        
        assert strategy1 is strategy2
    
    def test_register_fallback_convenience_function(self):
        """测试便捷注册函数"""
        fallback_func = lambda: {"global": True}
        
        register_fallback("global_test_service", fallback_func)
        
        strategy = get_fallback_strategy()
        registered = strategy.get_fallback("global_test_service")
        
        assert registered is not None
        assert registered["func"] == fallback_func


class TestFallbackIntegration:
    """Fallback 集成测试"""
    
    @pytest.mark.asyncio
    async def test_multiple_services_fallback(self):
        """测试多个服务的降级策略"""
        strategy = FallbackStrategy()
        
        # 注册多个服务
        strategy.register("service_a", lambda: {"service": "a"})
        strategy.register("service_b", lambda: {"service": "b"})
        strategy.register("service_c", lambda: {"service": "c"})
        
        @strategy.with_fallback("service_a")
        async def call_service_a():
            raise Exception("A 失败")
        
        @strategy.with_fallback("service_b")
        async def call_service_b():
            return {"success": True}  # B 成功
        
        @strategy.with_fallback("service_c")
        async def call_service_c():
            raise Exception("C 失败")
        
        # 执行
        result_a = await call_service_a()
        result_b = await call_service_b()
        result_c = await call_service_c()
        
        # 验证
        assert result_a["service"] == "a"
        assert result_a["_fallback"] is True
        
        assert result_b["success"] is True
        assert "_fallback" not in result_b
        
        assert result_c["service"] == "c"
        assert result_c["_fallback"] is True
    
    @pytest.mark.asyncio
    async def test_fallback_preserves_args(self):
        """测试降级函数接收原始参数"""
        strategy = FallbackStrategy()
        received_args = []
        
        def fallback_with_args(*args, **kwargs):
            received_args.append((args, kwargs))
            return {"received": True}
        
        strategy.register("args_service", fallback_with_args)
        
        @strategy.with_fallback("args_service")
        async def operation_with_args(a, b, c=None):
            raise Exception("失败")
        
        await operation_with_args(1, 2, c=3)
        
        assert len(received_args) == 1
        assert received_args[0][0] == (1, 2)
        assert received_args[0][1] == {"c": 3}
