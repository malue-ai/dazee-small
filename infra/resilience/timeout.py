"""
超时控制模块

提供统一的异步超时控制装饰器和上下文管理器
"""

import asyncio
import functools
from typing import TypeVar, Callable, Any, Optional
from dataclasses import dataclass

from logger import get_logger

logger = get_logger(__name__)

T = TypeVar('T')


@dataclass
class TimeoutConfig:
    """超时配置"""
    llm_timeout: float = 60.0      # LLM 调用超时（秒）
    tool_timeout: float = 30.0     # 工具执行超时（秒）
    database_timeout: float = 5.0  # 数据库操作超时（秒）
    cache_timeout: float = 2.0     # 缓存操作超时（秒）
    default_timeout: float = 30.0  # 默认超时（秒）


# 全局超时配置实例
_timeout_config = TimeoutConfig()


def get_timeout_config() -> TimeoutConfig:
    """获取全局超时配置"""
    return _timeout_config


def set_timeout_config(config: TimeoutConfig):
    """设置全局超时配置"""
    global _timeout_config
    _timeout_config = config
    logger.info(f"✅ 超时配置已更新: LLM={config.llm_timeout}s, Tool={config.tool_timeout}s, DB={config.database_timeout}s")


def with_timeout(
    timeout: Optional[float] = None,
    timeout_type: str = "default"
):
    """
    超时装饰器
    
    Args:
        timeout: 超时时间（秒），如果为 None 则从配置读取
        timeout_type: 超时类型（llm/tool/database/cache/default）
        
    Returns:
        装饰器函数
        
    使用示例:
        @with_timeout(timeout=60, timeout_type="llm")
        async def call_llm():
            ...
            
        @with_timeout(timeout_type="tool")
        async def execute_tool():
            ...
    """
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # 确定超时时间
            if timeout is not None:
                actual_timeout = timeout
            else:
                config = get_timeout_config()
                timeout_map = {
                    "llm": config.llm_timeout,
                    "tool": config.tool_timeout,
                    "database": config.database_timeout,
                    "cache": config.cache_timeout,
                    "default": config.default_timeout,
                }
                actual_timeout = timeout_map.get(timeout_type, config.default_timeout)
            
            try:
                result = await asyncio.wait_for(
                    func(*args, **kwargs),
                    timeout=actual_timeout
                )
                return result
            except asyncio.TimeoutError:
                func_name = func.__name__
                logger.error(f"⏰ {func_name} 超时 ({actual_timeout}s)")
                raise TimeoutError(
                    f"{func_name} 执行超时 ({actual_timeout}s)"
                )
        
        return wrapper
    return decorator


class TimeoutContext:
    """
    超时上下文管理器
    
    使用示例:
        async with TimeoutContext(timeout=10):
            await long_running_task()
    """
    
    def __init__(self, timeout: float, timeout_type: str = "default"):
        self.timeout = timeout if timeout else get_timeout_config().default_timeout
        self.timeout_type = timeout_type
    
    async def __aenter__(self):
        self.task = asyncio.current_task()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        # 如果发生超时异常，记录日志
        if exc_type is asyncio.TimeoutError:
            logger.error(f"⏰ 上下文操作超时 ({self.timeout}s)")
        return False
