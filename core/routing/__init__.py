"""
ZenFlux Agent 路由模块 V10.1

实现智能体路由决策：
1. IntentAnalyzer - 意图分析（只输出 3 个核心字段）
2. AgentRouter - 路由决策器（直接使用 agent_type 作为执行策略）
3. IntentSemanticCache - 意图识别语义缓存

架构原则（LLM-First）：
- 意图识别输出极简 JSON：complexity, agent_type, skip_memory
- agent_type 统一为执行策略：rvr | rvr-b | multi
- 代码从 complexity 推断 needs_plan, execution_strategy

使用方式：
    from core.routing import AgentRouter

    router = AgentRouter(llm_service=claude)
    decision = await router.route(user_query, conversation_history)

    # V10.1: agent_type 是执行策略，使用 is_multi_agent 判断
    if decision.is_multi_agent:
        result = await multi_agent.execute(decision)
    else:
        result = await agent.execute(strategy=decision.agent_type)
"""

from core.routing.intent_analyzer import IntentAnalyzer, create_intent_analyzer
from core.routing.intent_cache import (
    IntentCacheConfig,
    IntentSemanticCache,
    get_intent_cache,
)
from core.routing.router import AgentRouter, RoutingDecision

# 类型定义（V10.1 迁移到 core.routing.types，消除反向依赖）
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
