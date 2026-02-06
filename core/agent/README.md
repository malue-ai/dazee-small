# core/agent — 统一智能体框架

基于 **Agent + Executor 策略模式** 的统一智能体实现。
单一 `Agent` 类 + 可插拔执行策略，新增策略只需实现 `ExecutorProtocol` 并注册。

---

## 架构总览

```
                        ┌──────────────────────┐
                        │     ChatService      │
                        └──────────┬───────────┘
                                   │
                        ┌──────────▼───────────┐
                        │  AgentCoordinator    │  ← 门面：route → create → execute
                        │  (coordinator.py)    │
                        └──────────┬───────────┘
                                   │
                    ┌──────────────┼──────────────┐
                    │              │              │
             ┌──────▼──────┐  ┌───▼────┐  ┌──────▼──────┐
             │ AgentRouter  │  │Factory │  │   Agent     │
             │(core/routing)│  │        │  │  (base.py)  │
             └─────────────┘  └────────┘  └──────┬──────┘
                                                  │
                                                  │ 委托
                                                  │
                                       ┌──────────▼──────────┐
                                       │   Executor(策略)     │
                                       ├─────────────────────┤
                                       │ • RVRExecutor        │
                                       │ • RVRBExecutor       │
                                       │ • MultiAgentExecutor │
                                       └──────────┬──────────┘
                                                   │
                                    ┌──────────────┼──────────────┐
                                    │              │              │
                             ┌──────▼──────┐ ┌────▼─────┐ ┌──────▼──────┐
                             │PromptBuilder│ │ToolFlow  │ │ Backtrack   │
                             │ (context/)  │ │(tools/)  │ │(backtrack/) │
                             └─────────────┘ └──────────┘ └─────────────┘
```

**核心分工：**

| 角色 | 职责 | 不做什么 |
|------|------|----------|
| **Agent** | 编排：工具选择、上下文管理、状态管理 | 不包含执行循环逻辑 |
| **Executor** | 执行：LLM 调用循环、流式处理、工具调用 | 不持有 Agent 状态 |
| **Factory** | 创建：组装 Agent + 注入 Executor | 不做路由决策 |
| **Coordinator** | 门面：路由 → 创建 → 执行 | 不包含业务逻辑 |

---

## 目录结构

```
core/agent/
│
│  # ━━━ 核心层 ━━━
│
├── protocol.py              # AgentProtocol — 统一接口定义（Protocol）
├── base.py                  # Agent — 唯一的智能体实现类
├── factory.py               # AgentFactory — 工厂 + Executor 注册表
├── coordinator.py           # AgentCoordinator — 门面入口
├── models.py                # 数据模型（AgentConfig, CriticResult...）
├── errors.py                # 统一错误处理
├── content_handler.py       # Content Block 处理器
│
│  # ━━━ 执行策略层 ━━━
│
├── execution/
│   ├── protocol.py          # ExecutorProtocol + BaseExecutor + ExecutionContext
│   ├── rvr.py               # RVRExecutor — 标准 React-Validate-Reflect 循环
│   ├── rvrb.py              # RVRBExecutor — RVR + 回溯（继承 RVRExecutor）
│   ├── multi.py             # MultiAgentExecutor — 多智能体适配器
│   └── _multi/              # 多智能体内部实现（不对外暴露）
│       ├── orchestrator.py  #   编排器核心（组合下方子模块）
│       ├── events.py        #   EventEmitter — 事件发送
│       ├── task_decomposer.py  # TaskDecomposer — 任务分解
│       ├── worker_runner.py    # WorkerRunner — Worker 执行（复用 RVRExecutor）
│       ├── critic_evaluator.py # CriticEvaluator — Critic 评估循环
│       └── result_aggregator.py # ResultAggregator — 结果聚合
│
│  # ━━━ 组合层（组装 core/* 的通用能力） ━━━
│
├── context/
│   └── prompt_builder.py    # System Prompt 构建（组合 core/context injectors）
│
├── tools/
│   ├── flow.py              # ToolExecutionFlow — 统一 tool_use → tool_result
│   └── special.py           # 特殊工具 Handler（plan_todo, HITL...）
│
│  # ━━━ 辅助模块 ━━━
│
├── backtrack/
│   ├── error_classifier.py  # 错误分类（ErrorLayer, BacktrackType...）
│   └── manager.py           # 回溯管理器
│
└── components/              # 多智能体共享组件
    ├── checkpoint.py        # 检查点管理
    ├── critic.py            # 评审智能体（CriticAgent）
    └── lead_agent.py        # 主控智能体（任务分解 + 结果综合）
```

---

## 多智能体架构（`_multi/`）

### 架构概述

V10.3 将 `MultiAgentOrchestrator`（原 ~1,900 行）拆分为 **组合模式**，职责单一：

```
                        ┌──────────────────────────┐
                        │ MultiAgentOrchestrator   │  ← 编排入口，组合下方子模块
                        │ (orchestrator.py)        │
                        └──────────┬───────────────┘
                                   │
              ┌────────────┬───────┼───────┬────────────┐
              │            │       │       │            │
     ┌────────▼──────┐ ┌──▼────┐ ┌▼─────┐ ┌▼──────────┐ ┌▼───────────┐
     │TaskDecomposer │ │Worker │ │Critic│ │Result     │ │Event       │
     │               │ │Runner │ │Eval  │ │Aggregator │ │Emitter     │
     └───────────────┘ └───────┘ └──────┘ └───────────┘ └────────────┘
           │                │        │           │             │
     调用 LeadAgent    复用 RVR   CriticAgent  LeadAgent    Broadcaster
     任务分解         Executor   pass/retry   结果综合      SSE 事件
                      统一循环   /replan
```

### 子模块职责

| 子模块 | 文件 | 职责 |
|--------|------|------|
| **TaskDecomposer** | `task_decomposer.py` | 调用 LeadAgent 将复杂任务分解为子任务（SubTask） |
| **WorkerRunner** | `worker_runner.py` | 执行单个 Worker，复用 RVRExecutor 统一循环，管理工具加载 |
| **CriticEvaluator** | `critic_evaluator.py` | 执行 → 评估循环，根据 CriticAgent 结果决定 pass/retry/replan |
| **ResultAggregator** | `result_aggregator.py` | 多 Worker 结果聚合，调用 LeadAgent 生成最终摘要 |
| **EventEmitter** | `events.py` | SSE 事件发送（编排开始/结束、子任务进度、错误等） |

### 执行流程

```
1. TaskDecomposer.decompose()
   └─ LeadAgent 分析用户请求 → TaskDecompositionPlan（子任务列表）

2. 根据 ExecutionMode 执行 Workers:
   ├─ SEQUENTIAL: 依次执行，前一个输出作为后一个上下文
   ├─ PARALLEL: asyncio.gather 并发执行独立子任务
   └─ HIERARCHICAL: 主控分配 + 依赖拓扑排序

3. CriticEvaluator.evaluate_and_retry()（如果启用 Critic）
   ├─ PASS → 继续下一个子任务
   ├─ RETRY → 重新执行当前 Worker（最多 N 次）
   ├─ REPLAN → 调用 LeadAgent 重新分解任务
   └─ FAIL → 标记失败，继续或中止

4. ResultAggregator.synthesize_with_lead_agent()
   └─ LeadAgent 综合所有 Worker 输出 → 最终回答
```

### 组件关系：components/ vs _multi/

```
components/              → 可复用的智能体组件（领域能力）
├── LeadAgent            → 任务分解 + 结果综合（调用 LLM）
├── CriticAgent          → 质量评估（调用 LLM）
└── CheckpointManager    → 状态快照

execution/_multi/        → 编排流程实现（流程控制）
├── TaskDecomposer       → 包装 LeadAgent.decompose()，处理异常和事件
├── WorkerRunner         → 包装 RVRExecutor，注入工具和上下文
├── CriticEvaluator      → 包装 CriticAgent.critique()，处理 retry/replan
├── ResultAggregator     → 包装 LeadAgent.synthesize()，构建 content blocks
└── EventEmitter         → SSE 事件格式化和发送
```

> **设计原则**：`components/` 是"能力"（做什么），`_multi/` 是"编排"（怎么做）。

### Worker 复用 RVRExecutor（V10.4）

Worker 执行不再维护独立的 LLM 调用循环，而是**复用 `RVRExecutor`**：

```python
# worker_runner.py 内部
from core.agent.execution.rvr import RVRExecutor

executor = RVRExecutor(config=ExecutorConfig(max_turns=10))
async for event in executor.execute(messages, context, config):
    # Worker 和单智能体走完全相同的 RVR 循环
    ...
```

好处：
- 工具调用、流式处理、Token 管理的逻辑只维护一份
- Worker 自动获得 RVR 循环的所有优化（上下文裁剪、工具校验等）

---

## 快速开始

### 创建并执行 Agent（推荐方式）

```python
from core.agent import create_agent

# 创建标准 RVR Agent
agent = await create_agent(
    strategy="rvr",
    event_manager=event_manager,
)

# 执行
async for event in agent.execute(
    messages=[{"role": "user", "content": "你好"}],
    session_id="session-123",
):
    print(event)
```

### 可用策略

| 策略 | 说明 | 适用场景 |
|------|------|----------|
| `rvr` | 标准 RVR 循环 | 单轮/多轮对话、工具调用 |
| `rvr-b` | RVR + 回溯 | 复杂任务、需容错和自动修复 |
| `multi` | 多智能体协作 | 任务分解、并行执行 |
| `sequential` | 串行多智能体 | 有依赖关系的子任务 |
| `parallel` | 并行多智能体 | 独立子任务并发 |
| `hierarchical` | 层级多智能体 | 复杂编排、质量评审 |

### 通过 Factory 创建（更多控制）

```python
from core.agent.factory import AgentFactory
from core.schemas import AgentSchema

# 从 Schema 创建
agent = await AgentFactory.from_schema(
    schema=AgentSchema(execution_strategy="rvr-b"),
    system_prompt="你是一个智能助手。",
    event_manager=event_manager,
)

# 从路由决策创建
agent = await AgentFactory.create_from_decision(
    decision=routing_decision,
    event_manager=event_manager,
)
```

### 通过 Coordinator 一站式调用（路由 + 创建 + 执行）

```python
from core.agent.coordinator import AgentCoordinator

coordinator = AgentCoordinator(router=agent_router)

async for event in coordinator.route_and_execute(
    messages=messages,
    session_id="session-123",
    user_id="user-456",
):
    yield event
```

---

## 核心接口

### AgentProtocol

```python
class AgentProtocol(Protocol):
    """所有 Agent 的统一接口，上层只依赖此协议"""

    @property
    def model(self) -> str: ...
    @property
    def schema(self) -> AgentSchema: ...
    @property
    def usage_stats(self) -> Dict[str, int]: ...

    async def execute(
        self,
        messages: List[Dict],
        session_id: str,
        intent: Optional[IntentResult] = None,
        enable_stream: bool = True,
        **kwargs,
    ) -> AsyncGenerator[Dict, None]: ...

    def clone_for_session(
        self,
        event_manager: EventBroadcaster,
        **kwargs,
    ) -> AgentProtocol: ...
```

### ExecutorProtocol

```python
class ExecutorProtocol(Protocol):
    """所有执行策略的统一接口"""

    @property
    def name(self) -> str: ...

    async def execute(
        self,
        messages: List[Dict],
        context: ExecutionContext,
        config: Optional[ExecutorConfig] = None,
        **kwargs,
    ) -> AsyncGenerator[Dict, None]: ...

    def supports_backtrack(self) -> bool: ...
```

---

## 扩展指南

### 新增执行策略

只需 3 步：

**1. 实现 Executor**

```python
# core/agent/execution/my_strategy.py

from core.agent.execution.protocol import BaseExecutor, ExecutionContext, ExecutorConfig

class MyStrategyExecutor(BaseExecutor):
    """自定义执行策略"""

    @property
    def name(self) -> str:
        return "my-strategy"

    async def execute(self, messages, context, config=None, **kwargs):
        cfg = config or self.config
        # 你的执行逻辑...
        yield {"event": "content_delta", "data": {"text": "hello"}}

    def supports_backtrack(self) -> bool:
        return False
```

**2. 注册到 Factory**

```python
# core/agent/factory.py → _get_executor_registry()

def _get_executor_registry() -> Dict[str, type]:
    from core.agent.execution.my_strategy import MyStrategyExecutor
    return {
        "rvr": RVRExecutor,
        "rvr-b": RVRBExecutor,
        "my-strategy": MyStrategyExecutor,  # ← 新增
        ...
    }
```

**3. 使用**

```python
agent = await create_agent(strategy="my-strategy", event_manager=em)
```

### 新增特殊工具 Handler

```python
# core/agent/tools/special.py

class MyToolHandler(SpecialToolHandler):
    """自定义特殊工具处理"""

    def can_handle(self, tool_name: str) -> bool:
        return tool_name == "my_special_tool"

    async def handle(self, tool_call, context) -> dict:
        # 特殊处理逻辑...
        return {"type": "tool_result", "content": "..."}
```

---

## 依赖方向

```
core/agent/  ──依赖──▶  core/context/    （上下文构建）
             ──依赖──▶  core/tool/       （工具执行）
             ──依赖──▶  core/routing/    （路由结果：IntentResult）
             ──依赖──▶  core/llm/        （LLM 调用）
             ──依赖──▶  core/events/     （事件广播）
             ──依赖──▶  core/billing/    （用量统计）
             ──依赖──▶  core/schemas/    （Schema 定义）

⚠️ 禁止反向依赖：core/context、core/tool、core/routing 不得 import core/agent
```

---

## 设计约束

| 约束 | 说明 |
|------|------|
| **意图识别唯一位置** | `core/routing/intent_analyzer.py`，Agent 层只消费 `IntentResult` |
| **LLM-First** | Agent 层禁止关键词匹配式语义判断 |
| **Executor 无状态** | Executor 是纯策略对象，通过 `ExecutionContext` 传递依赖 |
| **Agent 只做编排** | 执行循环、工具调用、流式处理全在 Executor |
| **Factory 只做创建** | 不包含路由决策、意图识别 |
