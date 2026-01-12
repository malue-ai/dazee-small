"""
断路器模式

防止系统在下游服务故障时产生级联故障

参考白皮书 3.2 节：
- 当连续失败 N 次后，断路器"跳闸"（状态变为 open）
- 在接下来的一段时间内，所有调用都会立即失败
- 经过冷却期后，断路器进入 half_open 状态，允许试探性调用
- 如果试探成功，断路器关闭；否则重新打开
"""

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, Any, Optional, Callable, Awaitable, TypeVar, Generic
from functools import wraps

from logger import get_logger

logger = get_logger("circuit_breaker")

T = TypeVar("T")


class CircuitState(str, Enum):
    """断路器状态"""
    CLOSED = "closed"       # 正常状态，允许调用
    OPEN = "open"           # 跳闸状态，拒绝调用
    HALF_OPEN = "half_open" # 半开状态，允许试探性调用


class CircuitOpenError(Exception):
    """断路器打开时的错误"""
    
    def __init__(self, breaker_name: str, remaining_time: float):
        self.breaker_name = breaker_name
        self.remaining_time = remaining_time
        super().__init__(
            f"断路器 '{breaker_name}' 已打开，"
            f"剩余冷却时间: {remaining_time:.1f}秒"
        )


@dataclass
class CircuitBreakerConfig:
    """断路器配置"""
    failure_threshold: int = 5          # 连续失败次数阈值
    success_threshold: int = 2          # 半开状态下连续成功次数阈值
    timeout: float = 30.0               # 冷却超时时间（秒）
    excluded_exceptions: tuple = ()     # 不计入失败的异常类型


@dataclass
class CircuitBreakerStats:
    """断路器统计"""
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    rejected_calls: int = 0             # 被断路器拒绝的调用
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    last_failure_time: Optional[datetime] = None
    last_success_time: Optional[datetime] = None
    state_changes: list = field(default_factory=list)


class CircuitBreaker:
    """
    断路器
    
    使用示例：
        breaker = CircuitBreaker(name="claude_api")
        
        try:
            result = await breaker.call(api_client.create_message, ...)
        except CircuitOpenError as e:
            # 断路器打开，快速失败
            logger.warning(f"API 暂不可用: {e}")
        except Exception as e:
            # 实际调用失败
            logger.error(f"API 调用失败: {e}")
    """
    
    def __init__(
        self,
        name: str,
        config: CircuitBreakerConfig = None,
        on_state_change: Callable[[CircuitState, CircuitState], None] = None
    ):
        """
        初始化断路器
        
        Args:
            name: 断路器名称（标识哪个服务）
            config: 配置
            on_state_change: 状态变更回调
        """
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self._on_state_change = on_state_change
        
        # 状态
        self._state = CircuitState.CLOSED
        self._last_state_change_time = time.time()
        
        # 统计
        self._stats = CircuitBreakerStats()
        
        # 锁（并发保护）
        self._lock = asyncio.Lock()
        
        logger.info(f"断路器 '{name}' 初始化完成")
    
    @property
    def state(self) -> CircuitState:
        """获取当前状态"""
        return self._state
    
    @property
    def stats(self) -> CircuitBreakerStats:
        """获取统计信息"""
        return self._stats
    
    @property
    def is_closed(self) -> bool:
        return self._state == CircuitState.CLOSED
    
    @property
    def is_open(self) -> bool:
        return self._state == CircuitState.OPEN
    
    @property
    def is_half_open(self) -> bool:
        return self._state == CircuitState.HALF_OPEN
    
    async def call(
        self,
        func: Callable[..., Awaitable[T]],
        *args,
        **kwargs
    ) -> T:
        """
        通过断路器调用函数
        
        Args:
            func: 要调用的异步函数
            *args, **kwargs: 函数参数
            
        Returns:
            函数返回值
            
        Raises:
            CircuitOpenError: 断路器打开
            Exception: 函数抛出的异常
        """
        async with self._lock:
            # 检查并可能更新状态
            await self._check_state()
            
            # 如果断路器打开，快速失败
            if self._state == CircuitState.OPEN:
                self._stats.rejected_calls += 1
                remaining = self.config.timeout - (time.time() - self._last_state_change_time)
                raise CircuitOpenError(self.name, max(0, remaining))
        
        # 执行调用
        self._stats.total_calls += 1
        
        try:
            result = await func(*args, **kwargs)
            await self._on_success()
            return result
        except Exception as e:
            # 检查是否是排除的异常
            if isinstance(e, self.config.excluded_exceptions):
                await self._on_success()  # 排除的异常不计入失败
                raise
            
            await self._on_failure(e)
            raise
    
    async def _check_state(self):
        """检查并可能更新状态"""
        if self._state == CircuitState.OPEN:
            # 检查是否超过冷却时间
            elapsed = time.time() - self._last_state_change_time
            if elapsed >= self.config.timeout:
                await self._transition_to(CircuitState.HALF_OPEN)
    
    async def _on_success(self):
        """调用成功处理"""
        async with self._lock:
            self._stats.successful_calls += 1
            self._stats.consecutive_successes += 1
            self._stats.consecutive_failures = 0
            self._stats.last_success_time = datetime.now()
            
            if self._state == CircuitState.HALF_OPEN:
                # 半开状态下，连续成功达到阈值则关闭断路器
                if self._stats.consecutive_successes >= self.config.success_threshold:
                    await self._transition_to(CircuitState.CLOSED)
    
    async def _on_failure(self, error: Exception):
        """调用失败处理"""
        async with self._lock:
            self._stats.failed_calls += 1
            self._stats.consecutive_failures += 1
            self._stats.consecutive_successes = 0
            self._stats.last_failure_time = datetime.now()
            
            logger.warning(
                f"断路器 '{self.name}' 记录失败: "
                f"连续失败={self._stats.consecutive_failures}, "
                f"错误={error}"
            )
            
            if self._state == CircuitState.HALF_OPEN:
                # 半开状态下失败，立即打开
                await self._transition_to(CircuitState.OPEN)
            elif self._state == CircuitState.CLOSED:
                # 关闭状态下，连续失败达到阈值则打开
                if self._stats.consecutive_failures >= self.config.failure_threshold:
                    await self._transition_to(CircuitState.OPEN)
    
    async def _transition_to(self, new_state: CircuitState):
        """状态转换"""
        old_state = self._state
        self._state = new_state
        self._last_state_change_time = time.time()
        
        # 重置计数
        if new_state == CircuitState.CLOSED:
            self._stats.consecutive_failures = 0
        elif new_state == CircuitState.HALF_OPEN:
            self._stats.consecutive_successes = 0
        
        # 记录状态变更
        self._stats.state_changes.append({
            "from": old_state.value,
            "to": new_state.value,
            "time": datetime.now().isoformat()
        })
        
        logger.info(
            f"断路器 '{self.name}' 状态变更: "
            f"{old_state.value} → {new_state.value}"
        )
        
        # 回调
        if self._on_state_change:
            try:
                self._on_state_change(old_state, new_state)
            except Exception as e:
                logger.error(f"状态变更回调失败: {e}")
    
    def reset(self):
        """重置断路器"""
        self._state = CircuitState.CLOSED
        self._stats = CircuitBreakerStats()
        self._last_state_change_time = time.time()
        logger.info(f"断路器 '{self.name}' 已重置")
    
    def get_status(self) -> Dict[str, Any]:
        """获取断路器状态"""
        return {
            "name": self.name,
            "state": self._state.value,
            "stats": {
                "total_calls": self._stats.total_calls,
                "successful_calls": self._stats.successful_calls,
                "failed_calls": self._stats.failed_calls,
                "rejected_calls": self._stats.rejected_calls,
                "consecutive_failures": self._stats.consecutive_failures,
            },
            "config": {
                "failure_threshold": self.config.failure_threshold,
                "timeout": self.config.timeout,
            }
        }


# ==================== 装饰器版本 ====================

def circuit_breaker(
    name: str = None,
    failure_threshold: int = 5,
    timeout: float = 30.0
):
    """
    断路器装饰器
    
    使用示例：
        @circuit_breaker(name="claude_api", failure_threshold=3)
        async def call_claude_api():
            ...
    """
    # 全局断路器注册表
    _breakers: Dict[str, CircuitBreaker] = {}
    
    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        breaker_name = name or func.__name__
        
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            # 获取或创建断路器
            if breaker_name not in _breakers:
                _breakers[breaker_name] = CircuitBreaker(
                    name=breaker_name,
                    config=CircuitBreakerConfig(
                        failure_threshold=failure_threshold,
                        timeout=timeout
                    )
                )
            
            breaker = _breakers[breaker_name]
            return await breaker.call(func, *args, **kwargs)
        
        return wrapper
    
    return decorator
