"""
Usage Tracker - Token 使用统计跟踪器

职责：
- 累积多次 LLM 调用的 token 使用情况
- 记录每次调用的详细信息（model, purpose, tokens, price）
- 支持 Message ID 去重（避免重复计费）
- 提供统计数据查询和聚合

设计原则：
- 独立模块：可被任何 Agent 复用
- 线程安全：支持异步环境
- 易于测试：纯数据操作

使用示例：
    from utils.usage_tracker import UsageTracker
    
    # 创建 tracker
    tracker = UsageTracker()
    
    # 方式 1：简单累积（适用于单模型场景）
    tracker.accumulate(llm_response)
    
    # 方式 2：详细记录（推荐，支持多模型）
    tracker.record_call(
        llm_response=response,
        model="claude-sonnet-4",
        purpose="main_response",
        message_id=response.id  # 去重
    )
    
    # 获取统计
    stats = tracker.get_stats()
    
    # 生成 UsageResponse（包含调用明细）
    from models.usage import UsageResponse
    usage = UsageResponse.from_usage_tracker(
        tracker=tracker,
        model="claude-sonnet-4",
        latency=2.0
    )
"""

from core.billing.tracker import EnhancedUsageTracker, create_enhanced_usage_tracker

# UsageTracker 统一使用 EnhancedUsageTracker
UsageTracker = EnhancedUsageTracker
create_usage_tracker = create_enhanced_usage_tracker


__all__ = [
    "UsageTracker",
    "create_usage_tracker",
]
