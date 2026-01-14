# ZenFlux Agent V6.3 架构文档

> 📅 **最后更新**: 2026-01-14  
> 🎯 **当前版本**: V6.3 - 上下文压缩三层防护 + RVR 循环深化  
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

### V6.3 核心特性

V6.3 是 ZenFlux Agent 的**上下文压缩三层防护 + RVR 循环深化** 版本，核心架构：

1. **🔥 上下文压缩三层防护**：Memory Tool 指导 + 历史消息裁剪 + QoS 成本控制
2. **🔥 透明化用户体验**：自动处理 + 事件反馈，用户知道发生了什么但无需操作
3. **🔥 RVR 循环架构稳定**：继续使用 `messages.stream()` + 自主 RVR 循环（不切换到 tool_runner）
4. **✅ 三级配置优先级**：`config.yaml` > LLM 推断 > `DEFAULT_AGENT_SCHEMA`
5. **✅ 高质量默认配置**：`DEFAULT_AGENT_SCHEMA` 升级为最佳实践配置
6. **✅ 智能配置合并**：`_merge_config_to_schema()` 函数实现选择性覆盖
7. **✅ 场景化提示词分解**：运营 `prompt.md` → LLM 分解为 4 个专用提示词
8. **SimpleAgent 单智能体**：用户请求 → Service 层 → SimpleAgent，简洁高效
9. **Prompt-First 原则**：规则写在 Prompt 里，不写在代码里

### V6.3 新增功能

#### 🔥 上下文压缩三层防护策略

**核心问题**：长对话场景下如何保证用户体验和问答效果？

**架构决策**：
- ✅ 继续使用 `messages.stream()` + 自主 RVR 循环
- ❌ 不切换到 `tool_runner`（灵活性更高，重构成本极大）
- ✅ 采用三层防护策略：Memory + 裁剪 + QoS

```
┌─────────────────────────────────────────────────────────────────────────┐
│                  上下文压缩三层防护策略                                   │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  L1. Memory Tool 状态保存（Claude 自主）                                 │
│      → 在 System Prompt 中指导 Claude 使用 memory 工具保存重要状态       │
│      → 周期性保存当前工作进展                                            │
│      → 完整完成任务，不提前停止                                          │
│                                                                          │
│  L2. 历史消息智能裁剪（服务层自动 + 事件通知）                           │
│      → 保留首轮对话（任务定义）                                          │
│      → 保留最近 N 轮（当前工作上下文）                                   │
│      → 保留关键 tool_result（数据和结果）                                │
│      → 中间轮次丢弃细节，保留摘要                                        │
│      → 🆕 通过 Events 系统告知用户优化结果                               │
│                                                                          │
│  L3. QoS 成本控制（后端监控 + 可选通知）                                 │
│      → 根据用户等级设置 token 预算（FREE/BASIC/PRO/ENTERPRISE）          │
│      → 后端日志和成本统计                                                │
│      → 🆕 接近预算时可选择性提示用户（配置化）                           │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

**核心原则**：
1. ✅ **自动化**：上下文管理自动执行，用户无需手动操作
2. ✅ **透明化**：通过事件系统告知用户系统在做什么（类似 Cursor）
3. ✅ **非侵入式**：通知不打断用户当前操作（5秒淡出）
4. ✅ **问答效果优先**：智能保留关键上下文，不丢信息
5. ✅ **架构匹配**：与当前 RVR 循环完全兼容
6. ✅ **维护简单**：~200 行核心代码 + 事件系统集成

**配置管理**：
- **框架层统一管理**：`config/context_compaction.yaml`
- **不暴露给运营**：运营人员无需了解技术细节，开箱即用
- **环境变量支持**：`export QOS_LEVEL=enterprise`（极少数场景）

**代码结构**：
```
core/context/compaction/
└── __init__.py                         # ~200行
    ├── QoSLevel                        # QoS 等级枚举
    ├── ContextStrategy                 # 策略配置
    ├── get_memory_guidance_prompt()    # L1：生成 Memory 指导提示词
    ├── trim_history_messages()         # L2：智能裁剪历史消息
    └── should_warn_backend()           # L3：后端预警判断

config/context_compaction.yaml          # 框架配置
services/chat_service.py                # L2/L3 执行点
core/agent/simple_agent.py              # L1 Prompt 注入点
```

**上下文进度条 UI（类似 Cursor）**：

除了事件通知，还应提供**实时可见的进度指示器**：

```
┌─────────────────────────────────────────────────────────────┐
│  对话界面顶部                                                │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  上下文: ████████░░░░░░░░ 45%  (90K / 200K tokens)   │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                             │
│  ✓ 对话历史已智能优化，保留 15 条关键消息                   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**进度条颜色编码**（类似 Cursor）：
- 🟢 **0-60%**：绿色，正常状态
- 🟡 **60-80%**：黄色，提示即将优化
- 🟠 **80-95%**：橙色，即将触发裁剪
- 🔴 **95-100%**：红色，建议新会话（极少触发）

**实时更新时机**：
1. 每次用户发送消息后更新
2. 每次 Agent 回复后更新
3. 裁剪/压缩后立即更新（显著下降）

**实现方式**：
- 通过 SSE 事件流持续更新进度条
- 事件类型：`context_usage_update`
- 包含：当前 tokens、预算、百分比、颜色等级

**效果对比**：

| 指标 | 之前 | V6.3 |
|------|------|------|
| **用户体验** | 可能警告用户 | 🆕 实时进度条 + 事件通知 ✅ |
| **透明度** | 用户不知道状态 | 🆕 持续可见的上下文使用情况 ✅ |
| **焦虑感** | "是不是卡住了？" | 🆕 清晰的进度反馈 ✅ |
| **架构匹配** | ❌ 不匹配（考虑切换 tool_runner） | ✅ 完全匹配现有架构 |
| **问答效果** | 可能丢关键信息 | 智能保留关键上下文 ✅ |
| **代码复杂度** | 1,500+ 行（如果用 tool_runner） | ~200 行 + 进度条组件 ✅ |
| **维护成本** | 需要大规模重构 | 轻量增强 ✅ |

**参考文档**：
- [上下文压缩策略指南](../guides/context_compression_strategy.md)
- [上下文管理框架](./context_management_framework.md)
- [上下文管理架构决策](./context_management_decision.md)

---

### V6.2 功能（延续）

#### 1. 三级配置优先级体系

```
┌────────────────────────────────────────────────────────────────────────┐
│                      配置优先级（从高到低）                              │
├────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   ┌─────────────────────────────────────────────────────────────────┐  │
│   │  Level 1: config.yaml 显式配置                                   │  │
│   │  • 运营人员的场景化定制                                          │  │
│   │  • 字段有值 → 覆盖下级配置                                       │  │
│   │  • 字段为空/None → 透传到下级                                    │  │
│   └─────────────────────────────────────────────────────────────────┘  │
│                              │                                          │
│                              ▼ 未配置的字段                             │
│   ┌─────────────────────────────────────────────────────────────────┐  │
│   │  Level 2: LLM 推断的 Schema                                      │  │
│   │  • 基于 prompt.md 内容智能推断                                   │  │
│   │  • 语义理解业务需求                                              │  │
│   │  • 自动配置组件启用状态                                          │  │
│   └─────────────────────────────────────────────────────────────────┘  │
│                              │                                          │
│                              ▼ LLM 也未配置的字段                       │
│   ┌─────────────────────────────────────────────────────────────────┐  │
│   │  Level 3: DEFAULT_AGENT_SCHEMA（框架兜底）                       │  │
│   │  • 高质量的最佳实践配置                                          │  │
│   │  • 即使运营配置不全/错误也能稳定运行                             │  │
│   │  • "安全网"设计理念                                              │  │
│   └─────────────────────────────────────────────────────────────────┘  │
│                                                                         │
└────────────────────────────────────────────────────────────────────────┘
```

**设计理念**：
- config.yaml 有配置 → 使用 config.yaml 的值
- config.yaml 未配置 → 使用 LLM 推断或框架默认值兜底
- 即使运营配置不全/错误，Agent 也能以高质量默认行为运行

#### 2. 高质量默认配置（DEFAULT_AGENT_SCHEMA）

**文件**：`core/schemas/validator.py`

```python
DEFAULT_AGENT_SCHEMA = AgentSchema(
    name="GeneralAgent",
    description="通用智能助手（高质量默认配置）",
    
    # ===== 意图分析器：启用 LLM 分析，覆盖常见任务类型 =====
    intent_analyzer=IntentAnalyzerConfig(
        enabled=True,
        use_llm=True,
        task_types=[
            "question_answering",   # 问答
            "data_analysis",        # 数据分析
            "content_generation",   # 内容生成
            "code_execution",       # 代码执行
            "web_search",           # 网络搜索
            "file_operation",       # 文件操作
        ],
        complexity_levels=["low", "medium", "high"],
        llm_model="claude-haiku-4-5-20251001",  # Haiku 4.5 支持 64K output
    ),
    
    # ===== 计划管理器：适中规模，适应大多数任务 =====
    plan_manager=PlanManagerConfig(
        enabled=True,
        max_steps=15,                    # 适中的步骤数
        granularity="medium",            # 中等粒度
        allow_dynamic_adjustment=True,   # 允许动态调整
        replan_enabled=True,             # 允许重规划
        max_replan_attempts=2,           # 最多重规划 2 次
        replan_strategy="incremental",   # 增量重规划（保留已完成步骤）
        failure_threshold=0.3,           # 30% 失败率触发重规划建议
    ),
    
    # ===== 工具选择器：基于能力的选择策略 =====
    tool_selector=ToolSelectorConfig(
        enabled=True,
        selection_strategy="capability_based",  # 基于能力匹配
        allow_parallel=False,            # 默认串行（更稳定）
        max_parallel_tools=3,
        base_tools=["plan_todo"],        # 始终包含计划工具
        tool_timeout=300,                # 5 分钟超时
    ),
    
    # ===== 记忆管理器：session 级别，适度的工作记忆 =====
    memory_manager=MemoryManagerConfig(
        enabled=True,
        retention_policy="session",      # 会话级保留
        working_memory_limit=20,         # 适中的记忆容量
        auto_compress=True,              # 自动压缩长对话
        compress_threshold=15,           # 15 条消息触发压缩
    ),
    
    # ===== 输出格式化器：文本格式，支持代码高亮 =====
    output_formatter=OutputFormatterConfig(
        enabled=True,
        default_format="text",           # 默认纯文本（V6.3 支持 JSON/Pydantic）
        code_highlighting=True,
        max_output_length=50000,
    ),
    
    # ===== 运行时参数 =====
    model="claude-sonnet-4-5-20250929",  # 平衡能力和成本
    max_turns=15,                        # 适中的对话长度
    allow_parallel_tools=False,          # 默认串行（更稳定）
    skills=[],                           # 由 config.yaml 配置
    tools=[],                            # 由 config.yaml 配置
    
    reasoning="高质量默认配置：适应大多数场景，平衡能力和稳定性。作为 config.yaml 配置缺失时的兜底。",
)
```

**设计理念**：
- **最佳实践优先**：默认值应是"生产就绪"配置，而非"最小化"配置
- **平衡能力和稳定性**：启用核心功能（如计划管理、意图分析），但默认串行执行（避免并发风险）
- **适中的资源配置**：15 步计划、20 条工作记忆、5 分钟工具超时
- **安全网设计**：即使运营配置错误，Agent 也能以合理行为运行

#### 3. 智能配置合并函数

**文件**：`scripts/instance_loader.py`

```python
def _merge_config_to_schema(base_schema, config: InstanceConfig):
    """
    将 config.yaml 配置合并到 AgentSchema
    
    合并策略：
    - config.yaml 有显式配置 → 覆盖 Schema 默认值
    - config.yaml 未配置（None）→ 保留 Schema 的高质量默认值
    
    这样即使运营配置不全或配置错误，也能依赖 DEFAULT_AGENT_SCHEMA 兜底。
    
    Args:
        base_schema: 基础 Schema（来自 LLM 推断或 DEFAULT_AGENT_SCHEMA）
        config: InstanceConfig（从 config.yaml 读取）
        
    Returns:
        合并后的 AgentSchema
    """
    # 深拷贝 Schema，避免修改原始默认值
    merged = base_schema.copy(deep=True)
    
    # === 基础配置覆盖 ===
    if config.model:
        merged.model = config.model
    if config.max_turns:
        merged.max_turns = config.max_turns
    if config.allow_parallel_tools is not None:
        merged.allow_parallel_tools = config.allow_parallel_tools
    
    # === 计划管理器配置覆盖 ===
    if config.plan_manager_enabled is not None:
        merged.plan_manager.enabled = config.plan_manager_enabled
    if config.plan_manager_max_steps is not None:
        merged.plan_manager.max_steps = config.plan_manager_max_steps
    if config.plan_manager_granularity is not None:
        merged.plan_manager.granularity = config.plan_manager_granularity
    
    # === 意图分析器配置覆盖 ===
    if config.intent_analyzer_enabled is not None:
        merged.intent_analyzer.enabled = config.intent_analyzer_enabled
    if config.intent_analyzer_use_llm is not None:
        merged.intent_analyzer.use_llm = config.intent_analyzer_use_llm
    
    # === 输出格式配置覆盖（V6.3 Pydantic 支持）===
    if config.output_format:
        merged.output_formatter.default_format = config.output_format
    if config.output_code_highlighting is not None:
        merged.output_formatter.code_highlighting = config.output_code_highlighting
    
    # === 记录合并结果 ===
    override_count = sum([
        config.model is not None,
        config.max_turns is not None,
        config.allow_parallel_tools is not None,
        config.plan_manager_enabled is not None,
        # ... 其他字段
    ])
    
    if override_count > 0:
        logger.debug(f"⚙️ config.yaml 覆盖了 {override_count} 项配置")
    
    return merged
```

**使用示例**：

```python
# 加载实例时的完整流程
from core.schemas import DEFAULT_AGENT_SCHEMA

# 1. 加载 InstancePromptCache（包含 LLM 推断的 Schema）
prompt_cache = await load_instance_cache(...)

# 2. 获取基础 Schema
if prompt_cache.agent_schema:
    base_schema = prompt_cache.agent_schema  # LLM 推断
else:
    base_schema = DEFAULT_AGENT_SCHEMA       # 兜底

# 3. 合并 config.yaml 配置
merged_schema = _merge_config_to_schema(base_schema, config)

# 4. 使用合并后的 Schema 创建 Agent
agent = AgentFactory.from_schema(merged_schema, ...)
```

**合并逻辑示例**：

| 配置字段 | config.yaml | base_schema | 最终值 | 来源 |
|---------|-------------|-------------|-------|------|
| model | `claude-sonnet-4-5` | `claude-sonnet-4-5` | `claude-sonnet-4-5` | config.yaml |
| max_turns | `20` | `15` | `20` | config.yaml |
| plan_manager.enabled | `None` | `True` | `True` | base_schema |
| plan_manager.max_steps | `None` | `15` | `15` | base_schema |

**关键价值**：
- ✅ 运营只需配置关心的字段
- ✅ 未配置字段自动使用高质量默认值
- ✅ 容错性强：配置错误也能正常运行

#### 4. 场景化提示词分解

```
运营配置的 prompt.md
        │
        ▼ LLM 语义分析 + 分解
        │
        ├─→ intent_prompt.md    （意图识别专用）
        ├─→ simple_prompt.md    （简单任务：8,000-15,000 字符）
        ├─→ medium_prompt.md    （中等任务：15,000-25,000 字符）
        ├─→ complex_prompt.md   （复杂任务：30,000-50,000 字符）
        └─→ agent_schema.yaml   （Agent 配置）
```

**提示词长度规范**（V6.2 修正）：

| 复杂度 | 目标长度 | 适用场景 |
|--------|----------|---------|
| Simple | 8,000-15,000 字符 | 简单问答、快速响应 |
| Medium | 15,000-25,000 字符 | 标准任务、一般业务流程 |
| Complex | 30,000-50,000 字符 | 复杂任务、完整规则集 |

**分解原则**：
- **意图识别提示词**：从原始 prompt 提取意图定义、关键词、处理逻辑
- **简单/中等提示词**：精简版本，移除意图相关内容，聚焦任务执行
- **复杂提示词**：优化版本，保留核心规则，去除冗余

#### 5. prompt_results/ 目录

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

#### 6. 提示词模块边界定义

**文件**：`core/prompt/framework_rules.py`

```python
PROMPT_MODULES_BOUNDARY = {
    "simple": {
        "keep": [
            "role_definition",        # 角色定义（必须保留）
            "absolute_prohibitions",  # 绝对禁止项（安全底线）
            "output_format_basic",    # 基础输出格式
            "quick_response_rules",   # 快速响应规则
        ],
        "remove": [
            "intent_recognition",     # 意图识别（已由 IntentAnalyzer 完成）
            "planning_flow",          # 规划流程（简单任务不需要）
            "tool_guide_detailed",    # 详细工具指南
            "validation_loop",        # 验证循环
        ]
    },
    "medium": {
        "keep": [
            "role_definition", "absolute_prohibitions",
            "tool_guide", "card_requirements",
            "output_format", "basic_planning",
        ],
        "remove": [
            "intent_recognition", "planning_flow_detailed",
            "advanced_validation", "complex_examples",
        ]
    },
    "complex": {
        "keep": ["*"],                # 保留全部模块
        "remove": ["intent_recognition"],  # 意图识别已完成
    }
}
```

**设计意图**：
- **减少 LLM 理解偏差**：明确告诉 LLM 各复杂度级别应保留/移除哪些模块
- **避免重复信息**：意图识别已由 IntentAnalyzer 完成，不需要在执行提示词中重复
- **长度控制**：Simple < Medium < Complex，通过模块边界确保长度递增

**LLM 提示词生成模板**（framework_rules.py）：

```python
SIMPLE_PROMPT_GENERATION_TEMPLATE = """
你是一个系统提示词优化专家。根据以下原始提示词，生成适用于"简单任务"的精简版本。

【原始提示词】
{user_prompt_summary}

【生成要求】
1. 保留模块：{keep_modules}
2. 移除模块：{remove_modules}
3. 目标长度：8,000-15,000 字符
4. 特别注意：移除所有意图识别相关内容（IntentAnalyzer 已完成）
...
"""

COMPLEX_PROMPT_GENERATION_TEMPLATE = """
你是一个系统提示词优化专家。根据以下原始提示词，生成适用于"复杂任务"的优化版本。

【原始提示词】
{user_prompt}

【生成要求】
1. 保留所有关键规则和流程
2. 移除意图识别模块（IntentAnalyzer 已完成）
3. 优化表述，去除冗余描述
4. 目标长度：30,000-50,000 字符
5. 强调：这是完整规则集，用于复杂任务处理
...
"""
```

**使用流程**：

```
原始 prompt.md
     │
     ▼ LLM 分解（使用 PROMPT_MODULES_BOUNDARY）
     │
     ├─→ simple_prompt.md   (8k-15k 字符)
     ├─→ medium_prompt.md   (15k-25k 字符)
     └─→ complex_prompt.md  (30k-50k 字符)
```

#### 7. Multi-Agent Mode 配置

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
V5.0 (2026-01)    V5.1 (2026-01)    V6.1 (2026-01)    V6.2 (2026-01)    V6.3 (2026-01)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
实例级缓存       → Mem0 画像增强   → 场景化提示词分解 → 三级配置优先级 → 🔥 上下文压缩三层防护
LLM 语义驱动     → 语义推理模块   → prompt_results   → AgentSchema兜底 → 🔥 RVR 循环深化
Prompt-First     → 工具分层加载   → 动态更新检测    → 智能配置合并   → 🔥 用户体验优先
本地持久化       → HITL 完善      → 框架规则引导    → 提示词长度规范 → 🔥 架构决策稳定
```

| 维度 | V5.1 | V6.1 | V6.2 | V6.3 |
|------|------|------|------|------|
| **上下文管理** | 无 | 基础支持 | 基础支持 | 🆕 三层防护策略 |
| **架构稳定性** | 探索阶段 | 基本稳定 | 配置驱动 | 🆕 RVR 循环确立 |
| **用户体验** | 基础可用 | 改善 | 改善 | 🆕 静默处理，完全无感知 |
| **配置管理** | 单层配置 | config.yaml | ✅ 三级优先级体系 | ✅ 三级优先级 + 框架统一管理 |
| **Schema 默认值** | 最小化配置 | 基础配置 | ✅ 高质量最佳实践配置 | ✅ 高质量最佳实践配置 |
| **配置合并** | 无 | 简单覆盖 | ✅ 智能选择性合并 | ✅ 智能选择性合并 |
| **提示词长度** | 无规范 | 无规范 | ✅ Simple < Medium < Complex | ✅ Simple < Medium < Complex |
| **运营容错** | 配置错误即失败 | 基础兜底 | ✅ 高质量兜底保障 | ✅ 高质量兜底保障 |
| **代码行数** | ~15K | ~18K | ~20K | ~20K (+200 行压缩模块) |

---

## 核心设计原则

### 1. 配置优先级驱动（V6.2 核心新增）

```
┌────────────────────────────────────────────────────────────────────────┐
│                  V6.2 配置优先级驱动机制                                │
├────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   核心哲学：运营配置 → 智能推断 → 高质量兜底                             │
│                                                                         │
│   ┌─────────────────────────────────────────────────────────────────┐  │
│   │  运营人员只需配置关心的字段                                       │  │
│   │  • model: claude-sonnet-4-5                                      │  │
│   │  • max_turns: 20                                                 │  │
│   │  • plan_manager_enabled: true                                    │  │
│   │  • （其他字段留空 → 自动使用最佳默认值）                         │  │
│   └──────────────────────────┬──────────────────────────────────────┘  │
│                              │                                          │
│                              ▼ _merge_config_to_schema()                │
│                              │                                          │
│   ┌─────────────────────────────────────────────────────────────────┐  │
│   │  合并后的 AgentSchema                                            │  │
│   │  • 运营配置字段 → 使用运营值                                     │  │
│   │  • 未配置字段 → 使用 LLM 推断或 DEFAULT_AGENT_SCHEMA            │  │
│   │  • 结果：高质量、稳定、符合场景的 Agent 配置                     │  │
│   └─────────────────────────────────────────────────────────────────┘  │
│                                                                         │
│   关键价值：即使运营配置不全/错误，Agent 也能正常运行                   │
│                                                                         │
└────────────────────────────────────────────────────────────────────────┘
```

### 2. Prompt-Driven Agent Instantiation（V6.1 核心）

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

### 3. Prompt-First 原则

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

### 4. 用空间换时间原则

| 阶段 | 开销 | 频率 | 优化收益 |
|------|------|------|---------|
| 启动时 LLM 分解 | ~3-5分钟（首次）| 一次 | 换取运行时零开销 |
| 启动时加载缓存 | <100ms | 每次启动 | 快速启动 |
| 运行时取缓存 | <1ms | 每次请求 | 节省 ~500ms/请求 |

### 5. Memory-First Protocol

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
# V6.2 启动时配置合并流程（核心代码）
from core.prompt import load_instance_cache
from core.schemas import DEFAULT_AGENT_SCHEMA

# 1. 加载 InstancePromptCache（包含 LLM 推断的 Schema）
prompt_cache = await load_instance_cache(
    instance_name=instance_name,
    raw_prompt=instance_prompt,
    config=config.raw_config,
    force_refresh=False
)

# 2. 获取基础 Schema（LLM 推断 或 DEFAULT_AGENT_SCHEMA 兜底）
base_schema = prompt_cache.agent_schema or DEFAULT_AGENT_SCHEMA

# 3. 🆕 V6.2: 智能配置合并（config.yaml 覆盖 Schema）
merged_schema = _merge_config_to_schema(base_schema, config)

# 4. 使用合并后的 Schema 创建 Agent
agent = AgentFactory.from_schema(
    schema=merged_schema,
    prompt_cache=prompt_cache,
    ...
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
│ Phase 3: 🆕 历史消息智能裁剪（L2 策略）                     │
├───────────────────────────────────────────────────────────┤
│ from core.context.compaction import trim_history_messages │
│                                                           │
│ 裁剪逻辑：                                                 │
│   • 保留首轮对话（任务定义）                               │
│   • 保留最近 N 轮（当前工作上下文）                        │
│   • 保留关键 tool_result（数据和结果）                     │
│   • 中间轮次丢弃细节，保留摘要                             │
│                                                           │
│ 🆕 V6.3: 自动处理 + 透明反馈（类似 Cursor）                │
└───────────────────────────────────────────────────────────┘
            │
            ▼
┌───────────────────────────────────────────────────────────┐
│ Phase 4: 系统提示词组装（含 L1 Memory 指导）               │
├───────────────────────────────────────────────────────────┤
│ _prompt_cache.get_system_prompt(complexity)               │
│   → complex_prompt.md  ◄─ 从 prompt_results 加载          │
│                                                           │
│ 🆕 L1 策略：注入 Memory Tool 使用指导                      │
│   from core.context.compaction import get_memory_guidance_prompt│
│   → 指导 Claude 主动使用 memory 工具保存重要状态          │
│                                                           │
│ 注入：                                                     │
│   • 🆕 Memory Tool 使用指导（L1）                          │
│   • 用户画像（如果检索了 Mem0）                            │
│   • Skills 元数据                                          │
│   • 能力分类描述                                           │
└───────────────────────────────────────────────────────────┘
            │
            ▼
┌───────────────────────────────────────────────────────────┐
│ Phase 5: RVR 循环执行（Sonnet，强+准确）                    │
├───────────────────────────────────────────────────────────┤
│ for turn in range(max_turns):                             │
│   [Read]   → plan_memory.get_plan()                       │
│   [Reason] → LLM Extended Thinking                        │
│   [Act]    → Tool Execution                               │
│   [Observe]→ 观察结果                                      │
│   [Validate]→验证质量                                      │
│   [Write]  → plan_memory.update_step()                    │
│                                                           │
│   🆕 L3 策略：后端监控 + 可选用户通知                      │
│   if should_warn_backend(estimated_tokens):               │
│      logger.warning("⚠️ Token 使用预警")  # 仅日志         │
│                                                           │
│ 性能优势：                                                 │
│   • 意图提示词：0ms（从 prompt_results 取）                │
│   • 系统提示词：0ms（从 prompt_results 取）                │
│   • 🆕 历史消息裁剪：<10ms（服务层自动）                   │
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

**事件类型**（7 类）：

| 事件类别 | 文件 | 说明 |
|---------|------|------|
| message_events | `message_events.py` | 消息相关事件 |
| content_events | `content_events.py` | 内容生成事件 |
| session_events | `session_events.py` | 会话管理事件 |
| user_events | `user_events.py` | 用户操作事件 |
| system_events | `system_events.py` | 系统状态事件 |
| conversation_events | `conversation_events.py` | 对话流程事件 |
| 🆕 context_events | `context_events.py` | **V6.3 上下文管理事件** |

### 🆕 上下文事件系统（V6.3）

**文件**：`core/events/context_events.py`

**职责**：
- 上下文管理操作的透明化反馈
- 告知用户系统正在做什么（类似 Cursor 的 "Chat context summarized"）
- 提供优化统计（节省的 tokens、保留的消息数等）

**核心事件类型**：

```python
class ContextEventType(str, Enum):
    """上下文管理事件类型"""
    CONTEXT_USAGE_UPDATE = "context_usage_update"        # 🆕 上下文使用更新（实时）
    CONTEXT_TRIMMING_START = "context_trimming_start"    # 开始裁剪
    CONTEXT_TRIMMING_DONE = "context_trimming_done"      # 裁剪完成
    CONTEXT_COMPACTION_START = "context_compaction_start"  # 开始压缩
    CONTEXT_COMPACTION_DONE = "context_compaction_done"    # 压缩完成
    CONTEXT_BUDGET_WARNING = "context_budget_warning"      # Token 预算警告

@dataclass
class ContextUsageUpdateEvent:
    """
    上下文使用更新事件（实时）
    
    用于驱动上下文进度条更新（类似 Cursor）
    
    前端展示示例：
    ┌───────────────────────────────────────────────────┐
    │ 上下文: ████████░░░░░░░░ 45%  (90K / 200K tokens) │
    └───────────────────────────────────────────────────┘
    """
    event_type: ContextEventType = ContextEventType.CONTEXT_USAGE_UPDATE
    timestamp: datetime
    
    # 使用情况
    current_tokens: int         # 当前使用 tokens
    budget_tokens: int          # 总预算 tokens
    usage_percentage: float     # 使用百分比 (0-1)
    
    # 颜色等级（用于前端渲染）
    color_level: str            # "green" / "yellow" / "orange" / "red"
    
    # 统计信息
    message_count: int          # 当前消息数
    turn_count: int             # 对话轮次数
    
    # 可选的建议
    suggestion: Optional[str] = None  # 如 "建议新开对话"（极少触发）


@dataclass
class ContextTrimmingEvent:
    """
    上下文裁剪事件
    
    前端展示示例（类似 Cursor）：
    ┌────────────────────────────────────────────────────┐
    │ ✓ 对话历史已智能优化，保留 15 条关键消息            │
    │ 已节省约 50,000 tokens，保持流畅对话  了解更多 >   │
    └────────────────────────────────────────────────────┘
    """
    event_type: ContextEventType
    timestamp: datetime
    
    # 裁剪统计
    original_messages: int      # 原始消息数
    trimmed_messages: int       # 裁剪后消息数
    preserved_turns: int        # 保留的对话轮次
    
    # 优化效果
    tokens_before: Optional[int] = None
    tokens_after: Optional[int] = None
    tokens_saved: Optional[int] = None
    
    # 用户可读消息
    display_message: str = "对话历史已智能优化，保留关键上下文"
    details: Optional[str] = None
    learn_more_url: Optional[str] = "/docs/context-management"
```

**使用示例**（在 ChatService 中）：

```python
# services/chat_service.py

async def chat(self, message: str, user_id: str, **kwargs):
    """聊天主流程"""
    
    # ... 处理逻辑 ...
    
    # 1. 🆕 发送上下文使用更新事件（驱动进度条）
    current_tokens = estimate_tokens(messages)
    usage_percentage = current_tokens / self.context_strategy.token_budget
    
    # 根据使用率确定颜色
    if usage_percentage < 0.6:
        color_level = "green"
    elif usage_percentage < 0.8:
        color_level = "yellow"
    elif usage_percentage < 0.95:
        color_level = "orange"
    else:
        color_level = "red"
    
    await self.event_manager.emit_event(
        ContextUsageUpdateEvent(
            timestamp=datetime.now(),
            current_tokens=current_tokens,
            budget_tokens=self.context_strategy.token_budget,
            usage_percentage=usage_percentage,
            color_level=color_level,
            message_count=len(messages),
            turn_count=len(messages) // 2,
            suggestion="建议新开对话" if usage_percentage > 0.95 else None
        )
    )
    
    # 2. L2 裁剪完成后发送事件
    if trimming_occurred:
        await self.event_manager.emit_event(
            ContextTrimmingEvent(
                event_type=ContextEventType.CONTEXT_TRIMMING_DONE,
                timestamp=datetime.now(),
                original_messages=100,
                trimmed_messages=15,
                preserved_turns=12,
                tokens_before=50000,
                tokens_after=8000,
                tokens_saved=42000,
                display_message="✓ 对话历史已优化，保留 15 条关键消息",
                details="已节省约 42,000 tokens，保持流畅对话"
            )
        )
```

**前端展示效果**：

**1. 上下文进度条（持续显示）**：
```typescript
// 前端实时更新进度条
eventSource.addEventListener('context_usage_update', (event) => {
  const data = JSON.parse(event.data);
  
  updateContextProgressBar({
    percentage: data.usage_percentage * 100,
    current: data.current_tokens,
    budget: data.budget_tokens,
    colorLevel: data.color_level,
    messageCount: data.message_count
  });
  
  // 如果有建议，显示提示
  if (data.suggestion) {
    showSuggestion(data.suggestion);
  }
});
```

**2. 裁剪通知（临时显示）**：
- 淡灰色背景，顶部提示条
- 5 秒后自动淡出
- 不打断用户当前操作
- 可点击"了解更多"链接查看详情

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
│   ├── context/                    # 上下文管理
│   │   ├── compaction/             # 🔥 V6.3 上下文压缩模块
│   │   │   └── __init__.py         # 三层防护策略（~200行）
│   │   ├── context_engineering.py  # 上下文工程
│   │   ├── conversation.py         # 对话上下文
│   │   ├── fusion.py               # 上下文融合
│   │   ├── injector.py             # 上下文注入
│   │   ├── manager.py              # 上下文管理器
│   │   ├── prompt_manager.py       # Prompt 管理器
│   │   ├── provider.py             # 上下文提供商
│   │   ├── providers/              # 多种上下文提供商
│   │   ├── retriever.py            # 上下文检索器
│   │   └── runtime.py              # 运行时上下文
│   │
│   ├── prompt/                     # V6.1 提示词模块
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
│   │   ├── context_events.py       # 🔥 V6.3 上下文管理事件
│   │   ├── message_events.py       # 消息事件
│   │   ├── content_events.py       # 内容事件
│   │   ├── session_events.py       # 会话事件
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
│   ├── context_compaction.yaml     # 🔥 V6.3 上下文压缩配置
│   ├── llm_config/                 # LLM 配置
│   │   └── profiles.yaml           # 包含 prompt_decomposer
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
  allow_parallel_tools: false
  llm:
    enable_thinking: true
    thinking_budget: 10000
    max_tokens: 16384

# 🆕 V6.2 高级配置（可选，未配置则使用 DEFAULT_AGENT_SCHEMA 兜底）
advanced:
  intent_analyzer:
    enabled: true
    use_llm: true
  plan_manager:
    max_steps: 15
    granularity: "medium"
  output_formatter:
    default_format: "markdown"
    code_highlighting: true

mcp_tools:
  - name: text2flowchart
    server_url: "https://api.dify.ai/mcp/server/XXX/mcp"
    capability: "document_creation"

memory:
  mem0_enabled: true
  smart_retrieval: true

# Multi-Agent 配置
multi_agent:
  mode: "disabled"  # disabled / auto / enabled
```

**V6.2 配置优先级示例**：

| 配置字段 | config.yaml | LLM 推断 | DEFAULT_AGENT_SCHEMA | 最终值 | 优先级来源 |
|---------|-------------|---------|---------------------|-------|-----------|
| model | `claude-sonnet-4-5` | - | `claude-sonnet-4-5` | **claude-sonnet-4-5** | Level 1 (config) |
| max_turns | `20` | - | `15` | **20** | Level 1 (config) |
| plan_manager.max_steps | - | `10` | `15` | **10** | Level 2 (LLM) |
| output_formatter.format | - | - | `text` | **text** | Level 3 (default) |

**实际场景示例**：

**场景 1：运营只配置模型和轮数**

```yaml
# config.yaml（运营配置最少）
agent:
  model: "claude-sonnet-4-5-20250929"
  max_turns: 20
```

```
合并结果：
├─ model: claude-sonnet-4-5-20250929  ← config.yaml
├─ max_turns: 20                      ← config.yaml
├─ plan_manager.enabled: true         ← DEFAULT_AGENT_SCHEMA
├─ plan_manager.max_steps: 15         ← DEFAULT_AGENT_SCHEMA
├─ intent_analyzer.enabled: true      ← DEFAULT_AGENT_SCHEMA
└─ ... (其他 20+ 配置项都使用高质量默认值)
```

**场景 2：LLM 推断出高级配置，运营覆盖部分**

```yaml
# config.yaml
agent:
  model: "claude-sonnet-4-5-20250929"
  plan_manager_enabled: false  # 禁用计划管理器
```

```
合并结果：
├─ model: claude-sonnet-4-5-20250929  ← config.yaml
├─ plan_manager.enabled: false        ← config.yaml 覆盖
├─ intent_analyzer.enabled: true      ← LLM 推断（prompt 提到意图识别）
├─ tool_selector.strategy: "capability_based"  ← LLM 推断
└─ ... (其他使用 LLM 推断或默认值)
```

**场景 3：运营配置错误，框架兜底**

```yaml
# config.yaml（错误配置）
agent:
  model: "invalid-model-name"  # 错误的模型名
  max_turns: -1                # 非法值
```

```
合并结果（框架验证并修正）：
├─ model: "claude-sonnet-4-5-20250929"  ← 修正为默认值
├─ max_turns: 15                        ← 修正为默认值
├─ ⚠️ logger.warning("model 配置无效，使用默认值")
└─ ... (其他使用默认值)
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
- **🔥 context_compaction.yaml**：上下文压缩配置（三层防护策略）
- **llm_config/profiles.yaml**：LLM 配置（包含 `prompt_decomposer`）
- **storage.yaml**：存储配置

#### 🔥 上下文压缩配置（`config/context_compaction.yaml`）

**V6.3 新增**：统一管理上下文压缩策略，运营人员无需配置。

```yaml
# 上下文压缩配置（三层防护策略）
#
# 核心原则：
# 1. 用户体验和问答效果优先
# 2. 自动处理 + 透明反馈（类似 Cursor）
# 3. 非侵入式通知，不打断用户操作

# 默认 QoS 等级
default_qos_level: "pro"

# QoS 等级对应的 token 预算
qos_token_budgets:
  free: 50000        # 免费用户
  basic: 150000      # 基础付费
  pro: 200000        # 专业版（默认）
  enterprise: 1000000  # 企业版

# L2 策略：历史消息裁剪配置
history_trimming:
  max_history_messages: 50   # 最大保留消息数
  preserve_first_n: 2        # 始终保留前 N 轮（建立上下文）
  preserve_last_n: 10        # 始终保留最近 N 轮（当前上下文）
  preserve_tool_results: true  # 保留含 tool_result 的消息

# L3 策略：后端预警配置
backend_warning:
  warning_threshold: 0.8     # 80% 时后端日志警告
  enable_metrics: true       # 启用 token 使用统计

# 🆕 V6.3: 用户通知配置
user_notifications:
  # 是否启用上下文管理通知
  enable_notifications: true
  
  # 通知级别
  # - silent: 完全静默（仅后端日志）
  # - minimal: 仅关键操作（压缩/大量裁剪）
  # - detailed: 所有操作（推荐，类似 Cursor）
  notification_level: "detailed"
  
  # 🆕 上下文进度条配置
  progress_bar:
    enabled: true              # 是否显示进度条
    position: "top"            # top / bottom / sidebar
    show_percentage: true      # 显示百分比
    show_tokens: true          # 显示 token 数值
    update_frequency: "realtime"  # realtime / on_message
    
    # 颜色阈值（百分比）
    color_thresholds:
      green_max: 60            # 0-60% 绿色
      yellow_max: 80           # 60-80% 黄色
      orange_max: 95           # 80-95% 橙色
      # 95-100% 红色
  
  # 裁剪/压缩通知配置
  trimming_notifications:
    show_tokens_saved: true    # 显示节省的 tokens
    show_preserved_count: true # 显示保留的消息数
    auto_dismiss_seconds: 5    # 自动消失时间（秒）
    
    # 通知样式
    style:
      position: "top"          # top / bottom
      theme: "subtle"          # subtle / prominent
      show_learn_more: true    # 显示"了解更多"链接
```

**环境变量支持**（极少数场景）：

```bash
# 如果需要调整 QoS 等级（极少数情况）
export QOS_LEVEL=enterprise  # 更宽松的上下文限制
export QOS_LEVEL=free        # 更严格的成本控制
```

**设计原则**：
- ✅ **开箱即用**：默认启用，运营人员无需配置
- ✅ **自动化 + 透明化**：自动处理 + 事件反馈（类似 Cursor）
- ✅ **非侵入式**：通知不打断用户，5秒后自动淡出
- ✅ **框架统一管理**：不暴露给实例配置，简化运营工作
- ✅ **问答效果优先**：智能保留关键上下文，不丢信息

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
| **V6.3** | 2026-01-14 | 🔥 **当前版本**：上下文压缩三层防护 + RVR 循环深化 + 用户体验优先 |
| V6.2 | 2026-01-13 | 三级配置优先级 + AgentSchema 智能兜底 + 提示词长度规范 |
| V6.1 | 2026-01-13 | 场景化提示词分解 + prompt_results 输出 + 动态更新检测 |
| V5.1 | 2026-01-11 | Mem0 多层画像 + 工具分层加载 + 语义推理模块 |
| V5.0 | 2026-01-09 | 实例级提示词缓存 + LLM 语义驱动 Schema |
| V4.6 | 2026-01-08 | 智能记忆检索决策 |
| V4.5 | 2026-01-07 | Mem0 用户画像层 |

---

**🎯 架构设计目标**：
- ✅ **🔥 透明化用户体验**：自动处理 + 事件反馈，用户知道发生了什么但无需操作
- ✅ **🔥 问答效果优先**：智能保留关键上下文，不丢信息
- ✅ **🔥 架构稳定性**：RVR 循环深化，不切换到 tool_runner
- ✅ **配置优先级**：config.yaml > LLM 推断 > DEFAULT_AGENT_SCHEMA
- ✅ **高质量兜底**：即使运营配置不全/错误，Agent 也能高质量运行
- ✅ **Prompt-Driven**：运营 prompt.md → LLM 分解 → 场景化提示词
- ✅ **运营可见可编辑**：prompt_results/ 目录，所有生成文件可直接修改
- ✅ **智能更新**：检测源文件变更，保护手动编辑
- ✅ **简洁清晰**：Service → SimpleAgent 直接调用
- ✅ **Prompt-First**：规则写在 Prompt 里，不写在代码里
- ✅ **开箱即用**：上下文管理默认启用，运营无需配置
- 📝 **预留扩展**：Multi-Agent 代码已预留，通过 mode 配置启用

**📌 维护原则**：
- 架构变更时，只需更新此文档
- 历史版本归档到 `archived/` 目录
- prompt_results/ 中的 README.md 同步更新
- 新增功能需同步更新相关文档（guides/、architecture/）

**🔗 相关文档**：
- [上下文压缩策略指南](../guides/context_compression_strategy.md) - V6.3 核心功能
- [上下文管理框架](./context_management_framework.md) - 技术架构
- [上下文管理架构决策](./context_management_decision.md) - 决策过程
- [架构优化路线图 V2](../reports/architecture_optimization_roadmap_v2.md) - 未来规划