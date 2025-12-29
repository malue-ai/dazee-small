# RVR 循环退出逻辑分析

## 当前的循环判断标准

```python
for turn in range(max_turns):  # 最多 20 轮
    
    # LLM 调用
    response = await llm.create_message_async(...)
    stop_reason = response.stop_reason
    
    # 🔑 退出判断
    if stop_reason == "end_turn":
        ✅ LLM 认为任务完成
        break  # 退出循环
    
    elif stop_reason == "tool_use":
        ✅ LLM 需要调用工具
        # 执行工具
        # 更新 messages
        # 继续下一轮 (continue)
    
    else:
        ❌ 未知的 stop_reason
        break  # 退出循环
```

## 问题：为什么只执行一次就退出？

### 场景 1：简单问答（正常行为）
```
用户: "你好"
    ↓
Turn 1:
  LLM: "你好！有什么可以帮你的吗？"
  stop_reason: "end_turn"  ✅ 
    ↓
  break  # 第一轮就退出 ✅ 这是正常的！
```

### 场景 2：需要工具的任务（应该多轮）
```
用户: "深圳今天天气怎么样"
    ↓
Turn 1:
  LLM thinking: "需要搜索天气信息"
  LLM action: 调用 web_search 工具
  stop_reason: "tool_use"  ✅
    ↓
  执行工具 → 获取结果 → 更新 messages
  继续循环 ✅
    ↓
Turn 2:
  LLM: "根据搜索结果，深圳今天..."
  stop_reason: "end_turn"  ✅
    ↓
  break  # 第二轮退出 ✅ 正常！
```

### 场景 3：复杂任务（应该多轮，但可能有问题）
```
用户: "帮我生成一个关于 AI 的 PPT，包含 5 页内容"
    ↓
Turn 1:
  LLM thinking: "这是一个复杂任务，需要规划"
  LLM action: 调用 plan_todo 工具创建计划
  stop_reason: "tool_use"  ✅
    ↓
  执行工具 → 创建 Plan → 更新 messages
  继续循环 ✅
    ↓
Turn 2:
  LLM: "好的，我已经创建了计划。现在开始执行..."
  stop_reason: "end_turn"  ❌❌❌ 问题在这里！
    ↓
  break  # 第二轮就退出了，但 Plan 还没执行完！
```

## 🚨 核心问题

### 问题 1：LLM 过早返回 `end_turn`

**当前情况：**
```python
# Turn 1: LLM 创建了 Plan
LLM: "我创建了一个 5 步计划，接下来会逐步执行"
stop_reason: "end_turn"  # ❌ 错误！应该继续调用工具
```

**期望情况：**
```python
# Turn 1: LLM 创建了 Plan
LLM: 调用 plan_todo(create_plan)
stop_reason: "tool_use"  # ✅

# Turn 2: LLM 执行步骤 1
LLM: 调用 web_search(...)
stop_reason: "tool_use"  # ✅

# Turn 3: LLM 执行步骤 2
LLM: 调用 file_operations(...)
stop_reason: "tool_use"  # ✅

# ...

# Turn N: LLM 完成所有步骤
LLM: "任务已完成，共执行了 5 个步骤"
stop_reason: "end_turn"  # ✅ 现在退出才对！
```

### 问题 2：缺少"继续执行"的引导

**原因：**
LLM 不知道自己应该继续执行 Plan 中的下一步。

**System Prompt 可能缺少的内容：**
```
❌ 当前 Prompt（可能）:
"你是一个 AI 助手，可以使用工具来帮助用户完成任务。"

✅ 应该增加的内容:
"当你创建了 Plan 后，必须逐步执行 Plan 中的每个步骤，
直到所有步骤都完成。不要在创建 Plan 后就停止，
而是应该立即开始执行第一步。"
```

## 🔧 解决方案

### 方案 1：改进 System Prompt（推荐）

**在 `prompts/universal_agent_prompt.py` 中添加：**
```python
MEMORY_PROTOCOL = """
## 📋 Memory Protocol (Plan/Todo 工具使用规范)

重要规则：
1. ✅ 创建 Plan 后，必须立即开始执行第一步
2. ✅ 每完成一个步骤，立即执行下一步
3. ✅ 不要在创建 Plan 后就回复用户"我已经创建了计划"
4. ✅ 只有当所有步骤都完成后，才能回复最终结果

错误示例：
Turn 1: plan_todo(create_plan) → 创建 5 步计划
Turn 2: "好的，我已经创建了计划，准备执行" ❌ 错误！应该直接执行步骤 1

正确示例：
Turn 1: plan_todo(create_plan) → 创建 5 步计划
Turn 2: web_search(...) → 执行步骤 1
Turn 3: file_operations(...) → 执行步骤 2
...
Turn 6: "所有步骤已完成，结果是..." ✅ 正确！
"""
```

### 方案 2：在工具结果中添加"继续执行"提示

**在 `tools/plan_todo_tool.py` 中：**
```python
async def execute(self, operation: str, data: Dict[str, Any]) -> Dict[str, Any]:
    if operation == "create_plan":
        # ... 创建 Plan ...
        
        return {
            "success": True,
            "plan": plan,
            "display": self._format_plan_display(plan),
            # 🆕 添加提示
            "next_action": "请立即开始执行步骤 1，不要等待",
            "current_step": 1,
            "total_steps": len(steps)
        }
```

### 方案 3：添加循环检查（防御性编程）

**在 `core/agent.py` 中：**
```python
# 在循环结束时检查
if stop_reason == "end_turn":
    # 🆕 检查是否有未完成的 Plan
    plan = self.plan_state.get("plan")
    if plan and not self._is_plan_completed(plan):
        logger.warning("⚠️ Plan 未完成就退出了！")
        yield await self._emit_agent_event(session_id, "warning", {
            "message": "任务可能未完全完成，建议继续执行"
        })
    
    final_result = response.content
    break
```

### 方案 4：使用 `max_completion_tokens` 限制（强制多轮）

**在 LLM 调用时：**
```python
response = await self.llm.create_message_async(
    messages=messages,
    system=self.system_prompt,
    tools=tools_for_llm,
    max_tokens=4096,  # ✅ 当前
    # 🆕 添加 tool choice 强制调用工具（对于复杂任务）
    tool_choice={"type": "any"} if needs_plan else {"type": "auto"}
)
```

## 📊 循环退出的正确标准

```
✅ 应该继续循环:
  - stop_reason == "tool_use"  (需要调用工具)
  - 有未完成的 Plan 步骤

✅ 应该退出循环:
  - stop_reason == "end_turn" AND Plan 已完成 (或无 Plan)
  - 达到 max_turns (20 轮)
  - 发生严重错误

❌ 当前的问题:
  - 只检查 stop_reason，不检查 Plan 状态
  - LLM 可能在 Plan 未完成时就返回 end_turn
```

## 🎯 建议的修复优先级

1. **高优先级**：改进 System Prompt，明确告诉 LLM 要执行完整个 Plan
2. **中优先级**：在工具结果中添加"继续执行"提示
3. **低优先级**：添加循环检查（防御性）

