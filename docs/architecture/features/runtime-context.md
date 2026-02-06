# RuntimeContext - Agent 运行时上下文

## 概述

`RuntimeContext` 是 Agent 执行 `chat()` 方法期间的**唯一状态容器**。它将所有运行时状态集中管理，使 Agent 代码更加简洁、可测试、可追踪。

## 核心理念

```
┌─────────────────────────────────────────────────────────────┐
│                      RuntimeContext                         │
│  ┌─────────────┐  ┌─────────────┐  ┌──────────────────────┐│
│  │  messages   │  │ BlockState  │  │  ContentAccumulator  ││
│  │  (对话历史) │  │ (SSE 状态机)│  │  (内容累积器)        ││
│  └─────────────┘  └─────────────┘  └──────────────────────┘│
│  ┌─────────────┐  ┌─────────────┐  ┌──────────────────────┐│
│  │ current_turn│  │ step_index  │  │  last_llm_response   ││
│  │  (当前轮次) │  │ (步骤索引)  │  │  (LLM 响应缓存)      ││
│  └─────────────┘  └─────────────┘  └──────────────────────┘│
└─────────────────────────────────────────────────────────────┘
```

## 组件说明

### 1. BlockState - SSE 事件状态机

管理流式 SSE 事件的 `content_start` → `content_delta` → `content_stop` 生命周期。

```python
# 开始一个 thinking block
index = ctx.block.start_new_block("thinking")  # 返回 0

# 检查是否需要切换类型
if ctx.block.needs_transition("text"):
    ctx.block.close_current_block()
    ctx.block.start_new_block("text")  # 返回 1

# 检查状态
ctx.block.is_block_open()  # True/False
ctx.block.current_type     # "thinking" | "text" | "tool_use" | None
```

**设计好处**：
- 自动管理 block 索引（全局递增，保证唯一）
- 防止忘记关闭 block 导致的事件错乱
- 支持类型切换检测（避免重复发送 content_start）

### 2. ContentAccumulator - 内容累积器

将流式事件累积成 Claude API 标准的 `content_blocks` 数组。

```python
# 事件驱动累积（由 EventBroadcaster 自动调用）
ctx.accumulator.on_content_start({"type": "thinking"}, index=0)
ctx.accumulator.on_content_delta("这是思考过程...", index=0)
ctx.accumulator.on_content_stop(index=0)

# 获取累积内容
ctx.accumulator.get_text_content()      # 获取所有 text 内容
ctx.accumulator.get_thinking_content()  # 获取所有 thinking 内容
ctx.accumulator.all_blocks              # 完整的 content_blocks 数组
```

**输出格式**（Claude API 标准）：
```json
[
    {"type": "thinking", "thinking": "分析用户需求..."},
    {"type": "text", "text": "这是我的回答"},
    {"type": "tool_use", "id": "t1", "name": "bash", "input": {"command": "ls"}},
    {"type": "tool_result", "tool_use_id": "t1", "content": "file1.txt\nfile2.txt"}
]
```

**设计好处**：
- 支持并行累积（多个工具同时执行时，按 index 独立累积）
- 自动解析流式 JSON（工具参数增量累积）
- 一份数据，多处使用（SSE 推送、数据库存储、下轮上下文）

### 3. 消息管理

统一管理 LLM 对话的 messages 数组。

```python
# 添加历史消息
ctx.add_history_messages([
    {"role": "user", "content": "你好"},
    {"role": "assistant", "content": "你好！有什么可以帮你的？"}
])

# 添加当前用户消息
ctx.add_user_message("帮我写一个 Python 脚本")

# 添加 assistant 响应（RVR 循环后）
ctx.add_assistant_message(ctx.accumulator.all_blocks)

# 添加工具执行结果
ctx.add_tool_result([{"type": "tool_result", "tool_use_id": "t1", ...}])
```

## 生命周期

```
用户发送消息
      │
      ▼
┌─────────────────┐
│ 创建 ctx        │  ctx = RuntimeContext(session_id="...")
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 加载历史消息    │  ctx.add_history_messages(history)
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────────────────────┐
│                  RVR 循环                       │
│  ┌───────────────────────────────────────────┐ │
│  │ 1. LLM 流式响应                           │ │
│  │    - BlockState 管理 SSE 事件             │ │
│  │    - ContentAccumulator 累积内容          │ │
│  ├───────────────────────────────────────────┤ │
│  │ 2. 执行工具                               │ │
│  │    - ContentAccumulator 累积 tool_result  │ │
│  ├───────────────────────────────────────────┤ │
│  │ 3. 添加 assistant 消息                    │ │
│  │    ctx.add_assistant_message(all_blocks)  │ │
│  ├───────────────────────────────────────────┤ │
│  │ 4. 添加工具结果                           │ │
│  │    ctx.add_tool_result(tool_results)      │ │
│  └───────────────────────────────────────────┘ │
│                     │                          │
│                     ▼                          │
│              检查 stop_reason                  │
│              =="end_turn" ?                    │
│                 │     │                        │
│               是│     │否                      │
│                 │     └──── 继续循环           │
└─────────────────┼──────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────┐
│ 保存到数据库                                   │
│   content = ctx.accumulator.build_for_db_json()│
└─────────────────────────────────────────────────┘
```

## 设计好处

### 1. 单一状态源（Single Source of Truth）

所有运行时状态集中在 `ctx` 中，不再散落在各处：

```python
# 之前（散落的状态）
class SimpleAgent:
    def chat(self):
        messages = []
        current_block_index = 0
        current_block_type = None
        accumulated_thinking = ""
        accumulated_content = ""
        # ... 更多状态变量

# 现在（统一的 ctx）
class SimpleAgent:
    def chat(self):
        ctx = RuntimeContext(session_id=session_id)
        # 所有状态通过 ctx 访问
```

### 2. 可测试性

可以轻松创建 mock 的 RuntimeContext 进行单元测试：

```python
def test_tool_execution():
    ctx = RuntimeContext(session_id="test")
    ctx.add_user_message("运行 ls 命令")
    
    # 模拟工具执行
    ctx.accumulator.on_content_start({"type": "tool_use", "id": "t1", "name": "bash"}, index=0)
    ctx.accumulator.on_content_stop(index=0)
    
    assert len(ctx.accumulator.all_blocks) == 1
    assert ctx.accumulator.all_blocks[0]["name"] == "bash"
```

### 3. 可追踪性

通过 `summary()` 方法随时查看完整状态：

```python
print(ctx.summary())
# {
#     "session_id": "sess_123",
#     "messages_count": 5,
#     "current_turn": 2,
#     "block_index": 7,
#     "accumulator_stats": {"total_blocks": 4, "active_blocks": 0},
#     "accumulated_text_length": 1234,
#     "accumulated_thinking_length": 567,
#     "is_completed": False
# }
```

### 4. 关注点分离

- **BlockState**: 只关心 SSE 事件的状态机
- **ContentAccumulator**: 只关心内容累积
- **RuntimeContext**: 只关心状态聚合

每个组件职责单一，易于理解和维护。

### 5. 支持并行工具执行

ContentAccumulator 基于 `index` 的设计天然支持并行：

```python
# 两个工具同时执行
ctx.accumulator.on_content_start({"type": "tool_use", "id": "t1"}, index=0)
ctx.accumulator.on_content_start({"type": "tool_use", "id": "t2"}, index=1)

# 并行接收结果
ctx.accumulator.on_content_delta('{"path": "/app"}', index=1)  # t2 先返回
ctx.accumulator.on_content_delta('{"cmd": "ls"}', index=0)     # t1 后返回

# 按 index 顺序保存
ctx.accumulator.on_content_stop(index=0)
ctx.accumulator.on_content_stop(index=1)
```

## 与 ContentHandler 的配合

`ContentHandler` 是发送 SSE 事件的统一接口，它内部使用 `BlockState`：

```python
# ContentHandler 封装了 BlockState 的操作
content_handler = ContentHandler(broadcaster, ctx.block)

# 发送完整 block（非流式）
await content_handler.emit_block(session_id, "tool_result", {
    "tool_use_id": "t1",
    "content": "执行结果"
})

# 发送流式 block
async for event in content_handler.emit_block_stream(
    session_id, "text", {}, text_generator()
):
    yield event
```

**职责划分**：
- `RuntimeContext.block`: 管理状态
- `ContentHandler`: 发送事件
- `EventBroadcaster`: 实际的 SSE 推送 + 自动累积到 ContentAccumulator

## 总结

RuntimeContext 的核心价值：

| 特性 | 说明 |
|------|------|
| **集中管理** | 所有运行时状态在一个对象中 |
| **生命周期清晰** | 创建 → 使用 → 重置，流程明确 |
| **可测试** | 易于 mock 和断言 |
| **可追踪** | summary() 随时查看状态 |
| **支持并行** | 基于 index 的并行累积 |
| **标准输出** | 直接输出 Claude API 格式 |

