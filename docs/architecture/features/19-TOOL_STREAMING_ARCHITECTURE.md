# 工具流式调用架构

## 📋 目录

1. [概述](#概述)
2. [核心原理](#核心原理)
3. [流式调用流程](#流式调用流程)
4. [核心组件](#核心组件)
5. [事件流转](#事件流转)
6. [代码示例](#代码示例)
7. [特殊场景](#特殊场景)

---

## 概述

工具的流式调用是指在 Agent 执行工具时，将工具的调用过程和结果**实时**地流式推送给前端，提供更好的用户体验。

### 核心特性

- ✅ **实时反馈**：工具调用立即显示给用户
- ✅ **进度可见**：用户可以看到工具执行过程（如代码输出）
- ✅ **统一事件格式**：所有工具使用相同的事件协议（Claude 标准）
- ✅ **可中断**：用户可以随时停止工具执行

---

## 核心原理

### 一句话总结

> **Claude 返回流式，我们就流式处理。收集 `tool_result` 是为了下一次 LLM 请求时带入。**

### 为什么需要收集 tool_result？

Claude API 的多轮对话需要遵循特定的消息格式：

```
[user]      用户问题
[assistant] 我来调用工具... → tool_use blocks
[user]      工具执行结果    → tool_result blocks  ← 这就是我们收集的
[assistant] 根据结果回答...
```

当 Claude 返回 `stop_reason: tool_use` 时，我们需要：
1. **执行工具**：调用对应的工具
2. **收集结果**：把 `tool_result` 收集起来
3. **下一轮请求**：把结果作为 `[user]` 消息发给 Claude

### 如何收集？直接从 content_start 事件

我们不需要额外的内部事件。所有 `tool_result` 已经通过标准的 `content_start` 事件发出：

```python
# 在 _run_loop 中遍历工具执行事件
tool_results = []
async for tool_event in self._execute_tools_stream(tool_calls, session_id, ctx):
    # 1. yield 给前端（实时显示）
    yield tool_event
    
    # 2. 同时收集 tool_result（为下一轮 LLM 调用准备）
    if tool_event.get("type") == "content_start":
        content_block = tool_event.get("data", {}).get("content_block", {})
        if content_block.get("type") == "tool_result":
            tool_results.append(content_block)

# 3. 构建下一轮消息
messages.append(Message(role="assistant", content=response.raw_content))
messages.append(Message(role="user", content=tool_results))
```

### 事件协议

我们使用 Claude 标准的事件类型（简化命名）：

| Claude 官方 | 项目命名 | 作用 |
|-------------|----------|------|
| `content_block_start` | `content_start` | 内容块开始 |
| `content_block_delta` | `content_delta` | 内容块增量 |
| `content_block_stop` | `content_stop` | 内容块结束 |
| `message_start` | `message_start` | 消息开始 |
| `message_delta` | `message_delta` | 消息增量 |
| `message_stop` | `message_stop` | 消息结束 |

**没有自定义的内部事件**——所有事件都是标准事件，都会广播到前端

---

## 流式调用流程

### 整体流程图

```
用户发送消息
    ↓
┌─────────────────────────────────────────────────────────────┐
│ Turn 1: LLM 返回 tool_use                                   │
│                                                             │
│ Claude API (流式) → content_start (tool_use)                │
│                  → content_stop (tool_use)                  │
│                  → stop_reason: tool_use                    │
└─────────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────────┐
│ Agent 执行工具 + 广播事件                                    │
│                                                             │
│ _execute_tools_stream():                                    │
│   → content_start (tool_use)    ──→ 广播到前端 ✓            │
│   → content_stop                                            │
│   → [执行工具]                                              │
│   → content_start (tool_result) ──→ 广播到前端 ✓            │
│   → content_stop                     ↓                      │
│                                  同时收集到 tool_results     │
└─────────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────────┐
│ Turn 2: 带着 tool_result 继续请求                            │
│                                                             │
│ messages = [                                                │
│   {role: "user", content: "用户问题"},                       │
│   {role: "assistant", content: [tool_use blocks]},          │
│   {role: "user", content: [tool_result blocks]}  ← 收集的   │
│ ]                                                           │
│                                                             │
│ Claude API → 根据工具结果生成回复                            │
└─────────────────────────────────────────────────────────────┘
    ↓
前端实时显示完整对话过程
```

### 数据流向

```
_execute_tools_stream()
    │
    ├── yield content_start (tool_use)     ──┬──→ 广播到前端
    ├── yield content_stop                   │
    │                                        │
    ├── [执行工具]                           │
    │                                        │
    ├── yield content_start (tool_result)  ──┼──→ 广播到前端
    │                                        │
    └── yield content_stop                   │
                                             │
_run_loop() 调用方 ←─────────────────────────┘
    │
    └── 从 content_start 事件收集 tool_result
        构建下一轮 LLM 消息
```

---

## 核心组件

### 1. ClaudeLLMService - LLM 流式响应

负责处理 Claude API 的流式响应，识别工具调用。

```python
# core/llm/claude.py

async def create_message_stream(
    self,
    messages: List[Message],
    system: Optional[str] = None,
    tools: Optional[List[Union[ToolType, str, Dict]]] = None,
    on_thinking: Optional[Callable[[str], None]] = None,
    on_content: Optional[Callable[[str], None]] = None,
    on_tool_call: Optional[Callable[[Dict], None]] = None,
    **kwargs
) -> AsyncIterator[LLMResponse]:
    """
    流式调用 Claude API
    
    事件类型：
    - content_block_start: 开始新的内容块（thinking/text/tool_use）
    - content_block_delta: 内容增量（thinking_delta/text_delta/input_json_delta）
    - content_block_stop: 内容块结束
    - message_stop: 消息结束
    """
    
    async with self.async_client.messages.stream(**request_params) as stream:
        async for event in stream:
            if event.type == "content_block_start":
                block = event.content_block
                
                # 🎯 识别工具调用
                if block.type == "tool_use" and on_tool_call:
                    on_tool_call({
                        "id": block.id,
                        "name": block.name,
                        "input": block.input,
                        "type": "tool_use"
                    })
            
            elif event.type == "content_block_delta":
                delta = event.delta
                
                # 🎯 工具输入的增量更新（JSON 流式）
                if delta.type == "input_json_delta":
                    partial_json = delta.partial_json
                    if on_tool_call:
                        on_tool_call({
                            "partial_input": partial_json,
                            "type": "input_delta"
                        })
```

**关键点：**
- Claude API 支持工具输入的流式返回（`input_json_delta`）
- `on_tool_call` 回调用于通知上层有工具调用

---

### 2. SimpleAgent - 工具流式执行

负责执行工具并发送流式事件。

```python
# core/agent/simple/simple_agent.py

# ===== 调用方：_run_loop =====
# 执行工具并收集结果
tool_results = []
async for tool_event in self._execute_tools_stream(tool_calls, session_id, ctx):
    # 1. yield 给前端（实时显示）
    yield tool_event
    
    # 2. 从 content_start 事件收集 tool_result
    if tool_event.get("type") == "content_start":
        content_block = tool_event.get("data", {}).get("content_block", {})
        if content_block.get("type") == "tool_result":
            tool_results.append(content_block)

# 3. 构建下一轮消息（带上工具结果）
messages.append(Message(role="assistant", content=response.raw_content))
messages.append(Message(role="user", content=tool_results))


# ===== _execute_tools_stream =====
async def _execute_tools_stream(
    self,
    tool_calls: List[Dict],
    session_id: str,
    ctx: RuntimeContext
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    执行工具调用（流式版本）
    
    为每个工具生成事件序列：
    1. tool_use block (content_start → content_stop)
    2. tool_result block (content_start → content_stop)
    
    注意：调用方通过遍历事件来收集 tool_result，不需要特殊的完成事件
    """
    
    for tool_call in tool_calls:
        tool_name = tool_call['name']
        tool_input = tool_call['input'] or {}
        tool_id = tool_call['id']
        
        # ===== 1. 发送 tool_use 事件 =====
        tool_use_block = {
            "type": "tool_use",
            "id": tool_id,
            "name": tool_name,
            "input": tool_input
        }
        yield await self.broadcaster.emit_content_start(...)
        yield await self.broadcaster.emit_content_stop(...)
        
        # ===== 2. 执行工具 =====
        result = await self.tool_executor.execute(tool_name, tool_input)
        
        # ===== 3. 发送 tool_result 事件 =====
        tool_result_block = {
            "type": "tool_result",
            "tool_use_id": tool_id,
            "content": json.dumps(result, ensure_ascii=False),
            "is_error": False
        }
        
        # 这个事件会被：
        # - 广播到前端（实时显示）
        # - 被调用方收集（用于下一轮 LLM 调用）
        yield await self.broadcaster.emit_content_start(
            session_id=session_id,
            index=tool_result_index,
            content_block=tool_result_block
            )
        yield await self.broadcaster.emit_content_stop(...)
```

**关键点：**
- 每个工具调用生成 2 个 content block：`tool_use` 和 `tool_result`
- **不需要特殊的完成事件**：调用方直接从 `content_start` 事件收集 `tool_result`
- 所有事件都是标准事件，都会广播到前端

---

### 3. SSEBroadcaster - 事件广播

负责将事件广播到前端。

```python
# core/events/sse_broadcaster.py

async def emit_content_start(
    self,
    session_id: str,
    index: int,
    content_block: Dict[str, Any]
) -> Dict[str, Any]:
    """
    发送 content_start 事件
    
    Args:
        session_id: 会话ID
        index: 内容块索引
        content_block: 内容块数据（包含 type, id, name, input 等）
    """
    event = {
        "type": "content_start",
        "data": {
            "index": index,
            "content_block": content_block
        }
    }
    
    await self._broadcast(session_id, event)
    return event

async def emit_content_delta(
    self,
    session_id: str,
    index: int,
    delta: Dict[str, Any]
) -> Dict[str, Any]:
    """
    发送 content_delta 事件
    
    Args:
        delta: {"type": "text_delta", "text": "..."}
    """
    event = {
        "type": "content_delta",
        "data": {
            "index": index,
            "delta": delta
        }
    }
    
    await self._broadcast(session_id, event)
    return event
```

---

### 4. 特殊工具：E2B 沙箱流式输出

E2B 沙箱支持实时输出代码执行结果。

```python
# tools/e2b_sandbox.py

async def _execute_code_stream(
    self,
    sandbox,
    code: str,
    session_id: str,
    timeout: int = 300
) -> Dict[str, Any]:
    """
    流式执行代码
    
    工作原理：
    1. E2B SDK 通过 on_stdout/on_stderr 回调实时返回输出
    2. 回调函数通过 EventManager 发送自定义事件
    3. 前端实时显示代码输出
    """
    stdout_lines = []
    stderr_lines = []
    
    # 定义回调函数
    def on_stdout(data):
        """stdout 回调 - 发送到前端"""
        line = data.line
        stdout_lines.append(line)
        
        # 🎯 发送自定义 SSE 事件
        if self.event_manager:
            asyncio.create_task(
                self.event_manager.system.emit_custom(
                    session_id=session_id,
                    event_type="code_output",
                    event_data={
                        "stream": "stdout",
                        "text": line,
                        "timestamp": data.timestamp
                    }
                )
            )
    
    def on_stderr(data):
        """stderr 回调 - 发送到前端"""
        line = data.line
        stderr_lines.append(line)
        
        if self.event_manager:
            asyncio.create_task(
                self.event_manager.system.emit_custom(
                    session_id=session_id,
                    event_type="code_output",
                    event_data={
                        "stream": "stderr",
                        "text": line,
                        "error": True,
                        "timestamp": data.timestamp
                    }
                )
            )
    
    # 使用 E2B 的流式 API
    execution = await asyncio.to_thread(
        sandbox.run_code,
        code,
        on_stdout=on_stdout,  # 注册回调
        on_stderr=on_stderr,
        timeout=timeout
    )
    
    return {
        "success": execution.error is None,
        "stdout": "".join(stdout_lines),
        "stderr": "".join(stderr_lines),
        "error": execution.error.value if execution.error else None
    }
```

**关键点：**
- E2B 的 `on_stdout`/`on_stderr` 是**同步回调**
- 使用 `asyncio.create_task()` 在回调中发送异步事件
- 使用自定义事件类型 `code_output`

---

## 事件流转

### 完整事件序列（示例）

假设用户请求："帮我计算 1+1"，Agent 调用 `execute_code` 工具。

```
时间线                事件类型                  事件数据
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
T0    →  content_start (text)      {"type": "text"}
T1    →  content_delta (text)      {"text": "我来帮你计算"}
T2    →  content_stop (text)       {}

T3    →  content_start (tool_use)  {
                                      "type": "tool_use",
                                      "id": "toolu_xxx",
                                      "name": "execute_code",
                                      "input": {"code": "print(1+1)"}
                                    }
T4    →  content_stop (tool_use)   {}

      ┌─ 工具开始执行 ─┐
      
T5    →  code_output (自定义)      {"stream": "stdout", "text": "2\n"}

      └─ 工具执行完成 ─┘

T6    →  content_start (tool_result) {
                                         "type": "tool_result",
                                         "tool_use_id": "toolu_xxx",
                                         "content": "{\"success\": true, ...}"
                                      }
T7    →  content_delta (tool_result)  {"text": "{\"success\": true"}
T8    →  content_delta (tool_result)  {"text": ", \"output\": \"2\"}"}
T9    →  content_stop (tool_result)   {}

T10   →  content_start (text)      {"type": "text"}
T11   →  content_delta (text)      {"text": "计算结果是 2"}
T12   →  content_stop (text)       {}

T13   →  message_stop              {"stop_reason": "end_turn"}
```

### 事件处理流程

```
SSEBroadcaster.emit_xxx()
    ↓
Redis PUBLISH (channel: session:{session_id})
    ↓
SSE 监听器接收
    ↓
格式化为 SSE 格式：
    data: {"type": "xxx", "data": {...}}
    ↓
发送到前端 HTTP 连接
    ↓
前端 EventSource.onmessage()
    ↓
Vue 组件更新 UI
```

---

## 代码示例

### 示例 1：创建支持流式的自定义工具

```python
from tools.base import BaseTool
import asyncio

class MyStreamingTool(BaseTool):
    """支持流式输出的自定义工具"""
    
    async def execute(
        self,
        task: str,
        session_id: str = None,
        **kwargs
    ) -> dict:
        """
        执行任务并流式输出进度
        
        Args:
            task: 任务描述
            session_id: 会话ID（自动注入）
        """
        
        # 1. 发送开始通知
        if self.event_manager and session_id:
            await self.event_manager.system.emit_custom(
                session_id=session_id,
                event_type="task_start",
                event_data={"task": task}
            )
        
        # 2. 执行任务（模拟耗时操作）
        results = []
        for i in range(5):
            await asyncio.sleep(1)
            
            # 发送进度事件
            if self.event_manager and session_id:
                await self.event_manager.system.emit_custom(
                    session_id=session_id,
                    event_type="task_progress",
                    event_data={
                        "progress": (i + 1) * 20,
                        "message": f"步骤 {i+1}/5 完成"
                    }
                )
            
            results.append(f"结果 {i+1}")
        
        # 3. 发送完成通知
        if self.event_manager and session_id:
            await self.event_manager.system.emit_custom(
                session_id=session_id,
                event_type="task_complete",
                event_data={"results": results}
            )
        
        return {
            "status": "success",
            "results": results
        }
```

### 示例 2：前端接收流式事件

```javascript
// Vue 组件
export default {
  data() {
    return {
      toolProgress: {},
      codeOutput: []
    }
  },
  
  methods: {
    handleSSEEvent(event) {
      const data = JSON.parse(event.data)
      
      switch (data.type) {
        // 工具调用开始
        case 'content_start':
          if (data.data.content_block.type === 'tool_use') {
            const toolName = data.data.content_block.name
            this.toolProgress[toolName] = {
              status: 'running',
              input: data.data.content_block.input
            }
          }
          break
        
        // 代码输出（自定义事件）
        case 'code_output':
          this.codeOutput.push({
            stream: data.data.stream,
            text: data.data.text,
            error: data.data.error || false
          })
          break
        
        // 任务进度（自定义事件）
        case 'task_progress':
          console.log(`进度: ${data.data.progress}%`)
          console.log(`消息: ${data.data.message}`)
          break
        
        // 工具结果
        case 'content_start':
          if (data.data.content_block.type === 'tool_result') {
            const result = JSON.parse(data.data.content_block.content)
            console.log('工具执行完成:', result)
          }
          break
      }
    }
  }
}
```

---

## 特殊场景

### 1. 人工确认流程

对于需要人工确认的工具（如文件操作），流程如下：

```
Agent 调用工具
    ↓
工具检测到需要确认
    ↓
发送 human_confirmation_required 事件
    ↓
前端弹出确认对话框
    ↓
用户确认/拒绝
    ↓
发送确认结果到后端
    ↓
工具继续执行或取消
    ↓
发送 tool_result 事件
```

参考：`core/confirmation_manager.py`

### 2. 长时间运行的工具

对于需要长时间运行的工具（如训练模型），建议：

1. **后台任务**：使用 BackgroundTask 在后台执行
2. **定期发送进度**：每隔 5-10 秒发送一次进度事件
3. **可取消**：监听 Redis 停止标志

```python
async def execute(self, session_id: str = None, **kwargs):
    """长时间运行的任务"""
    
    for i in range(100):
        # 检查是否被取消
        if await redis.is_stopped(session_id):
            return {"status": "cancelled"}
        
        # 执行工作
        await asyncio.sleep(1)
        
        # 定期发送进度
        if i % 10 == 0:
            await self.event_manager.system.emit_custom(
                session_id=session_id,
                event_type="long_task_progress",
                event_data={"progress": i}
            )
    
    return {"status": "success"}
```

### 3. 工具链（多工具串行调用）

当 Agent 需要串行调用多个工具时：

```
工具1 调用
    ↓
发送 tool_use + tool_result
    ↓
LLM 分析结果，决定调用工具2
    ↓
发送 tool_use + tool_result
    ↓
...
    ↓
最终文本回复
```

每个工具都会生成独立的事件序列，前端可以清晰看到整个推理链。

---

## 最佳实践

### ✅ 应该做的

1. **使用自定义事件**：对于特殊进度（如代码输出、文件上传进度），使用自定义事件类型
2. **分块发送**：大量数据分块发送，避免单个事件过大
3. **错误处理**：工具执行失败时，设置 `is_error=True`
4. **上下文注入**：所有工具都应接收 `session_id` 参数

### ❌ 不应该做的

1. **阻塞事件循环**：不要在回调中执行耗时同步操作
2. **过度发送事件**：避免每毫秒发送一次事件（建议间隔 100ms）
3. **忘记错误处理**：工具异常必须捕获并返回错误结果
4. **硬编码 session_id**：始终通过参数传递

---

## 总结

### 核心思想

> **Claude 返回流式，我们就流式。收集 tool_result 只是为了下一轮请求带入。**

### 架构组件

1. **ClaudeLLMService**：处理 Claude API 的流式响应
2. **SimpleAgent**：执行工具并生成标准事件序列
3. **Broadcaster**：广播事件到前端（所有事件都广播，没有内部事件）

### 设计原则

- ✅ **使用标准事件**：`content_start`、`content_delta`、`content_stop`（Claude 命名简化版）
- ✅ **不造内部事件**：所有事件都是标准事件，都会广播到前端
- ✅ **数据收集方式**：调用方直接从标准事件中提取需要的数据

### 为什么这样设计？

| 问题 | 解决方案 |
|------|----------|
| 前端需要实时显示工具调用 | `content_start (tool_use)` 事件广播 |
| 前端需要实时显示工具结果 | `content_start (tool_result)` 事件广播 |
| 下一轮 LLM 需要工具结果 | 从同一个 `content_start` 事件中收集 |

**一个事件，两个用途**——既广播给前端，又被调用方收集。

相关文档：
- [事件协议](03-EVENT-PROTOCOL.md)
- [SSE 连接管理](04-SSE-CONNECTION-MANAGEMENT.md)
- [工具开发规范](.cursor/rules/04-tools-development/RULE.mdc)

