# ZenFlux Agent V10.0 更新文档

**版本**: V10.0  
**分支**: `merge/prompt-updates-with-v7-shared-layer`  
**日期**: 2026-02-06  
**变更规模**: 672 个文件 | +64,725 行 | -72,743 行（净精简约 8,000 行）

---

## 目录

1. [概述](#1-概述)
2. [Agent 执行层重构](#2-agent-执行层重构)
3. [Channels 多渠道架构](#3-channels-多渠道架构)
4. [Context 注入器重构](#4-context-注入器重构)
5. [Tool 工具层重构](#5-tool-工具层重构)
6. [Services 服务层优化](#6-services-服务层优化)
7. [Prompts 提示词精简](#7-prompts-提示词精简)
8. [Cursor Skills 技能模块](#8-cursor-skills-技能模块)
9. [其他变更](#9-其他变更)
10. [迁移指南](#10-迁移指南)
11. [附录：删除文件清单](#11-附录删除文件清单)

---

## 1. 概述

### 1.1 变更统计

| 指标 | 数值 |
|------|------|
| 新增文件 | 175 |
| 删除文件 | 125 |
| 修改文件 | 372 |
| 代码净变化 | -8,018 行（精简） |

### 1.2 核心改进

| 维度 | 改进内容 |
|------|----------|
| **代码复用** | 统一 `base.py` 基类，`components/` 共享组件 |
| **执行策略** | `execution/` 分离 RVR/RVR-B/Multi 策略 |
| **上下文注入** | 三阶段 `injectors/` 架构，职责清晰 |
| **工具管理** | 统一 `registry.py` + `types.py` |
| **多渠道** | `channels/` 插件化架构，支持飞书等渠道 |
| **Prompt** | 精简冗余，符合 LLM-First 原则 |

### 1.3 设计理念

本次重构遵循以下核心设计理念：

- **LLM-First**：语义理解优先，避免关键词匹配
- **Strategy Pattern**：通过 Executor 实现不同执行策略
- **Plugin Architecture**：渠道插件化，易于扩展
- **Phase-based Injection**：分阶段上下文注入，职责分离
- **Configuration-Driven**：配置驱动，减少硬编码

---

## 2. Agent 执行层重构

### 2.1 架构概述

V10.0 对 Agent 层进行了破坏性重构，核心变更：

- **统一 Agent 类**：不再有 `SimpleAgent`/`RVRBAgent`/`MultiAgentOrchestrator` 三个独立类
- **Strategy 模式**：执行策略通过注入 `Executor` 实现
- **扩展性**：新增策略只需新增 `execution/*.py` + 注册

### 2.2 新目录结构

```
core/agent/
├── __init__.py              # 模块入口，导出统一 API
├── base.py                  # 771 行，统一 Agent 类
├── errors.py                # 275 行，统一错误定义
├── models.py                # 数据模型（从 multi/ 迁移）
├── factory.py               # Agent 工厂 + Executor 注册表
├── protocol.py              # Agent 协议定义
├── coordinator.py           # 协调器
├── content_handler.py       # 内容处理器
│
├── execution/               # 执行策略层 ⭐ 新增
│   ├── __init__.py          # 导出所有 Executor
│   ├── protocol.py          # 199 行，ExecutorProtocol 协议
│   ├── rvr.py               # 710 行，RVR 执行器
│   ├── rvrb.py              # 798 行，RVR-B 执行器（带回溯）
│   ├── multi.py             # 150 行，多智能体入口
│   └── _multi/              # 多智能体内部实现（V10.3 组合模式）
│       ├── orchestrator.py  # 编排器核心（组合下方子模块）
│       ├── events.py        # EventEmitter — SSE 事件发送
│       ├── task_decomposer.py  # TaskDecomposer — 任务分解
│       ├── worker_runner.py    # WorkerRunner — Worker 执行（复用 RVRExecutor）
│       ├── critic_evaluator.py # CriticEvaluator — Critic 评估循环
│       └── result_aggregator.py # ResultAggregator — 结果聚合
│
├── components/              # 共享组件 ⭐ 新增
│   ├── __init__.py
│   ├── checkpoint.py        # 检查点（迁移自 multi/）
│   ├── critic.py            # 评审器（迁移自 multi/）
│   ├── lead_agent.py        # 主智能体（迁移自 multi/）
│   ├── critique_handler.py  # 319 行，评审处理器
│   └── subagent_manager.py  # 481 行，子智能体管理器
│
├── tools/                   # Agent 专用工具 ⭐ 新增
│   ├── __init__.py
│   ├── flow.py              # 417 行，工具执行流
│   └── special.py           # 233 行，特殊工具处理
│
├── context/                 # 上下文构建
│   ├── __init__.py
│   └── prompt_builder.py    # 360 行，提示词构建
│
└── backtrack/               # 回溯机制
    ├── __init__.py
    ├── error_classifier.py  # 错误分类器
    └── manager.py           # 回溯管理器
```

### 2.3 删除的旧目录

```
❌ core/agent/simple/              # 整个目录删除
   ├── simple_agent.py            # 818 行
   ├── simple_agent_context.py    # 270 行
   ├── simple_agent_errors.py     # 20 行
   ├── simple_agent_loop.py       # 451 行
   ├── simple_agent_tools.py      # 621 行
   ├── rvrb_agent.py              # 133 行
   ├── errors.py                  # 114 行
   └── mixins/
       ├── backtrack_mixin.py     # 589 行
       ├── stream_mixin.py        # 210 行
       └── tool_mixin.py          # 284 行

❌ core/agent/multi/               # 迁移到 execution/_multi/
   ├── orchestrator.py            # 迁移
   ├── models.py                  # 迁移到 agent/models.py
   ├── checkpoint.py              # 迁移到 components/
   ├── critic.py                  # 迁移到 components/
   └── lead_agent.py              # 迁移到 components/

❌ core/agent/simple_agent.py      # 2,473 行，删除
❌ core/agent/types.py             # 89 行，删除
```

### 2.4 核心类：Agent

```python
class Agent:
    """
    统一智能体实现
    
    通过注入 Executor 实现不同的执行策略：
    - RVRExecutor: 标准 RVR 循环
    - RVRBExecutor: 带回溯的 RVR-B 循环
    - SequentialExecutor: 多智能体顺序执行
    - ParallelExecutor: 多智能体并行执行
    - HierarchicalExecutor: 多智能体层级执行
    
    使用方式（由 Factory 创建）：
        agent = AgentFactory.create(
            strategy="rvr",
            event_manager=em,
            schema=schema
        )
        
        async for event in agent.execute(messages, session_id):
            yield event
    """
```

**关键设计原则**：
- Agent 只做编排，不包含执行逻辑
- 执行策略由 Executor 实现
- Factory 负责组装依赖

### 2.5 执行器协议：ExecutorProtocol

```python
@dataclass
class ExecutorConfig:
    """执行器配置"""
    max_turns: int = 30
    enable_stream: bool = True
    allow_parallel_tools: bool = True
    max_parallel_tools: int = 5
    token_budget: int = 180000
    safe_threshold_margin: int = 20000
    enable_backtrack: bool = False
    max_backtrack_attempts: int = 3

@dataclass
class ExecutionContext:
    """执行上下文"""
    llm: "BaseLLMService"
    session_id: str
    conversation_id: str
    tool_executor: Optional["ToolExecutor"]
    tools_for_llm: List[Dict[str, Any]]
    broadcaster: Optional["EventBroadcaster"]
    system_prompt: Any
    intent: Optional["IntentResult"]
    runtime_ctx: Optional["RuntimeContext"]
    context_strategy: Optional["ContextStrategy"]
    plan_cache: Dict[str, Any]
    extra: Dict[str, Any]

@runtime_checkable
class ExecutorProtocol(Protocol):
    """执行器协议"""
    
    @property
    def name(self) -> str: ...
    
    async def execute(
        self,
        messages: List[Dict[str, Any]],
        context: ExecutionContext,
        config: Optional[ExecutorConfig] = None,
        **kwargs
    ) -> AsyncGenerator[Dict[str, Any], None]: ...
    
    def supports_backtrack(self) -> bool: ...
```

### 2.6 RVR 执行器

```python
class RVRExecutor(BaseExecutor):
    """
    RVR 执行器（React-Validate-Reflect-Repeat）
    
    标准执行循环，不支持回溯。
    
    职责：
    - 标准 RVR 主循环
    - 流式 LLM 响应处理
    - 工具调用处理
    - 消息构建和更新
    - 上下文长度管理（Token 裁剪）
    """
    
    @property
    def name(self) -> str:
        return "RVRExecutor"
    
    def supports_backtrack(self) -> bool:
        return False
```

### 2.7 RVR-B 执行器

```python
class RVRBExecutor(RVRExecutor):
    """
    RVR-B 执行器（React-Validate-Reflect-Backtrack-Repeat）
    
    在 RVR 基础上增加回溯能力。
    
    回溯类型：
    - PLAN_REPLAN: Plan 重规划
    - TOOL_REPLACE: 工具替换
    - PARAM_ADJUST: 参数调整
    - CONTEXT_ENRICH: 上下文补充
    - INTENT_CLARIFY: 意图澄清
    """
    
    @property
    def name(self) -> str:
        return "RVRBExecutor"
    
    def supports_backtrack(self) -> bool:
        return True
```

### 2.8 创建 Agent 的方式

```python
# 推荐方式 1：通过便捷函数
from core.agent import create_agent

agent = await create_agent(
    strategy="rvr",      # 或 "rvr-b"、"multi"
    event_manager=em,
    schema=schema
)

# 推荐方式 2：通过 Factory
from core.agent import AgentFactory

agent = await AgentFactory.from_schema(
    schema=schema,
    system_prompt="你是一个智能助手。",
    event_manager=em
)

# 推荐方式 3：指定策略
agent = await AgentFactory.create(
    strategy="rvr-b",
    event_manager=em,
    schema=schema
)
```

---

## 3. Channels 多渠道架构

### 3.1 架构概述

V10.0 新增 `channels/` 模块，实现通用渠道集成框架，支持飞书、钉钉、Slack、Telegram 等多渠道双向对话。

**架构流程**：

```
消息来源层（飞书/钉钉/Slack/Telegram）
    ↓
Gateway 网关层（统一入口、预处理、权限检查）
    ↓
ChannelPlugin 渠道插件层（核心抽象）
    ↓
ChatService（Agent 调用层）
    ↓
Outbound 发送层（回复消息）
```

### 3.2 目录结构

```
channels/                        # +4,743 行 ⭐ 全新模块
├── __init__.py                  # 72 行，模块入口
├── config.py                    # 121 行，配置加载
├── manager.py                   # 388 行，渠道管理器
├── registry.py                  # 186 行，渠道注册表
│
├── base/                        # 基础抽象层
│   ├── __init__.py              # 54 行
│   ├── adapters.py              # 411 行，适配器基类
│   ├── capabilities.py          # 81 行，能力定义
│   ├── plugin.py                # 110 行，插件协议
│   └── types.py                 # 309 行，类型定义
│
├── feishu/                      # 飞书渠道实现 ⭐
│   ├── __init__.py              # 37 行
│   ├── client.py                # 538 行，飞书 API 客户端
│   ├── handler.py               # 338 行，消息处理器
│   ├── gateway.py               # 285 行，网关实现
│   ├── cards.py                 # 344 行，卡片消息构建
│   ├── outbound.py              # 219 行，消息发送
│   ├── security.py              # 110 行，安全校验
│   ├── plugin.py                # 129 行，插件注册
│   └── types.py                 # 164 行，类型定义
│
└── gateway/                     # 统一网关层
    ├── __init__.py              # 26 行
    ├── preprocessor.py          # 575 行，消息预处理器
    └── security.py              # 246 行，安全检查
```

### 3.3 核心类型定义

```python
@dataclass
class InboundMessage:
    """入站消息（从渠道接收的原始消息）"""
    message_id: str
    channel_id: str                              # feishu/dingtalk/slack
    account_id: str                              # 多账户支持
    chat_id: str                                 # 聊天 ID
    chat_type: Literal["direct", "group", "channel"]
    sender_id: str
    sender_name: str = ""
    content: str = ""
    msg_type: str = "text"                       # text/image/file
    media: List[Dict[str, Any]] = field(default_factory=list)
    reply_to: Optional[str] = None
    thread_id: Optional[str] = None
    mentions: List[str] = field(default_factory=list)
    timestamp: Optional[datetime] = None
    raw_event: Dict[str, Any] = field(default_factory=dict)

@dataclass
class OutboundContext:
    """出站消息上下文"""
    channel_id: str
    account_id: str
    chat_id: str
    text: str = ""
    card_data: Optional[Dict[str, Any]] = None
    media_url: Optional[str] = None
    reply_to: Optional[str] = None
    session_id: Optional[str] = None

@dataclass
class DeliveryResult:
    """消息发送结果"""
    success: bool
    message_id: Optional[str] = None
    error: Optional[str] = None
    raw_response: Optional[Dict[str, Any]] = None
```

### 3.4 安全策略

```python
class PolicyType(str, Enum):
    """策略类型"""
    OPEN = "open"           # 开放，所有人可用
    PAIRING = "pairing"     # 需要配对验证
    ALLOWLIST = "allowlist" # 白名单模式
    DISABLED = "disabled"   # 禁用

@dataclass
class DmPolicy:
    """私聊策略"""
    policy: PolicyType = PolicyType.OPEN
    allow_from: List[str] = field(default_factory=list)

@dataclass
class GroupPolicy:
    """群聊策略"""
    policy: PolicyType = PolicyType.OPEN
    allow_from: List[str] = field(default_factory=list)
    require_mention: bool = True
```

### 3.5 使用示例

```python
from channels import ChannelManager, get_channel_registry

# 获取渠道管理器
manager = ChannelManager(config)

# 注册消息处理回调
manager.on_message(async_message_handler)

# 启动所有渠道
await manager.start_all()

# 处理入站事件
response = await manager.handle_event("feishu", event_data)

# 发送消息
result = await manager.send_message(
    channel_id="feishu",
    account_id="default",
    chat_id="chat_123",
    text="Hello!"
)
```

### 3.6 配置文件

新增 `config/channels.yaml` 配置文件：

```yaml
channels:
  feishu:
    enabled: true
    accounts:
      default:
        app_id: "${FEISHU_APP_ID}"
        app_secret: "${FEISHU_APP_SECRET}"
        dm_policy:
          policy: open
        group_policy:
          policy: allowlist
          require_mention: true
```

---

## 4. Context 注入器重构

### 4.1 架构概述

V10.0 对上下文注入系统进行了重构，采用三阶段注入架构：

- **Phase 1 (System)**：注入到 `messages[0]`（role: "system"）
- **Phase 2 (User Context)**：注入到 `messages[1]`（role: "user", systemInjection: true）
- **Phase 3 (Runtime)**：追加到 `messages[n]`（最后一条用户消息）

### 4.2 新目录结构

```
core/context/
├── __init__.py                          # 模块入口
├── README.md                            # 文档
├── provider.py                          # 上下文提供者
├── retriever.py                         # 检索器
├── runtime.py                           # 运行时上下文
├── context_engineering.py               # 上下文工程
├── failure_summary.py                   # 失败摘要
│
├── compaction/                          # 压缩模块
│   ├── __init__.py                      # 压缩 API
│   ├── summarizer.py                    # 272 行，上下文摘要 ⭐ 新增
│   └── tool_result.py                   # 356 行，工具结果压缩 ⭐ 新增
│
├── injectors/                           # 注入器系统 ⭐ 全新架构
│   ├── __init__.py                      # 125 行，模块入口
│   ├── base.py                          # 228 行，注入器基类
│   ├── context.py                       # 197 行，注入上下文
│   ├── orchestrator.py                  # 377 行，编排器
│   │
│   ├── phase1/                          # 第一阶段：System Message
│   │   ├── __init__.py                  # 44 行
│   │   ├── history_summary.py           # 154 行，历史摘要
│   │   ├── system_role.py               # 153 行，系统角色
│   │   └── tool_provider.py             # 191 行，工具定义
│   │
│   ├── phase2/                          # 第二阶段：User Context
│   │   ├── __init__.py                  # 38 行
│   │   ├── knowledge.py                 # 161 行，知识库
│   │   └── user_memory.py               # 109 行，用户记忆
│   │
│   └── phase3/                          # 第三阶段：Runtime
│       ├── __init__.py                  # 38 行
│       ├── gtd_todo.py                  # 117 行，GTD Todo
│       └── page_editor.py               # 143 行，页面编辑器
│
└── providers/                           # 数据提供者
    ├── __init__.py
    ├── knowledge.py                     # 知识库提供者
    ├── memory.py                        # 记忆提供者
    └── metadata.py                      # 元数据提供者
```

### 4.3 删除的旧文件

```
❌ core/context/manager.py               # 265 行，删除
❌ core/context/prompt_manager.py        # 985 行，删除
❌ core/context/conversation.py          # 501 行，删除
❌ core/context/fusion.py                # 209 行，删除
❌ core/context/injector.py              # 199 行，删除
❌ core/context/rag_optimization.py      # 删除
```

### 4.4 注入阶段设计

```python
class InjectionPhase(Enum):
    """注入阶段"""
    SYSTEM = 1       # Phase 1: 注入到 system message
    USER_CONTEXT = 2 # Phase 2: 注入到 user context message
    RUNTIME = 3      # Phase 3: 追加到最后一条用户消息

class CacheStrategy(Enum):
    """缓存策略（与 Claude Prompt Caching 集成）"""
    STABLE = "stable"    # 极稳定，1h 缓存（框架规则、工具定义）
    SESSION = "session"  # 会话级，5min 缓存（用户画像）
    DYNAMIC = "dynamic"  # 动态，不缓存（历史摘要、实时数据）
```

**阶段分布**：

```
┌─────────────────────────────────────────────────────────────┐
│  Phase 1: System Message (role: "system")                   │
│  ├── SystemRoleInjector     # 角色定义                       │
│  ├── ToolSystemRoleProvider # 工具定义                       │
│  └── HistorySummaryProvider # 历史摘要                       │
├─────────────────────────────────────────────────────────────┤
│  Phase 2: User Context (role: "user", systemInjection: true)│
│  ├── UserMemoryInjector     # 用户记忆                       │
│  └── KnowledgeInjector      # 知识库                         │
├─────────────────────────────────────────────────────────────┤
│  Phase 3: Runtime Injection (追加到最后一条消息)              │
│  ├── PageEditorContextInjector  # 页面编辑器上下文           │
│  └── GTDTodoInjector            # GTD Todo                  │
└─────────────────────────────────────────────────────────────┘
```

### 4.5 使用示例

```python
from core.context.injectors import (
    InjectionOrchestrator,
    InjectionContext,
    create_default_orchestrator,
)

# 获取已注册所有 Injector 的编排器
orchestrator = create_default_orchestrator()

# 创建上下文
context = InjectionContext(
    user_id="user_123",
    user_query="帮我写一段代码",
    prompt_cache=prompt_cache,
)

# 构建 system blocks
system_blocks = await orchestrator.build_system_blocks(context)

# 构建 messages
messages = await orchestrator.build_messages(context)
```

---

## 5. Tool 工具层重构

### 5.1 架构概述

V10.0 对工具层进行了统一重构：

- 合并 `capability/registry.py` 和 `instance_registry.py` 为统一的 `registry.py`
- 合并 `capability/router.py` 和 `unified_tool_caller.py` 为统一的 `selector.py`
- 新增 `types.py` 统一类型定义

### 5.2 新目录结构

```
core/tool/
├── __init__.py                  # 114 行，模块入口
├── types.py                     # 515 行，统一类型定义 ⭐ 新增
├── registry.py                  # 872 行，统一注册表 ⭐ 新增
├── selector.py                  # 793 行，工具选择器（重构扩展）
├── executor.py                  # 466 行，工具执行器（重构）
├── loader.py                    # 213 行，工具加载器
├── llm_description.py           # LLM 描述生成
├── registry_config.py           # 注册表配置
├── validator.py                 # 工具验证器
│
├── capability/                  # Skill 相关（精简）
│   ├── __init__.py              # 精简
│   └── skill_loader.py          # Skill 内容加载器
│
└── README.md                    # 文档
```

### 5.3 删除的旧文件

```
❌ core/tool/base.py                     # 245 行
❌ core/tool/capability/invocation.py    # 409 行
❌ core/tool/capability/registry.py      # 712 行
❌ core/tool/capability/router.py        # 429 行
❌ core/tool/capability/types.py         # 163 行
❌ core/tool/instance_registry.py        # 623 行
❌ core/tool/result_compactor.py         # 511 行
❌ core/tool/unified_tool_caller.py      # 115 行
```

### 5.4 统一类型定义

```python
class CapabilityType(str, Enum):
    """能力类型"""
    SKILL = "skill"      # Skill（高级抽象）
    TOOL = "tool"        # 工具（原子操作）
    MCP = "mcp"          # MCP 协议
    CODE = "code"        # 代码执行

class CapabilitySubtype(str, Enum):
    """能力子类型"""
    NATIVE = "native"        # 内置
    CUSTOM = "custom"        # 自定义
    PREBUILT = "prebuilt"    # 预构建
    EXTERNAL = "external"    # 外部
    DYNAMIC = "dynamic"      # 动态

@dataclass
class Capability:
    """统一能力定义"""
    name: str
    type: CapabilityType
    subtype: CapabilitySubtype
    description: str
    handler: Optional[str] = None
    schema: Optional[Dict[str, Any]] = None
    enabled: bool = True
    level: int = 2                    # 工具层级 (1=核心, 2=动态)
    categories: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)
    fallback_capability: Optional[str] = None
```

### 5.5 统一注册表

```python
class CapabilityRegistry:
    """
    全局能力注册表（单例）
    
    管理所有能力（Skills/Tools/MCP/Code）
    从 capabilities.yaml 加载配置，同时扫描 skills/library/ 发现 Skills
    """
    
    async def initialize(self) -> None:
        """异步初始化"""
        await self._load_config_async()
        await self._scan_skills_async()
    
    def get(self, name: str) -> Optional[Capability]:
        """按名称获取能力"""
        
    def find_by_type(self, cap_type: CapabilityType) -> List[Capability]:
        """按类型查找"""
        
    def find_by_category(self, category: str) -> List[Capability]:
        """按分类查找"""

class InstanceRegistry:
    """
    实例级工具注册表
    
    每个 Agent 实例独立的工具注册表
    """
    
    def register(self, tool: InstanceTool) -> None:
        """注册工具实例"""
        
    def get(self, name: str) -> Optional[InstanceTool]:
        """获取工具实例"""
```

### 5.6 工具选择器

```python
class ToolSelector:
    """
    工具选择器
    
    职责：
    1. 根据意图和能力需求选择合适的工具
    2. 管理基础工具和动态工具的选择
    3. 提供工具 Schema 转换（用于 LLM API）
    4. 智能路由推荐
    5. Skill fallback 处理
    """
    
    async def select(
        self,
        required_capabilities: List[str],
        context: Dict[str, Any],
        allowed_tools: Optional[List[str]] = None,
    ) -> ToolSelectionResult:
        """选择工具"""
        
    async def resolve_capabilities(
        self,
        schema_tools: Optional[List[str]],
        plan: Optional[Dict],
        intent_task_type: Optional[str],
    ) -> Tuple[List[str], str, List[str], Optional[List[str]]]:
        """解析能力需求"""
        
    def get_tools_for_llm(
        self,
        selection: ToolSelectionResult,
        llm: "BaseLLMService",
    ) -> List[Dict[str, Any]]:
        """获取 LLM 工具格式"""
```

---

## 6. Services 服务层优化

### 6.1 变更概览

| 文件 | 变更 | 说明 |
|------|------|------|
| `chat_service.py` | +1,759/-1,200 | 大幅重构，流程优化 |
| `agent_registry.py` | +/-681 | 适配新 Agent 架构 |
| `realtime_service.py` | +415 | **新增** 实时语音服务 |
| `confirmation_service.py` | +/-240 | 优化确认流程 |
| `knowledge_service.py` | +/-620 | 重构知识服务 |
| `mcp_client.py` | +/-364 | 优化 MCP 客户端 |

### 6.2 ChatService 重构

`chat_service.py` 是核心服务，主要改进：

**设计原则**：
- `chat()` 是唯一入口，根据 `stream` 参数选择模式
- Session 管理由 `SessionService` 负责
- Agent 获取由 `AgentPool` 负责
- 内容累积和持久化由 `EventBroadcaster` 自动处理

**新增前置处理器**：

```python
@dataclass
class PreprocessingResult:
    """前置处理结果"""
    intent: Optional["IntentResult"]
    use_multi_agent: bool
    preface_text: Optional[str] = None

class PreprocessingHandler:
    """前置处理器：意图识别 + Preface 生成"""
    
    async def process(
        self,
        messages: List[Dict],
        session_id: str,
        conversation_id: str,
        user_id: str,
        **kwargs
    ) -> PreprocessingResult:
        """执行前置处理"""
```

### 6.3 新增 RealtimeService

`realtime_service.py` 提供实时语音通信服务：

```python
class RealtimeSession:
    """
    单个实时会话管理器
    
    负责维护与 OpenAI Realtime API 的 WebSocket 连接，
    并在客户端和 OpenAI 之间转发消息
    """
    
    OPENAI_REALTIME_URL = "wss://api.openai.com/v1/realtime"
    
    async def connect(self) -> bool:
        """连接到 OpenAI Realtime API"""
        
    async def send_client_event(self, event: Dict[str, Any]) -> bool:
        """发送客户端事件到 OpenAI"""
        
    async def close(self) -> None:
        """关闭会话"""

class RealtimeService:
    """
    实时服务管理器
    
    管理多个实时会话的生命周期
    """
    
    async def create_session(
        self,
        session_id: str,
        on_server_event: Callable,
        **kwargs
    ) -> RealtimeSession:
        """创建新会话"""
```

---

## 7. Prompts 提示词精简

### 7.1 变更概览

| 文件 | 变更 | 说明 |
|------|------|------|
| `intent_recognition_prompt.py` | **-700 行** | 大幅精简意图识别 |
| `universal_agent_prompt.py` | +/-266 | 优化结构 |

### 7.2 意图识别精简

V10.0 对 `intent_recognition_prompt.py` 进行了极简化：

**精简前**：~800 行，包含复杂的多字段输出

**精简后**：~100 行，只输出 3 个核心字段

```python
INTENT_RECOGNITION_PROMPT = """# 意图分类器

分析用户请求，输出 JSON。

## 输出格式

```json
{
  "complexity": "simple|medium|complex",
  "agent_type": "rvr|rvr-b|multi",
  "skip_memory": true|false
}
```

**所有字段必填**，不要省略。
"""
```

**字段说明**：

| 字段 | 说明 | 取值 |
|------|------|------|
| `complexity` | 复杂度等级 | `simple`/`medium`/`complex` |
| `agent_type` | 执行引擎 | `rvr`/`rvr-b`/`multi` |
| `skip_memory` | 跳过记忆检索 | `true`/`false` |

**设计原则**：
- 极简输出，减少 LLM 产生矛盾的可能
- Few-Shot 示例驱动决策
- LLM-First：语义理解，不做关键词匹配
- 其他字段（`needs_plan`, `execution_strategy`）由代码从 `complexity` 推断

---

## 8. Cursor Skills 技能模块

### 8.1 新增技能

V10.0 新增 `.cursor/skills/` 目录，包含以下技能：

```
.cursor/skills/
├── fastapi-feature/SKILL.md       # FastAPI 功能开发
├── vue-feature/SKILL.md           # Vue 功能开发
├── code-review/SKILL.md           # 代码审查
├── commit-message/SKILL.md        # Commit 消息生成
├── performance-report/skill.md    # 性能报告
└── run-tests/                     # 测试运行
    ├── SKILL.md
    └── scripts/
        ├── py.sh
        ├── pytest.sh
        └── uvicorn.sh
```

### 8.2 fastapi-feature 技能

**适用场景**：
- 新增/修改 FastAPI endpoint、路由、接口协议
- 新增/修改 Service 业务逻辑
- 新增/修改 Pydantic 请求/响应模型
- 修复接口类 bug

**强约束**：
- 三层架构：`routers/` → `services/` → `models/`
- 异步优先：禁止阻塞 I/O
- 日志规范：使用 `get_logger`，禁止 `print()`
- 错误返回一致：失败响应必须包含 `"error"` 字段

### 8.3 code-review 技能

**审查维度**：
- LLM-First 原则遵守
- 异步 I/O 使用
- 日志规范
- 品牌中立
- 架构分层
- 返回格式一致性

---

## 9. 其他变更

### 9.1 删除的文件

- `CHANGELOG_V9.0.md` - 已合并到主文档
- `comprehensive_test.py` - 废弃测试
- `tests/verify_*.py` - 验证脚本（共 829 行）

### 9.2 环境配置更新

- `.env`、`.env.development`、`.env.production`、`.env.staging` - 更新环境变量

### 9.3 配置文件更新

- `config/capabilities.yaml` - 能力配置
- `config/channels.yaml` - 渠道配置（新增）
- `config/context_compaction.yaml` - 上下文压缩配置
- `config/llm_config/profiles.yaml` - LLM 配置

### 9.4 LLM 层优化

- 新增 `core/llm/model_registry.py` - 模型注册表
- 新增 `core/llm/registry.py` - LLM 注册表
- 优化各 LLM 适配器（claude.py、openai.py、gemini.py、qwen.py）

---

## 10. 迁移指南

### 10.1 Agent 导入路径变更

```python
# ❌ 旧路径（已删除）
from core.agent.simple import SimpleAgent
from core.agent.simple.rvrb_agent import RVRBAgent
from core.agent.multi import MultiAgentOrchestrator

# ✅ 新路径
from core.agent import Agent, create_agent, AgentFactory
from core.agent.execution import RVRExecutor, RVRBExecutor, MultiAgentExecutor
```

### 10.2 Context 导入变更

```python
# ❌ 旧路径（已删除）
from core.context.manager import ContextManager
from core.context.prompt_manager import PromptManager
from core.context.injector import Injector

# ✅ 新路径
from core.context.injectors import (
    InjectionOrchestrator,
    InjectionContext,
    create_default_orchestrator,
)
```

### 10.3 Tool 导入变更

```python
# ❌ 旧路径（已删除）
from core.tool.capability.registry import CapabilityRegistry
from core.tool.capability.router import CapabilityRouter
from core.tool.instance_registry import InstanceToolRegistry

# ✅ 新路径
from core.tool import (
    CapabilityRegistry,
    InstanceRegistry,
    ToolSelector,
    create_capability_registry,
    create_tool_selector,
)
```

### 10.4 创建 Agent 的新方式

```python
# ❌ 旧方式
agent = SimpleAgent(
    llm_service=llm,
    event_manager=em,
    schema=schema,
)

# ✅ 新方式
agent = await create_agent(
    strategy="rvr",      # 或 "rvr-b"、"multi"
    event_manager=em,
    schema=schema,
)

# 或使用 Factory
agent = await AgentFactory.from_schema(
    schema=schema,
    system_prompt="你是一个智能助手。",
    event_manager=em,
)
```

---

## 11. 附录：删除文件清单

### Agent 层

| 文件 | 行数 | 说明 |
|------|------|------|
| `core/agent/simple_agent.py` | 2,473 | 旧 SimpleAgent 实现 |
| `core/agent/simple/simple_agent.py` | 818 | |
| `core/agent/simple/simple_agent_context.py` | 270 | |
| `core/agent/simple/simple_agent_loop.py` | 451 | |
| `core/agent/simple/simple_agent_tools.py` | 621 | |
| `core/agent/simple/rvrb_agent.py` | 133 | |
| `core/agent/simple/errors.py` | 114 | |
| `core/agent/simple/mixins/backtrack_mixin.py` | 589 | |
| `core/agent/simple/mixins/stream_mixin.py` | 210 | |
| `core/agent/simple/mixins/tool_mixin.py` | 284 | |
| `core/agent/types.py` | 89 | |
| `core/agent/multi/README.md` | 385 | |

### Context 层

| 文件 | 行数 | 说明 |
|------|------|------|
| `core/context/manager.py` | 265 | |
| `core/context/prompt_manager.py` | 985 | |
| `core/context/conversation.py` | 501 | |
| `core/context/fusion.py` | 209 | |
| `core/context/injector.py` | 199 | |

### Tool 层

| 文件 | 行数 | 说明 |
|------|------|------|
| `core/tool/base.py` | 245 | |
| `core/tool/capability/invocation.py` | 409 | |
| `core/tool/capability/registry.py` | 712 | |
| `core/tool/capability/router.py` | 429 | |
| `core/tool/capability/types.py` | 163 | |
| `core/tool/instance_registry.py` | 623 | |
| `core/tool/result_compactor.py` | 511 | |
| `core/tool/unified_tool_caller.py` | 115 | |

### 测试文件

| 文件 | 行数 | 说明 |
|------|------|------|
| `comprehensive_test.py` | - | 废弃 |
| `tests/verify_refactoring.py` | 273 | |
| `tests/verify_skill_refactoring.py` | 340 | |
| `tests/verify_tool_selection_v76.py` | 216 | |

---

## 总结

V10.0 是一次重大的架构重构，核心改进包括：

1. **统一 Agent 架构**：通过 Strategy 模式实现执行策略解耦
2. **多渠道支持**：插件化的 Channels 架构
3. **分阶段上下文注入**：清晰的职责分离
4. **统一工具管理**：简化的注册表和选择器
5. **精简 Prompts**：符合 LLM-First 原则
6. **代码精简**：净减少约 8,000 行代码

---

*文档生成日期：2026-02-06*
