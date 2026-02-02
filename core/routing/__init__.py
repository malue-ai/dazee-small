"""
ZenFlux Agent 路由模块

实现单智能体与多智能体的路由决策：
1. IntentAnalyzer - 意图分析（LLM 语义推理）
2. AgentRouter - 路由决策器
3. IntentSemanticCache - 意图识别语义缓存

架构原则（LLM-First）：
- 所有规则在 instance 系统提示词中用自然语言定义
- LLM 通过语义理解和深度推理输出判断结果
- 代码只负责传递 LLM 的判断，不做任何规则逻辑
- 不同场景只需修改提示词，代码无需变动

使用方式：
    from core.routing import AgentRouter
    
    router = AgentRouter(llm_service=claude)
    decision = await router.route(user_query, conversation_history)
    
    if decision.agent_type == "single":
        result = await simple_agent.chat(decision)
    else:
        result = await multi_agent.execute(decision)
"""

from core.routing.router import AgentRouter, RoutingDecision
from core.routing.intent_analyzer import IntentAnalyzer, create_intent_analyzer
from core.routing.intent_cache import (
    IntentSemanticCache,
    IntentCacheConfig,
    get_intent_cache,
)
# 重新导出 IntentResult 供外部使用
from core.agent.types import IntentResult, TaskType, Complexity

__all__ = [
    "AgentRouter",
    "RoutingDecision",
    # 意图分析
    "IntentAnalyzer",
    "create_intent_analyzer",
    # 语义缓存
    "IntentSemanticCache",
    "IntentCacheConfig",
    "get_intent_cache",
    # 重新导出
    "IntentResult",
    "TaskType",
    "Complexity",
]
