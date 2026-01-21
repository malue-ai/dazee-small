"""
Enhanced Usage Tracker

支持多模型调用记录和 Message ID 去重

关键特性：
1. 记录每次 LLM 调用的完整信息（模型、tokens、价格）
2. 支持多模型混合调用
3. 自动计算价格明细
4. 基于 Message ID 去重（遵循 Claude SDK 最佳实践）
5. 🆕 V7.5.1: 工具调用计费（按工具聚合）
"""

from logger import get_logger
from typing import List, Optional, Set, Dict, Any
from core.billing.models import LLMCallRecord, ToolCallRecord
from core.billing.pricing import get_pricing_for_model, calculate_cost
from core.billing.tool_pricing import get_tool_pricing, calculate_tool_cost

logger = get_logger(__name__)


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
        # LLM 调用记录
        self.calls: List[LLMCallRecord] = []  # 所有调用记录
        self._call_counter = 0
        self._seen_message_ids: Set[str] = set()  # 已处理的 Message ID（去重）
        
        # 🆕 V7.5.1: 工具调用记录（按工具聚合）
        self.tool_calls: Dict[str, ToolCallRecord] = {}  # key: tool_name, value: ToolCallRecord
        self._tool_call_counter = 0
    
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
    
    def record_tool_call(
        self,
        tool_name: str,
        success: bool = True,
        params: Optional[Dict[str, Any]] = None
    ) -> Optional[ToolCallRecord]:
        """
        记录工具调用（按工具聚合）
        
        设计原则：
        - 按工具聚合：同一工具只有一个 call_id，count 累加
        - 调用成功后记录：失败不计费
        - 免费工具也记录：tool_price = 0.0
        - 支持通用工具：api_calling 等通过 params 识别实际服务
        
        Args:
            tool_name: 工具名称
            success: 是否成功（失败不计费）
            params: 工具参数（可选，用于 api_calling 等通用工具的价格查询和聚合）
            
        Returns:
            ToolCallRecord 对象，如果失败则返回 None
            
        示例：
            # 普通工具调用
            tracker.record_tool_call("web_search", success=True)
            tracker.record_tool_call("web_search", success=True)  # count 累加
            
            # api_calling 工具调用（按 api_name 聚合）
            tracker.record_tool_call("api_calling", success=True, params={"api_name": "wenshu_api"})
            tracker.record_tool_call("api_calling", success=True, params={"api_name": "wenshu_api"})  # 按 wenshu_api 聚合
            
            # 工具调用失败（不计费）
            tracker.record_tool_call("web_search", success=False)  # 返回 None
        """
        # 失败不计费
        if not success:
            logger.debug(f"⚠️ 工具调用失败，不计费: tool_name={tool_name}")
            return None
        
        # 🔧 获取工具价格（传递 params 用于价格查询）
        tool_price = get_tool_pricing(tool_name, params=params)
        
        # 🔑 生成 billing_key（用于聚合）
        # 对于 api_calling，使用 api_name 作为聚合键
        billing_key = tool_name
        display_name = tool_name
        
        if tool_name == "api_calling" and params and params.get("api_name"):
            api_name = params["api_name"]
            billing_key = api_name  # 使用 api_name 作为聚合键
            display_name = api_name  # 显示名称也用 api_name
            logger.debug(
                f"🔑 api_calling 计费聚合: tool_name={tool_name}, "
                f"api_name={api_name}, billing_key={billing_key}"
            )
        
        # 检查是否已记录过该工具（使用 billing_key）
        if billing_key in self.tool_calls:
            # 已存在：累加 count 和 total_price
            record = self.tool_calls[billing_key]
            record.count += 1
            record.total_price = calculate_tool_cost(tool_name, record.count, params=params)
            
            logger.debug(
                f"📊 工具调用累加: billing_key={billing_key}, count={record.count}, "
                f"total_price=${record.total_price:.6f}"
            )
        else:
            # 新工具：创建记录
            self._tool_call_counter += 1
            call_id = f"tool_call_{self._tool_call_counter:03d}"
            
            record = ToolCallRecord(
                call_id=call_id,
                count=1,
                tool_name=display_name,  # 使用 display_name（可能是 api_name）
                tool_price=tool_price,
                total_price=tool_price
            )
            
            self.tool_calls[billing_key] = record
            
            logger.debug(
                f"📊 记录工具调用: billing_key={billing_key}, "
                f"display_name={display_name}, price=${tool_price:.6f}"
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
        # 🆕 V7.5.1: 清空工具调用记录
        self.tool_calls.clear()
        self._tool_call_counter = 0
        logger.debug("🔄 UsageTracker 已重置")
    
    # ========== 向后兼容方法（兼容旧版 UsageTracker 接口）==========
    
    def accumulate(
        self, 
        llm_response, 
        model: str = None,
        purpose: str = "main_response"
    ) -> None:
        """
        向后兼容：累积 LLM 响应的 usage 统计
        
        这是旧版 UsageTracker.accumulate() 的兼容接口。
        内部调用 record_call() 实现完整功能。
        
        Args:
            llm_response: LLMResponse 对象（需要有 usage 属性）
            model: 模型名称（如果 llm_response 有 model 属性则使用它）
            purpose: 调用目的
        """
        if not llm_response:
            return
        
        # 从 llm_response 获取模型名称
        if model is None:
            model = getattr(llm_response, 'model', None) or "claude-sonnet-4.5"
        
        # 从 llm_response 获取 message_id（用于去重）
        message_id = getattr(llm_response, 'id', None)
        
        # 调用新版 record_call
        self.record_call(
            llm_response=llm_response,
            model=model,
            purpose=purpose,
            message_id=message_id
        )
    
    def accumulate_from_dict(self, usage_dict: dict, model: str = "claude-sonnet-4.5") -> None:
        """
        向后兼容：从字典累积 usage
        
        Args:
            usage_dict: usage 字典，包含 input_tokens, output_tokens 等
            model: 模型名称
        """
        if not usage_dict:
            return
        
        # 创建一个模拟的 response 对象
        class MockResponse:
            usage = usage_dict
        
        self.record_call(
            llm_response=MockResponse(),
            model=model,
            purpose="from_dict"
        )
    
    def get_stats(self) -> dict:
        """
        向后兼容：获取当前统计数据（与旧版 UsageTracker.get_stats() 格式兼容）
        
        Returns:
            统计字典（与旧版格式完全一致 + 🆕 V7.5.1 工具调用统计）
        """
        return {
            # LLM 统计
            "total_input_tokens": sum(c.input_tokens for c in self.calls),
            "total_output_tokens": sum(c.output_tokens for c in self.calls),
            "total_thinking_tokens": sum(c.thinking_tokens for c in self.calls),
            "total_cache_read_tokens": sum(c.cache_read_tokens for c in self.calls),
            "total_cache_creation_tokens": sum(c.cache_write_tokens for c in self.calls),  # 注意：旧版用 creation
            "llm_calls": len(self.calls),
            # 🆕 V7.5.1: 工具调用统计
            "tool_calls": len(self.tool_calls),
            "total_tool_count": sum(record.count for record in self.tool_calls.values()),
            "tool_total_price": sum(record.total_price for record in self.tool_calls.values())
        }
    
    def get_total_tokens(self) -> int:
        """
        向后兼容：获取总 token 数
        
        Returns:
            总 token 数（input + output + thinking）
        """
        return sum(
            c.input_tokens + c.output_tokens + c.thinking_tokens
            for c in self.calls
        )
    
    def get_cost_estimate(
        self,
        input_price_per_mtok: float = None,  # 忽略，使用实际定价
        output_price_per_mtok: float = None,
        cache_read_price_per_mtok: float = None,
        cache_creation_price_per_mtok: float = None
    ) -> float:
        """
        向后兼容：估算成本
        
        注意：此方法忽略传入的价格参数，使用实际的模型定价。
        
        Returns:
            总成本（USD）
        """
        return sum(c.total_price for c in self.calls)
    
    def snapshot(self) -> dict:
        """
        向后兼容：创建当前统计的快照
        
        Returns:
            包含统计和计算信息的字典
        """
        stats = self.get_stats()
        total_tokens = self.get_total_tokens()
        total_input_tokens = stats["total_input_tokens"]
        total_cache_read_tokens = stats["total_cache_read_tokens"]
        
        return {
            **stats,
            "total_tokens": total_tokens,
            "estimated_cost_usd": self.get_cost_estimate(),
            "average_input_per_call": (
                total_input_tokens / stats["llm_calls"]
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
                total_cache_read_tokens /
                (total_input_tokens + total_cache_read_tokens)
                if (total_input_tokens + total_cache_read_tokens) > 0
                else 0
            )
        }
    
    def __repr__(self) -> str:
        """字符串表示"""
        stats = self.get_stats()
        return (
            f"EnhancedUsageTracker("
            f"calls={stats['llm_calls']}, "
            f"input={stats['total_input_tokens']}, "
            f"output={stats['total_output_tokens']}, "
            f"thinking={stats['total_thinking_tokens']}, "
            f"total={self.get_total_tokens()})"
        )


def create_enhanced_usage_tracker() -> EnhancedUsageTracker:
    """
    创建 EnhancedUsageTracker 实例（工厂函数）
    
    Returns:
        EnhancedUsageTracker 实例
    """
    return EnhancedUsageTracker()