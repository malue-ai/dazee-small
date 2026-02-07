# Memory Protocol（参考 Claude Platform Memory Tool）

## 核心原则

```
⚠️ CRITICAL: ASSUME INTERRUPTION

Your context window might reset at any moment.
所有进度必须记录在 Plan（plan 工具 + 注入的 “## 当前任务计划”）中，否则会丢失。

NEVER trust your thinking memory - ALWAYS read the injected "## 当前任务计划" at the end of the latest user message.
```

## 强制协议（MANDATORY）

### React 循环中的 Memory 交互

每个步骤的标准流程：

```
┌─────────────────────────────────────────────────────────┐
│ Turn N: 执行步骤 X                                       │
├─────────────────────────────────────────────────────────┤
│                                                         │
│ 1️⃣ [Reason] 准备执行步骤                                 │
│    ├─ MANDATORY: 阅读末尾注入的 “## 当前任务计划”        │
│    ├─ 读取未完成步骤与当前进行中步骤                       │
│    └─ 确认状态（避免重复执行已完成步骤）                    │
│                                                         │
│ 2️⃣ [Act] 执行工具调用                                    │
│    └─ 根据 plan.json 指示执行相应工具                    │
│                                                         │
│ 3️⃣ [Observe] 观察结果                                   │
│    └─ 分析工具返回                                       │
│                                                         │
│ 4️⃣ [Validate] 验证质量                                  │
│    ├─ 检查结果完整性                                     │
│    └─ 决定 status: completed|failed|retry               │
│                                                         │
│ 5️⃣ [Update] 写回 Memory                                 │
│    ├─ MANDATORY: 调用 plan(action="update")              │
│    ├─ 更新步骤状态和结果（todo_id/status/result）          │
│    └─ 写回 Plan（持久化到会话 metadata）                   │
│                                                         │
│ 6️⃣ [Next] 继续或结束                                    │
│    ├─ 如果还有未完成步骤 → 下一轮                         │
│    └─ 如果所有步骤完成 → end_turn                        │
└─────────────────────────────────────────────────────────┘
```

## 完整示例

### Turn 1: 创建 Plan

```
[Reason] 任务复杂，需要多步骤，创建 Plan
[Act] 调用 plan(action="create", name="生成AI市场分析报告", todos=[
  {"id": "1", "content": "收集市场信息", "status": "pending"},
  {"id": "2", "content": "收集技术趋势", "status": "pending"},
  {"id": "3", "content": "整合数据", "status": "pending"},
  {"id": "4", "content": "撰写报告", "status": "pending"}
])
[Observe] Plan 已创建，存入 Short Memory
```

### Turn 2: 执行 Step 1

```
[Reason] 准备执行第一步
[Act] 阅读末尾注入的 “## 当前任务计划”  ← 强制读取
[Observe] 看到当前步骤是：搜索类 Skill → 收集市场信息（Step 1/4）

[Reason] 当前步骤是搜索 - 收集市场信息
[Act] 调用搜索类 Skill 或可用工具（"AI 市场规模 2024"）
[Observe] 找到 5 篇相关文章

[Validate] 
  - 结果数量充足 ✓
  - 信息相关性高 ✓
  - 质量评分: 8/10
  → Decision: PASS

[Act] 调用 plan(action="update", todo_id="1", status="completed", result="找到5篇行业报告，包含市场规模、增长率数据")  ← 强制写回
[Observe] Short Memory 已更新，current_step: 1 → 2
```

### Turn 3: 执行 Step 2

```
[Reason] 继续执行
[Act] 阅读末尾注入的 “## 当前任务计划”  ← 每次都要读取！
[Observe] 看到当前步骤是：搜索类 Skill → 收集技术趋势（Step 2/4）

[Reason] 当前步骤是搜索 - 收集技术趋势（Step 1 已完成）
[Act] 调用搜索类 Skill 或可用工具（"AI 技术趋势 2024"）
[Observe] ...
[Validate] ...
[Act] 调用 plan(action="update", todo_id="2", status="completed", result="...")  ← 写回
```

## 为什么必须这样做？

### 问题：不读取 Memory，依赖 Thinking

```
❌ 错误做法:
Turn 2:
  [Reason] 我记得 Plan 有 4 个步骤，现在执行第 1 步
  [Act] 调用搜索类 Skill / 工具(...)
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
  [Act] 阅读末尾注入的 “## 当前任务计划”  ← 真实状态来源
  [Observe] 当前状态 = "Step: 1/4"
  [Reason] 根据 Memory 中的状态，当前执行第 1 步
  [Act] 调用搜索类 Skill 或可用工具(...)
  [Observe] ...
  [Act] 调用 plan(action="update", todo_id="1", status="completed", result="...")  ← 写回最新状态

优势：
- 状态始终同步
- 支持 context reset
- 避免重复执行
- 真正的 Short Memory 机制
```

## 与 Claude Platform Memory Tool 的对应关系

| Claude Platform | 我们的实现 | 说明 |
|----------------|----------|------|
| `memory.view()` | 阅读 “## 当前任务计划”（注入） | 读取当前状态 |
| `memory.write()` | `plan(action="update")` | 写入进度 |
| `memory.json` | `plan.json` | 结构化状态数据 |
| `memory.txt` | `todo.md` | 用户可读的进度 |
| Context reset resilient | Short Memory 存储 | 状态持久化 |

## 关键差异

### Claude Platform Memory Tool
- 存储在文件系统（持久化）
- 跨会话共享
- Git 版本控制

### 我们的 plan（Short Memory）
- 存储在 Conversation.metadata.plan（会话级持久化）
- 每轮会把摘要注入到用户消息末尾供你读取
- 你必须用 plan(action="update") 写回最新状态

**但核心机制相同：LLM 必须主动读写 Memory，不能依赖 thinking！**

