"""
熔断器模块

实现断路器模式，防止故障蔓延
"""

import asyncio
import time
from enum import Enum
from typing import Callable, Any, Optional
from dataclasses import dataclass, field
from collections import deque

from logger import get_logger

logger = get_logger(__name__)


class CircuitState(Enum):
    """熔断器状态"""
    CLOSED = "closed"        # 关闭（正常工作）
    OPEN = "open"            # 打开（熔断中）
    HALF_OPEN = "half_open"  # 半开（尝试恢复）


@dataclass
class CircuitBreakerConfig:
    """熔断器配置"""
    failure_threshold: int = 5           # 失败次数阈值
    success_threshold: int = 2           # 成功次数阈值（半开 → 关闭）
    timeout: float = 30.0                # 熔断超时时间（秒）
    window_size: int = 10                # 滑动窗口大小
    half_open_max_calls: int = 1         # 半开状态最大并发调用数


class CircuitBreaker:
    """
    熔断器
    
    使用示例:
        breaker = CircuitBreaker("llm_service")
        
        async def call_llm():
            async with breaker:
                return await llm.generate()
    """
    
    def __init__(
        self,
        name: str,
        config: Optional[CircuitBreakerConfig] = None
    ):
        self.name = name
        self.config = config or CircuitBreakerConfig()
        
        # 状态
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: Optional[float] = None
        
        # 滑动窗口（记录最近的调用结果）
        self._recent_calls = deque(maxlen=self.config.window_size)
        
        # 半开状态的并发控制
        self._half_open_calls = 0
        self._lock = asyncio.Lock()
        
        logger.info(f"🔌 熔断器已创建: {name}")
    
    @property
    def state(self) -> CircuitState:
        """获取当前状态"""
        return self._state
    
    @property
    def is_open(self) -> bool:
        """是否处于熔断状态"""
        return self._state == CircuitState.OPEN
    
    async def __aenter__(self):
        """进入上下文"""
        await self._before_call()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """退出上下文"""
        if exc_type is None:
            # 成功
            await self._on_success()
        else:
            # 失败
            await self._on_failure(exc_val)
        return False
    
    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        执行函数调用（带熔断保护）
        
        Args:
            func: 要执行的函数
            *args: 函数参数
            **kwargs: 函数关键字参数
            
        Returns:
            函数执行结果
            
        Raises:
            CircuitBreakerOpenError: 熔断器打开时
        """
        async with self:
            return await func(*args, **kwargs)
    
    async def _before_call(self):
        """调用前检查"""
        async with self._lock:
            # 如果是打开状态，检查是否可以转为半开
            if self._state == CircuitState.OPEN:
                if self._should_attempt_reset():
                    self._transition_to_half_open()
                else:
                    raise CircuitBreakerOpenError(
                        f"熔断器 {self.name} 处于打开状态，"
                        f"将在 {self._time_until_retry():.1f}s 后重试"
                    )
            
            # 如果是半开状态，检查并发调用数
            if self._state == CircuitState.HALF_OPEN:
                if self._half_open_calls >= self.config.half_open_max_calls:
                    raise CircuitBreakerOpenError(
                        f"熔断器 {self.name} 处于半开状态，"
                        "当前已达最大并发调用数"
                    )
                self._half_open_calls += 1
    
    async def _on_success(self):
        """调用成功回调"""
        async with self._lock:
            self._recent_calls.append(True)
            
            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                self._half_open_calls -= 1
                
                # 达到成功阈值，转为关闭状态
                if self._success_count >= self.config.success_threshold:
                    self._transition_to_closed()
            
            elif self._state == CircuitState.CLOSED:
                # 关闭状态下成功，重置失败计数
                self._failure_count = 0
    
    async def _on_failure(self, error: Exception):
        """调用失败回调"""
        async with self._lock:
            self._recent_calls.append(False)
            self._failure_count += 1
            self._last_failure_time = time.time()
            
            logger.warning(
                f"⚠️ 熔断器 {self.name} 记录失败 "
                f"({self._failure_count}/{self.config.failure_threshold}): {str(error)}"
            )
            
            if self._state == CircuitState.HALF_OPEN:
                # 半开状态失败，立即转为打开
                self._half_open_calls -= 1
                self._transition_to_open()
            
            elif self._state == CircuitState.CLOSED:
                # 关闭状态达到失败阈值，转为打开
                if self._failure_count >= self.config.failure_threshold:
                    self._transition_to_open()
    
    def _should_attempt_reset(self) -> bool:
        """是否应该尝试重置（从打开 → 半开）"""
        if self._last_failure_time is None:
            return True
        
        elapsed = time.time() - self._last_failure_time
        return elapsed >= self.config.timeout
    
    def _time_until_retry(self) -> float:
        """距离下次重试的时间"""
        if self._last_failure_time is None:
            return 0.0
        
        elapsed = time.time() - self._last_failure_time
        remaining = self.config.timeout - elapsed
        return max(0.0, remaining)
    
    def _transition_to_open(self):
        """转换到打开状态"""
        if self._state != CircuitState.OPEN:
            logger.error(
                f"🔴 熔断器 {self.name} 打开 "
                f"(失败次数: {self._failure_count}, 超时: {self.config.timeout}s)"
            )
            self._state = CircuitState.OPEN
            self._success_count = 0
    
    def _transition_to_half_open(self):
        """转换到半开状态"""
        if self._state != CircuitState.HALF_OPEN:
            logger.info(f"🟡 熔断器 {self.name} 转为半开状态（尝试恢复）")
            self._state = CircuitState.HALF_OPEN
            self._success_count = 0
            self._half_open_calls = 0
    
    def _transition_to_closed(self):
        """转换到关闭状态"""
        if self._state != CircuitState.CLOSED:
            logger.info(f"🟢 熔断器 {self.name} 恢复正常（关闭状态）")
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._success_count = 0
    
    def get_stats(self) -> dict:
        """获取统计信息"""
        total_calls = len(self._recent_calls)
        successful_calls = sum(1 for success in self._recent_calls if success)
        
        return {
            "name": self.name,
            "state": self._state.value,
            "failure_count": self._failure_count,
            "success_count": self._success_count,
            "total_calls": total_calls,
            "successful_calls": successful_calls,
            "success_rate": successful_calls / total_calls if total_calls > 0 else 0.0,
            "time_until_retry": self._time_until_retry() if self._state == CircuitState.OPEN else 0.0,
        }


class CircuitBreakerOpenError(Exception):
    """熔断器打开异常"""
    pass


# 全局熔断器注册表
_circuit_breakers: dict[str, CircuitBreaker] = {}


def get_circuit_breaker(
    name: str,
    config: Optional[CircuitBreakerConfig] = None
) -> CircuitBreaker:
    """
    获取或创建熔断器
    
    Args:
        name: 熔断器名称
        config: 配置（仅在首次创建时使用）
        
    Returns:
        熔断器实例
    """
    if name not in _circuit_breakers:
        _circuit_breakers[name] = CircuitBreaker(name, config)
    
    return _circuit_breakers[name]


def get_all_circuit_breakers() -> dict[str, CircuitBreaker]:
    """获取所有熔断器"""
    return _circuit_breakers.copy()
