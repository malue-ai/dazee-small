# Prompt 驱动架构实施完成报告

> 📅 **完成日期**: 2026-01-05  
> 🎯 **设计哲学**: System Prompt → LLM 生成 Schema → 动态初始化 Agent  
> ✅ **实施状态**: 已完成核心重构

---

## 📋 实施目标

将 ZenFlux Agent 框架重构为真正的 **Prompt 驱动架构**，遵循 `15-FRAMEWORK_PROMPT_CONTRACT.md` 中定义的设计哲学。

---

## 🎯 核心设计哲学

### 概念澄清

| 概念 | 定义 | 作用 | 生命周期 |
|------|------|------|---------|
| **System Prompt** | Agent 的"操作手册" | 定义 Agent 的角色、能力、规则 | 初始化时设定，相对固定 |
| **User Query** | 用户的具体请求 | 告诉 Agent "做什么" | 每次对话动态变化 |
| **Schema** | 组件配置 | 定义哪些组件启用、如何配置 | 从 System Prompt 推断 |

### 完整流程

```
开发者编写 System Prompt
        ↓
LLM 分析 Prompt 生成 AgentSchema
        ↓
AgentFactory 根据 Schema 初始化 Agent
        ↓
Agent 根据 Schema 动态创建组件
        ↓
用户发送 User Query
        ↓
Agent 根据 System Prompt 规则处理 User Query
```

---

## ✅ 完成的核心修改

### 1. `SimpleAgent.__init__` - 接收 Schema 和 System Prompt

**位置**: `core/agent/simple/simple_agent.py:60-103`

**修改内容**:
```python
def __init__(
    self,
    # ... 原有参数 ...
    schema=None,  # 🆕 AgentSchema 配置
    system_prompt: str = None  # 🆕 System Prompt（运行时指令）
):
    # 存储 Schema（如果未提供，使用 DEFAULT_AGENT_SCHEMA）
    self.schema = schema if schema is not None else DEFAULT_AGENT_SCHEMA
    
    # 存储 System Prompt
    self.system_prompt = system_prompt
    
    # 从 Schema 读取运行时参数
    if schema is not None:
        self.model = schema.model
        self.max_turns = schema.max_turns
    
    # 根据 Schema 动态初始化组件
    self._init_modules()
```

**设计理念**: Agent 不再硬编码配置，而是由 Schema 驱动

---

### 2. `SimpleAgent._init_modules()` - 根据 Schema 动态创建组件

**位置**: `core/agent/simple/simple_agent.py:139-197`

**修改内容**:
```python
def _init_modules(self):
    """根据 Schema 动态初始化各独立模块"""
    
    # 意图分析器 - 根据 Schema 决定是否创建
    if self.schema.intent_analyzer.enabled:
        intent_config = self.schema.intent_analyzer
        self.intent_analyzer = create_intent_analyzer(
            llm_service=...,
            enable_llm=intent_config.use_llm  # 从 Schema 读取
        )
    else:
        self.intent_analyzer = None  # 不创建
    
    # Plan Manager - 根据 Schema 决定是否创建
    if self.schema.plan_manager.enabled:
        self.plan_todo_tool = create_plan_todo_tool(...)
    else:
        self.plan_todo_tool = None  # 不创建
    
    # ... 其他组件同理 ...
```

**设计理念**: 组件不再全部创建，而是根据 Schema 配置按需创建

---

### 3. `SimpleAgent.chat()` - 使用传入的 System Prompt

**位置**: `core/agent/simple/simple_agent.py:245-276`

**修改内容**:
```python
async def chat(self, ...):
    # 1. 意图分析 - 根据 Schema 决定是否执行
    if self.schema.intent_analyzer.enabled and self.intent_analyzer:
        intent = await self.intent_analyzer.analyze(messages)
    else:
        intent = DEFAULT_INTENT
    
    # 2. System Prompt 选择（极简原则）
    # - 有自定义 System Prompt → 使用它（唯一真相来源）
    # - 没有 → 使用框架默认 Prompt
    if self.system_prompt:
        system_prompt = self.system_prompt  # 用户定义的 Prompt
    else:
        system_prompt = UNIVERSAL_AGENT_PROMPT  # 框架默认 Prompt
    
    # 3. 使用这个 System Prompt 调用 LLM
    response = await self.llm.create_message(
        system=system_prompt,  # ← 使用选定的 System Prompt
        messages=llm_messages,
        ...
    )
```

**设计理念**: 
- 用户只定义一套 System Prompt
- 不做复杂的分层或动态选择
- System Prompt 是唯一真相来源

---

### 4. `AgentFactory.from_schema()` - 正确传递 Schema 和 System Prompt

**位置**: `core/agent/factory.py:331-377`

**修改内容**:
```python
@classmethod
def from_schema(
    cls,
    schema: AgentSchema,
    system_prompt: str,
    event_manager,
    ...
):
    """根据 Schema 创建 Agent（设计哲学：Schema 驱动）"""
    
    # 🆕 直接传递 schema 和 system_prompt 给 SimpleAgent
    agent = SimpleAgent(
        model=schema.model,
        max_turns=schema.max_turns,
        event_manager=event_manager,
        workspace_dir=workspace_dir,
        conversation_service=conversation_service,
        schema=schema,  # 🆕 传递 Schema
        system_prompt=system_prompt  # 🆕 传递 System Prompt
    )
    
    return agent
```

**设计理念**: AgentFactory 不再只是设置属性，而是直接传递 Schema 驱动初始化

---

## 📊 修改前后对比

| 维度 | 修改前 | 修改后 |
|------|--------|--------|
| **组件初始化** | `_init_modules()` 硬编码创建所有组件 | 根据 Schema 按需创建组件 |
| **System Prompt** | 运行时动态选择（`prompt_selector`） | 初始化时传入，运行时使用 |
| **Schema 作用** | AgentFactory 设置属性，Agent 忽略 | Agent 根据 Schema 动态配置 |
| **向后兼容** | ❌ | ✅ 不提供 Schema 时使用默认值 |

---

## 🎯 使用示例

### 方式 1: 从自定义 System Prompt 创建（推荐）

```python
from core.agent import AgentFactory
from core.events import create_event_manager

# 1. 开发者编写 System Prompt
CUSTOM_PROMPT = """
你是一个数据分析助手。
你擅长使用 pandas 分析数据。
你会生成 Excel 报表。
复杂任务时，你会先制定计划。
"""

# 2. 从 Prompt 创建 Agent（LLM 分析 Prompt 生成 Schema）
event_manager = create_event_manager()
agent = await AgentFactory.from_prompt(
    system_prompt=CUSTOM_PROMPT,
    event_manager=event_manager
)

# 3. 用户发送请求
user_query = "分析这份数据并生成报表"  # ← User Query
async for event in agent.chat([{"role": "user", "content": user_query}]):
    yield event
```

### 方式 2: 精确控制 Schema

```python
from core.schemas import (
    AgentSchema,
    IntentAnalyzerConfig,
    PlanManagerConfig,
    SkillConfig,
)

# 1. 精确定义 Schema
schema = AgentSchema(
    name="DataAgent",
    intent_analyzer=IntentAnalyzerConfig(enabled=True),
    plan_manager=PlanManagerConfig(enabled=True, max_steps=10),
    tools=["e2b_sandbox"],
    skills=[SkillConfig(skill_id="xlsx", type="custom")],
    model="claude-sonnet-4-5-20250929",
    max_turns=15,
)

# 2. 从 Schema 创建 Agent
agent = AgentFactory.from_schema(
    schema=schema,
    system_prompt="你是数据分析助手...",
    event_manager=event_manager
)
```

### 方式 3: 向后兼容（不使用 Schema）

```python
from core.agent import SimpleAgent

# 直接创建（使用 DEFAULT_AGENT_SCHEMA）
agent = SimpleAgent(event_manager=event_manager)

# 所有组件将使用默认配置初始化
```

---

## ✅ 向后兼容性

| 场景 | 是否兼容 | 说明 |
|------|---------|------|
| 直接创建 `SimpleAgent()` | ✅ | 使用 `DEFAULT_AGENT_SCHEMA` |
| 不提供 `system_prompt` | ✅ | 运行时动态选择 Prompt |
| 现有代码调用 | ✅ | 参数向后兼容，新参数为可选 |

---

## 📚 相关文档

| 文档 | 说明 |
|------|------|
| `15-FRAMEWORK_PROMPT_CONTRACT.md` | 设计哲学详细说明 |
| `00-ARCHITECTURE-V4.md` | V4 架构总览 |
| `examples/prompt_driven_agent_example.py` | 完整使用示例 |
| `core/schemas/validator.py` | Schema 强类型定义 |

---

## 🎉 实施成果

✅ **设计哲学实现**：真正的 "Prompt → Schema → Agent" 流程  
✅ **Schema 驱动**：组件根据 Schema 配置按需创建  
✅ **System Prompt 传递**：从 AgentFactory 传入，运行时使用  
✅ **向后兼容**：现有代码无需修改  
✅ **强类型验证**：完整的 Pydantic Schema 定义  

---

## 🔗 下一步优化方向

1. **完善 Schema 生成 Prompt**：提升 LLM 推断 Schema 的准确性
2. **增强组件配置**：更多组件支持 Schema 配置参数
3. **动态 Prompt 更新**：支持运行时切换 System Prompt
4. **Schema 持久化**：保存和复用成功的 Schema 配置

