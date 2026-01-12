"""
容错层

统一封装断路器、重试策略、背压控制
"""

import asyncio
from typing import TypeVar, Callable, Awaitable, Dict, Optional

from logger import get_logger
from .circuit_breaker import CircuitBreaker, CircuitBreakerConfig, CircuitOpenError
from .retry_policy import (
    ExponentialBackoffRetry,
    ExponentialBackoffConfig,
    MaxRetriesExceededError
)
from .backpressure import BackpressureController, TokenBucketConfig

logger = get_logger("fault_tolerance_layer")

T = TypeVar("T")


class FaultToleranceLayer:
    """
    容错层
    
    统一管理断路器、重试策略、背压控制
    
    执行顺序：
    1. 背压控制（获取令牌）
    2. 断路器检查
    3. 执行调用（带重试）
    
    使用示例：
        layer = FaultToleranceLayer()
        
        # 注册服务
        layer.register_service(
            name="claude_api",
            circuit_config=CircuitBreakerConfig(failure_threshold=5),
            retry_config=ExponentialBackoffConfig(max_retries=3),
            rate_limit_config=TokenBucketConfig(capacity=10, refill_rate=2.0)
        )
        
        # 执行调用
        result = await layer.execute("claude_api", api_call, arg1, arg2)
    """
    
    def __init__(self):
        """初始化容错层"""
        self._circuit_breakers: Dict[str, CircuitBreaker] = {}
        self._retry_policies: Dict[str, ExponentialBackoffRetry] = {}
        self._backpressure = BackpressureController()
        
        logger.info("✅ 容错层初始化完成")
    
    def register_service(
        self,
        name: str,
        circuit_config: CircuitBreakerConfig = None,
        retry_config: ExponentialBackoffConfig = None,
        rate_limit_config: TokenBucketConfig = None
    ):
        """
        注册服务
        
        Args:
            name: 服务名称
            circuit_config: 断路器配置
            retry_config: 重试配置
            rate_limit_config: 速率限制配置
        """
        # 断路器
        if circuit_config:
            self._circuit_breakers[name] = CircuitBreaker(
                name=name,
                config=circuit_config
            )
        
        # 重试策略
        if retry_config:
            self._retry_policies[name] = ExponentialBackoffRetry(
                config=retry_config
            )
        
        # 速率限制
        if rate_limit_config:
            self._backpressure.register_bucket(
                name=name,
                config=rate_limit_config
            )
        
        logger.info(f"服务 '{name}' 已注册到容错层")
    
    async def execute(
        self,
        service_name: str,
        func: Callable[..., Awaitable[T]],
        *args,
        **kwargs
    ) -> T:
        """
        执行带容错保护的调用
        
        Args:
            service_name: 服务名称
            func: 要调用的异步函数
            *args, **kwargs: 函数参数
            
        Returns:
            函数返回值
            
        Raises:
            CircuitOpenError: 断路器打开
            MaxRetriesExceededError: 超过最大重试次数
        """
        # 1. 背压控制
        await self._backpressure.acquire(service_name)
        
        # 2. 获取断路器和重试策略
        breaker = self._circuit_breakers.get(service_name)
        retry_policy = self._retry_policies.get(service_name)
        
        # 3. 构建执行函数
        async def _execute():
            if breaker:
                return await breaker.call(func, *args, **kwargs)
            else:
                return await func(*args, **kwargs)
        
        # 4. 执行（带重试）
        if retry_policy:
            return await retry_policy.execute(_execute)
        else:
            return await _execute()
    
    def get_circuit_breaker(self, name: str) -> Optional[CircuitBreaker]:
        """获取断路器"""
        return self._circuit_breakers.get(name)
    
    def get_status(self) -> Dict:
        """获取容错层状态"""
        return {
            "circuit_breakers": {
                name: breaker.get_status()
                for name, breaker in self._circuit_breakers.items()
            },
            "backpressure": self._backpressure.get_status()
        }
    
    def reset_circuit_breaker(self, name: str):
        """重置断路器"""
        breaker = self._circuit_breakers.get(name)
        if breaker:
            breaker.reset()


def create_fault_tolerance_layer() -> FaultToleranceLayer:
    """创建容错层实例"""
    layer = FaultToleranceLayer()
    
    # 预注册常用服务
    layer.register_service(
        name="claude_api",
        circuit_config=CircuitBreakerConfig(
            failure_threshold=5,
            timeout=30.0
        ),
        retry_config=ExponentialBackoffConfig(
            max_retries=3,
            base_delay=1.0,
            max_delay=30.0
        ),
        rate_limit_config=TokenBucketConfig(
            capacity=10,
            refill_rate=2.0
        )
    )
    
    layer.register_service(
        name="e2b_sandbox",
        circuit_config=CircuitBreakerConfig(
            failure_threshold=3,
            timeout=60.0
        ),
        retry_config=ExponentialBackoffConfig(
            max_retries=2,
            base_delay=2.0,
            max_delay=20.0
        ),
        rate_limit_config=TokenBucketConfig(
            capacity=5,
            refill_rate=0.5
        )
    )
    
    return layer
