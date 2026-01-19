# Simple Agent 模块

单智能体执行引擎，支持 RVR (Read-Reason-Act-Observe-Validate-Write-Repeat) 循环。

## 📁 目录结构

```
simple/
├── __init__.py                 # 模块入口，导出 SimpleAgent 和 create_simple_agent
├── simple_agent.py             # 主入口 + 初始化 + 工具选择 (786 行)
├── simple_agent_context.py     # Prompt 构建 + Memory 调用 + 多层缓存 (270 行)
├── simple_agent_tools.py       # 工具执行 + Plan 特判 + HITL 处理 (621 行)
├── simple_agent_loop.py        # RVR 主循环 + 流式处理 (447 行)
├── simple_agent_errors.py      # 错误处理辅助函数 (114 行)
└── README.md                   # 本文件
```

**总计**: 2267 行（含注释和文档）

## 🏗️ 架构设计

### 继承关系

```
SimpleAgent
├── ToolExecutionMixin    # 工具执行相关方法
└── RVRLoopMixin          # RVR 主循环相关方法
```

使用 **Mixin 模式** 实现职责分离，保持主类 `SimpleAgent` 的简洁性。

### 职责划分

| 文件 | 职责 | 关键方法 |
|------|------|----------|
| `simple_agent.py` | • Agent 初始化<br>• 模块装配<br>• 工具选择<br>• 沙盒管理 | `__init__()`, `_init_modules()`, `_select_tools()`, `chat()` |
| `simple_agent_context.py` | • Prompt 构建<br>• Memory 检索<br>• 任务复杂度判断 | `build_system_prompt()`, `fetch_user_profile()`, `get_task_complexity()` |
| `simple_agent_tools.py` | • 工具执行<br>• Plan 特判<br>• HITL 处理<br>• 并行/串行执行 | `_execute_single_tool()`, `_execute_tools_core()`, `_handle_human_confirmation()` |
| `simple_agent_loop.py` | • RVR 主循环<br>• 流式 LLM 响应<br>• 消息构建 | `_run_rvr_loop()`, `_process_stream()`, `_handle_tool_calls()` |
| `simple_agent_errors.py` | • 错误处理<br>• 兜底结果生成 | `create_error_tool_result()`, `create_timeout_tool_results()` |

## 🔌 导入路径

### 推荐方式（从 `core.agent` 导入）

```python
from core.agent import SimpleAgent, create_simple_agent

# 创建 Agent
agent = create_simple_agent(
    model="claude-sonnet-4-5-20250929",
    event_manager=event_manager
)

# 执行聊天
async for event in agent.chat(messages, session_id):
    print(event)
```

### 直接导入（从 `core.agent.simple` 导入）

```python
from core.agent.simple import SimpleAgent, create_simple_agent

agent = SimpleAgent(
    model="claude-sonnet-4-5-20250929",
    max_turns=20,
    event_manager=event_manager,
    schema=agent_schema  # 可选：自定义 Schema
)
```

### 导入内部模块（用于扩展）

```python
# 导入 Context 构建函数
from core.agent.simple.simple_agent_context import (
    build_system_prompt,
    fetch_user_profile,
    get_task_complexity
)

# 导入错误处理函数
from core.agent.simple.simple_agent_errors import (
    create_error_tool_result,
    create_timeout_tool_results
)
```

## 🎯 使用示例

### 基础用法

```python
from core.agent import create_simple_agent
from core.events import EventManager

# 创建 EventManager
event_manager = EventManager()

# 创建 Agent
agent = create_simple_agent(
    model="claude-sonnet-4-5-20250929",
    event_manager=event_manager
)

# 执行聊天
messages = [{"role": "user", "content": "你好"}]
async for event in agent.chat(messages, session_id="sess-123"):
    if event["type"] == "content":
        print(event["data"]["text"])
```

### 使用 Schema 配置

```python
from core.schemas import AgentSchema, ToolSelectorConfig

# 自定义 Schema
schema = AgentSchema(
    name="CustomAgent",
    model="claude-sonnet-4-5-20250929",
    max_turns=15,
    tool_selector=ToolSelectorConfig(
        enabled=True,
        max_parallel_tools=3
    )
)

agent = SimpleAgent(
    event_manager=event_manager,
    schema=schema
)
```

### Clone 模式（高性能）

```python
# 创建原型 Agent
prototype_agent = create_simple_agent(event_manager=event_manager)
prototype_agent._is_prototype = True

# 为每个会话克隆（复用 LLM、工具等重量级组件）
session_agent = prototype_agent.clone_for_session(
    event_manager=new_event_manager,
    workspace_dir="/workspace/sess-123"
)
```

## 🔄 RVR 循环流程

```
┌─────────────────────────────────────────────────┐
│              SimpleAgent.chat()                 │
└─────────────────────────────────────────────────┘
                     │
    ┌────────────────┴────────────────┐
    │  1. 初始化（Session Context）   │
    └────────────────┬────────────────┘
                     │
    ┌────────────────┴────────────────┐
    │  2. Intent Analysis             │
    └────────────────┬────────────────┘
                     │
    ┌────────────────┴────────────────┐
    │  3. Tool Selection              │
    └────────────────┬────────────────┘
                     │
    ┌────────────────┴────────────────┐
    │  4. System Prompt 构建          │
    │     (_build_system_prompt)      │
    └────────────────┬────────────────┘
                     │
    ┌────────────────┴────────────────┐
    │  5-6. RVR Loop                  │
    │     (_run_rvr_loop)             │
    │                                 │
    │  ┌───────────────────────┐     │
    │  │ Read   (Plan 状态)     │     │
    │  │ Reason (LLM Thinking) │     │
    │  │ Act    (Tool Calls)   │     │
    │  │ Observe (Tool Results)│     │
    │  │ Validate (验证结果)    │     │
    │  │ Write  (更新状态)      │     │
    │  │ Repeat (if needed)    │     │
    │  └───────────────────────┘     │
    └────────────────┬────────────────┘
                     │
    ┌────────────────┴────────────────┐
    │  7. Final Output & Report       │
    └─────────────────────────────────┘
```

## 🛠️ 扩展点

### 1. 自定义 Mixin

```python
class CustomMixin:
    """自定义功能 Mixin"""
    
    def custom_method(self):
        # 自定义逻辑
        pass

class CustomAgent(CustomMixin, ToolExecutionMixin, RVRLoopMixin):
    """扩展 Agent，添加自定义功能"""
    pass
```

### 2. 重写 Context 构建

```python
def custom_build_system_prompt(intent, **kwargs):
    """自定义 Prompt 构建逻辑"""
    base_prompt = build_system_prompt(intent, **kwargs)
    # 添加自定义内容
    return f"{base_prompt}\n\n自定义指令..."
```

### 3. 自定义错误处理

```python
def custom_error_handler(tool_id, tool_name, error):
    """自定义错误处理"""
    # 记录到监控系统
    monitor.log_error(tool_name, error)
    # 返回标准格式
    return create_error_tool_result(tool_id, tool_name, error)
```

## 📊 与 Multi Agent 对比

| 特性 | Simple Agent | Multi Agent |
|------|-------------|-------------|
| **适用场景** | 单任务、线性流程 | 复杂任务、需要多角色协作 |
| **目录位置** | `core/agent/simple/` | `core/agent/multi/` |
| **核心类** | `SimpleAgent` | `MultiAgentOrchestrator`, `LeadAgent` |
| **执行模式** | RVR 循环 | Leader-Worker 模式 |
| **工具执行** | 直接执行 | 通过 sub-agent 执行 |
| **代码行数** | ~2267 行 | ~3000+ 行 |

## 🔗 相关模块

- **`core/agent/multi/`**: 多智能体编排
- **`core/agent/factory.py`**: Agent 工厂（创建和配置）
- **`core/context/`**: 上下文管理和 Prompt 工程
- **`core/tool/`**: 工具执行器和选择器
- **`core/billing/`**: 计费和 Usage 统计

## 📝 版本历史

- **V7.6** (2026-01-19): 拆分为独立模块，与 `multi/` 保持一致的目录结构
- **V7.5**: 引入 Billing V7.5，统一 `UsageTracker`
- **V7.0**: 路由层集成，支持 Intent 传入
- **V6.3**: Prompt Caching 多层缓存
- **V4.6**: PromptSchema 分层
