"""
Mixture-of-Agents (MoA) 模块

V8.0 新增模块

提供多模型协作能力：
1. AdaptiveMoARouter - 自适应 MoA 路由，关键决策点启用
2. MoAAggregator - Aggregate-and-Synthesize 响应聚合

设计原则：
- 选择性 MoA：只在关键决策点启用多模型协作，避免成本膨胀
- 成本可控：监控 MoA 调用成本，动态调整策略
- 可观测：完整的调用链路追踪
"""

from core.llm.moa.router import (
    AdaptiveMoARouter,
    MoADecisionPoint,
    MoAConfig,
    MoAResult,
    create_moa_router,
)

from core.llm.moa.aggregator import (
    MoAAggregator,
    AggregationStrategy,
    AggregatedResponse,
    create_moa_aggregator,
)

__all__ = [
    # 路由器
    "AdaptiveMoARouter",
    "MoADecisionPoint",
    "MoAConfig",
    "MoAResult",
    "create_moa_router",
    # 聚合器
    "MoAAggregator",
    "AggregationStrategy",
    "AggregatedResponse",
    "create_moa_aggregator",
]
