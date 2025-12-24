# Memory-First Protocol

> 📅 **最后更新**: 2025-12-23  
> 🔗 **参考**: Claude Platform Memory Tool

---

## 核心原则

```
⚠️ CRITICAL: ASSUME INTERRUPTION

Your context window might reset at any moment.
所有进度必须记录在 Short Memory (plan_todo) 中，否则会丢失。

NEVER trust your thinking memory - ALWAYS read from plan_todo.get_plan()
```

---

## 1. 架构图

```
User Query
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│                         Agent                                │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │           WorkingMemory (Short Memory)                  │ │
│  │  ┌───────────┐  ┌───────────┐                          │ │
│  │  │ plan.json │  │  todo.md  │  ← 会话级存储            │ │
│  │  │ (内部RVR) │  │ (用户展示)│     避免多轮 token 浪费  │ │
│  │  └─────↑─────┘  └─────↑─────┘                          │ │
│  └────────┴──────────────┴────────────────────────────────┘ │
│           │ CRUD (via plan_todo tool)                        │
│  ┌────────┴──────────────────────────────────────────────┐  │
│  │              plan_todo Tool                            │  │
│  │  ├─ create_plan → 写入 Memory                         │  │
│  │  ├─ get_plan → 读取 Memory（每步开始前 MANDATORY）    │  │
│  │  ├─ update_step → 更新 Memory（每步结束后 MANDATORY） │  │
│  │  └─ clear → 清空 Memory                               │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                              │
│  LLM 通过 plan_todo 工具管理计划                             │
│  Plan/Todo 存储在 Short Memory，不在每轮 input/output 中     │
└──────────────────────────────────────────────────────────────┘
```

---

## 2. 强制协议（MANDATORY）

### 每个步骤的标准流程

```
Turn N: 执行步骤 X
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│ 1️⃣ [Read] 步骤开始前 - MANDATORY                            │
│    └─ 调用 plan_todo.get_plan()                            │
│    └─ 读取 current_step, current_action                    │
│    └─ 确认状态（避免重复执行已完成步骤）                    │
│                                                             │
│ 2️⃣ [Act] 执行工具调用                                       │
│    └─ 根据 plan.json 指示执行相应工具                       │
│                                                             │
│ 3️⃣ [Observe] 观察结果                                       │
│    └─ 分析工具返回                                          │
│                                                             │
│ 4️⃣ [Validate] 验证质量                                      │
│    └─ 检查结果完整性                                        │
│    └─ 决定 status: completed|failed|retry                   │
│                                                             │
│ 5️⃣ [Write] 步骤完成后 - MANDATORY                           │
│    └─ 调用 plan_todo.update_step()                         │
│    └─ 更新步骤状态和结果                                    │
│    └─ 写入 Short Memory                                     │
│                                                             │
│ 6️⃣ [Next] 继续或结束                                        │
│    └─ 如果还有未完成步骤 → 下一轮                           │
│    └─ 如果所有步骤完成 → end_turn                           │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. plan_todo 工具 API

### 3.1 创建计划

```json
{
  "operation": "create_plan",
  "data": {
    "goal": "目标描述",
    "steps": [
      {"action": "web_search", "purpose": "收集信息"},
      {"action": "bash", "purpose": "处理数据"},
      {"action": "生成输出", "purpose": "完成任务"}
    ]
  }
}
```

**返回**:
- `plan_json`: JSON 格式计划（内部 RVR 调度）
- `todo_md`: Markdown 格式进度（用户展示）
- `context`: 精简上下文（避免 token 浪费）

### 3.2 读取计划（每步开始前 MANDATORY！）

```json
{
  "operation": "get_plan"
}
```

**返回示例**:
```json
{
  "status": "success",
  "has_plan": true,
  "context": "[Plan Context]\nGoal: 生成报告\nStatus: executing | Step: 2/5\nCurrent: bash → 处理数据"
}
```

### 3.3 更新步骤（每步结束后 MANDATORY！）

```json
{
  "operation": "update_step",
  "data": {
    "step_index": 0,
    "status": "completed",  // completed|failed|in_progress
    "result": "步骤结果描述"
  }
}
```

**工具自动**:
- 更新 plan.json 中的步骤状态
- 重新生成 todo.md
- 推进 current_step

---

## 4. 数据结构

### 4.1 plan.json（内部 RVR 调度）

```json
{
  "task_id": "task_20251223_001",
  "goal": "生成AI市场分析报告",
  "created_at": "2025-12-23T11:30:00Z",
  "status": "executing",
  "current_step": 1,
  "total_steps": 3,
  "retry_count": 0,
  "steps": [
    {
      "step_id": 1,
      "action": "web_search",
      "purpose": "收集市场信息",
      "status": "completed",
      "result": "找到5篇行业报告"
    },
    {
      "step_id": 2,
      "action": "bash",
      "purpose": "处理数据",
      "status": "in_progress",
      "result": null
    },
    {
      "step_id": 3,
      "action": "生成报告",
      "purpose": "完成任务",
      "status": "pending",
      "result": null
    }
  ]
}
```

### 4.2 todo.md（用户展示 + 状态追踪）

```markdown
<!-- Status: executing | Step: 2/3 | Retry: 0 -->

# 📋 任务进度

🎯 **目标**: 生成AI市场分析报告

## To-do List

- [x] ✅ Step 1: web_search → 收集市场信息 - 找到5篇行业报告
- [ ] 🔄 Step 2: bash → 处理数据 - 执行中...
- [ ] ○ Step 3: 生成报告 → 完成任务

---
**进度**: [██████████░░░░░░░░░░] 33% (1/3)
**阶段**: executing
```

**首行注释**包含状态元数据，Agent 可快速读取。

---

## 5. 完整示例

```
Turn 1:
  → [Reason] 任务复杂，需要创建 Plan
  → [Act] plan_todo.create_plan({goal: "...", steps: [...]})
  → [Observe] Plan 已创建

Turn 2:
  → [Read] plan_todo.get_plan()  ← MANDATORY
  → [Observe] context = "Status: executing | Step: 1/3"
  → [Reason] 当前步骤是 web_search - 收集市场信息
  → [Act] web_search("AI 市场规模 2024")
  → [Observe] 找到 5 篇相关文章
  → [Validate] 质量检查 → PASS
  → [Write] plan_todo.update_step({step_index: 0, status: "completed", result: "..."})  ← MANDATORY

Turn 3:
  → [Read] plan_todo.get_plan()  ← MANDATORY
  → [Observe] context = "Status: executing | Step: 2/3"
  → [Reason] 当前步骤是 bash - 处理数据
  → [Act] bash("python3 process_data.py")
  → ...
```

---

## 6. 为什么必须这样做？

### 问题：不读取 Memory，依赖 Thinking

```
❌ 错误做法:
Turn 2:
  [Reason] 我记得 Plan 有 3 个步骤，现在执行第 1 步
  [Act] 调用 web_search(...)
  [Observe] ...

问题：
- Context window 可能在 Turn 1 和 Turn 2 之间 reset
- "我记得" 的信息可能过时或错误
- 可能重复执行已完成的步骤
```

### 正确：每次从 Memory 读取

```
✅ 正确做法:
Turn 2:
  [Act] plan_todo.get_plan()  ← 真实状态来源
  [Observe] context = "Status: executing | Step: 1/3"
  [Reason] 根据 Memory 中的状态，当前执行第 1 步
  [Act] 调用 web_search(...)
  [Observe] ...
  [Act] plan_todo.update_step(...)  ← 写回最新状态

优势：
- 状态始终同步
- 支持 context reset
- 避免重复执行
- 真正的 Short Memory 机制
```

---

## 7. 与 Claude Platform Memory Tool 对比

| Claude Platform | 我们的实现 | 说明 |
|----------------|----------|------|
| `memory.view()` | `plan_todo.get_plan()` | 读取当前状态 |
| `memory.write()` | `plan_todo.update_step()` | 写入进度 |
| `memory.json` | `plan.json` | 结构化状态数据 |
| `memory.txt` | `todo.md` | 用户可读的进度 |
| 文件系统持久化 | WorkingMemory | 会话级存储 |

**关键差异**：
- Claude Platform Memory Tool 存储在文件系统（持久化）
- 我们的 plan_todo 存储在 WorkingMemory（会话级，自动清除）

**核心机制相同**：LLM 必须主动读写 Memory，不能依赖 thinking！

---

## 8. 代码位置

| 组件 | 文件 |
|------|------|
| WorkingMemory | `agent_v3/core/memory.py` |
| PlanTodoTool | `agent_v3/tools/plan_todo_tool.py` |
| capabilities.yaml | `agent_v3/config/capabilities.yaml` (plan_todo 定义) |
| System Prompt | `agent_v3/prompts/universal_prompt.py` (Planning Protocol) |
| Memory Protocol 详细说明 | `agent_v3/prompts/MEMORY_PROTOCOL.md` |

