"""
Enhanced Usage Tracker

支持多模型调用记录和 Message ID 去重

关键特性：
1. 记录每次 LLM 调用的完整信息（模型、tokens、价格）
2. 支持多模型混合调用
3. 自动计算价格明细
4. 基于 Message ID 去重（遵循 Claude SDK 最佳实践）
"""

import logging
from typing import List, Optional, Set
from core.billing.models import LLMCallRecord
from core.billing.pricing import get_pricing_for_model, calculate_cost

logger = logging.getLogger(__name__)


class EnhancedUsageTracker:
    """
    增强的 Usage Tracker - 支持多模型调用记录
    
    遵循 Claude SDK 最佳实践：
    - Same Message ID = Same Usage (相同消息 ID 使用量相同)
    - Charge Once Per Step (每个步骤只计费一次)
    - Use Message IDs for Deduplication (使用消息 ID 去重)
    
    使用示例：
        tracker = EnhancedUsageTracker()
        
        # 记录意图识别调用
        tracker.record_call(
            llm_response=intent_response,
            model="claude-haiku-4.5",
            purpose="intent_analysis"
        )
        
        # 记录主对话调用
        tracker.record_call(
            llm_response=main_response,
            model="claude-sonnet-4.5",
            purpose="main_response"
        )
        
        # 生成响应
        usage = UsageResponse.from_tracker(tracker, latency=4.0)
    """
    
    def __init__(self):
        self.calls: List[LLMCallRecord] = []  # 所有调用记录
        self._call_counter = 0
        self._seen_message_ids: Set[str] = set()  # 已处理的 Message ID（去重）
    
    def record_call(
        self,
        llm_response,
        model: str,
        purpose: str = "main_response",
        latency_ms: int = 0,
        message_id: Optional[str] = None
    ) -> Optional[LLMCallRecord]:
        """
        记录一次 LLM 调用
        
        Args:
            llm_response: LLMResponse 对象
            model: 模型名称（如 claude-sonnet-4.5）
            purpose: 调用目的（如 intent_analysis, main_response）
            latency_ms: 响应延迟（毫秒）
            message_id: Claude Message ID（可选，用于去重）
            
        Returns:
            LLMCallRecord 对象，如果是重复调用则返回 None
        """
        # Message ID 去重（遵循 Claude SDK 最佳实践）
        if message_id and message_id in self._seen_message_ids:
            logger.debug(f"⚠️ 跳过重复计费: message_id={message_id}")
            return None
        
        # 提取 usage（支持多种格式）
        usage = getattr(llm_response, 'usage', None) or {}
        
        # 提取 tokens
        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)
        thinking_tokens = usage.get("thinking_tokens", 0)
        cache_read_tokens = usage.get("cache_read_tokens", 0)
        cache_write_tokens = usage.get("cache_creation_tokens", 0) or usage.get("cache_write_tokens", 0)
        
        # 如果没有任何 tokens，跳过
        if input_tokens == 0 and output_tokens == 0:
            logger.debug(f"⚠️ 跳过空 usage: model={model}, purpose={purpose}")
            return None
        
        # 获取定价
        pricing = get_pricing_for_model(model)
        
        # 计算价格明细
        total_cost, cost_details = calculate_cost(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            thinking_tokens=thinking_tokens,
            cache_read_tokens=cache_read_tokens,
            cache_write_tokens=cache_write_tokens,
            model=model
        )
        
        # 创建记录（所有价格字段使用 float）
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
            # 单价（USD/百万tokens）
            input_unit_price=pricing['input'],
            output_unit_price=pricing['output'],
            cache_read_unit_price=pricing['cache_read'],
            cache_write_unit_price=pricing['cache_write'],
            # 总价（USD）
            input_total_price=cost_details['input_cost'],
            output_total_price=cost_details['output_cost'],
            thinking_total_price=cost_details['thinking_cost'],
            cache_read_price=cost_details['cache_read_cost'],
            cache_write_price=cost_details['cache_write_cost'],
            total_price=cost_details['total_cost'],
            latency_ms=latency_ms
        )
        
        # 记录到列表
        self.calls.append(record)
        
        # 标记 Message ID 为已处理
        if message_id:
            self._seen_message_ids.add(message_id)
        
        logger.debug(
            f"📊 记录 LLM 调用: model={model}, purpose={purpose}, "
            f"input={input_tokens}, output={output_tokens}, cost=${total_cost:.6f}"
        )
        
        return record
    
    def get_summary(self) -> dict:
        """
        获取累积汇总（向后兼容）
        
        Returns:
            汇总字典
        """
        return {
            "total_input_tokens": sum(c.input_tokens for c in self.calls),
            "total_output_tokens": sum(c.output_tokens for c in self.calls),
            "total_thinking_tokens": sum(c.thinking_tokens for c in self.calls),
            "total_cache_read_tokens": sum(c.cache_read_tokens for c in self.calls),
            "total_cache_write_tokens": sum(c.cache_write_tokens for c in self.calls),
            "llm_calls": len(self.calls),
            "total_cost": sum(c.total_price for c in self.calls)  # float 直接相加
        }
    
    def get_calls_by_model(self, model: str) -> List[LLMCallRecord]:
        """
        按模型筛选调用记录
        
        Args:
            model: 模型名称
            
        Returns:
            调用记录列表
        """
        return [c for c in self.calls if c.model == model]
    
    def get_calls_by_purpose(self, purpose: str) -> List[LLMCallRecord]:
        """
        按调用目的筛选记录
        
        Args:
            purpose: 调用目的
            
        Returns:
            调用记录列表
        """
        return [c for c in self.calls if c.purpose == purpose]
    
    def reset(self):
        """重置 tracker（清空所有记录）"""
        self.calls.clear()
        self._seen_message_ids.clear()
        self._call_counter = 0
        logger.debug("🔄 UsageTracker 已重置")
