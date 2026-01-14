"""
ZenFlux 多智能体框架

设计原则：
1. 与 SimpleAgent 完全独立，不存在互相调用关系
2. 通过路由层 (core/routing) 选择使用哪个框架
3. 支持并行和串行两种执行模式
4. 共享 core/routing/ 的意图分析和 core/planning/ 的计划协议

架构图：
```
                    ChatService
                        │
                        ▼
                   AgentRouter
                   /         \
                  /           \
        SimpleAgent    MultiAgentOrchestrator
        (单智能体)          (多智能体)
                              │
                    ┌─────────┼─────────┐
                    ▼         ▼         ▼
                 Agent1    Agent2    Agent3
                 (专家)    (审核)    (汇总)
```

执行模式：
- SEQUENTIAL: 串行执行（前一个 Agent 输出作为后一个输入）
- PARALLEL: 并行执行（多个 Agent 同时执行，结果汇总）
- HIERARCHICAL: 层级执行（主 Agent 分配任务给子 Agent）

使用方式：
    from core.agent.multi import MultiAgentOrchestrator, ExecutionMode
    
    orchestrator = MultiAgentOrchestrator(
        mode=ExecutionMode.SEQUENTIAL,
        agents=[
            {"role": "researcher", "model": "claude-sonnet"},
            {"role": "reviewer", "model": "claude-haiku"},
            {"role": "summarizer", "model": "claude-sonnet"}
        ]
    )
    
    async for event in orchestrator.execute(intent, messages):
        yield event
"""

from core.agent.multi.models import (
    ExecutionMode,
    AgentRole,
    AgentConfig,
    MultiAgentConfig,
    TaskAssignment,
    AgentResult,
    OrchestratorState,
)
from core.agent.multi.orchestrator import MultiAgentOrchestrator

__all__ = [
    # Models
    "ExecutionMode",
    "AgentRole",
    "AgentConfig",
    "MultiAgentConfig",
    "TaskAssignment",
    "AgentResult",
    "OrchestratorState",
    # Orchestrator
    "MultiAgentOrchestrator",
]
