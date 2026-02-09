"""
Usage 响应模型 - 统一的 Token 使用信息

提供：
- Token 统计（input/output/thinking/cache）
- 性能指标（延迟、调用次数）
- UsageTracker: 使用量追踪器
"""

from typing import Any, Dict, List, Optional, Set
from datetime import datetime
from pydantic import BaseModel, Field

from logger import get_logger

logger = get_logger(__name__)


class LLMCallRecord(BaseModel):
    """单次 LLM 调用记录"""

    call_id: str = Field(..., description="调用唯一标识")
    message_id: Optional[str] = Field(None, description="Claude Message ID")
    model: str = Field(..., description="模型名称")
    purpose: str = Field(..., description="调用目的")
    timestamp: datetime = Field(default_factory=datetime.now)

    input_tokens: int = Field(0, description="输入 tokens")
    output_tokens: int = Field(0, description="输出 tokens")
    thinking_tokens: int = Field(0, description="Extended Thinking tokens")
    cache_read_tokens: int = Field(0, description="缓存读取 tokens")
    cache_write_tokens: int = Field(0, description="缓存创建 tokens")

    latency_ms: int = Field(0, description="响应延迟（毫秒）")

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens + self.thinking_tokens + self.cache_read_tokens

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


class ToolCallRecord(BaseModel):
    """工具调用记录"""

    call_id: str = Field(..., description="调用标识")
    count: int = Field(..., description="调用次数")
    tool_name: str = Field(..., description="工具名称")


class UsageResponse(BaseModel):
    """Usage 响应"""

    prompt_tokens: int = Field(0, description="总输入 tokens")
    completion_tokens: int = Field(0, description="总输出 tokens")
    thinking_tokens: int = Field(0, description="总 thinking tokens")
    cache_read_tokens: int = Field(0, description="总缓存读取 tokens")
    cache_write_tokens: int = Field(0, description="总缓存创建 tokens")
    total_tokens: int = Field(0, description="总 tokens")

    latency: float = Field(0.0, description="总延迟（秒）")
    llm_calls: int = Field(0, description="LLM 调用次数")

    model: str = Field("unknown", description="主模型名称")
    cache_hit_rate: float = Field(0.0, description="缓存命中率")

    llm_call_details: List[LLMCallRecord] = Field(default_factory=list)
    tool_call_details: List[ToolCallRecord] = Field(default_factory=list)

    @classmethod
    def from_tracker(
        cls,
        tracker: "UsageTracker",
        latency: float = 0.0,
        model: Optional[str] = None,
    ) -> "UsageResponse":
        """从 UsageTracker 创建响应。

        Args:
            tracker: Token 使用量追踪器
            latency: 总延迟（秒）
            model: Agent 主模型名称。未传时从 tracker 第一次调用推断。
        """
        if not tracker.calls and not tracker.tool_calls:
            return cls(model=model or "unknown")

        total_input = sum(call.input_tokens for call in tracker.calls)
        total_output = sum(call.output_tokens for call in tracker.calls)
        total_thinking = sum(call.thinking_tokens for call in tracker.calls)
        total_cache_read = sum(call.cache_read_tokens for call in tracker.calls)
        total_cache_write = sum(call.cache_write_tokens for call in tracker.calls)

        total_prompt_tokens = total_input + total_cache_read + total_cache_write

        cache_hit_rate = (
            total_cache_read / (total_input + total_cache_read)
            if (total_input + total_cache_read) > 0
            else 0.0
        )

        resolved_model = model or (tracker.calls[0].model if tracker.calls else "unknown")

        return cls(
            prompt_tokens=total_prompt_tokens,
            completion_tokens=total_output,
            thinking_tokens=total_thinking,
            cache_read_tokens=total_cache_read,
            cache_write_tokens=total_cache_write,
            total_tokens=total_prompt_tokens + total_output + total_thinking,
            latency=latency,
            llm_calls=len(tracker.calls),
            model=resolved_model,
            cache_hit_rate=round(cache_hit_rate, 4),
            llm_call_details=tracker.calls,
            tool_call_details=list(tracker.tool_calls.values()),
        )

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


class UsageSummary(BaseModel):
    """使用量摘要"""

    period: str = Field(..., description="统计周期")
    start_time: str = Field(..., description="开始时间")
    end_time: str = Field(..., description="结束时间")

    total_prompt_tokens: int = Field(0)
    total_completion_tokens: int = Field(0)
    total_thinking_tokens: int = Field(0)
    total_cache_read_tokens: int = Field(0)
    total_cache_write_tokens: int = Field(0)
    total_tokens: int = Field(0)

    total_requests: int = Field(0)
    total_llm_calls: int = Field(0)

    average_latency: Optional[float] = Field(None)
    cache_hit_rate: float = Field(0.0)
    average_tokens_per_request: float = Field(0.0)


class UsageTracker:
    """Usage Tracker - Token 统计"""

    def __init__(self):
        self.calls: List[LLMCallRecord] = []
        self._call_counter = 0
        self._seen_message_ids: Set[str] = set()
        self.tool_calls: Dict[str, ToolCallRecord] = {}
        self._tool_call_counter = 0

    def record_call(
        self,
        llm_response,
        model: str,
        purpose: str = "main_response",
        latency_ms: int = 0,
        message_id: Optional[str] = None,
    ) -> Optional[LLMCallRecord]:
        """记录一次 LLM 调用"""
        if message_id and message_id in self._seen_message_ids:
            return None

        usage = getattr(llm_response, "usage", None) or {}

        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)
        thinking_tokens = usage.get("thinking_tokens", 0)
        cache_read_tokens = usage.get("cache_read_tokens", 0)
        cache_write_tokens = usage.get("cache_creation_tokens", 0) or usage.get(
            "cache_write_tokens", 0
        )

        if input_tokens == 0 and output_tokens == 0:
            return None

        self._call_counter += 1
        record = LLMCallRecord(
            call_id=f"call_{self._call_counter:03d}",
            message_id=message_id,
            model=model,
            purpose=purpose,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            thinking_tokens=thinking_tokens,
            cache_read_tokens=cache_read_tokens,
            cache_write_tokens=cache_write_tokens,
            latency_ms=latency_ms,
        )

        self.calls.append(record)

        if message_id:
            self._seen_message_ids.add(message_id)

        return record

    def record_tool_call(
        self, tool_name: str, success: bool = True, params: Optional[Dict[str, Any]] = None
    ) -> Optional[ToolCallRecord]:
        """记录工具调用"""
        if not success:
            return None

        billing_key = tool_name
        if tool_name == "api_calling" and params and params.get("api_name"):
            billing_key = params["api_name"]

        if billing_key in self.tool_calls:
            record = self.tool_calls[billing_key]
            record.count += 1
        else:
            self._tool_call_counter += 1
            record = ToolCallRecord(
                call_id=f"tool_call_{self._tool_call_counter:03d}",
                count=1,
                tool_name=billing_key,
            )
            self.tool_calls[billing_key] = record

        return record

    def accumulate(self, llm_response, model: str = None, purpose: str = "main_response") -> None:
        """累积 LLM 响应的 usage 统计"""
        if not llm_response:
            return

        if model is None:
            model = getattr(llm_response, "model", None) or "unknown"

        message_id = getattr(llm_response, "id", None)
        self.record_call(llm_response=llm_response, model=model, purpose=purpose, message_id=message_id)

    def accumulate_from_dict(self, usage_dict: dict, model: str = "claude-sonnet-4") -> None:
        """从字典累积 usage"""
        if not usage_dict:
            return

        class MockResponse:
            usage = usage_dict

        self.record_call(llm_response=MockResponse(), model=model, purpose="from_dict")

    def get_stats(self) -> dict:
        """获取统计数据"""
        return {
            "total_input_tokens": sum(c.input_tokens for c in self.calls),
            "total_output_tokens": sum(c.output_tokens for c in self.calls),
            "total_thinking_tokens": sum(c.thinking_tokens for c in self.calls),
            "total_cache_read_tokens": sum(c.cache_read_tokens for c in self.calls),
            "total_cache_creation_tokens": sum(c.cache_write_tokens for c in self.calls),
            "llm_calls": len(self.calls),
            "tool_calls": len(self.tool_calls),
            "total_tool_count": sum(record.count for record in self.tool_calls.values()),
        }

    def get_total_tokens(self) -> int:
        """获取总 token 数"""
        return sum(c.input_tokens + c.output_tokens + c.thinking_tokens for c in self.calls)

    def estimate_cost(self) -> Optional[float]:
        """
        Estimate cumulative cost in USD based on actual model pricing.

        Resolves pricing from ModelRegistry per-model (supports mixed-model
        calls within one query). Returns None if all models have unknown pricing
        (e.g. private deployments).
        """
        if not self.calls:
            return None

        from core.llm.model_registry import ModelRegistry

        total_cost = 0.0
        has_pricing = False

        for call in self.calls:
            config = ModelRegistry.get(call.model)
            if not config or config.pricing.is_free:
                continue

            call_cost = config.pricing.estimate_cost(
                input_tokens=call.input_tokens,
                output_tokens=call.output_tokens,
                cache_read_tokens=call.cache_read_tokens,
                cache_write_tokens=call.cache_write_tokens,
            )
            if call_cost is not None:
                total_cost += call_cost
                has_pricing = True

        return total_cost if has_pricing else None

    def reset(self):
        """重置 tracker"""
        self.calls.clear()
        self._seen_message_ids.clear()
        self._call_counter = 0
        self.tool_calls.clear()
        self._tool_call_counter = 0

    def snapshot(self) -> dict:
        """创建统计快照"""
        stats = self.get_stats()
        total_tokens = self.get_total_tokens()
        total_input_tokens = stats["total_input_tokens"]
        total_cache_read_tokens = stats["total_cache_read_tokens"]

        return {
            **stats,
            "total_tokens": total_tokens,
            "average_input_per_call": (
                total_input_tokens / stats["llm_calls"] if stats["llm_calls"] > 0 else 0
            ),
            "average_output_per_call": (
                stats["total_output_tokens"] / stats["llm_calls"] if stats["llm_calls"] > 0 else 0
            ),
            "cache_hit_rate": (
                total_cache_read_tokens / (total_input_tokens + total_cache_read_tokens)
                if (total_input_tokens + total_cache_read_tokens) > 0
                else 0
            ),
        }


def create_usage_tracker() -> UsageTracker:
    """创建 UsageTracker 实例"""
    return UsageTracker()


__all__ = [
    "UsageResponse",
    "LLMCallRecord",
    "ToolCallRecord",
    "UsageSummary",
    "UsageTracker",
    "create_usage_tracker",
]
