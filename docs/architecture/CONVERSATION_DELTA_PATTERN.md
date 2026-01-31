# Conversation Delta 更新模式

## 📋 设计目标

统一 Conversation 的增量更新机制，前端使用简单的合并逻辑即可处理所有更新。

---

## 🎯 核心概念

### Conversation 数据结构

```json
{
  "id": "conv_123",
  "title": "新对话",
  "created_at": "2024-01-01T12:00:00Z",
  "updated_at": "2024-01-01T12:05:00Z",
  "metadata": {
    "plan": {...},      // plan_todo_tool 返回的完整 plan
    "context": {...},   // 上下文压缩信息
    "tags": [...],      // 标签
    "custom": {...}     // 自定义数据
  }
}
```

---

## 🔄 统一更新模式：`conversation_delta`

### 核心事件

```json
{
  "type": "conversation_delta",
  "data": {
    "conversation_id": "conv_123",
    "delta": {
      // 任何需要更新的字段
      "title": "新标题",       // 可选
      "plan": {...},          // 可选
      "metadata": {...},      // 可选
      "updated_at": "..."     // 自动添加
    }
  }
}
```

### 前端处理（超简单）

```javascript
// 监听 conversation_delta 事件
eventSource.addEventListener('conversation_delta', (e) => {
    const data = JSON.parse(e.data).data;
    const delta = data.delta;
    
    // 🎯 核心：直接合并 delta
    Object.assign(conversation, delta);
    
    // 触发 UI 更新
    updateUI(conversation);
});
```

---

## 📝 使用示例

### 1. 更新标题

```python
# 后端
await events.conversation.emit_conversation_delta(
    session_id=session_id,
    conversation_id=conversation_id,
    delta={"title": "分析数据报告"}
)
```

```javascript
// 前端收到
delta = {"title": "分析数据报告", "updated_at": "..."}
// Object.assign(conversation, delta)
// → conversation.title 更新
```

---

### 2. 创建 Plan

```python
# plan_todo_tool 执行 create_plan 后
await events.conversation.emit_conversation_plan_created(
    session_id=session_id,
    conversation_id=conversation_id,
    plan={
        "task_id": "task_123",
        "goal": "生成PPT",
        "steps": [
            {"action": "搜索资料", "status": "in_progress"},
            {"action": "生成大纲", "status": "pending"}
        ],
        "status": "executing",
        "current_step": 0,
        "total_steps": 2
    }
)
```

```javascript
// 前端收到（内部调用 conversation_delta）
delta = {
    "plan": {...},
    "updated_at": "..."
}
// Object.assign(conversation, delta)
// → conversation.plan 创建
```

---

### 3. 更新 Plan 步骤

```python
# plan_todo_tool 执行 update_step 后
await events.conversation.emit_conversation_plan_updated(
    session_id=session_id,
    conversation_id=conversation_id,
    plan={
        "task_id": "task_123",
        "goal": "生成PPT",
        "steps": [
            {"action": "搜索资料", "status": "completed", "result": "已完成"},
            {"action": "生成大纲", "status": "in_progress"}
        ],
        "status": "executing",
        "current_step": 1,
        "completed_steps": 1,
        "total_steps": 2
    }
)
```

```javascript
// 前端收到（完整替换 plan）
delta = {"plan": {...完整的新plan...}}
// Object.assign(conversation, delta)
// → conversation.plan 完整替换
```

---

### 4. 更新 Metadata

```python
# 只更新 tags，不影响 plan
await events.conversation.emit_conversation_metadata_update(
    session_id=session_id,
    conversation_id=conversation_id,
    metadata={"tags": ["数据分析", "报告"]}
)
```

```javascript
// 前端收到
delta = {
    "metadata": {"tags": ["数据分析", "报告"]},
    "updated_at": "..."
}
// Object.assign(conversation, delta)
// → conversation.metadata.tags 更新（plan 保留）
```

---

## 🔧 后端事件 API

### 通用事件（推荐）

```python
# 1. conversation_delta - 统一的增量更新
await events.conversation.emit_conversation_delta(
    session_id=session_id,
    conversation_id=conversation_id,
    delta={
        "title": "新标题",
        "plan": {...},
        "metadata": {...}
    }
)
```

### 语义化快捷方法

```python
# 2. 标题更新（内部调用 conversation_delta）
await events.conversation.emit_conversation_title_update(
    session_id=session_id,
    conversation_id=conversation_id,
    title="新标题"
)

# 3. Plan 创建（首次，内部调用 conversation_delta）
await events.conversation.emit_conversation_plan_created(
    session_id=session_id,
    conversation_id=conversation_id,
    plan={...}
)

# 4. Plan 更新（内部调用 conversation_delta）
await events.conversation.emit_conversation_plan_updated(
    session_id=session_id,
    conversation_id=conversation_id,
    plan={...}  # 完整的 plan 对象
)

# 5. Metadata 更新（内部调用 conversation_delta）
await events.conversation.emit_conversation_metadata_update(
    session_id=session_id,
    conversation_id=conversation_id,
    metadata={"tags": [...]}
)
```

---

## 🔄 完整流程示例

### Plan 创建流程

```
1. 用户：帮我生成一份数据分析报告

2. LLM：调用 plan_todo tool
   {"operation": "create_plan", "data": {"goal": "生成报告", "steps": [...]}}

3. Agent: 执行 plan_todo_tool
   → 返回 {"status": "success", "plan": {...}}

4. Agent: 发送事件
   await events.conversation.emit_conversation_plan_created(
       session_id=session_id,
       conversation_id=conversation_id,
       plan=new_plan
   )

5. ChatEventHandler: 监听 conversation_delta 事件
   → 更新数据库: conversation.metadata.plan = new_plan

6. 前端: 监听 SSE conversation_delta 事件
   → Object.assign(conversation, delta)
   → 渲染 Plan UI（进度条、步骤列表）
```

### Plan 更新流程

```
1. LLM：完成第一步，调用 plan_todo tool
   {"operation": "update_step", "data": {"step_index": 0, "status": "completed"}}

2. Agent: 执行 plan_todo_tool
   → 返回 {"status": "success", "plan": {...updated...}}

3. Agent: 发送事件
   await events.conversation.emit_conversation_plan_updated(
       session_id=session_id,
       conversation_id=conversation_id,
       plan=updated_plan
   )

4. ChatEventHandler: 监听 conversation_delta 事件
   → 更新数据库: conversation.metadata.plan = updated_plan

5. 前端: 监听 SSE conversation_delta 事件
   → Object.assign(conversation, delta)
   → 更新 Plan UI（进度条移动，步骤状态更新）
```

---

## 🎨 前端完整示例

```javascript
// 初始化
let conversation = null;

const eventSource = new EventSource('/api/v1/chat?stream=true');

// 1. 监听 conversation_start（初始化）
eventSource.addEventListener('conversation_start', (e) => {
    const data = JSON.parse(e.data).data;
    conversation = {
        id: data.conversation_id,
        title: data.title,
        created_at: data.created_at,
        updated_at: data.updated_at,
        metadata: data.metadata || {}
    };
    
    console.log('Conversation initialized:', conversation);
});

// 2. 监听 conversation_delta（统一更新）
eventSource.addEventListener('conversation_delta', (e) => {
    const data = JSON.parse(e.data).data;
    const delta = data.delta;
    
    console.log('Received delta:', delta);
    
    // 🎯 核心：直接合并
    Object.assign(conversation, delta);
    
    // 根据 delta 内容更新不同的 UI
    if (delta.title) {
        updateTitleUI(delta.title);
    }
    
    if (delta.plan) {
        updatePlanUI(delta.plan);
    }
    
    if (delta.metadata) {
        updateMetadataUI(delta.metadata);
    }
});

// 3. UI 更新函数
function updatePlanUI(plan) {
    if (!plan) return;
    
    // 更新进度条
    const progress = plan.completed_steps / plan.total_steps;
    document.querySelector('.progress-bar').style.width = `${progress * 100}%`;
    
    // 更新步骤列表
    const stepsContainer = document.querySelector('.steps');
    stepsContainer.innerHTML = plan.steps.map((step, index) => `
        <div class="step step-${step.status}">
            <span class="step-number">${index + 1}</span>
            <span class="step-action">${step.action}</span>
            <span class="step-status">${step.status}</span>
        </div>
    `).join('');
}

function updateTitleUI(title) {
    document.querySelector('.conversation-title').textContent = title;
}

function updateMetadataUI(metadata) {
    if (metadata.tags) {
        const tagsContainer = document.querySelector('.tags');
        tagsContainer.innerHTML = metadata.tags.map(tag => 
            `<span class="tag">${tag}</span>`
        ).join('');
    }
}
```

---

## ⚠️ 废弃的方法

### system_events.emit_plan_update()

```python
# ❌ 已废弃，不要使用
await events.system.emit_plan_update(session_id, plan)

# ✅ 使用新的方法
await events.conversation.emit_conversation_plan_updated(
    session_id=session_id,
    conversation_id=conversation_id,
    plan=plan
)
```

---

## 📊 数据流对比

### 旧的方式（已废弃）

```
plan_todo_tool → Agent → emit_plan_update (system)
                              ↓
                        ChatEventHandler 监听 plan_update
                              ↓
                        更新 Conversation.metadata.plan
                              ↓
                        前端需要单独处理 plan_update 事件
```

### 新的方式（统一）

```
plan_todo_tool → Agent → emit_conversation_delta (conversation)
                              ↓
                        ChatEventHandler 监听 conversation_delta
                              ↓
                        更新 Conversation 字段
                              ↓
                        前端统一处理 conversation_delta 事件
                              ↓
                        Object.assign(conversation, delta)
```

---

## 🎯 优势

1. **统一模式**：所有更新都通过 `conversation_delta`
2. **前端简单**：只需要 `Object.assign(conversation, delta)`
3. **可扩展**：新增字段无需修改前端逻辑
4. **语义清晰**：保留快捷方法（如 `emit_conversation_plan_created`）
5. **类型安全**：delta 结构明确，易于验证

---

## 📚 相关文件

- `core/events/conversation_events.py` - Conversation 事件管理器
- `services/chat_event_handler.py` - 事件处理器（更新数据库）
- `core/agent/simple/simple_agent.py` - Agent 发送事件
- `tools/plan_todo_tool.py` - Plan/Todo 工具

