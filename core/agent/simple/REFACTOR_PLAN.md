# 单智能体架构 V8.0

## 一、架构设计

```
core/agent/simple/
├── __init__.py                 # 统一导出 + 工厂函数
├── simple_agent.py             # SimpleAgent（核心实现）
├── rvrb_agent.py               # RVRBAgent（继承 + Mixin）
├── mixins/
│   ├── __init__.py
│   ├── stream_mixin.py         # 流式处理
│   ├── tool_mixin.py           # 工具执行
│   └── backtrack_mixin.py      # 回溯能力
├── errors.py                   # 错误处理
├── simple_agent_context.py     # 上下文构建
├── simple_agent_loop.py        # RVRLoopMixin
└── simple_agent_tools.py       # ToolExecutionMixin
```

## 二、类继承关系

```
SimpleAgent
├── ToolExecutionMixin      # 工具执行能力
└── RVRLoopMixin            # 标准 RVR 循环
        ↓
RVRBAgent(SimpleAgent, BacktrackMixin)
├── SimpleAgent             # 继承所有基础能力
└── BacktrackMixin          # 混入回溯能力
```

## 三、Mixin 设计

### BacktrackMixin

```python
class BacktrackMixin:
    """回溯能力 Mixin"""
    
    # 初始化
    def _init_backtrack(self, max_backtracks):
        ...
    
    # 状态管理
    def _get_rvrb_state(self, session_id) -> RVRBState:
        ...
    
    # 回溯评估
    async def _evaluate_backtrack(self, error, ...) -> BacktrackResult:
        ...
    
    # 错误处理（带回溯）
    async def _handle_tool_error_with_backtrack(self, ...) -> tuple:
        ...
    
    # 替代工具
    async def _try_alternative_tool(self, ...) -> Optional[str]:
        ...
    
    # RVR-B 主循环
    async def _run_rvr_loop_with_backtrack(self, ...) -> AsyncGenerator:
        ...
```

### RVRBAgent 实现

```python
class RVRBAgent(SimpleAgent, BacktrackMixin):
    """继承 + Mixin"""
    
    def __init__(self, max_backtracks=3, **kwargs):
        SimpleAgent.__init__(self, **kwargs)
        BacktrackMixin._init_backtrack(self, max_backtracks)
    
    async def _run_rvr_loop(self, ...):
        # 委托给 BacktrackMixin
        async for event in self._run_rvr_loop_with_backtrack(...):
            yield event
```

## 四、调用关系

```
IntentAnalyzer.analyze()
    │
    └── LLM 输出 execution_strategy: "rvr" | "rvr-b"
            │
            ▼
AgentRouter.route()
    │
    └── RoutingDecision.execution_strategy（从 IntentResult 传递）
            │
            ▼
AgentFactory._create_simple_agent()
    │
    ├── execution_strategy == "rvr"   → SimpleAgent
    │
    └── execution_strategy == "rvr-b" → RVRBAgent
    
AgentFactory.from_schema() → SimpleAgent（Schema 驱动，无策略分流）

create_simple_agent(strategy="rvr-b") → RVRBAgent（直接工厂）
```

### 路由决策驱动（V8.0）

**完全依赖 LLM 语义判断，移除所有硬编码阈值。**

#### 单/多智能体选择（needs_multi_agent）

| 维度 | 单智能体 (false) | 多智能体 (true) |
|------|-----------------|-----------------|
| 子任务数量 | 1 个主任务 | 3+ 个独立子任务 |
| 子任务依赖 | 串行依赖 | 互相独立/可并行 |
| 实体数量 | 单一对象 | 多个独立实体 |

#### 执行策略选择（execution_strategy）

| 场景 | execution_strategy | 说明 |
|------|-------------------|------|
| 简单问答 | rvr | 标准循环，无回溯开销 |
| 单工具调用 | rvr | 确定性结果 |
| 多步骤任务 | rvr-b | 可能需要策略调整 |
| 探索性任务 | rvr-b | 结果不确定，需回溯 |
| 可能失败需重试 | rvr-b | 工具替换/参数调整 |

### 全局导出路径

```
zenflux_agent/
├── __init__.py              # SimpleAgent, RVRBAgent, create_simple_agent
├── core/
│   ├── __init__.py          # SimpleAgent, RVRBAgent, create_simple_agent
│   └── agent/
│       ├── __init__.py      # SimpleAgent, RVRBAgent, create_simple_agent
│       ├── factory.py       # AgentFactory (import SimpleAgent, RVRBAgent)
│       └── simple/
│           └── __init__.py  # SimpleAgent, RVRBAgent, create_simple_agent
```

### 调用入口

| 入口 | 说明 | 使用场景 |
|------|------|----------|
| `AgentCoordinator.route_and_execute()` | 推荐入口 | 生产环境 |
| `AgentFactory.create_from_decision()` | 路由决策驱动 | 已有路由结果时 |
| `AgentFactory.from_schema()` | Schema 驱动 | 实例级配置 |
| `create_simple_agent(strategy=...)` | 直接创建 | 测试/调试 |

## 五、代码行数

| 文件 | 行数 | 职责 |
|------|------|------|
| `simple_agent.py` | ~1050 | 核心实现 |
| `rvrb_agent.py` | ~140 | 继承 + 委托 |
| `backtrack_mixin.py` | ~450 | 回溯逻辑 |
| `simple_agent_loop.py` | ~450 | RVRLoopMixin |
| `simple_agent_tools.py` | ~300 | ToolExecutionMixin |

## 六、使用方式

```python
# SimpleAgent（标准 RVR）
from core.agent.simple import SimpleAgent
agent = SimpleAgent(event_manager=em)

# RVRBAgent（RVR + 回溯）
from core.agent.simple import RVRBAgent
agent = RVRBAgent(event_manager=em, max_backtracks=3)

# 工厂函数
from core.agent.simple import create_simple_agent
agent = create_simple_agent(strategy="rvr-b", event_manager=em)
```

## 七、复杂度分流

| 复杂度 | Agent | 说明 |
|--------|-------|------|
| 0-4 | SimpleAgent | 标准 RVR，无回溯 |
| 4-7 | RVRBAgent | RVR + 回溯 |
| 7+ | MultiAgentOrchestrator | 完整 DAG |
