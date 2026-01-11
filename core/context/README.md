# Context 模块 - 上下文管理

> 核心模块：管理 Agent 运行时的上下文状态、消息历史、Prompt 追加

## 🎯 设计理念

基于 [Anthropic: Effective harnesses for long-running agents](https://www.anthropic.com/engineering) 的 6 大策略：

| # | 策略 | 目的 | 实现状态 |
|---|------|------|---------|
| 1 | **KV-Cache 优化** | 保持前缀稳定，最大化缓存命中率 | 🟡 待集成 |
| 2 | **Todo 重写** | 任务目标注入末尾，对抗 Lost-in-the-Middle | ✅ 已实现 |
| 3 | **工具遮蔽** | 状态机驱动的工具可见性控制 | 🟡 待集成 |
| 4 | **可恢复压缩** | 保留引用丢弃内容，按需恢复 | 🟡 待集成 |
| 5 | **模式锚定检测** | 检测重复格式（仅检测，干预由上层决定） | 🔴 待研究 |
| 6 | **错误保留** | 保留失败记录作为学习素材 | ✅ 已实现 |

## 📁 文件职责

```
core/context/
├── README.md              # 本文档（必读！）
├── __init__.py            # 统一导出
├── runtime.py             # ✅ 运行时状态（SSE 流式处理）
├── conversation.py        # ✅ 对话历史（消息加载、Token 压缩）
├── prompt_manager.py      # ✅ Prompt 追加（事件驱动）
└── context_engineering.py # ⚠️ 上下文优化（需要精简）
```

### 各文件职责边界

| 文件 | 职责 | 不该做的事 |
|------|------|-----------|
| `runtime.py` | SSE 块状态、Content 累积、Turn 管理 | 不处理 Prompt、不访问数据库 |
| `conversation.py` | 从 DB 加载历史消息、Token 压缩 | 不处理流式响应、不构建 Prompt |
| `prompt_manager.py` | 事件驱动的 Prompt 片段追加 | 不处理消息格式转换 |
| `context_engineering.py` | 6 大优化策略的实现 | 不做 Prompt 片段管理 |

## 🏗️ 架构图

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          Agent.chat() 主循环                             │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
        ┌───────────────────────────┼───────────────────────────┐
        │                           │                           │
        ▼                           ▼                           ▼
┌───────────────────┐   ┌───────────────────┐   ┌───────────────────┐
│   RuntimeContext  │   │    Context        │   │  PromptManager    │
│   (runtime.py)    │   │ (conversation.py) │   │(prompt_manager.py)│
│                   │   │                   │   │                   │
│ • SSE 块状态      │   │ • 加载历史消息    │   │ • 事件触发追加    │
│ • Content 累积    │   │ • Token 压缩      │   │ • 片段去重        │
│ • Turn 计数       │   │ • 格式转换        │   │ • 构建最终 Prompt │
└───────────────────┘   └───────────────────┘   └───────────────────┘
                                    │
                                    ▼
                        ┌───────────────────┐
                        │ContextEngineering │
                        │     Manager       │
                        │                   │
                        │ • Todo 重写       │
                        │ • 错误保留        │
                        │ • (其他策略待实现)│
                        └───────────────────┘
```

## 📖 使用规范

### 1. RuntimeContext - 流式状态管理

```python
from core.context import RuntimeContext, create_runtime_context

# 创建（每次 chat() 调用创建一个）
ctx = create_runtime_context(session_id="sess_123", max_turns=20)

# 处理 SSE 事件
ctx.accumulator.on_content_start({"type": "thinking"})
ctx.accumulator.on_content_delta("让我思考...")
ctx.accumulator.on_content_stop(signature="...")

# 获取累积内容
content = ctx.accumulator.build_for_db()

# Turn 管理
ctx.next_turn()
if ctx.is_max_turns_reached():
    break
```

### 2. Context - 对话历史管理

```python
from core.context import Context, create_context

# 创建并加载历史（会自动压缩）
context = await create_context(
    conversation_id="conv_123",
    conversation_service=conversation_service
)

# 获取用于 LLM 的消息
messages = context.get_messages_for_llm()

# 检查 Token 使用
is_over, current, threshold = context.check_threshold(0.8)

# 手动压缩
await context.compress_if_needed()
```

### 3. PromptManager - Prompt 追加

```python
from core.context import get_prompt_manager

prompt_mgr = get_prompt_manager()

# 事件触发追加
prompt_mgr.on_session_start(ctx, conversation_id="conv_123")
prompt_mgr.on_tool_result(ctx, tool_name="rag_search", result={...})
prompt_mgr.on_task_detected(ctx, task_type="ppt_generation")

# 追加自定义片段
prompt_mgr.append_fragment(ctx, "e2b_rules", priority=60)

# 构建最终 Prompt
system_prompt = prompt_mgr.build_system_prompt(ctx, base_prompt="...")

# 检查已追加的片段
if prompt_mgr.has_fragment(ctx, "sandbox_context"):
    print("已追加沙盒上下文")
```

### 4. ContextEngineeringManager - 上下文优化

```python
from core.context import create_context_engineering_manager

ce_mgr = create_context_engineering_manager()

# Todo 重写（对抗 Lost-in-the-Middle）
prepared = ce_mgr.prepare_messages_for_llm(
    messages=messages,
    plan=current_plan,
    inject_plan=True
)

# 错误记录
ce_mgr.record_error(
    tool_name="web_search",
    error=e,
    input_params={"query": "..."}
)
```

## ⚠️ 代码规范（必须遵守！）

### 1. 新增功能放哪里？

```
问：我要添加一个新的上下文处理功能，放哪里？

判断流程：
├── 处理 SSE 流式响应？ → runtime.py
├── 处理数据库消息？ → conversation.py
├── 追加 Prompt 片段？ → prompt_manager.py
└── 优化上下文策略？ → context_engineering.py
```

### 2. 禁止事项

```python
# ❌ 禁止在 runtime.py 中访问数据库
class RuntimeContext:
    async def load_from_db(self):  # ❌ 不要这样做！
        ...

# ❌ 禁止在 conversation.py 中处理 SSE
class Context:
    def on_content_delta(self):  # ❌ 不要这样做！
        ...

# ❌ 禁止在 prompt_manager.py 中直接操作消息列表
class PromptManager:
    def modify_messages(self, messages):  # ❌ 不要这样做！
        ...

# ❌ 禁止创建新的上下文类
class MyNewContext:  # ❌ 不要新建，扩展现有类！
    ...
```

### 3. 扩展方式

```python
# ✅ 正确：在 context_engineering.py 中添加新策略
class ContextEngineeringManager:
    def __init__(self):
        # 现有
        self.error_retention = ErrorRetention()
        # 新增策略
        self.my_new_strategy = MyNewStrategy()  # ✅ 这样添加

# ✅ 正确：在 prompt_manager.py 中添加新事件
class PromptManager:
    def on_my_new_event(self, ctx, **kwargs):  # ✅ 这样添加
        ...

# ✅ 正确：添加新的 Prompt 片段
# 1. 在 prompts/fragments/ 创建 my_fragment.md
# 2. 调用 prompt_mgr.append_fragment(ctx, "my_fragment")
```

### 4. 函数签名规范

```python
# ✅ 正确：第一个参数是 RuntimeContext
def process_something(ctx: RuntimeContext, **kwargs) -> Result:
    ...

# ✅ 正确：异步方法用于 I/O 操作
async def load_messages(self) -> List[Dict]:
    ...

# ✅ 正确：纯计算方法用同步
def count_tokens(self, messages: List[Dict]) -> int:
    ...
```

## 🔧 待办事项

### 需要实现的功能

1. **KV-Cache 优化**
   - [ ] 实现消息前缀稳定性检测
   - [ ] 添加缓存命中率监控

2. **工具遮蔽**
   - [ ] 实现状态机
   - [ ] 集成到 Agent 主循环

3. **可恢复压缩**
   - [ ] 实现引用存储
   - [ ] 支持按需恢复

### 策略 5：模式锚定检测（复杂问题）

**问题描述**：模型会被上下文中的格式"锚定"，持续输出相同结构

**难点**：
- 写报告的用户：希望格式一致 ✅
- 写小说的用户：希望每章不同 ✅
- **系统无法自动判断用户意图**

**当前实现**：
- `PatternAnchoringDetector` 仅提供检测能力
- `detect_patterns()` - 检测重复模式
- `get_repetition_score()` - 计算重复度评分
- `should_warn()` - 是否需要警告
- **不做自动干预**，由上层根据场景决定

**未来方向**：
- 用户偏好设置（"创意模式" vs "结构化模式"）
- 场景识别（报告/小说/代码等）
- 动态干预策略

### 需要集成的代码

1. **context_engineering.py**
   - [ ] 集成 `CacheOptimizer` 到消息序列化流程
   - [ ] 集成 `ToolMasker` 到 Agent 主循环
   - [ ] 集成 `RecoverableCompressor` 到工具结果处理

2. **prompt_manager.py**
   - [ ] 删除未使用的 `on_task_detected`（或使用它）
   - [ ] 删除未使用的 `on_files_uploaded`（或使用它）
   - [ ] 精简重复代码

## 📊 指标

| 文件 | 当前行数 | 目标行数 | 状态 |
|------|---------|---------|------|
| runtime.py | 672 | 600 | 🟡 可优化 |
| conversation.py | 758 | 500 | 🟡 可优化 |
| prompt_manager.py | 848 | 400 | 🔴 需精简 |
| context_engineering.py | 961 | 300 | 🔴 需大幅精简 |
| **总计** | **3239** | **1800** | **目标减少 44%** |

---

**维护者**: ZenFlux Team  
**最后更新**: 2026-01-11  
**相关文档**: 
- [V4 架构总览](../../docs/architecture/00-ARCHITECTURE-V4.md)
- [Memory Protocol](../../docs/architecture/01-MEMORY-PROTOCOL.md)

