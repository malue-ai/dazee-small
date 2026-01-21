# Zenflux Agent 系统架构

> 版本: 7.1.0  
> 更新时间: 2026-01-20

## 一、系统整体架构

### 1.1 V7 架构总览

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              客户端 (Client)                                 │
│                     Web App / Mobile App / API Consumer                      │
└───────────────────────────────────┬─────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              入口层 (Entry Layer)                            │
├─────────────────────────────────┬───────────────────────────────────────────┤
│         HTTP/REST API           │              gRPC API                      │
│    (FastAPI - routers/*.py)     │    (grpc_server/*_servicer.py)            │
│         Port: 8000              │           Port: 50051                      │
└─────────────────────────────────┴───────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              服务层 (Service Layer)                          │
├─────────────────────────────────────────────────────────────────────────────┤
│  ChatService     │  SessionService  │  AgentRegistry  │  ConversationService│
├─────────────────────────────────────────────────────────────────────────────┤
│           Mem0Service  │  KnowledgeService  │  TaskService                  │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        🆕 V7 路由层 (Routing Layer)                          │
├─────────────────────────────────────────────────────────────────────────────┤
│   AgentRouter (路由决策)  │  IntentAnalyzer (意图分析)  │  ComplexityScorer   │
├─────────────────────────────────────────────────────────────────────────────┤
│                         路由决策: complexity_score                           │
│              ┌─────────────────┴─────────────────┐                          │
│              ▼                                   ▼                          │
│      < 0.6 (简单)                        >= 0.6 (复杂)                       │
│      SimpleAgent                    MultiAgentOrchestrator                  │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              核心层 (Core Layer)                             │
├─────────────────────────────────────────────────────────────────────────────┤
│    SimpleAgent    │    ClaudeService    │    ToolExecutor    │  EventManager │
│   (单智能体引擎)    │    (LLM 调用)        │    (工具执行)       │   (事件分发)   │
├─────────────────────────────────────────────────────────────────────────────┤
│ 🆕 MultiAgent    │  ToolSelector  │  PlanManager  │  ContextEngineering      │
│   Orchestrator   │   (工具选择)     │   (计划管理)   │    (上下文工程)          │
│  (多智能体编排)    │                │              │                         │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        🆕 V7 监控层 (Monitoring Layer)                       │
├─────────────────────────────────────────────────────────────────────────────┤
│  TokenAuditor (审计) │ UsageTracker (用量) │ UsageResponse (计费) │ Billing  │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           基础设施层 (Infrastructure)                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                        资源池架构 (infra/pools)                              │
│     UserPool (用户追踪)  │  AgentPool (实例管理)  │  SessionPool (追踪)      │
├──────────────────┬──────────────────┬──────────────────┬────────────────────┤
│      Redis       │     Database     │    MCP Servers   │    E2B Sandbox     │
│   (事件/缓存)      │   (PostgreSQL)   │   (外部工具)      │    (代码执行)       │
└──────────────────┴──────────────────┴──────────────────┴────────────────────┘
```

### 1.2 V7 路由决策流程

```
用户请求
    │
    ▼
┌──────────────────────────────────────┐
│         AgentRouter (路由层)          │
│  1. IntentAnalyzer: 分析用户意图       │
│  2. ComplexityScorer: 评估任务复杂度   │
└──────────────────────────────────────┘
    │
    ├─── complexity < 0.6 ───► SimpleAgent (单智能体)
    │                          快速响应，适合简单任务
    │
    └─── complexity >= 0.6 ──► MultiAgentOrchestrator (多智能体)
                               复杂任务分解，多角色协作
                               │
                               ├── Lead Agent (Opus) - 任务分解、结果综合
                               ├── Worker Agents (Sonnet) - 执行具体任务
                               └── Critic Agent (Sonnet) - 质量评审
```

### 1.3 V7 多智能体配置

| 配置模式 | Orchestrator | Worker | Critic | 适用场景 |
|---------|-------------|--------|--------|---------|
| `default` | Opus 4.5 | Sonnet 4.5 | Sonnet | 平衡质量和成本 |
| `cost_optimized` | Sonnet | Haiku | 关闭 | 控制成本 |
| `high_quality` | Opus | Opus | Opus | 追求最高质量 |
| `prototype` | Sonnet | Sonnet | 关闭 | 快速原型 |

## 二、资源池架构详解

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            ChatService                                       │
│  ├── session_service       → Session 生命周期管理                            │
│  ├── session_pool          → 活跃 Session 追踪（整合各池状态）                │
│  └── agent_pool            → Agent 获取/释放                                 │
└─────────────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         SessionPool (追踪层)                                 │
│  ├── on_session_start()    → 更新 UserPool + AgentPool + Redis Set          │
│  ├── on_session_end()      → 更新 UserPool + AgentPool + Redis Set          │
│  ├── get_system_stats()    → 汇总系统统计                                    │
│  ├── calibrate()           → 校准活跃 Session（清理孤立记录）                 │
│  └── 维护 zf:sessions:active (Set) 可靠追踪                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                   │                                          │
│    ┌──────────────────────────────┼──────────────────────────────┐           │
│    ▼                              ▼                              ▼           │
│ ┌─────────────────┐    ┌─────────────────────┐    ┌─────────────────────┐   │
│ │    UserPool     │    │      AgentPool      │    │  🆕 MCPPool         │   │
│ │ ├─ add_session  │    │  ├── preload_all    │    │  ├── preconnect_all │   │
│ │ ├─ remove_sess  │    │  ├── acquire        │    │  ├── get_client     │   │
│ │ ├─ get_stats    │    │  │   ├─ 快路径:clone │    │  ├── health_check   │   │
│ │ └─ 限流预留     │    │  │   └─ 慢路径:创建  │    │  ├── auto_reconnect │   │
│ │                 │    │  ├── release        │    │  └── get_stats      │   │
│ │                 │    │  └── get_stats      │    │                     │   │
│ └─────────────────┘    └─────────────────────┘    └─────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Redis                                           │
│  zf:sessions:active           → Set: 所有活跃 Session ID（可靠追踪）          │
│  zf:sessions:meta:{session_id}→ Hash: Session 元数据（user_id, agent_id）    │
│  zf:user:{user_id}:sessions   → Set: 用户活跃 Session 列表                   │
│  zf:user:{user_id}:stats      → Hash: 用户统计                              │
│  zf:agent:{agent_id}:instances→ String: 当前活跃实例数（原子计数）            │
│  zf:agent:{agent_id}:stats    → Hash: Agent 调用统计                        │
│  🆕 zf:mcp:{server}:stats     → Hash: MCP 调用统计                          │
│  🆕 zf:mcp:{server}:health    → String: 最后健康检查时间                     │
│  🆕 zf:mcp:active             → Set: 活跃的 MCP 服务器                       │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.1 MCPPool 架构

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            MCPPool (连接池)                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│  职责：                                                                      │
│  - 应用启动时预连接所有 MCP 服务器                                            │
│  - 提供统一的客户端获取接口（带并发控制）                                      │
│  - 健康检查和自动重连                                                        │
│  - 统计监控                                                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                     MCPServerState (每个服务器)                       │    │
│  │  ├── config: MCPConfig        # 配置（URL、认证、超时等）             │    │
│  │  ├── client: MCPClientWrapper # 客户端实例                           │    │
│  │  ├── connected: bool          # 连接状态                             │    │
│  │  ├── tools_count: int         # 工具数量                             │    │
│  │  └── reconnect_attempts: int  # 重连尝试次数                          │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                             │
│  主要方法：                                                                  │
│  ├── preconnect_all()      → 并行预连接所有 MCP 服务器                       │
│  ├── get_client(url)       → 获取/复用 MCP 客户端（带并发信号量）            │
│  ├── start_health_check()  → 启动后台健康检查任务                            │
│  ├── stop_health_check()   → 停止健康检查                                   │
│  └── cleanup()             → 清理所有连接                                   │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 MCPPool 启动流程

```
应用启动 (main.py lifespan)
    │
    ├── 1. MCPPool.preconnect_all()    ← 在 AgentPool 之前
    │       ├── 从 AgentRegistry 收集 MCP 配置
    │       ├── 并行连接所有 MCP 服务器
    │       └── 建立连接，缓存客户端实例
    │
    ├── 2. AgentPool.preload_all()     ← 使用 MCPPool 中的连接
    │       └── 创建 Agent 原型时，MCP 工具使用已建立的连接
    │
    └── 3. MCPPool.start_health_check()
            └── 启动后台健康检查任务（30s 间隔）
```

### 2.3 资源池职责

| 组件 | 职责 | 存储 |
|---|------|------|
| **UserPool** | 用户活跃 Session 追踪、统计、限流预留 | Redis |
| **AgentPool** | Agent 原型缓存、实例获取/释放（含 fallback）、使用统计 | 本地内存 + Redis |
| **SessionPool** | 追踪层：追踪活跃 Session 集合、提供统计视图、Session 校准 | Redis |
| **🆕 MCPPool** | MCP 客户端连接复用、健康检查、自动重连、调用统计 | 本地内存 + Redis |

## 三、系统详细架构

```mermaid
flowchart TB
    subgraph client [客户端]
        WEB[Web App]
        MOBILE[Mobile App]
        API_CLIENT[API Consumer]
    end

    subgraph entry [入口层]
        subgraph http [HTTP/REST - Port 8000]
            CHAT_ROUTER[chat.py<br/>聊天接口]
            CONV_ROUTER[conversation.py<br/>对话管理]
            AGENT_ROUTER[agents.py<br/>Agent 管理]
            AUTH_ROUTER[auth.py<br/>认证]
            FILES_ROUTER[files.py<br/>文件上传]
        end
        subgraph grpc [gRPC - Port 50051]
            CHAT_SERVICER[ChatServicer]
            SESSION_SERVICER[SessionServicer]
            HEALTH_SERVICER[HealthServicer]
        end
    end

    subgraph service [服务层 - services/]
        CS[ChatService<br/>核心对话服务]
        SS[SessionService<br/>会话管理]
        AR[AgentRegistry<br/>Agent 配置注册]
        CONV_SVC[ConversationService<br/>对话持久化]
        MEM0_SVC[Mem0Service<br/>用户记忆]
        TASK_SVC[TaskService<br/>后台任务]
        FILE_SVC[FileService<br/>文件处理]
        MCP_SVC[MCPService<br/>MCP 客户端]
    end

    subgraph core [核心层 - core/]
        subgraph agent_module [agent/]
            SA[SimpleAgent<br/>编排引擎]
            IA[IntentAnalyzer<br/>意图分析]
            FACTORY[AgentFactory<br/>Agent 工厂]
        end
        subgraph llm_module [llm/]
            CLAUDE[ClaudeService<br/>Claude API]
            ADAPTOR[ClaudeAdaptor<br/>消息适配]
        end
        subgraph tool_module [tool/]
            TE[ToolExecutor<br/>工具执行器]
            TS[ToolSelector<br/>工具选择器]
            CR[CapabilityRegistry<br/>能力注册表]
        end
        subgraph event_module [events/]
            EM[EventManager<br/>事件管理器]
            EB[EventBroadcaster<br/>事件广播器]
            ADAPTER[ZenOAdapter<br/>格式适配器]
        end
        subgraph context_module [context/]
            CE[ContextEngineering<br/>上下文工程]
            COMPACT[Compaction<br/>上下文压缩]
        end
    end

    subgraph infra [基础设施层 - infra/]
        subgraph pools [资源池 - pools/]
            SP[SessionPool<br/>活跃 Session 追踪]
            UP[UserPool<br/>用户追踪]
            AP[AgentPool<br/>实例管理]
        end
        REDIS[(Redis<br/>事件流/缓存/池状态)]
        DB[(Database<br/>PostgreSQL)]
        MCP_SERVER[MCP Servers<br/>外部工具服务]
        E2B[E2B Sandbox<br/>代码执行沙箱]
    end

    %% 客户端到入口
    WEB --> CHAT_ROUTER
    MOBILE --> CHAT_SERVICER
    API_CLIENT --> CHAT_ROUTER
    API_CLIENT --> CHAT_SERVICER

    %% 入口到服务
    CHAT_ROUTER --> CS
    CHAT_SERVICER --> CS
    CONV_ROUTER --> CONV_SVC
    AGENT_ROUTER --> AR
    FILES_ROUTER --> FILE_SVC

    %% ChatService 到资源池
    CS --> SS
    CS --> SP
    CS --> AP
    CS --> CONV_SVC
    CS --> MEM0_SVC
    CS --> TASK_SVC

    %% 资源池内部关系
    SP --> UP
    SP --> AP
    AP --> AR

    %% AgentPool 到 Agent
    AP --> SA
    AR --> FACTORY
    FACTORY --> SA

    %% Agent 内部
    SA --> IA
    SA --> CLAUDE
    SA --> TE
    SA --> EM
    SA --> CE

    %% LLM 模块
    CLAUDE --> ADAPTOR

    %% 工具模块
    TE --> CR
    TE --> TS

    %% 事件模块
    EM --> EB
    EB --> ADAPTER

    %% 基础设施连接
    SS --> REDIS
    SP --> REDIS
    UP --> REDIS
    AP --> REDIS
    EM --> REDIS
    CONV_SVC --> DB
    AR --> DB
    SA --> MCP_SERVER
    TE --> E2B
    MCP_SVC --> MCP_SERVER
```

## 四、核心流程图

### 4.1 对话请求流程（含错误处理）

```mermaid
sequenceDiagram
    participant C as Client
    participant R as Router/gRPC
    participant CS as ChatService
    participant SP as SessionPool
    participant AP as AgentPool
    participant SS as SessionService
    participant SA as SimpleAgent
    participant LLM as ClaudeService
    participant Redis as Redis

    C->>R: POST /api/v1/chat
    R->>CS: chat(message, user_id, agent_id)
    
    Note over CS: 1. 验证 agent_id
    Note over CS: 2. 处理文件附件
    Note over CS: 3. 创建/获取 Conversation
    
    CS->>SP: check_can_create_session(user_id)
    SP-->>CS: allowed
    
    CS->>SS: create_session()
    SS-->>CS: session_id
    
    CS->>AP: acquire(agent_id, event_manager, ...)
    
    alt agent_id 在原型池中（快路径）
        AP->>AP: prototype.clone()
        AP-->>CS: cloned_agent (< 1ms)
    else 不在池中（慢路径 fallback）
        AP->>AP: 记录 warning 日志
        AP->>AP: Registry.get_agent()
        AP-->>CS: new_agent (50-100ms)
    end
    
    AP->>Redis: INCR instances count
    
    CS->>SP: on_session_start(session_id, user_id, agent_id)
    SP->>Redis: SADD sessions:active session_id
    SP->>Redis: HSET sessions:meta:{id} user_id, agent_id
    
    CS->>SA: agent.chat(messages, session_id)
    
    loop RVR 循环
        SA->>LLM: create_message()
        
        alt LLM 调用成功
            LLM-->>SA: response (text/tool_use)
        else LLM 调用失败
            LLM-->>SA: error
            SA->>SA: 记录错误到 context_engineering
            Note over SA: 错误保留，供下轮使用
        end
        
        alt 有工具调用
            SA->>SA: tool_executor.execute()
            alt 工具执行失败
                SA->>SA: 生成 is_error: true 的 tool_result
            end
            SA->>LLM: 继续对话（包含工具结果）
        end
        
        SA->>Redis: 发布事件
    end
    
    alt 执行成功
        SA-->>CS: 完成
        CS->>AP: release(agent_id)
        AP->>Redis: DECR instances count
        CS->>SP: on_session_end(session_id, user_id, agent_id)
        SP->>Redis: SREM sessions:active session_id
        SP->>Redis: DEL sessions:meta:{id}
        CS->>SS: end_session(session_id, status="completed")
    else 执行失败
        SA-->>CS: 异常
        Note over CS: 确保资源释放
        CS->>AP: release(agent_id)
        CS->>SP: on_session_end(session_id, user_id, agent_id)
        CS->>SS: end_session(session_id, status="failed")
        CS->>CS: 发送 error 事件到客户端
    end
    
    CS-->>R: SSE 事件流
    R-->>C: 流式响应
```

### 4.2 资源池初始化流程

```mermaid
flowchart TB
    subgraph startup [服务启动阶段 - main.py lifespan]
        A[init_database] --> B[preload_agent_registry]
        B --> C[AgentRegistry.preload_all]
        C --> D[加载 instances/ 配置]
        D --> E[加载 InstancePromptCache]
        E --> F[存入 _configs Dict]
        
        F --> G[init_pools]
        G --> H[get_agent_pool]
        H --> I[AgentPool.preload_all]
        I --> J[从 Registry 创建 Agent 原型]
        J --> K[存入 _prototypes Dict]
        K --> L[初始化 Redis 元数据]
        
        L --> M[get_session_pool]
        M --> N[SessionPool.calibrate]
        N --> O{有孤立 Session?}
        O -->|是| P[清理孤立记录]
        O -->|否| Q[跳过]
        P --> Q
    end

    subgraph runtime [运行时阶段]
        R[用户请求] --> S{agent_id 在原型池中?}
        S -->|是| T[快路径: prototype.clone]
        S -->|否| U[慢路径: Registry.get_agent]
        T --> V[注入 event_manager]
        U --> V
        V --> W[执行 Agent.chat]
        W --> X{执行结果}
        X -->|成功| Y[释放 Agent]
        X -->|失败| Z[释放 Agent + 发送错误事件]
        Y --> AA[on_session_end]
        Z --> AA
    end

    startup --> runtime
```

### 4.3 事件流转流程

```mermaid
flowchart LR
    subgraph agent [SimpleAgent]
        A1[LLM 响应] --> A2[生成事件]
    end

    subgraph broadcaster [EventBroadcaster]
        B1[接收事件] --> B2[累积内容]
        B2 --> B3[EventManager]
    end

    subgraph storage [RedisSessionManager.buffer_event]
        S1[格式转换] --> S2[Redis INCR seq]
        S2 --> S3[存入 Redis]
        S3 --> S4[Pub/Sub 发布]
    end

    subgraph client [客户端]
        C1[SSE 订阅]
        C2[gRPC Stream]
    end

    A2 --> B1
    B3 --> S1
    S4 --> C1
    S4 --> C2
```

### 4.3.1 🆕 V7.2 事件系统架构（重构后）

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              事件流程（简化版）                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│    SimpleAgent / ChatService                                                │
│         │                                                                   │
│         ▼                                                                   │
│    EventBroadcaster / EventManager  ← 统一事件入口                           │
│         │                                                                   │
│         │  Agent 使用 EventBroadcaster（含累积、持久化等增强功能）            │
│         │  Service 使用 EventManager（纯粹的事件发送）                       │
│         │                                                                   │
│         ▼                                                                   │
│    BaseEventManager._send_event()  ← 所有事件最终走这里                      │
│         │                                                                   │
│         ▼                                                                   │
│    storage.buffer_event()  ← 统一处理入口                                    │
│         │                                                                   │
│         ├── 格式转换（ZenO adapter，如果需要）                               │
│         ├── Redis INCR 生成 seq（原子操作）                                  │
│         ├── 存入 Redis List                                                 │
│         └── Pub/Sub 发布（实时推送）                                         │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**V7.2 事件系统设计原则：**

| 原则 | 说明 |
|------|------|
| **单一入口** | 所有事件通过 `EventManager` 进入 |
| **统一 seq 生成** | seq 在 `buffer_event` 中由 Redis INCR 原子生成 |
| **格式转换前置** | 进入 Redis 前完成格式转换（Zenflux → ZenO） |
| **存储实现分离** | 生产环境用 `RedisSessionManager`，开发环境用 `InMemoryEventStorage` |

**Redis Key 设计：**
```
session:{session_id}:seq      → String: 事件序号计数器（Redis INCR）
session:{session_id}:events   → List: 事件缓冲列表
session:{session_id}:stream   → Pub/Sub: 实时事件通道
```

### 4.4 AgentPool 获取流程（含 fallback）

```mermaid
flowchart TB
    A[AgentPool.acquire] --> B{已初始化?}
    B -->|否| C[preload_all]
    C --> D{检查实例数限制}
    B -->|是| D
    
    D -->|超限| E[记录 warning]
    D -->|未超限| F{agent_id 在原型池?}
    E --> F
    
    F -->|是| G[快路径]
    G --> H[prototype.clone]
    H --> I[注入 event_manager]
    
    F -->|否| J[慢路径 fallback]
    J --> K[记录 warning 日志]
    K --> L{是默认 Agent?}
    L -->|是| M[create_simple_agent]
    L -->|否| N[Registry.get_agent]
    M --> I
    N --> I
    
    I --> O[INCR instances count]
    O --> P[increment_stat total_acquires]
    P --> Q[返回 Agent 实例]
```

## 五、目录结构

```
zenflux_agent/
├── main.py                          # 应用入口，lifespan 管理
├── logger.py                        # 日志配置
│
├── routers/                         # HTTP 路由层
│   ├── chat.py                      # 聊天接口
│   ├── conversation.py              # 对话管理
│   ├── agents.py                    # Agent CRUD
│   ├── auth.py                      # 认证
│   ├── files.py                     # 文件上传
│   └── ...
│
├── grpc_server/                     # gRPC 服务
│   ├── server.py                    # gRPC 服务器
│   ├── chat_servicer.py             # Chat 服务实现
│   ├── session_servicer.py          # Session 服务实现
│   └── ...
│
├── services/                        # 服务层（业务逻辑）
│   ├── chat_service.py              # 核心对话服务（🆕 含路由层集成）
│   ├── session_service.py           # Session 生命周期管理
│   ├── agent_registry.py            # Agent 配置注册表
│   ├── conversation_service.py      # 对话持久化
│   ├── redis_manager.py             # Redis 连接管理
│   ├── mem0_service.py              # 用户记忆
│   ├── mcp_client.py                # MCP 客户端
│   └── ...
│
├── core/                            # 核心模块
│   ├── agent/                       # Agent 实现
│   │   ├── simple_agent.py          # 单智能体编排引擎
│   │   ├── factory.py               # Agent 工厂
│   │   ├── types.py                 # 类型定义（IntentResult 等）
│   │   └── multi/                   # 🆕 V7: 多智能体系统
│   │       ├── __init__.py          # 模块导出
│   │       ├── orchestrator.py      # 多智能体编排器
│   │       ├── lead_agent.py        # 主控智能体
│   │       ├── critic.py            # 评审智能体
│   │       ├── checkpoint.py        # 检查点管理
│   │       └── models.py            # 数据模型
│   │
│   ├── routing/                     # 🆕 V7: 路由层
│   │   ├── __init__.py              # 模块导出
│   │   ├── router.py                # AgentRouter 路由决策器
│   │   ├── intent_analyzer.py       # IntentAnalyzer 意图分析
│   │   └── complexity_scorer.py     # ComplexityScorer 复杂度评分
│   │
│   ├── monitoring/                  # 🆕 V7: 监控系统
│   │   ├── __init__.py              # 模块导出
│   │   ├── token_audit.py           # Token 审计
│   │   ├── token_budget.py          # Token 预算管理
│   │   ├── production_monitor.py    # 生产监控
│   │   ├── failure_detector.py      # 失败检测
│   │   └── failure_case_db.py       # 失败案例数据库
│   │
│   ├── billing/                     # 🆕 V7: 计费系统
│   │   ├── __init__.py              # 模块导出
│   │   ├── pricing.py               # 多模型定价
│   │   ├── tracker.py               # 费用追踪
│   │   └── models.py                # 计费数据模型
│   │
│   ├── planning/                    # 🆕 V7: 计划层
│   │   ├── __init__.py              # 模块导出
│   │   ├── protocol.py              # 计划协议
│   │   ├── storage.py               # 计划存储
│   │   └── validators.py            # 计划验证器
│   │
│   ├── llm/                         # LLM 服务
│   │   ├── claude.py                # Claude API 封装
│   │   ├── adaptor.py               # 消息格式适配器
│   │   └── base.py                  # 基础类型定义
│   │
│   ├── tool/                        # 工具系统
│   │   ├── executor.py              # 工具执行器
│   │   ├── selector.py              # 工具选择器
│   │   └── capability.py            # 能力注册表
│   │
│   ├── events/                      # 事件系统（🆕 V7.1 重构）
│   │   ├── manager.py               # 事件管理器（聚合各层 EventManager）
│   │   ├── broadcaster.py           # 事件广播器（Agent 统一入口）
│   │   ├── base.py                  # 基类和 EventStorage Protocol
│   │   ├── storage.py               # InMemoryEventStorage（开发环境）
│   │   ├── dispatcher.py            # 外部 Webhook 发送器
│   │   ├── *_events.py              # 各层事件管理器（session/message/content 等）
│   │   └── adapters/                # 格式适配器（ZenO 等）
│   │
│   └── context/                     # 上下文管理
│       ├── compaction/              # 上下文压缩
│       ├── runtime.py               # 运行时上下文
│       └── rag_optimization.py      # 🆕 V7: RAG 优化
│
├── models/                          # 数据模型
│   ├── __init__.py                  # 模块导出
│   ├── usage.py                     # 🆕 V7: UsageResponse 计费响应模型
│   └── ...
│
├── evaluation/                      # 🆕 V7: 评估框架
│   ├── __init__.py                  # 模块导出
│   ├── harness.py                   # 测试框架
│   ├── models.py                    # 评估数据模型
│   ├── qos_config.py                # QoS 配置
│   ├── graders/                     # 评分器
│   │   ├── code_based.py            # 代码评测
│   │   ├── model_based.py           # 模型评测
│   │   └── human.py                 # 人工评测
│   └── config/                      # 评估配置
│       └── settings.yaml
│
├── tools/                           # 内置工具
│   ├── web_search.py                # 网页搜索
│   ├── api_calling.py               # API 调用
│   └── ...
│
├── utils/                           # 工具函数
│   ├── usage_tracker.py             # Token 用量追踪（与 UsageResponse 关联）
│   └── ...
│
├── infra/                           # 基础设施
│   ├── pools/                       # 资源池（追踪活跃资源）
│   │   ├── __init__.py              # 导出
│   │   ├── user_pool.py             # 用户池（用户活跃 Session 追踪）
│   │   ├── agent_pool.py            # Agent 池（原型缓存+实例管理）
│   │   ├── session_pool.py          # Session 池（活跃 Session 追踪+统计）
│   │   └── mcp_pool.py              # 🆕 MCP 池（连接复用+健康检查+自动重连）
│   ├── database/                    # 数据库
│   │   ├── __init__.py              # 连接管理
│   │   ├── crud.py                  # CRUD 操作
│   │   └── models.py                # ORM 模型
│   └── resilience/                  # 容错机制
│       ├── circuit_breaker.py       # 熔断器
│       └── retry.py                 # 重试（🆕 V7: with_retry 统一重试）
│
├── config/                          # 全局配置
│   ├── llm_config.py                # LLM 配置
│   ├── capabilities.yaml            # 工具能力配置
│   ├── multi_agent_config.yaml      # 🆕 V7: 多智能体配置
│   └── ...
│
├── instances/                       # Agent 实例配置
│   ├── _template/                   # 模板
│   ├── test_agent/                  # 测试 Agent
│   │   ├── config.yaml              # 配置
│   │   ├── prompt.md                # 提示词
│   │   └── .cache/                  # 缓存
│   └── ...
│
└── docs/                            # 文档
    ├── architecture/                # 架构文档
    │   └── SYSTEM_ARCHITECTURE.md   # 本文件
    └── analysis/                    # 🆕 V7: 流程分析
        ├── SIMPLE_AGENT_FLOW_ANALYSIS.md
        └── MULTI_AGENT_FLOW_ANALYSIS.md
```

## 六、关键设计决策

### 6.1 资源池架构

**问题**: 
- 每次请求创建 Agent 实例耗时 50-100ms
- 缺乏用户级并发控制
- 缺乏系统级监控视图
- 简单计数器在服务重启后不可靠

**方案**: 资源池架构（UserPool + AgentPool + SessionPool）

| 组件 | 问题解决 | 实现方式 |
|---|---------|---------|
| **AgentPool** | Agent 创建慢 | 原型缓存 + clone() 复用 + fallback 机制 |
| **UserPool** | 用户并发控制 | Redis Set 追踪 + 统计 |
| **SessionPool** | 系统监控 + 可靠性 | 追踪活跃 Session + Set 存储 + 校准机制 |

**Redis Key 设计**（改进版）:
```
# SessionPool 管理
zf:sessions:active              # Set: 所有活跃 Session ID（可靠追踪）
zf:sessions:meta:{session_id}   # Hash: Session 元数据（user_id, agent_id, start_time）

# UserPool 管理
zf:user:{user_id}:sessions      # Set: 用户活跃 Session
zf:user:{user_id}:stats         # Hash: 用户统计

# AgentPool 管理
zf:agent:{agent_id}:instances   # String: 活跃实例计数
zf:agent:{agent_id}:stats       # Hash: Agent 统计
```

**校准机制**:
- 服务启动时自动调用 `SessionPool.calibrate()`
- 检查 `zf:sessions:active` 中的每个 Session
- 移除没有对应元数据的孤立 Session
- 确保计数准确性

### 6.2 AgentRegistry vs AgentPool

| | AgentRegistry | AgentPool |
|--|---------------|-----------|
| **职责** | 配置管理 + 工厂 | 实例缓存 + 统计 |
| **存储** | 内存（配置数据） | 内存（原型） + Redis（统计） |
| **创建 Agent** | 从配置文件创建 | 从原型克隆（含 fallback） |
| **性能** | 慢（每次加载配置） | 快（克隆原型 < 1ms） |

**依赖关系**: AgentPool 依赖 AgentRegistry 的配置来创建原型

**Fallback 机制**:
```
acquire(agent_id) →
  if agent_id in _prototypes:
    快路径: prototype.clone() (< 1ms)
  else:
    慢路径: Registry.get_agent() (50-100ms)
    记录 warning 日志
```

### 6.3 依赖注入支持

为了便于测试，所有单例函数都支持依赖注入：

```python
# 默认使用单例
session_pool = get_session_pool()

# 测试时注入 mock
session_pool = get_session_pool(
    redis_manager=mock_redis,
    user_pool=mock_user_pool,
    agent_pool=mock_agent_pool
)

# 重置单例（测试后清理）
reset_session_pool()
```

### 6.4 双协议支持

**HTTP (FastAPI)**:
- RESTful API，适合 Web 应用
- SSE 流式响应
- 文档自动生成 (Swagger)

**gRPC**:
- 高性能 RPC，适合服务间调用
- 双向流式传输
- 强类型 protobuf

两者共享 `ChatService` 单例，保证业务逻辑一致。

### 6.5 事件驱动架构（🆕 V7.2 重构）

**核心设计：**
- Agent 执行过程产生事件流（Zenflux 内部格式）
- 统一通过 `EventManager` 入口（Agent 使用 EventBroadcaster 包装）
- `buffer_event` 负责：格式转换 → seq 生成 → 存储 → Pub/Sub
- 支持断线重连和事件补偿（基于 seq）

**事件格式：**

| 格式 | 用途 | 说明 |
|------|------|------|
| **Zenflux** | 内部处理 | 原始格式，包含完整上下文 |
| **ZenO** | 前端展示 | 简化格式，符合 ZenO SSE 规范 |

**组件职责：**

| 组件 | 职责 |
|------|------|
| `EventBroadcaster` | Agent 事件发送入口，内容累积，持久化 |
| `RedisSessionManager.buffer_event` | 格式转换、seq 生成、存储、Pub/Sub |
| `InMemoryEventStorage` | 开发环境的内存实现 |
| `EventDispatcher` | 外部 Webhook 发送（可选） |
| `ZenOAdapter` | Zenflux → ZenO 格式转换 |

### 6.6 实例化配置

每个 Agent 实例独立配置：
- `config.yaml`: 模型、工具、API 等配置
- `prompt.md`: 系统提示词
- `.cache/`: Schema 和提示词缓存

支持热更新：修改配置后调用 reload 接口即可生效。

## 七、错误处理策略

### 7.1 资源释放保证

无论执行成功或失败，都确保资源释放：

```python
try:
    # 执行 Agent
    await agent.chat(...)
finally:
    # 确保释放资源
    await agent_pool.release(agent_id)
    await session_pool.on_session_end(...)
```

### 7.2 错误分类和用户提示

| 错误类型 | 错误码 | 用户提示 |
|---------|-------|---------|
| PermissionDeniedError | permission_denied | API 权限错误，请检查 API Key 配置 |
| RateLimitError | rate_limit | 请求频率过高，请稍后重试 |
| AuthenticationError | authentication_error | API 认证失败，请检查 API Key |
| TimeoutError | timeout | 请求超时，请稍后重试 |
| ConnectionError | connection_error | 网络连接失败，请检查网络 |
| 其他 | unknown_error | 执行失败，请稍后重试 |

### 7.3 工具执行失败

工具执行失败时：
1. 生成 `is_error: true` 的 `tool_result`
2. 记录错误到 `context_engineering`（错误保留）
3. 让 Agent 在下轮决定如何处理

## 八、V7 新增功能

### 8.1 路由层 (core/routing/)

| 组件 | 职责 |
|------|------|
| `AgentRouter` | 路由决策器，决定使用单智能体还是多智能体 |
| `IntentAnalyzer` | 意图分析器，从 SimpleAgent 剥离成为共享模块 |
| `ComplexityScorer` | 复杂度评分器，评估任务难度 |

### 8.2 多智能体系统 (core/agent/multi/)

| 组件 | 职责 |
|------|------|
| `MultiAgentOrchestrator` | 多智能体编排器，协调多个智能体协作 |
| `LeadAgent` | 主控智能体（Opus），负责任务分解和结果综合 |
| `Critic` | 评审智能体，负责质量评估和计划调整 |
| `CheckpointManager` | 检查点管理，支持长时间任务的断点续传 |

### 8.3 监控与计费

| 组件 | 职责 |
|------|------|
| `TokenAuditor` | Token 审计，记录每次请求的 Token 消耗 |
| `UsageTracker` | 用量追踪，累积多次 LLM 调用的统计 |
| `UsageResponse` | 计费响应模型，标准化的 API 响应格式 |
| `TokenBudget` | Token 预算管理 |

### 8.4 数据流变化

**V6 流程:**
```
用户消息 → ChatService → SimpleAgent → LLM → 响应
                            ↓
                      (内部意图分析)
```

**V7 流程:**
```
用户消息 → ChatService → AgentRouter → 路由决策
                              ↓
              ┌───────────────┴───────────────┐
              ↓                               ↓
        SimpleAgent                   MultiAgentOrchestrator
        (简单任务)                     (复杂任务)
              ↓                               ↓
            LLM                    Lead → Workers → Critic
              ↓                               ↓
        ┌─────┴─────────────────────────────┘
        ↓
    TokenAuditor (审计记录)
        ↓
    UsageResponse (计费信息)
        ↓
    SSE: usage 事件 → 前端
```

## 九、后续优化方向

### 已完成
1. ✅ **资源池架构** - UserPool、AgentPool、SessionPool、MCPPool 已实现
2. ✅ **可靠计数** - 使用 Set 存储 + 校准机制
3. ✅ **依赖注入** - 支持测试时注入 mock
4. ✅ **Multi-Agent 支持** - V7 多智能体编排系统
5. ✅ **路由层** - V7 单智能体/多智能体路由决策
6. ✅ **Token 审计** - V7 TokenAuditor + UsageResponse
7. ✅ **计费系统** - V7 多模型定价和成本计算
8. ✅ **MCP 客户端池化** - MCPPool 连接复用 + 健康检查 + 自动重连
9. ✅ **事件系统重构** - V7.1 统一 seq 生成、单一入口、格式转换前置

### 待优化
1. **LLM Service 池化** - 复用 HTTP 客户端
2. **上下文压缩优化** - 更智能的历史裁剪策略
3. **UserPool 限流** - 基于 Redis 的滑动窗口限流
4. **评估框架完善** - 自动化测试套件
