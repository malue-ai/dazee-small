"""
Billing 数据模型

定义计费相关的核心数据结构：
- LLMCallRecord: 单次 LLM 调用记录
- UsageResponse: 完整的 Usage 响应（Dify 兼容 + 多模型支持）

所有价格字段使用 float 类型（单位：USD），方便前端处理和计算
"""

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


class LLMCallRecord(BaseModel):
    """
    单次 LLM 调用的完整记录
    
    用于记录每次调用的详细信息（模型、tokens、价格等）
    支持 Message ID 去重，避免重复计费
    """
    # 基础信息
    call_id: str = Field(..., description="调用唯一标识")
    message_id: Optional[str] = Field(None, description="Claude Message ID（用于去重）")
    model: str = Field(..., description="模型名称，如 claude-sonnet-4.5")
    purpose: str = Field(..., description="调用目的，如 intent_analysis, main_response")
    timestamp: datetime = Field(default_factory=datetime.now)
    
    # Token 统计
    input_tokens: int = Field(0, description="输入 tokens")
    output_tokens: int = Field(0, description="输出 tokens")
    thinking_tokens: int = Field(0, description="Extended Thinking tokens")
    cache_read_tokens: int = Field(0, description="缓存读取 tokens")
    cache_write_tokens: int = Field(0, description="缓存创建 tokens")
    
    # 单价（USD/百万tokens）- float 类型
    input_unit_price: float = Field(..., description="输入单价（USD/百万tokens），如 3.0")
    output_unit_price: float = Field(..., description="输出单价（USD/百万tokens），如 15.0")
    cache_read_unit_price: float = Field(0.0, description="缓存读取单价")
    cache_write_unit_price: float = Field(0.0, description="缓存创建单价")
    
    # 总价（USD）- float 类型
    input_total_price: float = Field(0.0, description="输入总价（USD）")
    output_total_price: float = Field(0.0, description="输出总价（USD）")
    thinking_total_price: float = Field(0.0, description="Thinking 总价（USD）")
    cache_read_price: float = Field(0.0, description="缓存读取价格（USD）")
    cache_write_price: float = Field(0.0, description="缓存创建价格（USD）")
    total_price: float = Field(0.0, description="本次调用总价（USD）")
    
    # 性能指标
    latency_ms: int = Field(0, description="响应延迟（毫秒）")
    
    # 元数据
    metadata: dict = Field(default_factory=dict, description="额外元数据")
    
    @property
    def total_tokens(self) -> int:
        """总 tokens = input + output + thinking + cache_read（反映真实使用量）"""
        return self.input_tokens + self.output_tokens + self.thinking_tokens + self.cache_read_tokens
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class UsageResponse(BaseModel):
    """
    完整的 Usage 响应（Dify 兼容 + 多模型支持）
    
    所有价格字段使用 float 类型（单位：USD），方便前端处理和计算
    
    遵循 Claude SDK 最佳实践：
    - 基于 Message ID 去重，避免重复计费
    - 累积所有调用的使用量
    - 提供详细的调用明细
    """
    # 累积统计（所有调用的总和）
    # 遵循 Claude Platform 规范：prompt_tokens = input_tokens + cache_read_tokens + cache_write_tokens
    prompt_tokens: int = Field(0, description="总输入 tokens（包含 input + cache_read + cache_write）")
    completion_tokens: int = Field(0, description="总输出 tokens")
    thinking_tokens: int = Field(0, description="总 thinking tokens")
    cache_read_tokens: int = Field(0, description="总缓存读取 tokens")
    cache_write_tokens: int = Field(0, description="总缓存创建 tokens")
    total_tokens: int = Field(0, description="总 tokens")
    
    # 累积价格（所有调用的总价，USD）- float 类型
    prompt_price: float = Field(0.0, description="总输入价格（USD）")
    completion_price: float = Field(0.0, description="总输出价格（USD）")
    thinking_price: float = Field(0.0, description="总 thinking 价格（USD）")
    cache_read_price: float = Field(0.0, description="总缓存读取价格（USD）")
    cache_write_price: float = Field(0.0, description="总缓存创建价格（USD）")
    total_price: float = Field(0.0, description="总价格（USD）")
    
    # 平均单价（加权平均，USD/百万tokens）- float 类型
    prompt_unit_price: float = Field(0.0, description="平均输入单价（USD/百万tokens）")
    completion_unit_price: float = Field(0.0, description="平均输出单价（USD/百万tokens）")
    currency: str = Field("USD", description="货币")
    
    # 性能指标
    latency: float = Field(0.0, description="总延迟（秒）")
    llm_calls: int = Field(0, description="LLM 调用次数")
    
    # 主模型信息（向后兼容）
    model: str = Field("unknown", description="主模型名称")
    
    # 缓存效果
    cache_hit_rate: float = Field(0.0, description="缓存命中率（0.0-1.0）")
    cost_saved_by_cache: float = Field(0.0, description="缓存节省的成本（USD）")
    
    # 🆕 多模型调用明细
    llm_call_details: List[LLMCallRecord] = Field(
        default_factory=list,
        description="每次 LLM 调用的详细记录"
    )
    
    @classmethod
    def from_tracker(
        cls,
        tracker: 'EnhancedUsageTracker',
        latency: float = 0.0
    ) -> 'UsageResponse':
        """
        从增强的 UsageTracker 创建响应
        
        Args:
            tracker: EnhancedUsageTracker 实例
            latency: 总延迟（秒）
            
        Returns:
            UsageResponse 对象
        """
        if not tracker.calls:
            return cls()
        
        # 累积所有调用的统计
        total_input = sum(call.input_tokens for call in tracker.calls)
        total_output = sum(call.output_tokens for call in tracker.calls)
        total_thinking = sum(call.thinking_tokens for call in tracker.calls)
        total_cache_read = sum(call.cache_read_tokens for call in tracker.calls)
        total_cache_write = sum(call.cache_write_tokens for call in tracker.calls)
        
        # 累积所有调用的价格（直接相加，因为都是 float）
        total_input_price = sum(call.input_total_price for call in tracker.calls)
        total_output_price = sum(call.output_total_price for call in tracker.calls)
        total_thinking_price = sum(call.thinking_total_price for call in tracker.calls)
        total_cache_read_price = sum(call.cache_read_price for call in tracker.calls)
        total_cache_write_price = sum(call.cache_write_price for call in tracker.calls)
        
        # 计算加权平均单价（考虑所有输入 tokens，包括缓存）
        # prompt_unit_price 基于 total_prompt_tokens（input + cache_read + cache_write）
        total_prompt_tokens_for_weighting = total_input + total_cache_read + total_cache_write
        if total_prompt_tokens_for_weighting > 0:
            # 加权平均：考虑 input_tokens、cache_read_tokens、cache_write_tokens 各自的单价
            weighted_input_price = (
                sum(call.input_tokens * call.input_unit_price for call in tracker.calls) +
                sum(call.cache_read_tokens * call.cache_read_unit_price for call in tracker.calls) +
                sum(call.cache_write_tokens * call.cache_write_unit_price for call in tracker.calls)
            ) / total_prompt_tokens_for_weighting
        else:
            weighted_input_price = 0.0
        
        weighted_output_price = (
            sum(call.output_tokens * call.output_unit_price for call in tracker.calls) 
            / total_output if total_output > 0 else 0.0
        )
        
        # 计算缓存命中率和节省的成本
        cache_hit_rate = (
            total_cache_read / (total_input + total_cache_read)
            if (total_input + total_cache_read) > 0 else 0.0
        )
        cost_saved_by_cache = sum(
            call.cache_read_tokens * (call.input_unit_price - call.cache_read_unit_price) / 1_000_000
            for call in tracker.calls
        )
        
        # 根据 Claude Platform 规范：total_input_tokens = input_tokens + cache_read_tokens + cache_write_tokens
        # 这三个字段是独立的：input_tokens 是未缓存部分，cache_read/write 是缓存部分
        total_prompt_tokens = total_input + total_cache_read + total_cache_write
        
        return cls(
            prompt_tokens=total_prompt_tokens,  # 包含 input + cache_read + cache_write
            completion_tokens=total_output,
            thinking_tokens=total_thinking,
            cache_read_tokens=total_cache_read,
            cache_write_tokens=total_cache_write,
            total_tokens=total_prompt_tokens + total_output + total_thinking,  # 包含所有输入 tokens（含缓存）
            prompt_price=round(total_input_price, 6),  # 只包含 input_tokens 的价格（不含缓存）
            completion_price=round(total_output_price, 6),
            thinking_price=round(total_thinking_price, 6),
            cache_read_price=round(total_cache_read_price, 6),
            cache_write_price=round(total_cache_write_price, 6),
            total_price=round(
                total_input_price + total_output_price + total_thinking_price 
                + total_cache_read_price + total_cache_write_price, 
                6
            ),
            prompt_unit_price=round(weighted_input_price, 2),
            completion_unit_price=round(weighted_output_price, 2),
            latency=latency,
            llm_calls=len(tracker.calls),
            model=tracker.calls[0].model if tracker.calls else "unknown",
            cache_hit_rate=round(cache_hit_rate, 4),
            cost_saved_by_cache=round(cost_saved_by_cache, 6),
            llm_call_details=tracker.calls  # 🔥 关键：包含所有调用明细
        )
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


# 类型注解（避免循环导入）
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from core.billing.tracker import EnhancedUsageTracker
