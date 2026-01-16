"""
Usage Tracker - Token 使用统计跟踪器

职责：
- 累积多次 LLM 调用的 token 使用情况
- 提供统计数据查询
- 支持重置和快照

设计原则：
- 独立模块：可被任何 Agent 复用
- 线程安全：支持异步环境
- 易于测试：纯数据操作
"""

from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class UsageTracker:
    """
    Token 使用统计跟踪器
    
    用于累积一个对话中所有 LLM 调用的 token 使用情况。
    
    使用示例：
        tracker = UsageTracker()
        
        # 累积 LLM 响应
        tracker.accumulate(llm_response)
        
        # 获取统计
        stats = tracker.get_stats()
        print(f"总 input tokens: {stats['total_input_tokens']}")
        
        # 重置（新对话开始时）
        tracker.reset()
    """
    
    def __init__(self):
        """初始化 UsageTracker"""
        self._stats = self._create_empty_stats()
    
    def _create_empty_stats(self) -> Dict[str, int]:
        """创建空统计字典"""
        return {
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "total_thinking_tokens": 0,  # 🆕 Extended Thinking tokens
            "total_cache_read_tokens": 0,
            "total_cache_creation_tokens": 0,
            "llm_calls": 0
        }
    
    def accumulate(self, llm_response) -> None:
        """
        累积 LLM 响应的 usage 统计
        
        Args:
            llm_response: LLMResponse 对象（需要有 usage 属性）
        """
        if not llm_response:
            return
        
        # 从 LLMResponse 中提取 usage
        usage = getattr(llm_response, 'usage', None)
        if not usage:
            logger.debug("LLM 响应中没有 usage 信息")
            return
        
        # 累积各项统计
        self._stats["total_input_tokens"] += usage.get("input_tokens", 0)
        self._stats["total_output_tokens"] += usage.get("output_tokens", 0)
        self._stats["total_thinking_tokens"] += usage.get("thinking_tokens", 0)  # 🆕
        self._stats["total_cache_read_tokens"] += usage.get("cache_read_tokens", 0)
        self._stats["total_cache_creation_tokens"] += usage.get("cache_creation_tokens", 0)
        self._stats["llm_calls"] += 1
        
        logger.debug(
            f"📊 Usage 累积: "
            f"input={usage.get('input_tokens', 0)}, "
            f"output={usage.get('output_tokens', 0)}, "
            f"thinking={usage.get('thinking_tokens', 0)}, "
            f"cache_read={usage.get('cache_read_tokens', 0)}, "
            f"总计: input={self._stats['total_input_tokens']}, "
            f"output={self._stats['total_output_tokens']}, "
            f"thinking={self._stats['total_thinking_tokens']}, "
            f"calls={self._stats['llm_calls']}"
        )
    
    def accumulate_from_dict(self, usage_dict: Dict[str, int]) -> None:
        """
        从字典累积 usage（用于非 LLMResponse 的情况）
        
        Args:
            usage_dict: usage 字典，包含 input_tokens, output_tokens 等
        """
        if not usage_dict:
            return
        
        self._stats["total_input_tokens"] += usage_dict.get("input_tokens", 0)
        self._stats["total_output_tokens"] += usage_dict.get("output_tokens", 0)
        self._stats["total_thinking_tokens"] += usage_dict.get("thinking_tokens", 0)  # 🆕
        self._stats["total_cache_read_tokens"] += usage_dict.get("cache_read_tokens", 0)
        self._stats["total_cache_creation_tokens"] += usage_dict.get("cache_creation_tokens", 0)
        self._stats["llm_calls"] += 1
    
    def get_stats(self) -> Dict[str, int]:
        """
        获取当前统计数据（副本）
        
        Returns:
            统计字典的副本
        """
        return self._stats.copy()
    
    def get_total_tokens(self) -> int:
        """
        获取总 token 数（input + output + thinking）
        
        Returns:
            总 token 数
        """
        return (
            self._stats["total_input_tokens"] + 
            self._stats["total_output_tokens"] +
            self._stats["total_thinking_tokens"]
        )
    
    def get_cost_estimate(
        self,
        input_price_per_mtok: float = 3.0,
        output_price_per_mtok: float = 15.0,
        cache_read_price_per_mtok: float = 0.3,
        cache_creation_price_per_mtok: float = 3.75
    ) -> float:
        """
        估算成本（美元）
        
        默认价格基于 Claude Sonnet 4.5:
        - Input: $3 / 1M tokens
        - Output: $15 / 1M tokens
        - Cache Read: $0.30 / 1M tokens
        - Cache Creation: $3.75 / 1M tokens
        
        Args:
            input_price_per_mtok: Input token 价格（每百万 tokens）
            output_price_per_mtok: Output token 价格（每百万 tokens）
            cache_read_price_per_mtok: Cache read 价格（每百万 tokens）
            cache_creation_price_per_mtok: Cache creation 价格（每百万 tokens）
            
        Returns:
            估算成本（美元）
        """
        input_cost = (self._stats["total_input_tokens"] / 1_000_000) * input_price_per_mtok
        output_cost = (self._stats["total_output_tokens"] / 1_000_000) * output_price_per_mtok
        cache_read_cost = (self._stats["total_cache_read_tokens"] / 1_000_000) * cache_read_price_per_mtok
        cache_creation_cost = (self._stats["total_cache_creation_tokens"] / 1_000_000) * cache_creation_price_per_mtok
        
        return input_cost + output_cost + cache_read_cost + cache_creation_cost
    
    def reset(self) -> None:
        """重置所有统计（在新对话开始时调用）"""
        self._stats = self._create_empty_stats()
        logger.debug("🔄 Usage 统计已重置")
    
    def snapshot(self) -> Dict[str, Any]:
        """
        创建当前统计的快照（包含额外计算信息）
        
        Returns:
            包含统计和计算信息的字典
        """
        stats = self.get_stats()
        return {
            **stats,
            "total_tokens": self.get_total_tokens(),
            "estimated_cost_usd": self.get_cost_estimate(),
            "average_input_per_call": (
                stats["total_input_tokens"] / stats["llm_calls"] 
                if stats["llm_calls"] > 0 else 0
            ),
            "average_output_per_call": (
                stats["total_output_tokens"] / stats["llm_calls"] 
                if stats["llm_calls"] > 0 else 0
            ),
            "average_thinking_per_call": (
                stats["total_thinking_tokens"] / stats["llm_calls"] 
                if stats["llm_calls"] > 0 else 0
            ),
            "cache_hit_rate": (
                stats["total_cache_read_tokens"] / 
                (stats["total_input_tokens"] + stats["total_cache_read_tokens"])
                if (stats["total_input_tokens"] + stats["total_cache_read_tokens"]) > 0 
                else 0
            )
        }
    
    def __repr__(self) -> str:
        """字符串表示"""
        return (
            f"UsageTracker("
            f"calls={self._stats['llm_calls']}, "
            f"input={self._stats['total_input_tokens']}, "
            f"output={self._stats['total_output_tokens']}, "
            f"thinking={self._stats['total_thinking_tokens']}, "
            f"total={self.get_total_tokens()})"
        )
    
    def to_usage_response(
        self,
        model: str = "claude-sonnet-4.5",
        latency: Optional[float] = None
    ):
        """
        转换为 UsageResponse（用于 API 响应）
        
        Args:
            model: 模型名称
            latency: 响应延迟（秒）
            
        Returns:
            UsageResponse 实例
        """
        from models.usage import UsageResponse
        return UsageResponse.from_usage_tracker(
            tracker=self,
            model=model,
            latency=latency
        )


def create_usage_tracker() -> UsageTracker:
    """
    创建 UsageTracker 实例（工厂函数）
    
    Returns:
        UsageTracker 实例
    """
    return UsageTracker()

