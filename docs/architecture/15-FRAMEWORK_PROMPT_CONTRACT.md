# Prompt 驱动的 Agent 实例化机制

> 📅 **版本**: V2.0  
> 🎯 **核心思想**: Prompt → LLM 生成 Schema → 动态初始化 Agent  
> 🔗 **本质**: Prompt 驱动编程（Prompt-Driven Programming）

---

## 📋 目录

- [核心理念](#核心理念)
- [Prompt → Schema → Agent 流程](#prompt--schema--agent-流程)
- [动态初始化机制](#动态初始化机制)
- [实现方案](#实现方案)
- [完整示例](#完整示例)

---

## 🎯 核心理念

### Prompt 驱动编程

**传统方式 vs Prompt 驱动方式**：

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    两种架构模式对比                                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   ❌ 传统方式（静态配置）                                                     │
│   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│                                                                              │
│   1. 开发者定义 Schema（YAML/JSON 配置）                                     │
│   2. 框架根据 Schema 初始化 Agent                                            │
│   3. Prompt 只是"使用说明书"                                                 │
│                                                                              │
│   问题：                                                                     │
│   • Schema 修改需要改代码/配置文件                                           │
│   • 不够灵活，无法根据用户需求动态调整                                       │
│   • Prompt 和 Schema 可能不一致                                              │
│                                                                              │
│   ✅ Prompt 驱动方式（动态生成）                                             │
│   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│                                                                              │
│   1. 用户/开发者编写 Prompt（描述需求和规则）                                │
│   2. LLM 根据 Prompt 生成 Schema                                             │
│   3. 框架根据生成的 Schema 动态初始化 Agent                                  │
│                                                                              │
│   优势：                                                                     │
│   • 修改 Prompt 即可改变 Agent 行为                                          │
│   • 极致灵活，可以为不同用户定制不同的 Agent                                 │
│   • Prompt 是唯一的真相来源（Single Source of Truth）                       │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 完整流程

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                  Prompt 驱动的 Agent 实例化流程                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   Step 1: 用户/开发者编写 System Prompt                                      │
│   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│   ┌────────────────────────────────────────────────────────────────────┐   │
│   │ SYSTEM_PROMPT = """                                                │   │
│   │ 你是一个数据分析助手。                                            │   │
│   │                                                                    │   │
│   │ ## 意图识别规则                                                   │   │
│   │ - 复杂度判断：涉及多步骤或需要计划的任务为 high                   │   │
│   │ - 输出格式：分析任务类型并识别用户期望的输出格式                 │   │
│   │                                                                    │   │
│   │ ## 工具选择策略                                                   │   │
│   │ - 需要 pandas/numpy → 使用 E2B Sandbox                            │   │
│   │ - 需要生成 Excel → 使用 xlsx Skill                                │   │
│   │                                                                    │   │
│   │ ## 输出要求                                                       │   │
│   │ - 分析结果输出为 JSON 格式                                        │   │
│   │ - 包含推理过程                                                    │   │
│   │ """                                                                │   │
│   └────────────────────────────────────────────────────────────────────┘   │
│                                      │                                       │
│                                      ▼                                       │
│   Step 2: LLM 根据 Prompt 生成 Schema（或使用默认 Schema）                   │
│   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│   ┌────────────────────────────────────────────────────────────────────┐   │
│   │ # 框架调用 LLM 分析 Prompt 并生成 Schema                          │   │
│   │ schema_response = await llm.create_message(                       │   │
│   │     system=SCHEMA_GENERATOR_PROMPT,                                │   │
│   │     messages=[{                                                    │   │
│   │         "role": "user",                                            │   │
│   │         "content": f"分析以下 Prompt 并生成 Agent Schema:\n"      │   │
│   │                    f"{SYSTEM_PROMPT}"                              │   │
│   │     }]                                                             │   │
│   │ )                                                                  │   │
│   │                                                                    │   │
│   │ # LLM 输出 Schema                                                  │   │
│   │ agent_schema = {                                                   │   │
│   │     "name": "DataAnalysisAgent",                                   │   │
│   │     "description": "数据分析助手",                                 │   │
│   │     "components": {                                                │   │
│   │         "intent_analyzer": {                                       │   │
│   │             "enabled": true,                                       │   │
│   │             "complexity_levels": ["low", "medium", "high"],        │   │
│   │             "output_formats": ["text", "excel", "json"]            │   │
│   │         },                                                         │   │
│   │         "plan_manager": {                                          │   │
│   │             "enabled": true,                                       │   │
│   │             "trigger_condition": "complexity == high"              │   │
│   │         },                                                         │   │
│   │         "tool_selector": {                                         │   │
│   │             "available_tools": ["e2b_sandbox", "xlsx"],            │   │
│   │             "selection_strategy": "capability_based"               │   │
│   │         },                                                         │   │
│   │         "memory_manager": {                                        │   │
│   │             "enabled": true,                                       │   │
│   │             "retention_policy": "session"                          │   │
│   │         }                                                          │   │
│   │     },                                                             │   │
│   │     "skills": [                                                    │   │
│   │         {"type": "anthropic", "skill_id": "xlsx"}                 │   │
│   │     ],                                                             │   │
│   │     "max_turns": 10,                                               │   │
│   │     "allow_parallel_tools": false                                  │   │
│   │ }                                                                  │   │
│   └────────────────────────────────────────────────────────────────────┘   │
│                                      │                                       │
│                                      ▼                                       │
│   Step 3: 框架根据 Schema 动态初始化 Agent                                   │
│   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│   ┌────────────────────────────────────────────────────────────────────┐   │
│   │ # AgentFactory 根据 Schema 构建 Agent                             │   │
│   │ agent = AgentFactory.from_schema(                                  │   │
│   │     schema=agent_schema,                                           │   │
│   │     system_prompt=SYSTEM_PROMPT                                    │   │
│   │ )                                                                  │   │
│   │                                                                    │   │
│   │ # 初始化各个组件（根据 Schema 配置）                               │   │
│   │ agent.intent_analyzer = IntentAnalyzer(                            │   │
│   │     complexity_levels=schema["components"]["intent_analyzer"][    │   │
│   │         "complexity_levels"                                        │   │
│   │     ]                                                              │   │
│   │ )                                                                  │   │
│   │                                                                    │   │
│   │ agent.plan_manager = PlanManager(                                  │   │
│   │     trigger_condition=schema["components"]["plan_manager"][       │   │
│   │         "trigger_condition"                                        │   │
│   │     ]                                                              │   │
│   │ )                                                                  │   │
│   │                                                                    │   │
│   │ agent.tool_selector = ToolSelector(                                │   │
│   │     available_tools=schema["components"]["tool_selector"][        │   │
│   │         "available_tools"                                          │   │
│   │     ]                                                              │   │
│   │ )                                                                  │   │
│   │                                                                    │   │
│   │ # 配置 Skills                                                      │   │
│   │ agent.skills = schema["skills"]                                    │   │
│   │                                                                    │   │
│   │ # 配置运行时参数                                                   │   │
│   │ agent.max_turns = schema["max_turns"]                              │   │
│   └────────────────────────────────────────────────────────────────────┘   │
│                                      │                                       │
│                                      ▼                                       │
│   Step 4: Agent 运行（按 Prompt 规则 + Schema 配置执行）                     │
│   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│   ┌────────────────────────────────────────────────────────────────────┐   │
│   │ # Agent 执行用户请求                                               │   │
│   │ async for event in agent.chat(user_messages):                     │   │
│   │     # Agent 内部根据 Schema 配置和 Prompt 规则决策                 │   │
│   │     yield event                                                    │   │
│   └────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 关键优势

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    Prompt 驱动架构的核心优势                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   1. 极致灵活性                                                              │
│   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│   • 修改 Prompt → LLM 生成新 Schema → Agent 行为改变                        │
│   • 无需修改代码或配置文件                                                   │
│   • 可以为不同用户/场景定制不同的 Agent                                      │
│                                                                              │
│   示例：                                                                     │
│   - 企业用户：Prompt 强调"需要审批流程" → Schema 包含审批组件               │
│   - 个人用户：Prompt 强调"快速响应" → Schema 简化流程                       │
│                                                                              │
│   2. 一致性保证                                                              │
│   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│   • Prompt 是唯一的真相来源（Single Source of Truth）                      │
│   • Schema 自动根据 Prompt 生成，不会不一致                                 │
│   • Agent 行为严格遵循 Prompt 描述                                          │
│                                                                              │
│   3. 智能默认值                                                              │
│   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│   • Prompt 未明确说明的部分 → 使用智能默认 Schema                           │
│   • LLM 根据 Prompt 上下文推断合理配置                                      │
│   • 开发者无需考虑每个细节                                                   │
│                                                                              │
│   示例：                                                                     │
│   - Prompt 提到"数据分析" → LLM 自动启用 E2B Sandbox                        │
│   - Prompt 提到"生成报告" → LLM 自动启用 Plan Manager                       │
│                                                                              │
│   4. 可解释性                                                                │
│   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│   • Schema 包含推理过程（为什么这样配置）                                    │
│   • 开发者可以理解 LLM 的决策逻辑                                           │
│   • 便于调试和优化                                                           │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 🔄 Prompt → Schema → Agent 流程

### Schema 生成 Prompt

框架需要一个"元 Prompt"来引导 LLM 生成 Schema：

```python
# prompts/schema_generator_prompt.py

SCHEMA_GENERATOR_PROMPT = """
# Agent Schema 生成器

你是一个 Agent 架构专家。根据用户提供的 System Prompt，生成一个完整的 Agent Schema 配置。

## 任务

分析 System Prompt 的内容，推断出最合适的 Agent 配置，包括：
1. 需要启用哪些组件（IntentAnalyzer, PlanManager, ToolSelector, MemoryManager）
2. 每个组件的配置参数
3. 需要哪些 Skills 和 Tools
4. 运行时参数（max_turns, allow_parallel_tools 等）

## 分析维度

### 1. Intent Analyzer 配置
- 如果 Prompt 提到"复杂度"或"计划" → enabled=true
- 根据 Prompt 推断支持的输出格式（text/excel/ppt/pdf）
- 根据 Prompt 推断任务类型分类

### 2. Plan Manager 配置
- 如果 Prompt 提到"多步骤"、"计划"、"规划" → enabled=true
- 根据 Prompt 推断触发计划的条件
- 根据 Prompt 推断计划的粒度（fine/medium/coarse）

### 3. Tool Selector 配置
- 根据 Prompt 中提到的能力推断所需工具：
  - 提到"数据分析"、"pandas" → e2b_sandbox
  - 提到"搜索"、"查找" → web_search
  - 提到"Excel"、"表格" → xlsx Skill
  - 提到"PPT"、"演示" → pptx Skill
  
### 4. Skills 配置
- 根据 Prompt 推断需要的 Skills
- 优先使用 Pre-built Skills（xlsx/pptx/pdf/docx）
- 如果 Prompt 提到自定义能力 → 标记为 custom_skill

### 5. 运行时参数
- 简单任务 → max_turns=5
- 复杂任务 → max_turns=10-15
- 根据 Prompt 判断是否允许并行工具调用

## 输出格式

输出一个 JSON 格式的 Schema，必须包含以下结构：

```json
{
  "name": "string",  // Agent 名称（根据 Prompt 推断）
  "description": "string",  // Agent 描述
  "components": {
    "intent_analyzer": {
      "enabled": boolean,
      "complexity_levels": ["low", "medium", "high"],
      "task_types": [string],  // 支持的任务类型
      "output_formats": [string]  // 支持的输出格式
    },
    "plan_manager": {
      "enabled": boolean,
      "trigger_condition": string,  // 触发条件（表达式）
      "max_steps": integer,
      "granularity": "fine|medium|coarse"
    },
    "tool_selector": {
      "enabled": true,  // 总是启用
      "available_tools": [string],  // 工具列表
      "selection_strategy": "capability_based|explicit",
      "allow_parallel": boolean
    },
    "memory_manager": {
      "enabled": boolean,
      "retention_policy": "session|persistent|hybrid",
      "episodic_memory": boolean,
      "working_memory_limit": integer
    }
  },
  "skills": [
    {
      "type": "anthropic|custom",
      "skill_id": string,
      "version": "latest"
    }
  ],
  "tools": [string],  // E2B, web_search 等标准工具
  "max_turns": integer,
  "allow_parallel_tools": boolean,
  "context_limits": {
    "max_context_tokens": integer,
    "warning_threshold": float  // 0.0-1.0
  },
  "reasoning": string  // 🔑 说明为什么这样配置（可解释性）
}
```

## 示例

### 输入 System Prompt:
"你是一个数据分析助手，专门帮助用户分析 CSV 数据并生成 Excel 报表。"

### 输出 Schema:
```json
{
  "name": "DataAnalysisAgent",
  "description": "数据分析助手，专注于CSV分析和Excel报表生成",
  "components": {
    "intent_analyzer": {
      "enabled": true,
      "complexity_levels": ["low", "medium", "high"],
      "task_types": ["data_analysis", "document_generation"],
      "output_formats": ["text", "excel", "json"]
    },
    "plan_manager": {
      "enabled": true,
      "trigger_condition": "complexity == 'high' or output_format == 'excel'",
      "max_steps": 8,
      "granularity": "medium"
    },
    "tool_selector": {
      "enabled": true,
      "available_tools": ["e2b_sandbox", "xlsx"],
      "selection_strategy": "capability_based",
      "allow_parallel": false
    },
    "memory_manager": {
      "enabled": true,
      "retention_policy": "session",
      "episodic_memory": false,
      "working_memory_limit": 10
    }
  },
  "skills": [
    {"type": "anthropic", "skill_id": "xlsx", "version": "latest"}
  ],
  "tools": ["e2b_sandbox"],
  "max_turns": 10,
  "allow_parallel_tools": false,
  "context_limits": {
    "max_context_tokens": 200000,
    "warning_threshold": 0.8
  },
  "reasoning": "用户需求明确为数据分析+Excel生成，因此启用E2B Sandbox（数据处理）和xlsx Skill（报表生成）。由于涉及多步骤，启用Plan Manager。max_turns设为10以支持复杂分析流程。"
}
```

## 默认策略

如果 Prompt 中没有明确说明某些方面，使用以下默认值：
- intent_analyzer: enabled=true（总是启用）
- plan_manager: enabled=false（除非 Prompt 明确需要计划）
- tool_selector: enabled=true（总是启用）
- memory_manager: enabled=true, retention_policy="session"
- max_turns: 8
- allow_parallel_tools: false（除非 Prompt 明确要求并行）

## 注意事项

1. 优先根据 Prompt 的**明确描述**推断配置
2. 对于模糊或未提及的部分，使用**保守的默认值**
3. 在 `reasoning` 字段中**解释配置理由**
4. 如果 Prompt 中有矛盾，优先**用户安全和体验**
5. Skills 列表应该**尽量精简**（利于 Prompt Cache）

现在，请分析用户提供的 System Prompt 并生成 Agent Schema。
"""
```

### Schema 验证器

```python
# core/schemas/validator.py

from typing import Dict, Any, List
from pydantic import BaseModel, Field, validator


class ComponentConfig(BaseModel):
    """组件配置基类"""
    enabled: bool = True


class IntentAnalyzerConfig(ComponentConfig):
    """意图分析器配置"""
    complexity_levels: List[str] = Field(default=["low", "medium", "high"])
    task_types: List[str] = Field(default_factory=list)
    output_formats: List[str] = Field(default=["text"])


class PlanManagerConfig(ComponentConfig):
    """计划管理器配置"""
    trigger_condition: str = "complexity == 'high'"
    max_steps: int = 10
    granularity: str = "medium"


class ToolSelectorConfig(ComponentConfig):
    """工具选择器配置"""
    available_tools: List[str] = Field(default_factory=list)
    selection_strategy: str = "capability_based"
    allow_parallel: bool = False


class MemoryManagerConfig(ComponentConfig):
    """记忆管理器配置"""
    retention_policy: str = "session"
    episodic_memory: bool = False
    working_memory_limit: int = 10


class SkillConfig(BaseModel):
    """Skill 配置"""
    type: str = "anthropic"  # anthropic | custom
    skill_id: str
    version: str = "latest"


class ContextLimitsConfig(BaseModel):
    """上下文限制配置"""
    max_context_tokens: int = 200000
    warning_threshold: float = 0.8


class AgentSchema(BaseModel):
    """
    Agent Schema
    
    由 LLM 根据 System Prompt 生成，或使用默认值
    """
    
    name: str = Field(description="Agent 名称")
    description: str = Field(description="Agent 描述")
    
    # 组件配置
    components: Dict[str, Any] = Field(description="各组件配置")
    
    # Skills 和 Tools
    skills: List[SkillConfig] = Field(default_factory=list)
    tools: List[str] = Field(default_factory=list)
    
    # 运行时参数
    max_turns: int = Field(default=8, ge=1, le=50)
    allow_parallel_tools: bool = False
    
    # 上下文限制
    context_limits: ContextLimitsConfig = Field(default_factory=ContextLimitsConfig)
    
    # 推理说明
    reasoning: str = Field(description="配置理由（可解释性）")
    
    @validator("components")
    def validate_components(cls, v):
        """验证组件配置"""
        required_components = ["intent_analyzer", "tool_selector"]
        for comp in required_components:
            if comp not in v:
                raise ValueError(f"缺少必需组件: {comp}")
        return v


# 默认 Schema
DEFAULT_AGENT_SCHEMA = AgentSchema(
    name="GeneralAgent",
    description="通用智能助手",
    components={
        "intent_analyzer": IntentAnalyzerConfig().dict(),
        "plan_manager": PlanManagerConfig(enabled=False).dict(),
        "tool_selector": ToolSelectorConfig().dict(),
        "memory_manager": MemoryManagerConfig().dict(),
    },
    skills=[],
    tools=[],
    max_turns=8,
    allow_parallel_tools=False,
    reasoning="默认配置，适用于一般场景"
)
```

---

## 🛠️ 动态初始化机制

### AgentFactory 实现

```python
# core/agent/factory.py

from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class AgentFactory:
    """
    Agent 工厂
    
    根据 Prompt 和 Schema 动态构建 Agent
    """
    
    @classmethod
    async def from_prompt(
        cls,
        system_prompt: str,
        llm_service: Optional[LLMService] = None,
        use_default_if_failed: bool = True
    ) -> "SimpleAgent":
        """
        从 System Prompt 创建 Agent
        
        流程：
        1. 调用 LLM 根据 Prompt 生成 Schema
        2. 验证 Schema
        3. 根据 Schema 初始化 Agent
        
        Args:
            system_prompt: 系统提示词
            llm_service: LLM 服务（用于生成 Schema）
            use_default_if_failed: 如果生成失败，是否使用默认 Schema
        
        Returns:
            配置好的 Agent 实例
        """
        
        # 1. 生成 Schema
        try:
            schema = await cls._generate_schema(system_prompt, llm_service)
            logger.info(f"✅ 成功生成 Agent Schema: {schema.name}")
            logger.debug(f"Schema reasoning: {schema.reasoning}")
        except Exception as e:
            logger.error(f"❌ Schema 生成失败: {e}")
            if use_default_if_failed:
                logger.warning("使用默认 Schema")
                schema = DEFAULT_AGENT_SCHEMA
            else:
                raise
        
        # 2. 根据 Schema 初始化 Agent
        agent = cls.from_schema(schema, system_prompt)
        
        return agent
    
    @classmethod
    async def _generate_schema(
        cls,
        system_prompt: str,
        llm_service: Optional[LLMService] = None
    ) -> AgentSchema:
        """
        调用 LLM 生成 Schema
        """
        
        if llm_service is None:
            # 使用默认 LLM Service（通常是 Haiku，快速且便宜）
            llm_service = create_llm_service("claude-haiku-4-5-20251001")
        
        # 调用 LLM 生成 Schema
        response = await llm_service.create_message(
            system=SCHEMA_GENERATOR_PROMPT,
            messages=[{
                "role": "user",
                "content": f"请分析以下 System Prompt 并生成 Agent Schema:\n\n{system_prompt}"
            }],
            max_tokens=4096
        )
        
        # 提取 JSON
        schema_json = extract_json_from_response(response.content[0].text)
        
        # 验证并构造 Schema
        schema = AgentSchema.model_validate(schema_json)
        
        return schema
    
    @classmethod
    def from_schema(
        cls,
        schema: AgentSchema,
        system_prompt: str
    ) -> "SimpleAgent":
        """
        根据 Schema 构建 Agent
        
        这是核心方法：根据 Schema 动态初始化所有组件
        """
        
        logger.info(f"🏗️ 根据 Schema 初始化 Agent: {schema.name}")
        
        # 创建 Agent 实例
        agent = SimpleAgent(
            name=schema.name,
            description=schema.description,
            system_prompt=system_prompt,
            max_turns=schema.max_turns
        )
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 根据 Schema 初始化各个组件
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        # 1. Intent Analyzer
        if schema.components.get("intent_analyzer", {}).get("enabled", True):
            agent.intent_analyzer = cls._create_intent_analyzer(
                schema.components["intent_analyzer"]
            )
            logger.debug("✓ Intent Analyzer 已启用")
        
        # 2. Plan Manager
        if schema.components.get("plan_manager", {}).get("enabled", False):
            agent.plan_manager = cls._create_plan_manager(
                schema.components["plan_manager"]
            )
            logger.debug("✓ Plan Manager 已启用")
        else:
            agent.plan_manager = None
            logger.debug("○ Plan Manager 未启用")
        
        # 3. Tool Selector
        agent.tool_selector = cls._create_tool_selector(
            schema.components["tool_selector"],
            schema.tools
        )
        logger.debug(f"✓ Tool Selector 已启用 (工具: {schema.tools})")
        
        # 4. Memory Manager
        if schema.components.get("memory_manager", {}).get("enabled", True):
            agent.memory_manager = cls._create_memory_manager(
                schema.components["memory_manager"]
            )
            logger.debug("✓ Memory Manager 已启用")
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 配置 Skills 和 Tools
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        agent.skills = [skill.dict() for skill in schema.skills]
        agent.tools = schema.tools
        agent.allow_parallel_tools = schema.allow_parallel_tools
        
        logger.debug(f"✓ Skills: {[s.skill_id for s in schema.skills]}")
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 配置运行时参数
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        agent.context_limits = schema.context_limits
        
        logger.info(f"✅ Agent 初始化完成: {schema.name}")
        logger.info(f"   Schema reasoning: {schema.reasoning}")
        
        return agent
    
    @staticmethod
    def _create_intent_analyzer(config: Dict[str, Any]) -> IntentAnalyzer:
        """创建意图分析器"""
        return IntentAnalyzer(
            complexity_levels=config.get("complexity_levels", ["low", "medium", "high"]),
            task_types=config.get("task_types", []),
            output_formats=config.get("output_formats", ["text"])
        )
    
    @staticmethod
    def _create_plan_manager(config: Dict[str, Any]) -> PlanManager:
        """创建计划管理器"""
        return PlanManager(
            trigger_condition=config.get("trigger_condition", "complexity == 'high'"),
            max_steps=config.get("max_steps", 10),
            granularity=config.get("granularity", "medium")
        )
    
    @staticmethod
    def _create_tool_selector(config: Dict[str, Any], tools: List[str]) -> ToolSelector:
        """创建工具选择器"""
        return ToolSelector(
            available_tools=config.get("available_tools", tools),
            selection_strategy=config.get("selection_strategy", "capability_based"),
            allow_parallel=config.get("allow_parallel", False)
        )
    
    @staticmethod
    def _create_memory_manager(config: Dict[str, Any]) -> MemoryManager:
        """创建记忆管理器"""
        return MemoryManager(
            retention_policy=config.get("retention_policy", "session"),
            episodic_memory=config.get("episodic_memory", False),
            working_memory_limit=config.get("working_memory_limit", 10)
        )
```

### 使用示例

```python
# 示例 1: 从 Prompt 创建 Agent

# 用户编写的 System Prompt
CUSTOM_PROMPT = """
你是一个专门的数据分析助手。

## 核心能力
- 使用 pandas 分析 CSV/Excel 数据
- 生成带图表的 Excel 报表
- 提供统计分析和趋势预测

## 工作流程
1. 接收用户上传的数据文件
2. 进行数据清洗和预处理
3. 执行统计分析
4. 生成可视化图表
5. 导出为 Excel 报表

## 输出要求
- 分析结果必须包含推理过程
- Excel 报表必须包含数据透视表和图表
- 提供下载链接
"""

# 自动从 Prompt 创建 Agent
agent = await AgentFactory.from_prompt(CUSTOM_PROMPT)

# Agent 已经根据 Prompt 配置好了：
# - 启用了 E2B Sandbox（因为需要 pandas）
# - 启用了 xlsx Skill（因为需要生成 Excel）
# - 启用了 Plan Manager（因为有多步骤工作流程）
# - max_turns=10（因为任务较复杂）

# 直接使用
async for event in agent.chat([{"role": "user", "content": "分析这份销售数据"}]):
    print(event)
```

```python
# 示例 2: 不同 Prompt 生成不同的 Agent

# 简单问答 Agent
QA_PROMPT = """
你是一个知识问答助手，专门回答用户的问题。
保持回答简洁准确，不需要复杂的工具。
"""

qa_agent = await AgentFactory.from_prompt(QA_PROMPT)
# → Schema: plan_manager=False, tools=[], max_turns=5


# 复杂任务 Agent
COMPLEX_PROMPT = """
你是一个项目管理助手，需要：
1. 制定详细的项目计划
2. 跟踪任务进度
3. 生成项目报告（PPT 和 Excel）
4. 协调多个工具完成复杂任务
"""

complex_agent = await AgentFactory.from_prompt(COMPLEX_PROMPT)
# → Schema: plan_manager=True, skills=[pptx, xlsx], max_turns=15
```

---

## 📊 完整示例

### 端到端流程

```python
# main.py

import asyncio
from core.agent.factory import AgentFactory


async def main():
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Step 1: 定义 System Prompt
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    SYSTEM_PROMPT = """
    你是一个企业数据分析助手，专为业务分析师设计。
    
    ## 核心职责
    - 分析销售数据、财务数据、运营数据
    - 生成专业的分析报告（Excel 和 PPT）
    - 提供数据驱动的业务洞察
    
    ## 分析流程
    1. 数据清洗和验证
    2. 探索性数据分析（EDA）
    3. 计算关键指标（KPI）
    4. 生成可视化图表
    5. 撰写分析报告
    
    ## 输出标准
    - Excel 报表：包含数据透视表、图表、趋势分析
    - PPT 汇报：包含执行摘要、关键发现、建议
    - 分析过程：记录推理步骤，确保可解释性
    
    ## 质量要求
    - 数据准确性：所有计算必须验证
    - 专业性：使用业务术语和行业标准
    - 可操作性：提供具体的业务建议
    """
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Step 2: 从 Prompt 创建 Agent（自动生成 Schema）
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    print("🔧 正在根据 Prompt 生成 Agent Schema...")
    agent = await AgentFactory.from_prompt(SYSTEM_PROMPT)
    
    print(f"\n✅ Agent 创建成功: {agent.name}")
    print(f"   描述: {agent.description}")
    print(f"   Skills: {[s['skill_id'] for s in agent.skills]}")
    print(f"   Tools: {agent.tools}")
    print(f"   Max Turns: {agent.max_turns}")
    print(f"   Plan Manager: {'启用' if agent.plan_manager else '未启用'}")
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Step 3: 使用 Agent
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    user_query = """
    我有一份今年的销售数据CSV，包含每月的销售额、客户数、平均客单价。
    请帮我分析：
    1. 销售趋势如何？
    2. 哪些月份表现最好/最差？
    3. 客单价变化情况？
    
    然后生成一份Excel报表和一份PPT，用于向管理层汇报。
    """
    
    print(f"\n📝 用户查询: {user_query}\n")
    print("💬 Agent 响应:\n")
    
    async for event in agent.chat([{"role": "user", "content": user_query}]):
        if event.type == "content_block_delta":
            print(event.delta.text, end="", flush=True)
        elif event.type == "tool_use":
            print(f"\n🔧 使用工具: {event.name}")
        elif event.type == "file_generated":
            print(f"\n📄 文件生成: {event.file_path}")


if __name__ == "__main__":
    asyncio.run(main())
```

**运行输出**:

```
🔧 正在根据 Prompt 生成 Agent Schema...

✅ Agent 创建成功: EnterpriseDataAnalysisAgent
   描述: 企业数据分析助手，专为业务分析师提供数据洞察
   Skills: ['xlsx', 'pptx']
   Tools: ['e2b_sandbox']
   Max Turns: 12
   Plan Manager: 启用

📝 用户查询: 我有一份今年的销售数据CSV...

💬 Agent 响应:

我将帮您完成这个分析任务。这是一个复杂的多步骤任务，让我先制定一个详细计划。

[Plan Created]
- Step 1: 使用 E2B Sandbox 读取并清洗数据
- Step 2: 进行探索性数据分析
- Step 3: 计算关键指标和趋势
- Step 4: 生成 Excel 报表（包含图表）
- Step 5: 生成 PPT 汇报材料

正在执行...

🔧 使用工具: e2b_sandbox
正在分析数据...

分析完成！主要发现：
1. 销售趋势：整体上升，Q4 增长最快
2. 最佳月份：12月（节日促销效果显著）
   最差月份：2月（春节影响）
3. 客单价：稳步上升 8.5%

🔧 使用工具: xlsx_skill
正在生成 Excel 报表...

📄 文件生成: workspace/outputs/销售分析报表.xlsx

🔧 使用工具: pptx_skill
正在生成 PPT 汇报...

📄 文件生成: workspace/outputs/销售分析汇报.pptx

✅ 分析完成！已生成 Excel 报表和 PPT 汇报材料，请查收。
```

---

## 🎯 总结

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    Prompt 驱动架构核心原则                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   流程：Prompt → LLM 生成 Schema → 动态初始化 Agent                          │
│                                                                              │
│   优势：                                                                     │
│   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│   • 极致灵活：修改 Prompt 即可改变 Agent 行为                               │
│   • 零配置：LLM 自动推断最佳配置                                            │
│   • 可解释：Schema 包含配置理由                                             │
│   • 智能默认：未明确部分使用智能推断                                         │
│                                                                              │
│   职责分工：                                                                 │
│   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│   • 用户/开发者：编写 Prompt（描述需求）                                    │
│   • LLM：根据 Prompt 生成 Schema（推断配置）                                │
│   • 框架：根据 Schema 初始化 Agent（执行）                                  │
│   • Agent：按 Prompt 规则 + Schema 配置运行                                 │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 🔗 相关文档

- [00-ARCHITECTURE-V4.md](./00-ARCHITECTURE-V4.md) - V4 架构总览
- [13-INVOCATION_STRATEGY_V2.md](./13-INVOCATION_STRATEGY_V2.md) - 调用策略
- [14-CLAUDE_SKILLS_DEEP_DIVE.md](./14-CLAUDE_SKILLS_DEEP_DIVE.md) - Claude Skills 深度分析

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    框架（Framework）vs 系统提示词（System Prompt）            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   类比：编程语言 vs 程序代码                                                  │
│   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│                                                                              │
│   编程语言（Framework）            程序代码（System Prompt）                 │
│   ──────────────────────          ──────────────────────────               │
│   • 提供语法和关键字              • 使用语法编写具体逻辑                    │
│   • 定义数据类型                  • 创建具体变量和函数                      │
│   • 提供标准库                    • 调用库完成业务功能                      │
│   • 执行引擎                      • 业务规则和流程                          │
│                                                                              │
│   Agent Framework                  System Prompt                             │
│   ──────────────────────          ──────────────────────────               │
│   • 提供 Intent/Plan/Tool/Memory  • 定义何时使用这些能力                    │
│   • 定义 Schema 格式              • 指定具体的输入输出格式                  │
│   • 提供 RVR Loop 引擎            • 引导每个阶段的决策逻辑                  │
│   • 提供执行环境                  • 描述业务规则和约束                      │
│                                                                              │
│   关系：Framework 是"能力集"，Prompt 是"使用说明书"                         │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 三层架构

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         三层架构：框架 → 契约 → 策略                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   Layer 1: Framework Layer（框架层）                                         │
│   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│   职责：提供通用能力，不包含业务逻辑                                         │
│                                                                              │
│   • IntentAnalyzer：意图识别引擎（输入/输出格式由 Schema 定义）              │
│   • PlanManager：计划管理引擎（Plan/Todo 格式由 Schema 定义）               │
│   • ToolExecutor：工具执行引擎（工具定义由配置提供）                        │
│   • MemoryManager：记忆管理引擎（存储策略由配置提供）                       │
│   • RVR Loop：循环控制引擎（循环策略由 Prompt 引导）                        │
│                                                                              │
│   Layer 2: Schema Contract Layer（契约层）                                   │
│   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│   职责：定义框架与 Prompt 之间的"接口约定"                                   │
│                                                                              │
│   • IntentResult Schema：意图识别的输出格式                                  │
│   • PlanTodo Schema：计划的 JSON 格式                                        │
│   • ToolCall Schema：工具调用的参数格式                                      │
│   • Response Schema：最终响应的格式                                          │
│                                                                              │
│   Layer 3: Prompt Strategy Layer（策略层）                                   │
│   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│   职责：定义具体的业务规则和决策逻辑                                         │
│                                                                              │
│   • 意图识别策略：如何判断任务类型和复杂度                                   │
│   • 工具选择策略：何时使用 Skills/E2B/标准工具                              │
│   • 执行策略：如何编排多步骤任务                                             │
│   • 输出策略：如何格式化最终响应                                             │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 📝 Schema 契约机制

### 核心思想

**Schema 是框架与 Prompt 之间的"API 契约"**：
- 框架定义 Schema（输入/输出格式）
- Prompt 中引用 Schema（告诉 Claude 按格式输出）
- 框架解析 Claude 的输出（根据 Schema 提取结构化数据）

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Schema 契约工作流程                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   1. 框架定义 Schema                                                         │
│      ┌────────────────────────────────────────────────────────────────────┐ │
│      │ IntentResultSchema = {                                             │ │
│      │     "task_type": "string",      # 任务类型                         │ │
│      │     "complexity": "low|medium|high",                               │ │
│      │     "needs_plan": "boolean",                                       │ │
│      │     "required_capabilities": ["string"]                            │ │
│      │ }                                                                  │ │
│      └────────────────────────────────────────────────────────────────────┘ │
│                                      │                                       │
│                                      ▼                                       │
│   2. Prompt 引用 Schema                                                      │
│      ┌────────────────────────────────────────────────────────────────────┐ │
│      │ System Prompt:                                                     │ │
│      │ """                                                                │ │
│      │ ## 意图识别                                                        │ │
│      │                                                                    │ │
│      │ 分析用户请求后，输出以下 JSON 格式：                                │ │
│      │ ```json                                                            │ │
│      │ {                                                                  │ │
│      │     "task_type": "information_query|content_generation|...",      │ │
│      │     "complexity": "low|medium|high",                              │ │
│      │     "needs_plan": true/false,                                     │ │
│      │     "required_capabilities": ["web_search", "xlsx_generation"]    │ │
│      │ }                                                                  │ │
│      │ ```                                                                │ │
│      │ """                                                                │ │
│      └────────────────────────────────────────────────────────────────────┘ │
│                                      │                                       │
│                                      ▼                                       │
│   3. Claude 按 Schema 输出                                                   │
│      ┌────────────────────────────────────────────────────────────────────┐ │
│      │ Claude Response:                                                   │ │
│      │ ```json                                                            │ │
│      │ {                                                                  │ │
│      │     "task_type": "data_analysis",                                 │ │
│      │     "complexity": "medium",                                       │ │
│      │     "needs_plan": true,                                           │ │
│      │     "required_capabilities": ["xlsx_generation", "e2b_sandbox"]   │ │
│      │ }                                                                  │ │
│      │ ```                                                                │ │
│      └────────────────────────────────────────────────────────────────────┘ │
│                                      │                                       │
│                                      ▼                                       │
│   4. 框架解析并执行                                                          │
│      ┌────────────────────────────────────────────────────────────────────┐ │
│      │ intent = parse_intent_json(claude_response)                       │ │
│      │ if intent.needs_plan:                                              │ │
│      │     plan = await create_plan(intent)                              │ │
│      │ tools = select_tools(intent.required_capabilities)                 │ │
│      └────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Schema 定义示例

```python
# schemas/intent_schema.py

from typing import List, Literal, Optional
from pydantic import BaseModel, Field


class IntentResultSchema(BaseModel):
    """
    意图识别结果 Schema
    
    此 Schema 会被嵌入到 System Prompt 中，
    引导 Claude 按此格式输出意图分析结果。
    """
    
    task_type: Literal[
        "information_query",      # 信息查询
        "content_generation",     # 内容生成
        "data_analysis",          # 数据分析
        "code_task",              # 代码任务
        "app_creation",           # 应用创建
        "document_generation",    # 文档生成
        "other"                   # 其他
    ] = Field(description="任务类型")
    
    complexity: Literal["low", "medium", "high"] = Field(
        description="任务复杂度：low=简单对话，medium=需要工具，high=需要计划"
    )
    
    needs_plan: bool = Field(
        description="是否需要创建详细计划（medium/high 复杂度通常需要）"
    )
    
    required_capabilities: List[str] = Field(
        default_factory=list,
        description="完成任务需要的能力列表"
    )
    
    output_format: Optional[Literal["text", "excel", "ppt", "pdf", "word", "code"]] = Field(
        default="text",
        description="期望的输出格式"
    )
    
    reasoning: str = Field(
        description="分析理由（简短说明为什么这样判断）"
    )


# 生成 Prompt 中使用的 Schema 说明
def generate_schema_prompt(schema_class: type) -> str:
    """
    从 Pydantic Schema 自动生成 Prompt 中的格式说明
    """
    schema = schema_class.model_json_schema()
    
    # 简化的 JSON 示例
    example = {}
    for field_name, field_info in schema.get("properties", {}).items():
        if "enum" in field_info:
            example[field_name] = field_info["enum"][0]
        elif field_info.get("type") == "boolean":
            example[field_name] = True
        elif field_info.get("type") == "array":
            example[field_name] = ["example_item"]
        else:
            example[field_name] = f"<{field_name}>"
    
    return json.dumps(example, indent=2, ensure_ascii=False)
```

---

## ⚙️ 框架能力 vs Prompt 策略

### 能力与策略的分离

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    框架能力（What）vs Prompt 策略（How/When）                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   框架提供能力（Framework Capabilities）                                     │
│   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│                                                                              │
│   能力                     框架实现                    Prompt 引导           │
│   ────────────────        ──────────────              ──────────────        │
│   Intent Analysis         IntentAnalyzer.analyze()    何时判断为复杂任务？   │
│   Plan Management         PlanManager.create/update() 计划应包含哪些步骤？   │
│   Tool Execution          ToolExecutor.execute()      何时使用哪个工具？     │
│   Memory Storage          MemoryManager.store/get()   存储什么？存多久？     │
│   Skills Invocation       code_execution + container  何时生成文档？         │
│   E2B Sandbox             e2b_sandbox.run()           何时需要沙箱？         │
│                                                                              │
│   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│                                                                              │
│   框架代码示例（通用，不含业务逻辑）                                         │
│   ┌────────────────────────────────────────────────────────────────────┐   │
│   │ class IntentAnalyzer:                                              │   │
│   │     """意图分析器 - 框架只负责解析，不负责决策"""                   │   │
│   │                                                                    │   │
│   │     async def analyze(self, user_input: str) -> IntentResult:     │   │
│   │         # 1. 调用 LLM（决策逻辑在 System Prompt 中）               │   │
│   │         response = await self.llm.create_message(                  │   │
│   │             system=self.intent_prompt,  # ← Prompt 定义决策规则    │   │
│   │             messages=[{"role": "user", "content": user_input}]    │   │
│   │         )                                                          │   │
│   │                                                                    │   │
│   │         # 2. 解析结果（根据 Schema）                               │   │
│   │         intent_json = extract_json(response.content)              │   │
│   │         return IntentResultSchema.model_validate(intent_json)     │   │
│   └────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│   Prompt 策略示例（具体，包含业务逻辑）                                       │
│   ┌────────────────────────────────────────────────────────────────────┐   │
│   │ INTENT_ANALYSIS_PROMPT = """                                       │   │
│   │ ## 意图识别规则                                                    │   │
│   │                                                                    │   │
│   │ 分析用户请求，判断任务类型和复杂度：                                │   │
│   │                                                                    │   │
│   │ ### 复杂度判断标准                                                 │   │
│   │ - low: 简单问答、单步操作（如"今天天气"）                          │   │
│   │ - medium: 需要工具但步骤清晰（如"搜索xxx并总结"）                  │   │
│   │ - high: 多步骤、需要规划（如"分析数据并生成报告"）                 │   │
│   │                                                                    │   │
│   │ ### 输出格式判断                                                   │   │
│   │ - 用户要求 Excel/表格 → output_format: "excel"                    │   │
│   │ - 用户要求 PPT/演示 → output_format: "ppt"                        │   │
│   │ - 无特殊要求 → output_format: "text"                              │   │
│   │                                                                    │   │
│   │ ### 输出 JSON 格式                                                 │   │
│   │ {schema_example}                                                   │   │
│   │ """                                                                │   │
│   └────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### RVR Loop 中的框架 vs Prompt 职责

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    RVR Loop：框架执行 + Prompt 引导                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  User Input: "分析这份销售数据，生成一份带图表的 Excel 报表"                 │
│      │                                                                       │
│      ▼                                                                       │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │ Step 1: Intent Analysis                                              │   │
│  │                                                                       │   │
│  │   框架职责                        Prompt 职责                         │   │
│  │   ━━━━━━━━                        ━━━━━━━━                           │   │
│  │   • 调用 LLM                      • 定义判断规则                      │   │
│  │   • 解析 JSON 输出                • 定义输出格式                      │   │
│  │   • 验证 Schema                   • 提供示例和边界情况                │   │
│  │                                                                       │   │
│  │   输入: user_input                                                    │   │
│  │   输出: IntentResult {                                                │   │
│  │       task_type: "data_analysis",     ← Prompt 引导判断              │   │
│  │       complexity: "high",             ← Prompt 定义标准              │   │
│  │       needs_plan: true,               ← Prompt 定义何时需要 Plan     │   │
│  │       output_format: "excel",         ← Prompt 识别输出格式          │   │
│  │       required_capabilities: ["e2b_sandbox", "xlsx"]                 │   │
│  │   }                                                                   │   │
│  │                                                                       │   │
│  └───────────────────────────────────┬──────────────────────────────────┘   │
│                                      │                                       │
│                                      ▼                                       │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │ Step 2: Plan Creation（如果 needs_plan == true）                     │   │
│  │                                                                       │   │
│  │   框架职责                        Prompt 职责                         │   │
│  │   ━━━━━━━━                        ━━━━━━━━                           │   │
│  │   • 调用 LLM 生成 Plan            • 定义 Plan 的结构要求             │   │
│  │   • 解析并存储 plan.json          • 定义步骤粒度                      │   │
│  │   • 解析并存储 todo.md            • 定义依赖关系规则                  │   │
│  │                                                                       │   │
│  │   输出: plan.json + todo.md                                           │   │
│  │   ┌────────────────────────────────────────────────────────────────┐ │   │
│  │   │ {                                                              │ │   │
│  │   │   "goal": "分析销售数据并生成带图表的Excel报表",               │ │   │
│  │   │   "steps": [                                                   │ │   │
│  │   │     {"id": "1", "action": "使用E2B分析数据", "status": "todo"},│ │   │
│  │   │     {"id": "2", "action": "生成图表数据", "status": "todo"},   │ │   │
│  │   │     {"id": "3", "action": "使用xlsx生成报表", "status": "todo"}│ │   │
│  │   │   ]                                                            │ │   │
│  │   │ }                                                              │ │   │
│  │   └────────────────────────────────────────────────────────────────┘ │   │
│  │                                                                       │   │
│  └───────────────────────────────────┬──────────────────────────────────┘   │
│                                      │                                       │
│                                      ▼                                       │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │ Step 3: RVR Turn Loop                                                │   │
│  │                                                                       │   │
│  │   框架职责                        Prompt 职责                         │   │
│  │   ━━━━━━━━                        ━━━━━━━━                           │   │
│  │   • 控制循环流程                  • 引导 Claude 决策下一步            │   │
│  │   • 执行工具调用                  • 定义何时使用哪个工具              │   │
│  │   • 收集工具结果                  • 定义如何解读工具结果              │   │
│  │   • 更新 Plan 状态                • 定义何时标记步骤完成              │   │
│  │                                                                       │   │
│  │   Turn 1: [Read] plan.json → [Reason] 需要先分析数据                 │   │
│  │           [Act] e2b_sandbox.run(pandas_code)                         │   │
│  │           [Observe] 分析结果 → [Write] step 1 = done                 │   │
│  │                                                                       │   │
│  │   Turn 2: [Read] plan.json → [Reason] 数据已有，生成报表             │   │
│  │           [Act] xlsx Skill (通过 code_execution)                     │   │
│  │           [Observe] file_id → [Write] step 3 = done                  │   │
│  │                                                                       │   │
│  └───────────────────────────────────┬──────────────────────────────────┘   │
│                                      │                                       │
│                                      ▼                                       │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │ Step 4: Complete                                                     │   │
│  │                                                                       │   │
│  │   框架职责                        Prompt 职责                         │   │
│  │   ━━━━━━━━                        ━━━━━━━━                           │   │
│  │   • 下载生成的文件                • 定义最终响应格式                  │   │
│  │   • 发送完成事件                  • 定义总结内容                      │   │
│  │   • 清理临时资源                  • 定义用户引导语                    │   │
│  │                                                                       │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 🛠️ 实现方案

### 1. Schema 注册机制

```python
# core/schemas/registry.py

from typing import Dict, Type
from pydantic import BaseModel


class SchemaRegistry:
    """
    Schema 注册表
    
    管理所有框架与 Prompt 之间的契约 Schema
    """
    
    _schemas: Dict[str, Type[BaseModel]] = {}
    
    @classmethod
    def register(cls, name: str, schema: Type[BaseModel]):
        """注册一个 Schema"""
        cls._schemas[name] = schema
    
    @classmethod
    def get(cls, name: str) -> Type[BaseModel]:
        """获取 Schema"""
        return cls._schemas.get(name)
    
    @classmethod
    def generate_prompt_section(cls, name: str) -> str:
        """
        生成 Schema 对应的 Prompt 部分
        
        将 Pydantic Schema 转换为 Prompt 中的格式说明
        """
        schema = cls.get(name)
        if not schema:
            return ""
        
        # 获取 JSON Schema
        json_schema = schema.model_json_schema()
        
        # 生成字段说明
        fields_doc = []
        for field_name, field_info in json_schema.get("properties", {}).items():
            desc = field_info.get("description", "")
            field_type = field_info.get("type", "string")
            if "enum" in field_info:
                field_type = " | ".join(f'"{v}"' for v in field_info["enum"])
            fields_doc.append(f"  - {field_name} ({field_type}): {desc}")
        
        # 生成示例 JSON
        example = cls._generate_example(json_schema)
        
        return f"""
### {name} 输出格式

字段说明：
{chr(10).join(fields_doc)}

JSON 格式：
```json
{json.dumps(example, indent=2, ensure_ascii=False)}
```
"""
    
    @classmethod
    def _generate_example(cls, json_schema: dict) -> dict:
        """根据 Schema 生成示例 JSON"""
        example = {}
        for field_name, field_info in json_schema.get("properties", {}).items():
            if "enum" in field_info:
                example[field_name] = field_info["enum"][0]
            elif "default" in field_info:
                example[field_name] = field_info["default"]
            elif field_info.get("type") == "boolean":
                example[field_name] = True
            elif field_info.get("type") == "array":
                example[field_name] = ["item1", "item2"]
            elif field_info.get("type") == "integer":
                example[field_name] = 0
            else:
                example[field_name] = f"<{field_name}>"
        return example


# 注册 Schemas
SchemaRegistry.register("intent_result", IntentResultSchema)
SchemaRegistry.register("plan_json", PlanJsonSchema)
SchemaRegistry.register("tool_call", ToolCallSchema)
```

### 2. Prompt 模板与 Schema 绑定

```python
# prompts/intent_analysis_prompt.py

from core.schemas.registry import SchemaRegistry


class IntentAnalysisPrompt:
    """
    意图分析 Prompt
    
    将框架 Schema 与业务规则结合
    """
    
    @staticmethod
    def build() -> str:
        """构建完整的意图分析 Prompt"""
        
        # 获取 Schema 生成的格式说明
        schema_section = SchemaRegistry.generate_prompt_section("intent_result")
        
        # 业务规则部分（可独立配置/修改）
        rules_section = """
## 意图识别规则

### 任务类型判断
- **information_query**: 查询信息、搜索资料、获取知识
- **content_generation**: 写作、创作、生成文本内容
- **data_analysis**: 数据处理、统计分析、图表生成
- **document_generation**: 生成 Excel/PPT/PDF/Word 文档
- **code_task**: 编写代码、调试、重构
- **app_creation**: 创建 Web 应用、Dashboard

### 复杂度判断标准
- **low**: 
  - 简单问答（"什么是 xxx"）
  - 单步操作（"翻译这段话"）
  - 不需要工具
  
- **medium**: 
  - 需要使用工具但步骤清晰
  - 例如："搜索 xxx 并总结"
  - 通常 1-3 个工具调用
  
- **high**: 
  - 多步骤复杂任务
  - 需要制定计划
  - 例如："分析数据并生成报告"
  - 通常 3+ 个工具调用

### 何时需要 Plan
- complexity == "high" → needs_plan = true
- 多步骤依赖关系 → needs_plan = true
- 用户明确要求"规划" → needs_plan = true

### 能力识别
根据任务需求识别所需能力：
- 需要搜索 → "web_search"
- 需要 Excel → "xlsx_generation"
- 需要 PPT → "pptx_generation"
- 需要 pandas/numpy → "e2b_sandbox"
- 需要网络请求 → "e2b_sandbox"
"""
        
        return f"""
{rules_section}

{schema_section}

分析用户请求后，严格按照上述 JSON 格式输出结果。
"""
```

### 3. 框架执行引擎

```python
# core/agent/simple/simple_agent.py

class SimpleAgent:
    """
    简化版 Agent
    
    框架负责执行流程，Prompt 负责决策逻辑
    """
    
    def __init__(self, config: AgentConfig):
        self.config = config
        self.llm = create_llm_service(config.llm_provider)
        
        # 构建 System Prompt（组合多个部分）
        self.system_prompt = self._build_system_prompt()
        
        # Schema 解析器
        self.intent_schema = SchemaRegistry.get("intent_result")
        self.plan_schema = SchemaRegistry.get("plan_json")
    
    def _build_system_prompt(self) -> str:
        """
        构建完整的 System Prompt
        
        组合：基础身份 + 能力说明 + Schema 格式 + 业务规则
        """
        return "\n\n".join([
            BASE_IDENTITY_PROMPT,                    # 基础身份
            IntentAnalysisPrompt.build(),            # 意图识别规则 + Schema
            PlanManagementPrompt.build(),            # 计划管理规则 + Schema
            ToolGuidancePrompt.build(),              # 工具使用引导
            SkillsGuidancePrompt.build(),            # Skills 使用引导
            OutputFormatPrompt.build(),              # 输出格式规则
        ])
    
    async def chat(self, messages: List[dict]) -> AsyncIterator[StreamEvent]:
        """
        主聊天方法
        
        框架控制流程，Claude 根据 Prompt 决策
        """
        
        # Step 1: 构建请求
        request = self._build_request(messages)
        
        # Step 2: 调用 LLM（Claude 根据 Prompt 自主决策）
        async for event in self.llm.stream_message(request):
            
            # Step 3: 框架处理事件
            if event.type == "content_block_delta":
                yield event
            
            elif event.type == "tool_use":
                # 框架执行工具
                result = await self.tool_executor.execute(
                    event.tool_name,
                    event.tool_input
                )
                yield ToolResultEvent(result=result)
            
            elif event.type == "message_stop":
                # 框架后处理
                await self._post_process(event)
                yield event
    
    def _build_request(self, messages: List[dict]) -> dict:
        """构建 API 请求"""
        return {
            "model": self.config.model,
            "max_tokens": self.config.max_tokens,
            "system": self.system_prompt,  # ← 包含所有 Schema 和规则
            "betas": self.config.betas,
            "container": {
                "skills": self.config.skills  # 固定列表
            },
            "tools": self.config.tools,  # 所有可用工具
            "messages": messages,
            "stream": True
        }
    
    async def _post_process(self, event):
        """后处理：下载文件、更新状态等"""
        if hasattr(event, "file_id"):
            await self.files_api.download(event.file_id)
```

### 4. 动态 Prompt 配置

```python
# config/prompt_config.py

from dataclasses import dataclass
from typing import Dict, Any
import yaml


@dataclass
class PromptConfig:
    """
    Prompt 配置
    
    允许通过配置文件调整 Prompt 策略，无需修改代码
    """
    
    # 意图识别配置
    intent_rules: Dict[str, Any]
    
    # 计划管理配置
    plan_rules: Dict[str, Any]
    
    # 工具选择配置
    tool_rules: Dict[str, Any]
    
    # 输出格式配置
    output_rules: Dict[str, Any]
    
    @classmethod
    def from_yaml(cls, path: str) -> "PromptConfig":
        """从 YAML 文件加载配置"""
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return cls(**data)


# config/prompt_rules.yaml
"""
intent_rules:
  complexity_thresholds:
    low_keywords: ["什么是", "翻译", "简单"]
    high_keywords: ["分析", "报告", "规划", "多步骤"]
  
  needs_plan_conditions:
    - complexity: "high"
    - keywords: ["计划", "规划", "步骤"]
    - tool_count_threshold: 3

plan_rules:
  max_steps: 10
  step_granularity: "medium"  # fine | medium | coarse
  require_dependencies: true

tool_rules:
  skills_triggers:
    xlsx: ["excel", "表格", "电子表格", "报表"]
    pptx: ["ppt", "演示", "幻灯片"]
    pdf: ["pdf", "导出"]
  
  e2b_triggers:
    - "pandas"
    - "numpy"
    - "爬取"
    - "api调用"

output_rules:
  include_reasoning: true
  include_next_steps: true
  max_summary_length: 500
"""
```

---

## 📖 完整示例

### 示例场景：数据分析 + Excel 报表

```
┌─────────────────────────────────────────────────────────────────────────────┐
│           用户请求: "分析这份销售数据CSV，生成一份带图表的Excel报表"           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Step 1: Intent Analysis                                                     │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│                                                                              │
│  框架调用:                                                                   │
│  ┌────────────────────────────────────────────────────────────────────────┐│
│  │ response = await llm.create_message(                                   ││
│  │     system=INTENT_ANALYSIS_PROMPT,  # 包含 Schema 和规则               ││
│  │     messages=[{"role": "user", "content": user_input}]                ││
│  │ )                                                                      ││
│  └────────────────────────────────────────────────────────────────────────┘│
│                                                                              │
│  Claude 思考（根据 Prompt 中的规则）:                                        │
│  ┌────────────────────────────────────────────────────────────────────────┐│
│  │ "用户要求分析数据并生成Excel"                                          ││
│  │ "分析数据 → task_type = data_analysis"                                ││
│  │ "生成Excel → output_format = excel"                                   ││
│  │ "需要pandas分析 + xlsx生成 → complexity = high"                       ││
│  │ "高复杂度 → needs_plan = true"                                        ││
│  │ "能力需求: e2b_sandbox (pandas) + xlsx_generation"                    ││
│  └────────────────────────────────────────────────────────────────────────┘│
│                                                                              │
│  Claude 输出（按 Schema 格式）:                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐│
│  │ {                                                                      ││
│  │   "task_type": "data_analysis",                                       ││
│  │   "complexity": "high",                                               ││
│  │   "needs_plan": true,                                                 ││
│  │   "output_format": "excel",                                           ││
│  │   "required_capabilities": ["e2b_sandbox", "xlsx_generation"],        ││
│  │   "reasoning": "任务需要pandas数据分析+Excel生成，属于复杂多步骤任务"  ││
│  │ }                                                                      ││
│  └────────────────────────────────────────────────────────────────────────┘│
│                                                                              │
│  框架解析:                                                                   │
│  ┌────────────────────────────────────────────────────────────────────────┐│
│  │ intent = IntentResultSchema.model_validate(extract_json(response))    ││
│  │ # → IntentResult(task_type="data_analysis", complexity="high", ...)   ││
│  └────────────────────────────────────────────────────────────────────────┘│
│                                                                              │
│  Step 2: Plan Creation（needs_plan == true）                                │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│                                                                              │
│  框架调用:                                                                   │
│  ┌────────────────────────────────────────────────────────────────────────┐│
│  │ response = await llm.create_message(                                   ││
│  │     system=PLAN_CREATION_PROMPT,  # 包含 Plan Schema 和规则            ││
│  │     messages=[                                                         ││
│  │         {"role": "user", "content": user_input},                      ││
│  │         {"role": "assistant", "content": f"意图分析：{intent.json()}"} ││
│  │     ]                                                                  ││
│  │ )                                                                      ││
│  └────────────────────────────────────────────────────────────────────────┘│
│                                                                              │
│  Claude 输出 Plan（按 Schema 格式）:                                         │
│  ┌────────────────────────────────────────────────────────────────────────┐│
│  │ {                                                                      ││
│  │   "goal": "分析销售数据并生成带图表的Excel报表",                       ││
│  │   "steps": [                                                           ││
│  │     {"id": "1", "action": "读取并分析CSV数据", "tool": "e2b_sandbox"}, ││
│  │     {"id": "2", "action": "计算关键指标和趋势", "tool": "e2b_sandbox"},││
│  │     {"id": "3", "action": "生成带图表的Excel", "tool": "xlsx"}         ││
│  │   ]                                                                    ││
│  │ }                                                                      ││
│  └────────────────────────────────────────────────────────────────────────┘│
│                                                                              │
│  Step 3: RVR Turn Loop                                                      │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│                                                                              │
│  框架构建请求（包含 Plan 上下文 + Tools + Skills）:                          │
│  ┌────────────────────────────────────────────────────────────────────────┐│
│  │ response = await llm.stream_message(                                   ││
│  │     system=EXECUTION_PROMPT,                                           ││
│  │     container={"skills": [{"skill_id": "xlsx", ...}]},                ││
│  │     tools=[e2b_sandbox, code_execution, ...],                         ││
│  │     messages=[                                                         ││
│  │         {"role": "user", "content": "[Plan]\n" + plan.json() + ...}   ││
│  │     ]                                                                  ││
│  │ )                                                                      ││
│  └────────────────────────────────────────────────────────────────────────┘│
│                                                                              │
│  Claude 自主执行（根据 Plan + Prompt 引导）:                                 │
│                                                                              │
│  Turn 1: 调用 e2b_sandbox 分析数据                                          │
│  Turn 2: xlsx Skill 生成 Excel（通过 code_execution）                       │
│                                                                              │
│  Step 4: Complete                                                            │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│                                                                              │
│  框架后处理:                                                                 │
│  ┌────────────────────────────────────────────────────────────────────────┐│
│  │ file_path = await files_api.download(file_id)                         ││
│  │ emit_file_generated(file_path)                                        ││
│  │ emit_message_stop(summary=claude_summary)                             ││
│  └────────────────────────────────────────────────────────────────────────┘│
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 📊 总结：框架与 Prompt 的协同

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    框架与 Prompt 协同机制总结                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   核心原则                                                                   │
│   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│                                                                              │
│   1. Schema 是契约                                                           │
│      • 框架定义 Schema（输入输出格式）                                       │
│      • Prompt 引用 Schema（告诉 Claude 按格式输出）                          │
│      • 框架解析 Claude 输出（根据 Schema 提取数据）                          │
│                                                                              │
│   2. 能力与策略分离                                                          │
│      • 框架提供能力（Intent/Plan/Tool/Memory）                              │
│      • Prompt 定义策略（何时用、怎么用）                                     │
│      • Claude 执行决策（根据 Prompt 规则）                                   │
│                                                                              │
│   3. 配置驱动                                                                │
│      • 业务规则放在 Prompt 中（可调整）                                      │
│      • 不硬编码在框架代码中                                                  │
│      • 通过 YAML 配置修改策略                                                │
│                                                                              │
│   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│                                                                              │
│   职责分工                                                                   │
│                                                                              │
│   框架（代码）               Schema（契约）           Prompt（策略）         │
│   ━━━━━━━━━━               ━━━━━━━━━━━              ━━━━━━━━━━━           │
│   • 流程控制                • 输入格式               • 决策规则             │
│   • 工具执行                • 输出格式               • 判断标准             │
│   • 结果解析                • 字段定义               • 业务逻辑             │
│   • 状态管理                • 类型约束               • 示例说明             │
│                                                                              │
│   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│                                                                              │
│   修改影响范围                                                               │
│                                                                              │
│   修改内容                  影响范围                需要重启？              │
│   ────────────────        ──────────────          ──────────────          │
│   框架代码                  需要发布新版本           是                     │
│   Schema 定义               框架 + Prompt 都要改     是                     │
│   Prompt 规则               仅 Prompt 配置           否（热更新）           │
│   YAML 配置                 仅运行时参数             否（热更新）           │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 🔗 相关文档

- [00-ARCHITECTURE-V4.md](./00-ARCHITECTURE-V4.md) - V4 架构总览
- [13-INVOCATION_STRATEGY_V2.md](./13-INVOCATION_STRATEGY_V2.md) - 调用策略
- [PROMPT_ENGINEERING_GUIDE.md](./PROMPT_ENGINEERING_GUIDE.md) - Prompt 设计指南（待创建）

