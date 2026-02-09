"""
ZenFlux Agent 路由模块 V11.0

实现智能体路由决策：
1. IntentAnalyzer - 意图分析（complexity、skip_memory、is_follow_up）
2. AgentRouter - 路由决策器（固定 RVR-B 执行策略）
3. IntentSemanticCache - 意图识别语义缓存

架构原则（V11.0 小搭子简化版）：
- 意图识别输出极简 JSON：complexity, skip_memory, is_follow_up
- 固定使用 RVR-B 执行策略
- 代码从 complexity 推断 needs_plan

使用方式：
    from core.routing import AgentRouter

    router = AgentRouter(llm_service=claude)
    decision = await router.route(user_query, conversation_history)

    # 固定 rvr-b
    await agent.execute(strategy="rvr-b")
"""

from core.routing.intent_analyzer import IntentAnalyzer, create_intent_analyzer
from core.routing.intent_cache import (
    IntentCacheConfig,
    IntentSemanticCache,
    get_intent_cache,
)
from core.routing.router import AgentRouter, RoutingDecision

# 类型定义
from core.routing.types import Complexity, IntentResult

__all__ = [
    # 路由
    "AgentRouter",
    "RoutingDecision",
    # 意图分析
    "IntentAnalyzer",
    "create_intent_analyzer",
    # 语义缓存
    "IntentSemanticCache",
    "IntentCacheConfig",
    "get_intent_cache",
    # 类型定义
    "IntentResult",
    "Complexity",
]
