# 复杂任务一轮退出问题调试

## 问题现象

```
用户输入: "帮我生成一个 PPT"
    ↓
Turn 1:
  LLM thinking: "这是一个复杂任务..."
  LLM response: "好的，我可以帮你生成 PPT。请告诉我主题..."
  stop_reason: "end_turn"  ❌
    ↓
循环退出，没有调用任何工具！
```

## 根本原因

### 原因 1：LLM 没有被告知要使用工具

**当前 System Prompt 可能的问题：**
```
❌ "你是一个 AI 助手，可以使用工具..."
   → LLM 理解为"可以用，也可以不用"

✅ "你必须使用工具来完成任务，不要直接回答..."
   → LLM 理解为"必须用工具"
```

### 原因 2：Task Type 判断错误

**Intent Recognition 可能返回：**
```json
{
  "task_type": "content_generation",
  "complexity": "simple",  // ❌ 应该是 complex
  "needs_plan": false      // ❌ 应该是 true
}
```

如果 complexity 被判断为 "simple"，Agent 会使用 simple_prompt，不包含工具使用指导。

### 原因 3：工具筛选过滤掉了关键工具

```python
# Capability Router 可能筛选结果：
required_capabilities = ["content_generation"]
selected_tools = ["ppt_generation"]  # ✅ 包含 ppt

但是：
- 没有包含 plan_todo
- 没有包含 file_operations
- LLM 不知道先调用什么
```

## 🔍 调试步骤

### 步骤 1：检查 Intent Recognition 结果

```bash
# 在日志中搜索：
grep "intent_analysis" logs/agent.log

# 期望看到：
{
  "task_type": "content_generation",
  "complexity": "complex",    # ✅ 应该是 complex
  "needs_plan": true,         # ✅ 应该需要 plan
  "prompt_level": "full"      # ✅ 应该使用 full prompt
}
```

### 步骤 2：检查工具筛选结果

```bash
# 在日志中搜索：
grep "tool_selection" logs/agent.log

# 期望看到：
{
  "required_capabilities": [
    "content_generation",
    "ppt_generation",
    "task_planning",      # ✅ 应该包含
    "file_operations"     # ✅ 应该包含
  ],
  "selected_tools": [
    "plan_todo",          # ✅ 必须有
    "ppt_generation",
    "file_operations",
    ...
  ]
}
```

### 步骤 3：检查 LLM 响应

```bash
# 在日志中搜索：
grep "stop_reason" logs/agent.log

# 第一轮应该是：
Turn 1: stop_reason = "tool_use"  # ✅ 调用工具

# 而不是：
Turn 1: stop_reason = "end_turn"  # ❌ 直接结束
```

## 🔧 修复方案

### 修复 1：改进 Intent Recognition Prompt

**文件：`prompts/intent_recognition_prompt.py`**

```python
def get_intent_recognition_prompt() -> str:
    return """你是一个任务意图分析专家。

判断标准：
- complexity = "complex" 如果：
  * 需要多步骤执行
  * 需要调用多个工具
  * 需要生成文件（PPT、文档等）
  * 用户明确要求"帮我做..."

示例：
- "帮我生成一个 PPT" → complex, needs_plan=true
- "帮我写一份报告" → complex, needs_plan=true
- "今天天气" → simple, needs_plan=false
"""
```

### 修复 2：改进 System Prompt（强制工具使用）

**文件：`prompts/universal_agent_prompt.py`**

```python
TOOL_USAGE_RULES = """
## 🔧 工具使用规则（重要！）

1. ✅ 复杂任务必须先创建 Plan：
   - 如果用户要求"帮我做..."、"生成..."、"创建..."
   - 第一步：调用 plan_todo(operation="create_plan") 创建计划
   - 第二步：逐步执行 Plan 中的每个步骤
   - 最后一步：告诉用户完成情况

2. ✅ 创建 Plan 后必须立即执行：
   ❌ 错误示例：
   Turn 1: plan_todo(create_plan)
   Turn 2: "好的，我已经创建了计划"  // ❌ 不要这样！
   
   ✅ 正确示例：
   Turn 1: plan_todo(create_plan)
   Turn 2: ppt_generation(...)  // ✅ 立即执行步骤 1
   Turn 3: file_operations(...)  // ✅ 执行步骤 2
   ...
   Turn N: "所有步骤已完成"

3. ✅ 不要直接回答，要使用工具：
   ❌ 用户："帮我生成 PPT"
       你："好的，我可以帮你生成..."  // ❌ 不要直接回答！
   
   ✅ 用户："帮我生成 PPT"
       你：调用 plan_todo 工具  // ✅ 直接行动！
"""
```

### 修复 3：添加循环检查（防御性编程）

**文件：`core/agent.py`**

```python
# 在 agent.py 的循环中添加：
if stop_reason == "end_turn":
    # 🆕 检查是否过早退出
    plan = self.plan_state.get("plan")
    if plan and not self._is_plan_completed(plan):
        logger.warning(f"⚠️ Plan 未完成就退出了！")
        logger.warning(f"   Plan: {plan.get('goal')}")
        logger.warning(f"   进度: {self._get_plan_progress(plan)}")
        
        # 🆕 添加一个"继续执行"的提示到 messages
        messages.append(Message(
            role="user",
            content="请继续执行 Plan 中的下一个步骤，不要停下来。"
        ))
        continue  # 🔥 强制继续循环，不要退出！
    
    # Plan 已完成，正常退出
    final_result = response.content
    break

def _is_plan_completed(self, plan: Dict) -> bool:
    """检查 Plan 是否完成"""
    steps = plan.get("steps", [])
    if not steps:
        return True
    
    completed = sum(1 for s in steps if s.get("status") == "completed")
    return completed == len(steps)

def _get_plan_progress(self, plan: Dict) -> str:
    """获取 Plan 进度"""
    steps = plan.get("steps", [])
    total = len(steps)
    completed = sum(1 for s in steps if s.get("status") == "completed")
    return f"{completed}/{total}"
```

### 修复 4：添加详细日志

**文件：`core/agent.py`**

```python
for turn in range(self.max_turns):
    logger.info(f"{'='*60}")
    logger.info(f"🔄 Turn {turn + 1}/{self.max_turns}")
    logger.info(f"{'='*60}")
    
    # LLM 调用前
    logger.debug(f"📨 发送消息数量: {len(messages)}")
    logger.debug(f"🔧 可用工具: {[t if isinstance(t, str) else t.get('name') for t in tools_for_llm]}")
    
    # LLM 调用
    response = await self.llm.create_message_async(...)
    
    # LLM 响应后
    logger.info(f"📥 LLM 响应:")
    logger.info(f"   stop_reason: {response.stop_reason}")
    logger.info(f"   thinking: {len(response.thinking) if response.thinking else 0} 字符")
    logger.info(f"   content: {len(response.content) if response.content else 0} 字符")
    logger.info(f"   tool_calls: {len(response.tool_calls) if response.tool_calls else 0} 个")
    
    if response.tool_calls:
        for tc in response.tool_calls:
            logger.info(f"      🔧 {tc['name']}({list(tc['input'].keys())})")
```

## 🧪 测试用例

```python
# test_complex_task.py
import asyncio
from core.agent import create_simple_agent

async def test_ppt_generation():
    agent = create_simple_agent(event_manager=...)
    
    user_input = [{"type": "text", "text": "帮我生成一个关于 AI 的 PPT，包含 5 页内容"}]
    
    turn_count = 0
    async for event in agent.chat(user_input, session_id="test-123"):
        if event["type"] == "turn_progress":
            turn_count = event["data"]["turn"]
            print(f"Turn {turn_count}")
        
        if event["type"] == "tool_call_start":
            print(f"  🔧 调用工具: {event['data']['tool_name']}")
        
        if event["type"] == "complete":
            print(f"✅ 完成，总共 {turn_count} 轮")
            assert turn_count > 1, f"复杂任务只执行了 {turn_count} 轮！"

asyncio.run(test_ppt_generation())
```

## 📊 期望的执行流程

```
用户: "帮我生成一个 PPT"
    ↓
Turn 1:
  LLM thinking: "这需要多步骤，先创建 Plan"
  LLM action: plan_todo(operation="create_plan", ...)
  stop_reason: "tool_use"  ✅
    ↓
Turn 2:
  LLM thinking: "Plan 已创建，开始执行步骤 1"
  LLM action: ppt_generation(...)
  stop_reason: "tool_use"  ✅
    ↓
Turn 3:
  LLM thinking: "步骤 1 完成，执行步骤 2"
  LLM action: file_operations(...)
  stop_reason: "tool_use"  ✅
    ↓
...
    ↓
Turn N:
  LLM thinking: "所有步骤已完成"
  LLM response: "PPT 已生成，包含 5 页内容..."
  stop_reason: "end_turn"  ✅
```

