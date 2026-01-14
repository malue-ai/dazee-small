"""
容错与弹性模块

提供统一的超时、重试、熔断、降级机制
"""

from core.resilience.timeout import with_timeout, TimeoutConfig
from core.resilience.retry import with_retry, RetryConfig
from core.resilience.circuit_breaker import CircuitBreaker, CircuitBreakerConfig
from core.resilience.fallback import FallbackStrategy, register_fallback

__all__ = [
    "with_timeout",
    "TimeoutConfig",
    "with_retry",
    "RetryConfig",
    "CircuitBreaker",
    "CircuitBreakerConfig",
    "FallbackStrategy",
    "register_fallback",
]
