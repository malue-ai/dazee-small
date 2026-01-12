# ZenFlux Agent V5.1 架构文档

> 📅 **最后更新**: 2026-01-11  
> 🎯 **当前版本**: V5.1 - Mem0 用户画像增强 + 工具分层加载 + 语义推理模块  
> 🔗 **历史版本**: 已归档至 [`archived/`](./archived/) 目录  
> ✅ **架构状态**: 生产就绪，端到端验证通过

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

### V5.1 核心特性

V5.1 是 V5.0 基础上的**功能增强版本**，核心变化：

1. **Mem0 用户画像增强**：新增 `core/memory/mem0/schemas/` 多层用户画像结构（UserPersona、PlanSummary、行为/情感分析）
2. **工具分层加载**：新增 `core/tool/loader.py` 统一管理三类工具（通用工具、MCP 工具、Claude Skills）
3. **语义推理模块**：新增 `core/inference/` 模块，所有推理通过 LLM 语义完成
4. **后台任务增强**：`utils/background_tasks.py` 新增 Mem0 增量更新、批量处理等功能
5. **HITL 确认管理**：`core/confirmation_manager.py` 完善人机协作确认流程
6. **工作区管理**：`core/workspace_manager.py` 管理 conversation 级别的文件工作区

### V5.0 核心特性（继承）

1. **实例级提示词缓存**：启动时一次性生成所有提示词版本，运行时直接取用
2. **LLM 语义驱动 Schema**：用 Few-shot 引导 LLM 推理配置，而非硬编码关键词规则
3. **Prompt-First 设计原则**：规则写在 Prompt 里，不写在代码里
4. **本地文件持久化**：缓存数据持久化到 `.cache/` 目录，避免每次重启都 LLM 分析
5. **三层 API 架构**：routers（HTTP）+ grpc_server（gRPC）+ services（业务逻辑）

### 版本演进路线

```
V3.7 (2025-12)        V4.x (2026-01)        V5.0 (2026-01)        V5.1 (2026-01)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
基础架构           → Mem0 用户画像        → 实例级缓存          → Mem0 画像增强
能力抽象层         → 智能记忆检索        → LLM 语义驱动        → 语义推理模块
E2B 沙箱集成       → Skills/Tools 分层   → Prompt-First        → 工具分层加载
                   → Plan 持久化         → 本地持久化          → HITL 完善
```

| 维度 | V3.7 | V4.6 | V5.0 | V5.1 |
|------|------|------|------|------|
| **提示词管理** | 单一 Prompt | 动态裁剪 | 启动时预生成 3 版本 | ✅ 继承 + 复杂度检测器增强 |
| **Schema 生成** | 配置驱动 | 硬编码规则 | LLM 语义分析 | ✅ 继承 + 统一推理模块 |
| **记忆检索** | 无 | 每次都检索 | 智能按需检索 | ✅ Mem0 多层画像 + 异步更新 |
| **工具管理** | 单一列表 | 分类配置 | 能力注册 | ✅ 三类统一加载器 |
| **API 架构** | 单层 | 单层 | 三层架构 | ✅ gRPC + 工具服务 |

---

## 核心设计原则

### 1. Prompt-First 原则

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
│   ✅ V5.0 Few-shot 引导 LLM 推理（强泛化能力）：                │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │ <example>                                               │   │
│   │   <prompt>帮我分析销售数据，生成周报</prompt>            │   │
│   │   <reasoning>数据分析+表格生成</reasoning>              │   │
│   │   <schema>{"skills": [{"skill_id": "xlsx"}]}</schema>   │   │
│   │ </example>                                              │   │
│   │                                                         │   │
│   │ LLM 通过 Few-shot 学习推理模式，可泛化到：              │   │
│   │ - "整理成报告" → docx                                   │   │
│   │ - "准备演示材料" → pptx（虽未提及"PPT"）                │   │
│   │ - "分析竞品" → web_search + docx                        │   │
│   └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│   维护方式：修改 Few-shot 示例即可扩展能力，无需改代码           │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 2. 用空间换时间原则

| 阶段 | 开销 | 频率 | 优化收益 |
|------|------|------|---------|
| 启动时 LLM 分析 | ~2-3秒 | 一次 | 换取运行时零开销 |
| 运行时取缓存 | <1ms | 每次请求 | 节省 ~500ms/请求 |

### 3. Memory-First Protocol

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
┌──────────────────────────────────────────────────────────────────────┐
│                         ZenFlux Agent V5.0                            │
├──────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │                     协议入口层（平级）                          │ │
│  │  ┌──────────────┐              ┌──────────────┐                │ │
│  │  │  routers/    │  HTTP        │  grpc_server/│  gRPC          │ │
│  │  │  (FastAPI)   │ ◄──────      │  (gRPC)      │ ◄──────        │ │
│  │  └──────┬───────┘              └──────┬───────┘                │ │
│  │         │                             │                         │ │
│  │         └─────────────┬───────────────┘                         │ │
│  │                       ▼                                         │ │
│  │  ┌─────────────────────────────────────────────────────────┐   │ │
│  │  │              services/ 业务逻辑层                        │   │
│  │  │  • chat_service.py                                      │   │
│  │  │  • conversation_service.py                              │   │
│  │  │  • mem0_service.py                                      │   │
│  │  │  （只写一次，被 HTTP 和 gRPC 复用）                     │   │
│  │  └──────────────────────────┬──────────────────────────────┘   │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                                │                                     │
│                                ▼                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │                    SimpleAgent（编排层）                      │  │
│  │  ┌──────────────────────────────────────────────────────────┐│  │
│  │  │ InstancePromptCache（启动时加载，运行时复用）             ││  │
│  │  │  • system_prompt_simple/medium/complex                   ││  │
│  │  │  • intent_prompt                                         ││  │
│  │  │  • prompt_schema + agent_schema                          ││  │
│  │  └──────────────────────────────────────────────────────────┘│  │
│  │                                                              │  │
│  │  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌──────────┐│  │
│  │  │IntentAnalyzer│ContextMgr │ ToolSelector│ │EventMgr  ││  │
│  │  └────────────┘ └────────────┘ └────────────┘ └──────────┘│  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                │                                     │
│                                ▼                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │                      Memory 三层系统                          │  │
│  │  ┌──────────────────────────────────────────────────────────┐│  │
│  │  │ 会话级：WorkingMemory（messages/plan/tool_calls）        ││  │
│  │  └──────────────────────────────────────────────────────────┘│  │
│  │  ┌──────────────────────────────────────────────────────────┐│  │
│  │  │ 用户级：Episodic/Preference/Plan/E2B/Mem0               ││  │
│  │  │   • Episodic（历史经验）• Preference（偏好）            ││  │
│  │  │   • PlanMemory（跨Session）• E2BMemory（沙箱）          ││  │
│  │  │   • Mem0（用户画像，可选）                               ││  │
│  │  └──────────────────────────────────────────────────────────┘│  │
│  │  ┌──────────────────────────────────────────────────────────┐│  │
│  │  │ 系统级：Skill（注册表）• Cache（系统缓存）               ││  │
│  │  └──────────────────────────────────────────────────────────┘│  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                │                                     │
│                                ▼                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │                      Tool 执行层                              │  │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐        │  │
│  │  │ MCP Tools│ │ E2B      │ │ Skills   │ │ Built-in │        │  │
│  │  │ (Dify等) │ │ Sandbox  │ │ (SKILL.md)│ │ Tools    │        │  │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘        │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

### 启动阶段

```
启动阶段流程（一次性，2-3秒）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

instances/test_agent/
├── prompt.md        ─────────┐
├── config.yaml               │
└── .env                      ▼
                ┌────────────────────┐
                │ instance_loader.py │
                └─────────┬──────────┘
                          │
                          ▼
        ┌─────────────────────────────────┐
        │ InstancePromptCache.load_once() │
        └─────────────┬───────────────────┘
                      │
        ┌─────────────┼─────────────┐
        │             │             │
        ▼             ▼             ▼
┌─────────────┐ ┌─────────────┐ ┌─────────────────────┐
│LLM 语义分析│ │LLM 语义分析│ │IntentPromptGenerator│
│→PromptSchema│ │→AgentSchema│ │ .generate()         │
└──────┬──────┘ └──────┬──────┘ └──────┬──────────────┘
       │               │               │
       └───────────────┼───────────────┘
                       ▼
        ┌─────────────────────────────────┐
        │    InstancePromptCache（内存）   │
        │  ┌──────────────────────────┐   │
        │  │ • system_prompt_simple   │   │
        │  │ • system_prompt_medium   │   │
        │  │ • system_prompt_complex  │   │
        │  │ • intent_prompt          │   │
        │  │ • prompt_schema          │   │
        │  │ • agent_schema           │   │
        │  └──────────────────────────┘   │
        └──────────────┬──────────────────┘
                       │
                       ▼
        ┌─────────────────────────────────┐
        │  持久化到 .cache/ 目录（磁盘）   │
        │  • prompt_cache.json            │
        │  • agent_schema.json            │
        │  • cache_meta.json              │
        └─────────────────────────────────┘

关键产出：
• PromptSchema：提示词结构（模块、复杂度关键词）
• AgentSchema：Agent 配置（工具、Skills、组件开关）
• 3 版本系统提示词：Simple/Medium/Complex
• 意图识别提示词：动态生成（用户配置优先）
```

**代码入口**：`scripts/instance_loader.py` → `create_agent_from_instance()`

```python
# 启动时一次性加载（核心代码）
from core.prompt import load_instance_cache

prompt_cache = await load_instance_cache(
    instance_name=instance_name,
    raw_prompt=instance_prompt,
    config=config.raw_config,
    force_refresh=False  # 优先加载磁盘缓存
)
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
│   → _prompt_cache.get_intent_prompt()  ◄─ 直接从缓存取     │
│   → LLM (Haiku)                                           │
│                                                           │
│ 输出：IntentResult                                         │
│   • task_type: content_generation                         │
│   • complexity: COMPLEX                                   │
│   • needs_plan: true                                      │
│   • skip_memory_retrieval: false  ← V4.6 智能决策         │
└───────────────────────────────────────────────────────────┘
            │
            ▼
┌───────────────────────────────────────────────────────────┐
│ Phase 2: 记忆检索（V4.6 按需检索）                          │
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
│   → system_prompt_complex  ◄─ 直接从缓存取（预生成）       │
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
│   • 意图提示词：0ms（缓存命中）                            │
│   • 系统提示词：0ms（缓存命中）                            │
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
        prompt_cache=None  # V5.0: InstancePromptCache
    ):
        """初始化 Agent"""
        self.model = model
        self.max_turns = max_turns
        self.event_manager = event_manager
        self.schema = schema
        self._prompt_cache = prompt_cache  # V5.0 核心
        
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
        1. 意图识别（IntentAnalyzer）
        2. 记忆检索（Mem0，按需）
        3. 系统提示词组装（从缓存取）
        4. RVR 循环执行
        """
        # 1. 意图识别（使用缓存的 intent_prompt）
        intent = await self.intent_analyzer.analyze(user_input)
        
        # 2. 记忆检索（V4.6 智能决策）
        user_profile = None
        if not intent.skip_memory_retrieval:
            user_profile = await self._fetch_user_profile(user_id)
        
        # 3. 系统提示词组装（V5.0 从缓存取）
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

**关键改进（V5.0）**：
- ✅ 优先使用 `_prompt_cache.get_system_prompt()`（启动时预生成）
- ✅ 集成智能记忆检索决策（V4.6）
- ✅ 完全解耦业务逻辑

### InstancePromptCache（提示词缓存）

**文件**：`core/prompt/instance_cache.py`

**职责**：
- 实例启动时一次性加载所有提示词版本
- 运行时提供毫秒级的提示词访问
- 管理缓存生命周期（包括失效检测）
- V5.0：支持本地文件持久化

```python
class InstancePromptCache:
    """
    实例级提示词缓存管理器（单例模式）
    
    核心属性：
    - prompt_schema: 解析后的提示词结构
    - agent_schema: Agent 配置
    - system_prompt_simple/medium/complex: 3 版本系统提示词
    - intent_prompt: 意图识别提示词
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
        cache_dir: Path = None  # V5.0: 磁盘缓存目录
    ):
        """
        一次性加载（幂等）
        
        流程：
        1. 检查磁盘缓存是否有效
        2. 有效 → 直接加载（< 100ms）
        3. 无效/无缓存 → LLM 分析（2-3秒）→ 写入磁盘
        """
        # V5.0: 优先尝试从磁盘加载
        if cache_dir and not force_refresh:
            if await self._try_load_from_disk(cache_dir):
                return
        
        # LLM 语义分析
        self.prompt_schema = await self._analyze_prompt_structure(raw_prompt)
        self.agent_schema = await self._analyze_agent_schema(raw_prompt, config)
        
        # 生成 3 个版本系统提示词
        await self._generate_all_prompts()
        
        # 生成意图识别提示词
        self.intent_prompt = IntentPromptGenerator.generate(
            self.prompt_schema
        )
        
        # V5.0: 持久化到磁盘
        if cache_dir:
            await self._save_to_disk(cache_dir)
    
    def get_system_prompt(self, complexity: TaskComplexity) -> str:
        """获取对应复杂度的系统提示词（直接从缓存取）"""
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

**使用方式**：

```python
# 获取缓存实例
cache = InstancePromptCache.get_instance("test_agent")

# 启动时一次性加载
await cache.load_once(
    raw_prompt=prompt,
    config=config,
    cache_dir=Path("instances/test_agent/.cache")
)

# 运行时获取（毫秒级）
intent_prompt = cache.get_intent_prompt()
system_prompt = cache.get_system_prompt(TaskComplexity.COMPLEX)
```

**缓存文件结构**（V5.0）：

```
instances/test_agent/.cache/
├── prompt_cache.json       # 3 版本系统提示词 + intent_prompt
├── agent_schema.json       # AgentSchema 配置
├── cache_meta.json         # 缓存元数据（哈希、时间戳）
└── tools_inference.json    # 工具推断缓存
```

**缓存失效策略**：

```python
@dataclass
class CacheMeta:
    """缓存元数据"""
    prompt_hash: str        # prompt.md 的哈希
    config_hash: str        # config.yaml 的哈希
    combined_hash: str      # 组合哈希
    created_at: str         # 创建时间
    version: str = "5.0"    # 缓存版本

# 启动时验证
if meta.combined_hash != computed_hash:
    # 配置已变更，重新 LLM 分析
    pass
```

### IntentAnalyzer（意图识别）

**文件**：`core/agent/intent_analyzer.py`

**职责**：
- 快速识别用户意图（使用 Haiku，快+便宜）
- 判断任务复杂度（Simple/Medium/Complex）
- V4.6：智能决策是否需要记忆检索

```python
class IntentAnalyzer:
    """意图分析器"""
    
    def __init__(self, prompt_cache: InstancePromptCache = None):
        self._prompt_cache = prompt_cache
        self.llm = create_claude_service(model="claude-haiku-4-5")
    
    async def analyze(self, user_input: str) -> IntentResult:
        """
        分析用户意图
        
        返回：
        - task_type: 任务类型（content_generation 等）
        - complexity: 复杂度（SIMPLE/MEDIUM/COMPLEX）
        - needs_plan: 是否需要创建计划
        - skip_memory_retrieval: 是否跳过记忆检索（V4.6）
        """
        # V5.0: 从缓存获取意图识别提示词
        intent_prompt = self._get_intent_prompt()
        
        # 使用 Haiku 快速分析
        response = await self.llm.create_message(
            messages=[{"role": "user", "content": user_input}],
            system=intent_prompt
        )
        
        return self._parse_intent_result(response)
    
    def _get_intent_prompt(self) -> str:
        """获取意图识别提示词（V5.0 从缓存取）"""
        if self._prompt_cache and self._prompt_cache.is_loaded:
            return self._prompt_cache.get_intent_prompt()
        
        # Fallback: 使用默认提示词
        return IntentPromptGenerator.get_default()
```

**意图识别输出**（V4.6）：

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
│ │ • 用户历史任务记录                                  │ │
│ │ • 成功/失败经验                                     │ │
│ │                                                    │ │
│ │ PreferenceMemory（用户偏好）                       │ │
│ │ • 用户个性化设置                                    │ │
│ │ • 风格偏好                                          │ │
│ │                                                    │ │
│ │ PlanMemory（任务计划持久化，V4.3+）                │ │
│ │ • 跨 Session 任务计划保存                          │ │
│ │ • 支持中断恢复                                      │ │
│ │                                                    │ │
│ │ E2BMemory（E2B 沙箱记忆）                          │ │
│ │ • 用户的云端计算环境                                │ │
│ │ • 持久化沙箱 Session                                │ │
│ │ • 代码执行历史                                      │ │
│ │                                                    │ │
│ │ Mem0（用户画像，V4.5+，可选）                      │ │
│ │ • 向量化语义记忆                                    │ │
│ │ • 智能按需检索（V4.6）                             │ │
│ │ • 多向量数据库支持                                  │ │
│ └────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────┐
│ 系统级（System Scope）- 全局共享                        │
│ ┌────────────────────────────────────────────────────┐ │
│ │ SkillMemory（Skills 注册表）                       │ │
│ │ • Skills 元数据和路径                               │ │
│ │ • 全局共享                                          │ │
│ │                                                    │ │
│ │ CacheMemory（系统缓存）                            │ │
│ │ • 临时数据缓存                                      │ │
│ │ • TTL 管理                                          │ │
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
│   ├── plan.py          # PlanMemory（V4.3+）
│   └── e2b.py           # E2BMemory
├── system/              # 系统级记忆
│   ├── skill.py         # SkillMemory
│   └── cache.py         # CacheMemory
└── mem0/                # Mem0 用户画像（可选）
    ├── pool.py
    └── tencent_vectordb.py
```

#### WorkingMemory（会话级短期记忆）

**文件**：`core/memory/working.py`

**职责**：
- 存储当前会话的短期记忆
- 管理 messages、tool_calls、plan/todo

```python
class WorkingMemory:
    """工作记忆 - 当前会话的短期记忆"""
    
    def __init__(self):
        self.messages = []       # 消息历史
        self.tool_calls = []     # 工具调用记录
        self.plan_json = None    # Plan 存储
        self.todo_md = None      # Todo 存储
    
    # Plan/Todo CRUD
    def set_plan(self, plan_json, todo_md): ...
    def get_plan(self) -> Optional[Dict]: ...
    def update_plan_step(self, step_index, status, result): ...
```

#### 用户级记忆（User Scope）

**1. PlanMemory（任务计划持久化，V4.3+）**

**文件**：`core/memory/user/plan.py`

**职责**：
- 跨 Session 保存任务计划
- 支持长时运行任务中断恢复
- 与 WorkingMemory 协同工作

```python
class PlanMemory:
    """任务计划持久化记忆"""
    
    async def save_plan(self, plan_id: str, plan_data: Dict):
        """保存任务计划"""
        pass
    
    async def load_plan(self, plan_id: str) -> Optional[Dict]:
        """加载任务计划"""
        pass
    
    async def list_active_plans(self, user_id: str) -> List[Dict]:
        """列出用户的活跃任务"""
        pass
```

**2. E2BMemory（E2B 沙箱记忆）**

**文件**：`core/memory/user/e2b.py`

**职责**：
- 管理用户的云端计算环境
- 持久化沙箱 Session
- 代码执行历史

**3. EpisodicMemory & PreferenceMemory**

**文件**：`core/memory/user/episodic.py`, `preference.py`

**职责**：
- 用户历史经验记录
- 用户偏好设置

#### Mem0（用户画像，可选）

**文件**：`core/memory/mem0/` + `services/mem0_service.py`

**职责**（V4.5+，V5.1 增强）：
- 跨 Session 用户画像与偏好记忆
- 基于 Mem0 框架的向量检索
- 支持多向量数据库（Qdrant、腾讯云 VectorDB）
- V4.6：智能按需检索
- **V5.1：多层用户画像结构**

**V5.1 Mem0 模块结构**：

```
core/memory/mem0/
├── __init__.py
├── pool.py                 # Mem0 连接池
├── config.py               # Mem0 配置
├── tencent_vectordb.py     # 腾讯云向量数据库
├── aggregator.py           # 🆕 记忆聚合器
├── analyzer.py             # 🆕 行为分析器
├── extractor.py            # 🆕 记忆提取器
├── planner.py              # 🆕 计划跟踪器
├── prompts.py              # 🆕 Mem0 提示词
├── reminder.py             # 🆕 提醒生成器
├── reporter.py             # 🆕 报告生成器
├── reranker.py             # 🆕 记忆重排序
├── formatter.py            # 画像格式化
└── schemas/                # 🆕 V5.1 多层画像结构
    ├── persona.py          # UserPersona 用户画像
    ├── behavior.py         # 行为分析结构
    ├── emotion.py          # 情感分析结构
    ├── fragment.py         # 记忆片段结构
    └── plan.py             # 计划跟踪结构
```

**UserPersona 数据结构**（V5.1）：

```python
# core/memory/mem0/schemas/persona.py
@dataclass
class UserPersona:
    """
    用户画像 - 汇总所有层的分析结果
    用于 Prompt 注入和个性化响应
    """
    user_id: str
    
    # 身份推断
    inferred_role: str = "unknown"  # product_manager/developer/sales
    role_confidence: float = 0.0
    work_domain: str = "general"
    
    # 行为摘要
    routine_overview: str = ""      # 工作规律概述
    work_style: str = ""            # 工作风格
    time_management: str = ""       # 时间管理方式
    
    # 当前状态
    current_focus: str = ""         # 当前关注点
    emotional_state: str = "neutral"
    energy_level: str = "normal"
    
    # 计划跟踪
    active_plans: List[PlanSummary] = field(default_factory=list)
    upcoming_reminders: List[ReminderSummary] = field(default_factory=list)
```

```python
class Mem0Service:
    """Mem0 用户记忆服务"""
    
    async def search(
        self, 
        user_id: str, 
        query: str, 
        limit: int = 5
    ) -> List[Memory]:
        """
        检索用户记忆（V4.6 按需调用）
        
        只在以下场景检索：
        - PPT 生成（可能有风格偏好）
        - 代码编写（可能有编码风格）
        - 推荐任务（需要了解用户喜好）
        
        通用查询（天气、百科）跳过检索
        """
        pass
    
    async def add(
        self, 
        user_id: str, 
        messages: List[Message]
    ):
        """添加用户记忆（异步更新）"""
        pass
```

**V5.1 后台任务增强**（`utils/background_tasks.py`）：

```python
class BackgroundTaskService:
    """
    后台任务服务
    
    支持任务类型：
    - 对话标题生成
    - 推荐问题生成
    - 🆕 V5.1 Mem0 用户记忆增量更新
    """
    
    async def update_mem0_for_user(
        self, 
        user_id: str,
        conversations: List[Conversation]
    ) -> Mem0UpdateResult:
        """单用户 Mem0 增量更新"""
        pass
    
    async def batch_update_mem0(
        self,
        user_ids: List[str]
    ) -> Mem0BatchUpdateResult:
        """批量 Mem0 更新"""
        pass
```

#### MemoryManager（统一入口）

**文件**：`core/memory/manager.py`

```python
class MemoryManager:
    """
    统一记忆管理器
    
    整合三层记忆，提供统一访问接口
    """
    
    def __init__(self, user_id: str = None, storage_dir: str = None):
        # 会话级
        self.working = create_working_memory()
        
        # 用户级（懒加载）
        self.episodic = ...  # EpisodicMemory
        self.preference = ...  # PreferenceMemory
        self.plan = ...  # PlanMemory（V4.3+）
        self.e2b = create_e2b_memory(user_id)
        
        # 系统级（单例）
        self.skill = ...  # SkillMemory
        self.cache = ...  # CacheMemory
```

**Mem0 集成流程**（V4.5）：

```
Phase 2: 记忆检索（按需）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

if not intent.skip_memory_retrieval:  ← V4.6 智能决策
    ┌─────────────────────────────────────────┐
    │ Mem0Service.search(user_id, query)      │
    └─────────────────┬───────────────────────┘
                      │
                      ▼
    ┌─────────────────────────────────────────┐
    │ 向量数据库（Qdrant / 腾讯云 VectorDB） │
    │ • 语义相似度检索                         │
    │ • 返回 top-k 相关记忆                    │
    └─────────────────┬───────────────────────┘
                      │
                      ▼
    ┌─────────────────────────────────────────┐
    │ 用户画像 & 偏好                          │
    │ • "用户偏好简洁风格的 PPT"               │
    │ • "用户习惯使用 Python 3.10+"            │
    └─────────────────┬───────────────────────┘
                      │
                      ▼
    ┌─────────────────────────────────────────┐
    │ 注入到 System Prompt                     │
    └─────────────────────────────────────────┘
```

**参考来源**：
- [Mem0 官方文档](https://docs.mem0.ai/)
- [Mem0 论文](https://arxiv.org/abs/2504.19413)

### Events 系统

**文件**：`core/events/`

**职责**：
- 统一的事件管理和分发
- 支持 SSE 流式输出
- 多平台适配器（ZenO、钉钉、飞书等）

**核心组件**：

```python
# core/events/manager.py
class EventManager:
    """事件管理器"""
    
    async def emit(
        self, 
        event_type: str, 
        data: Dict, 
        session_id: str
    ):
        """发送事件"""
        pass

# core/events/adapters/zeno.py
class ZenOAdapter(EventAdapter):
    """ZenO 事件适配器"""
    
    def transform(self, event: Dict) -> Optional[Dict]:
        """转换为 ZenO SSE 格式"""
        pass
```

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
- **V5.1：统一工具加载器**

**核心文件结构**：

```
core/tool/
├── __init__.py
├── executor.py             # 工具执行器
├── selector.py             # 工具选择器
├── loader.py               # 🆕 V5.1 统一工具加载器
├── instance_registry.py    # 实例级工具注册
├── result_compactor.py     # 结果压缩器
├── validator.py            # 工具参数验证
└── capability/             # 能力系统
    ├── invocation.py       # 调用选择器
    ├── registry.py         # 能力注册表
    ├── router.py           # 能力路由
    ├── skill_loader.py     # Skill 加载器
    └── types.py            # 类型定义
```

**V5.1 工具分层加载**：

```python
# core/tool/loader.py
class ToolLoader:
    """
    统一工具加载器 - 管理三类工具
    
    1. 通用工具：从 capabilities.yaml 加载，根据 enabled_capabilities 过滤
    2. MCP 工具：从 config.yaml 的 mcp_tools 配置加载
    3. Claude Skills：从 skills/skill_registry.yaml 加载
    """
    
    # 工具类别定义（类别化配置）
    TOOL_CATEGORIES = {
        "document_skills": ["pptx", "xlsx", "docx", "pdf"],
        "sandbox_tools": ["sandbox_run_code", "sandbox_list_dir", ...],
        "ppt_tools": ["ppt_generator", "slidespeak_render"],
    }
```

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
                      │
                      ▼
┌────────────────────────────────────────────────────────┐
│                   ToolExecutor                          │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐             │
│  │MCP Tools │  │ E2B      │  │ Built-in │             │
│  │(Dify等)  │  │ Sandbox  │  │ Tools    │             │
│  └──────────┘  └──────────┘  └──────────┘             │
└────────────────────────────────────────────────────────┘
```

**MCP 工具示例**（`instances/test_agent/config.yaml`）：

```yaml
mcp_tools:
  - name: text2flowchart
    server_url: "https://api.dify.ai/mcp/server/XXX/mcp"
    server_name: "dify"
    auth_type: "bearer"
    auth_env: "DIFY_API_KEY"
    capability: "document_creation"
    description: "从自然语言描述生成 Mermaid 流程图"
```

### Orchestration 系统

**文件**：`core/orchestration/`

**职责**：
- 代码生成、验证、执行的完整编排
- 自动错误恢复与重试
- E2B 沙箱深度集成
- 执行状态追踪

**核心组件**：

```python
# core/orchestration/code_orchestrator.py
class CodeOrchestrator:
    """
    代码执行编排器
    
    流程：代码生成 → 验证 → 执行 → 结果验证
    特性：
    - 自动错误分析和重试
    - 详细执行记录
    - E2B 沙箱集成
    """
    
    async def execute_code(
        self, 
        code: str, 
        conversation_id: str,
        max_retries: int = 3
    ) -> ExecutionResult:
        """执行代码（带自动恢复）"""
        pass

# core/orchestration/code_validator.py
class CodeValidator:
    """代码验证器 - 执行前验证 + 执行后验证"""
    pass

# core/orchestration/pipeline_tracer.py
class E2EPipelineTracer:
    """端到端流水线追踪器"""
    pass
```

### Inference 系统

**文件**：`core/inference/`

**职责**（V5.1 新增）：
- 统一语义推理模块
- 所有推理通过 LLM 语义完成
- Few-Shot 教会 LLM 推理模式
- 保守 fallback，不做关键词猜测

```python
# core/inference/semantic_inference.py
class SemanticInferenceEngine:
    """
    V5.0 统一语义推理引擎
    
    核心理念：
    - 代码只做调用和解析，不做规则判断
    - 运营无需配置任何推理规则
    - 框架内置 Few-Shot 示例
    """
    
    class InferenceType(Enum):
        COMPLEXITY = "complexity"   # 复杂度推理
        INTENT = "intent"           # 意图推理
        CAPABILITY = "capability"   # 能力推理
        SCHEMA = "schema"           # Schema 推理
    
    async def infer(
        self, 
        query: str, 
        inference_type: InferenceType
    ) -> InferenceResult:
        """执行语义推理"""
        pass
```

**推理流程**：

```
用户输入 → LLM 语义推理 → 结构化结果

Few-Shot 示例教会 LLM:
• "构造CRM系统" → Complex (build + 完整架构)
• "这个系统怎么用" → Simple (询问，非构建)
• "分析销售趋势" → Medium (分析，单一任务)
```

---

## API 三层架构

V5.0 采用**三层架构**，HTTP 和 gRPC 入口共享业务逻辑：

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

### 示例代码

```python
# services/chat_service.py（业务逻辑，只写一次）
class ChatService:
    async def send_message(self, user_id: str, content: str):
        """发送消息（核心业务逻辑）"""
        # HTTP 和 gRPC 都调用这个
        pass

# routers/chat.py（HTTP 入口）
@router.post("/chat")
async def chat(request: ChatRequest):
    service = get_chat_service()
    return await service.send_message(request.user_id, request.content)

# grpc_server/chat_servicer.py（gRPC 入口）
class ChatServicer(chat_pb2_grpc.ChatServiceServicer):
    async def SendMessage(self, request, context):
        service = get_chat_service()
        result = await service.send_message(request.user_id, request.content)
        return chat_pb2.ChatResponse(...)
```

**参考文档**：[`02-api-development/RULE.mdc`](.cursor/rules/02-api-development/RULE.mdc)

---

## 目录结构

```
zenflux_agent/
├── core/                           # 核心组件
│   ├── agent/                      # Agent 模块
│   │   ├── factory.py              # Agent 工厂（LLM 语义分析）
│   │   ├── intent_analyzer.py      # 意图分析器
│   │   ├── simple_agent.py         # SimpleAgent（编排层）
│   │   └── types.py                # Agent 类型定义
│   │
│   ├── prompt/                     # 🔥 V5.0 核心模块
│   │   ├── instance_cache.py       # InstancePromptCache（单例+持久化）
│   │   ├── intent_prompt_generator.py  # 动态意图提示词生成
│   │   ├── prompt_layer.py         # 提示词分层管理
│   │   ├── complexity_detector.py  # 复杂度检测器
│   │   └── llm_analyzer.py         # LLM 提示词语义分析器
│   │
│   ├── inference/                  # 🆕 V5.1 语义推理模块
│   │   └── semantic_inference.py   # 统一语义推理引擎
│   │
│   ├── orchestration/              # 🆕 代码编排模块
│   │   ├── code_orchestrator.py    # 代码执行编排器
│   │   ├── code_validator.py       # 代码验证器
│   │   └── pipeline_tracer.py      # 流水线追踪器
│   │
│   ├── memory/                     # Memory 系统
│   │   ├── manager.py              # MemoryManager 统一入口
│   │   ├── working.py              # WorkingMemory
│   │   ├── base.py                 # 基类定义
│   │   ├── mem0/                   # 🆕 V5.1 增强 Mem0 用户画像
│   │   │   ├── pool.py             # 连接池
│   │   │   ├── config.py           # 配置
│   │   │   ├── aggregator.py       # 记忆聚合器
│   │   │   ├── analyzer.py         # 行为分析器
│   │   │   ├── extractor.py        # 记忆提取器
│   │   │   ├── planner.py          # 计划跟踪器
│   │   │   ├── prompts.py          # Mem0 提示词
│   │   │   ├── reminder.py         # 提醒生成器
│   │   │   ├── reporter.py         # 报告生成器
│   │   │   ├── reranker.py         # 记忆重排序
│   │   │   ├── formatter.py        # 画像格式化
│   │   │   ├── tencent_vectordb.py # 腾讯云向量库
│   │   │   └── schemas/            # 🆕 多层画像结构
│   │   │       ├── persona.py      # UserPersona
│   │   │       ├── behavior.py     # 行为分析
│   │   │       ├── emotion.py      # 情感分析
│   │   │       ├── fragment.py     # 记忆片段
│   │   │       └── plan.py         # 计划跟踪
│   │   ├── user/                   # 用户记忆
│   │   │   ├── episodic.py         # EpisodicMemory
│   │   │   ├── preference.py       # PreferenceMemory
│   │   │   ├── plan.py             # PlanMemory
│   │   │   └── e2b.py              # E2BMemory
│   │   └── system/                 # 系统记忆
│   │       ├── skill.py            # SkillMemory
│   │       └── cache.py            # CacheMemory
│   │
│   ├── events/                     # Events 系统
│   │   ├── manager.py              # 事件管理器
│   │   ├── broadcaster.py          # 事件广播器
│   │   ├── dispatcher.py           # 事件分发器
│   │   ├── storage.py              # 事件存储
│   │   ├── message_events.py       # 消息事件
│   │   ├── content_events.py       # 内容事件
│   │   ├── session_events.py       # 会话事件
│   │   ├── user_events.py          # 用户事件
│   │   ├── system_events.py        # 系统事件
│   │   ├── conversation_events.py  # 对话事件
│   │   └── adapters/               # 平台适配器
│   │       ├── base.py             # 适配器基类
│   │       ├── zeno.py             # ZenO 适配器
│   │       ├── dingtalk.py         # 钉钉适配器
│   │       ├── feishu.py           # 飞书适配器
│   │       ├── slack.py            # Slack 适配器
│   │       └── webhook.py          # Webhook 适配器
│   │
│   ├── tool/                       # Tool 系统
│   │   ├── executor.py             # 工具执行器
│   │   ├── selector.py             # 工具选择器
│   │   ├── loader.py               # 🆕 V5.1 统一工具加载器
│   │   ├── instance_registry.py    # 实例级工具注册
│   │   ├── result_compactor.py     # 结果压缩器
│   │   ├── validator.py            # 工具参数验证
│   │   └── capability/             # 能力系统
│   │       ├── invocation.py       # 调用选择器
│   │       ├── registry.py         # 能力注册表
│   │       ├── router.py           # 能力路由
│   │       ├── skill_loader.py     # Skill 加载器
│   │       └── types.py            # 类型定义
│   │
│   ├── llm/                        # LLM 提供商
│   │   ├── base.py                 # LLM 基类
│   │   ├── adaptor.py              # LLM 适配器
│   │   ├── claude.py               # Claude 服务
│   │   ├── openai.py               # OpenAI 服务
│   │   └── gemini.py               # Gemini 服务
│   │
│   ├── context/                    # Context 管理
│   │   ├── context_engineering.py  # Context Engineering
│   │   ├── prompt_manager.py       # 提示词管理
│   │   ├── runtime.py              # 运行时上下文
│   │   └── conversation.py         # 对话上下文
│   │
│   ├── schemas/                    # Schema 验证
│   │   └── validator.py            # Schema 验证器
│   │
│   ├── confirmation_manager.py     # 🆕 HITL 确认管理器
│   ├── workspace_manager.py        # 🆕 工作区管理器
│   └── agent_manager.py            # Agent 管理器
│
├── services/                       # 🔥 业务逻辑层（API 三层架构）
│   ├── chat_service.py             # 聊天服务（被 HTTP 和 gRPC 复用）
│   ├── conversation_service.py     # 对话服务
│   ├── session_service.py          # 会话服务
│   ├── mem0_service.py             # Mem0 服务
│   ├── file_service.py             # 文件服务
│   ├── knowledge_service.py        # 知识库服务
│   ├── sandbox_service.py          # 沙盒服务
│   ├── tool_service.py             # 工具服务
│   ├── mcp_client.py               # MCP 客户端
│   └── redis_manager.py            # Redis 管理
│
├── routers/                        # HTTP 入口（FastAPI）
│   ├── chat.py                     # 聊天路由
│   ├── conversation.py             # 对话路由
│   ├── mem0_router.py              # Mem0 路由
│   ├── files.py                    # 文件路由
│   ├── knowledge.py                # 知识库路由
│   ├── tools.py                    # 工具路由
│   ├── workspace.py                # 工作区路由
│   └── human_confirmation.py       # HITL 确认路由
│
├── grpc_server/                    # gRPC 入口
│   ├── server.py                   # gRPC 服务器
│   ├── client.py                   # gRPC 客户端
│   ├── chat_servicer.py            # 聊天 Servicer
│   ├── session_servicer.py         # 会话 Servicer
│   └── generated/                  # protoc 生成的代码
│       ├── tool_service_pb2.py
│       └── tool_service_pb2_grpc.py
│
├── tools/                          # Built-in 工具
│   ├── base.py                     # 工具基类
│   ├── plan_todo_tool.py           # Plan/Todo 工具
│   ├── exa_search.py               # Exa 搜索
│   ├── knowledge_search.py         # 知识库搜索
│   ├── ppt_generator.py            # PPT 生成器
│   ├── slidespeak.py               # SlidesSpeak 集成
│   ├── sandbox_tools.py            # E2B 沙盒工具
│   ├── api_calling.py              # API 调用工具
│   ├── request_human_confirmation.py  # HITL 工具
│   └── e2b_template_manager.py     # E2B 模板管理
│
├── skills/                         # Skills 库
│   ├── library/                    # 内置 Skills
│   │   ├── ontology-builder/       # 本体构建
│   │   ├── planning-task/          # 任务规划
│   │   ├── ppt-generator/          # PPT 生成
│   │   ├── slidespeak-generator/   # SlidesSpeak 生成
│   │   ├── slidespeak-editor/      # SlidesSpeak 编辑
│   │   └── slidespeak-slide-editor/ # 幻灯片编辑
│   └── custom_claude_skills/       # 自定义 Skills
│
├── instances/                      # 实例配置
│   ├── _template/                  # 实例模板
│   │   ├── prompt.md               # 提示词模板
│   │   ├── config.yaml             # 配置模板
│   │   ├── config_example_full.yaml    # 完整配置示例
│   │   ├── config_example_minimal.yaml # 最小配置示例
│   │   ├── env.example             # 环境变量模板
│   │   ├── api_desc/               # API 描述
│   │   └── skills/                 # 实例级 Skills
│   └── test_agent/                 # 测试实例
│       ├── prompt.md
│       ├── config.yaml
│       ├── api_desc/
│       ├── skills/
│       └── .cache/                 # V5.0 缓存目录
│
├── config/                         # 全局配置
│   ├── capabilities.yaml           # 能力配置
│   ├── llm_config/                 # LLM 配置
│   │   └── profiles.yaml           # LLM 配置文件
│   └── storage.yaml                # 存储配置
│
├── models/                         # Pydantic 数据模型
│   ├── api.py                      # API 模型
│   ├── chat.py                     # 聊天模型
│   ├── database.py                 # 数据库模型
│   ├── file.py                     # 文件模型
│   ├── knowledge.py                # 知识库模型
│   ├── mem0.py                     # Mem0 模型
│   ├── ragie.py                    # Ragie 模型
│   └── tool.py                     # 工具模型
│
├── utils/                          # 工具函数
│   ├── background_tasks.py         # 🆕 V5.1 后台任务增强
│   ├── cache_utils.py              # 缓存工具
│   ├── file_handler.py             # 文件处理
│   ├── file_processor.py           # 文件处理器
│   ├── json_file_store.py          # JSON 存储
│   ├── json_utils.py               # JSON 工具
│   ├── knowledge_store.py          # 知识存储
│   ├── message_utils.py            # 消息工具
│   ├── ragie_client.py             # Ragie 客户端
│   ├── s3_uploader.py              # S3 上传
│   └── usage_tracker.py            # 使用量追踪
│
├── prompts/                        # 提示词模板
│   └── universal_agent_prompt.py   # 通用 Agent 提示词
│
├── scripts/                        # 脚本
│   ├── instance_loader.py          # 实例加载器
│   ├── run_instance.py             # 运行实例
│   ├── run_agent.py                # 运行 Agent
│   ├── skill_cli.py                # Skill CLI
│   ├── sync_capabilities.py        # 同步能力配置
│   ├── generate_grpc.sh            # 生成 gRPC 代码
│   └── e2e_architecture_verify.py  # E2E 架构验证
│
├── tests/                          # 测试
│   └── dazee_e2e/                  # 🆕 E2E 测试
│
├── docs/                           # 文档
│   └── architecture/               # 架构文档
│       ├── 00-ARCHITECTURE-OVERVIEW.md  # 本文档
│       └── archived/               # 历史版本
│
├── main.py                         # 应用入口
├── logger.py                       # 日志配置
├── requirements.txt                # 依赖
├── Dockerfile                      # Docker 配置
├── Dockerfile.production           # 生产 Docker
└── docker-compose.yml              # Docker Compose
```

---

## 配置管理

### 实例配置（`instances/xxx/`）

每个实例独立配置，支持：
- **prompt.md**：运营写的系统提示词（业务规则）
- **config.yaml**：实例配置（工具、记忆、Agent 参数）
- **.env**：环境变量（API Keys）
- **.cache/**：V5.0 缓存目录（启动时自动生成）

**示例**：`instances/test_agent/config.yaml`

```yaml
instance:
  name: "test_agent"
  description: "测试智能体"

agent:
  model: "claude-sonnet-4-5-20250929"
  max_turns: 20
  plan_manager_enabled: true

mcp_tools:
  - name: text2flowchart
    server_url: "https://api.dify.ai/mcp/server/XXX/mcp"
    capability: "document_creation"

memory:
  mem0_enabled: true
  smart_retrieval: true  # V4.6 智能记忆检索
```

### 全局配置（`config/`）

全局共享配置：
- **capabilities.yaml**：能力配置（工具注册、分类定义）
- **llm_config/**：LLM 配置（多提供商支持）
- **storage.yaml**：存储配置（数据库、向量数据库）

---

## 快速验证

### 验证 InstancePromptCache 加载

```bash
cd /Users/liuyi/Documents/langchain/CoT_agent/mvp/zenflux_agent
source venv/bin/activate

# 首次启动（LLM 分析 + 写缓存）
python scripts/run_instance.py --instance test_agent
```

**预期日志**：

```
🔄 开始 LLM 分析: test_agent
   LLM 分析: 2312ms
💾 缓存已保存到磁盘: instances/test_agent/.cache
✅ InstancePromptCache 加载: Simple=749字符, Medium=760字符, Complex=768字符
```

### 验证磁盘持久化

```bash
# 再次启动（从磁盘加载）
python scripts/run_instance.py --instance test_agent
```

**预期日志**：

```
✅ 从磁盘缓存加载: test_agent
   磁盘加载耗时: 45ms
```

### 验证缓存文件

```bash
ls -la instances/test_agent/.cache/
# 预期输出：
# prompt_cache.json
# agent_schema.json
# cache_meta.json

cat instances/test_agent/.cache/cache_meta.json
# 预期输出：
# {
#   "prompt_hash": "abc123...",
#   "config_hash": "def456...",
#   "combined_hash": "ghi789...",
#   "created_at": "2026-01-11T...",
#   "version": "5.0"
# }
```

### 验证 API 三层架构

```bash
# 测试 HTTP API
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "你好", "session_id": "test"}'

# 测试 gRPC（需要 grpcurl）
grpcurl -plaintext -d '{"user_id": "test", "message": "你好"}' \
  localhost:50051 zenflux.ChatService/SendMessage
```

**预期**：两个 API 返回相同的业务结果（共享 `services/chat_service.py`）

---

## 相关文档

| 文档 | 说明 |
|------|------|
| [00-ARCHITECTURE-OVERVIEW.md](./00-ARCHITECTURE-OVERVIEW.md) | V5.1 架构总览（本文档，唯一架构详细文档） |
| [archived/V4-ARCHITECTURE-HISTORY.md](./archived/V4-ARCHITECTURE-HISTORY.md) | V4.x 历史版本（已归档） |
| [archived/V5-INSTANCE-CACHE-DESIGN.md](./archived/V5-INSTANCE-CACHE-DESIGN.md) | V5.0 提示词缓存专题设计（已归档） |
| [01-MEMORY-PROTOCOL.md](./01-MEMORY-PROTOCOL.md) | Memory-First Protocol 详解 |
| [03-EVENT-PROTOCOL.md](./03-EVENT-PROTOCOL.md) | SSE 事件协议 |
| [tool_configuration_guide.md](../tool_configuration_guide.md) | 🆕 工具配置指南 |
| [tool_reference.md](../tool_reference.md) | 🆕 工具参考手册 |
| [.cursor/rules/02-api-development/RULE.mdc](../.cursor/rules/02-api-development/RULE.mdc) | API 三层架构开发规范 |

---

## 版本历史

| 版本 | 日期 | 核心变化 |
|------|------|---------|
| **V5.1** | 2026-01-11 | 🔥 Mem0 多层画像 + 工具分层加载 + 语义推理模块 + HITL 完善 |
| V5.0 | 2026-01-09 | 实例级提示词缓存 + LLM 语义驱动 Schema + 本地持久化 |
| V4.6 | 2026-01-08 | 智能记忆检索决策（按需检索 Mem0） |
| V4.5 | 2026-01-07 | Mem0 用户画像层（跨 Session 记忆） |
| V4.4 | 2026-01-06 | Skills + Tools 整合（能力分层清晰化） |
| V4.3 | 2026-01-05 | Plan 持久化 + Session 恢复 |
| V4.0 | 2026-01-01 | 模块化重构（core/agent/memory/events 分离） |
| V3.7 | 2025-12-29 | 能力抽象层 + E2B 沙箱集成 |

---

**🎯 架构设计目标**：
- ✅ **单一事实来源**：本文档是唯一需要维护的架构详细文档
- ✅ **代码-文档一致**：所有代码路径、类名、函数名与实际代码一致
- ✅ **可执行验证**：包含快速验证命令，确保架构可验证
- ✅ **Prompt-First**：规则写在 Prompt 里，不写在代码里

**📌 维护原则**：
- 架构变更时，只需更新此文档
- 历史版本归档到 `archived/` 目录
- 专题设计可独立成文档，但总览保持简洁
