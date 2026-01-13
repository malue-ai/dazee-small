# ZenFlux Agent V6.1 架构文档

> 📅 **最后更新**: 2026-01-13  
> 🎯 **当前版本**: V6.1 - Prompt-Driven Agent Instantiation + 场景化提示词分解  
> 🔗 **历史版本**: 已归档至 [`archived/`](./archived/) 目录  
> ✅ **架构状态**: 生产就绪，端到端验证通过  
> 📝 **待扩展**: Multi-Agent 编排（代码已预留，暂未启用）

---

## 📋 目录

- [版本概述](#版本概述)
- [核心设计原则](#核心设计原则)
- [整体架构](#整体架构)
  - [启动阶段](#启动阶段)
  - [运行阶段](#运行阶段)
- [核心组件](#核心组件)
  - [SimpleAgent（编排层）](#simpleagent编排层)
  - [InstancePromptCache（提示词缓存）](#instancepromptcache提示词缓存)
  - [PromptResultsWriter（提示词输出管理）](#promptresultswriter提示词输出管理)
  - [IntentAnalyzer（意图识别）](#intentanalyzer意图识别)
  - [Memory 系统](#memory-系统)
  - [Events 系统](#events-系统)
  - [Tool 系统](#tool-系统)
  - [Orchestration 系统](#orchestration-系统)
  - [Inference 系统](#inference-系统)
- [API 三层架构](#api-三层架构)
- [目录结构](#目录结构)
- [配置管理](#配置管理)
- [快速验证](#快速验证)

---

## 版本概述

### V6.1 核心特性

V6.1 是 ZenFlux Agent 的**Prompt-Driven Agent Instantiation** 版本，核心架构：

1. **🆕 场景化提示词分解**：运营 `prompt.md` → LLM 分解为 4 个专用提示词
2. **🆕 prompt_results/ 目录**：自动生成，支持运营二次编辑，动态更新检测
3. **🆕 框架规则引导**：`framework_rules.py` 引导 LLM 生成高质量提示词和 Schema
4. **SimpleAgent 单智能体**：用户请求 → Service 层 → SimpleAgent，简洁高效
5. **Prompt-First 原则**：规则写在 Prompt 里，不写在代码里
6. **实例级提示词缓存**：启动时一次性生成所有提示词版本，运行时直接取用

### V6.1 新增功能

#### 1. 场景化提示词分解

```
运营配置的 prompt.md
        │
        ▼ LLM 语义分析 + 分解
        │
        ├─→ intent_prompt.md    （意图识别专用）
        ├─→ simple_prompt.md    （简单任务专用）
        ├─→ medium_prompt.md    （中等任务专用）
        ├─→ complex_prompt.md   （复杂任务专用）
        └─→ agent_schema.yaml   （Agent 配置）
```

**分解原则**：
- **意图识别提示词**：从原始 prompt 提取意图定义、关键词、处理逻辑
- **简单/中等提示词**：精简版本，移除意图相关内容，聚焦任务执行
- **复杂提示词**：优化版本，保留核心规则，去除冗余

#### 2. prompt_results/ 目录

```
instances/my_agent/
├── prompt.md              # 运营编写的原始提示词
├── config.yaml            # 配置文件
└── prompt_results/        # 🆕 框架自动生成
    ├── README.md          # 使用说明
    ├── _metadata.json     # 元数据（哈希、时间戳）
    ├── agent_schema.yaml  # Agent 配置
    ├── intent_prompt.md   # 意图识别提示词
    ├── simple_prompt.md   # 简单任务提示词
    ├── medium_prompt.md   # 中等任务提示词
    └── complex_prompt.md  # 复杂任务提示词
```

**运营可见可编辑**：
- ✅ 所有生成文件均可手动编辑
- ✅ 系统检测手动修改，不会覆盖
- ✅ 删除 `_metadata.json` 可强制重新生成

#### 3. Multi-Agent Mode 配置

```yaml
multi_agent:
  # mode 选项：disabled / auto / enabled
  mode: "disabled"  # 当前版本默认禁用
```

| Mode | 行为 |
|------|------|
| `disabled` | 始终使用 SimpleAgent（推荐） |
| `auto` | LLM 判断是否需要多智能体协作 |
| `enabled` | 始终使用 Multi-Agent 编排 |

### 【待扩展】Multi-Agent 编排

> ⚠️ Multi-Agent 相关代码已预留在 `core/multi_agent/` 目录，当前版本暂未启用。
> 
> 预留功能（未来版本启用）：
> - 任务分解、并行执行、结果聚合
> - FSM 状态机编排
> - 多类型 Worker（AgentWorker、MCPWorker、WorkflowWorker）
> - Service 层路由决策

### 版本演进路线

```
V3.7 (2025-12)    V5.0 (2026-01)    V5.1 (2026-01)    V6.1 (2026-01)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
基础架构         → 实例级缓存       → Mem0 画像增强   → 🔥 场景化提示词分解
能力抽象层       → LLM 语义驱动     → 语义推理模块   → 🔥 prompt_results 输出
E2B 沙箱集成     → Prompt-First    → 工具分层加载   → 🔥 动态更新检测
               → 本地持久化       → HITL 完善      → 🔥 框架规则引导
```

| 维度 | V5.0 | V5.1 | V6.1 |
|------|------|------|------|
| **提示词管理** | 启动时预生成 3 版本 | 复杂度检测器增强 | 🆕 场景化分解 + 运营可编辑 |
| **Schema 生成** | LLM 语义分析 | 统一推理模块 | 🆕 框架规则引导生成 |
| **提示词输出** | 缓存到 `.cache/` | 同上 | 🆕 输出到 `prompt_results/` |
| **动态更新** | 无 | 无 | 🆕 检测源文件变更 + 保护手动编辑 |
| **Multi-Agent** | 代码预留 | 代码预留 | 🆕 mode 配置（disabled/auto/enabled） |

---

## 核心设计原则

### 1. Prompt-Driven Agent Instantiation（V6.1 核心）

```
┌─────────────────────────────────────────────────────────────────────────┐
│                                                                          │
│   核心哲学：运营 prompt.md → LLM 语义分析 → 场景化提示词 + AgentSchema   │
│                                                                          │
│   ┌─────────────────────────────────────────────────────────────────┐   │
│   │                    运营配置 (prompt.md)                          │   │
│   │  • 角色定义：你是 XX 领域专家                                    │   │
│   │  • 意图定义：意图1-4，关键词，处理逻辑                           │   │
│   │  • 工作规则：回复格式，卡片要求                                  │   │
│   │  • 边界限制：不应该做什么                                        │   │
│   └──────────────────────────┬──────────────────────────────────────┘   │
│                              │                                          │
│                              ▼ LLM 语义分析 + 分解                      │
│                              │                                          │
│   ┌──────────────────────────┼──────────────────────────────────────┐   │
│   │                  prompt_results/ 目录                            │   │
│   │                                                                  │   │
│   │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌────────────┐│   │
│   │  │intent_prompt│ │simple_prompt│ │medium_prompt│ │complex_    ││   │
│   │  │.md          │ │.md          │ │.md          │ │prompt.md   ││   │
│   │  │             │ │             │ │             │ │            ││   │
│   │  │意图识别专用 │ │简单任务     │ │中等任务     │ │复杂任务    ││   │
│   │  │提取意图定义 │ │精简版本     │ │标准版本     │ │优化完整版  ││   │
│   │  └─────────────┘ └─────────────┘ └─────────────┘ └────────────┘│   │
│   │                                                                  │   │
│   │  ┌─────────────────────────────────────────────────────────────┐│   │
│   │  │ agent_schema.yaml                                           ││   │
│   │  │ • 组件启用：intent_analyzer, plan_manager, memory_manager  ││   │
│   │  │ • 工具配置：enabled_capabilities, mcp_tools                ││   │
│   │  │ • 运行参数：max_turns, model, temperature                  ││   │
│   │  └─────────────────────────────────────────────────────────────┘│   │
│   └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│   运营可见可编辑：直接修改 prompt_results/ 中的文件，下次启动生效        │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2. Prompt-First 原则

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│   核心哲学：规则写在 Prompt 里，不写在代码里                     │
│                                                                 │
│   ❌ V4.6 代码硬编码规则（泛化能力极差）：                       │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │ if "excel" in prompt_lower:                             │   │
│   │     skills.append("xlsx")  # 只能识别关键词              │   │
│   │ if "ppt" in prompt_lower:                               │   │
│   │     skills.append("pptx")  # 无法理解业务意图            │   │
│   └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│   ✅ V6.1 LLM 语义分解（强泛化能力）：                          │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │ 运营 prompt.md 定义意图：                                │   │
│   │ "意图1: 简单问候 - keywords: 你好,hi - 直接回复"         │   │
│   │                                                         │   │
│   │ LLM 分解后的 intent_prompt.md：                         │   │
│   │ • 提取所有意图定义                                       │   │
│   │ • 生成结构化分类逻辑                                     │   │
│   │ • 保留关键词和处理规则                                   │   │
│   └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│   维护方式：修改 prompt.md 即可，框架自动重新分解               │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 3. 用空间换时间原则

| 阶段 | 开销 | 频率 | 优化收益 |
|------|------|------|---------|
| 启动时 LLM 分解 | ~3-5分钟（首次）| 一次 | 换取运行时零开销 |
| 启动时加载缓存 | <100ms | 每次启动 | 快速启动 |
| 运行时取缓存 | <1ms | 每次请求 | 节省 ~500ms/请求 |

### 4. Memory-First Protocol

```
┌─────────────────────────────────────────────────────────────┐
│   核心理念：始终从持久化存储读取，而非依赖 Context Window   │
│                                                             │
│   ✅ ALWAYS read from plan_memory.get_plan()                │
│   ✅ ALWAYS write to plan_memory.update_step()              │
│   ✅ Mem0 用户画像自动注入（V4.5+）                         │
│   ✅ 智能记忆检索决策（V4.6+）                              │
│   ❌ NEVER trust thinking memory                            │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**参考来源**：
- [Claude Platform Memory Tool](https://docs.anthropic.com/claude/docs/memory)
- [Mem0 论文: Scalable Long-Term Memory](https://arxiv.org/abs/2504.19413)

---

## 整体架构

### 系统架构图

```
┌──────────────────────────────────────────────────────────────────────────┐
│                         ZenFlux Agent V6.1                                │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                           │
│  ┌─────────────────────────────────────────────────────────────────────┐ │
│  │                     协议入口层（平级）                               │ │
│  │  ┌──────────────┐              ┌──────────────┐                     │ │
│  │  │  routers/    │  HTTP        │  grpc_server/│  gRPC               │ │
│  │  │  (FastAPI)   │ ◄──────      │  (gRPC)      │ ◄──────             │ │
│  │  └──────┬───────┘              └──────┬───────┘                     │ │
│  │         │                             │                              │ │
│  │         └─────────────┬───────────────┘                              │ │
│  │                       ▼                                              │ │
│  │  ┌─────────────────────────────────────────────────────────────┐    │ │
│  │  │              services/ 业务逻辑层                            │    │ │
│  │  │  • chat_service.py  ← 直接调用 SimpleAgent                  │    │ │
│  │  │  • conversation_service.py                                  │    │ │
│  │  │  • mem0_service.py                                          │    │ │
│  │  └────────────────────┬────────────────────────────────────────┘    │ │
│  └─────────────────────────────────────────────────────────────────────┘ │
│                                │                                          │
│                                ▼                                          │
│  ┌──────────────────────────────────────────────────────────────────────┐│
│  │                    SimpleAgent（单智能体）                            ││
│  │  ┌─────────────────────────┐  ┌───────────────────────────────────┐ ││
│  │  │InstancePromptCache      │  │ IntentAnalyzer（意图识别）         │ ││
│  │  │ • intent_prompt         │  │ • 使用 intent_prompt.md            │ ││
│  │  │ • simple/medium/complex │  │ • 任务复杂度判断                   │ ││
│  │  │ • agent_schema          │  │ • 是否跳过记忆检索                 │ ││
│  │  └─────────────────────────┘  └───────────────────────────────────┘ ││
│  │  ┌─────────────────────────┐  ┌───────────────────────────────────┐ ││
│  │  │PromptResultsWriter      │  │ ContextManager                     │ ││
│  │  │ • 输出到 prompt_results/│  │ EventManager                       │ ││
│  │  │ • 动态更新检测          │  │                                    │ ││
│  │  └─────────────────────────┘  └───────────────────────────────────┘ ││
│  │                                                                       ││
│  │  职责：RVR 循环（Read-Reason-Act-Observe-Validate-Write）            ││
│  └──────────────────────────────────────────────────────────────────────┘│
│                                │                                          │
│  ┌──────────────────────────────────────────────────────────────────────┐│
│  │                      Memory 三层系统                                  ││
│  │  ┌──────────────────────────────────────────────────────────────────┐││
│  │  │ 会话级：WorkingMemory（messages/plan/tool_calls）                │││
│  │  └──────────────────────────────────────────────────────────────────┘││
│  │  ┌──────────────────────────────────────────────────────────────────┐││
│  │  │ 用户级：Episodic/Preference/Plan/E2B/Mem0                       │││
│  │  └──────────────────────────────────────────────────────────────────┘││
│  │  ┌──────────────────────────────────────────────────────────────────┐││
│  │  │ 系统级：Skill（注册表）• Cache（系统缓存）                       │││
│  │  └──────────────────────────────────────────────────────────────────┘││
│  └──────────────────────────────────────────────────────────────────────┘│
│                                │                                          │
│                                ▼                                          │
│  ┌──────────────────────────────────────────────────────────────────────┐│
│  │                      Tool 执行层                                      ││
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐                 ││
│  │  │ MCP Tools│ │ E2B      │ │ Skills   │ │ Built-in │                 ││
│  │  │ (Dify等) │ │ Sandbox  │ │ (SKILL.md)│ │ Tools    │                 ││
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘                 ││
│  └──────────────────────────────────────────────────────────────────────┘│
│                                                                           │
└──────────────────────────────────────────────────────────────────────────┘
```

### 启动阶段（V6.1 场景化分解）

```
启动阶段流程（首次 3-5 分钟，后续 <100ms）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

instances/my_agent/
├── prompt.md        ─────────┐
├── config.yaml               │
└── .env                      ▼
                ┌────────────────────┐
                │ instance_loader.py │
                └─────────┬──────────┘
                          │
                          ▼
        ┌─────────────────────────────────────────────────┐
        │      InstancePromptCache.load_once()             │
        │                                                  │
        │  1. 检查 prompt_results/ 是否存在且有效         │
        │     → 有效：直接加载（<100ms）                   │
        │     → 无效/不存在：进入 LLM 分解流程            │
        └────────────────────┬────────────────────────────┘
                             │
            ┌────────────────┼────────────────┐
            │                │                │
            ▼                ▼                ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│ Step 1: Schema  │ │ Step 2: Intent  │ │ Step 3-5:       │
│ 生成 AgentSchema│ │ 生成意图提示词  │ │ Simple/Medium/  │
│ (LLM 推断配置)  │ │ (提取意图定义)  │ │ Complex 提示词  │
└────────┬────────┘ └────────┬────────┘ └────────┬────────┘
         │                   │                   │
         └───────────────────┼───────────────────┘
                             ▼
        ┌─────────────────────────────────────────────────┐
        │         PromptResultsWriter 输出                 │
        │                                                  │
        │  prompt_results/                                 │
        │  ├── _metadata.json    # 哈希、时间戳           │
        │  ├── agent_schema.yaml # Agent 配置             │
        │  ├── intent_prompt.md  # 意图识别               │
        │  ├── simple_prompt.md  # 简单任务               │
        │  ├── medium_prompt.md  # 中等任务               │
        │  └── complex_prompt.md # 复杂任务               │
        └────────────────────┬────────────────────────────┘
                             │
                             ▼
        ┌─────────────────────────────────────────────────┐
        │        InstancePromptCache（内存缓存）           │
        │  • system_prompt_simple/medium/complex           │
        │  • intent_prompt                                 │
        │  • agent_schema                                  │
        │  • prompt_schema                                 │
        └─────────────────────────────────────────────────┘

关键产出：
• AgentSchema：Agent 配置（工具、Skills、组件开关、运行参数）
• 4 个场景化提示词：Intent/Simple/Medium/Complex
• 所有输出保存到 prompt_results/ 目录，运营可见可编辑
```

**代码入口**：`scripts/instance_loader.py` → `create_agent_from_instance()`

```python
# 启动时一次性加载（核心代码）
from core.prompt import load_instance_cache

prompt_cache = await load_instance_cache(
    instance_name=instance_name,
    raw_prompt=instance_prompt,
    config=config.raw_config,
    force_refresh=False  # 优先加载已生成的 prompt_results
)
```

### 动态更新检测（V6.1 新增）

```
动态更新检测流程
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

                    启动时检测
                         │
                         ▼
        ┌─────────────────────────────────────────────────┐
        │     比较源文件哈希 vs _metadata.json            │
        │                                                  │
        │     prompt.md 哈希变化？                         │
        │     config.yaml 哈希变化？                       │
        └────────────────────┬────────────────────────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
         无变化         有变化         有变化
              │              │              │
              ▼              ▼              ▼
        ┌───────────┐ ┌───────────────────────────────────┐
        │直接加载   │ │ 检查每个文件是否被手动编辑         │
        │prompt_    │ │                                    │
        │results/   │ │ intent_prompt.md 的哈希 ≠ 记录值？ │
        │           │ │ → 是：保留（手动编辑过）           │
        │           │ │ → 否：重新生成                     │
        └───────────┘ └───────────────────────────────────┘

规则：
• 未编辑的文件：源文件变更时自动更新
• 手动编辑的文件：保留用户版本，不覆盖
• 强制重新生成：删除 _metadata.json 或使用 --force-refresh
```

### 运行阶段

```
运行阶段流程（每次请求，毫秒级）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

用户请求: "帮我生成一个产品介绍 PPT"
            │
            ▼
┌───────────────────────────────────────────────────────────┐
│ Phase 1: 意图识别（Haiku，快速+便宜）                       │
├───────────────────────────────────────────────────────────┤
│ IntentAnalyzer._get_intent_prompt()                       │
│   → _prompt_cache.get_intent_prompt()  ◄─ 从 prompt_results│
│   → LLM (Haiku)                                           │
│                                                           │
│ 输出：IntentResult                                         │
│   • task_type: content_generation                         │
│   • complexity: COMPLEX                                   │
│   • needs_plan: true                                      │
│   • skip_memory_retrieval: false                          │
└───────────────────────────────────────────────────────────┘
            │
            ▼
┌───────────────────────────────────────────────────────────┐
│ Phase 2: 记忆检索（按需检索）                               │
├───────────────────────────────────────────────────────────┤
│ if not skip_memory_retrieval:                             │
│   → Mem0.search(user_id, query)                           │
│   → 获取用户画像和偏好                                     │
│ else:                                                     │
│   → 跳过检索（节省 ~200ms）                                │
└───────────────────────────────────────────────────────────┘
            │
            ▼
┌───────────────────────────────────────────────────────────┐
│ Phase 3: 系统提示词组装                                     │
├───────────────────────────────────────────────────────────┤
│ _prompt_cache.get_system_prompt(complexity)               │
│   → complex_prompt.md  ◄─ 从 prompt_results 加载          │
│                                                           │
│ 注入：                                                     │
│   • 用户画像（如果检索了 Mem0）                            │
│   • Skills 元数据                                          │
│   • 能力分类描述                                           │
└───────────────────────────────────────────────────────────┘
            │
            ▼
┌───────────────────────────────────────────────────────────┐
│ Phase 4: RVR 循环执行（Sonnet，强+准确）                    │
├───────────────────────────────────────────────────────────┤
│ for turn in range(max_turns):                             │
│   [Read]   → plan_memory.get_plan()                       │
│   [Reason] → LLM Extended Thinking                        │
│   [Act]    → Tool Execution                               │
│   [Observe]→ 观察结果                                      │
│   [Validate]→验证质量                                      │
│   [Write]  → plan_memory.update_step()                    │
│                                                           │
│ 性能优势：                                                 │
│   • 意图提示词：0ms（从 prompt_results 取）                │
│   • 系统提示词：0ms（从 prompt_results 取）                │
│   • 总节省：~500ms/请求                                    │
└───────────────────────────────────────────────────────────┘
```

---

## 核心组件

### SimpleAgent（编排层）

**文件**：`core/agent/simple_agent.py`

**职责**：
- 只做编排（Orchestrator），不包含业务逻辑
- 协调各个独立模块完成任务
- 实现 RVR（Read-Reason-Act-Observe-Validate-Write）循环

```python
class SimpleAgent:
    """
    精简版 Agent - 编排层
    
    设计哲学：System Prompt → Schema → Agent
    - System Prompt 定义 Agent 的行为规范和能力边界
    - Schema 配置组件的启用状态和参数
    - Agent 根据 Schema 动态初始化组件
    """
    
    def __init__(
        self,
        model: str = "claude-sonnet-4-5-20250929",
        max_turns: int = 20,
        event_manager=None,
        schema=None,  # AgentSchema 配置
        system_prompt: str = None,
        prompt_cache=None  # V6.1: InstancePromptCache
    ):
        """初始化 Agent"""
        self.model = model
        self.max_turns = max_turns
        self.event_manager = event_manager
        self.schema = schema
        self._prompt_cache = prompt_cache  # V6.1 核心
        
        # 初始化子组件
        self.intent_analyzer = create_intent_analyzer(prompt_cache)
        self.tool_selector = create_tool_selector()
        self.tool_executor = create_tool_executor()
        self.context_manager = create_context_engineering_manager()
        
    async def chat(
        self, 
        user_input: str, 
        session_id: str = None
    ) -> AsyncGenerator[Dict, None]:
        """
        处理用户输入（流式返回）
        
        流程：
        1. 意图识别（使用 intent_prompt.md）
        2. 记忆检索（Mem0，按需）
        3. 系统提示词组装（从 prompt_results 取）
        4. RVR 循环执行
        """
        # 1. 意图识别（使用 prompt_results 中的 intent_prompt）
        intent = await self.intent_analyzer.analyze(user_input)
        
        # 2. 记忆检索（智能决策）
        user_profile = None
        if not intent.skip_memory_retrieval:
            user_profile = await self._fetch_user_profile(user_id)
        
        # 3. 系统提示词组装（V6.1 从 prompt_results 取）
        if self._prompt_cache and self._prompt_cache.is_loaded:
            system_prompt = self._prompt_cache.get_system_prompt(
                intent.complexity
            )
        
        # 4. RVR 循环执行
        async for event in self._rvr_loop(
            user_input, 
            system_prompt,
            user_profile
        ):
            yield event
```

**关键改进（V6.1）**：
- ✅ 从 `prompt_results/` 加载场景化提示词
- ✅ 意图识别使用专用的 `intent_prompt.md`
- ✅ 根据复杂度选择 `simple/medium/complex_prompt.md`

### InstancePromptCache（提示词缓存）

**文件**：`core/prompt/instance_cache.py`

**职责**：
- 实例启动时一次性加载所有提示词版本
- 运行时提供毫秒级的提示词访问
- **V6.1：场景化提示词分解 + prompt_results 输出**

```python
class InstancePromptCache:
    """
    实例级提示词缓存管理器（单例模式）
    
    V6.1 核心改进：
    - 5 步分解流程生成场景化提示词
    - 输出到 prompt_results/ 目录
    - 动态更新检测
    """
    
    # 单例存储
    _instances: Dict[str, "InstancePromptCache"] = {}
    
    @classmethod
    def get_instance(cls, instance_name: str):
        """获取实例缓存（单例）"""
        if instance_name not in cls._instances:
            cls._instances[instance_name] = cls(instance_name)
        return cls._instances[instance_name]
    
    async def load_once(
        self, 
        raw_prompt: str, 
        config=None, 
        force_refresh=False,
        instance_dir: Path = None  # V6.1: 实例目录
    ):
        """
        一次性加载（幂等）
        
        V6.1 流程：
        1. 检查 prompt_results/ 是否有效
        2. 有效 → 直接加载（<100ms）
        3. 无效 → 5 步 LLM 分解（3-5分钟）→ 写入 prompt_results/
        """
        self.results_writer = PromptResultsWriter(instance_dir)
        
        # 尝试从 prompt_results 加载
        if not force_refresh:
            if await self._try_load_from_prompt_results():
                return
        
        # LLM 5 步分解流程
        await self._generate_decomposed_prompts(raw_prompt, config)
        
        # 输出到 prompt_results/
        await self.results_writer.write_all(
            agent_schema=self.agent_schema,
            intent_prompt=self.intent_prompt,
            simple_prompt=self.system_prompt_simple,
            medium_prompt=self.system_prompt_medium,
            complex_prompt=self.system_prompt_complex
        )
    
    async def _generate_decomposed_prompts(self, raw_prompt: str, config):
        """
        V6.1 核心：5 步 LLM 分解流程
        """
        logger.info("🔄 开始 5 步 LLM 分解流程...")
        
        # Step 1: 生成 AgentSchema
        await self._generate_agent_schema(raw_prompt, config)
        
        # Step 2: 生成意图识别提示词
        await self._generate_intent_prompt_decomposed(raw_prompt)
        
        # Step 3: 生成简单任务提示词
        await self._generate_simple_prompt_decomposed(raw_prompt)
        
        # Step 4: 生成中等任务提示词
        await self._generate_medium_prompt_decomposed(raw_prompt)
        
        # Step 5: 生成复杂任务提示词
        await self._generate_complex_prompt_decomposed(raw_prompt)
        
        logger.info("✅ 5 步分解流程完成")
    
    def get_system_prompt(self, complexity: TaskComplexity) -> str:
        """获取对应复杂度的系统提示词"""
        if complexity == TaskComplexity.SIMPLE:
            return self.system_prompt_simple
        elif complexity == TaskComplexity.MEDIUM:
            return self.system_prompt_medium
        else:
            return self.system_prompt_complex
    
    def get_intent_prompt(self) -> str:
        """获取意图识别提示词"""
        return self.intent_prompt
```

### PromptResultsWriter（提示词输出管理）

**文件**：`core/prompt/prompt_results_writer.py`（V6.1 新增）

**职责**：
- 管理 `prompt_results/` 目录的读写
- 元数据管理（哈希、时间戳）
- 动态更新检测（保护手动编辑的文件）

```python
class PromptResultsWriter:
    """
    提示词结果输出管理器
    
    功能：
    - 输出生成的提示词到 prompt_results/ 目录
    - 管理 _metadata.json（源文件哈希、生成时间）
    - 检测手动编辑，保护用户修改
    """
    
    def __init__(self, instance_dir: Path):
        self.instance_dir = instance_dir
        self.results_dir = instance_dir / "prompt_results"
    
    async def write_all(
        self,
        agent_schema: dict,
        intent_prompt: str,
        simple_prompt: str,
        medium_prompt: str,
        complex_prompt: str
    ):
        """写入所有生成的文件"""
        await self._ensure_results_dir()
        
        # 写入各文件
        await self._write_file("agent_schema.yaml", yaml.dump(agent_schema))
        await self._write_file("intent_prompt.md", intent_prompt)
        await self._write_file("simple_prompt.md", simple_prompt)
        await self._write_file("medium_prompt.md", medium_prompt)
        await self._write_file("complex_prompt.md", complex_prompt)
        
        # 更新元数据
        await self._write_metadata()
        
        # 写入 README
        await self._write_readme()
    
    async def check_needs_update(self, source_hash: str) -> Dict[str, bool]:
        """
        检查哪些文件需要更新
        
        返回：{"intent_prompt": True, "simple_prompt": False, ...}
        - True: 需要重新生成（源文件变更且未手动编辑）
        - False: 不需要更新（已手动编辑，保护用户修改）
        """
        metadata = await self._load_metadata()
        
        if metadata.get("source_hash") != source_hash:
            # 源文件变更，检查每个文件
            return await self._check_each_file(metadata)
        
        return {}  # 无变更
    
    async def _check_each_file(self, metadata: dict) -> Dict[str, bool]:
        """检查每个文件是否被手动编辑"""
        needs_update = {}
        
        for filename in ["intent_prompt.md", "simple_prompt.md", 
                         "medium_prompt.md", "complex_prompt.md"]:
            file_path = self.results_dir / filename
            if file_path.exists():
                current_hash = self._compute_hash(file_path.read_text())
                recorded_hash = metadata.get(f"{filename}_hash")
                
                # 哈希不匹配 = 被手动编辑过
                needs_update[filename] = (current_hash == recorded_hash)
            else:
                needs_update[filename] = True
        
        return needs_update
```

### IntentAnalyzer（意图识别）

**文件**：`core/agent/intent_analyzer.py`

**职责**：
- 快速识别用户意图（使用 Haiku，快+便宜）
- **V6.1：使用 prompt_results 中的 intent_prompt.md**
- 判断任务复杂度（Simple/Medium/Complex）

```python
class IntentAnalyzer:
    """意图分析器"""
    
    def __init__(self, prompt_cache: InstancePromptCache = None):
        self._prompt_cache = prompt_cache
        self.llm = create_claude_service(model="claude-haiku-4-5")
    
    async def analyze(self, user_input: str) -> IntentResult:
        """
        分析用户意图
        
        V6.1 改进：使用 prompt_results 中生成的 intent_prompt.md
        该提示词从运营 prompt.md 提取了：
        - 意图定义（意图1-4）
        - 关键词映射
        - 处理逻辑
        - 特殊路由规则
        """
        # 从 prompt_results 获取意图识别提示词
        intent_prompt = self._get_intent_prompt()
        
        # 使用 Haiku 快速分析
        response = await self.llm.create_message(
            messages=[{"role": "user", "content": user_input}],
            system=intent_prompt
        )
        
        return self._parse_intent_result(response)
    
    def _get_intent_prompt(self) -> str:
        """获取意图识别提示词（V6.1 从 prompt_results 取）"""
        if self._prompt_cache and self._prompt_cache.is_loaded:
            return self._prompt_cache.get_intent_prompt()
        
        # Fallback: 使用默认提示词
        return IntentPromptGenerator.get_default()
```

**意图识别输出**：

```json
{
  "task_type": "content_generation",
  "complexity": "COMPLEX",
  "needs_plan": true,
  "skip_memory_retrieval": false,
  "reasoning": "PPT 生成任务，用户可能有风格偏好"
}
```

### Memory 系统

Memory 系统采用**三层架构**（会话级、用户级、系统级）：

```
Memory 三层架构
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

┌────────────────────────────────────────────────────────┐
│ 会话级（Session Scope）- 当前会话                      │
│ ┌────────────────────────────────────────────────────┐ │
│ │ WorkingMemory                                      │ │
│ │ • messages（消息历史）                              │ │
│ │ • tool_calls（工具调用记录）                       │ │
│ │ • plan_json / todo_md（当前任务计划）             │ │
│ │                                                    │ │
│ │ 生命周期：单个 Session（end_session 后清除）       │ │
│ └────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────┐
│ 用户级（User Scope）- 跨 Session 保留                   │
│ ┌────────────────────────────────────────────────────┐ │
│ │ EpisodicMemory（历史经验）                         │ │
│ │ PreferenceMemory（用户偏好）                       │ │
│ │ PlanMemory（任务计划持久化）                       │ │
│ │ E2BMemory（E2B 沙箱记忆）                          │ │
│ │ Mem0（用户画像，可选）                             │ │
│ └────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────┐
│ 系统级（System Scope）- 全局共享                        │
│ ┌────────────────────────────────────────────────────┐ │
│ │ SkillMemory（Skills 注册表）                       │ │
│ │ CacheMemory（系统缓存）                            │ │
│ └────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────┘
```

**文件结构**：

```
core/memory/
├── manager.py           # MemoryManager（统一入口）
├── working.py           # WorkingMemory
├── user/                # 用户级记忆
│   ├── episodic.py      # EpisodicMemory
│   ├── preference.py    # PreferenceMemory
│   ├── plan.py          # PlanMemory
│   └── e2b.py           # E2BMemory
├── system/              # 系统级记忆
│   ├── skill.py         # SkillMemory
│   └── cache.py         # CacheMemory
└── mem0/                # Mem0 用户画像（可选）
    ├── pool.py
    ├── schemas/         # 多层画像结构
    └── tencent_vectordb.py
```

### Events 系统

**文件**：`core/events/`

**职责**：
- 统一的事件管理和分发
- 支持 SSE 流式输出
- 多平台适配器（ZenO、钉钉、飞书等）

**事件类型**（6 类）：

| 事件类别 | 文件 | 说明 |
|---------|------|------|
| message_events | `message_events.py` | 消息相关事件 |
| content_events | `content_events.py` | 内容生成事件 |
| session_events | `session_events.py` | 会话管理事件 |
| user_events | `user_events.py` | 用户操作事件 |
| system_events | `system_events.py` | 系统状态事件 |
| conversation_events | `conversation_events.py` | 对话流程事件 |

### Tool 系统

**文件**：`core/tool/` + `tools/`

**职责**：
- 工具选择与执行
- MCP 工具集成
- E2B 沙箱支持
- Skills 加载与调用
- 统一工具加载器

```
Tool 系统架构
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

┌────────────────────────────────────────────────────────┐
│              ToolLoader（统一加载器）                   │
│  • 类别化配置展开（sandbox_tools → 9个具体工具）       │
│  • 核心工具自动启用（Level 1）                         │
│  • 三类工具统一注册                                    │
└─────────────────────┬──────────────────────────────────┘
                      │
       ┌──────────────┼──────────────┐
       ▼              ▼              ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│ 通用工具     │ │ MCP 工具     │ │ Claude Skills│
│ (Built-in)   │ │ (Dify 等)    │ │ (SKILL.md)   │
│ • plan_todo  │ │ • text2flow  │ │ • pptx       │
│ • exa_search │ │ • workflow   │ │ • xlsx       │
│ • knowledge  │ │              │ │ • docx       │
└──────────────┘ └──────────────┘ └──────────────┘
```

### Orchestration 系统

**文件**：`core/orchestration/`

**职责**：
- 代码生成、验证、执行的完整编排
- 自动错误恢复与重试
- E2B 沙箱深度集成
- 执行状态追踪

### Inference 系统

**文件**：`core/inference/`

**职责**：
- 统一语义推理模块
- 所有推理通过 LLM 语义完成
- Few-Shot 教会 LLM 推理模式
- 保守 fallback，不做关键词猜测

---

## API 三层架构

V6.1 采用**三层架构**，HTTP 和 gRPC 入口共享业务逻辑：

```
协议入口层（平级）           业务逻辑层（共享）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

routers/ (FastAPI)           services/
├── chat.py          ────┐   ├── chat_service.py
├── conversation.py  ────┼──→├── conversation_service.py
└── mem0_router.py   ────┘   ├── mem0_service.py
                             └── session_service.py
grpc_server/ (gRPC)          ↑
├── chat_servicer.py ────────┘
└── session_servicer.py      （只写一次，被复用）
```

### 层次职责

| 层次 | 职责 | 禁止 |
|------|------|------|
| **routers/** | HTTP 协议处理，调用 Service | ❌ 不写业务逻辑 |
| **grpc_server/** | gRPC 协议处理，调用 Service | ❌ 不写业务逻辑 |
| **services/** | 业务逻辑实现，被两层复用 | ❌ 不处理协议细节 |

---

## 目录结构

```
zenflux_agent/
├── core/                           # 核心组件
│   ├── agent/                      # Agent 模块
│   │   ├── factory.py              # Agent 工厂
│   │   ├── intent_analyzer.py      # 意图分析器
│   │   ├── simple_agent.py         # SimpleAgent（编排层）
│   │   └── types.py                # Agent 类型定义
│   │
│   ├── prompt/                     # 🔥 V6.1 核心模块
│   │   ├── instance_cache.py       # InstancePromptCache（5步分解）
│   │   ├── prompt_results_writer.py# 🆕 V6.1 结果输出管理
│   │   ├── framework_rules.py      # 🆕 V6.1 框架规则定义
│   │   ├── intent_prompt_generator.py  # 意图提示词生成
│   │   ├── prompt_layer.py         # 提示词分层管理
│   │   ├── complexity_detector.py  # 复杂度检测器
│   │   └── llm_analyzer.py         # LLM 提示词语义分析器
│   │
│   ├── inference/                  # 语义推理模块
│   │   └── semantic_inference.py   # 统一语义推理引擎
│   │
│   ├── orchestration/              # 代码编排模块
│   │   ├── code_orchestrator.py    # 代码执行编排器
│   │   ├── code_validator.py       # 代码验证器
│   │   └── pipeline_tracer.py      # 流水线追踪器
│   │
│   ├── memory/                     # Memory 系统
│   │   ├── manager.py              # MemoryManager 统一入口
│   │   ├── working.py              # WorkingMemory
│   │   ├── mem0/                   # Mem0 用户画像
│   │   │   ├── pool.py             # 连接池
│   │   │   ├── schemas/            # 多层画像结构
│   │   │   └── ...
│   │   ├── user/                   # 用户记忆
│   │   └── system/                 # 系统记忆
│   │
│   ├── events/                     # Events 系统
│   │   ├── manager.py              # 事件管理器
│   │   └── adapters/               # 平台适配器
│   │
│   ├── tool/                       # Tool 系统
│   │   ├── executor.py             # 工具执行器
│   │   ├── selector.py             # 工具选择器
│   │   ├── loader.py               # 统一工具加载器
│   │   └── capability/             # 能力系统
│   │
│   ├── llm/                        # LLM 提供商
│   │   ├── base.py                 # LLM 基类
│   │   ├── claude.py               # Claude 服务
│   │   └── ...
│   │
│   ├── multi_agent/                # 【预留】Multi-Agent 编排
│   │   ├── orchestrator.py         # 编排器
│   │   ├── config.py               # 配置
│   │   └── scheduling/             # 调度模块
│   │
│   └── ...
│
├── services/                       # 业务逻辑层
│   ├── chat_service.py             # 聊天服务
│   ├── conversation_service.py     # 对话服务
│   ├── mem0_service.py             # Mem0 服务
│   └── ...
│
├── routers/                        # HTTP 入口（FastAPI）
│   ├── chat.py                     # 聊天路由
│   └── ...
│
├── grpc_server/                    # gRPC 入口
│   ├── server.py                   # gRPC 服务器
│   └── ...
│
├── tools/                          # Built-in 工具
│   └── ...
│
├── skills/                         # Skills 库
│   └── ...
│
├── instances/                      # 🔥 实例配置
│   ├── _template/                  # 实例模板
│   │   ├── prompt.md               # 提示词模板
│   │   ├── config.yaml             # 配置模板
│   │   ├── config_example_full.yaml
│   │   ├── config_example_minimal.yaml
│   │   ├── env.example
│   │   ├── prompt_results/         # 🆕 V6.1 生成结果目录
│   │   │   └── README.md           # 使用说明
│   │   └── workers/                # Workers 配置
│   └── test_agent/                 # 测试实例
│       ├── prompt.md
│       ├── config.yaml
│       ├── prompt_results/         # 🆕 自动生成
│       │   ├── _metadata.json
│       │   ├── agent_schema.yaml
│       │   ├── intent_prompt.md
│       │   ├── simple_prompt.md
│       │   ├── medium_prompt.md
│       │   └── complex_prompt.md
│       └── .cache/                 # 缓存目录
│
├── config/                         # 全局配置
│   ├── capabilities.yaml           # 能力配置
│   ├── llm_config/                 # LLM 配置
│   │   └── profiles.yaml           # 🆕 包含 prompt_decomposer
│   └── storage.yaml                # 存储配置
│
├── scripts/                        # 脚本
│   ├── instance_loader.py          # 实例加载器
│   └── ...
│
├── docs/                           # 文档
│   └── architecture/               # 架构文档
│       ├── 00-ARCHITECTURE-OVERVIEW.md  # 本文档
│       └── archived/               # 历史版本
│
└── ...
```

---

## 配置管理

### 实例配置（`instances/xxx/`）

每个实例独立配置，支持：
- **prompt.md**：运营写的系统提示词（业务规则）
- **config.yaml**：实例配置（工具、记忆、Agent 参数）
- **.env**：环境变量（API Keys）
- **prompt_results/**：V6.1 自动生成的场景化提示词

**示例**：`instances/test_agent/config.yaml`

```yaml
instance:
  name: "test_agent"
  description: "测试智能体"
  version: "1.0.0"

agent:
  model: "claude-sonnet-4-5-20250929"
  max_turns: 20
  plan_manager_enabled: true

# 🆕 V6.1 Multi-Agent 配置
multi_agent:
  # mode 选项：disabled / auto / enabled
  mode: "disabled"  # 当前版本推荐禁用

mcp_tools:
  - name: text2flowchart
    server_url: "https://api.dify.ai/mcp/server/XXX/mcp"
    capability: "document_creation"

memory:
  mem0_enabled: true
  smart_retrieval: true
```

### prompt_results/ 目录（V6.1 新增）

```
instances/my_agent/prompt_results/
├── README.md          # 使用说明
├── _metadata.json     # 元数据
│   {
│     "source_hash": "abc123...",      # prompt.md + config.yaml 哈希
│     "created_at": "2026-01-13T...",
│     "intent_prompt_hash": "def456...",
│     "simple_prompt_hash": "ghi789...",
│     ...
│   }
├── agent_schema.yaml  # Agent 配置（可编辑）
├── intent_prompt.md   # 意图识别提示词（可编辑）
├── simple_prompt.md   # 简单任务提示词（可编辑）
├── medium_prompt.md   # 中等任务提示词（可编辑）
└── complex_prompt.md  # 复杂任务提示词（可编辑）
```

**运营操作指南**：

| 操作 | 方法 |
|------|------|
| 查看生成的提示词 | 直接打开 `prompt_results/` 中的 `.md` 文件 |
| 编辑提示词 | 直接修改文件，下次启动自动生效 |
| 强制重新生成某个文件 | 删除该文件，下次启动重新生成 |
| 强制全部重新生成 | 删除 `_metadata.json` |
| 命令行强制刷新 | `--force-refresh` 参数 |

### 全局配置（`config/`）

全局共享配置：
- **capabilities.yaml**：能力配置（工具注册、分类定义）
- **llm_config/profiles.yaml**：LLM 配置（包含 `prompt_decomposer`）
- **storage.yaml**：存储配置

**LLM Profile 示例**（`config/llm_config/profiles.yaml`）：

```yaml
# V6.1 场景化提示词分解专用
prompt_decomposer:
  description: "将运营 prompt 分解为场景化提示词"
  model: "claude-sonnet-4-5-20250929"
  max_tokens: 60000
  temperature: 0
  enable_thinking: false
  enable_caching: false
  timeout: 300.0  # 5 分钟
  max_retries: 2
```

---

## 快速验证

### 验证 V6.1 场景化分解

```bash
cd /Users/liuyi/Documents/langchain/CoT_agent/mvp/zenflux_agent
source venv/bin/activate

# 首次启动（LLM 分解，3-5分钟）
python scripts/instance_loader.py --instance test_agent --info
```

**预期日志**：

```
⏳ 正在加载实例: test_agent...
📂 实例路径: instances/test_agent
📝 prompt.md 长度: 67890 字符

🔄 开始 5 步 LLM 分解流程...
   Step 1: 生成 AgentSchema...
   ✅ AgentSchema 生成成功
   Step 2: 生成意图识别提示词...
   ✅ 意图识别提示词生成成功，长度: 3500 字符
   Step 3: 生成简单任务提示词...
   ✅ 简单任务提示词生成成功，长度: 8000 字符
   Step 4: 生成中等任务提示词...
   ✅ 中等任务提示词生成成功，长度: 12000 字符
   Step 5: 生成复杂任务提示词...
   ✅ 复杂任务提示词生成成功，长度: 15000 字符
✅ 5 步分解流程完成

📁 已输出到 prompt_results/ 目录
✅ InstancePromptCache 加载完成
```

### 验证 prompt_results 目录

```bash
ls -la instances/test_agent/prompt_results/
# 预期输出：
# README.md
# _metadata.json
# agent_schema.yaml
# intent_prompt.md
# simple_prompt.md
# medium_prompt.md
# complex_prompt.md

# 查看元数据
cat instances/test_agent/prompt_results/_metadata.json
```

### 验证再次启动（从 prompt_results 加载）

```bash
# 再次启动（直接加载，<100ms）
python scripts/instance_loader.py --instance test_agent --info
```

**预期日志**：

```
⏳ 正在加载实例: test_agent...
✅ 从 prompt_results/ 加载: test_agent
   加载耗时: 45ms
✅ InstancePromptCache 加载完成
   Intent: 3500 字符
   Simple: 8000 字符
   Medium: 12000 字符
   Complex: 15000 字符
```

### 验证强制刷新

```bash
# 方式 1：删除元数据
rm instances/test_agent/prompt_results/_metadata.json
python scripts/instance_loader.py --instance test_agent --info

# 方式 2：使用命令行参数
python scripts/instance_loader.py --instance test_agent --force-refresh
```

### 验证 API

```bash
# 测试 HTTP API
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "你好", "session_id": "test"}'
```

---

## 相关文档

| 文档 | 说明 |
|------|------|
| [00-ARCHITECTURE-OVERVIEW.md](./00-ARCHITECTURE-OVERVIEW.md) | V6.1 架构总览（本文档） |
| [15-FRAMEWORK_PROMPT_CONTRACT.md](./15-FRAMEWORK_PROMPT_CONTRACT.md) | Prompt-Driven 设计契约 |
| [archived/](./archived/) | 历史版本（V4.x, V5.x） |
| [01-MEMORY-PROTOCOL.md](./01-MEMORY-PROTOCOL.md) | Memory-First Protocol 详解 |
| [03-EVENT-PROTOCOL.md](./03-EVENT-PROTOCOL.md) | SSE 事件协议 |
| [tool_configuration_guide.md](../tool_configuration_guide.md) | 工具配置指南 |

---

## 版本历史

| 版本 | 日期 | 核心变化 |
|------|------|---------|
| **V6.1** | 2026-01-13 | 🔥 **当前版本**：场景化提示词分解 + prompt_results 输出 + 动态更新检测 |
| V5.1 | 2026-01-11 | Mem0 多层画像 + 工具分层加载 + 语义推理模块 |
| V5.0 | 2026-01-09 | 实例级提示词缓存 + LLM 语义驱动 Schema |
| V4.6 | 2026-01-08 | 智能记忆检索决策 |
| V4.5 | 2026-01-07 | Mem0 用户画像层 |

---

**🎯 架构设计目标**：
- ✅ **Prompt-Driven**：运营 prompt.md → LLM 分解 → 场景化提示词
- ✅ **运营可见可编辑**：prompt_results/ 目录，所有生成文件可直接修改
- ✅ **智能更新**：检测源文件变更，保护手动编辑
- ✅ **简洁清晰**：Service → SimpleAgent 直接调用
- ✅ **Prompt-First**：规则写在 Prompt 里，不写在代码里
- 📝 **预留扩展**：Multi-Agent 代码已预留，通过 mode 配置启用

**📌 维护原则**：
- 架构变更时，只需更新此文档
- 历史版本归档到 `archived/` 目录
- prompt_results/ 中的 README.md 同步更新
