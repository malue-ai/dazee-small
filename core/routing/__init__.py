"""
ZenFlux Agent 路由模块

实现单智能体与多智能体的路由决策：
1. IntentAnalyzer - 意图分析（共享模块）
2. ComplexityScorer - 任务复杂度评分
3. AgentRouter - 路由决策器

架构原则：
- IntentAnalyzer 从 SimpleAgent 剥离，成为共享模块
- 单智能体和多智能体通过 AgentRouter 路由决策
- 两个框架完全独立，不互相调用

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
from core.routing.complexity_scorer import ComplexityScorer, ComplexityScore

__all__ = [
    "AgentRouter",
    "RoutingDecision",
    "ComplexityScorer",
    "ComplexityScore",
]
