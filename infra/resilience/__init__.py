"""
容错与弹性模块

提供统一的超时、重试、熔断、降级机制
"""

from infra.resilience.timeout import with_timeout, TimeoutConfig
from infra.resilience.retry import with_retry, RetryConfig
from infra.resilience.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    get_circuit_breaker,
    get_all_circuit_breakers,
)
from infra.resilience.fallback import (
    FallbackStrategy,
    FallbackType,
    register_fallback,
    get_fallback_strategy,
)

__all__ = [
    "with_timeout",
    "TimeoutConfig",
    "with_retry",
    "RetryConfig",
    "CircuitBreaker",
    "CircuitBreakerConfig",
    "get_circuit_breaker",
    "get_all_circuit_breakers",
    "FallbackStrategy",
    "FallbackType",
    "register_fallback",
    "get_fallback_strategy",
]
