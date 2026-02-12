"""
降级策略模块

提供服务降级和回退机制
"""

from typing import Callable, Any, Optional, Dict
from enum import Enum
import functools

from logger import get_logger

logger = get_logger(__name__)


class FallbackType(Enum):
    """降级类型"""
    CACHED_RESPONSE = "cached_response"      # 返回缓存响应
    DEFAULT_RESPONSE = "default_response"    # 返回默认响应
    SKIP = "skip"                            # 跳过该步骤
    SIMPLIFIED = "simplified"                # 使用简化版本


class FallbackStrategy:
    """
    降级策略
    
    使用示例:
        strategy = FallbackStrategy()
        strategy.register("llm_service", lambda: {"response": "服务暂时不可用"})
        
        @strategy.with_fallback("llm_service")
        async def call_llm():
            ...
    """
    
    def __init__(self):
        self._fallbacks: Dict[str, Callable] = {}
    
    def register(
        self,
        service_name: str,
        fallback_func: Callable[..., Any],
        fallback_type: FallbackType = FallbackType.DEFAULT_RESPONSE
    ):
        """
        注册降级策略
        
        Args:
            service_name: 服务名称
            fallback_func: 降级函数
            fallback_type: 降级类型
        """
        self._fallbacks[service_name] = {
            "func": fallback_func,
            "type": fallback_type
        }
        logger.info(f"✅ 降级策略已注册: {service_name} (type={fallback_type.value})")
    
    def get_fallback(self, service_name: str) -> Optional[dict]:
        """获取降级策略"""
        return self._fallbacks.get(service_name)
    
    def with_fallback(self, service_name: str):
        """
        降级装饰器
        
        Args:
            service_name: 服务名称
            
        Returns:
            装饰器函数
        """
        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            @functools.wraps(func)
            async def wrapper(*args, **kwargs):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    # 获取降级策略
                    fallback = self.get_fallback(service_name)
                    
                    if fallback is None:
                        # 没有降级策略，直接抛出异常
                        logger.error(f"❌ {service_name} 失败且无降级策略: {str(e)}")
                        raise
                    
                    # 执行降级
                    fallback_func = fallback["func"]
                    fallback_type = fallback["type"]
                    
                    logger.warning(
                        f"⚠️ {service_name} 失败，触发降级 (type={fallback_type.value}): {str(e)}"
                    )
                    
                    # 调用降级函数
                    if asyncio.iscoroutinefunction(fallback_func):
                        result = await fallback_func(*args, **kwargs)
                    else:
                        result = fallback_func(*args, **kwargs)
                    
                    # 添加降级标记
                    if isinstance(result, dict):
                        result["_fallback"] = True
                        result["_fallback_type"] = fallback_type.value
                    
                    return result
            
            return wrapper
        return decorator


# 全局降级策略实例
_global_fallback_strategy = FallbackStrategy()


def get_fallback_strategy() -> FallbackStrategy:
    """获取全局降级策略"""
    return _global_fallback_strategy


def register_fallback(
    service_name: str,
    fallback_func: Callable[..., Any],
    fallback_type: FallbackType = FallbackType.DEFAULT_RESPONSE
):
    """
    注册全局降级策略（便捷函数）
    
    Args:
        service_name: 服务名称
        fallback_func: 降级函数
        fallback_type: 降级类型
    """
    _global_fallback_strategy.register(service_name, fallback_func, fallback_type)


# 预定义的常用降级响应

def default_llm_fallback(*args, **kwargs) -> dict:
    """LLM 服务默认降级响应"""
    return {
        "success": False,
        "content": "AI 服务暂时不可用，请稍后重试",
        "error": "llm_service_unavailable"
    }


def default_tool_fallback(*args, **kwargs) -> dict:
    """工具服务默认降级响应"""
    return {
        "success": False,
        "error": "工具暂时不可用",
        "skipped": True
    }


def default_database_fallback(*args, **kwargs) -> dict:
    """数据库服务默认降级响应"""
    return {
        "success": False,
        "error": "数据库连接失败",
        "cached": False
    }


# 导入 asyncio（用于降级装饰器）
import asyncio
