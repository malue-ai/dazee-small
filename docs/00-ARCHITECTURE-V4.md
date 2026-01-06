# ZenFlux Agent V4 架构总览

> 📅 **最后更新**: 2026-01-06  
> 🎯 **当前版本**: V4.2.2 - Re-Plan（自适应重规划）  
> 🔗 **前版本**: [V3.7 架构](./ARCHITECTURE_V3.7_E2B.md)
> ✅ **优化状态**: Schema 驱动 + Context Reduction + 工具分层 + Code-First 编排 + E2E 追踪 + **Re-Plan**

---

## 📋 目录

- [版本演进](#版本演进)
- [核心理念](#核心理念)
- [整体架构](#整体架构)
- [模块详解](#模块详解)
- [数据流](#数据流)
- [文件结构](#文件结构)

---

## 🚀 版本演进

### V4.2.1 → V4.2.2 核心变化（Re-Plan 自适应重规划）

| 维度 | V4.2.1 | V4.2.2 | 改进 |
|------|--------|--------|------|
| **计划执行** | 固定计划 | 自适应重规划 | ✅ Claude 自主决定是否 replan |
| **失败处理** | 手动重试 | 智能重规划 | ✅ 保留已完成步骤，重新生成剩余 |
| **工具封装** | Agent 管理 | 工具内部闭环 | ✅ plan_todo 内置 Claude + Extended Thinking |
| **Schema 配置** | 基础配置 | Re-Plan 配置 | ✅ replan_enabled/max_attempts/strategy |

### V4.2 → V4.2.1 核心变化（Code-First + E2E Pipeline）

| 维度 | V4.2 | V4.2.1 | 改进 |
|------|------|------|------|
| **代码编排** | LLM 自由生成 | Code-First 编排器 | ✅ 结构化代码生成与验证 |
| **代码验证** | 无 | `CodeValidator` | ✅ 语法/依赖/安全自动验证 |
| **执行追踪** | 分散日志 | `E2EPipelineTracer` | ✅ 全链路可观测 |
| **E2B 集成** | 工具调用 | CodeOrchestrator | ✅ 代码生成-验证-执行闭环 |

### V4.1 → V4.2 核心变化

| 维度 | V4.1 | V4.2 | 改进 |
|------|------|------|------|
| **工具选择** | Intent 推断 | Schema 驱动优先 | ✅ 优先使用 Schema 配置 |
| **选择优先级** | Plan > Intent | Schema > Plan > Intent | ✅ 符合 Prompt 驱动设计 |

### V4.0 → V4.1 核心变化

| 维度 | V4.0 | V4.1 | 改进 |
|------|------|------|------|
| **Result Compaction** | 无 | `ResultCompactor` | ✅ 搜索结果减少 76.6% |
| **状态管理** | `plan_state` | `_plan_cache` | ✅ 明确是缓存非隐式状态 |
| **工具分层** | 无 | `level` + `cache_stable` | ✅ 支持工具分层加载 |
| **Cache 监控** | 无 | 实时日志 | ✅ 显示 Cache HIT/节省 |
| **配置驱动** | 部分 | 完全 YAML | ✅ 精简规则自动加载 |

### V3.7 → V4.0 核心变化

| 维度 | V3.7 | V4.0 | 改进 |
|------|------|------|------|
| **Agent** | 单文件 `agent.py` (1000+行) | `core/agent/` 模块化 | ✅ 拆分为 3 个独立文件 |
| **Context** | 分散在 Agent 内部 | `core/context/` 独立模块 | ✅ Runtime + Conversation 分离 |
| **Tool** | `tools/executor.py` | `core/tool/` 独立模块 | ✅ Selector + Executor 解耦 |
| **Memory** | 单文件 `memory.py` | `core/memory/` 层级化 | ✅ user/ + system/ 分层 |
| **LLM** | `llm_service.py` | `core/llm/` 多提供商 | ✅ Claude/OpenAI/Gemini |
| **Events** | 分散的事件发射 | `core/events/` 统一管理 | ✅ 6 类事件统一接口 |

### 🎯 V4.2.2 优化重点（Re-Plan 自适应重规划）

1. **Re-Plan 机制** - Claude 自主决定是否调用 replan，无需 Agent 硬规则
2. **工具封装闭环** - plan_todo 内部调用 Claude + Extended Thinking 生成计划
3. **增量/全量策略** - incremental 保留已完成步骤，full 全量重新生成
4. **失败阈值控制** - failure_threshold 配置触发重规划的失败率阈值

### 🎯 V4.2.1 优化重点（Code-First + E2E Pipeline）

1. **Code-First 编排** - 参考 Manus/Claude Code，代码先行策略
2. **E2E Pipeline 追踪** - 全链路可观测，每阶段输入-处理-输出
3. **代码验证闭环** - 语法检查→依赖检查→安全检查→执行
4. **CodeOrchestrator** - 统一代码生成-验证-执行流程

### 🎯 V4.2 优化重点

1. **Schema 驱动** - 工具选择优先使用 Schema 配置
2. **Context Reduction** - 工具结果精简，减少 70%+ Context
3. **配置驱动** - 精简规则在 YAML 中配置，自动生效
4. **Cache 友好** - 工具分层 + 稳定性标记

### 🎯 V4.0 设计目标

1. **模块化** - 每个模块单一职责，可独立测试
2. **层级化** - 清晰的依赖方向，避免循环依赖
3. **可扩展** - 新功能通过配置添加，不修改核心代码
4. **可观测** - 统一事件系统，完整的执行追踪

### ✨ V4.2.2 核心成就（Re-Plan 自适应重规划）

| 改进项 | 实现状态 | 具体成果 |
|-------|---------|---------|
| **PlanManagerConfig 扩展** | ✅ 完成 | replan_enabled/max_replan_attempts/replan_strategy/failure_threshold |
| **plan_todo.replan 操作** | ✅ 完成 | 增量(incremental)/全量(full)两种重规划策略 |
| **工具封装闭环** | ✅ 完成 | plan_todo 内部调用 Claude + Extended Thinking |
| **capabilities.yaml 更新** | ✅ 完成 | plan_todo 新增 replan/adaptive_planning 能力 |
| **Re-Plan 测试脚本** | ✅ 完成 | `scripts/test_replan.py` |

### ✨ V4.2.1 核心成就（Code-First + E2E Pipeline）

| 改进项 | 实现状态 | 具体成果 |
|-------|---------|---------|
| **E2EPipelineTracer** | ✅ 完成 | 全链路追踪，输入-处理-输出可视化 |
| **CodeValidator** | ✅ 完成 | 语法/依赖/安全多级验证 |
| **CodeOrchestrator** | ✅ 完成 | 代码生成-验证-执行编排器 |
| **SimpleAgent 集成** | ✅ 完成 | chat() 自动追踪各阶段 |
| **E2E 验证脚本** | ✅ 完成 | `scripts/e2e_code_first_verify.py` |

### ✨ V4.2 核心成就

| 改进项 | 实现状态 | 具体成果 |
|-------|---------|---------|
| **Schema 驱动工具选择** | ✅ 完成 | 优先级：Schema > Plan > Intent |
| **ResultCompactor** | ✅ 完成 | 搜索结果 Context 减少 76.6% |
| **配置驱动精简** | ✅ 完成 | 精简规则在 YAML 中配置 |
| **工具分层** | ✅ 完成 | Level 1/2/3 + cache_stable |
| **状态缓存标记** | ✅ 完成 | `_plan_cache` 明确语义 |

### ✨ V4.0 核心成就

| 改进项 | 实现状态 | 具体成果 |
|-------|---------|---------|
| **Agent 模块化** | ✅ 完成 | 从 1000+ 行拆分为 3 个独立文件 |
| **Context 独立** | ✅ 完成 | Runtime + Conversation 分离 |
| **Tool 层重构** | ✅ 完成 | Selector + Executor + Capability 解耦 |
| **Capability 子包** | ✅ 完成 | Registry/Router/Invocation/SkillLoader 统一管理 |
| **Memory 层级化** | ✅ 完成 | user/ + system/ 分层 |
| **Event 统一** | ✅ 完成 | 6 类事件统一接口 |
| **LLM 多提供商** | ✅ 完成 | Claude/OpenAI/Gemini 支持 |

**关键突破**：
- 🎯 **单一职责原则**：每个模块职责明确，不再有"上帝类"
- 🎯 **依赖注入**：所有依赖通过构造函数注入，易于测试
- 🎯 **配置驱动**：能力定义在 YAML，代码只负责执行
- 🎯 **类型安全**：完整的类型定义和接口规范
- 🎯 **Context Engineering**：基于 Manus 原则优化上下文管理

---

## 🎯 核心理念

### 1. 编排模式（Orchestrator Pattern）

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│   SimpleAgent = 编排者（Orchestrator）                          │
│   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│   • 协调各模块工作                                              │
│   • 不包含业务逻辑                                              │
│   • 不直接调用 LLM                                              │
│                                                                 │
│   独立模块 = 专家（Specialists）                                │
│   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│   • IntentAnalyzer  → 意图分析专家                              │
│   • ToolSelector    → 工具选择专家                              │
│   • ToolExecutor    → 工具执行专家                              │
│   • EventManager    → 事件管理专家                              │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 2. 分层架构（Layered Architecture）

```
┌─────────────────────────────────────────────────────────────────┐
│                      API Layer (FastAPI)                        │
│   routers/chat.py, routers/session.py, routers/health.py       │
└───────────────────────────────┬─────────────────────────────────┘
                                │
┌───────────────────────────────▼─────────────────────────────────┐
│                     Service Layer                               │
│   services/chat_service.py, services/session_service.py        │
└───────────────────────────────┬─────────────────────────────────┘
                                │
┌───────────────────────────────▼─────────────────────────────────┐
│                      Core Layer                                 │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │
│  │ core/agent/ │  │ core/tool/  │  │core/memory/ │             │
│  └─────────────┘  └─────────────┘  └─────────────┘             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │
│  │ core/llm/   │  │core/events/ │  │core/context/│             │
│  └─────────────┘  └─────────────┘  └─────────────┘             │
└───────────────────────────────┬─────────────────────────────────┘
                                │
┌───────────────────────────────▼─────────────────────────────────┐
│                   Infrastructure Layer                          │
│   models/ (SQLAlchemy), config/ (YAML), tools/ (实现)          │
└─────────────────────────────────────────────────────────────────┘
```

### 3. 依赖方向（Dependency Direction）

```
                    ┌─────────────────┐
                    │   SimpleAgent   │
                    └────────┬────────┘
                             │ depends on
        ┌────────────────────┼────────────────────┐
        │                    │                    │
        ▼                    ▼                    ▼
┌───────────────┐    ┌───────────────┐    ┌───────────────┐
│IntentAnalyzer │    │ ToolSelector  │    │ ToolExecutor  │
└───────┬───────┘    └───────┬───────┘    └───────┬───────┘
        │                    │                    │
        │              depends on                 │
        │                    │                    │
        │                    ▼                    │
        │         ┌─────────────────────┐         │
        └────────►│CapabilityRegistry  │◄────────┘
                  └─────────────────────┘
                             │
                             ▼
                  ┌─────────────────────┐
                  │  capabilities.yaml  │
                  └─────────────────────┘
```

---

## 🏗️ 整体架构

### V4.2.2 架构图

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                                 User Request                                     │
└─────────────────────────────────────┬───────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              API Layer (FastAPI)                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐        │
│  │ POST /chat   │  │GET /sessions │  │ POST /confirm│  │ GET /health  │        │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘        │
└─────────────────────────────────────┬───────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              Service Layer                                       │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │                          ChatService                                     │   │
│  │  • 消息持久化（DB）                                                      │   │
│  │  • 会话管理                                                              │   │
│  │  • SSE 事件流                                                            │   │
│  │  • Plan 更新监听                                                         │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │                         SessionService                                   │   │
│  │  • Agent 池管理                                                          │   │
│  │  • Session 生命周期                                                      │   │
│  │  • Redis 事件缓冲                                                        │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────┬───────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                                Core Layer                                        │
│                                                                                  │
│  ┌────────────────────────────────────────────────────────────────────────────┐│
│  │                         core/agent/ (编排层)                                ││
│  │  ┌──────────────────────────────────────────────────────────────────────┐  ││
│  │  │                        SimpleAgent                                    │  ││
│  │  │   • RVR Loop 编排                                                     │  ││
│  │  │   • 模块协调（无业务逻辑）                                            │  ││
│  │  │   • Plan Cache 管理                                                   │  ││
│  │  │   • E2E Pipeline 追踪                                                 │  ││
│  │  └──────────────────────────────────────────────────────────────────────┘  ││
│  │  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐         ││
│  │  │ IntentAnalyzer   │  │     types.py     │  │   factory.py     │         ││
│  │  │  • 意图识别      │  │  • TaskType      │  │  • Schema 驱动   │         ││
│  │  │  • 复杂度判断    │  │  • Complexity    │  │  • 动态初始化    │         ││
│  │  │  • needs_plan    │  │  • IntentResult  │  │  • Prompt→Schema │         ││
│  │  └──────────────────┘  └──────────────────┘  └──────────────────┘         ││
│  └────────────────────────────────────────────────────────────────────────────┘│
│                                                                                  │
│  ┌────────────────────────────────────────────────────────────────────────────┐│
│  │                     core/orchestration/ (编排层)                            ││
│  │  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐         ││
│  │  │ pipeline_tracer  │  │  code_validator  │  │ code_orchestrator│         ││
│  │  │  • E2E 追踪      │  │  • 语法检查      │  │  • 代码生成      │         ││
│  │  │  • 阶段记录      │  │  • 依赖验证      │  │  • 验证执行      │         ││
│  │  │  • 统计报告      │  │  • 安全检查      │  │  • 错误修复      │         ││
│  │  └──────────────────┘  └──────────────────┘  └──────────────────┘         ││
│  └────────────────────────────────────────────────────────────────────────────┘│
│                                                                                  │
│  ┌────────────────────────────────────────────────────────────────────────────┐│
│  │                          core/tool/ (工具层)                                ││
│  │  ┌──────────────────────────────────────────────────────────────────────┐  ││
│  │  │                        ToolSelector                                   │  ││
│  │  │   • Schema 驱动优先                                                   │  ││
│  │  │   • 委托 CapabilityRouter 执行路由                                    │  ││
│  │  │   • 选择优先级：Schema > Plan > Intent                                │  ││
│  │  └──────────────────────────────────────────────────────────────────────┘  ││
│  │  ┌──────────────────────────────────────────────────────────────────────┐  ││
│  │  │                        ToolExecutor                                   │  ││
│  │  │   • 动态加载工具实例                                                  │  ││
│  │  │   • 依赖注入（event_manager, workspace_dir）                          │  ││
│  │  │   • ResultCompactor 自动精简结果                                      │  ││
│  │  └──────────────────────────────────────────────────────────────────────┘  ││
│  │  ┌──────────────────────────────────────────────────────────────────────┐  ││
│  │  │              core/tool/capability/ (能力管理子包)                     │  ││
│  │  │   ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐  │  ││
│  │  │   │  registry.py     │  │   router.py      │  │ invocation.py    │  │  ││
│  │  │   │ (能力注册表)     │  │ (智能路由)       │  │ (调用策略)       │  │  ││
│  │  │   └──────────────────┘  └──────────────────┘  └──────────────────┘  │  ││
│  │  │   ┌──────────────────┐  ┌──────────────────┐                        │  ││
│  │  │   │ skill_loader.py  │  │    types.py      │                        │  ││
│  │  │   │ (Skills加载器)   │  │ (类型定义)       │                        │  ││
│  │  │   └──────────────────┘  └──────────────────┘                        │  ││
│  │  └──────────────────────────────────────────────────────────────────────┘  ││
│  └────────────────────────────────────────────────────────────────────────────┘│
│                                                                                  │
│  ┌────────────────────────────────────────────────────────────────────────────┐│
│  │                        core/memory/ (记忆层)                                ││
│  │                                                                             ││
│  │  ┌───────────────────┐                                                     ││
│  │  │   MemoryManager   │ ← 统一入口                                          ││
│  │  └─────────┬─────────┘                                                     ││
│  │            │                                                                ││
│  │  ┌─────────┴─────────┬─────────────────┬─────────────────┐                 ││
│  │  │                   │                 │                 │                 ││
│  │  ▼                   ▼                 ▼                 ▼                 ││
│  │  ┌─────────┐   ┌───────────┐   ┌───────────┐   ┌───────────┐              ││
│  │  │Working  │   │  user/    │   │  user/    │   │ system/   │              ││
│  │  │Memory   │   │ episodic  │   │   e2b     │   │  skill    │              ││
│  │  │(会话级) │   │ (用户级)  │   │ (用户级)  │   │ (系统级)  │              ││
│  │  └─────────┘   └───────────┘   └───────────┘   └───────────┘              ││
│  │                                                                             ││
│  └────────────────────────────────────────────────────────────────────────────┘│
│                                                                                  │
│  ┌─────────────────────────────┐  ┌─────────────────────────────┐              │
│  │       core/context/         │  │        core/events/         │              │
│  │  ┌───────────────────────┐  │  │  ┌───────────────────────┐  │              │
│  │  │   RuntimeContext      │  │  │  │    EventManager       │  │              │
│  │  │   • Block 状态        │  │  │  │    • session_events   │  │              │
│  │  │   • Stream 累积       │  │  │  │    • message_events   │  │              │
│  │  │   • Turn 管理         │  │  │  │    • content_events   │  │              │
│  │  └───────────────────────┘  │  │  │    • system_events    │  │              │
│  │  ┌───────────────────────┐  │  │  │    • user_events      │  │              │
│  │  │  ConversationContext  │  │  │  │    • conversation_    │  │              │
│  │  │   • Token 计数        │  │  │  │      events           │  │              │
│  │  │   • 历史压缩          │  │  │  └───────────────────────┘  │              │
│  │  └───────────────────────┘  │  └─────────────────────────────┘              │
│  └─────────────────────────────┘                                               │
│                                                                                  │
│  ┌─────────────────────────────┐  ┌─────────────────────────────┐              │
│  │        core/llm/            │  │      core/schemas/          │              │
│  │  ┌───────────────────────┐  │  │  ┌───────────────────────┐  │              │
│  │  │   ClaudeLLMService    │  │  │  │    validator.py       │  │              │
│  │  │   • Stream 支持       │  │  │  │  • AgentSchema        │  │              │
│  │  │   • Tool 格式转换     │  │  │  │  • PlanManagerConfig  │  │              │
│  │  │   • Extended Thinking │  │  │  │  • Re-Plan 配置       │  │              │
│  │  └───────────────────────┘  │  │  └───────────────────────┘  │              │
│  │  ┌─────────┐ ┌─────────┐   │  │                              │              │
│  │  │ OpenAI  │ │ Gemini  │   │  │                              │              │
│  │  └─────────┘ └─────────┘   │  │                              │              │
│  └─────────────────────────────┘  └─────────────────────────────┘              │
│                                                                                  │
└──────────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           Infrastructure Layer                                   │
│                                                                                  │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐                 │
│  │     tools/      │  │     config/     │  │     models/     │                 │
│  │                 │  │                 │  │                 │                 │
│  │ • plan_todo     │  │ • capabilities  │  │ • Conversation  │                 │
│  │   (含 replan)   │  │   .yaml         │  │ • Message       │                 │
│  │ • exa_search    │  │ • routing_rules │  │ • Session       │                 │
│  │ • e2b_sandbox   │  │   .yaml         │  │ • User          │                 │
│  │ • e2b_vibe      │  │                 │  │                 │                 │
│  │ • slidespeak    │  │                 │  │                 │                 │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘                 │
│                                                                                  │
└──────────────────────────────────────────────────────────────────────────────────┘
```

---

## 📦 模块详解

### 1. core/agent/ - 编排层

```
core/agent/
├── __init__.py          # 导出 SimpleAgent, IntentAnalyzer
├── simple_agent.py      # 核心编排器
├── intent_analyzer.py   # 意图分析
├── factory.py           # Schema 驱动的 Agent 工厂
└── types.py             # 类型定义
```

**SimpleAgent 职责**：
```python
class SimpleAgent:
    """
    编排器 - 协调各模块完成任务（无业务逻辑）
    
    不做：
    - ❌ 直接调用 LLM API
    - ❌ 直接执行工具
    - ❌ 业务逻辑判断
    - ❌ 硬编码工具调用规则
    
    只做：
    - ✅ 协调 IntentAnalyzer 分析意图
    - ✅ 协调 ToolSelector 选择工具
    - ✅ 协调 ToolExecutor 执行工具
    - ✅ 管理 RVR 循环
    - ✅ 发射事件到 EventManager
    - ✅ 管理 Plan Cache（_plan_cache）
    - ✅ E2E Pipeline 追踪（E2EPipelineTracer）
    """
```

**IntentAnalyzer 职责**：
```python
class IntentAnalyzer:
    """
    意图分析器
    
    输入: 用户消息列表（包含上下文）
    输出: IntentResult {
        task_type: TaskType,      # 任务类型
        complexity: Complexity,    # 复杂度
        needs_plan: bool,         # 是否需要 Plan
        keywords: List[str]       # 提取的关键词
    }
    
    注意：
    - 不负责 Prompt 选择（由 AgentFactory 在创建时确定）
    - 使用 Haiku 快速分析，支持规则降级
    """
```

**AgentFactory 职责**：
```python
class AgentFactory:
    """
    Schema 驱动的 Agent 工厂
    
    功能：
    - 从 System Prompt 动态生成 Schema
    - 根据 Schema 配置初始化 Agent
    - 支持 Re-Plan 相关配置（PlanManagerConfig）
    """
```

### 2. core/orchestration/ - 编排层（🆕 V4.2.1）

```
core/orchestration/
├── __init__.py           # 统一导出
├── pipeline_tracer.py    # 🆕 E2E Pipeline 追踪器
├── code_validator.py     # 🆕 代码验证器
└── code_orchestrator.py  # 🆕 代码执行编排器
```

**E2EPipelineTracer 职责**：
```python
class E2EPipelineTracer:
    """
    端到端管道追踪器 - 全链路可观测
    
    职责：
    - 追踪 Agent 执行各阶段（意图分析/工具选择/代码执行等）
    - 记录每阶段输入-处理-输出
    - 生成执行报告（耗时/状态/错误）
    - 支持调试和问题定位
    
    使用方式：
        tracer = create_pipeline_tracer(session_id)
        stage = tracer.create_stage("intent_analysis")
        stage.start()
        stage.set_input({"messages": messages})
        # ... 执行处理 ...
        stage.complete({"task_type": "code_generation"})
        tracer.finish()
        print(tracer.to_dict())  # 获取完整报告
    """
```

**CodeValidator 职责**：
```python
class CodeValidator:
    """
    代码验证器 - 多级验证保障
    
    验证流程：
    1. 语法检查 - AST 解析验证
    2. 依赖检查 - import 模块可用性
    3. 安全检查 - 危险操作检测（可选）
    
    返回：ValidationResult
    - is_valid: 是否通过验证
    - errors: 错误列表
    - suggestions: 修复建议
    """
```

**CodeOrchestrator 职责**：
```python
class CodeOrchestrator:
    """
    代码执行编排器 - 代码先行策略
    
    编排流程：
    1. 代码生成（LLM）
    2. 代码验证（CodeValidator）
    3. 代码执行（E2B Sandbox）
    4. 结果验证
    5. 错误修复（自动重试）
    
    设计原则：
    - 参考 Manus/Claude Code 的 Code-First 策略
    - 结构化的代码生成与验证
    - 自动错误修复和重试
    """
```

### 2.5 Re-Plan 机制（🆕 V4.2.2）

**设计理念**：
- Claude 在 RVR 循环中**自主决定**是否调用 replan
- Agent 层**无硬规则**，保持简洁的编排职责
- **工具封装闭环**：plan_todo 内部调用 Claude + Extended Thinking

**架构流程**：
```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                            Re-Plan 决策流程                                      │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  RVR 循环执行中                                                                  │
│      │                                                                           │
│      ▼                                                                           │
│  ┌──────────────────────────────────────────────────────────────────────────┐   │
│  │ 步骤执行 → 更新状态                                                       │   │
│  │   • plan_todo.update_step({step_index, status: "completed|failed"})      │   │
│  └───────────────────────────────────┬──────────────────────────────────────┘   │
│                                      │                                           │
│                                      ▼                                           │
│  ┌──────────────────────────────────────────────────────────────────────────┐   │
│  │ Claude 自主评估（基于 System Prompt 指导）                                │   │
│  │   触发条件：                                                               │   │
│  │   • 多个步骤连续失败                                                       │   │
│  │   • 发现原计划遗漏关键信息                                                 │   │
│  │   • 用户需求发生变化                                                       │   │
│  │   • 执行过程中发现更优方案                                                 │   │
│  └───────────────────────────────────┬──────────────────────────────────────┘   │
│                                      │                                           │
│              ┌───────────────────────┴───────────────────────┐                  │
│              │                                               │                  │
│              ▼                                               ▼                  │
│  ┌──────────────────────────┐               ┌──────────────────────────┐       │
│  │ 继续执行当前计划          │               │ 调用 plan_todo.replan    │       │
│  │ • update_step            │               │ • reason: "失败原因"     │       │
│  │ • 下一步骤               │               │ • strategy: incremental  │       │
│  └──────────────────────────┘               └────────────┬─────────────┘       │
│                                                          │                      │
│                                                          ▼                      │
│                                              ┌──────────────────────────┐       │
│                                              │ plan_todo 内部处理        │       │
│                                              │ • 调用 Claude + Thinking  │       │
│                                              │ • 保留已完成步骤          │       │
│                                              │ • 生成新的剩余步骤        │       │
│                                              │ • 返回新计划              │       │
│                                              └────────────┬─────────────┘       │
│                                                          │                      │
│                                                          ▼                      │
│                                              ┌──────────────────────────┐       │
│                                              │ Agent 更新 plan 缓存     │       │
│                                              │ 继续 RVR 循环            │       │
│                                              └──────────────────────────┘       │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

**PlanManagerConfig 配置**（core/schemas/validator.py）：
```python
class PlanManagerConfig(ComponentConfig):
    """计划管理器配置"""
    
    # 基础配置
    enabled: bool = True
    max_steps: int = 10
    granularity: str = "medium"  # fine/medium/coarse
    
    # 🆕 Re-Plan 配置（V4.2.2）
    replan_enabled: bool = True           # 是否允许重新规划
    max_replan_attempts: int = 2          # 最大重规划次数（0-5）
    replan_strategy: str = "incremental"  # full: 全量 / incremental: 保留已完成
    failure_threshold: float = 0.3        # 失败率阈值（超过时建议重规划）
```

**plan_todo 工具操作**（tools/plan_todo_tool.py）：
```python
# 操作类型
operations = [
    "create_plan",   # 创建计划（调用 Claude + Extended Thinking）
    "update_step",   # 更新步骤状态
    "add_step",      # 动态添加步骤
    "replan",        # 🆕 重新规划（V4.2.2）
    "get_plan",      # 获取当前计划
]

# replan 参数
{
    "operation": "replan",
    "data": {
        "reason": "步骤2失败，CSS框架无法加载",  # 必需
        "strategy": "incremental"                # 可选，默认 incremental
    }
}

# replan 策略
- incremental: 保留已完成步骤，只重新生成剩余步骤
- full: 全量重新生成计划（保存历史记录）
```

### 3. core/tool/ - 工具层

```
core/tool/
├── __init__.py          # 导出 ToolSelector, ToolExecutor
├── selector.py          # 工具选择器
├── executor.py          # 工具执行器
├── result_compactor.py  # 🆕 结果精简器
└── capability/          # ✅ 能力管理子包（已完成重构）
    ├── __init__.py      # 统一导出
    ├── registry.py      # 能力注册表
    ├── router.py        # 智能路由器
    ├── invocation.py    # 调用策略选择器
    ├── skill_loader.py  # Skills 加载器
    └── types.py         # 类型定义
```

**ToolSelector 职责**：
```python
class ToolSelector:
    """
    工具选择器（高层接口）
    
    输入: required_capabilities (如 ["web_search", "ppt_generation"])
    输出: ToolSelectionResult {
        tools: List[Capability],   # 选中的工具
        tool_names: List[str],     # 工具名称
        base_tools: List[str],     # 基础工具
        dynamic_tools: List[str]   # 动态选择的工具
    }
    
    选择策略：
    1. 始终包含基础工具（plan_todo, bash）
    2. 委托 CapabilityRouter 进行智能路由
    3. 自动包含 Skills 依赖的底层工具
    4. 按优先级排序
    """
```

**ToolExecutor 职责**：
```python
class ToolExecutor:
    """
    工具执行器
    
    职责：
    - 动态加载工具实例（从 tools/ 目录）
    - 依赖注入（event_manager, workspace_dir）
    - 执行工具并格式化结果
    - 错误处理和日志记录
    """
```

**✅ capability/ 子包职责**：
```python
# registry.py - 能力注册表
class CapabilityRegistry:
    """
    从 capabilities.yaml 加载并管理所有能力
    - 提供能力查询接口
    - 管理能力元数据
    - 支持 TOOL/SKILL/CUSTOM 类型
    """

# router.py - 智能路由器
class CapabilityRouter:
    """
    基于需求智能选择工具
    - 评分机制（关键词匹配、优先级）
    - 约束检查（API 可用性、网络状态）
    - 返回排序后的推荐列表
    """

# invocation.py - 调用策略选择器
class InvocationSelector:
    """
    选择最优的工具调用方式
    - Direct Tool Call（标准）
    - Code Execution（配置生成）
    - Programmatic Calling（多工具编排）
    - Fine-grained Streaming（大参数）
    - Tool Search（工具数量 >30）
    """

# skill_loader.py - Skills 加载器
class SkillLoader:
    """
    加载和管理 Skills 包
    - 从 skills/library/ 发现 Skills
    - 解析 skill.yaml 元数据
    - 加载 prompt/config/resources
    """
```

### 4. core/memory/ - 记忆层

```
core/memory/
├── __init__.py          # 统一导出
├── base.py              # 基类和类型定义
├── working.py           # WorkingMemory (会话级)
├── manager.py           # MemoryManager (统一入口)
├── user/                # 用户级记忆
│   ├── episodic.py      # 情景记忆（历史总结）
│   ├── e2b.py           # E2B 沙箱记忆
│   └── preference.py    # 用户偏好（预留）
└── system/              # 系统级记忆
    ├── skill.py         # Skill 记忆
    └── cache.py         # 系统缓存（预留）
```

**记忆层级**：
```
┌─────────────────────────────────────────────────────────────────────┐
│                         Memory Hierarchy                             │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  Session Level (会话级)                                              │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│  WorkingMemory                                                       │
│  • messages: 当前对话消息                                            │
│  • tool_calls: 工具调用记录                                          │
│  • metadata: 元数据                                                  │
│  生命周期: session 结束时清除                                         │
│                                                                      │
│  User Level (用户级)                                                 │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│  EpisodicMemory                                                      │
│  • 用户历史总结                                                      │
│  • 长期经验                                                          │
│                                                                      │
│  E2BMemory                                                           │
│  • 临时沙箱会话                                                      │
│  • 持久沙箱（命名）                                                  │
│  • 执行历史                                                          │
│                                                                      │
│  System Level (系统级)                                               │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│  SkillMemory                                                         │
│  • 已加载的 Skills                                                   │
│  • Skill 资源缓存                                                    │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### 5. core/context/ - 上下文层

```
core/context/
├── __init__.py        # 导出 RuntimeContext, Context
├── runtime.py         # 运行时上下文（单次 chat 调用）
└── conversation.py    # 会话上下文（历史管理、压缩）
```

**RuntimeContext 职责**：
```python
@dataclass
class RuntimeContext:
    """
    运行时上下文 - 管理单次 chat() 调用的状态
    
    包含：
    - session_id: 会话 ID
    - block: BlockState (当前输出块状态)
    - stream: StreamAccumulator (流式内容累积)
    - current_turn: 当前轮次
    - completed: 是否完成
    """
```

### 6. core/events/ - 事件层

```
core/events/
├── __init__.py              # 导出 EventManager
├── base.py                  # 基类
├── manager.py               # EventManager (统一入口)
├── session_events.py        # 会话事件
├── message_events.py        # 消息事件
├── content_events.py        # 内容事件（流式）
├── conversation_events.py   # 对话事件
├── user_events.py           # 用户事件
└── system_events.py         # 系统事件
```

**EventManager 职责**：
```python
class EventManager:
    """
    统一事件管理器
    
    子管理器：
    - session: SessionEventManager    # start, end, status
    - message: MessageEventManager    # start, stop, tool_call
    - content: ContentEventManager    # start, delta, stop
    - conversation: ConversationEventManager
    - user: UserEventManager
    - system: SystemEventManager      # plan_update, error
    """
```

### 7. core/llm/ - LLM 层

```
core/llm/
├── __init__.py     # 导出 create_claude_service, etc.
├── base.py         # BaseLLMService
├── claude.py       # ClaudeLLMService
├── openai.py       # OpenAILLMService
└── gemini.py       # GeminiLLMService
```

---

## 🔄 数据流

### RVR 循环数据流

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              RVR Loop 数据流                                     │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  User Input                                                                      │
│      │                                                                           │
│      ▼                                                                           │
│  ┌──────────────────────────────────────────────────────────────────────────┐   │
│  │ 1. Intent Analysis                                                        │   │
│  │    IntentAnalyzer.analyze(messages)  # 使用完整消息列表理解上下文         │   │
│  │    → IntentResult { task_type, complexity, needs_plan }                   │   │
│  └───────────────────────────────────┬──────────────────────────────────────┘   │
│                                      │                                           │
│                                      ▼                                           │
│  ┌──────────────────────────────────────────────────────────────────────────┐   │
│  │ 2. Tool Selection                                                         │   │
│  │    ToolSelector.select(required_capabilities)                             │   │
│  │    → ToolSelectionResult { tools, tool_names }                           │   │
│  └───────────────────────────────────┬──────────────────────────────────────┘   │
│                                      │                                           │
│                                      ▼                                           │
│  ┌──────────────────────────────────────────────────────────────────────────┐   │
│  │ 3. RVR Turn Loop                                                          │   │
│  │    for turn in range(max_turns):                                          │   │
│  │        ┌─────────────────────────────────────────────────────────────┐    │   │
│  │        │ [Read]   ← Plan 状态（如果有）                               │    │   │
│  │        │ [Reason] ← LLM Extended Thinking                             │    │   │
│  │        │ [Act]    ← LLM Tool Calls                                    │    │   │
│  │        │              │                                               │    │   │
│  │        │              ▼                                               │    │   │
│  │        │          ToolExecutor.execute(tool_name, input)             │    │   │
│  │        │              │                                               │    │   │
│  │        │              ▼                                               │    │   │
│  │        │ [Observe] ← Tool Result                                      │    │   │
│  │        │ [Validate] ← 验证结果（在 thinking 中）                      │    │   │
│  │        │ [Write]   ← 更新 Plan 状态                                   │    │   │
│  │        │ [Repeat]  ← if stop_reason == "tool_use"                    │    │   │
│  │        └─────────────────────────────────────────────────────────────┘    │   │
│  └───────────────────────────────────┬──────────────────────────────────────┘   │
│                                      │                                           │
│                                      ▼                                           │
│  ┌──────────────────────────────────────────────────────────────────────────┐   │
│  │ 4. Complete                                                               │   │
│  │    emit_message_stop()                                                    │   │
│  │    → Final Response                                                       │   │
│  └──────────────────────────────────────────────────────────────────────────┘   │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### 事件流

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              Event Flow                                          │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  SimpleAgent                    EventManager                    Frontend         │
│      │                              │                              │             │
│      │  emit_message_start()        │                              │             │
│      │─────────────────────────────►│  message_start               │             │
│      │                              │─────────────────────────────►│             │
│      │                              │                              │             │
│      │  emit_content_start()        │                              │             │
│      │─────────────────────────────►│  content_start (thinking)    │             │
│      │                              │─────────────────────────────►│             │
│      │                              │                              │             │
│      │  emit_content_delta()        │                              │             │
│      │─────────────────────────────►│  content_delta               │             │
│      │         (多次)               │─────────────────────────────►│             │
│      │                              │         (SSE)                │             │
│      │                              │                              │             │
│      │  emit_content_stop()         │                              │             │
│      │─────────────────────────────►│  content_stop                │             │
│      │                              │─────────────────────────────►│             │
│      │                              │                              │             │
│      │  emit_tool_call_start()      │                              │             │
│      │─────────────────────────────►│  tool_call_start             │             │
│      │                              │─────────────────────────────►│             │
│      │                              │                              │             │
│      │  emit_tool_call_complete()   │                              │             │
│      │─────────────────────────────►│  tool_call_complete          │             │
│      │                              │─────────────────────────────►│             │
│      │                              │                              │             │
│      │  emit_plan_update()          │                              │             │
│      │─────────────────────────────►│  plan_update                 │             │
│      │                              │─────────────────────────────►│             │
│      │                              │                              │             │
│      │  emit_message_stop()         │                              │             │
│      │─────────────────────────────►│  message_stop                │             │
│      │                              │─────────────────────────────►│             │
│      │                              │                              │             │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## 📁 文件结构

### V4.0 目录结构

```
zenflux_agent/
│
├── core/                           # 🆕 核心模块（模块化）
│   ├── __init__.py                 # 统一导出
│   │
│   ├── agent/                      # 🆕 Agent 模块
│   │   ├── __init__.py
│   │   ├── simple_agent.py         # 编排器
│   │   ├── intent_analyzer.py      # 意图分析
│   │   └── types.py                # 类型定义
│   │
│   ├── tool/                       # 🆕 工具模块
│   │   ├── __init__.py
│   │   ├── selector.py             # 工具选择器
│   │   ├── executor.py             # 工具执行器
│   │   └── capability/             # ✅ 能力管理子包（已完成）
│   │       ├── __init__.py
│   │       ├── registry.py         # 能力注册表
│   │       ├── router.py           # 智能路由器
│   │       ├── invocation.py       # 调用策略选择
│   │       ├── skill_loader.py     # Skills 加载器
│   │       └── types.py            # 类型定义
│   │
│   ├── memory/                     # 🆕 记忆模块（层级化）
│   │   ├── __init__.py
│   │   ├── base.py                 # 基类
│   │   ├── working.py              # 工作记忆
│   │   ├── manager.py              # 统一管理器
│   │   ├── user/                   # 用户级
│   │   │   ├── episodic.py
│   │   │   ├── e2b.py
│   │   │   └── preference.py
│   │   └── system/                 # 系统级
│   │       ├── skill.py
│   │       └── cache.py
│   │
│   ├── context/                    # 🆕 上下文模块
│   │   ├── __init__.py
│   │   ├── runtime.py              # 运行时上下文
│   │   └── conversation.py         # 会话上下文
│   │
│   ├── events/                     # 事件模块
│   │   ├── __init__.py
│   │   ├── manager.py              # 统一管理器
│   │   ├── session_events.py
│   │   ├── message_events.py
│   │   ├── content_events.py
│   │   ├── conversation_events.py
│   │   ├── user_events.py
│   │   └── system_events.py
│   │
│   ├── llm/                        # LLM 模块
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── claude.py
│   │   ├── openai.py
│   │   └── gemini.py
│   │
│   ├── orchestration/              # 🆕 V4.2.1 编排模块
│   │   ├── __init__.py
│   │   ├── pipeline_tracer.py      # E2E Pipeline 追踪器
│   │   ├── code_validator.py       # 代码验证器
│   │   └── code_orchestrator.py    # 代码执行编排器
│   │
│   ├── schemas/                    # Schema 定义
│   │   ├── __init__.py
│   │   └── validator.py            # 🆕 V4.2.2 含 Re-Plan 配置
│   │
│   ├── capability_registry.py      # ⚠️ 已废弃 → 使用 core.tool.capability
│   ├── capability_router.py        # ⚠️ 已废弃 → 使用 core.tool.capability
│   ├── invocation_selector.py      # ⚠️ 已废弃 → 使用 core.tool.capability
│   └── skills_manager.py           # ⚠️ 已废弃 → 使用 core.tool.capability
│
├── tools/                          # 工具实现
│   ├── __init__.py
│   ├── plan_todo_tool.py           # 🆕 V4.2.2 含 replan 操作
│   ├── exa_search.py               # Exa 搜索
│   ├── e2b_sandbox.py              # E2B 沙箱
│   ├── e2b_vibe_coding.py          # Vibe Coding
│   ├── slidespeak.py               # SlideSpeak
│   └── ...
│
├── services/                       # 服务层
│   ├── chat_service.py             # 聊天服务
│   ├── session_service.py          # 会话服务
│   └── redis_manager.py            # Redis 管理
│
├── routers/                        # API 路由
│   ├── chat.py
│   ├── session.py
│   └── health.py
│
├── models/                         # 数据模型
│   ├── conversation.py
│   ├── message.py
│   ├── session.py
│   └── user.py
│
├── prompts/                        # 提示词
│   ├── universal_prompt.py
│   ├── simple_prompt.py
│   ├── standard_prompt.py
│   └── intent_recognition_prompt.py
│
├── config/                         # 配置
│   ├── capabilities.yaml           # 能力配置（单一数据源）
│   └── routing_rules.yaml          # 路由规则
│
├── skills/                         # Skills 包
│   └── library/
│       ├── slidespeak-generator/
│       └── ...
│
├── scripts/                        # 🆕 测试脚本
│   ├── e2e_code_first_verify.py    # V4.2.1 Code-First 验证
│   ├── e2e_real_query_test.py      # 真实 Query E2E 测试
│   ├── e2e_real_world_test.py      # 真实场景测试
│   ├── e2e_verify_tool_execution.py # 工具执行验证
│   └── test_replan.py              # 🆕 V4.2.2 Re-Plan 测试
│
└── docs/                           # 文档
    ├── 00-ARCHITECTURE-V4.md       # 🆕 本文档
    └── ...
```

---

## 🔮 下一步计划

### ✅ 已完成：core/tool/capability/ 重构

```
✅ 已完成模块化重构（2025-12-30）

原分散模块                        新统一子包
━━━━━━━━━━━━━━━━━━━━━━━━━━      ━━━━━━━━━━━━━━━━━━━━━━━━━━
capability_registry.py    ─┐
capability_router.py      ─┼─→  core/tool/capability/
invocation_selector.py    ─┤       ├── registry.py    ✅
skills_manager.py         ─┘       ├── router.py      ✅
                                   ├── invocation.py  ✅
                                   ├── skill_loader.py✅
                                   └── types.py       ✅

收益：
✅ 统一"能力"概念（Tool | Skill | Custom）
✅ 清晰的模块边界
✅ 完整的类型定义
✅ 易于扩展和测试
```

### 🎯 后续优化方向

1. **清理旧文件**
   - 删除根目录下的旧文件（capability_registry.py 等）
   - 更新所有导入路径为新路径

2. **增强 Memory 系统**
   - 完善 user/episodic.py（历史总结）
   - 实现智能压缩策略

3. **多 LLM 提供商支持**
   - 完善 OpenAI 和 Gemini 适配器
   - 统一接口和错误处理

4. **性能优化**
   - 能力匹配缓存
   - Skills 元数据预加载
   - 并发工具调用

---

## 📊 模块依赖图

```
                              ┌─────────────────┐
                              │   SimpleAgent   │
                              └────────┬────────┘
                                       │
           ┌───────────────────────────┼───────────────────────────┐
           │                           │                           │
           ▼                           ▼                           ▼
    ┌──────────────┐           ┌──────────────┐           ┌──────────────┐
    │IntentAnalyzer│           │ ToolSelector │           │ ToolExecutor │
    └──────┬───────┘           └──────┬───────┘           └──────┬───────┘
           │                          │                          │
           │                          └────────────┬─────────────┘
           │                                       │
           │                                       ▼
           │                          ┌────────────────────────────────┐
           │                          │  core/tool/capability/         │
           │                          │  ┌────────────────────────┐    │
           │                          │  │ CapabilityRegistry     │    │
           │                          │  ├────────────────────────┤    │
           │                          │  │ CapabilityRouter       │    │
           │                          │  ├────────────────────────┤    │
           │                          │  │ InvocationSelector     │    │
           │                          │  ├────────────────────────┤    │
           │                          │  │ SkillLoader            │    │
           │                          │  └────────────────────────┘    │
           │                          └────────────┬───────────────────┘
           │                                       │
           │                                       ▼
           │                          ┌───────────────────────┐
           │                          │  capabilities.yaml    │
           │                          └───────────────────────┘
           │
           │         ┌────────────────────────────────────────────┐
           │         │                                            │
           ▼         ▼                                            ▼
    ┌──────────────────────┐                            ┌──────────────┐
    │  ClaudeLLMService    │                            │ EventManager │
    │  (Haiku for intent)  │                            └──────────────┘
    └──────────────────────┘

图例：
─────▶  依赖方向
🔲      模块边界
```

---

## 🧹 清理计划

### 待删除的旧文件

```bash
# 以下文件已废弃，应当删除：

# 1. 旧架构文档（已被 V4.0 替代）
docs/00-ARCHITECTURE-OVERVIEW.md

# 2. 旧模块文件（已移至 core/tool/capability/）
core/capability_registry.py
core/capability_router.py
core/invocation_selector.py
core/skills_manager.py

# 3. 其他废弃文件
core/agent_old.py              # 旧版 Agent
```

### 迁移指南

如果代码中仍在使用旧的导入路径，请更新为：

```python
# ❌ 旧导入（已废弃）
from core.capability_registry import CapabilityRegistry
from core.capability_router import CapabilityRouter
from core.invocation_selector import InvocationSelector
from core.skills_manager import SkillsManager

# ✅ 新导入（推荐）
from core.tool.capability import (
    CapabilityRegistry,
    CapabilityRouter,
    InvocationSelector,
    SkillLoader  # 原 SkillsManager
)
```

---

## 🔗 相关文档

| 文档 | 说明 | 状态 |
|------|------|------|
| [00-ARCHITECTURE-OVERVIEW.md](./00-ARCHITECTURE-OVERVIEW.md) | V3.7 架构（旧版） | ⚠️ 待删除 |
| [ARCHITECTURE_V3.7_E2B.md](./ARCHITECTURE_V3.7_E2B.md) | V3.7+E2B 详细架构 | 📦 归档 |
| [01-MEMORY-PROTOCOL.md](./01-MEMORY-PROTOCOL.md) | Memory Protocol | ✅ 有效 |
| [02-CAPABILITY-ROUTING.md](./02-CAPABILITY-ROUTING.md) | 能力路由 | 🔄 待更新（V4） |
| [03-EVENT-PROTOCOL.md](./03-EVENT-PROTOCOL.md) | 统一事件协议（SSE/WebSocket） | ✅ 有效 |
| [08-DATA_STORAGE_ARCHITECTURE.md](./08-DATA_STORAGE_ARCHITECTURE.md) | 数据存储 | ✅ 有效 |
| [12-CONTEXT_ENGINEERING_OPTIMIZATION.md](./12-CONTEXT_ENGINEERING_OPTIMIZATION.md) | Context Engineering 优化 | ✅ V4.1 |
| [RESULT_COMPACTOR_IMPLEMENTATION.md](./RESULT_COMPACTOR_IMPLEMENTATION.md) | ResultCompactor 实施 | ✅ V4.1 |

