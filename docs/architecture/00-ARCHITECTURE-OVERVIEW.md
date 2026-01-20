# ZenFlux Agent V7.5 架构文档

> **最后更新**: 2026-01-19  
> **架构版本**: V7.5  
> **架构状态**: 生产就绪 - 多模型计费系统、消息会话管理、缓存预加载

---

## 目录

- [概述](#概述)
- [核心架构决策](#核心架构决策)
- [系统架构全景图](#系统架构全景图)
- [核心模块详解](#核心模块详解)
  - [共享路由层 (core/routing/)](#共享路由层-corerouting)
  - [共享 Plan 层 (core/planning/)](#共享-plan-层-coreplanning)
  - [计费系统 (core/billing/)](#计费系统-corebilling)
  - [Agent 引擎 (core/agent/)](#agent-引擎-coreagent)
  - [消息会话管理](#消息会话管理)
  - [上下文工程 (core/context/)](#上下文工程-corecontext)
  - [记忆系统 (core/memory/)](#记忆系统-corememory)
  - [工具能力层 (core/tool/)](#工具能力层-coretool)
  - [LLM 适配层 (core/llm/)](#llm-适配层-corellm)
  - [事件系统 (core/events/)](#事件系统-coreevents)
  - [监控系统 (core/monitoring/)](#监控系统-coremonitoring)
- [服务层与 API 架构](#服务层与-api-架构)
- [配置管理体系](#配置管理体系)
- [容错与弹性](#容错与弹性)
- [版本演进](#版本演进)
- [相关文档](#相关文档)

---

## 概述

ZenFlux Agent V7.5 是一个生产就绪的企业级 AI Agent 框架，支持单智能体和多智能体两种执行模式，提供完整的消息会话管理、多模型计费追踪、高性能缓存和异步持久化能力。

### 核心特性

| 特性 | 说明 | 技术实现 |
|------|------|---------|
| **多模型计费** | 精确追踪每次 LLM 调用，支持多模型混合 | `core/billing/` - EnhancedUsageTracker |
| **消息会话管理** | 两阶段持久化、异步写入、内存缓存 | `services/session_cache_service.py` |
| **缓存预加载** | 用户打开会话窗口时主动预热，提升首次响应速度 | `POST /conversations/{id}/preload` |
| **单/多智能体路由** | 基于复杂度自动路由，支持预算管理 | `core/routing/router.py` |
| **异步持久化** | Redis Streams 解耦，不阻塞 API 响应 | `infra/message_queue/` |
| **容错机制** | 网络重试、检查点恢复、熔断器 | `infra/resilience/` |

### 版本演进路线

```
V5.0 → V6.1 → V6.2 → V6.3 → V7.0 → V7.1 → V7.2 → V7.3 → V7.4 → V7.5
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
实例缓存  场景化   配置优先级  上下文   架构重构  多智能体  Critic  网络弹性  计费系统  多模型计费
LLM驱动  提示词   Schema兜底  三层防护  单/多独立  生产就绪  质量保证  重试机制  统一追踪  缓存计费
```

**当前版本（V7.5）核心改进**：
- ✅ **多模型计费系统**：LLMCallRecord + EnhancedUsageTracker，精确追踪每次调用
- ✅ **缓存计费规范**：符合 Claude Platform 规范，支持 cache_read/cache_write
- ✅ **消息会话管理**：两阶段持久化、异步写入、内存缓存、缓存预加载
- ✅ **框架统一**：UsageTracker = EnhancedUsageTracker，无冗余代码

---

## 核心架构决策

### 决策 1：单智能体与多智能体完全独立

**原则**：SimpleAgent 和 MultiAgentOrchestrator 是平级的执行框架，不互相调用。

```
用户请求 → ChatService → AgentRouter（路由层，默认启用）
                            ↓
                    路由决策 (use_multi_agent)
                         ┌─────┴─────┐
                         ↓           ↓
                  ┌──────────┐  ┌──────────────┐
                  │SimpleAgent│  │MultiAgent    │
                  │(单智能体) │  │Orchestrator  │
                  │           │  │(多智能体)    │
                  │ 线性执行   │  │ DAG 执行     │
                  │ plan_todo │  │ ✅ 工具加载   │
                  │           │  │ ✅ 记忆集成   │
                  └────┬──────┘  └──────┬───────┘
                       │                │
                       └───────┬────────┘
                               ↓
                        共享基础设施
          ✅ (LLM、Tool、Memory、Plan 协议) 完全集成
```

**关键约束**：
- `SimpleAgent` 不包含任何多智能体调用逻辑
- `MultiAgentOrchestrator` 不继承或调用 `SimpleAgent`
- 意图识别在路由层完成，执行框架只负责执行

### 决策 2：共享层剥离与路由决策依据

**原则**：将通用能力从 Agent 中剥离，形成独立的共享模块。

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           共享层架构                                      │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────────┐│
│  │                    core/routing/ (共享路由层)                        ││
│  │  ┌─────────────────┐ ┌─────────────────┐ ┌────────────────────┐    ││
│  │  │ IntentAnalyzer  │ │ AgentRouter     │ │ ComplexityScorer   │    ││
│  │  │ 意图识别        │ │ 路由决策        │ │ 复杂度评分         │    ││
│  │  └─────────────────┘ └─────────────────┘ └────────────────────┘    ││
│  └─────────────────────────────────────────────────────────────────────┘│
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────────┐│
│  │                    core/planning/ (共享 Plan 层)                     ││
│  │  ┌─────────────────┐ ┌─────────────────┐ ┌────────────────────┐    ││
│  │  │ Plan Protocol   │ │ PlanStorage     │ │ PlanValidators     │    ││
│  │  │ 数据协议        │ │ 持久化存储      │ │ 验证器             │    ││
│  │  │ linear/dag模式  │ │                 │ │                    │    ││
│  │  └─────────────────┘ └─────────────────┘ └────────────────────┘    ││
│  └─────────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────────┘
```

#### 路由决策依据

**决策流程**：
```
用户请求 → IntentAnalyzer（意图分析）→ ComplexityScorer（复杂度评分）→ 路由决策
                  ↓                              ↓
           IntentResult                   ComplexityScore
           • task_type                    • score (0-10)
           • complexity                   • level
           • complexity_score             • dimensions
           • needs_plan
           • needs_multi_agent
           • is_follow_up
           • skip_memory_retrieval
```

**路由规则**（按优先级）：
| 优先级 | 条件 | 决策 | 说明 |
|--------|------|------|------|
| 1 | `intent.needs_multi_agent == true` | 多智能体 | 意图分析明确需要多智能体协作 |
| 2 | `complexity_score > 5.0` | 多智能体 | 复杂度评分超过阈值 |
| 3 | 其他情况 | 单智能体 | 默认使用单智能体 |

**实现方式（Prompt-First 原则）**：
- IntentAnalyzer 直接输出 `complexity_score` (0-10)，LLM 一次性完成
- AgentRouter 优先使用 LLM 评分，ComplexityScorer 保留向后兼容

### 决策 3：三级配置优先级

```
┌────────────────────────────────────────────────────────────────────────┐
│                      配置优先级（从高到低）                              │
├────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   Level 1: config.yaml 显式配置                                         │
│   • 运营人员的场景化定制                                                │
│   • 字段有值 → 覆盖下级配置                                             │
│                           ↓                                             │
│   Level 2: LLM 推断的 Schema                                            │
│   • 基于 prompt.md 内容智能推断                                         │
│   • 语义理解业务需求                                                    │
│                           ↓                                             │
│   Level 3: DEFAULT_AGENT_SCHEMA（框架兜底）                             │
│   • 高质量的最佳实践配置                                                │
│   • 即使运营配置不全/错误也能稳定运行                                   │
│                                                                         │
└────────────────────────────────────────────────────────────────────────┘
```

### 决策 4：Prompt-First 原则

**核心哲学**：规则写在 Prompt 里，不写在代码里。

```
❌ 旧方式（代码硬编码）：
   if "excel" in prompt_lower:
       skills.append("xlsx")

✅ 新方式（LLM 语义分解）：
   运营 prompt.md → LLM 分解 → 场景化提示词
   • intent_prompt.md  (意图识别专用)
   • simple_prompt.md  (简单任务)
   • medium_prompt.md  (中等任务)
   • complex_prompt.md (复杂任务)
```

---

## 系统架构全景图

### 整体架构

```
┌────────────────────────────────────────────────────────────────────────────────────┐
│                             ZenFlux Agent V7.5                                      │
├────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                     │
│  ┌──────────────────────────────────────────────────────────────────────────────┐  │
│  │                          协议入口层（平级）                                   │  │
│  │  ┌──────────────────┐                     ┌──────────────────┐               │  │
│  │  │  routers/        │  HTTP/SSE           │    grpc/         │  gRPC         │  │
│  │  │  (FastAPI)       │ ◄──────             │                  │ ◄──────       │  │
│  │  │  • chat.py       │                     │  • servicer.py   │  (Go 调用)    │  │
│  │  └────────┬─────────┘                     └────────┬─────────┘               │  │
│  │           └────────────────────┬────────────────────┘                         │  │
│  └────────────────────────────────┼─────────────────────────────────────────────┘  │
│                                   ↓                                                 │
│  ┌──────────────────────────────────────────────────────────────────────────────┐  │
│  │                         services/ 业务逻辑层                                  │  │
│  │  ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐                 │  │
│  │  │ chat_service    │ │ conversation    │ │ session_cache   │                 │  │
│  │  │ • AgentRouter   │ │ • 对话管理      │ │ • 内存缓存      │                 │  │
│  │  │ • UsageResponse │ │ • 消息查询      │ │ • 缓存预加载    │                 │  │
│  │  └─────────────────┘ └─────────────────┘ └─────────────────┘                 │  │
│  │  ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐                 │  │
│  │  │ mem0_service    │ │ agent_registry  │ │ sandbox_service │                 │  │
│  │  │ • 长期记忆      │ │ • 实例注册      │ │ • E2B 沙箱调用  │                 │  │
│  │  └─────────────────┘ └─────────────────┘ └─────────────────┘                 │  │
│  └────────────────────────────────┬────────────────────────────────────────────┘  │
│                                   ↓                                                 │
│  ┌──────────────────────────────────────────────────────────────────────────────┐  │
│  │                       共享层 (V7.5 核心重构)                                  │  │
│  │  ┌────────────────────────────┐  ┌────────────────────────────┐              │  │
│  │  │  core/routing/             │  │  core/planning/            │              │  │
│  │  │  • IntentAnalyzer          │  │  • Plan Protocol           │              │  │
│  │  │  • AgentRouter             │  │  • PlanStorage             │              │  │
│  │  │  • ComplexityScorer        │  │  • PlanValidators          │              │  │
│  │  └────────────────────────────┘  └────────────────────────────┘              │  │
│  │  ┌────────────────────────────────────────────────────────────┐              │  │
│  │  │  core/billing/ 🆕 V7.5 统一计费                             │              │  │
│  │  │  • EnhancedUsageTracker    • LLMCallRecord                 │              │  │
│  │  │  • UsageResponse           • pricing.py (定价表)           │              │  │
│  │  └────────────────────────────────────────────────────────────┘              │  │
│  └──────────────────────────────────────────────────────────────────────────────┘  │
│                                   │                                                 │
│                        ┌──────────┴──────────┐                                      │
│                        ↓                     ↓                                      │
│  ┌──────────────────────────────┐  ┌──────────────────────────────┐                │
│  │   SimpleAgent (单智能体)      │  │  MultiAgentOrchestrator      │                │
│  │   • RVR 循环执行              │  │  (多智能体)                   │                │
│  │   • plan_todo 工具            │  │  • Leader-Worker 模式         │                │
│  │   • Mixin 模式（5个模块）     │  │  • 上下文隔离                 │                │
│  │   • UsageTracker 统计         │  │  • 检查点恢复                 │                │
│  │   core/agent/simple/          │  │  • Critic 评估                │                │
│  └──────────────────────────────┘  │  core/agent/multi/           │                │
│                        │            └──────────────────────────────┘                │
│                        └──────────┬──────────┘                                      │
│                                   ↓                                                 │
│  ┌──────────────────────────────────────────────────────────────────────────────┐  │
│  │                       core/ 核心能力层                                        │  │
│  │  ┌───────────────┐ ┌───────────────┐ ┌───────────────┐ ┌───────────────┐     │  │
│  │  │ core/context/ │ │ core/memory/  │ │ core/tool/    │ │ core/llm/     │     │  │
│  │  │ 上下文工程     │ │ 记忆系统      │ │ 工具能力      │ │ LLM 适配      │     │  │
│  │  │ • Compaction  │ │ • Working     │ │ • Executor    │ │ • Claude      │     │  │
│  │  │ • PromptMgr   │ │ • Mem0        │ │ • Loader      │ │ • OpenAI      │     │  │
│  │  │ • RAG         │ │ • User/System │ │ • Capability  │ │ • Gemini      │     │  │
│  │  └───────────────┘ └───────────────┘ └───────────────┘ └───────────────┘     │  │
│  │  ┌───────────────┐ ┌───────────────┐ ┌───────────────┐ ┌───────────────┐     │  │
│  │  │ core/events/  │ │ core/monitor/  │ │ core/prompt/  │ │core/inference/│     │  │
│  │  │ 事件系统       │ │ 监控系统      │ │ 提示词管理    │ │ 语义推理      │     │  │
│  │  │ • Dispatcher  │ │ • ProdMonitor │ │ • Cache       │ │ • Semantic    │     │  │
│  │  │ • Broadcaster │ │ • TokenAudit  │ │ • Writer      │ │   Inference   │     │  │
│  │  │ • Adapters    │ │               │ │               │ │               │     │  │
│  │  └───────────────┘ └───────────────┘ └───────────────┘ └───────────────┘     │  │
│  └──────────────────────────────────────────────────────────────────────────────┘  │
│                                   │                                                 │
│  ┌──────────────────────────────────────────────────────────────────────────────┐  │
│  │                        infra/ 基础设施层                                      │  │
│  │  ┌───────────────┐ ┌───────────────┐ ┌───────────────┐ ┌───────────────┐     │  │
│  │  │ database/     │ │ message_queue/│ │ cache/        │ │ resilience/   │     │  │
│  │  │ 数据库        │ │ Redis Streams │ │ Redis 缓存    │ │ 容错层        │     │  │
│  │  │ • Models      │ │ • Streams     │ │ • redis.py    │ │ • Breaker     │     │  │
│  │  │ • CRUD        │ │ • Workers    │ │               │ │ • Retry       │     │  │
│  │  └───────────────┘ └───────────────┘ └───────────────┘ └───────────────┘     │  │
│  └──────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                     │
└────────────────────────────────────────────────────────────────────────────────────┘
```

### 请求处理流程

```
用户请求
    │
    ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│ Phase 0: ChatService 入口                                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│  chat() → 验证 agent_id → 处理文件 → 创建 Conversation → 创建 Session       │
│  → get_agent() from AgentRegistry (原型池化，<5ms)                            │
│  → 启动 _run_agent()                                                         │
└─────────────────────────────────────────────────────────────────────────────┘
    │
    ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│ Phase 1: 路由决策 (统一路由层)                                              │
├─────────────────────────────────────────────────────────────────────────────┤
│  AgentRouter.route() (enable_routing=True，默认启用)                          │
│       ├─→ IntentAnalyzer.analyze() (使用 Haiku 快速分析)                     │
│       │        ↓                                                             │
│       │   IntentResult + complexity_score (0-10)                              │
│       │                                                                      │
│       └─→ RoutingDecision:                                                   │
│              • use_multi_agent: bool                                         │
│              • intent: IntentResult                                          │
│              • complexity_score: float                                       │
│              • fallback_reason: Optional[str]  (Budget不足时降级)            │
└─────────────────────────────────────────────────────────────────────────────┘
    │
    ↓ (根据 use_multi_agent 决策)
┌─────────────────────────────────────────────────────────────────────────────┐
│ Phase 2: Agent 执行                                                          │
├─────────────────────────────────────────────────────────────────────────────┤
│  if use_multi_agent:                                                        │
│     MultiAgentOrchestrator.execute()                                        │
│     ├─ 初始化共享资源 (ToolLoader, WorkingMemory, Mem0)                      │
│     ├─ Lead Agent 任务分解 (Sonnet)                                         │
│     ├─ Worker Agents 并行/串行 (Haiku)                                      │
│     │  • 动态加载工具                                                         │
│     │  • 工具调用 + LLM 推理                                                  │
│     ├─ Critic Agent 质量评估 (Sonnet)                                       │
│     └─ Lead Agent 结果综合                                                  │
│  else:                                                                       │
│     SimpleAgent.chat() (RVR 循环)                                            │
│     ├─ 接收 intent (来自路由层)                                              │
│     ├─ Tool Selection                                                       │
│     ├─ System Prompt 组装                                                   │
│     ├─ RVR Loop: React → Act → Validation → Reflection                      │
│     └─ Final Output                                                         │
└─────────────────────────────────────────────────────────────────────────────┘
    │
    ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│ Phase 3: 流式响应与持久化                                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│  SSE Events (EventBroadcaster)                                              │
│    • message_start/content_delta/tool_use/message_end                      │
│    • orchestrator_start/task_decomposition/agent_start/end                  │
│    • usage (计费信息)                                                        │
│                                                                              │
│  异步持久化 (Redis Streams)                                                 │
│    • 占位消息 → message_create_stream → InsertWorker → PostgreSQL           │
│    • 最终更新 → message_update_stream → UpdateWorker → PostgreSQL           │
│    • 内存缓存更新 (SessionCacheService)                                      │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 核心模块详解

### 共享路由层 (core/routing/)

**职责**：在服务层完成意图识别和路由决策，为执行框架提供统一入口。

**文件结构**：
```
core/routing/
├── __init__.py
├── intent_analyzer.py      # IntentAnalyzer (共享，使用 Haiku 快速分析)
├── router.py               # AgentRouter 路由决策器
└── complexity_scorer.py    # ComplexityScorer 复杂度评分（向后兼容）
```

**核心接口**：

```python
# core/routing/intent_analyzer.py
class IntentAnalyzer:
    """意图分析器（共享模块，单/多智能体共用）"""
    
    async def analyze(
        self, 
        user_query: str, 
        conversation_history: List[Message],
        user_id: Optional[str] = None
    ) -> IntentAnalysisResult:
        """
        分析用户意图（LLM 一次性输出所有判断）
        
        Returns:
            IntentAnalysisResult:
                - task_type: str
                - complexity: TaskComplexity
                - complexity_score: float  # 0-10，LLM 直接输出
                - needs_plan: bool
                - needs_multi_agent: bool
                - skip_memory_retrieval: bool
        """

# core/routing/router.py
class AgentRouter:
    """智能体路由器，决策使用单智能体还是多智能体"""
    
    async def route(
        self, 
        user_query: str, 
        conversation_history: List[Message],
        user_id: Optional[str] = None
    ) -> RoutingDecision:
        """
        路由决策流程：
        1. 意图识别 (IntentAnalyzer + Haiku)
        2. 复杂度评分 (优先使用LLM评分)
        3. 路由决策 (单/多智能体)
        4. Budget检查 (多智能体场景)
        
        Returns:
            RoutingDecision:
                - use_multi_agent: bool
                - intent: IntentResult
                - complexity_score: float
                - fallback_reason: Optional[str]
        """
```

### 共享 Plan 层 (core/planning/)

**职责**：定义统一的 Plan 数据协议，支持线性执行（单智能体）和 DAG 执行（多智能体）。

**核心数据结构**：

```python
# core/planning/protocol.py
class PlanStep(BaseModel):
    """Plan 步骤（单智能体和多智能体共享数据结构）"""
    id: str
    description: str
    status: Literal["pending", "in_progress", "completed", "failed"] = "pending"
    dependencies: List[str] = Field(default_factory=list)  # 支持 DAG
    result: Optional[str] = None
    error: Optional[str] = None

class Plan(BaseModel):
    """Plan 协议（统一数据结构）"""
    plan_id: str
    goal: str
    steps: List[PlanStep]
    execution_mode: Literal["linear", "dag"] = "linear"
    metadata: Dict[str, Any] = Field(default_factory=dict)
```

### 计费系统 (core/billing/)

**职责**：统一的 Token 计费管理，支持多模型调用追踪、缓存计费、成本分析。

**文件结构**：
```
core/billing/
├── __init__.py             # 统一导出接口
├── models.py               # LLMCallRecord, UsageResponse
├── tracker.py              # EnhancedUsageTracker（唯一实现）
└── pricing.py              # 模型定价表和成本计算
```

**核心数据模型**：

```python
# core/billing/models.py
class LLMCallRecord(BaseModel):
    """单次 LLM 调用记录"""
    call_id: str
    model: str                      # claude-sonnet-4 / claude-haiku-3.5
    purpose: str                    # intent_analysis / main_response
    input_tokens: int
    output_tokens: int
    thinking_tokens: int
    cache_read_tokens: int          # 缓存命中
    cache_write_tokens: int         # 缓存写入
    input_unit_price: float         # $/M tokens
    output_unit_price: float
    total_price: float              # 本次调用总价

class UsageResponse(BaseModel):
    """聚合响应（Dify 兼容）"""
    prompt_tokens: int              # = input + cache_read + cache_write
    completion_tokens: int
    thinking_tokens: int
    total_tokens: int
    total_price: float
    cache_hit_rate: float           # 缓存命中率
    cost_saved_by_cache: float       # 缓存节省成本
    llm_call_details: List[LLMCallRecord]  # 调用明细
```

**调用路径**：
```
SimpleAgent._chat_loop()
  ↓
usage_tracker.accumulate(response)  # 或 record_call()
  ↓
EnhancedUsageTracker 记录（自动计算价格）
  ↓
ChatService 调用 UsageResponse.from_tracker()
  ↓
SSE 事件 {"event": "usage", "data": {...}}
```

**统一别名**：
```python
# utils/usage_tracker.py
from core.billing.tracker import EnhancedUsageTracker
UsageTracker = EnhancedUsageTracker  # 统一使用
```

**定价模型（Claude Platform 官方价格 2026-01）**：

| 模型 | Input ($/M) | Output ($/M) | Cache Read ($/M) | Cache Write ($/M) |
|------|-------------|--------------|------------------|-------------------|
| Claude Opus 4.1 | $15.0 | $75.0 | $1.5 | $18.75 |
| Claude Opus 4 | $15.0 | $75.0 | $1.5 | $18.75 |
| Claude Sonnet 4 | $3.0 | $15.0 | $0.3 | $3.75 |
| Claude Sonnet 3.7 | $3.0 | $15.0 | $0.3 | $3.75 |
| Claude Haiku 3.5 | $0.8 | $4.0 | $0.08 | $1.0 |
| Claude Haiku 3 | $0.25 | $1.25 | $0.03 | $0.3 |

### Agent 引擎 (core/agent/)

**文件结构**（V7.6 模块化重构）：
```
core/agent/
├── __init__.py             # 统一导出接口（Simple + Multi）
├── factory.py              # Agent Factory 统一入口
├── simple/                 # Simple Agent 模块（独立）
│   ├── simple_agent.py     # 主入口 + 初始化
│   ├── simple_agent_context.py   # Prompt + Memory
│   ├── simple_agent_tools.py     # 工具执行 + HITL
│   ├── simple_agent_loop.py      # RVR 循环 + 流式处理
│   └── simple_agent_errors.py    # 错误处理工具
└── multi/                  # Multi Agent 模块（独立）
    ├── orchestrator.py     # MultiAgentOrchestrator
    ├── lead_agent.py       # LeadAgent 任务分解
    ├── critic.py           # CriticAgent 质量评估
    ├── checkpoint.py       # 检查点恢复机制
    └── models.py           # 多智能体数据模型
```

#### SimpleAgent（单智能体）

**职责**：单智能体执行框架，实现 RVR（Read-Reason-Act-Observe-Validate-Write-Repeat）循环。

**架构特点**：
- ✅ **意图分析外置化**：依赖路由层传入 `intent`
- ✅ **原型池优化**：`clone_for_session()` 性能提升10-20x
- ✅ **Billing 系统集成**：`EnhancedUsageTracker` 统一计费
- ✅ **模块化重构**：拆分为 5 个文件（Mixin 模式）

**核心方法**：

```python
class SimpleAgent:
    async def chat(
        self, 
        messages: List[Dict[str, str]],
        session_id: str,
        intent: Optional[IntentResult] = None  # V7: 从路由层接收
    ) -> AsyncGenerator[Dict, None]:
        """
        处理用户输入（流式返回）
        
        执行流程：
        1. 使用路由层传入的 Intent（不再执行内部分析）
        2. Tool Selection（Schema > Plan > Intent）
        3. System Prompt 组装（多层缓存 L1/L2/L3）
        4. RVR Loop 核心执行
        5. Final Output & Tracing Report
        """
    
    def clone_for_session(
        self,
        event_manager: EventBroadcaster,
        workspace_dir: Optional[Path] = None
    ) -> "SimpleAgent":
        """
        从原型克隆 Session 级实例（V7.1 优化）
        
        浅拷贝共享组件（共享）：
        - LLM Services
        - CapabilityRegistry
        - ToolExecutor
        - PromptCache
        
        重置 Session 级状态：
        - EventBroadcaster
        - UsageTracker
        - _plan_cache
        
        性能：<5ms（原 50-100ms）
        """
```

#### MultiAgentOrchestrator（多智能体）

**职责**：多智能体执行框架，支持 Leader-Worker 模式和 DAG 任务编排。

**架构特点**：
- ✅ **独立设计**：不继承 `SimpleAgent`，完全独立实现
- ✅ **Leader-Worker 模式**：Lead Agent (Opus) + Worker Agents (Sonnet)
- ✅ **检查点恢复**：长时间运行任务支持故障恢复
- ✅ **上下文隔离**：Subagent 独立上下文，减少 token 消耗
- ✅ **Critic 评估**：质量评估和改进建议

**执行模式**：
| 模式 | 适用场景 | 优点 | 缺点 |
|-----|---------|------|------|
| **串行模式** | 严格依赖关系 | 逻辑清晰、易调试 | 总耗时 = Σ(子任务耗时) |
| **并行模式** | 独立子任务 | 总耗时 ≈ max(子任务耗时) | Token消耗峰值高 |
| **混合模式** | 部分并行/部分串行 | 兼顾性能和依赖 | 管理复杂度高 |

**强弱配对策略**：
- **LeadAgent**: Opus (任务分解、结果聚合)
- **SubAgents**: Sonnet (执行具体子任务)
- **Critic**: Sonnet (质量评审)
- **成本优化**: 节省 39% (相比全Sonnet)

### 消息会话管理

> **详细文档**: [22-MESSAGE-SESSION-MANAGEMENT.md](./22-MESSAGE-SESSION-MANAGEMENT.md)

消息会话管理是 ZenFlux Agent 的核心基础设施，提供完整的消息生命周期管理、流式消息处理、高性能读取和异步持久化能力。

#### 核心特性

- ✅ **两阶段持久化**：占位消息 + 完整更新，保证流式消息可靠性
- ✅ **异步写入**：Redis Streams 解耦，不阻塞 API 响应
- ✅ **内存缓存**：SessionCacheService 实现纳秒级读取
- ✅ **缓存预加载**：用户打开会话窗口时主动预热，提升首次响应速度
- ✅ **游标分页**：支持长会话历史查询
- ✅ **合并写入优化**：计费信息与最终消息合并，减少 50% 数据库操作

#### 架构组件

```
ChatService → EventBroadcaster → MessageQueueClient → Redis Streams
     ↓              ↓                    ↓
SessionCacheService (内存缓存)    InsertWorker/UpdateWorker → PostgreSQL
```

#### 关键实现

| 组件 | 职责 | 文件位置 |
|------|------|----------|
| **ChatService** | 消息发送入口，流式处理 | `services/chat_service.py` |
| **EventBroadcaster** | 内容累积和持久化触发 | `core/events/broadcaster.py` |
| **SessionCacheService** | 内存会话上下文缓存 | `services/session_cache_service.py` |
| **MessageQueueClient** | Redis Streams 客户端 | `infra/message_queue/streams.py` |
| **InsertWorker/UpdateWorker** | 后台消息处理 | `infra/message_queue/workers.py` |

#### 数据流程

**写入流程**：
1. 创建占位消息 → Redis Streams → InsertWorker → PostgreSQL
2. 流式传输 → EventBroadcaster 累积 → SSE 发送
3. 最终更新（合并 usage）→ Redis Streams → UpdateWorker → PostgreSQL

**读取流程**：
1. 优先从 SessionCacheService 内存缓存读取
2. 缓存未命中时从数据库加载（冷启动）
3. 分页加载使用游标（`before_cursor`）
4. 预加载机制：用户打开会话窗口时主动预热缓存（`POST /conversations/{id}/preload`）

#### 缓存预加载机制

**设计目标**：用户打开会话窗口时，提前将历史消息加载到内存缓存，提升首次响应速度。

**实现方式**：

```python
class SessionCacheService:
    async def warmup_context(
        self,
        conversation_id: str,
        limit: int = 50,
        force: bool = False
    ) -> Dict[str, Any]:
        """
        预加载会话上下文到内存缓存
        
        Args:
            conversation_id: 对话 ID
            limit: 预加载消息数量（受 max_context_size 限制）
            force: 是否强制刷新（默认 False，缓存命中时直接返回）
            
        Returns:
            {
                "context": ConversationContext,
                "cache_hit": bool,
                "effective_limit": int
            }
        """
```

**API 接口**：`POST /api/v1/conversations/{conversation_id}/preload`

**性能优化**：
- ✅ **首次响应速度提升**：预加载后，首次消息查询命中缓存（纳秒级）
- ✅ **用户体验改善**：打开会话窗口时提前加载，用户感知延迟降低
- ✅ **智能缓存管理**：`force=false` 时，已存在缓存直接返回，避免重复加载

### 上下文工程 (core/context/)

**文件结构**：
```
core/context/
├── compaction/             # 上下文压缩三层防护
├── manager.py              # 上下文管理器
├── prompt_manager.py       # Prompt 分层管理
└── providers/              # 多种上下文提供商
```

#### 上下文压缩三层防护

```
┌─────────────────────────────────────────────────────────────────────────┐
│                  上下文压缩三层防护策略                                   │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  L1. Memory Tool 状态保存（Claude 自主）                                 │
│      → 在 System Prompt 中指导 Claude 使用 memory 工具保存重要状态       │
│      → 周期性保存当前工作进展                                            │
│                                                                          │
│  L2. 历史消息智能裁剪（服务层自动）                                      │
│      → 保留首轮对话（任务定义）                                          │
│      → 保留最近 N 轮（当前工作上下文）                                   │
│      → 保留关键 tool_result（数据和结果）                                │
│                                                                          │
│  L3. QoS 成本控制（后端监控）                                            │
│      → 根据用户等级设置 token 预算（FREE/BASIC/PRO/ENTERPRISE）          │
│      → 后端日志和成本统计                                                │
└─────────────────────────────────────────────────────────────────────────┘
```

### 记忆系统 (core/memory/)

**三层架构**：

```
┌────────────────────────────────────────────────────────────────────────┐
│                          Memory 三层架构                                │
├────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  会话级（Session Scope）- 当前会话                                      │
│  ┌────────────────────────────────────────────────────────────────┐    │
│  │ WorkingMemory (core/memory/working.py)                         │    │
│  │ • messages（消息历史）                                          │    │
│  │ • tool_calls（工具调用记录）                                    │    │
│  │ • plan_json / todo_md（当前任务计划）                          │    │
│  │ 生命周期：单个 Session（end_session 后清除）                    │    │
│  └────────────────────────────────────────────────────────────────┘    │
│                                                                         │
│  用户级（User Scope）- 跨 Session 保留                                  │
│  ┌────────────────────────────────────────────────────────────────┐    │
│  │ core/memory/user/                                               │    │
│  │ • EpisodicMemory（历史经验）                                    │    │
│  │ • PreferenceMemory（用户偏好）                                  │    │
│  │ • PlanMemory（任务计划持久化）                                  │    │
│  │ core/memory/mem0/                                               │    │
│  │ • Mem0 Pool（用户画像，长期记忆）                               │    │
│  └────────────────────────────────────────────────────────────────┘    │
│                                                                         │
│  系统级（System Scope）- 全局共享                                       │
│  ┌────────────────────────────────────────────────────────────────┐    │
│  │ core/memory/system/                                             │    │
│  │ • SkillMemory（Skills 注册表）                                  │    │
│  │ • CacheMemory（系统缓存）                                       │    │
│  └────────────────────────────────────────────────────────────────┘    │
│                                                                         │
└────────────────────────────────────────────────────────────────────────┘
```

### 工具能力层 (core/tool/)

**工具分类**（基于 Claude Platform 接口规范）：

```
┌────────────────────────────────────────────────────────────────────────┐
│                          Tool 系统架构                                  │
├────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ToolLoader（统一加载器）                                               │
│  • 类别化配置展开（sandbox_tools → 9个具体工具）                        │
│  • 核心工具自动启用（Level 1）                                          │
│  • Server-side / Client-side 工具统一注册                              │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐  │
│  │ Server-side Built-in Tools（Claude 原生支持）                     │  │
│  ├─────────────────────────────────────────────────────────────────┤  │
│  │  • Memory            # 记忆管理                                 │  │
│  │  • Text Editor       # 文本编辑                                 │  │
│  │  • Web Fetch         # 网页抓取                                 │  │
│  │  • Web Search        # 网络搜索                                 │  │
│  │  • PDF Reading       # PDF 读取（原生支持）                      │  │
│  └─────────────────────────────────────────────────────────────────┘  │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐  │
│  │ Client-side Custom Tools（客户自定义）                           │  │
│  ├─────────────────────────────────────────────────────────────────┤  │
│  │  • Agent Skills（Claude Skills）                                 │  │
│  │    - Pre-built: Excel, PowerPoint, PDF, Word                    │  │
│  │    - Custom: 自定义 SKILL.md                                    │  │
│  │  • MCP Tools（MCP 协议工具）                                     │  │
│  │  • Framework Built-in Tools（框架内置工具）                       │  │
│  │    - plan_todo, exa_search, knowledge_search                    │  │
│  └─────────────────────────────────────────────────────────────────┘  │
│                                                                         │
└────────────────────────────────────────────────────────────────────────┘
```

### LLM 适配层 (core/llm/)

**文件结构**：
```
core/llm/
├── base.py                 # LLM 基类
├── claude.py               # Claude 适配（支持网络重试）
├── openai.py               # OpenAI 适配
└── gemini.py               # Gemini 适配
```

**LLM Profile 配置**（`config/llm_config/profiles.yaml`）：

```yaml
# 主力模型
claude_sonnet:
  model: "claude-sonnet-4-5-20250929"
  max_tokens: 16384
  enable_thinking: true
  thinking_budget: 10000

# 意图识别（快速便宜）
claude_haiku:
  model: "claude-haiku-4-5-20251001"
  max_tokens: 8192
  enable_thinking: false
```

**网络重试机制（V7.3）**：
- 使用 `@with_retry` 装饰器（指数退避：1s → 2s → 4s）
- 自动处理：连接错误、超时、限流（429）
- 实现位置：`core/llm/claude.py` - `create_message_async` 方法

### 事件系统 (core/events/)

**文件结构**：
```
core/events/
├── manager.py              # 事件管理器
├── broadcaster.py          # 消息广播（内容累积、持久化触发）
├── dispatcher.py           # 事件分发器
└── adapters/               # 平台适配器
```

**事件类型**：
| 事件类别 | 说明 |
|---------|------|
| message_events | 消息相关事件 |
| content_events | 内容生成事件 |
| session_events | 会话管理事件 |
| context_events | 上下文管理事件 |
| progress_events | 进度事件 |

### 监控系统 (core/monitoring/)

**文件结构**：
```
core/monitoring/
├── token_budget.py          # 多智能体成本预算管理
├── token_audit.py          # Token 使用审计
├── production_monitor.py    # 生产环境监控
└── failure_detector.py     # 失败检测器
```

#### 多智能体成本预算管理

**核心功能**：
- 分层预算管理（FREE/BASIC/PRO/ENTERPRISE）
- 多智能体成本估算（~15× 单智能体，参考 Anthropic 数据）
- 预算检查与自动降级
- 实时 Token 监控

**使用方式**：
```python
from core.monitoring import get_token_budget

budget = get_token_budget()

# 检查预算
result = await budget.check_budget(
    user_tier="PRO",
    agent_type="multi",
    estimated_tokens=500_000
)

if not result.allowed:
    # 自动降级到单智能体
    agent_type = "single"
```

---

## 服务层与 API 架构

### 三层架构

```
协议入口层（平级）           业务逻辑层（共享）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
routers/ (FastAPI)           services/
├── chat.py          ────┐   ├── chat_service.py
├── conversation.py  ────┼──→├── conversation_service.py
├── health.py        ────┘   ├── agent_registry.py
└── mem0_router.py           └── mem0_service.py

grpc_server/ (gRPC)          ↑
├── chat_servicer.py ────────┘
├── session_servicer.py      （只写一次，被复用）
└── health_servicer.py
```

### 层次职责

| 层次 | 职责 | 禁止 |
|------|------|------|
| **routers/** | HTTP 协议处理，调用 Service | 不写业务逻辑 |
| **grpc_server/** | gRPC 协议处理，调用 Service | 不写业务逻辑 |
| **services/** | 业务逻辑实现，被两层复用 | 不处理协议细节 |

### 健康检查接口

```
/health/live     - 存活探针（Kubernetes liveness）
/health/ready    - 就绪探针（Kubernetes readiness）
/health/metrics  - 健康指标（熔断器状态、系统资源）
```

---

## 配置管理体系

### 实例配置 (instances/{name}/)

```
instances/my_agent/
├── prompt.md               # 运营写的系统提示词
├── config.yaml             # 实例配置（框架内置工具 + 运营可配置工具）
├── .env                    # 环境变量（API Keys）
├── api_desc/               # REST API 文档（运营可配置工具）
├── skills/                 # Custom Skills（运营可配置工具）
│   ├── skill_registry.yaml # Skills 注册表
│   └── [custom-skill]/     # 自定义 Skill
└── prompt_results/         # 自动生成的场景化提示词
    ├── _metadata.json
    ├── agent_schema.yaml
    ├── intent_prompt.md
    ├── simple_prompt.md
    ├── medium_prompt.md
    └── complex_prompt.md
```

**配置分类**：

| 配置类型 | 配置位置 | 说明 | 示例 |
|---------|---------|------|------|
| **框架内置工具** | `config.yaml` → `enabled_capabilities` | 启用/禁用框架提供的工具 | `plan_todo: 1`, `exa_search: 1` |
| **MCP Tools** | `config.yaml` → `mcp_tools` | 连接外部 MCP 服务器 | `{ name: "text2flow", server_url: "..." }` |
| **REST APIs** | `config.yaml` → `apis` + `api_desc/*.md` | 接入第三方 REST API | `{ name: "weather_api", base_url: "..." }` |
| **Custom Skills** | `skills/` 目录 + `skill_registry.yaml` | 自定义 Claude Skills | `skills/ontology-builder/SKILL.md` |

### config.yaml 示例

```yaml
instance:
  name: "my_agent"
  description: "我的智能体"
  version: "1.0.0"

agent:
  model: "claude-sonnet-4-5-20250929"
  max_turns: 20
  plan_manager_enabled: true
  allow_parallel_tools: false

# ==================== 框架内置工具配置 ====================
enabled_capabilities:
  # 内容生成类（Claude Pre-built Skills）
  pptx: 1                    # PPT 生成
  xlsx: 1                    # Excel 表格操作
  docx: 1                    # Word 文档生成
  pdf: 1                     # PDF 生成
  
  # 信息获取类
  web_search: 1              # 互联网搜索
  exa_search: 1              # Exa 语义搜索
  knowledge_search: 1        # 个人知识库检索
  
  # 核心工具
  plan_todo: 1               # 任务规划工具
  api_calling: 1             # 通用 API 调用

# ==================== 运营可配置工具 ====================
# MCP Tools（连接外部 MCP 服务器）
mcp_tools:
  - name: text2flowchart
    server_url: "https://api.dify.ai/mcp/server/XXX/mcp"
    server_name: "dify"
    auth_type: "bearer"
    auth_env: "DIFY_API_KEY"

# REST APIs（接入第三方 API）
apis:
  - name: weather_api
    base_url: "https://api.weather.com/v1"
    auth:
      type: api_key
      header: X-API-Key
      env: WEATHER_API_KEY
    doc: weather              # 对应 api_desc/weather.md
```

### 全局配置 (config/)

| 配置文件 | 用途 |
|----------|------|
| `config/resilience.yaml` | 容错配置（超时/重试/熔断） |
| `config/context_compaction.yaml` | 上下文压缩策略 |
| `config/capabilities.yaml` | 工具能力配置 |
| `config/llm_config/profiles.yaml` | LLM 配置 |
| `config/routing_rules.yaml` | 路由规则 |
| `config/storage.yaml` | 存储配置 |

---

## 容错与弹性

### 容错基础设施 (infra/resilience/)

**配置文件**：`config/resilience.yaml`

**核心机制**：

1. **网络重试机制（V7.3）** ✅
   - 使用 `@with_retry` 装饰器（指数退避：1s → 2s → 4s）
   - 自动处理：连接错误、超时、限流（429）
   - 实现位置：`core/llm/claude.py` - `create_message_async` 方法

2. **熔断器模式**
   - 状态机：CLOSED → OPEN → HALF_OPEN
   - 失败阈值触发熔断
   - 超时后进入半开状态探测

3. **超时控制**
   - LLM 调用超时：60s
   - 工具执行超时：30s
   - 数据库操作超时：5s

### 架构分层改进（V7.3）

**✅ 正确实现**：
- 在 `core/llm/claude.py` 的 `create_message_async` 方法上应用 `@with_retry`
- **优势**：
  - 所有 LLM 调用（SimpleAgent、MultiAgent、Critic）自动受益
  - 统一使用 `infra/resilience/retry.py` 的成熟实现
  - 关注点分离：业务层专注编排，基础设施层处理重试

---

## 版本演进

| 版本 | 日期 | 核心变化 |
|------|------|---------|
| **V7.5** | 2026-01-19 | **当前版本**：多模型计费系统 + 消息会话管理 + 缓存预加载 |
| V7.4 | 2026-01-16 | 统一计费系统 + Token 使用追踪 |
| V7.3 | 2026-01-16 | 网络弹性增强 + 统一重试机制 + 架构分层优化 |
| V7.2 | 2026-01-15 | 多智能体完整集成 + Critic Agent 质量保证 + 工具/记忆系统 |
| V7.1 | 2026-01-15 | 多智能体生产就绪 + Anthropic 启发优化（池化、Prompts Engineering、成本预算、检查点恢复） |
| V7.0 | 2026-01-15 | 单/多智能体独立 + 共享层剥离 + 生产就绪 |

**关键里程碑**：
- **V7.0**：架构重构，单/多智能体独立
- **V7.1**：原型池化，性能提升 90%+
- **V7.2**：多智能体完整集成，Critic 质量保证
- **V7.3**：网络弹性，统一重试机制
- **V7.4**：统一计费系统
- **V7.5**：多模型计费 + 消息会话管理 + 缓存预加载

---

## 相关文档

| 文档 | 说明 |
|------|------|
| [00-ARCHITECTURE-OVERVIEW.md](./00-ARCHITECTURE-OVERVIEW.md) | V7.5 架构总览（本文档） |
| [22-MESSAGE-SESSION-MANAGEMENT.md](./22-MESSAGE-SESSION-MANAGEMENT.md) | 消息会话管理架构详解 |
| [21-BILLING_V7.5_IMPLEMENTATION_SUMMARY.md](./21-BILLING_V7.5_IMPLEMENTATION_SUMMARY.md) | Token 计费系统 V7.5 完整文档 |
| [01-MEMORY-PROTOCOL.md](./01-MEMORY-PROTOCOL.md) | Memory-First Protocol 详解 |
| [03-EVENT-PROTOCOL.md](./03-EVENT-PROTOCOL.md) | SSE 事件协议 |
| [15-FRAMEWORK_PROMPT_CONTRACT.md](./15-FRAMEWORK_PROMPT_CONTRACT.md) | Prompt-Driven 设计契约 |
| [archived/](./archived/) | 历史版本 |

---

**文档版本**: V7.5  
**最后更新**: 2026-01-19  
**维护者**: ZenFlux Agent Team
