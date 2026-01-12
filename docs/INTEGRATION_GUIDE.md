# Multi-Agent 优化集成指南

> 📅 **日期**: 2026-01-12  
> 🎯 **目的**: 快速集成已实现的优化组件

---

## ✅ 已完成组件

### 1. ConflictResolver（冲突解决器）
- **文件**: `core/multi_agent/scheduling/conflict_resolver.py`
- **集成状态**: ✅ 已集成到 `WorkerScheduler`
- **功能**: 文件锁、冲突检测、串行化策略

### 2. Mermaid DAG 生成
- **文件**: `core/multi_agent/decomposition/task_decomposer.py`
- **方法**: `generate_mermaid_dag(sub_tasks)`
- **集成状态**: 🚧 方法已实现，需要调用

---

## 🔧 待集成步骤

### Step 1: 在 FSM Engine 中生成并携带 DAG

**文件**: `core/multi_agent/fsm/engine.py`

**位置**: `_on_decomposition_complete` 方法

**添加代码**:
```python
async def _on_decomposition_complete(self, state: TaskState):
    """任务分解完成"""
    # ... 现有代码 ...
    
    # 🆕 生成 Mermaid DAG
    mermaid_dag = self.orchestrator.task_decomposer.generate_mermaid_dag(state.sub_tasks)
    
    # 发布事件（携带 DAG）
    await self._emit_task_event("decomposition_complete", state, extra_data={
        "dag_mermaid": mermaid_dag
    })
    
    # ... 继续现有代码 ...
```

### Step 2: EventManager 支持 DAG 事件

**文件**: `core/events/conversation_events.py`

**添加方法**:
```python
async def emit_task_graph(
    self,
    session_id: str,
    conversation_id: str,
    task_id: str,
    dag_mermaid: str
) -> Dict[str, Any]:
    """
    发送任务流程图事件
    
    Args:
        session_id: Session ID
        conversation_id: Conversation ID
        task_id: 任务 ID
        dag_mermaid: Mermaid 格式的 DAG
        
    Returns:
        事件数据
    """
    event_data = await self._create_event(
        session_id=session_id,
        event_type="task_graph",
        data={
            "task_id": task_id,
            "dag": dag_mermaid,
            "format": "mermaid"
        }
    )
    return event_data
```

### Step 3: 前端渲染 Mermaid

**示例代码**:
```javascript
import mermaid from 'mermaid';

// 监听 task_graph 事件
eventSource.addEventListener('task_graph', (event) => {
  const data = JSON.parse(event.data);
  const dagCode = data.dag;
  
  // 渲染 Mermaid 图表
  const element = document.getElementById('task-graph');
  mermaid.render('task-dag', dagCode, (svgCode) => {
    element.innerHTML = svgCode;
  });
});
```

---

## 📊 实施优先级（剩余任务）

| 优先级 | 任务 | 工作量 | 价值 |
|--------|------|--------|------|
| P1 | 集成 DAG 到事件 | 1小时 | 高（可视化） |
| P2 | 产物持久化（ArtifactStore） | 2小时 | 中（审计） |
| P3 | Worker 池化（LRU Cache） | 2小时 | 中（性能） |
| P4 | 可观测性增强（Metrics） | 1小时 | 中（运维） |
| P0 | 创建 Workers 配置 | 0.5小时 | 高（必需） |
| P0 | 端到端验证 | 0.5小时 | 高（质量） |

---

## 🚀 快速验证步骤

### 1. 创建 Workers 配置

```bash
mkdir -p instances/test_agent/workers/research
mkdir -p instances/test_agent/workers/analysis
mkdir -p instances/test_agent/workers/synthesis
```

**`instances/test_agent/workers/research/prompt.md`**:
```markdown
# Research Expert

你是一个专业的研究专家，擅长信息收集和分析。

## 专业领域
- 公司战略研究
- 技术趋势分析
- 市场调研

## 工作方式
1. 系统性收集信息
2. 关注权威来源
3. 提供结构化输出

## 输出格式
- 使用 Markdown
- 包含数据来源
- 突出关键发现
```

**`instances/test_agent/workers/analysis/prompt.md`**:
```markdown
# Analysis Expert

你是一个专业的分析专家，擅长数据对比和深度分析。

## 专业领域
- 竞品对比分析
- 优劣势评估
- 趋势预测

## 工作方式
1. 多维度对比
2. 量化评估
3. 逻辑推理

## 输出格式
- 使用表格对比
- 提供评分
- 给出结论建议
```

**`instances/test_agent/workers/synthesis/prompt.md`**:
```markdown
# Synthesis Expert

你是一个专业的综合专家，擅长整合信息和生成报告。

## 专业领域
- 信息整合
- 报告撰写
- 结论提炼

## 工作方式
1. 整合多源信息
2. 结构化呈现
3. 突出核心观点

## 输出格式
- 完整报告
- 清晰层次
- 结论明确
```

### 2. 运行验证

```bash
cd /Users/liuyi/Documents/langchain/CoT_agent/mvp/zenflux_agent
/Users/liuyi/Documents/langchain/liuy/bin/python tests/test_orchestrator_e2e.py
```

**预期输出**:
```
✅ MultiAgentOrchestrator 初始化成功
✅ 加载 3 个 Workers 配置
✅ 任务分解成功: 6 个子任务
✅ 冲突检测: 0 个冲突
✅ 并行执行: 5 个 Worker
✅ 结果聚合完成
✅ 输出质量评分: 80% (8/10)
```

---

## 📝 技术债务清单

1. **高优先级**
   - [ ] Workers 配置目录创建
   - [ ] DAG 事件集成到 FSM
   - [ ] 端到端验证通过

2. **中优先级**
   - [ ] ArtifactStore 实现
   - [ ] Worker 池化实现
   - [ ] 可观测性 Metrics

3. **低优先级**
   - [ ] 语义冲突检测（预留接口）
   - [ ] 人工介入接口（HITL）
   - [ ] 前端 Dashboard 实现

---

## 🎯 成功标准

端到端验证通过的标准：

1. ✅ **触发验证**: Multi-Agent 成功触发（6 个子任务）
2. ✅ **并行执行**: 至少 3 个任务并行执行
3. ✅ **冲突管理**: 检测到冲突时自动串行化
4. ✅ **输出质量**: 最终报告质量评分 >= 70%
5. ✅ **性能目标**: 并行比串行节省 >= 20% 时间

---

**文档版本**: 1.0  
**最后更新**: 2026-01-12 18:40
