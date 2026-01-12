"""
容错模块

职责：
- 断路器模式：防止级联故障
- 指数退避重试：处理瞬时错误
- 背压控制：流量控制

参考：
- 白皮书 3.2 节：容错模式
"""

from .circuit_breaker import CircuitBreaker, CircuitState, CircuitOpenError
from .retry_policy import RetryPolicy, ExponentialBackoffRetry, MaxRetriesExceededError
from .backpressure import BackpressureController, TokenBucket
from .layer import FaultToleranceLayer, create_fault_tolerance_layer

__all__ = [
    # 断路器
    "CircuitBreaker",
    "CircuitState",
    "CircuitOpenError",
    
    # 重试
    "RetryPolicy",
    "ExponentialBackoffRetry",
    "MaxRetriesExceededError",
    
    # 背压
    "BackpressureController",
    "TokenBucket",
    
    # 统一层
    "FaultToleranceLayer",
    "create_fault_tolerance_layer",
]
