# Memory-First Protocol

> 📅 **最后更新**: 2025-12-30  
> 🎯 **适用版本**: V4.0  
> 🔗 **参考**: Claude Platform Memory Tool

---

## 🆕 V4.0 更新要点

### 关键变化

1. **记忆层级化**：WorkingMemory → MemoryManager（统一管理三层记忆）
2. **WorkingMemory 纯净化**：不再包含 plan_json/todo_md
3. **plan_todo 纯计算化**：无状态工具，返回纯 JSON
4. **❌ 移除 todo.md**：不再生成 Markdown，改用 SSE + JSON
5. **✅ 前端自渲染**：通过 `plan_update` 事件接收 JSON，自由渲染 UI
6. **数据持久化**：Service 层将 plan 存入 `Conversation.metadata.plan`
7. **文件路径变化**：`core/memory.py` → `core/memory/` 目录
8. **新增用户级/系统级记忆**：支持跨会话持久化

### 核心原则（不变）

```
⚠️ CRITICAL: ASSUME INTERRUPTION

Your context window might reset at any moment.
所有进度必须记录在 plan_todo 工具中，否则会丢失。

NEVER trust your thinking memory - ALWAYS read from plan_todo.get_plan()
```

**V4.0 强化**：
- ✅ MemoryManager 提供统一入口
- ✅ WorkingMemory 职责更清晰
- ✅ plan_todo 纯计算化（无状态）
- ✅ **SSE + JSON 架构**：实时推送 + 前端自由渲染
- ✅ 数据与视图分离：plan.json 存数据库，UI 由前端决定
- ✅ 支持更多记忆类型（用户级/系统级）

### 🎯 V4.0 核心特性：SSE + JSON

```
旧设计（V3.7）                    新设计（V4.0）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
plan_todo → todo.md              plan_todo → plan.json
   ↓                                ↓
前端渲染 Markdown                Service 层持久化
   ↓                                ↓
❌ 固定格式                      SSE: emit_plan_update()
❌ 需解析文本                       ↓
❌ 难以扩展                      Frontend 接收 JSON
                                    ↓
                                 ✅ 自由渲染（进度条/看板/时间线）
                                 ✅ 实时更新
                                 ✅ 易于扩展
```

**关键收益**：
1. 🎨 **UI 灵活性**：前端可以渲染任意样式
2. ⚡ **实时性**：SSE 推送，无需轮询
3. 📦 **数据与视图分离**：plan.json 是纯数据
4. 🔧 **易维护**：Tool 无状态，Service 层负责持久化
5. 📊 **易扩展**：添加字段无需修改 Tool 代码

---

## 1. V4.0 架构图

```
User Query
    │
    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     SimpleAgent (V4.0)                               │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │              MemoryManager (统一入口)                           │ │
│  │  ┌──────────────────────────────────────────────────────────┐  │ │
│  │  │         WorkingMemory (会话级短期记忆)                    │  │ │
│  │  │  • messages: 消息历史                                     │  │ │
│  │  │  • tool_calls: 工具调用记录                               │  │ │
│  │  │  • metadata: 临时元数据                                   │  │ │
│  │  │                                                           │  │ │
│  │  │  ⚠️ 不再包含 plan_json/todo_md（由 plan_todo 工具管理）  │  │ │
│  │  └──────────────────────────────────────────────────────────┘  │ │
│  │                            ↕ CRUD                               │ │
│  │  ┌──────────────────────────────────────────────────────────┐  │ │
│  │  │  plan_todo Tool（工具层 - 纯计算版本）                  │  │ │
│  │  │  • 内部状态：plan.json（RVR 调度）                       │  │ │
│  │  │  • 不生成 Markdown：前端自己渲染 ✅                      │  │ │
│  │  │  • 通过 SSE 事件发送 JSON 到前端                         │  │ │
│  │  │                                                           │  │ │
│  │  │  API:                                                     │  │ │
│  │  │  ├─ create_plan → 创建计划                               │  │ │
│  │  │  ├─ update_step → 更新步骤（每步后 MANDATORY）           │  │ │
│  │  │  └─ add_step → 动态添加步骤                              │  │ │
│  │  │                                                           │  │ │
│  │  │  返回纯 JSON → Service 层持久化 → SSE 通知前端          │  │ │
│  │  └──────────────────────────────────────────────────────────┘  │ │
│  │                                                                 │ │
│  │  ┌──────────────────────────────────────────────────────────┐  │ │
│  │  │         用户级记忆（User Memory）                         │  │ │
│  │  │  • episodic: 历史总结（跨会话）                          │  │ │
│  │  │  • e2b: E2B 沙箱会话                                     │  │ │
│  │  │  • preference: 用户偏好                                  │  │ │
│  │  └──────────────────────────────────────────────────────────┘  │ │
│  │                                                                 │ │
│  │  ┌──────────────────────────────────────────────────────────┐  │ │
│  │  │         系统级记忆（System Memory）                       │  │ │
│  │  │  • skill: Skills 缓存                                    │  │ │
│  │  │  • cache: 系统缓存                                       │  │ │
│  │  └──────────────────────────────────────────────────────────┘  │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                                                                      │
│  核心原则（V4.0）：                                                  │
│  • MemoryManager 统一管理三层记忆                                    │
│  • WorkingMemory 纯净化（不包含 plan/todo）                         │
│  • plan_todo 作为独立工具，LLM 显式调用                             │
│  • 用户级/系统级记忆支持跨会话持久化                                 │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 2. V4.0 记忆层级

### 2.1 三层记忆架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                       Memory Hierarchy (V4.0)                        │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  会话级（Session Level）- WorkingMemory                              │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│  • messages: 当前对话消息                                            │
│  • tool_calls: 工具调用记录                                          │
│  • metadata: 临时元数据                                              │
│                                                                      │
│  生命周期：单个 session，结束后清除                                  │
│  存储位置：内存（不持久化）                                          │
│                                                                      │
│  用户级（User Level）- 跨会话持久化                                  │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│  • episodic: 历史总结（学习用户习惯）                                │
│  • e2b: E2B 沙箱会话（云端计算环境）                                 │
│  • preference: 用户偏好                                              │
│                                                                      │
│  生命周期：长期保存，用户生命周期                                    │
│  存储位置：数据库 / 文件系统                                         │
│                                                                      │
│  系统级（System Level）- 全局共享                                    │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│  • skill: Skills 元数据缓存                                          │
│  • cache: 系统级缓存                                                 │
│                                                                      │
│  生命周期：进程生命周期，所有用户共享                                │
│  存储位置：内存（可选持久化）                                        │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 使用场景

| 记忆类型 | 使用场景 | 示例 |
|---------|---------|------|
| **WorkingMemory** | 当前对话追踪 | 消息历史、工具调用序列 |
| **EpisodicMemory** | 跨会话学习 | "用户喜欢简洁的报告" |
| **E2BMemory** | 代码执行环境 | 保持沙箱状态、文件系统 |
| **PreferenceMemory** | 用户偏好 | 语言偏好、主题样式 |
| **SkillMemory** | Skills 加速 | 缓存 Skills 元数据 |
| **CacheMemory** | 性能优化 | API 响应缓存 |

### 2.3 V4.0 关键改进

**V3.7 vs V4.0**：

| 维度 | V3.7 | V4.0 | 改进 |
|------|------|------|------|
| **WorkingMemory** | 包含 plan_json/todo_md | 纯净化，不包含 plan | ✅ 职责清晰 |
| **记忆层级** | 单层 | 三层（Session/User/System） | ✅ 清晰分层 |
| **管理器** | 无统一管理 | MemoryManager 统一入口 | ✅ 易用性 |
| **持久化** | 混乱 | 按层级明确 | ✅ 可维护 |
| **plan_todo** | 存储在 WorkingMemory | 独立工具管理 | ✅ 解耦 |

**核心原则（不变）**：
- ✅ Memory-First：始终从 Memory 读取状态
- ✅ 显式调用：LLM 必须主动调用 plan_todo.get_plan()
- ✅ 防中断：支持 context window reset

---

## 3. 强制协议（MANDATORY）

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

## 4. plan_todo 工具 API

### 4.1 创建计划

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
- `plan`: JSON 格式计划（内部 RVR 调度）
- `status`: 操作状态（success/error）
- `message`: 操作结果描述

**事件流**:
```
LLM 调用 plan_todo → Tool 返回 JSON → Service 持久化 
    → emit_plan_update(plan) → SSE → 前端渲染 UI
```

### 4.2 读取计划（每步开始前 MANDATORY！）

```json
{
  "operation": "get_plan"
}
```

**返回示例**:
```json
{
  "status": "success",
  "plan": {
    "goal": "生成报告",
    "status": "executing",
    "current_step": 1,
    "total_steps": 5,
    "steps": [
      {
        "step_id": 1,
        "action": "bash",
        "purpose": "处理数据",
        "status": "in_progress",
        "result": null
      }
      // ... 其他步骤
    ]
  }
}
```

### 4.3 更新步骤（每步结束后 MANDATORY！）

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

**工具返回**:
- 更新后的 plan.json
- 自动推进 current_step
- Service 层持久化并触发 SSE 事件

**事件通知**:
```python
# Service 层监听 plan_todo 结果
await event_manager.system.emit_plan_update(
    session_id=session_id,
    plan=updated_plan
)
# → SSE → Frontend 接收并渲染
```

---

## 5. 数据结构

### 5.1 plan.json（内部 RVR 调度）

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

### 5.2 前端渲染（基于 SSE + JSON）

**V4.0 设计：不生成 Markdown，前端自己渲染**

```
数据流：
┌─────────────┐  tool_result   ┌─────────────┐  persist   ┌─────────────┐
│ plan_todo   │───────────────►│ChatService  │───────────►│  Database   │
│  (纯计算)   │    plan_json   │  (业务层)   │            │(Conversation│
└─────────────┘                └──────┬──────┘            │ .metadata)  │
                                      │                   └─────────────┘
                                      │ emit_plan_update
                                      ▼
                               ┌─────────────┐
                               │     SSE     │
                               │  (事件流)   │
                               └──────┬──────┘
                                      │ plan_update event
                                      ▼
                               ┌─────────────┐
                               │   Frontend  │
                               │  (自渲染)   │
                               └─────────────┘
```

**前端接收的 JSON 格式**:

```json
{
  "event": "plan_update",
  "data": {
    "plan": {
      "task_id": "task_20251230_001",
      "goal": "生成AI市场分析报告",
      "status": "executing",
      "current_step": 1,
      "total_steps": 3,
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
  }
}
```

**前端渲染方式（自由选择）**:
- ✅ 进度条（Progress Bar）
- ✅ 看板（Kanban Board）
- ✅ 时间线（Timeline）
- ✅ 列表（Checklist）
- ✅ 自定义 UI 组件

**优势**：
- 🎨 前端完全控制样式
- 🔄 支持多种渲染方式
- ⚡ 实时更新（SSE）
- 📦 数据与视图分离

---

## 6. 完整示例（V4.0 SSE + JSON 版本）

```
Turn 1: 创建 Plan
  → [Reason] 任务复杂，需要创建 Plan
  → [Act] plan_todo.create_plan({goal: "生成AI市场报告", steps: [...]})
  → [Observe] Tool 返回 plan.json
  → [Service] 持久化到 Conversation.metadata.plan
  → [SSE] emit_plan_update(plan) → Frontend 收到并渲染进度 UI

Turn 2: 执行步骤 1
  → [Read] plan_todo 自动从 Service 层获取当前 plan
  → [Observe] 当前步骤：web_search - 收集市场信息
  → [Reason] 需要搜索 AI 市场数据
  → [Act] web_search("AI 市场规模 2024")
  → [Observe] 找到 5 篇相关文章
  → [Validate] 质量检查 → PASS
  → [Write] plan_todo.update_step({step_index: 0, status: "completed", result: "..."})
  → [Service] 更新 Conversation.metadata.plan
  → [SSE] emit_plan_update(updated_plan) → Frontend 实时更新进度

Turn 3: 执行步骤 2
  → [Read] plan_todo 获取最新 plan（从数据库）
  → [Observe] 当前步骤：bash - 处理数据
  → [Reason] 需要运行数据处理脚本
  → [Act] bash("python3 process_data.py")
  → [Observe] 数据处理完成
  → [Validate] 输出文件正确 → PASS
  → [Write] plan_todo.update_step({step_index: 1, status: "completed", result: "..."})
  → [SSE] emit_plan_update(updated_plan) → Frontend 更新
  → ...
```

**前端接收的事件序列**:

```javascript
// Turn 1: 创建 Plan
{
  event: "plan_update",
  data: {
    plan: {
      goal: "生成AI市场报告",
      status: "executing",
      current_step: 0,
      total_steps: 3,
      steps: [
        { step_id: 1, action: "web_search", status: "pending", ... },
        { step_id: 2, action: "bash", status: "pending", ... },
        { step_id: 3, action: "生成报告", status: "pending", ... }
      ]
    }
  }
}

// Turn 2: 完成步骤 1
{
  event: "plan_update",
  data: {
    plan: {
      current_step: 1,
      steps: [
        { step_id: 1, action: "web_search", status: "completed", result: "找到5篇文章" },
        { step_id: 2, action: "bash", status: "in_progress", ... },
        ...
      ]
    }
  }
}

// Frontend 根据 JSON 实时更新 UI（进度条、看板等）
```

---

## 7. 为什么必须这样做？

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

## 8. 与 Claude Platform Memory Tool 对比

| Claude Platform | V4.0 实现 | 说明 |
|----------------|----------|------|
| `memory.view()` | `plan_todo` 返回 JSON | 读取当前状态 |
| `memory.write()` | `plan_todo.update_step()` | 写入进度 |
| `memory.json` | `plan.json` | 结构化状态数据 |
| `memory.txt` | ~~todo.md~~ → **SSE + JSON** | ❌ 不生成 Markdown，前端自渲染 |
| 文件系统持久化 | Conversation.metadata.plan | Service 层持久化到数据库 |
| - | MemoryManager | V4.0 统一管理器 |
| - | WorkingMemory | 会话级消息历史 |
| - | User/System Memory | V4.0 跨会话记忆 |
| - | SSE Event: `plan_update` | V4.0 实时推送 JSON |

### V4.0 架构对比

```
Claude Platform Memory:
  memory.json (持久化) → 文件系统
  memory.txt (Markdown) → 人类可读
  
V4.0 Memory Architecture:
  plan_todo (纯计算) → plan.json (纯数据)
    ↓
  Service 层 → Conversation.metadata.plan (数据库持久化)
    ↓
  SSE Event → plan_update (实时推送)
    ↓
  Frontend → 自定义渲染（进度条/看板/时间线...）
  
  MemoryManager.working → messages + tool_calls
  MemoryManager.episodic → 跨会话总结（持久化）
  MemoryManager.e2b → E2B 沙箱状态（持久化）
```

**关键差异**：

| 维度 | Claude Platform | V4.0 ZenFlux |
|------|----------------|--------------|
| **Plan 存储** | 文件系统 | 数据库（Conversation.metadata） |
| **用户展示** | memory.txt（Markdown） | SSE + JSON → 前端渲染 |
| **工具设计** | 有状态（文件） | 无状态（纯计算） |
| **记忆层级** | 单层 | 三层（Session/User/System） |
| **实时更新** | 不支持 | ✅ SSE 实时推送 |
| **UI 灵活性** | 固定 Markdown | ✅ 前端自由渲染 |

**核心机制相同**：LLM 必须主动读写 Memory，不能依赖 thinking！

---

## 9. V4.0 代码位置

### 核心记忆模块

| 组件 | V4.0 文件路径 | 职责 |
|------|-------------|------|
| **MemoryManager** | `core/memory/manager.py` | 统一记忆管理器 |
| **WorkingMemory** | `core/memory/working.py` | 会话级短期记忆 |
| **EpisodicMemory** | `core/memory/user/episodic.py` | 用户历史总结 |
| **E2BMemory** | `core/memory/user/e2b.py` | E2B 沙箱会话 |
| **PreferenceMemory** | `core/memory/user/preference.py` | 用户偏好 |
| **SkillMemory** | `core/memory/system/skill.py` | Skills 缓存 |
| **CacheMemory** | `core/memory/system/cache.py` | 系统缓存 |

### Plan/Todo 工具

| 组件 | 文件路径 | 职责 |
|------|---------|------|
| **PlanTodoTool** | `tools/plan_todo_tool.py` | Plan/Todo 纯计算工具（无状态） |
| **能力定义** | `config/capabilities.yaml` | plan_todo 工具配置 |
| **数据持久化** | `models/database.py` | Conversation.metadata.plan |

### SSE 事件

| 组件 | 文件路径 | 职责 |
|------|---------|------|
| **SystemEventManager** | `core/events/system_events.py` | plan_update 事件发射 |
| **ChatService** | `services/chat_service.py` | 监听 tool 结果 + 触发 SSE |
| **事件协议** | `docs/03-EVENT-PROTOCOL.md` | 统一事件格式规范（SSE/WebSocket） |

### 提示词

| 组件 | 文件路径 | 内容 |
|------|---------|------|
| **System Prompt** | `prompts/universal_prompt.py` | Planning Protocol 规则 |
| **Memory Protocol** | `docs/01-MEMORY-PROTOCOL.md` | 本文档 |

### 架构文档

| 文档 | 路径 | 说明 |
|------|------|------|
| **V4.0 架构总览** | `docs/00-ARCHITECTURE-V4.md` | 完整架构说明 |
| **Memory Protocol** | `docs/01-MEMORY-PROTOCOL.md` | Memory-First 协议 |

---

## 10. SSE 事件流详解（V4.0 核心特性）

### 10.1 完整的事件流

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Plan 更新事件流                               │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  1️⃣ LLM 调用 plan_todo 工具                                          │
│     {                                                                │
│       "operation": "create_plan",                                    │
│       "data": { "goal": "...", "steps": [...] }                     │
│     }                                                                │
│                                                                      │
│  2️⃣ PlanTodoTool 执行（纯计算）                                      │
│     → 返回 plan.json（纯数据）                                       │
│                                                                      │
│  3️⃣ SimpleAgent 接收 tool_result                                     │
│     → 传递给 EventManager                                            │
│                                                                      │
│  4️⃣ ChatService 监听到 plan_todo 结果                                │
│     → 持久化到 Conversation.metadata.plan（数据库）                  │
│     → 调用 event_manager.system.emit_plan_update(plan)               │
│                                                                      │
│  5️⃣ SSE 推送到前端                                                   │
│     event: plan_update                                               │
│     data: { "plan": { ... } }                                        │
│                                                                      │
│  6️⃣ Frontend 接收并渲染                                              │
│     → 更新进度条 / 看板 / 时间线                                     │
│     → 用户实时看到进度变化                                           │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### 10.2 事件格式

**plan_update 事件结构**:

```typescript
interface PlanUpdateEvent {
  event: "plan_update";
  data: {
    plan: {
      task_id: string;
      goal: string;
      status: "planning" | "executing" | "completed" | "failed";
      current_step: number;
      total_steps: number;
      created_at: string;
      updated_at: string;
      steps: Array<{
        step_id: number;
        action: string;
        purpose: string;
        status: "pending" | "in_progress" | "completed" | "failed";
        result: string | null;
        error: string | null;
      }>;
    };
  };
}
```

### 10.3 前端渲染示例

**React 示例**:

```tsx
import { useEffect, useState } from 'react';

function PlanProgress() {
  const [plan, setPlan] = useState(null);
  
  useEffect(() => {
    const eventSource = new EventSource('/api/chat/stream');
    
    eventSource.addEventListener('plan_update', (e) => {
      const { plan } = JSON.parse(e.data);
      setPlan(plan);
    });
    
    return () => eventSource.close();
  }, []);
  
  if (!plan) return null;
  
  const progress = (plan.current_step / plan.total_steps) * 100;
  
  return (
    <div className="plan-progress">
      <h3>{plan.goal}</h3>
      <div className="progress-bar">
        <div style={{ width: `${progress}%` }} />
      </div>
      <ul>
        {plan.steps.map((step) => (
          <li key={step.step_id} className={step.status}>
            {step.status === 'completed' && '✅ '}
            {step.status === 'in_progress' && '🔄 '}
            {step.status === 'pending' && '○ '}
            {step.action} - {step.purpose}
            {step.result && <span>: {step.result}</span>}
          </li>
        ))}
      </ul>
    </div>
  );
}
```

### 10.4 与旧版本对比

| 维度 | V3.7（todo.md） | V4.0（SSE + JSON） |
|------|----------------|-------------------|
| **数据格式** | Markdown 文本 | 结构化 JSON |
| **渲染方式** | 固定格式 | 前端自由设计 |
| **更新方式** | 轮询/重载 | SSE 实时推送 |
| **UI 灵活性** | ❌ 受限 | ✅ 完全自由 |
| **性能** | ❌ 需解析 Markdown | ✅ 直接使用 JSON |
| **扩展性** | ❌ 难以添加字段 | ✅ 易于扩展 |

---

## 11. V4.0 最佳实践

### 11.1 何时使用哪种记忆？

```python
# 会话级消息历史 → WorkingMemory
memory_manager.working.add_message(role="user", content="...")
memory_manager.working.get_messages()

# Plan/Todo 状态管理 → plan_todo 工具
await agent.chat("创建报告")  # LLM 内部调用 plan_todo.create_plan()
# LLM 自动调用 plan_todo.get_plan() / update_step()

# 用户历史学习 → EpisodicMemory
summary = await memory_manager.episodic.get_summary()
await memory_manager.episodic.add_episode(session_data)

# E2B 沙箱环境 → E2BMemory
sandbox_id = await memory_manager.e2b.get_or_create_sandbox()
await memory_manager.e2b.record_execution(sandbox_id, code, result)

# Skills 加速 → SkillMemory
skills = await memory_manager.skill.list_loaded_skills()
```

### 11.2 初始化模式

```python
from core.memory import create_memory_manager

# 基础模式（仅会话级）
memory = create_memory_manager()

# 用户模式（包含用户级记忆）
memory = create_memory_manager(
    user_id="user-123",
    storage_dir="/data/memory"
)

# 访问各层记忆
memory.working     # 会话级（总是可用）
memory.episodic    # 用户级（懒加载）
memory.e2b         # 用户级（懒加载）
memory.skill       # 系统级（懒加载）
```

### 11.3 清理模式

```python
# 会话结束清理
async def end_session():
    # 1. 保存重要信息到用户级记忆（可选）
    if should_save:
        await memory.episodic.add_episode({
            "summary": "用户完成了报告生成",
            "insights": ["偏好简洁风格"]
        })
    
    # 2. 清空会话级记忆
    memory.working.clear()
    
    # 3. E2B 沙箱按需清理
    if temporary_sandbox:
        await memory.e2b.cleanup_sandbox(sandbox_id)
```

### 11.4 性能优化

```python
# ✅ 推荐：按需访问用户级记忆
if need_history:
    summary = await memory.episodic.get_summary()

# ❌ 避免：每次都读取（浪费）
summary = await memory.episodic.get_summary()  # 不需要时不要调用

# ✅ 推荐：批量操作
messages = memory.working.get_messages(last_n=10)

# ❌ 避免：循环调用
for i in range(10):
    msg = memory.working.get_messages(last_n=1)  # 效率低
```

### 11.5 错误处理

```python
# plan_todo 协议必须遵守
try:
    # 步骤开始前 - MANDATORY
    plan = await plan_todo_tool.execute("get_plan", {})
    
    # 执行工具...
    
    # 步骤结束后 - MANDATORY
    await plan_todo_tool.execute("update_step", {
        "step_index": 0,
        "status": "completed",
        "result": "..."
    })
except Exception as e:
    # 失败时也要更新状态
    await plan_todo_tool.execute("update_step", {
        "step_index": 0,
        "status": "failed",
        "result": str(e)
    })
    raise
```

---

## 🔗 相关文档

| 文档 | 说明 | 状态 |
|------|------|------|
| [00-ARCHITECTURE-V4.md](./00-ARCHITECTURE-V4.md) | V4.0 完整架构 | ✅ 最新 |
| [01-MEMORY-PROTOCOL.md](./01-MEMORY-PROTOCOL.md) | 本文档 | ✅ V4.0 |
| [03-EVENT-PROTOCOL.md](./03-EVENT-PROTOCOL.md) | 统一事件协议 | ✅ 有效 |

