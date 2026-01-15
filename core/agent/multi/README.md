# 多智能体框架（V7.1 - Anthropic 启发）

> **更新日期**: 2026-01-15  
> **版本**: V7.1  
> **灵感来源**: [Anthropic Multi-Agent Research System](https://www.anthropic.com/engineering/multi-agent-research-system)

## 概览

V7.1 多智能体框架基于 Anthropic 的多智能体研究系统设计，提供生产级的多智能体协作能力，支持长时间运行、故障恢复、智能任务分解。

## 核心组件

### 1. **MultiAgentOrchestrator** - 编排器

负责协调多个 Agent 的执行，支持三种模式：

```python
from core.agent.multi import MultiAgentOrchestrator, ExecutionMode

orchestrator = MultiAgentOrchestrator(
    config=multi_agent_config,
    enable_checkpoints=True,      # 启用检查点
    enable_lead_agent=True,       # 启用 Lead Agent
)

async for event in orchestrator.execute(
    intent=intent_result,
    messages=messages,
    session_id="session_123",
    resume_from_checkpoint=True,  # 尝试从检查点恢复
):
    # 处理事件
    print(event)
```

**执行模式**：
- `SEQUENTIAL`: 串行执行，有依赖关系
- `PARALLEL`: 并行执行，独立子任务
- `HIERARCHICAL`: 层级执行，主从协调

### 2. **CheckpointManager** - 检查点管理

支持长时间运行的工作流，失败时从检查点恢复。

```python
from core.agent.multi import CheckpointManager

manager = CheckpointManager(
    storage_path="data/checkpoints",
    auto_save=True,
    retention_days=7
)

# 保存检查点
checkpoint = await manager.save_checkpoint(state, reason="auto")

# 加载最新检查点
checkpoint = await manager.load_latest_checkpoint(session_id)

# 恢复状态
if checkpoint and manager.can_resume(checkpoint):
    state = manager.restore_state(checkpoint)
```

**关键特性**：
- ✅ 每个 Agent 完成后自动保存
- ✅ 错误时保存当前进度
- ✅ 持久化到磁盘（跨进程）
- ✅ 支持恢复验证（是否可恢复、是否过期）

### 3. **LeadAgent** - 主控智能体

使用 Claude Opus 进行智能任务分解和结果综合。

```python
from core.agent.multi import LeadAgent

lead_agent = LeadAgent(
    model="claude-opus-4",
    max_subtasks=5,
    enable_thinking=True
)

# 任务分解
plan = await lead_agent.decompose_task(
    user_query="研究人工智能在医疗领域的应用",
    available_tools=["web_search", "knowledge_query"],
    intent_info={"task_type": "research", "complexity": "complex"}
)

# 结果综合
final_result = await lead_agent.synthesize_results(
    subtask_results=results,
    original_query=user_query,
    synthesis_strategy=plan.synthesis_strategy
)

# 质量审查
review = await lead_agent.review_result(
    final_result=final_result,
    original_query=user_query,
    success_criteria=["完整性", "准确性"]
)
```

**子任务定义（明确边界）**：
```python
SubTask(
    subtask_id="task_1",
    title="医疗诊断应用研究",
    description="研究 AI 在医疗影像分析、疾病预测中的应用",
    assigned_agent_role=AgentRole.RESEARCHER,
    tools_required=["web_search", "knowledge_query"],
    expected_output="Markdown 格式的研究报告，包含应用场景、技术方案、案例分析",
    success_criteria=["覆盖至少 3 个应用场景", "引用权威来源"],
    depends_on=[],  # 无依赖
    constraints=["聚焦于实际应用，避免纯理论"],
    max_time_seconds=120
)
```

## 核心改进（vs V7.0）

### 1. 故障恢复

**问题**：V7.0 无法处理长时间运行任务的故障，需要从头开始。

**解决方案**：检查点机制

```
Agent 1 完成 → 保存检查点 ✅
Agent 2 执行中... → 网络错误 ❌
          ↓
从检查点恢复 → Agent 2 继续 ✅
```

**收益**：
- 节省 token 成本（不重复已完成工作）
- 减少用户等待时间
- 提高系统可靠性

### 2. 智能任务分解

**问题**：V7.0 使用硬编码规则，缺乏灵活性。

**解决方案**：Lead Agent 智能分析

```
用户查询 → Lead Agent (Opus) 分析
         ↓
    任务分解计划
    ├── 子任务 1: 明确目标、工具、边界
    ├── 子任务 2: 明确目标、工具、边界
    └── 子任务 3: 明确目标、工具、边界
         ↓
    Worker Agents (Sonnet) 执行
         ↓
    Lead Agent 综合结果
```

**优势**：
- 语义理解，适应性强
- 明确定义，减少重叠和遗漏
- 专业综合，输出连贯

### 3. 完整追踪

**问题**：V7.0 无法调试 Agent 决策过程。

**解决方案**：执行追踪系统

```python
orchestrator._trace("lead_agent_decompose_start", {...})
orchestrator._trace("agent_execution_start", {...})
orchestrator._trace("agent_execution_done", {...})

# 获取完整追踪
trace = orchestrator.get_execution_trace()
```

**用途**：
- 调试 Agent 决策
- 分析性能瓶颈
- 监控资源消耗
- 优化执行策略

## 最佳实践

### 1. 何时使用多智能体？

**✅ 适合场景**：
- **广度优先问题**：复杂查询，多个独立方向
- **并行子任务**：信息收集、多实体研究
- **大搜索空间**：需要同时探索多个路径

**❌ 不适合场景**：
- 简单问答（成本高，收益低）
- 深度优先、顺序工作（无并行收益）
- 紧密依赖链的编码任务

### 2. 成本权衡

多智能体工作流消耗 **~15× token**（相比单智能体）

**决策依据**：
- 任务复杂度 > 5.0 → 考虑多智能体
- 高价值任务 → 值得投入
- 简单任务 → 使用单智能体

### 3. 检查点策略

**自动检查点**（推荐）：
```python
enable_checkpoints=True  # 每个 Agent 完成后自动保存
```

**手动检查点**（精细控制）：
```python
checkpoint = await manager.save_checkpoint(state, reason="manual")
```

### 4. Lead Agent 配置

**Opus vs Sonnet**：
- **Lead Agent**：使用 Opus（任务分解、结果综合）
- **Worker Agents**：使用 Sonnet（具体执行）

**原因**：
- Opus：理解能力强，适合规划
- Sonnet：成本低，适合执行

## 示例

### 简单例子：并行研究

```python
from core.agent.multi import (
    MultiAgentOrchestrator,
    MultiAgentConfig,
    AgentConfig,
    AgentRole,
    ExecutionMode
)

# 配置
config = MultiAgentConfig(
    config_id="research_task",
    mode=ExecutionMode.PARALLEL,
    agents=[
        AgentConfig(
            agent_id="researcher_ai",
            role=AgentRole.RESEARCHER,
            model="claude-sonnet-4-5-20250929",
            tools=["web_search"],
        ),
        AgentConfig(
            agent_id="researcher_blockchain",
            role=AgentRole.RESEARCHER,
            model="claude-sonnet-4-5-20250929",
            tools=["web_search"],
        ),
        AgentConfig(
            agent_id="summarizer",
            role=AgentRole.SUMMARIZER,
            model="claude-sonnet-4-5-20250929",
        ),
    ],
    enable_final_summary=True,
)

# 执行
orchestrator = MultiAgentOrchestrator(
    config=config,
    enable_checkpoints=True,
    enable_lead_agent=True,
)

async for event in orchestrator.execute(
    messages=[{"role": "user", "content": "比较 AI 和区块链的技术趋势"}],
    session_id="session_123",
):
    # 处理事件
    if event["type"] == "agent_end":
        print(f"✅ {event['agent_id']} 完成")
```

### 复杂例子：带恢复的层级任务

```python
# 第一次执行（可能失败）
try:
    async for event in orchestrator.execute(
        messages=messages,
        session_id="session_456",
        resume_from_checkpoint=False,  # 首次执行
    ):
        # 处理事件
        pass
except Exception as e:
    print(f"执行失败: {e}")
    # 检查点已自动保存

# 第二次执行（从检查点恢复）
async for event in orchestrator.execute(
    messages=messages,
    session_id="session_456",
    resume_from_checkpoint=True,  # 从检查点恢复
):
    # 继续执行未完成的 Agent
    pass
```

## 测试

运行测试：

```bash
cd /path/to/zenflux_agent
python tests/test_multi_agent_anthropic.py
```

测试内容：
1. CheckpointManager：保存、加载、恢复
2. LeadAgent：任务分解、结果综合
3. MultiAgentOrchestrator：完整流程

## 监控与调试

### 获取执行追踪

```python
# 执行后
trace = orchestrator.get_execution_trace()

for entry in trace:
    print(f"{entry['timestamp']}: {entry['event_type']}")
    print(f"  数据: {entry['data']}")
```

### 获取检查点列表

```python
checkpoints = await manager.list_checkpoints(session_id)

for cp in checkpoints:
    print(f"检查点: {cp.checkpoint_id}")
    print(f"  创建时间: {cp.created_at}")
    print(f"  已完成: {len(cp.completed_agents)}")
    print(f"  待执行: {len(cp.pending_agents)}")
```

## 下一步

### P1 优先级

1. **实现 Worker Agent 执行逻辑** ⭐
   - 当前是占位实现
   - 需要实际 LLM 调用
   - 参考 `SimpleAgent` 的实现

2. **集成到 AgentRouter**
   - 当 `complexity.score > 5.0` 时路由到多智能体
   - 传递完整的 intent 信息

3. **评估与优化**
   - 监控 token 消耗
   - A/B 测试效果
   - 优化检查点策略

### P2 后续优化

- 蓝绿部署支持
- 异步执行（vs 同步点）
- 动态 Agent 数量调整
- 更细粒度的错误恢复

## 参考资料

- [Anthropic: How we built our multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system)
- [架构文档](../../../docs/architecture/00-ARCHITECTURE-OVERVIEW.md)
- [Orchestrator-Worker Pattern](https://en.wikipedia.org/wiki/Master%E2%80%93slave_(technology))

## 许可

参考项目根目录的 LICENSE 文件。
