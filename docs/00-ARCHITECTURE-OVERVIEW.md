# Agent V3.7 架构总览

> 📅 **最后更新**: 2025-12-24  
> 🎯 **当前版本**: V3.7 - Dynamic Routing + Abstraction Layer  
> 🔗 **文档索引**: [README.md](./README.md)
> 
> **🆕 V3.7 核心改进**：
> - ✅ 能力抽象层（Capability Abstraction Layer）
> - ✅ 动态工具筛选（Router 真正生效）
> - ✅ 智能调用方式选择（5种调用方式）
> - ✅ 配置驱动（单一数据源原则）

---

## 📋 目录

- [核心理念](#核心理念)
- [整体架构](#整体架构)
- [核心组件](#核心组件)
- [工作流程](#工作流程)
- [文件结构](#文件结构)

---

## 🎯 核心理念

### 1. Prompt-Driven Architecture（提示词驱动）

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│   System Prompt = 大脑（定义所有逻辑规则）                   │
│   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│   • 意图识别规则                                             │
│   • 是否需要 Plan 的判断                                     │
│   • RVR 循环执行                                             │
│   • 最终验证                                                 │
│                                                             │
│   Agent Code = 骨架（框架管理，不含业务规则）                │
│   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│   • 调用 LLM                                                 │
│   • 执行工具                                                 │
│   • 管理 Memory                                              │
│   • 通知进度                                                 │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**关键原则**：
- ❌ Agent 代码中不包含 `if task == "ppt"` 等业务判断
- ✅ 所有逻辑由 System Prompt 定义，LLM 自主决策

### 2. Memory-First Protocol（内存优先）

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│   ⚠️ ASSUME INTERRUPTION                                    │
│   Context window 可能随时 reset                             │
│                                                             │
│   ✅ ALWAYS read from plan_todo.get_plan()                  │
│   ✅ ALWAYS write to plan_todo.update_step()                │
│   ❌ NEVER trust thinking memory                            │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**参考**：Claude Platform Memory Tool

### 3. AGI Framework（通用框架）

```
┌─────────────────────────────────────────────────────────────┐
│                  AGI Framework（稳定层）                     │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│  • 通用，不针对特定任务                                      │
│  • 代码稳定，不频繁修改                                      │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                  Skills（领域知识层）                        │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│  • 可插拔的专业知识包                                        │
│  • 不影响框架核心                                            │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                  Test Cases（验证层）                        │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│  • PPT生成、数据分析、代码审查...                            │
│  • 验证框架通用性                                            │
└─────────────────────────────────────────────────────────────┘
```

### 🆕 4. Capability Abstraction Layer（能力抽象层）

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     两层抽象：解耦 LLM 和工具                            │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  🏷️ 能力分类（8个抽象标签）         🔧 具体工具（12+个实现）            │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━      ━━━━━━━━━━━━━━━━━━━━━━━━            │
│  Sonnet 只需知道：                   Router 负责映射：                   │
│                                                                          │
│  • web_search          ─────────→   exa_search, web_search              │
│  • ppt_generation      ─────────→   slidespeak-generator, pptx          │
│  • file_operations     ─────────→   file_read, file_write, bash         │
│  • data_analysis       ─────────→   xlsx, python                        │
│  • code_execution      ─────────→   bash, code_execution                │
│  • api_calling         ─────────→   slidespeak_render, ...              │
│  • document_creation   ─────────→   docx, pdf                           │
│  • task_planning       ─────────→   plan_todo                           │
│                                                                          │
│  核心收益：                                                              │
│  ✅ Sonnet 不需要知道所有工具（只知道 8 个抽象分类）                    │
│  ✅ 新增工具无需修改 Prompt（只需在 YAML 声明 capabilities）            │
│  ✅ Router 动态筛选工具（从 12 个选 5 个，减少 LLM 选择困难）            │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

**示例**：
```yaml
# capabilities.yaml
capability_categories:
  - id: web_search
    description: "搜索互联网信息"
    
capabilities:
  - name: exa_search
    capabilities: [web_search, semantic_search]  # 映射到分类
  - name: web_search  
    capabilities: [web_search]
```

---

## 🏗️ 整体架构

### 架构图（V3.7 完整版）

```
┌─────────────────────────────────────────────────────────────────────┐
│                           User Query                                │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         SimpleAgent (V3.7)                           │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │                    System Prompt (大脑)                        │  │
│  │  • Intent Recognition Protocol                                │  │
│  │  • Planning Protocol (Memory-First)                           │  │
│  │  • RVR Protocol                                               │  │
│  │  • Final Validation Protocol                                  │  │
│  │  🆕 • 动态注入能力分类（来自 CapabilityRegistry）              │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                                                      │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │                 WorkingMemory (Short Memory)                   │  │
│  │  ┌───────────┐  ┌───────────┐  ┌───────────┐                  │  │
│  │  │ messages  │  │ plan.json │  │  todo.md  │                  │  │
│  │  └───────────┘  └─────↑─────┘  └─────↑─────┘                  │  │
│  │                       │ CRUD         │                         │  │
│  │  ┌────────────────────┴──────────────┴───────────────────────┐│  │
│  │  │                   plan_todo Tool (🆕 动态 Schema)          ││  │
│  │  │  • create_plan → 写入 Memory                              ││  │
│  │  │  • get_plan → 读取 Memory (每步开始)                      ││  │
│  │  │  • update_step → 更新 Memory (每步结束)                   ││  │
│  │  └───────────────────────────────────────────────────────────┘│  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  🆕 CapabilityRegistry (能力注册表)                           │  │
│  │  ┌─────────────────┐                                          │  │
│  │  │capabilities.yaml│ ← 唯一数据源                             │  │
│  │  │  • task_type_mappings (🆕 任务类型映射)                   │  │
│  │  │  • capability_categories (🆕 能力分类)                     │  │
│  │  │  • capabilities (工具/Skills 定义)                        │  │
│  │  └────────┬────────┘                                          │  │
│  │           │ 加载配置                                           │  │
│  │           ▼                                                    │  │
│  │  • get_categories_for_prompt() → System Prompt               │  │
│  │  • get_category_ids() → plan_todo Schema                     │  │
│  │  • get_capabilities_for_task_type() → 能力推断               │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                      │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐ │
│  │  Intent LLM │  │ Execution   │  │ Capability  │  │   Skills    │ │
│  │  (Haiku)    │  │ LLM (Sonnet)│  │   Router    │  │   Manager   │ │
│  │  ━━━━━━━━━  │  │  ━━━━━━━━━  │  │  🆕 真正筛选 │  │             │ │
│  │  快速分类   │  │  深度推理   │  │  工具子集    │  │  Skills发现  │ │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘ │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  🆕 InvocationSelector (调用方式选择器)                       │  │
│  │  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │  │
│  │  select_strategy() - 智能选择：                              │  │
│  │    • Direct Tool Call (单工具+简单参数)                      │  │
│  │    • Code Execution (配置生成/计算逻辑)                      │  │
│  │    • Programmatic Tool Calling (多工具编排>2)                │  │
│  │    • Fine-grained Streaming (大参数>10KB)                    │  │
│  │    • Tool Search (工具数量>30)                               │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                      │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │                      Tool Executor                             │  │
│  │  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐          │  │
│  │  │  bash   │  │web_search│  │plan_todo│  │ custom  │          │  │
│  │  └─────────┘  └─────────┘  └─────────┘  └─────────┘          │  │
│  │  执行筛选后的工具子集（5/12，不是全部）🎯                     │  │
│  └───────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

**V3.7 架构改进标注**：
- 🆕 **CapabilityRegistry**: 统一配置管理，单一数据源
- 🆕 **InvocationSelector**: 5 种调用方式智能选择
- 🆕 **Router 真正生效**: 从观察者变为核心功能（筛选工具子集）
- 🆕 **动态 Schema**: plan_todo 的 enum 自动生成
- 🆕 **能力推断**: task_type → capabilities 统一映射

### 以 Agent 为中心的完整流程图

```
                            👤 用户输入
                                │
                    "帮我生成一个产品PPT"
                                │
                                ▼
        ┌───────────────────────────────────────────────────────────┐
        │                    SimpleAgent 启动                        │
        │  1️⃣ 初始化组件：                                           │
        │     • CapabilityRegistry 加载 capabilities.yaml           │
        │     • 构建 System Prompt（注入能力分类）                   │
        │     • 初始化 Router、Selector、LLM Service                │
        └───────────────────────┬───────────────────────────────────┘
                                │
                                ▼
        ┌───────────────────────────────────────────────────────────┐
        │              阶段 1: Intent Analysis (Haiku)               │
        ├───────────────────────────────────────────────────────────┤
        │  Prompt: Intent Recognition Prompt                        │
        │  Model: claude-haiku-4-5-20251001 (快+便宜)               │
        │                                                            │
        │  Output:                                                   │
        │  {                                                         │
        │    "task_type": "content_generation",                     │
        │    "complexity": "complex",                                │
        │    "needs_plan": true                                      │
        │  }                                                         │
        └───────────────────────┬───────────────────────────────────┘
                                │
                                ▼
        ┌───────────────────────────────────────────────────────────┐
        │           阶段 2: System Prompt 动态组装                   │
        ├───────────────────────────────────────────────────────────┤
        │  🆕 从 CapabilityRegistry 动态注入：                       │
        │                                                            │
        │  Base Prompt (universal_agent_prompt.py)                  │
        │      +                                                     │
        │  🔧 Capability Categories (来自 capabilities.yaml)        │
        │  ┌─────────────────────────────────────────────────────┐  │
        │  │ ## 🏷️ Available Capability Categories              │  │
        │  │ | Category | Description | Use When |                │  │
        │  │ |----------|-------------|----------|                │  │
        │  │ | web_search | 搜索互联网信息 | ... |                │  │
        │  │ | ppt_generation | 生成演示文稿 | ... |              │  │
        │  │ | ... (8 个分类)                                    │  │
        │  └─────────────────────────────────────────────────────┘  │
        │      +                                                     │
        │  Skills Metadata (来自 SkillsManager)                     │
        │                                                            │
        │  → 完整 System Prompt 准备就绪                            │
        └───────────────────────┬───────────────────────────────────┘
                                │
                                ▼
        ┌───────────────────────────────────────────────────────────┐
        │          阶段 3: Plan Creation (Sonnet + Extended Thinking)│
        ├───────────────────────────────────────────────────────────┤
        │  Model: claude-sonnet-4-5-20250929 (强+准确)              │
        │  Tools: [plan_todo] (只传这一个工具)                      │
        │                                                            │
        │  💭 Extended Thinking (内部推理):                          │
        │     "用户要生成产品PPT...需要：                             │
        │      1. 搜索产品信息 → web_search                          │
        │      2. 生成PPT配置 → ppt_generation                       │
        │      3. 渲染PPT → api_calling"                             │
        │                                                            │
        │  🔧 Tool Call: plan_todo.create_plan()                    │
        │  {                                                         │
        │    "operation": "create_plan",                             │
        │    "data": {                                               │
        │      "goal": "生成产品PPT",                                │
        │      "steps": [                                            │
        │        {                                                   │
        │          "action": "搜索产品信息",                         │
        │          "capability": "web_search"  🆕                    │
        │        },                                                  │
        │        {                                                   │
        │          "action": "生成PPT配置",                          │
        │          "capability": "ppt_generation"  🆕                │
        │        }                                                   │
        │      ],                                                    │
        │      "required_capabilities": [                            │
        │        "web_search", "ppt_generation"  🆕                  │
        │      ]                                                     │
        │    }                                                       │
        │  }                                                         │
        │                                                            │
        │  → Plan 存储到 WorkingMemory                              │
        └───────────────────────┬───────────────────────────────────┘
                                │
                                ▼
        ┌───────────────────────────────────────────────────────────┐
        │  📊 用户看到 Todo 进度显示（Markdown 格式）                │
        ├───────────────────────────────────────────────────────────┤
        │  ┌─────────────────────────────────────────────────────┐  │
        │  │ 📋 Todo Progress: 0/2 completed                      │  │
        │  │                                                      │  │
        │  │ 🎯 Goal: 生成产品PPT                                │  │
        │  │                                                      │  │
        │  │ - [ ] 搜索产品信息                                   │  │
        │  │ - [ ] 生成PPT配置                                    │  │
        │  │                                                      │  │
        │  │ [░░░░░░░░░░░░░░░░░░░░] 0%                           │  │
        │  └─────────────────────────────────────────────────────┘  │
        └───────────────────────┬───────────────────────────────────┘
                                │
                                ▼
        ┌───────────────────────────────────────────────────────────┐
        │       阶段 4: Dynamic Tool Selection (Router)              │
        ├───────────────────────────────────────────────────────────┤
        │  Input: plan.required_capabilities                         │
        │    → ["web_search", "ppt_generation"]                      │
        │                                                            │
        │  🔍 Router 查询 capabilities.yaml:                        │
        │                                                            │
        │  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
        │  web_search (分类) → 匹配工具:                             │
        │    • exa_search (priority: 90, type: TOOL) ✅              │
        │    • web_search (priority: 85, type: TOOL) ✅              │
        │                                                            │
        │  📋 选择策略:                                              │
        │    1. 按 priority 排序（90 > 85）                          │
        │    2. 约束检查（API可用性、网络状态）                      │
        │    3. 全部保留，让 LLM 根据场景自主选择                    │
        │       - exa_search: 语义搜索，深度内容                     │
        │       - web_search: 快速搜索，实时信息                     │
        │                                                            │
        │  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
        │  ppt_generation (分类) → 匹配工具:                         │
        │    • slidespeak-generator (priority: 85, CUSTOM) ✅        │
        │    • pptx (priority: 60, PREBUILT) ✅                      │
        │                                                            │
        │  📋 选择策略（多工具竞争场景）:                             │
        │    1. 按 priority 排序（85 > 60）                          │
        │    2. 根据 metadata.preferred_for 进一步区分:              │
        │       • slidespeak-generator → 专业、产品、客户场景        │
        │         ↑ keywords: ["专业", "产品", "业务"]               │
        │       • pptx → 快速、草稿、简单场景                        │
        │         ↑ keywords: ["快速", "草稿", "简单"]               │
        │    3. ✅ 策略: 两个都传给 LLM，由 Sonnet 根据用户意图选择  │
        │       - 用户说"专业的产品PPT" → 选 slidespeak-generator   │
        │       - 用户说"快速做个草稿" → 选 pptx                     │
        │                                                            │
        │  🎯 为什么不在 Router 直接去重？                           │
        │    • LLM (Sonnet) 比规则引擎更智能，能根据上下文选择       │
        │    • 不同工具有不同特点（专业 vs 快速）                    │
        │    • 保留选择余地，适应更多场景                            │
        │                                                            │
        │  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
        │  + 基础工具: plan_todo, bash (总是包含)                    │
        │                                                            │
        │  Output: 筛选后的工具列表 (6/12 = 50%)                    │
        │    按 priority 排序：                                      │
        │    [exa_search(90), slidespeak-generator(85),             │
        │     web_search(85), pptx(60), plan_todo(95), bash(90)]    │
        │                                                            │
        │  📊 筛选效果:                                              │
        │    • 原始工具: 12 个                                       │
        │    • 筛选后: 6 个 (50% 减少)                               │
        │    • LLM 选择困难降低，但保留智能选择空间                  │
        └───────────────────────┬───────────────────────────────────┘
                                │
                                ▼
        ┌───────────────────────────────────────────────────────────┐
        │    阶段 5: Invocation Strategy Selection                   │
        ├───────────────────────────────────────────────────────────┤
        │  InvocationSelector.select_strategy():                    │
        │                                                            │
        │  task_type: "content_generation"                           │
        │  selected_tools: 6 个                                      │
        │  判断: 不是 config_generation，工具数 > 2                 │
        │                                                            │
        │  → Strategy: Programmatic Tool Calling                     │
        │    Reason: "多工具编排，减少往返"                          │
        │    Config: {                                               │
        │      "tools": [...],                                       │
        │      "betas": ["code-execution-2025-05-22"]                │
        │    }                                                       │
        └───────────────────────┬───────────────────────────────────┘
                                │
                                ▼
        ┌───────────────────────────────────────────────────────────┐
        │             阶段 6: RVR Loop (执行步骤)                    │
        ├───────────────────────────────────────────────────────────┤
        │                                                            │
        │  ═══════════════ Turn 1: 执行步骤 1 ═══════════════        │
        │                                                            │
        │  1️⃣ Read: plan_todo.get_plan()                            │
        │     → current_step: "搜索产品信息"                         │
        │                                                            │
        │  2️⃣ Reason: LLM Extended Thinking                         │
        │     "需要搜索产品信息...使用 exa_search"                   │
        │                                                            │
        │  3️⃣ Act: Tool Call                                        │
        │     exa_search({query: "产品名称 功能特点"})               │
        │                                                            │
        │  4️⃣ Observe: 获取搜索结果                                 │
        │     [产品信息、市场数据、功能介绍...]                      │
        │                                                            │
        │  5️⃣ Validate: 验证结果质量                                │
        │     ✅ 信息完整、相关性高                                  │
        │                                                            │
        │  6️⃣ Write: plan_todo.update_step()                        │
        │     → status: "completed", result: "已获取产品信息"        │
        │                                                            │
        │  📊 更新进度显示:                                          │
        │  ┌─────────────────────────────────────────────────────┐  │
        │  │ 📋 Todo Progress: 1/2 completed                      │  │
        │  │                                                      │  │
        │  │ - [x] 搜索产品信息 ✅                                │  │
        │  │ - [ ] 生成PPT配置                                    │  │
        │  │                                                      │  │
        │  │ [██████████░░░░░░░░░] 50%                           │  │
        │  └─────────────────────────────────────────────────────┘  │
        │                                                            │
        │  ═══════════════ Turn 2: 执行步骤 2 ═══════════════        │
        │                                                            │
        │  1️⃣ Read: plan_todo.get_plan()                            │
        │     → current_step: "生成PPT配置"                          │
        │                                                            │
        │  2️⃣ Reason: LLM Extended Thinking                         │
        │     "需要生成SlideSpeak配置...使用code_execution"          │
        │                                                            │
        │  3️⃣ Act: Code Execution (程序化调用)                      │
        │     生成 JSON 配置：                                       │
        │     {                                                      │
        │       "template": "default",                               │
        │       "language": "zh-CN",                                 │
        │       "slides": [...]                                      │
        │     }                                                      │
        │                                                            │
        │  4️⃣ Observe: 配置已生成                                   │
        │                                                            │
        │  5️⃣ Validate: 验证格式                                    │
        │     ✅ JSON 格式正确、字段完整                             │
        │                                                            │
        │  6️⃣ Write: plan_todo.update_step()                        │
        │     → status: "completed"                                  │
        │                                                            │
        │  7️⃣ Act: 调用 slidespeak_render                           │
        │     渲染 PPT → 获得下载链接                                │
        │                                                            │
        │  📊 最终进度:                                              │
        │  ┌─────────────────────────────────────────────────────┐  │
        │  │ 📋 Todo Progress: 2/2 completed                      │  │
        │  │                                                      │  │
        │  │ - [x] 搜索产品信息 ✅                                │  │
        │  │ - [x] 生成PPT配置 ✅                                 │  │
        │  │                                                      │  │
        │  │ [████████████████████] 100%                          │  │
        │  └─────────────────────────────────────────────────────┘  │
        │                                                            │
        │  🎉 RVR Loop 完成                                          │
        └───────────────────────┬───────────────────────────────────┘
                                │
                                ▼
        ┌───────────────────────────────────────────────────────────┐
        │            阶段 7: Final Validation & Output               │
        ├───────────────────────────────────────────────────────────┤
        │  LLM 最终验证:                                             │
        │  ✅ 所有步骤完成                                           │
        │  ✅ PPT 已生成                                             │
        │  ✅ 质量符合要求                                           │
        │                                                            │
        │  Final Output:                                             │
        │  {                                                         │
        │    "status": "success",                                    │
        │    "final_result": {                                       │
        │      "ppt_url": "https://slidespeak.co/download/...",     │
        │      "preview_url": "https://...",                         │
        │      "slide_count": 8                                      │
        │    },                                                      │
        │    "turns": 2,                                             │
        │    "quality_score": 95                                     │
        │  }                                                         │
        └───────────────────────┬───────────────────────────────────┘
                                │
                                ▼
                            👤 用户收到
        ┌───────────────────────────────────────────────────────────┐
        │  ✅ 任务完成！                                             │
        │                                                            │
        │  📄 产品PPT 已生成                                         │
        │  🔗 下载链接: https://slidespeak.co/download/...          │
        │  📊 总计 8 页幻灯片                                        │
        │  ⏱️  用时: 45 秒                                           │
        │  🔧 使用工具: exa_search, code_execution, slidespeak      │
        └───────────────────────────────────────────────────────────┘
```

**流程关键点**：

| 阶段 | 核心动作 | Agent 组件 | 用户可见 |
|-----|---------|-----------|---------|
| 1️⃣ Intent | 快速分类 | Haiku LLM | ❌ |
| 2️⃣ Prompt | 动态组装 | Registry | ❌ |
| 3️⃣ Plan | 创建计划 | Sonnet LLM + plan_todo | ✅ Todo 显示 |
| 4️⃣ Router | 筛选工具 | Router | ❌ |
| 5️⃣ Selector | 选调用方式 | InvocationSelector | ❌ |
| 6️⃣ RVR | 执行步骤 | Sonnet + Tools | ✅ 进度更新 |
| 7️⃣ Output | 返回结果 | Agent | ✅ 最终输出 |

### 双 LLM 架构

```
┌─────────────────────────────────────────────────────────────┐
│                     双 LLM 架构                              │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Stage 1: Intent Recognition (Haiku 4.5)                    │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━                  │
│  • 快速、便宜                                                │
│  • 判断任务类型和复杂度                                      │
│  • 选择系统提示词级别                                        │
│                                                             │
│  Stage 2: Task Execution (Sonnet 4.5)                       │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━                  │
│  • 强大、准确                                                │
│  • Extended Thinking                                         │
│  • 工具调用                                                  │
│  • RVR 循环                                                  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 🎯 工具选择策略详解

### 问题：多工具竞争场景

当多个工具都能完成同一任务时（如 PPT 生成有 slidespeak-generator 和 pptx），Router 如何选择？

```
ppt_generation (能力分类)
    ↓
├─ slidespeak-generator (CUSTOM, priority: 85)  ← 专业、产品、客户
│   keywords: ["专业", "产品", "业务", "演示"]
│   preferred_for: ["professional PPT", "business presentation"]
│
└─ pptx (PREBUILT, priority: 60)  ← 快速、草稿、简单
    keywords: ["快速", "草稿", "简单"]
    preferred_for: ["quick PPT", "draft slides"]
```

### 当前策略：优先级排序 + LLM 智能选择

```
┌─────────────────────────────────────────────────────────────────────┐
│              Router 的三层筛选策略                                   │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  1️⃣ 能力匹配 (Capability Matching)                                  │
│     • 从 capabilities.yaml 查找匹配的工具                           │
│     • ppt_generation → [slidespeak-generator, pptx]                 │
│                                                                      │
│  2️⃣ 约束过滤 (Constraint Filtering)                                 │
│     • 检查 API 可用性（requires_api: true）                         │
│     • 检查网络状态（requires_network: true）                        │
│     • 检查认证状态（requires_auth: true）                           │
│     • 不满足约束的工具被过滤掉                                       │
│                                                                      │
│  3️⃣ 优先级排序 (Priority Sorting)                                   │
│     • 按 priority 字段排序（高 → 低）                               │
│     • slidespeak-generator (85) 排在 pptx (60) 前面                │
│     • ⚠️ 但两个都保留，不强制去重                                   │
│                                                                      │
│  4️⃣ 传给 LLM (智能选择)                                             │
│     • Sonnet 看到工具列表：                                          │
│       [slidespeak-generator(85), pptx(60)]                          │
│     • System Prompt 中包含每个工具的 metadata:                      │
│       - slidespeak: "专业、产品、客户场景"                          │
│       - pptx: "快速、草稿、简单场景"                                │
│     • Sonnet 根据用户意图智能选择:                                  │
│       用户: "生成专业的产品PPT" → slidespeak-generator              │
│       用户: "快速做个草稿PPT" → pptx                                │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### 为什么不在 Router 强制去重？

| 方案 | 优点 | 缺点 | 适用场景 |
|-----|------|------|---------|
| **Router 去重**<br>（只选最高优先级） | • 工具列表最短<br>• 减少 LLM 选择 | • 失去灵活性<br>• 无法根据上下文调整 | 工具功能完全重复 |
| **LLM 智能选择**<br>（当前策略） | • 根据语义选择<br>• 适应不同场景<br>• 保留专业/快速选项 | • 工具列表稍长<br>• 依赖 LLM 理解 | ✅ **工具有差异化特点** |

**结论**：V3.7 采用 **LLM 智能选择**，因为：
1. ✅ Sonnet 能理解用户意图（"专业" vs "快速"）
2. ✅ 不同工具有不同特点（slidespeak 专业、pptx 快速）
3. ✅ 适应更多场景，而不是一刀切

### 实际案例

**场景 1: 专业产品 PPT**
```
用户: "帮我生成一个专业的产品发布PPT"
      ↓
Router 筛选: [slidespeak-generator, pptx]
      ↓
LLM 推理: "专业" + "产品" → 关键词匹配 slidespeak
      ↓
选择: slidespeak-generator ✅
```

**场景 2: 快速草稿**
```
用户: "快速做个草稿PPT，简单就行"
      ↓
Router 筛选: [slidespeak-generator, pptx]
      ↓
LLM 推理: "快速" + "草稿" + "简单" → 关键词匹配 pptx
      ↓
选择: pptx ✅ (更快、免API调用)
```

### 配置文件中的关键字段

```yaml
# capabilities.yaml
capabilities:
  - name: slidespeak-generator
    type: SKILL
    capabilities: [ppt_generation]
    priority: 85  # 🔑 优先级（越高越优先）
    metadata:
      preferred_for:  # 🔑 优先使用场景（给 LLM 的提示）
        - professional PPT
        - business presentation
        - client-facing decks
      keywords:  # 🔑 关键词（LLM 匹配依据）
        - 专业
        - 产品
        - 客户
        - 业务
  
  - name: pptx
    type: SKILL
    capabilities: [ppt_generation]
    priority: 60
    metadata:
      preferred_for:
        - quick PPT
        - draft slides
      keywords:
        - 快速
        - 草稿
        - 简单
```

### 进阶：显式工具选择（未来扩展）

如果用户明确指定工具：
```
用户: "用 slidespeak 生成PPT"
      ↓
Router 检测显式请求 → 直接返回 slidespeak-generator
      ↓
跳过其他工具，优先级最高
```

---

## 🔧 核心组件

### 1. SimpleAgent（agent.py）

**职责**：框架管理（骨架），不含业务规则

```python
class SimpleAgent:
    """
    V3.7 Agent - 框架管理 + 动态路由
    
    职责：
    - 调用 LLM → 🆕 动态筛选工具 → 执行工具 → 管理 Memory → 通知进度
    
    不做：
    - 意图判断（LLM 做）
    - Plan 创建判断（LLM 做）
    - 质量验证（LLM 做）
    """
    
    def __init__(self):
        # 1. 能力注册表（🆕 加载 capability_categories）
        self.capability_registry = create_capability_registry()
        
        # 2. 能力路由器
        self.capability_router = create_capability_router()
        
        # 3. Skills 管理器
        self.skills_manager = create_skills_manager()
        
        # 4. 工具执行器
        self.tool_executor = create_tool_executor()
        
        # 5. 记忆管理
        self.memory = create_memory_manager()
        
        # 6. Plan/Todo 工具（🆕 传入 Registry 支持动态 Schema）
        self.plan_todo_tool = create_plan_todo_tool(
            memory=self.memory.working,
            registry=self.capability_registry  # 🆕
        )
        
        # 🆕 7. InvocationSelector - 调用方式选择器
        self.invocation_selector = create_invocation_selector(
            enable_code_execution=True,
            enable_programmatic=True,
            enable_streaming=True
        )
        
        # 8. LLM Service（双 LLM）
        self.intent_llm = create_claude_service(model="claude-haiku-4-5")
        self.llm = create_claude_service(model="claude-sonnet-4-5")
        
    async def run(self, user_input: str):
        """
        🆕 V3.7 执行流程（正确顺序）
        
        1. Intent Analysis (Haiku)
        2. Plan Creation (Sonnet) - 指定 capability
        3. 🆕 Dynamic Tool Selection (Router) - 真正筛选工具
        4. 🆕 Invocation Strategy (Selector) - 选择调用方式
        5. RVR Loop - 只用筛选后的工具
        """
        # ... 详见代码实现
```

### 🆕 1.5. CapabilityRegistry（capability_registry.py）

**职责**：能力注册表 + 能力分类管理

```python
class CapabilityRegistry:
    """
    V3.7 新增：能力分类管理
    
    核心功能：
    - 从 capabilities.yaml 加载 capability_categories
    - 提供 get_categories_for_prompt() - 动态生成 Prompt
    - 提供 get_category_ids() - 动态生成 Schema enum
    - 单一数据源原则
    """
    
    def __init__(self):
        self.capabilities = {}  # 工具/Skills 注册表
        self.categories = []    # 🆕 能力分类定义
        
    def get_categories_for_prompt(self) -> str:
        """
        🆕 动态生成 System Prompt 中的能力分类说明
        
        Returns:
            Markdown 格式的分类表格
            
        Example:
            ## 🏷️ Available Capability Categories
            | Category | Description | Use When |
            |----------|-------------|----------|
            | web_search | 搜索互联网信息 | 需要查找资料... |
            | ppt_generation | 生成演示文稿 | 需要创建PPT... |
            ...
        """
    
    def get_category_ids(self) -> List[str]:
        """
        🆕 获取分类 ID（用于 plan_todo Schema enum）
        
        Returns:
            ["web_search", "ppt_generation", ...]
        """
```

**关键改进**：
- ✅ 能力分类定义在 YAML，不在代码中
- ✅ System Prompt 动态生成，无需手动同步
- ✅ plan_todo Schema enum 自动生成

### 🆕 1.6. InvocationSelector（invocation_selector.py）

**职责**：智能选择工具调用方式

```python
class InvocationSelector:
    """
    V3.7 新增：调用方式选择器
    
    支持 5 种调用方式：
    1. Direct Tool Call - 标准方式
    2. Code Execution - 配置生成/计算逻辑
    3. Programmatic Tool Calling - 多工具编排
    4. Fine-grained Streaming - 大参数传输
    5. Tool Search - 工具数量>30时动态发现
    """
    
    def select_strategy(
        self,
        task_type: str,
        selected_tools: List[str],
        estimated_input_size: int = 0
    ) -> InvocationStrategy:
        """
        根据任务类型和工具特征选择最优调用方式
        
        规则：
        - 配置生成 → Code Execution
        - 多工具(>2) → Programmatic Tool Calling
        - 大参数(>10KB) → Fine-grained Streaming
        - 工具多(>30) → Tool Search
        - 默认 → Direct Tool Call
        """
```

**使用场景**：
```python
# 场景1: 配置生成
strategy = selector.select_strategy(
    task_type="config_generation",
    selected_tools=["slidespeak-generator"]
)
# → Code Execution

# 场景2: 多工具编排
strategy = selector.select_strategy(
    task_type="multi_tool",
    selected_tools=["web_search", "exa_search", "slidespeak"]
)
# → Programmatic Tool Calling
```

### 2. WorkingMemory（memory.py）

**职责**：会话级短期记忆

```python
class WorkingMemory:
    """
    工作记忆 - 当前会话的短期记忆
    
    存储：
    - messages: 消息历史
    - tool_calls: 工具调用记录
    - plan_json: 内部 RVR 调度（🆕）
    - todo_md: 用户进度展示（🆕）
    """
    
    def __init__(self):
        self.messages = []
        self.tool_calls = []
        self.plan_json = None  # 🆕 Plan 存储
        self.todo_md = None    # 🆕 Todo 存储
    
    # Plan/Todo CRUD
    def set_plan(self, plan_json, todo_md): ...
    def get_plan(self) -> Optional[Dict]: ...
    def get_todo(self) -> Optional[str]: ...
    def has_plan(self) -> bool: ...
    def update_plan_step(self, step_index, status, result): ...
    def get_plan_context_for_llm(self) -> str: ...  # 精简上下文
```

### 3. PlanTodoTool（plan_todo_tool.py）

**职责**：Plan/Todo CRUD 工具 + 🆕 动态 Schema 生成

```python
class PlanTodoTool:
    """
    V3.7 增强：动态 Schema 生成
    
    操作：
    - create_plan: 创建计划（🆕 步骤需指定 capability）
    - get_plan: 读取计划（每步开始前 MANDATORY）
    - update_step: 更新步骤（每步结束后 MANDATORY）
    - add_step: 动态添加步骤
    - clear: 清除计划
    """
    
    def __init__(self, memory: WorkingMemory, registry: CapabilityRegistry):
        self._memory = memory
        self._registry = registry  # 🆕 用于动态生成 Schema
    
    def get_input_schema(self) -> Dict:
        """
        🆕 动态生成 input_schema
        
        - 从 Registry 获取 capability_categories
        - 生成 capability enum（自动同步）
        - 无需手动维护多处定义
        """
        capability_enum = self._registry.get_category_ids()
        
        return {
            "properties": {
                "data": {
                    "properties": {
                        "steps": {
                            "items": {
                                "properties": {
                                    "capability": {
                                        "type": "string",
                                        "enum": capability_enum  # 🆕 动态生成
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    
    def execute(self, operation: str, data: Dict) -> Dict:
        if operation == "create_plan":
            return self._create_plan(data)
        elif operation == "get_plan":
            return self._get_plan()
        elif operation == "update_step":
            return self._update_step(data)
        # ...
```

**Plan 结构变化**：
```json
{
  "goal": "生成产品PPT",
  "steps": [
    {
      "action": "搜索产品信息",
      "capability": "web_search",  // 🆕 抽象能力标签
      "status": "pending"
    },
    {
      "action": "生成PPT",
      "capability": "ppt_generation",  // 🆕 抽象能力标签
      "status": "pending"
    }
  ],
  "required_capabilities": ["web_search", "ppt_generation"]  // 🆕 汇总
}
```

### 4. System Prompt（universal_prompt.py）

**职责**：定义所有逻辑规则（大脑）

```
核心协议：
1. Intent Recognition Protocol - 意图识别
2. Planning Protocol (Memory-First) - Plan/Todo 管理
3. RVR Protocol - React+Validation+Reflection
4. Final Validation Protocol - 最终验证
```

---

## 🔄 工作流程

### 🆕 V3.7 完整流程图（正确顺序）

```
User Query
    │
    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 1️⃣ Intent Analysis (Haiku 4.5) - 快速分类                               │
├─────────────────────────────────────────────────────────────────────────┤
│ 职责：简单分类（Haiku 快+便宜）                                          │
│ Output:                                                                  │
│   • task_type: information_query|content_generation|data_analysis|...   │
│   • complexity: simple|medium|complex                                    │
│   • needs_plan: true|false                                               │
│                                                                          │
│ ❌ 不分析 required_capabilities（留给 Sonnet）                          │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
        ┌────────────────────────┴────────────────────────────┐
        │                                                      │
        ▼                                                      ▼
  [needs_plan: false]                              [needs_plan: true]
  complexity: simple                               complexity: medium/complex
        │                                                      │
        │                                                      ▼
        │                              ┌───────────────────────────────────────┐
        │                              │ 2️⃣ Plan Creation (Sonnet 4.5)         │
        │                              ├───────────────────────────────────────┤
        │                              │ 职责：深度推理（Sonnet 强+准确）       │
        │                              │                                       │
        │                              │ 在 Extended Thinking 中推理：         │
        │                              │ • 分析任务需求                        │
        │                              │ • 拆解步骤                            │
        │                              │ • 🆕 每步指定 capability（抽象标签）  │
        │                              │                                       │
        │                              │ Output via plan_todo.create_plan():   │
        │                              │ {                                     │
        │                              │   "goal": "生成产品PPT",              │
        │                              │   "steps": [                          │
        │                              │     {                                 │
        │                              │       "action": "搜索产品信息",       │
        │                              │       "capability": "web_search" 🆕   │
        │                              │     },                                │
        │                              │     {                                 │
        │                              │       "action": "生成PPT",            │
        │                              │       "capability": "ppt_generation" │
        │                              │     }                                 │
        │                              │   ],                                  │
        │                              │   "required_capabilities": [...]  🆕  │
        │                              │ }                                     │
        │                              └───────────────────────┬───────────────┘
        │                                                      │
        │                                                      ▼
        │                              ┌───────────────────────────────────────┐
        │                              │ 🆕 3️⃣ Dynamic Tool Selection (Router)  │
        │                              ├───────────────────────────────────────┤
        │                              │ 职责：抽象能力 → 具体工具映射         │
        │                              │                                       │
        │                              │ Input: plan.required_capabilities     │
        │                              │   ["web_search", "ppt_generation"]    │
        │                              │                                       │
        │                              │ Router 查询 capabilities.yaml：       │
        │                              │   web_search → [exa_search, ...]      │
        │                              │   ppt_generation → [slidespeak, ...]  │
        │                              │                                       │
        │                              │ Output: 筛选后的工具子集              │
        │                              │   [exa_search, slidespeak, bash, ...]│
        │                              │   (5/12 工具，不是全部) 🎯            │
        │                              └───────────────────────┬───────────────┘
        │                                                      │
        │                                                      ▼
        │                              ┌───────────────────────────────────────┐
        │                              │ 🆕 4️⃣ Invocation Strategy Selection    │
        │                              ├───────────────────────────────────────┤
        │                              │ 职责：根据任务选择最优调用方式        │
        │                              │                                       │
        │                              │ InvocationSelector.select_strategy(): │
        │                              │   • 配置生成 → Code Execution         │
        │                              │   • 多工具编排 → Programmatic         │
        │                              │   • 简单查询 → Direct Call            │
        │                              │   • 大参数 → Streaming                │
        │                              │   • 工具多(>30) → Tool Search         │
        │                              └───────────────────────┬───────────────┘
        │                                                      │
        └──────────────────────────────┬───────────────────────┘
                                       │
                                       ▼
                   ┌───────────────────────────────────────────────────────┐
                   │ 5️⃣ RVR Loop - 只用筛选后的工具                        │
                   ├───────────────────────────────────────────────────────┤
                   │ for each step in plan:                                │
                   │   [Read] get_plan() ← MANDATORY                       │
                   │   [Reason] LLM 分析当前步骤                           │
                   │   [Act] 使用选定的 invocation_strategy 执行           │
                   │        • LLM 只看到筛选后的工具（5个，不是全部12个）  │
                   │   [Observe] 分析结果                                  │
                   │   [Validate] 验证质量                                 │
                   │   [Write] update_step() ← MANDATORY                   │
                   │   [Reflect] 失败时反思+重试                           │
                   └───────────────────────────┬───────────────────────────┘
                                               │
                                               ▼
                   ┌───────────────────────────────────────────────────────┐
                   │ 6️⃣ Final Output                                        │
                   ├───────────────────────────────────────────────────────┤
                   │ • Final Validation                                    │
                   │ • Quality Score                                       │
                   │ • Deliverables                                        │
                   └───────────────────────────────────────────────────────┘
```

### 🎯 关键改进点

| 步骤 | 旧版本 | V3.7 新版本 | 改进 |
|------|--------|------------|------|
| **1. Intent** | 分析能力需求 | 只做简单分类 | Haiku 不够强，交给 Sonnet |
| **2. Plan** | 不指定 capability | 指定抽象 capability | 解耦 LLM 和工具 ✅ |
| **3. Router** | 只记录日志 | 真正筛选工具 | **核心功能生效** ✅ |
| **4. Invocation** | 未使用 | 智能选择调用方式 | 5种方式支持 ✅ |
| **5. RVR** | 传入所有工具 | 只用筛选后的工具 | 减少选择困难 ✅ |

### RVR 循环详解

```
每个步骤的完整流程：

┌─────────────────────────────────────────────────────────────┐
│                     Turn N: 执行步骤 X                       │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│ 1️⃣ [Read] plan_todo.get_plan()  ← MANDATORY                 │
│    └─ 从 WorkingMemory 读取当前状态                         │
│    └─ 获取 current_step, current_action                    │
│                                                             │
│ 2️⃣ [Reason] Extended Thinking                               │
│    └─ 分析当前步骤需求                                      │
│    └─ 规划执行策略                                          │
│                                                             │
│ 3️⃣ [Act] 执行工具                                           │
│    └─ 根据 plan.json 指示执行                               │
│    └─ 支持：Direct Call / Code Execution / Programmatic    │
│                                                             │
│ 4️⃣ [Observe] 观察结果                                       │
│    └─ 分析工具返回                                          │
│                                                             │
│ 5️⃣ [Validate] 验证质量                                      │
│    └─ Completeness: 完整性                                  │
│    └─ Correctness: 正确性                                   │
│    └─ Quality: 质量                                         │
│                                                             │
│ 6️⃣ [Write] plan_todo.update_step()  ← MANDATORY            │
│    └─ 更新步骤状态（completed|failed）                      │
│    └─ 记录步骤结果                                          │
│    └─ 写入 WorkingMemory                                    │
│                                                             │
│ 7️⃣ [Reflect] 如果验证失败                                   │
│    └─ 分析失败原因                                          │
│    └─ 调整策略重试（最多 3 次）                             │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 📁 文件结构

```
/
├── core/                          # 核心组件
│   ├── agent.py                   # SimpleAgent（框架管理）
│   ├── memory.py                  # MemoryManager（含 WorkingMemory）
│   ├── llm_service.py             # LLM 封装（工具格式转换）
│   ├── capability_registry.py     # 能力注册表（从 YAML 加载）
│   ├── capability_router.py       # 能力路由器
│   ├── skills_manager.py          # Skills 管理器
│   ├── invocation_selector.py     # 🆕 调用方式选择器
│   └── planning.py                # ⚠️ 已废弃，使用 plan_todo_tool
│
├── tools/                         # 工具层
│   ├── executor.py                # 工具执行器（从 Registry 加载）
│   ├── plan_todo_tool.py          # Plan/Todo CRUD 工具
│   ├── exa_search.py              # Exa 搜索工具
│   ├── slidespeak.py              # SlideSpeak 渲染工具
│   └── ...
│
├── prompts/                       # 提示词层
│   ├── universal_prompt.py        # 完整系统提示词
│   ├── simple_prompt.py           # 简单任务提示词
│   ├── standard_prompt.py         # 标准任务提示词
│   ├── intent_recognition_prompt.py # 意图识别提示词
│   └── MEMORY_PROTOCOL.md         # Memory Protocol 详细说明
│
├── skills/                        # Skills 层
│   └── library/
│       ├── slidespeak-generator/  # PPT 生成 Skill
│       └── ...
│
├── config/
│   └── capabilities.yaml          # 📌 能力配置（统一定义所有工具）
│
└── __init__.py                    # 包导出
```

### 🆕 工具定义统一原则（V3.7 强化版）

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     capabilities.yaml = 唯一配置源                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  🆕 Part 1: Capability Categories（能力分类定义）                            │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│  capability_categories:                                                      │
│    - id: web_search                                                          │
│      description: "搜索互联网信息"                                           │
│      use_when: "需要查找资料、新闻、数据"                                    │
│                                                                              │
│  作用：                                                                       │
│  ✅ System Prompt 自动生成（get_categories_for_prompt()）                    │
│  ✅ plan_todo Schema enum 自动生成（get_category_ids()）                     │
│  ✅ 修改一处，全局同步                                                        │
│                                                                              │
│  Part 2: Capabilities（工具/Skills 定义）                                    │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│  capabilities:                                                               │
│    - name: exa_search                                                        │
│      type: TOOL                                                              │
│      capabilities: [web_search, semantic_search]  # 🆕 映射到分类            │
│      priority: 90                                                            │
│      implementation:                                                         │
│        module: "tools.exa_search"                                   │
│                                                                              │
│  作用：                                                                       │
│  ✅ Router 根据 capabilities 字段匹配工具                                    │
│  ✅ 新增工具只需声明 capabilities，无需修改 Prompt                           │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │  🆕 能力映射关系                                                          ││
│  │  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ ││
│  │  Capability Category     →     具体工具                                  ││
│  │  ━━━━━━━━━━━━━━━━━━━━━━       ━━━━━━━━━━━━━━━━━━━━━━                    ││
│  │  web_search              →     exa_search, web_search                    ││
│  │  ppt_generation          →     slidespeak-generator, pptx                ││
│  │  file_operations         →     file_read, file_write, bash               ││
│  │  data_analysis           →     xlsx, python                              ││
│  │  ...                                                                     ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                                                              │
│  ❌ 禁止：                                                                    │
│  • 在 prompts/*.py 中硬编码能力列表                                          │
│  • 在 plan_todo_tool.py 中硬编码 enum                                        │
│  • 在多处定义相同的分类                                                      │
│                                                                              │
│  ✅ 单一数据源原则：所有定义在 capabilities.yaml，其他处自动同步             │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 🔧 五种工具调用方式

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       Claude 五种工具调用方式                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  1️⃣ Direct Tool Call (标准)                                                 │
│     • 场景: 单工具 + 简单参数                                                │
│     • 示例: web_search("天气"), bash("ls -la")                              │
│     • 配置: 默认方式，无需特殊配置                                           │
│                                                                              │
│  2️⃣ Code Execution (代码执行)                                               │
│     • 场景: 配置生成、计算逻辑、数据处理                                     │
│     • 示例: 生成 PPT JSON 配置、数据转换                                    │
│     • 配置: code_execution tool (Beta)                                      │
│                                                                              │
│  3️⃣ Programmatic Tool Calling (程序化调用)                                  │
│     • 场景: 多工具编排、循环调用、批量处理                                   │
│     • 示例: 在代码中调用多个搜索 API 并聚合结果                              │
│     • 配置: 在 Code Execution 容器内调用工具                                 │
│                                                                              │
│  4️⃣ Fine-grained Streaming (细粒度流式)                                     │
│     • 场景: 大参数传输 (>10KB)、实时反馈                                     │
│     • 示例: 流式传输 PPT 配置 JSON                                          │
│     • 配置: stream=True + 大参数                                            │
│                                                                              │
│  5️⃣ Tool Search (工具搜索)                                                  │
│     • 场景: 工具数量 >30，动态发现所需工具                                   │
│     • 示例: 从 100+ 工具中搜索相关工具                                       │
│     • 配置: defer_loading=True + tool_search_tool (Beta)                    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘

🆕 V3.7 选择策略（InvocationSelector 自动选择）：

┌─────────────────┬────────────────────────────────────────────────────────────┐
│ 条件             │ 推荐调用方式                                               │
├─────────────────┼────────────────────────────────────────────────────────────┤
│ 单工具+简单参数   │ Direct Tool Call                                          │
│ 配置生成/计算逻辑 │ Code Execution ✅ 已集成                                   │
│ 多工具编排(>2)   │ Programmatic Tool Calling ✅ 已集成                        │
│ 大参数(>10KB)    │ Fine-grained Streaming ✅ 已集成                           │
│ 工具数量>30      │ Tool Search → 动态发现 ✅ 已集成                           │
└─────────────────┴────────────────────────────────────────────────────────────┘

**V3.7 改进**：
- ✅ InvocationSelector 全面集成
- ✅ 根据任务类型自动选择最优方式
- ✅ 充分利用 Claude 五种调用能力

**使用示例**：
```python
# Agent 自动选择调用方式
invocation_strategy = self.invocation_selector.select_strategy(
    task_type=intent_analysis['task_type'],
    selected_tools=[t.name for t in selected_tools],
    estimated_input_size=len(str(plan))
)

# 根据策略配置工具
tools_config = self.invocation_selector.get_tools_config(
    all_tools=tools_for_llm,
    strategy=invocation_strategy
)

# LLM 调用
response = self.llm.create_message(
    messages=messages,
    system=self.system_prompt,
    tools=tools_config['tools'],
    **tools_config.get('extra', {})
)
```

---

## 🧠 记忆机制（简化版）

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          记忆架构（权责划分）                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ⚠️ 核心原则：线上 Agent 只负责「读」，不负责「生成/分析」                   │
│                                                                              │
│  1️⃣ Short Memory (WorkingMemory) - 当前会话 ← Agent 完全负责                │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│  • 存储：messages, tool_calls, plan_json, todo_md                          │
│  • 能力：✅ 多轮对话、✅ 会话级上下文保持                                   │
│  • 生命周期：单个 session（end_session 后清除）                             │
│  • 状态：✅ 已实现                                                           │
│                                                                              │
│  2️⃣ Long Memory (知识库) - 跨会话 ← Agent 只读                              │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│  • 存储：外部数据库（用户画像、历史摘要等）                                  │
│  • Agent 操作：只读（从数据库读取）                                          │
│  • 生成方：离线系统（定时任务，非 Agent 职责）                               │
│  • 状态：保留接口，暂不实现生成逻辑                                          │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘

多轮对话 + HITL API：
┌──────────────────────────────────────────────────────────────┐
│                                                              │
│  agent = create_simple_agent()                               │
│                                                              │
│  # ===== 多轮对话 =====                                      │
│                                                              │
│  # 第一轮对话                                                │
│  result1 = await agent.chat("帮我生成一个 PPT")              │
│                                                              │
│  # 第二轮对话（保持上下文）                                  │
│  result2 = await agent.chat("把标题改成'AI技术分享'")        │
│                                                              │
│  # 获取对话历史                                              │
│  history = agent.get_conversation_history()                  │
│                                                              │
│  # 结束会话                                                  │
│  agent.end_session()                                         │
│                                                              │
│  # ===== HITL (Human-in-the-Loop) =====                      │
│                                                              │
│  # 1. 任务后反馈改进                                         │
│  refined = await agent.refine(                               │
│      original_query="生成PPT",                               │
│      previous_result=result['final_result'],                 │
│      user_feedback="内容太少，再加一些细节"                  │
│  )                                                           │
│                                                              │
│  # 2. 澄清请求（Agent 需要更多信息）                         │
│  clarification = await agent.clarify("PPT风格？商务/学术？")│
│  # → 用户用 chat() 回复                                      │
│  result = await agent.chat("商务风格")                       │
│                                                              │
│  # 3. 确认请求                                               │
│  question = await agent.confirm("是否继续？")                │
│  # → UI 层展示给用户，用户确认后继续                         │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

---

---

## 🎯 V3.7 版本更新日志

### 🆕 核心改进（2025-12-24）

#### 1. **能力抽象层（Capability Abstraction Layer）**

**问题**：Sonnet 需要知道所有工具名称才能制定 Plan，但这导致 Router 无法筛选工具。

**解决**：引入抽象能力层，Sonnet 只需知道 8 个抽象分类，Router 负责映射到具体工具。

```yaml
# 修改前：Sonnet 需要知道所有工具
tools: [exa_search, web_search, slidespeak-generator, pptx, ...]

# 修改后：Sonnet 只需知道抽象分类
capability_categories:
  - web_search
  - ppt_generation
  - ...
```

**效果**：
- ✅ 解耦 LLM 和工具实现
- ✅ 新增工具无需修改 Prompt
- ✅ Router 可以真正筛选工具

#### 2. **动态工具筛选（Router 真正生效）**

**问题**：Router 只用于日志，所有工具一次性传给 LLM（12/12）。

**解决**：根据 Plan 的 required_capabilities 动态筛选工具。

```python
# 修改前
tools_for_llm = all_tools  # 12 个工具全部传入

# 修改后
required_capabilities = plan.get('required_capabilities', [])
selected_tools = router.select_tools_for_capabilities(required_capabilities)
tools_for_llm = [t.name for t in selected_tools]  # 只传入 5 个相关工具
```

**效果**：
- ✅ 筛选比例：5/12 = 41.7%
- ✅ 减少 LLM 选择困难
- ✅ 提高工具调用准确性

#### 3. **智能调用方式选择（InvocationSelector 集成）**

**问题**：InvocationSelector 代码存在但未使用。

**解决**：在 agent.py 中集成 InvocationSelector，根据任务类型自动选择调用方式。

```python
# 新增逻辑
invocation_strategy = self.invocation_selector.select_strategy(
    task_type=intent_analysis['task_type'],
    selected_tools=[t.name for t in selected_tools]
)

# 配置生成 → Code Execution
# 多工具编排 → Programmatic Tool Calling
# 简单查询 → Direct Tool Call
```

**效果**：
- ✅ 5 种调用方式全部支持
- ✅ 自动选择最优方式
- ✅ 充分利用 Claude 能力

#### 4. **配置驱动（单一数据源原则）**

**问题**：能力分类在多处定义（Prompt、Schema、代码），维护困难。

**解决**：统一在 capabilities.yaml 定义，其他处动态生成。

```yaml
# 唯一数据源：capabilities.yaml
capability_categories:
  - id: web_search
    description: "搜索互联网信息"
    ...
```

```python
# System Prompt 自动生成
prompt = registry.get_categories_for_prompt()

# Schema enum 自动生成  
schema_enum = registry.get_category_ids()
```

**效果**：
- ✅ 修改一处，全局同步
- ✅ 无需手动维护多处定义
- ✅ 易于扩展新能力

### 📊 对比表

| 特性 | V3.6 | V3.7 | 改进 |
|------|------|------|------|
| **能力定义** | 硬编码 | 动态加载 | ✅ 易扩展 |
| **LLM 感知** | 所有工具名称 | 8个抽象分类 | ✅ 解耦 |
| **工具筛选** | 传入全部(12/12) | 动态筛选(5/12) | ✅ 41.7% 优化 |
| **调用方式** | 未使用 | 智能选择 | ✅ 5种方式 |
| **Router** | 仅日志 | 核心功能 | ✅ 真正生效 |
| **Schema** | 硬编码 | 动态生成 | ✅ 自动同步 |

### 🎉 核心收益

1. **架构清晰** - 正确的执行顺序（Intent → Plan → Router → Selector → RVR）
2. **真正解耦** - Sonnet 不需要知道具体工具，只需知道抽象能力
3. **动态筛选** - Router 从"观察者"变为"核心功能"
4. **智能调用** - 根据场景自动选择最优调用方式
5. **易于扩展** - 新增工具/能力只需在 YAML 声明

---

## 🔗 相关文档

| 文档 | 说明 | 状态 |
|------|------|------|
| [MEMORY_ARCHITECTURE.md](./MEMORY_ARCHITECTURE.md) | 完整记忆架构 | 📝 设计阶段 |
| [01-MEMORY-PROTOCOL.md](./01-MEMORY-PROTOCOL.md) | Memory-First Protocol 详解 | ✅ 已实现 |
| [02-CAPABILITY-ROUTING.md](./02-CAPABILITY-ROUTING.md) | 🆕 能力路由算法（V3.7 更新） | ✅ 已实现 |
| [03-SKILLS-DISCOVERY.md](./03-SKILLS-DISCOVERY.md) | Skills 发现机制 | ✅ 已实现 |
| [04-TOOL-CALLING-STRATEGIES.md](./04-TOOL-CALLING-STRATEGIES.md) | 🆕 工具调用策略（V3.7 更新） | ✅ 已实现 |
| [STREAMING_ARCHITECTURE.md](..//docs/STREAMING_ARCHITECTURE.md) | 🆕 流式输出架构设计 | 🔧 设计完成，待重构 |
| [HITL-USAGE-GUIDE.md](./HITL-USAGE-GUIDE.md) | Human-in-the-Loop | ✅ 已实现 |
