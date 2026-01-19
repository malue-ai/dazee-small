# ZenFlux Agent 分层架构原则

**版本**: V1.0  
**日期**: 2024-01-14

---

## 一、分层概述

ZenFlux Agent 采用经典的分层架构，严格遵守职责分离原则：

```
┌─────────────────────────────────────┐
│         routers/                     │  HTTP/gRPC 接口层
│  (HTTP请求处理、参数验证、响应封装)    │
└─────────────────────────────────────┘
           ↓
┌─────────────────────────────────────┐
│         services/                    │  业务服务层
│  (业务逻辑、流程编排、服务协调)        │
└─────────────────────────────────────┘
           ↓
┌─────────────────────────────────────┐
│         core/                        │  领域核心层
│  (Agent逻辑、工具系统、记忆系统)       │
└─────────────────────────────────────┘
           ↓
┌─────────────────────────────────────┐
│         infra/                       │  基础设施层
│  (数据库、Redis、容错、存储)          │
└─────────────────────────────────────┘
```

---

## 二、各层职责

### 1. routers/ - 接口层

**职责**：
- HTTP/gRPC 请求处理
- 参数验证（Pydantic）
- 响应封装（JSON/SSE）
- 异常转换为 HTTP 状态码

**原则**：
- ✅ 薄接口层，只做协议转换
- ✅ 调用 service 层处理业务
- ❌ 不包含业务逻辑
- ❌ 不直接操作数据库

**示例**：
```python
# routers/chat.py
@router.post("/chat")
async def chat(request: ChatRequest):
    # ✅ 只做参数验证和服务调用
    chat_service = get_chat_service()
    result = await chat_service.chat(
        message=request.message,
        user_id=request.user_id
    )
    return result
```

---

### 2. services/ - 业务服务层

**职责**：
- 业务逻辑实现
- 多个 core 组件的编排
- 事务管理
- 错误处理和降级

**原则**：
- ✅ 协调多个 core 模块
- ✅ 处理业务异常
- ✅ 可以使用 infra 层的容错机制
- ❌ 不包含 Agent 核心算法
- ❌ 不直接实现工具逻辑

**示例**：
```python
# services/chat_service.py
class ChatService:
    def __init__(self):
        self.session_service = get_session_service()
        self.agent_breaker = get_circuit_breaker("agent")  # ✅ 使用 infra
    
    async def chat(self, message, user_id):
        # ✅ 编排多个组件
        session = await self.session_service.create_session(user_id)
        agent = create_simple_agent()
        
        # ✅ 使用容错机制
        async with self.agent_breaker:
            result = await agent.chat(message, session_id=session.id)
        
        return result
```

---

### 3. core/ - 领域核心层

**职责**：
- Agent 核心算法（RVR 循环）
- 工具系统（选择、执行）
- 记忆系统（Memory Manager）
- 事件系统（EventBroadcaster）
- 领域对象（Context、Schema）

**原则**：
- ✅ 专注于业务领域逻辑
- ✅ 高内聚、低耦合
- ✅ 可测试性强（纯业务逻辑）
- ❌ 不依赖外部服务（数据库、Redis）
- ❌ 不包含基础设施代码

**目录结构**：
```
core/
├── agent/              # Agent 核心
│   ├── simple_agent.py
│   ├── intent_analyzer.py
│   └── factory.py
├── tool/               # 工具系统
│   ├── selector.py
│   ├── executor.py
│   └── loader.py
├── memory/             # 记忆系统
│   ├── working_memory.py
│   ├── episodic_memory.py
│   └── mem0/
├── events/             # 事件系统
│   ├── broadcaster.py
│   └── emitters/
├── context/            # 上下文管理
├── prompt/             # 提示词管理
└── schemas/            # 领域对象
```

**示例**：
```python
# core/agent/simple/simple_agent.py
class SimpleAgent:
    """Agent 核心逻辑，不依赖外部基础设施"""
    
    def __init__(self, schema, llm, memory, tool_executor):
        self.schema = schema
        self.llm = llm
        self.memory = memory  # ✅ 注入依赖，不直接创建
        self.tool_executor = tool_executor
    
    async def chat(self, messages, session_id):
        # ✅ 纯业务逻辑：RVR 循环
        intent = await self.intent_analyzer.analyze(messages)
        tools = await self.tool_selector.select(intent)
        result = await self.tool_executor.execute(tools)
        return result
```

---

### 4. infra/ - 基础设施层

**职责**：
- 数据库访问（Database）
- 缓存服务（Redis）
- 容错机制（Resilience）
- 存储抽象（Storage）
- 外部 API 封装

**原则**：
- ✅ 封装外部依赖
- ✅ 提供统一接口
- ✅ 可被各层使用（横切关注点）
- ❌ 不包含业务逻辑
- ❌ 不调用上层（service、core）

**目录结构**：
```
infra/
├── resilience/         # 容错机制 ✅
│   ├── timeout.py
│   ├── retry.py
│   ├── circuit_breaker.py
│   └── fallback.py
├── storage/            # 存储抽象 ✅
│   ├── async_writer.py
│   ├── batch_writer.py
│   └── storage_manager.py
├── database/           # 数据库
│   ├── session.py
│   └── crud.py
├── redis/              # Redis
│   └── client.py
└── llm/                # LLM API 封装
    ├── anthropic.py
    └── openai.py
```

**示例**：
```python
# infra/resilience/circuit_breaker.py
class CircuitBreaker:
    """熔断器 - 基础设施，各层可用"""
    
    async def call(self, func, *args):
        if self.is_open:
            raise CircuitBreakerOpenError()
        
        try:
            return await func(*args)
        except Exception:
            self._record_failure()
            raise
```

---

## 三、依赖关系

### 允许的依赖方向（✅）

```
routers → services → core → infra
   ↓         ↓         ↓
   └─────────┴─────────┴────→ infra
```

- routers 可以调用 services 和 infra
- services 可以调用 core 和 infra
- core 可以调用 infra（但应该通过依赖注入）
- infra 不依赖任何上层

### 禁止的依赖方向（❌）

```
❌ infra → core
❌ infra → services
❌ core → services
❌ core → routers
```

---

## 四、关键设计决策

### 决策 1: 容错机制放在 infra/

**背景**: 容错（超时、重试、熔断）应该放在哪一层？

**选项**:
- A. `core/resilience/` - Agent 核心能力
- B. `services/resilience/` - 服务层专用
- C. `infra/resilience/` - 基础设施

**决策**: ✅ 选择 C（`infra/resilience/`）

**理由**:
1. 容错是**横切关注点**（cross-cutting concern）
2. 不仅 service 需要，tool executor、llm caller 也需要
3. 属于基础设施范畴，类似数据库连接池、Redis 客户端
4. 可以被各层使用，不绑定业务逻辑

**示例**:
```python
# service 层使用
from infra.resilience import get_circuit_breaker
breaker = get_circuit_breaker("llm_service")

# tool executor 使用
from infra.resilience import with_timeout
@with_timeout(timeout_type="tool")
async def execute_tool():
    ...
```

---

### 决策 2: 存储抽象放在 infra/

**背景**: AsyncWriter、BatchWriter 应该放在哪一层？

**选项**:
- A. `core/storage/` - Agent 核心能力
- B. `services/storage/` - 服务层专用
- C. `infra/storage/` - 基础设施

**决策**: ✅ 选择 C（`infra/storage/`）

**理由**:
1. 存储优化是**基础设施能力**，不是业务逻辑
2. 类似数据库连接池、Redis 客户端
3. 可以被各层使用（service、core 都可能写数据）
4. 封装了底层的队列、批量写入等技术细节

---

### 决策 3: Memory 系统放在 core/

**背景**: Memory Manager 应该放在哪一层？

**选项**:
- A. `core/memory/` - Agent 核心能力
- B. `infra/memory/` - 基础设施

**决策**: ✅ 选择 A（`core/memory/`）

**理由**:
1. Memory 是 **Agent 的核心能力**，不是通用基础设施
2. 包含业务逻辑（记忆检索策略、上下文构建）
3. 与 Agent 的 RVR 循环紧密耦合
4. 虽然底层用了 Mem0、Ragie，但这些是通过适配器模式封装的

**目录结构**:
```
core/memory/
├── working_memory.py   # 业务逻辑
├── episodic_memory.py  # 业务逻辑
└── mem0/               # 适配器（封装 infra）
    └── adapter.py
```

---

## 五、实践指南

### 1. 新增功能时如何选择层级？

**判断标准**:

| 如果是... | 应该放在... | 示例 |
|----------|-----------|------|
| HTTP 接口 | `routers/` | 新增 API 端点 |
| 业务流程编排 | `services/` | 订单创建流程 |
| Agent 核心算法 | `core/agent/` | 新的推理策略 |
| 工具实现 | `core/tool/` | 新的工具定义 |
| 外部服务封装 | `infra/` | 新的 LLM Provider |
| 通用基础设施 | `infra/` | 日志、监控、容错 |

### 2. 依赖注入 vs 直接创建

**✅ 推荐（依赖注入）**:
```python
class SimpleAgent:
    def __init__(self, memory: MemoryManager):
        self.memory = memory  # 外部注入，便于测试

# 使用
memory = MemoryManager()
agent = SimpleAgent(memory=memory)
```

**❌ 不推荐（直接创建）**:
```python
class SimpleAgent:
    def __init__(self):
        self.memory = MemoryManager()  # 硬编码依赖，难以测试
```

### 3. 跨层调用原则

**✅ 允许**:
```python
# services/chat_service.py
from core.agent import SimpleAgent
from infra.resilience import get_circuit_breaker

class ChatService:
    def __init__(self):
        self.agent = SimpleAgent()
        self.breaker = get_circuit_breaker("agent")
```

**❌ 禁止**:
```python
# infra/database/crud.py
from services.chat_service import ChatService  # ❌ infra 不能调用 service

# core/agent/simple/simple_agent.py
from services.session_service import SessionService  # ❌ core 不能调用 service
```

---

## 六、重构检查清单

在移动代码时，请检查：

- [ ] 模块职责是否清晰？
- [ ] 是否有跨层的反向依赖？
- [ ] 是否可以被多层复用？
- [ ] 是否包含业务逻辑？
- [ ] 测试是否仍然通过？
- [ ] 文档是否已更新？

---

## 七、常见问题

### Q1: infra 层可以使用 core 层的对象吗？

**A**: 不可以直接依赖，但可以通过接口（抽象类）。

```python
# ✅ 正确：infra 定义接口
# infra/storage/interface.py
class Storable(Protocol):
    def to_dict(self) -> dict:
        ...

# core 实现接口
# core/schemas/message.py
class Message:
    def to_dict(self) -> dict:
        return {"content": self.content}

# infra 使用接口
# infra/storage/writer.py
async def save(obj: Storable):
    await db.insert(obj.to_dict())
```

### Q2: service 层可以直接调用数据库吗？

**A**: 可以，但建议通过 infra 层封装。

```python
# ✅ 推荐：通过 infra 封装
# services/conversation_service.py
from infra.database import crud

async def get_conversation(conversation_id):
    return await crud.get_conversation(conversation_id)

# ⚠️ 不推荐但允许：直接使用 SQLAlchemy
from infra.database import AsyncSessionLocal

async with AsyncSessionLocal() as session:
    result = await session.execute(query)
```

### Q3: core 层需要数据库怎么办？

**A**: 通过依赖注入，由上层传入。

```python
# core/agent/simple/simple_agent.py
class SimpleAgent:
    def __init__(self, memory_repository):
        self.memory_repo = memory_repository  # 抽象依赖
    
    async def load_memory(self, user_id):
        return await self.memory_repo.get(user_id)

# services/chat_service.py
from infra.database import MemoryRepository

agent = SimpleAgent(
    memory_repository=MemoryRepository()  # service 层注入具体实现
)
```

---

## 八、总结

**核心原则**:
1. **单一职责**: 每层只做自己的事
2. **依赖倒置**: 依赖抽象，不依赖具体
3. **开闭原则**: 对扩展开放，对修改关闭
4. **横切分离**: 基础设施独立，可被各层复用

**记住**:
- 🏗️ `infra/` = 基础设施，横切关注点
- 🧠 `core/` = 业务核心，领域逻辑
- 🔧 `services/` = 流程编排，业务服务
- 🌐 `routers/` = 接口暴露，协议转换

---

**文档版本**: 1.0  
**最后更新**: 2024-01-14  
**维护者**: ZenFlux Agent Team
