"""
Multi-Agent 编排模块 - V6.0

职责：
- 复杂任务的多 Agent 协作编排
- FSM 状态机管理任务生命周期
- LLM 语义任务分解
- 生产级容错（断路器、重试、背压）

设计原则：
- 与 SimpleAgent 平级，共享基础设施
- 复用 EventManager、MemoryManager、SemanticInference
- Prompt-First：任务分解规则写在 Prompt 里
- Memory-First：FSM 状态持久化到 PlanMemory

架构位置：
┌─────────────────────────────────────────────────────────────┐
│  services/chat_service.py                                   │
│      │                                                      │
│      ├─── SimpleAgent（单 Agent，V5.1）                     │
│      │                                                      │
│      └─── MultiAgentOrchestrator（多 Agent，V6.0）          │
│              │                                              │
│              ├── TaskDecomposer（LLM 语义分解）             │
│              ├── FSMEngine（状态机引擎）                    │
│              ├── WorkerScheduler（Worker 调度）             │
│              └── FaultToleranceLayer（容错层）              │
└─────────────────────────────────────────────────────────────┘

使用方式：
    from core.multi_agent import MultiAgentOrchestrator
    
    orchestrator = MultiAgentOrchestrator(
        event_manager=event_manager,
        memory_manager=memory_manager,
        prompt_cache=prompt_cache
    )
    
    async for event in orchestrator.execute(task, session_id):
        yield event
"""

from .orchestrator import MultiAgentOrchestrator, create_multi_agent_orchestrator
from .config import MultiAgentConfig, MultiAgentMode, WorkerConfig
from .fsm import FSMEngine, TaskState, TaskStatus
from .decomposition import TaskDecomposer
from .scheduling import WorkerScheduler
from .fault_tolerance import CircuitBreaker, RetryPolicy, FaultToleranceLayer

__all__ = [
    # 主类
    "MultiAgentOrchestrator",
    "create_multi_agent_orchestrator",
    
    # 配置
    "MultiAgentConfig",
    "MultiAgentMode",
    "WorkerConfig",
    
    # FSM
    "FSMEngine",
    "TaskState", 
    "TaskStatus",
    
    # 分解
    "TaskDecomposer",
    
    # 调度
    "WorkerScheduler",
    
    # 容错
    "CircuitBreaker",
    "RetryPolicy",
    "FaultToleranceLayer",
]
