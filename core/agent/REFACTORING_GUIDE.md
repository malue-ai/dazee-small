## core/agent 重构执行指南（详细版 / 可交付实施）

> 目标读者：负责实施重构的工程师/自动化编码助手  
> 目标：把 `core/agent` 的**代码结构与设计模式**落地成可持续演进的形态，并提供**一步一步可验证**的实施清单。  
> 原则：**先跑通、再抽象、再变薄、最后减债**；每一步都可回滚。

---

## 0. 范围与硬规则

### 0.1 本次重构范围

- **优先重构 `core/agent/*` 内部结构**（execution/context/tools 子包的引入、职责切分、依赖收敛）。
- `services/chat_service.py` 当前已承担部分“门面（Facade）”职责；本指南提供两条接入路线：
  - **保守接入（推荐先做）**：不改 `ChatService` 对外行为，只把 agent 内部结构理顺。
  - **统一接入（最终目标）**：把 `ChatService` 的分流/创建/执行收敛到 `AgentCoordinator.route_and_execute()`。

### 0.2 架构硬规则（必须遵守）

- **意图识别唯一位置**：`core/routing/intent_analyzer.py`（Agent 层只消费 `IntentResult/RoutingDecision`）。
- **LLM-First**：禁止在 Agent 层做“关键词匹配式语义判断”（只允许格式校验/安全边界等确定性逻辑）。
- **依赖方向**：
  - ✅ `core/agent/*` 可以依赖 `core/context`、`core/tool`、`core/routing`
  - ❌ `core/context` / `core/tool` / `core/routing` 不得依赖 `core/agent`（否则 core 不再通用）
- **品牌中立**：代码/注释/文档中不得出现竞品智能体框架名称。

---

## 1. 当前系统现状（以真实调用链为准）

### 1.1 真实调用链（当前生产形态）

`services/chat_service.py` 当前核心分流形态（概念总结）：

- **路由/预处理**：得到 `routing_intent` 与 `use_multi_agent`
- **multi 路径**：直接 new `MultiAgentOrchestrator(...).execute(...)`，事件由 broadcaster 内部发送
- **single 路径**：调用 `agent.chat(...)`（注意：不是 `agent.execute(...)`）

因此当前的“统一入口”实际在 Service 层，而 `core/agent/coordinator.py` 更像一个未完全接入/未对齐的门面实现。

### 1.2 已确认的 P0 问题（先修，否则重构会反复救火）

- **接口不一致（P0）**：
  - `core/agent/coordinator.py` 调用的 `AgentFactory.create_router()` / `AgentFactory.create_from_decision()` 在 `core/agent/factory.py` 中不存在。
  - `core/agent/coordinator.py` 调用 `router.route(... previous_intent=...)`，但 `core/routing/router.py:AgentRouter.route()` 不接受该参数。
- **依赖过重（P0/P1）**：`core/agent/factory.py` 顶层 import `core.agent.multi`（易触发循环依赖/增大加载成本）。
- **边界被稀释（P1）**：`core/agent/__init__.py` re-export 路由层对象（例如 `IntentAnalyzer`），会弱化“意图识别唯一在 routing 层”的纪律。

---

## 2. 目标架构（设计模式 + 目录结构 + 接口约定）

### 2.1 设计模式与代码落点（评审看这一段就够）

- **Facade（门面）**：统一入口（最终建议 `AgentCoordinator.route_and_execute()`；短期可由 `ChatService` 继续扮演）
- **Factory（工厂）**：`AgentFactory` 只负责创建（输入 Schema/Decision，输出 `AgentProtocol`）
- **Strategy（策略）**：`core/agent/execution/*` 表达执行差异（RVR/RVR-B/Multi）
- **Template Method（模板方法）**：`BaseAgent` 统一生命周期（状态/步数上限/usage/通用骨架）
- **Builder（建造者）**：`core/agent/context/*` 组装 system blocks / runtime ctx（组合 `core/context` 能力）
- **Adapter（适配器）**：`core/agent/tools/*` 统一工具执行流（组合 `core/tool` executor/selector，支持特判插件）

### 2.2 目标目录树（建议）

> `execution/`、`context/`、`tools/` 都是 **agent 内部子包**，用于把 `core/context`、`core/tool` 的通用能力组合成可执行行为。  
> 它们不是“另一个层”，也不取代 `core/context` / `core/tool`。

```text
core/agent/                          # ✅ 当前实际结构（2026-02-06 更新）
  __init__.py
  protocol.py                        # AgentProtocol 定义
  base.py                            # 统一 Agent 类（不再是抽象基类）
  coordinator.py                     # AgentCoordinator 门面
  factory.py                         # AgentFactory 工厂
  content_handler.py
  errors.py                          # 统一错误定义
  models.py                          # 从 multi/ 迁移的模型

  execution/                         # 执行策略层
    __init__.py
    protocol.py                      # ExecutorProtocol
    rvr.py                           # RVRExecutor
    rvrb.py                          # RVRBExecutor（带回溯）
    multi.py                         # MultiAgentExecutor 适配器
    _multi/                          # Multi-Agent 内部实现
      __init__.py
      orchestrator.py                # MultiAgentOrchestrator 核心
      events.py                      # OrchestratorEventsMixin
      prompts.py                     # OrchestratorPromptsMixin

  context/                           # 上下文/提示词构建
    __init__.py
    prompt_builder.py                # build_system_blocks_with_injector

  tools/                             # 工具执行流
    __init__.py
    flow.py                          # ToolExecutionFlow
    special.py                       # SpecialToolHandler 插件

  components/                        # 从 multi/ 迁移的组件
    __init__.py
    checkpoint.py
    critic.py
    lead_agent.py

  backtrack/                         # 回溯机制
    __init__.py
    error_classifier.py
    manager.py
```

> **注意**：`simple/` 和 `multi/` 目录已删除。
> - `simple/` 的功能已合并到 `base.py`（统一 Agent）和 `execution/rvr*.py`
> - `multi/` 的功能已迁移到 `execution/_multi/` 和 `components/`

### 2.3 核心接口约定（实现指导）

#### 2.3.1 `AgentFactory.create_from_decision()`（必须补齐）

放在 `core/agent/factory.py`（或等价入口，建议用这个名字以配合 `coordinator.py`）：

```python
async def create_from_decision(
    decision: "RoutingDecision",
    event_manager,
    conversation_service=None,
    workspace_dir: str | None = None,
    base_schema=None,
    prompt_cache=None,
    system_prompt: str | None = None,
    **kwargs,
) -> "AgentProtocol":
    """按路由决策创建 Agent：single/multi 分流只依赖 decision.agent_type。"""
```

约束：
- 只能消费 `decision.intent`（不得在 factory 里再做意图识别/语义判断）。
- multi 创建必须 **延迟导入**。

#### 2.3.2 `ExecutorProtocol`（Phase 4 引入）

放在 `core/agent/execution/protocol.py`：

```python
class ExecutorProtocol(Protocol):
    async def execute(
        self,
        agent: "BaseAgent",
        messages: list[dict],
        session_id: str,
        intent: "IntentResult | None" = None,
        **kwargs,
    ) -> AsyncGenerator[dict, None]:
        ...
```

说明：executor 是纯策略对象；`SimpleAgent` 只负责选择 executor 并转发事件。

#### 2.3.3 `PromptBuilder`（Phase 2 引入）

放在 `core/agent/context/prompt_builder.py`：

```python
async def build_system_blocks(
    intent: "IntentResult | None",
    prompt_cache,
    context_strategy,
    user_id: str | None,
    user_query: str | None,
    available_tools: list[dict] | None,
    history_messages: list[dict] | None,
    variables: dict | None,
    metadata: dict | None,
) -> list[dict]:
    """仅负责组合 core/context injectors；不得引入新的网络/LLM 调用。"""
```

#### 2.3.4 `ToolExecutionFlow`（Phase 3 引入）

放在 `core/agent/tools/flow.py`：

```python
class ToolExecutionFlow:
    async def run(
        self,
        tool_calls: list[dict],
        tool_executor,
        tool_context: dict,
        *,
        handlers: list["SpecialToolHandler"] | None = None,
    ) -> list[dict]:
        """统一 tool_use -> tool_result；特判通过 handler 插件处理。"""
```

---

## 3. 分阶段实施清单（可打勾 + 精确到文件/函数/验证）

> 每个 Phase 结束必须跑“阶段验证”。不通过就不要进入下一阶段。  
> **建议每个 Phase 至少一个独立提交**（方便回滚与 diff 审核）。

### Phase 0（P0）：先跑通且一致（接口对齐 + 最小兼容）

#### 0.1 修复 `AgentCoordinator`/`AgentRouter`/`AgentFactory` 不一致（必须做）

- [x] **对齐 `core/agent/coordinator.py` 与 `core/routing/router.py` 的 route() 参数** ✅ 2026-02-04
  - 选择：优先修改 `AgentCoordinator`（改动更小）
  - 验收：`AgentCoordinator` 调用 `AgentRouter.route()` 时只传入 router 支持的参数

- [x] **在 `core/agent/factory.py` 增加 `create_from_decision()`** ✅ 2026-02-04
  - single 分支：创建 `SimpleAgent`/`RVRBAgent`（依据 `decision.intent.agent_type` 或 schema 的执行策略字段）
  - multi 分支：创建 `MultiAgentOrchestrator`（延迟导入）
  - 兼容：允许继续走 `from_schema()` 与 `from_prompt()`

- [x] **修复 `core/agent/factory.py` 中明显的死代码/不可达 return（如存在）** ✅ 2026-02-04
  - 验收：无不可达代码块/重复 return

#### 0.2 入口统一策略（两条路线，选其一即可）

- [x] **路线 A（保守，推荐先做）**：不改 `ChatService`，继续 single 走 `agent.chat()` ✅ 2026-02-04
  - 目标：只让 agent 内部结构可演进，不影响外部调用点
  - 状态：`execute()` 作为 wrapper 委托给 `chat()`
- [ ] **路线 B（推荐，最终形态）**：single 也统一走 `AgentProtocol.execute()`（后续迭代）  
  - 做法：让 `SimpleAgent.execute()` 成为主入口；`chat()` 变成 wrapper（或反之，但必须只有一个承载核心逻辑）
  - 目标：single/multi 都可通过 `AgentProtocol.execute()` 驱动，便于 Facade 收敛

#### Phase 0 验证（必须全部通过）

- [x] **静态验证（每次提交都跑）** ✅ 2026-02-04

```bash
python -m compileall -q core/agent core/routing
python -c "import core.agent; import core.routing"
```

- [ ] **运行验证（按项目现状三选一）**
  - [ ] `python -m pytest -q`
  - [ ] `uvicorn main:app --reload`（按实际启动命令）
  - [ ] 写一个临时 smoke 脚本直接调用 `ChatService` 最短路径（见第 4 节模板）

#### Phase 0 回滚策略（必须写进代码）

- [ ] 加一个**临时开关**允许回退到旧路径（例如 `AGENT_REFACTOR_DISABLE=1`）  
  - 约束：Phase 2 结束必须移除（避免永久遗留分叉逻辑）

---

### Phase 0B（P0）：收口清单（让新结构真正“生效”）

> 这部分是“你改了很多代码但感觉没达到预期”的核心原因。  
> 目标：把 **UnifiedAgent + Executor + tools/context/components** 真正收敛成一条主干，避免两套体系并存继续变复杂。

#### 0B.1 统一策略字段语义（最关键，必须先做）

- [ ] **定义单义策略字段：`agent_type` 只表示执行策略枚举**  
  - 规范值：`"rvr" | "rvr-b" | "multi"`（未来新增策略继续扩展该枚举，但保持单义）  
  - 要求：`core/routing/router.py` 的 `RoutingDecision.agent_type` 与 `core/routing/types.py:IntentResult.agent_type` **语义一致**  
  - 如果需要 `"single"|"multi"` 这种“路由模式”维度：新增字段（例如 `route_mode`），或使用 `intent.is_multi_agent` 推导，**不要复用 `agent_type`**

- [ ] **Factory/Coordinator 只依据该策略字段选 Executor**  
  - 文件：`core/agent/factory.py`、`core/agent/coordinator.py`  
  - 验收：当 `intent.agent_type == "rvr-b"` 时，必然选到 RVRB；当 `"multi"` 时必然走 Multi executor；不得在 agent 层二次语义推断

#### 0B.2 统一运行入口（确保你的结构改动在 runtime 里真正生效）

二选一（推荐 B）：

- [ ] **路线 A（保守）**：`ChatService` 继续分流，但 **创建必须走 Factory**  
  - 目标：Service 层不再 `new MultiAgentOrchestrator(...)`  
  - 改动点：`services/chat_service.py` multi 分支改为走 `AgentFactory.create_from_decision()` 或 `AgentFactory.from_schema(..., strategy="multi")`
  - 验收：全仓搜索 `MultiAgentOrchestrator(`，`services/chat_service.py` 不再直接 new

- [ ] **路线 B（终局推荐）**：`ChatService` 全部走 `AgentCoordinator.route_and_execute()`  
  - 目标：route → create → execute 全部收敛到 agent 层门面
  - 验收：single/multi 只出现一次入口调用；Service 层只做协议/持久化/后台任务

> 不管选 A/B，都要满足：**single/multi 都走 `AgentProtocol.execute()`**（`chat()` 如保留，只能是 wrapper，不能承载核心逻辑）。

#### 0B.3 Multi 入口收口（把执行入口关到 `core/agent/execution/multi.py`）

- [ ] **规定唯一入口：multi 的执行只能从 `core/agent/execution/multi.py` 进入**  
  - 文件：`core/agent/execution/multi.py`、`core/agent/orchestrator.py`  
  - 做法建议：将 `core/agent/orchestrator.py` 逐步内聚为 `execution/multi/*` 的内部实现；上层（Service/Factory）只能看见 `MultiAgentExecutor`
  - 验收：除 `execution/multi.py` 外，不再有调用点直接调用 `MultiAgentOrchestrator.execute(...)`

#### 0B.4 去掉 Executor 对 `context.extra["agent"]` 的隐式耦合（提升可测试/可替换）

- [ ] **Executor 依赖显式化：只从 `ExecutionContext` 取 llm/tool_executor/broadcaster**  
  - 文件：`core/agent/execution/protocol.py`、`core/agent/execution/multi.py`（以及其他策略执行器）  
  - 禁止：`context.extra.get("agent")` 这种“从 agent 取依赖再塞回去”的写法
  - 验收：`core/agent/execution/*` 内全仓不再出现 `context.extra.get("agent")`

#### 0B.5 兼容导出“不能伪装”（避免调用方误以为在用 rvr-b）

- [ ] **兼容要么强绑定策略，要么明确 deprecated 并逐步移除**  
  - 文件：`core/agent/__init__.py`
  - 推荐：保留 `create_agent(strategy=...)` 为唯一推荐入口；兼容函数/别名必须能 100% 触发对应策略（否则宁可删掉或发告警）
  - 验收：调用方写 `create_agent(strategy="rvr-b")` 时 100% 走 rvr-b executor；不会因为 alias 导致默认为 rvr

#### 0B.6 Pool/Registry 创建入口收口（避免 runtime 绕开你的新结构）

- [ ] **`infra/pools/agent_pool.py` 默认原型创建走统一入口（create_agent/AgentFactory）**  
  - 目标：pool clone 出来的实例 executor 可追踪、可预测
  - 验收：默认原型不再调用旧的 simple/multi 构造路径

#### 0B.7 工具流与 Prompt 构建必须走组合层（Agent 才能继续变薄）

- [ ] **System blocks 必须由 `core/agent/context/prompt_builder.py` 生成**  
  - 验收：executor/agent 内不再散落“拼 system prompt”的逻辑（除 builder 外）

- [ ] **tool_use → tool_result 必须走 `core/agent/tools/flow.py`**  
  - 验收：executor/agent 内不再各写一套工具执行循环；特判只在 `tools/special.py` handler

#### Phase 0B 最小验证闭环（每完成一个子项就跑）

- [ ] 静态验证：

```bash
python -m compileall -q core/agent core/routing
python -c "import core.agent; import core.routing"
```

- [ ] 运行时验证（至少覆盖 3 条路径）：
  - [ ] `intent.agent_type="rvr"` → 走 RVRExecutor
  - [ ] `intent.agent_type="rvr-b"` → 走 RVRBExecutor
  - [ ] `intent.agent_type="multi"` → 走 MultiAgentExecutor（且 Service 层不直接 new orchestrator）

#### Phase 0B 完成定义（DoD）

- [x] `agent_type` 字段语义单义：`rvr|rvr-b|multi` ✅ P0-1
- [x] Service 层不直接 `new MultiAgentOrchestrator` ✅ P0-2
- [x] single/multi 都只走 `AgentProtocol.execute()` ✅ P0-5
- [x] `execution/*` 不依赖 `context.extra["agent"]` ✅ P1
- [ ] prompt/tool 分别只从组合层（context/tools）进入

---

### Phase 1（P1）：依赖与导出边界收敛（降低循环依赖风险）

- [x] **1.1 `AgentFactory` 移除顶层 multi import** ✅ 2026-02-04
  - 文件：`core/agent/factory.py`
  - 要求：multi 相关 import 移到 `_create_multi_agent()` 内部
  - 验收：`python -c "import core.agent.factory"` 通过

- [x] **1.2 `core/agent/__init__.py` 不再 re-export 路由层对象** ✅ 2026-02-04
  - 文件：`core/agent/__init__.py`
  - 要求：移除 `IntentAnalyzer/create_intent_analyzer` 导出；路由对象统一从 `core/routing` 导入
  - 验收：全仓无 `from core.agent import IntentAnalyzer`

---

### Phase 2（P1/P2）：抽出 Builder（Prompt/上下文胶水层归位）

目标：`SimpleAgent` 不直接拼装 injector orchestrator/prompt_cache 分层细节。

- [x] **2.1 新增 `core/agent/context/prompt_builder.py`** ✅ 2026-02-04
  - 从 `core/agent/simple/simple_agent_context.py` 迁移 `build_system_blocks_with_injector()` 的核心实现
  - 原位置保留同名 wrapper（转调新实现），减少调用点改动

- [ ] **2.2（可选）新增 `core/agent/context/context_builder.py`**（跳过）
  - 用一个“接收对象、返回对象（RORO）”的方式，统一组装 runtime ctx/variables/metadata/history

验证：
- [ ] 同一输入下，system blocks 的 **LLM 可见文本**不变（允许内部 debug 字段变化）
- [ ] builder 不引入额外网络调用，不引入新的 LLM 调用

---

### Phase 3（P2）：抽出 Adapter（统一工具执行流）

目标：single/multi 共享 tool_use -> tool_result 逻辑；特判通过插件机制。

- [x] **3.1 新增 `core/agent/tools/flow.py`：ToolExecutionFlow** ✅ 2026-02-04
- [x] **3.2 新增 `core/agent/tools/special.py`：SpecialToolHandler 插件** ✅ 2026-02-04
  - `plan_todo`、HITL 等特判迁移到 handler

- [ ] **3.3 Simple 工具执行委托给 flow**（后续迭代）
  - 文件：`core/agent/simple/simple_agent_tools.py`
  - 验收：SimpleAgent 不再维护重复的 tool loop 细节

- [ ] **3.4 Multi 工具执行逐步委托给 flow**（后续迭代）
  - 文件：`core/agent/multi/orchestrator.py`
  - 策略：先覆盖最常见工具路径，避免一次性大改 2000+ 行

验证：
- [ ] tool_result 结构兼容（字段/错误格式不变）
- [ ] 至少跑通 1 条 `plan_todo` 与 1 条 HITL 路径

---

### Phase 4（P2/P3）：Strategy 化执行（让 Agent 真正变薄）

目标：把循环细节迁移到 `execution/*`，Agent 类只做策略选择与事件桥接。

- [x] **4.1 新增 `core/agent/execution/protocol.py`** ✅ 2026-02-04
- [x] **4.2 实现 `RVRExecutor` / `RVRBExecutor`** ✅ 2026-02-04
  - 迁移/委托来源：`core/agent/simple/simple_agent_loop.py`、`core/agent/simple/mixins/backtrack_mixin.py`

- [ ] **4.3 实现 `MultiExecutorAdapter`**（后续迭代）
  - 适配 `core/agent/multi/executors/*` 为统一协议

- [ ] **4.4 精简 `SimpleAgent`**
  - 目标：只保留“选 executor + 透传事件 + 少量状态”

- [ ] **4.5 精简 `MultiAgentOrchestrator`**
  - 目标：保留 initialize/state/trace；执行交给 multi executor

验证：
- [ ] `SimpleAgent` 主文件行数显著下降（建议 < 500 行）
- [ ] `multi/orchestrator.py` 明显下降（目标 < 800 行，或至少把旧兼容路径拆出去）
- [ ] single/multi 的 usage/event schema 一致

---

### Phase 5（可选）：类型解耦（消除 routing 对 agent 的反向依赖）

现状：`core/routing` 依赖 `core/agent/types.py`，边界变脆。

- [x] 迁移 `IntentResult/Complexity` 到中立模块（建议 `core/routing/types.py` 或 `core/types/intent.py`） ✅ 2026-02-04
- [x] 全仓替换导入路径，确保 routing 不再 import agent ✅ 2026-02-04

验证：
- [x] `core/routing/*` 不再出现 `from core.agent.types import ...` ✅ 2026-02-04

---

## 4. 验证手册（复制即用）

### 4.1 每个 Phase 都跑：静态验证

```bash
python -m compileall -q core/agent core/routing
python -c "import core.agent; import core.routing"
```

### 4.2 如果仓库有 pytest：跑测试

```bash
python -m pytest -q
```

### 4.3 无 pytest 时：推荐加临时 smoke 脚本（完成 Phase 2 后删除或转正）

> 建议文件：`scripts/smoke_agent_refactor.py`  
> 目标：不依赖 HTTP，只走一条最短“路由 -> 创建 -> 执行”路径。

```python
import asyncio

async def main() -> None:
    from core.routing import AgentRouter
    from core.agent.factory import AgentFactory

    # 注意：event_manager 以项目实际实现为准，这里仅示意
    event_manager = object()

    router = AgentRouter(llm_service=None, enable_llm=False)
    decision = await router.route(
        user_query="你好，简单介绍一下你能做什么",
        conversation_history=[],
        user_id=None,
    )

    agent = await AgentFactory.create_from_decision(
        decision=decision,
        event_manager=event_manager,
        conversation_service=None,
        workspace_dir=None,
        base_schema=None,
        prompt_cache=None,
        system_prompt=None,
    )

    async for _event in agent.execute(
        messages=[{"role": "user", "content": "你好"}],
        session_id="smoke",
        intent=decision.intent,
        enable_stream=False,
    ):
        pass

if __name__ == "__main__":
    asyncio.run(main())
```

---

## 5. 最终验收清单（Definition of Done）

- [x] single/multi 至少都能走 `AgentProtocol.execute()`（允许 `chat()` 存在，但只能是 wrapper） ✅
- [x] `AgentFactory` 只负责创建（不包含路由决策/意图识别） ✅
- [x] 意图识别只在 `core/routing/intent_analyzer.py`，Agent 层不创建也不导出 `IntentAnalyzer` ✅
- [ ] `SimpleAgent` / `MultiAgentOrchestrator` 只做编排：执行细节在 `execution/*`、上下文在 `context/*`、工具流在 `tools/*`（基础结构已建立，完整迁移待后续迭代）
- [x] `core/context` / `core/tool` / `core/routing` 不依赖 `core/agent` ✅
- [ ] 覆盖关键路径：single + multi + 至少 1 个工具调用 + 至少 1 次 tool_error（需运行时验证）

---

## 6. 推荐实施顺序（强烈建议照做）

- Phase 0：接口对齐、补齐创建入口（先让结构可运行）
- Phase 1：依赖收敛（去顶层 multi import、去 agent 导出路由对象）
- Phase 2/3：抽 PromptBuilder + ToolExecutionFlow（收益最大）
- Phase 4：executor strategy 化（Agent 彻底变薄）
- Phase 5：类型解耦（长期治理，可选）

> 不要跨 phase 同时大改。每个 phase 做完立刻跑验证，失败就回滚到上一个 phase。

---

## 变更记录

| 日期 | Phase | 变更内容 |
|------|-------|----------|
| 2026-02-04 | Phase 0 | 修复 coordinator.py 调用 router.route() 参数不匹配问题 |
| 2026-02-04 | Phase 0 | 新增 AgentFactory.create_router() 和 create_from_decision() |
| 2026-02-04 | Phase 1 | factory.py 移除顶层 multi import，改为延迟导入 |
| 2026-02-04 | Phase 1 | __init__.py 不再 re-export IntentAnalyzer |
| 2026-02-04 | Phase 2 | 新增 core/agent/context/prompt_builder.py，迁移 build_system_blocks_with_injector |
| 2026-02-04 | Phase 3 | 新增 core/agent/tools/flow.py (ToolExecutionFlow) 和 special.py (特判 Handler) |
| 2026-02-04 | Phase 4 | 新增 core/agent/execution/ 模块 (ExecutorProtocol, RVRExecutor, RVRBExecutor) |
| 2026-02-04 | Phase 0.3 | 修复 factory.py 中死代码（不可达 return 语句） |
| 2026-02-04 | Phase 5 | 类型解耦：IntentResult/Complexity 迁移到 core/routing/types.py |
| 2026-02-04 | Phase 0.2 | 入口统一策略：选择路线 A（保守），execute() 作为 wrapper |
| 2026-02-04 | 验收 | 最终验收清单：4/6 项通过，基础结构完成 |
| 2026-02-04 | 清理 | 删除 core/agent/types.py，全仓改用 core.routing.types |
| 2026-02-04 | 激进重构 | 完全迁移 Mixin 逻辑到新模块 |
|  | - | RVRLoopMixin → execution/rvr.py (RVRExecutor) |
|  | - | ToolExecutionMixin → tools/flow.py (ToolExecutionFlow) |
|  | - | BacktrackMixin → execution/rvrb.py (RVRBExecutor) |
|  | - | SimpleAgent 不再继承 Mixin，使用 RVRExecutor |
|  | - | RVRBAgent 使用 RVRBExecutor |
|  | - | 删除旧文件：simple_agent_loop.py, simple_agent_tools.py, mixins/* |
| 2026-02-04 | **破坏性重构** | 统一 Agent 架构 |
|  | - | 删除 simple/ 整个目录 |
|  | - | base.py 重写为统一 Agent 类（不再是抽象基类） |
|  | - | Factory 增加 Executor 注册表 |
|  | - | errors.py 移到 core/agent/ 根目录 |
|  | - | SimpleAgent/RVRBAgent 作为 deprecated 别名保留 |
|  | - | multi/ 保留待后续迭代迁移 |
| 2026-02-04 | 多智能体适配 | execution/multi.py |
|  | - | 创建 MultiAgentExecutor 适配器 |
|  | - | SequentialMultiExecutor, ParallelMultiExecutor, HierarchicalMultiExecutor |
|  | - | 委托给 orchestrator.py 的实现 |
|  | - | 统一到 Executor 注册表 |
| 2026-02-04 | **完全迁移 multi/** | 删除 multi/ 目录 |
|  | - | models.py → core/agent/models.py |
|  | - | orchestrator.py → core/agent/orchestrator.py |
|  | - | checkpoint.py → components/checkpoint.py |
|  | - | lead_agent.py → components/lead_agent.py |
|  | - | critic.py → components/critic.py |
|  | - | subagent_manager.py → components/subagent_manager.py |
|  | - | critique_handler.py → components/critique_handler.py |
|  | - | 删除 multi/executors/（功能已在 orchestrator 内部实现）|
| 2026-02-04 | **P0 收口清单** | 统一架构收口 |
|  | P0-1 ✅ | agent_type 统一为执行策略语义 (rvr/rvr-b/multi)，RoutingDecision.is_multi_agent |
|  | P0-2 ✅ | ChatService 多智能体创建通过 Factory，不直接 new MultiAgentOrchestrator |
|  | P0-3 ✅ | orchestrator.py 移到 execution/_multi/ 作为内部实现 |
|  | P0-4 ✅ | 去掉 context.extra["agent"] 隐式耦合（P1 已完全移除 context.agent） |
|  | P0-5 ✅ | create_agent(strategy=...) 作为推荐入口，create_simple_agent 已移除 |
|  | P0-6 ✅ | agent_pool 使用 create_agent 代替 create_simple_agent |
| 2026-02-05 | **架构清理** | 移除已废弃的别名和函数 |
|  | ✅ | 移除 SimpleAgent/RVRBAgent/BaseAgent 废弃别名 |
|  | ✅ | 移除 create_simple_agent() 废弃函数 |
|  | ✅ | 更新 protocol.py docstrings 反映统一 Agent 架构 |
|  | ✅ | 更新所有导入点使用 Agent 而非 SimpleAgent |
|  | P0-7 🔶 | system blocks 统一走 prompt_builder ✅，工具执行待 P1 迁移到 ToolExecutionFlow |
|  | 新增 | AgentSchema.execution_strategy 字段 |
| 2026-02-04 | **P1 Executor 解耦** | 完成 Executor 与 Agent 的完全解耦 |
|  | P1-1 ✅ | _process_stream 迁移到 RVRExecutor（从 Agent 迁移） |
|  | P1-2 ✅ | _handle_tool_calls 迁移到 RVRExecutor（从 Agent 迁移） |
|  | P1-3 ✅ | _handle_last_turn_tools 迁移到 RVRExecutor（从 Agent 迁移） |
|  | P1-4 ✅ | RVRBExecutor 同步更新（继承父类方法 + 带回溯版本） |
|  | 移除 | ExecutionContext.agent 字段（所有依赖通过显式字段传递） |
|  | 移除 | ToolExecutionContext.agent 字段 |
|  | 更新 | Agent.execute() 构建 ExecutionContext 时传递所有依赖 |
| 2026-02-04 | **P2 工具执行 + Orchestrator 拆分** | 统一工具执行流 + 拆分巨型文件 |
|  | P2-1 ✅ | RVRExecutor._handle_tool_calls 使用 ToolExecutionFlow |
|  | P2-2 ✅ | RVRBExecutor._handle_tool_calls_with_backtrack 使用 ToolExecutionFlow |
|  | P2-3 ✅ | orchestrator.py 拆分：事件发送层 → _multi/events.py (OrchestratorEventsMixin) |
|  | P2-4 ✅ | orchestrator.py 拆分：提示词构建层 → _multi/prompts.py (OrchestratorPromptsMixin) |
|  | 结构 | MultiAgentOrchestrator 现在继承 OrchestratorEventsMixin + OrchestratorPromptsMixin |
| 2026-02-06 | **Bug 修复** | 导入和运行时错误修复 |
|  | ✅ | 修复 `context/__init__.py` 导入不存在的 `build_cached_system_prompt` |
|  | ✅ | 修复 `base.py` 中 `ExecutorConfig/ExecutionContext` 只在 TYPE_CHECKING 导入 |
| 2026-02-06 | **Multi-Agent 修复** | 子 Agent 工具调用问题修复 |
|  | ✅ | 移除 `_emit_subtask_end` 中 output 截断 `[:200]`（子 Agent 输出应完整返回）|
|  | ✅ | 修复 `_initialize_shared_resources` 创建空 `CapabilityRegistry()` → 改用 `get_capability_registry()` |
|  | ✅ | 修复子 Agent 无法调用工具（LLM 输出 XML 假工具调用）|
|  | ✅ | 修复 `_emit_decomposition` 缺少 `tool_result` 事件（前端显示"执行中"）|
|  | ✅ | 强化子 Agent system prompt：第一个动作必须是工具调用 |
