# ZenFlux Agent 文档

> 📅 **最后更新**: 2026-01-09  
> 🎯 **当前版本**: V4.0 - 模块化重构版

---

## 📚 文档结构

```
docs/
├── README.md                        # 👈 你在这里（索引）
│
├── architecture/                    # 🏗️ 架构文档 (23个)
│   ├── 00-ARCHITECTURE-V4.md        # ⭐⭐⭐ V4 架构总览（必读）
│   ├── 00-ARCHITECTURE-OVERVIEW.md  # V3.7 架构（归档）
│   ├── 01-MEMORY-PROTOCOL.md        # Memory-First 协议
│   ├── 02-CAPABILITY-ROUTING.md     # 能力路由算法
│   ├── 03-EVENT-PROTOCOL.md         # 统一事件协议
│   ├── 04-SSE-CONNECTION-MANAGEMENT.md
│   ├── 05-MULTI-AGENT-ORCHESTRATION.md
│   ├── 06-CONVERSATION-HISTORY.md
│   ├── 07-WORKSPACE-ARCHITECTURE.md
│   ├── 08-DATA_STORAGE_ARCHITECTURE.md
│   ├── 09-MESSAGE_SCHEMA_UPGRADE.md
│   ├── 10-EVENT_DRIVEN_BEST_PRACTICES.md
│   ├── 12-CONTEXT_ENGINEERING_OPTIMIZATION.md
│   ├── 13-INVOCATION_STRATEGY_V2.md
│   ├── 14-CLAUDE_SKILLS_DEEP_DIVE.md
│   ├── 15-FRAMEWORK_PROMPT_CONTRACT.md
│   ├── 16-USAGE_TRACKING.md
│   ├── 17-PROMPT_TEMPLATE_SYSTEM.md
│   ├── 18-THINKING_STORAGE_STRATEGY.md
│   ├── 19-TOOL_STREAMING_ARCHITECTURE.md
│   ├── AGENT_ARCHITECTURE_VISUAL.md
│   ├── CONVERSATION_DELTA_PATTERN.md
│   └── MULTI_AGENT_ROADMAP.md
│
├── guides/                          # 📖 使用指南 (10个)
│   ├── E2B_INTEGRATION.md           # E2B 集成指南
│   ├── E2B_QUICKSTART.md            # E2B 快速开始
│   ├── E2B_SANDBOX_LIFECYCLE_GUIDE.md
│   ├── E2B_ARCHITECTURE_VALIDATION.md
│   ├── E2B_CORE_CAPABILITIES_ANALYSIS.md
│   ├── MEM0_EMBEDDING_GUIDE.md
│   ├── MEM0_SETUP_GUIDE.md
│   ├── GRPC_INTEGRATION.md
│   ├── PROMPT_DRIVEN_IMPLEMENTATION.md
│   └── RESULT_COMPACTOR_IMPLEMENTATION.md
│
├── specs/                           # 📋 规范文档 (4个)
│   ├── AGENT_IO_SPECIFICATION.md
│   ├── DATABASE.md
│   ├── FILE_STORAGE_SYSTEM.md
│   └── TOOL_REGISTRATION_SPEC.md
│
├── reports/                         # 📊 报告文档 (5个)
│   ├── ANTIGRAVITY_COMPARISON_REPORT.md
│   ├── E2E_FLOW_AUDIT_REPORT.md
│   ├── E2E_OPTIMIZATION_VERIFICATION.md
│   ├── MEM0_E2E_TEST_SUMMARY.md
│   └── PROJECT_ISSUES_ANALYSIS.md
│
├── deployment/                      # 🚀 部署文档 (3个)
│   ├── DEPLOYMENT_COMPLETE.md
│   ├── DOCKER_DEPLOYMENT.md
│   └── README_DOCKER.md
│
└── internal/                        # 🔒 内部文档 (2个)
    ├── AI技术团队招聘规划_完整版.md
    └── E2B_VIBE_CODING_GUIDE.md
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
async for event in agent.chat(
    messages=messages,  # List[Message]
    session_id="session_001"
):
    print(event)
```

### 3. V4.0 核心改进

| 维度 | V3.7 | V4.0 |
|------|------|------|
| **Agent** | 单文件 1000+ 行 | `core/agent/` 模块化 |
| **Tool** | 分散 | `core/tool/` Selector + Executor |
| **Memory** | 单文件 | `core/memory/` user/ + system/ |
| **Context** | 内嵌 Agent | `core/context/` 独立模块 |
| **Events** | 分散发射 | `core/events/` 统一管理 |

---

## 📖 阅读顺序

### 必读（理解架构）

1. **[architecture/00-ARCHITECTURE-V4.md](./architecture/00-ARCHITECTURE-V4.md)** ⭐⭐⭐
   - V4 整体架构、模块职责、数据流图

### 协议与规范

2. **[architecture/01-MEMORY-PROTOCOL.md](./architecture/01-MEMORY-PROTOCOL.md)** ⭐⭐
   - Memory-First Protocol、Plan/Todo 管理

3. **[architecture/03-EVENT-PROTOCOL.md](./architecture/03-EVENT-PROTOCOL.md)** ⭐⭐
   - 统一事件协议、前端接入指南

### 按需阅读

4. **[architecture/02-CAPABILITY-ROUTING.md](./architecture/02-CAPABILITY-ROUTING.md)**
   - 能力路由算法、工具选择策略

5. **[guides/E2B_INTEGRATION.md](./guides/E2B_INTEGRATION.md)**
   - E2B 沙箱集成、Vibe Coding 支持

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
| **能力注册** | `core/tool/capability/registry.py` | 能力配置 |

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
