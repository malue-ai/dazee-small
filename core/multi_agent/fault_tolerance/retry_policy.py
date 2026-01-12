"""
重试策略

处理瞬时性错误（网络抖动、API 暂时过载等）

参考白皮书 3.2 节：
- 指数退避 + 抖动（Exponential Backoff with Jitter）
- 防止"惊群效应"
"""

import asyncio
import random
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import TypeVar, Generic, Callable, Awaitable, Optional, Tuple, Type
from functools import wraps

from logger import get_logger

logger = get_logger("retry_policy")

T = TypeVar("T")


class MaxRetriesExceededError(Exception):
    """超过最大重试次数错误"""
    
    def __init__(
        self,
        attempts: int,
        last_error: Exception,
        total_time: float
    ):
        self.attempts = attempts
        self.last_error = last_error
        self.total_time = total_time
        super().__init__(
            f"超过最大重试次数 ({attempts})，"
            f"最后错误: {last_error}，"
            f"总耗时: {total_time:.1f}秒"
        )


@dataclass
class RetryAttempt:
    """重试尝试记录"""
    attempt: int
    error: Optional[Exception]
    wait_time: float
    timestamp: datetime


class RetryPolicy(ABC):
    """重试策略基类"""
    
    @abstractmethod
    def get_wait_time(self, attempt: int) -> float:
        """
        获取等待时间
        
        Args:
            attempt: 当前重试次数（从 1 开始）
            
        Returns:
            等待时间（秒）
        """
        pass
    
    @abstractmethod
    def should_retry(self, attempt: int, error: Exception) -> bool:
        """
        判断是否应该重试
        
        Args:
            attempt: 当前重试次数
            error: 当前错误
            
        Returns:
            是否应该重试
        """
        pass


@dataclass
class ExponentialBackoffConfig:
    """指数退避配置"""
    max_retries: int = 3                    # 最大重试次数
    base_delay: float = 1.0                 # 基础延迟（秒）
    max_delay: float = 60.0                 # 最大延迟（秒）
    exponential_base: float = 2.0           # 指数基数
    jitter: bool = True                     # 是否添加抖动
    jitter_range: Tuple[float, float] = (0.5, 1.5)  # 抖动范围
    retryable_exceptions: Tuple[Type[Exception], ...] = (Exception,)  # 可重试的异常类型


class ExponentialBackoffRetry(RetryPolicy):
    """
    指数退避重试策略
    
    等待时间计算：
        wait = min(base_delay * (exponential_base ** attempt), max_delay)
        if jitter:
            wait = wait * random.uniform(jitter_range[0], jitter_range[1])
    
    使用示例：
        retry = ExponentialBackoffRetry(config=ExponentialBackoffConfig(
            max_retries=3,
            base_delay=1.0,
            max_delay=30.0
        ))
        
        result = await retry.execute(api_call, arg1, arg2)
    """
    
    def __init__(self, config: ExponentialBackoffConfig = None):
        self.config = config or ExponentialBackoffConfig()
        self._attempts: list[RetryAttempt] = []
    
    def get_wait_time(self, attempt: int) -> float:
        """计算等待时间（指数退避 + 抖动）"""
        # 指数退避
        wait = min(
            self.config.base_delay * (self.config.exponential_base ** attempt),
            self.config.max_delay
        )
        
        # 添加抖动
        if self.config.jitter:
            jitter_min, jitter_max = self.config.jitter_range
            wait = wait * random.uniform(jitter_min, jitter_max)
        
        return wait
    
    def should_retry(self, attempt: int, error: Exception) -> bool:
        """判断是否应该重试"""
        # 检查重试次数
        if attempt >= self.config.max_retries:
            return False
        
        # 检查异常类型
        return isinstance(error, self.config.retryable_exceptions)
    
    async def execute(
        self,
        func: Callable[..., Awaitable[T]],
        *args,
        **kwargs
    ) -> T:
        """
        执行带重试的调用
        
        Args:
            func: 要调用的异步函数
            *args, **kwargs: 函数参数
            
        Returns:
            函数返回值
            
        Raises:
            MaxRetriesExceededError: 超过最大重试次数
        """
        self._attempts = []
        start_time = time.time()
        last_error = None
        
        for attempt in range(self.config.max_retries + 1):
            try:
                result = await func(*args, **kwargs)
                
                # 成功
                if attempt > 0:
                    logger.info(
                        f"重试成功: 第 {attempt + 1} 次尝试，"
                        f"总耗时 {time.time() - start_time:.1f}秒"
                    )
                
                return result
                
            except Exception as e:
                last_error = e
                
                # 记录尝试
                wait_time = self.get_wait_time(attempt) if self.should_retry(attempt, e) else 0
                self._attempts.append(RetryAttempt(
                    attempt=attempt + 1,
                    error=e,
                    wait_time=wait_time,
                    timestamp=datetime.now()
                ))
                
                # 判断是否应该重试
                if not self.should_retry(attempt, e):
                    logger.warning(
                        f"不可重试的错误: {type(e).__name__}: {e}"
                    )
                    raise
                
                # 等待后重试
                logger.warning(
                    f"第 {attempt + 1} 次尝试失败: {type(e).__name__}: {e}，"
                    f"等待 {wait_time:.1f}秒后重试"
                )
                
                await asyncio.sleep(wait_time)
        
        # 超过最大重试次数
        total_time = time.time() - start_time
        raise MaxRetriesExceededError(
            attempts=self.config.max_retries + 1,
            last_error=last_error,
            total_time=total_time
        )
    
    @property
    def attempts(self) -> list[RetryAttempt]:
        """获取重试尝试记录"""
        return self._attempts


# ==================== 装饰器版本 ====================

def retry(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    jitter: bool = True,
    retryable_exceptions: Tuple[Type[Exception], ...] = (Exception,)
):
    """
    重试装饰器
    
    使用示例：
        @retry(max_retries=3, base_delay=1.0)
        async def call_api():
            ...
    """
    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        retry_policy = ExponentialBackoffRetry(
            config=ExponentialBackoffConfig(
                max_retries=max_retries,
                base_delay=base_delay,
                max_delay=max_delay,
                jitter=jitter,
                retryable_exceptions=retryable_exceptions
            )
        )
        
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            return await retry_policy.execute(func, *args, **kwargs)
        
        return wrapper
    
    return decorator


# ==================== 常用预设 ====================

def create_api_retry_policy() -> ExponentialBackoffRetry:
    """
    创建 API 调用重试策略
    
    适用于 Claude API、外部 API 等
    """
    return ExponentialBackoffRetry(
        config=ExponentialBackoffConfig(
            max_retries=3,
            base_delay=1.0,
            max_delay=30.0,
            jitter=True,
            retryable_exceptions=(
                ConnectionError,
                TimeoutError,
                # 可以添加更多 API 特定异常
            )
        )
    )


def create_tool_execution_retry_policy() -> ExponentialBackoffRetry:
    """
    创建工具执行重试策略
    
    适用于 E2B 沙箱、MCP 工具等
    """
    return ExponentialBackoffRetry(
        config=ExponentialBackoffConfig(
            max_retries=2,
            base_delay=2.0,
            max_delay=20.0,
            jitter=True,
        )
    )
