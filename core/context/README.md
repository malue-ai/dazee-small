# Context 模块 - 上下文管理

> 核心模块：管理 Agent 运行时的上下文状态、消息历史

## 🎯 设计理念

基于 [Anthropic: Effective harnesses for long-running agents](https://www.anthropic.com/engineering) 的 6 大策略：

| # | 策略 | 目的 | 实现状态 |
|---|------|------|---------|
| 1 | **KV-Cache 优化** | 保持前缀稳定，最大化缓存命中率 | ✅ 已集成 |
| 2 | **Todo 重写** | 任务目标注入末尾，对抗 Lost-in-the-Middle | ✅ 已实现 |
| 3 | **工具遮蔽** | 状态机驱动的工具可见性控制 | 🟡 待集成 |
| 4 | **可恢复压缩** | 保留引用丢弃内容，按需恢复 | 🟡 待集成 |
| 5 | **模式锚定检测** | 检测重复格式（仅检测，干预由上层决定） | 🔴 待研究 |
| 6 | **错误保留** | 保留失败记录作为学习素材 | ✅ 已实现 |

## 📁 文件职责

```
core/context/
├── README.md              # 本文档
├── __init__.py            # 统一导出
├── runtime.py             # ✅ 运行时状态（SSE 流式处理）
├── injectors/             # ✅ Phase-based Injector 系统（V9.0+）
│   ├── phase1/            # System Message 注入
│   ├── phase2/            # User Context 注入
│   └── phase3/            # Runtime 注入
├── providers/             # ✅ 上下文数据提供器
└── context_engineering.py # ✅ 上下文优化策略
```

### 各文件职责边界

| 文件/目录 | 职责 | 不该做的事 |
|-----------|------|-----------|
| `runtime.py` | SSE 块状态、Content 累积、Turn 管理 | 不处理 Prompt、不访问数据库 |
| `injectors/` | Phase-based 上下文注入 | 不直接调用 LLM |
| `providers/` | 从 DB/缓存 获取上下文数据 | 不处理消息格式转换 |
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
│   RuntimeContext  │   │  Injectors        │   │ContextEngineering │
│   (runtime.py)    │   │  (injectors/)     │   │     Manager       │
│                   │   │                   │   │                   │
│ • SSE 块状态      │   │ • Phase 1: System │   │ • KV-Cache 优化   │
│ • Content 累积    │   │ • Phase 2: User   │   │ • Todo 重写       │
│ • Turn 计数       │   │ • Phase 3: Runtime│   │ • 错误保留        │
└───────────────────┘   └───────────────────┘   └───────────────────┘
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

### 2. Injectors - Phase-based 上下文注入（推荐）

```python
from core.context.injectors import (
    InjectionOrchestrator,
    InjectionContext,
    create_default_orchestrator,
)

# 创建编排器
orchestrator = create_default_orchestrator()

# 构建上下文
context = InjectionContext(
    user_id="user_123",
    user_query="帮我写一段代码",
    prompt_cache=prompt_cache,
)

# Phase 1: System Message（带缓存元数据）
system_blocks = await orchestrator.build_system_blocks(context)

# Phase 2 & 3: User Messages
messages = await orchestrator.build_messages(context)
```

### 3. MetadataProvider - 通用元数据获取

```python
from core.context.providers import (
    ConversationMetadataProvider,
    load_plan_for_context,
    load_context_metadata
)

# 方式1：使用 Provider 类（推荐，支持缓存）
provider = ConversationMetadataProvider("conv_123")
plan = await provider.get_plan()
compression = await provider.get_compression_info()

# 方式2：批量获取（一次数据库查询）
data = await provider.get_context_data(["plan", "compression"])
plan = data.get("plan")

# 方式3：便捷函数
plan = await load_plan_for_context("conv_123")
context = await load_context_metadata("conv_123", ["plan", "compression"])

# 扩展新字段：只需在 FIELD_CONFIGS 中添加配置
# 然后添加对应的 get_xxx() 方法
```

### 5. ContextEngineeringManager - 上下文优化

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
├── 注入上下文到 System Message？ → injectors/phase1/
├── 注入上下文到 User Message？ → injectors/phase2/
├── 运行时追加上下文？ → injectors/phase3/
└── 优化上下文策略？ → context_engineering.py
```

### 2. 禁止事项

```python
# ❌ 禁止在 runtime.py 中访问数据库
class RuntimeContext:
    async def load_from_db(self):  # ❌ 不要这样做！
        ...

# ❌ 禁止在 Injector 中直接调用 LLM
class MyInjector(BaseInjector):
    async def inject(self, ctx):
        await llm.create_message()  # ❌ 不要这样做！

# ❌ 禁止创建新的上下文类
class MyNewContext:  # ❌ 不要新建，扩展现有类！
    ...
```

### 3. 扩展方式

```python
# ✅ 正确：创建新的 Injector
from core.context.injectors import BaseInjector, InjectionPhase

class MyNewInjector(BaseInjector):
    @property
    def phase(self) -> InjectionPhase:
        return InjectionPhase.USER_CONTEXT  # Phase 2
    
    async def inject(self, context) -> InjectionResult:
        # 获取数据并返回
        return InjectionResult(content="...")

# ✅ 正确：在 context_engineering.py 中添加新策略
class ContextEngineeringManager:
    def __init__(self):
        self.error_retention = ErrorRetention()
        self.my_new_strategy = MyNewStrategy()  # ✅ 这样添加
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

1. **KV-Cache 优化** ✅ 已完成
   - [x] `stable_json_dumps` 稳定序列化函数
   - [x] 集成到工具结果序列化流程
   - [ ] 添加缓存命中率监控（可选）

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

## 📊 指标

| 文件/目录 | 当前行数 | 目标行数 | 状态 |
|-----------|---------|---------|------|
| runtime.py | 672 | 600 | 🟡 可优化 |
| injectors/ | ~500 | 500 | ✅ 合理 |
| context_engineering.py | 961 | 500 | 🟡 可优化 |

---

**维护者**: ZenFlux Team  
**最后更新**: 2026-02-03  
**相关文档**: 
- [架构总览](../../docs/architecture/00-ARCHITECTURE-OVERVIEW.md)

