"""
重试机制模块

提供带指数退避的智能重试装饰器
"""

import asyncio
import functools
from typing import TypeVar, Callable, Any, Tuple, Type
from dataclasses import dataclass
import time

from logger import get_logger

logger = get_logger(__name__)

T = TypeVar('T')


@dataclass
class RetryConfig:
    """重试配置"""
    max_retries: int = 3                    # 最大重试次数
    base_delay: float = 0.5                 # 基础延迟（秒）
    max_delay: float = 60.0                 # 最大延迟（秒）
    exponential_base: float = 2.0           # 指数退避基数
    retryable_errors: Tuple[Type[Exception], ...] = (
        ConnectionError,
        TimeoutError,
        asyncio.TimeoutError,
    )
    
    def __post_init__(self):
        """添加常见的可重试 HTTP 错误码"""
        # 429: Too Many Requests
        # 503: Service Unavailable
        # 502: Bad Gateway
        # 504: Gateway Timeout
        self.retryable_status_codes = {429, 502, 503, 504}


# 全局重试配置实例
_retry_config = RetryConfig()


def get_retry_config() -> RetryConfig:
    """获取全局重试配置"""
    return _retry_config


def set_retry_config(config: RetryConfig):
    """设置全局重试配置"""
    global _retry_config
    _retry_config = config
    logger.info(f"✅ 重试配置已更新: max_retries={config.max_retries}, base_delay={config.base_delay}s")


def _calculate_delay(attempt: int, base_delay: float, exponential_base: float, max_delay: float) -> float:
    """
    计算指数退避延迟
    
    Args:
        attempt: 当前重试次数（从 0 开始）
        base_delay: 基础延迟
        exponential_base: 指数基数
        max_delay: 最大延迟
        
    Returns:
        延迟时间（秒）
    """
    delay = base_delay * (exponential_base ** attempt)
    return min(delay, max_delay)


def _is_retryable_error(
    error: Exception, 
    retryable_errors: Tuple[Type[Exception], ...],
    retryable_status_codes: set = None
) -> bool:
    """
    判断错误是否可重试
    
    Args:
        error: 异常对象
        retryable_errors: 可重试的异常类型元组
        retryable_status_codes: 可重试的状态码集合
        
    Returns:
        是否可重试
    """
    # 检查异常类型
    if isinstance(error, retryable_errors):
        return True
    
    # 检查 HTTP 状态码（如果是 HTTP 相关异常）
    if retryable_status_codes and hasattr(error, 'status_code'):
        return error.status_code in retryable_status_codes
    
    # 检查异常消息中是否包含可重试的关键词
    error_str = str(error).lower()
    retryable_keywords = ['timeout', 'connection', 'unavailable', 'rate limit']
    return any(keyword in error_str for keyword in retryable_keywords)


def with_retry(
    max_retries: int = None,
    base_delay: float = None,
    retryable_errors: Tuple[Type[Exception], ...] = None
):
    """
    重试装饰器
    
    Args:
        max_retries: 最大重试次数
        base_delay: 基础延迟（秒）
        retryable_errors: 可重试的异常类型
        
    Returns:
        装饰器函数
        
    使用示例:
        @with_retry(max_retries=3, base_delay=1.0)
        async def call_external_api():
            ...
    """
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            config = get_retry_config()
            
            # 使用传入参数或配置默认值
            actual_max_retries = max_retries if max_retries is not None else config.max_retries
            actual_base_delay = base_delay if base_delay is not None else config.base_delay
            actual_retryable_errors = retryable_errors if retryable_errors is not None else config.retryable_errors
            
            last_exception = None
            
            for attempt in range(actual_max_retries + 1):
                try:
                    # 尝试执行函数
                    result = await func(*args, **kwargs)
                    
                    # 如果之前有重试，记录成功日志
                    if attempt > 0:
                        logger.info(f"✅ {func.__name__} 重试成功 (尝试 {attempt + 1}/{actual_max_retries + 1})")
                    
                    return result
                    
                except Exception as e:
                    last_exception = e
                    
                    # 检查是否可重试
                    if not _is_retryable_error(e, actual_retryable_errors, config.retryable_status_codes):
                        logger.error(f"❌ {func.__name__} 失败（不可重试）: {str(e)}")
                        raise
                    
                    # 如果已达最大重试次数，抛出异常
                    if attempt >= actual_max_retries:
                        logger.error(
                            f"❌ {func.__name__} 失败（已达最大重试次数 {actual_max_retries}）: {str(e)}"
                        )
                        raise
                    
                    # 计算延迟时间
                    delay = _calculate_delay(
                        attempt,
                        actual_base_delay,
                        config.exponential_base,
                        config.max_delay
                    )
                    
                    logger.warning(
                        f"⚠️ {func.__name__} 失败，{delay:.2f}s 后重试 "
                        f"(尝试 {attempt + 1}/{actual_max_retries + 1}): {str(e)}"
                    )
                    
                    # 等待后重试
                    await asyncio.sleep(delay)
            
            # 理论上不会到达这里，但为了类型检查完整性
            if last_exception:
                raise last_exception
        
        return wrapper
    return decorator


async def retry_async(
    func: Callable[..., Any],
    *args,
    max_retries: int = None,
    base_delay: float = None,
    **kwargs
) -> Any:
    """
    函数式重试接口（不使用装饰器）
    
    Args:
        func: 要执行的异步函数
        *args: 函数参数
        max_retries: 最大重试次数
        base_delay: 基础延迟
        **kwargs: 函数关键字参数
        
    Returns:
        函数执行结果
        
    使用示例:
        result = await retry_async(call_api, url="...", max_retries=3)
    """
    decorated = with_retry(max_retries=max_retries, base_delay=base_delay)(func)
    return await decorated(*args, **kwargs)
