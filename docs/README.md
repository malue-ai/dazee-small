# ZenFlux Agent 文档

> 📅 **最后更新**: 2026-01-05  
> 🎯 **当前版本**: V4.0 - 模块化重构版

---

## 📚 文档结构

```
docs/
├── README.md                        # 👈 你在这里（索引）
│
├── 【核心架构】
│   ├── 00-ARCHITECTURE-V4.md        # ⭐⭐⭐ V4 架构总览（必读）
│   ├── 00-ARCHITECTURE-OVERVIEW.md  # V3.7 架构（归档）
│   └── AGENT_ARCHITECTURE_VISUAL.md # 架构可视化图
│
├── 【协议与规范】
│   ├── 01-MEMORY-PROTOCOL.md        # Memory-First 协议
│   ├── 02-CAPABILITY-ROUTING.md     # 能力路由算法
│   ├── 03-EVENT-PROTOCOL.md         # 统一事件协议
│   ├── 10-EVENT_DRIVEN_BEST_PRACTICES.md  # 事件驱动最佳实践
│   └── 14-TOOL_STREAMING_ARCHITECTURE.md  # 工具流式调用架构
│
├── 【模块文档】
│   ├── 04-SSE-CONNECTION-MANAGEMENT.md  # SSE 连接管理
│   ├── 05-MULTI-AGENT-ORCHESTRATION.md  # 多 Agent 编排
│   ├── 06-CONVERSATION-HISTORY.md   # 对话历史管理
│   ├── 07-WORKSPACE-ARCHITECTURE.md # Workspace 架构
│   ├── 08-DATA_STORAGE_ARCHITECTURE.md  # 数据存储架构
│   ├── 09-MESSAGE_SCHEMA_UPGRADE.md # 消息 Schema
│   ├── 13-THINKING_STORAGE_STRATEGY.md  # Thinking 存储策略
│   ├── 15-MESSAGE_STATUS_AND_METADATA.md # 消息状态与元数据
│   └── 16-USAGE_TRACKING.md         # 用量追踪
│
├── 【数据与存储】
│   ├── DATABASE.md                  # 数据库设计
│   ├── FILE_STORAGE_SYSTEM.md       # 文件存储系统
│   ├── RVR_LOOP_LOGIC.md            # RVR 循环逻辑
│   └── CONVERSATION_DELTA_PATTERN.md # 对话增量模式
│
└── 【E2B 集成】
    ├── E2B_INTEGRATION.md           # E2B 集成指南
    ├── E2B_QUICKSTART.md            # E2B 快速开始
    ├── E2B_SANDBOX_LIFECYCLE_GUIDE.md   # 沙箱生命周期
    └── E2B_ARCHITECTURE_VALIDATION.md   # E2B 架构验证
```

---

## 🚀 快速开始

### 1. 理解 V4 架构（2分钟）

```
┌─────────────────────────────────────────────────────────────────────┐
│                        V4 模块化架构                                 │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  SimpleAgent = 编排者（Orchestrator）                               │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│  只做协调，不包含业务逻辑                                            │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │                    独立模块（专家）                              │ │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │ │
│  │  │IntentAnalyzer│  │ ToolSelector │  │ ToolExecutor │         │ │
│  │  │  意图分析    │  │  工具选择    │  │  工具执行    │         │ │
│  │  └──────────────┘  └──────────────┘  └──────────────┘         │ │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │ │
│  │  │ EventManager │  │MemoryManager │  │RuntimeContext│         │ │
│  │  │  事件管理    │  │  记忆管理    │  │  运行上下文  │         │ │
│  │  └──────────────┘  └──────────────┘  └──────────────┘         │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### 2. 基本使用

```python
from core.agent import create_simple_agent
from core.events import EventManager

# 创建必需的 EventManager
event_manager = EventManager()

# 创建 Agent
agent = create_simple_agent(
    model="claude-sonnet-4-5-20250929",
    event_manager=event_manager
)

# 运行任务（流式输出）
# messages 应由 ChatService 准备好，包含完整历史 + 当前用户消息
async for event in agent.chat(
    messages=messages,  # List[Message]，包含用户输入
    session_id="session_001"
):
    print(event)
```

### 3. V4.0 核心改进

| 维度 | V3.7 | V4.0 |
|------|------|------|
| **Agent** | 单文件 1000+ 行 | `core/agent/` 模块化 3 个文件 |
| **Tool** | 分散 | `core/tool/` Selector + Executor |
| **Memory** | 单文件 | `core/memory/` user/ + system/ 层级 |
| **Context** | 内嵌 Agent | `core/context/` 独立模块 |
| **Events** | 分散发射 | `core/events/` 6 类统一管理 |

---

## 📖 阅读顺序

### 必读（理解架构）

1. **[00-ARCHITECTURE-V4.md](./00-ARCHITECTURE-V4.md)** ⭐⭐⭐
   - V4 整体架构
   - 模块职责划分
   - 数据流图

### 协议与规范

2. **[01-MEMORY-PROTOCOL.md](./01-MEMORY-PROTOCOL.md)** ⭐⭐
   - Memory-First Protocol
   - Plan/Todo 管理

3. **[03-EVENT-PROTOCOL.md](./03-EVENT-PROTOCOL.md)** ⭐⭐
   - 统一事件协议（SSE/WebSocket）
   - 事件类型定义
   - 前端接入指南

### 按需阅读

4. **[02-CAPABILITY-ROUTING.md](./02-CAPABILITY-ROUTING.md)**
   - 能力路由算法
   - 工具选择策略

5. **[E2B_INTEGRATION.md](./E2B_INTEGRATION.md)**
   - E2B 沙箱集成
   - Vibe Coding 支持

---

## 🗂️ 代码位置速查

| 模块 | 位置 | 说明 |
|------|------|------|
| **Agent 编排** | `core/agent/simple_agent.py` | 核心编排器 |
| **意图分析** | `core/agent/intent_analyzer.py` | 意图识别 |
| **工具选择** | `core/tool/selector.py` | 工具选择器 |
| **工具执行** | `core/tool/executor.py` | 工具执行器 |
| **记忆管理** | `core/memory/manager.py` | 统一入口 |
| **运行上下文** | `core/context/runtime.py` | 运行时状态 |
| **事件管理** | `core/events/manager.py` | 统一事件 |
| **LLM 服务** | `core/llm/claude.py` | Claude API |
| **能力注册** | `core/capability_registry.py` | 能力配置 |

---

## 📊 模块依赖图

```
                    SimpleAgent
                         │
         ┌───────────────┼───────────────┐
         │               │               │
         ▼               ▼               ▼
  IntentAnalyzer   ToolSelector   ToolExecutor
         │               │               │
         │               └───────┬───────┘
         │                       │
         │                       ▼
         │            CapabilityRegistry
         │                       │
         │                       ▼
         │             capabilities.yaml
         │
         ▼
   ClaudeLLMService
```

---

## 🔮 版本演进

| 版本 | 日期 | 主要变化 |
|------|------|----------|
| V4.0 | 2025-12-30 | 模块化重构、Memory 层级化 |
| V3.7 | 2025-12-24 | E2B 集成、能力抽象层 |
| V3.6 | 2025-12-23 | Memory-First Protocol |
| V3.5 | 2025-12-20 | 基础架构 |

---

## 🗑️ 废弃文件

以下文件已在 V4.0 中废弃：

| 文件 | 替代 |
|------|------|
| `core/agent.py` | `core/agent/simple_agent.py` |
| `core/memory.py` | `core/memory/` 目录 |
| `core/llm_service.py` | `core/llm/` 目录 |
| `core/planning.py` | 已删除（使用 `plan_todo_tool`） |
| `core/context.py` | `core/context/conversation.py` |

---

**🎉 欢迎使用 ZenFlux Agent V4！**
