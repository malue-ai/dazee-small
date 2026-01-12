"""
背压控制

流量控制，防止系统过载

参考白皮书 3.1 节：
- Token 桶算法：高效、允许突发、平滑节流
- 自适应并发控制：自动寻找最优吞吐量
"""

import asyncio
import time
from dataclasses import dataclass
from typing import TypeVar, Callable, Awaitable, Optional
from functools import wraps

from logger import get_logger

logger = get_logger("backpressure")

T = TypeVar("T")


class TokenBucketExhaustedError(Exception):
    """令牌桶耗尽错误"""
    
    def __init__(self, bucket_name: str, wait_time: float):
        self.bucket_name = bucket_name
        self.wait_time = wait_time
        super().__init__(
            f"令牌桶 '{bucket_name}' 已耗尽，"
            f"需等待 {wait_time:.2f}秒"
        )


@dataclass
class TokenBucketConfig:
    """令牌桶配置"""
    capacity: int = 10                  # 桶容量
    refill_rate: float = 1.0            # 令牌补充速率（个/秒）
    initial_tokens: Optional[int] = None  # 初始令牌数，默认等于容量


class TokenBucket:
    """
    令牌桶
    
    特性：
    - 固定容量
    - 固定速率补充令牌
    - 允许突发流量（最多消耗桶容量）
    
    使用示例：
        bucket = TokenBucket(name="claude_api", config=TokenBucketConfig(
            capacity=10,
            refill_rate=1.0  # 每秒补充 1 个令牌
        ))
        
        # 获取令牌（阻塞直到有令牌）
        await bucket.acquire()
        await api_call()
        
        # 或者使用 context manager
        async with bucket:
            await api_call()
    """
    
    def __init__(
        self,
        name: str,
        config: TokenBucketConfig = None
    ):
        """
        初始化令牌桶
        
        Args:
            name: 令牌桶名称
            config: 配置
        """
        self.name = name
        self.config = config or TokenBucketConfig()
        
        # 当前令牌数
        initial = self.config.initial_tokens
        if initial is None:
            initial = self.config.capacity
        self._tokens = float(initial)
        
        # 上次更新时间
        self._last_update = time.time()
        
        # 锁
        self._lock = asyncio.Lock()
        
        logger.info(
            f"令牌桶 '{name}' 初始化完成: "
            f"容量={self.config.capacity}, "
            f"速率={self.config.refill_rate}/s"
        )
    
    @property
    def tokens(self) -> float:
        """获取当前令牌数"""
        return self._tokens
    
    async def acquire(
        self,
        tokens: int = 1,
        blocking: bool = True,
        timeout: float = None
    ) -> bool:
        """
        获取令牌
        
        Args:
            tokens: 需要的令牌数
            blocking: 是否阻塞等待
            timeout: 超时时间（秒），None 表示无限等待
            
        Returns:
            是否成功获取
            
        Raises:
            TokenBucketExhaustedError: 非阻塞模式下令牌不足
        """
        start_time = time.time()
        
        while True:
            async with self._lock:
                # 补充令牌
                self._refill()
                
                # 检查令牌是否足够
                if self._tokens >= tokens:
                    self._tokens -= tokens
                    return True
                
                # 计算等待时间
                tokens_needed = tokens - self._tokens
                wait_time = tokens_needed / self.config.refill_rate
            
            # 非阻塞模式
            if not blocking:
                raise TokenBucketExhaustedError(self.name, wait_time)
            
            # 检查超时
            if timeout is not None:
                elapsed = time.time() - start_time
                if elapsed >= timeout:
                    raise TokenBucketExhaustedError(self.name, wait_time)
                wait_time = min(wait_time, timeout - elapsed)
            
            # 等待
            logger.debug(
                f"令牌桶 '{self.name}' 等待 {wait_time:.2f}秒"
            )
            await asyncio.sleep(wait_time)
    
    def _refill(self):
        """补充令牌"""
        now = time.time()
        elapsed = now - self._last_update
        
        # 计算补充的令牌数
        new_tokens = elapsed * self.config.refill_rate
        self._tokens = min(self._tokens + new_tokens, self.config.capacity)
        self._last_update = now
    
    async def __aenter__(self):
        """Context manager 入口"""
        await self.acquire()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager 出口"""
        pass
    
    def get_status(self) -> dict:
        """获取状态"""
        return {
            "name": self.name,
            "tokens": self._tokens,
            "capacity": self.config.capacity,
            "refill_rate": self.config.refill_rate,
        }


class BackpressureController:
    """
    背压控制器
    
    管理多个令牌桶，实现细粒度的流量控制
    
    使用示例：
        controller = BackpressureController()
        controller.register_bucket("claude_api", TokenBucketConfig(
            capacity=10,
            refill_rate=2.0
        ))
        controller.register_bucket("e2b_sandbox", TokenBucketConfig(
            capacity=5,
            refill_rate=0.5
        ))
        
        # 获取令牌
        await controller.acquire("claude_api")
        await api_call()
    """
    
    def __init__(self):
        """初始化背压控制器"""
        self._buckets: dict[str, TokenBucket] = {}
        self._lock = asyncio.Lock()
        
        logger.info("背压控制器初始化完成")
    
    def register_bucket(
        self,
        name: str,
        config: TokenBucketConfig = None
    ) -> TokenBucket:
        """
        注册令牌桶
        
        Args:
            name: 令牌桶名称
            config: 配置
            
        Returns:
            创建的令牌桶
        """
        bucket = TokenBucket(name=name, config=config)
        self._buckets[name] = bucket
        return bucket
    
    def get_bucket(self, name: str) -> Optional[TokenBucket]:
        """获取令牌桶"""
        return self._buckets.get(name)
    
    async def acquire(
        self,
        bucket_name: str,
        tokens: int = 1,
        blocking: bool = True,
        timeout: float = None
    ) -> bool:
        """
        从指定桶获取令牌
        """
        bucket = self._buckets.get(bucket_name)
        if not bucket:
            logger.warning(f"令牌桶 '{bucket_name}' 不存在，跳过流量控制")
            return True
        
        return await bucket.acquire(
            tokens=tokens,
            blocking=blocking,
            timeout=timeout
        )
    
    def get_status(self) -> dict:
        """获取所有令牌桶状态"""
        return {
            name: bucket.get_status()
            for name, bucket in self._buckets.items()
        }


# ==================== 装饰器版本 ====================

def rate_limit(
    bucket_name: str,
    capacity: int = 10,
    refill_rate: float = 1.0
):
    """
    速率限制装饰器
    
    使用示例：
        @rate_limit(bucket_name="claude_api", capacity=10, refill_rate=2.0)
        async def call_api():
            ...
    """
    # 全局桶注册表
    _buckets: dict[str, TokenBucket] = {}
    
    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            # 获取或创建令牌桶
            if bucket_name not in _buckets:
                _buckets[bucket_name] = TokenBucket(
                    name=bucket_name,
                    config=TokenBucketConfig(
                        capacity=capacity,
                        refill_rate=refill_rate
                    )
                )
            
            bucket = _buckets[bucket_name]
            await bucket.acquire()
            
            return await func(*args, **kwargs)
        
        return wrapper
    
    return decorator
