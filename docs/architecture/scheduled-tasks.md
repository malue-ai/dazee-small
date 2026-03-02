# 定时任务系统架构文档

## 目录

1. [系统概览](#1-系统概览)
2. [双调度器架构](#2-双调度器架构)
3. [系统级调度器 (TaskScheduler)](#3-系统级调度器-taskscheduler)
4. [用户级调度器 (UserTaskScheduler)](#4-用户级调度器-usertaskscheduler)
5. [后台任务框架](#5-后台任务框架)
6. [数据模型](#6-数据模型)
7. [API 层](#7-api-层)
8. [AI 工具层](#8-ai-工具层)
9. [前端交互](#9-前端交互)
10. [生命周期管理](#10-生命周期管理)
11. [关键设计决策](#11-关键设计决策)
12. [文件索引](#12-文件索引)

---

## 1. 系统概览

定时任务系统负责两类需求：

| 类别 | 说明 | 示例 |
|------|------|------|
| **系统级任务** | 后台运维任务，配置驱动 | Mem0 记忆批量更新（每天凌晨 2 点） |
| **用户级任务** | 用户通过 AI 对话创建的任务 | "每天早上 9 点提醒我开会"、"明天下午 3 点帮我查天气" |

技术栈：

- **APScheduler** (AsyncIOScheduler)：核心调度引擎
- **croniter**：Cron 表达式解析
- **SQLite** (via SQLAlchemy async)：用户任务持久化
- **YAML**：系统任务配置
- **WebSocket**：任务执行通知推送

---

## 2. 双调度器架构

系统采用 **双调度器** 设计，各司其职：

```
┌──────────────────────────────────────────────────────────────┐
│                     FastAPI Lifespan                         │
│                                                              │
│  启动阶段:                                                   │
│    1. _start_scheduler()       → TaskScheduler (系统级)       │
│    2. _start_user_task_scheduler() → UserTaskScheduler (用户级)│
│                                                              │
│  关闭阶段:                                                   │
│    1. _stop_user_task_scheduler()                            │
│    2. _stop_scheduler()                                      │
└──────────────────────────────────────────────────────────────┘
```

### 两个调度器的区别

| 维度 | TaskScheduler | UserTaskScheduler |
|------|---------------|-------------------|
| 定位 | 系统后台运维 | 用户自定义提醒/任务 |
| 配置来源 | `config/scheduled_tasks.yaml` | SQLite `scheduled_tasks` 表 |
| 触发器 | CronTrigger / IntervalTrigger | DateTrigger (统一用 next_run_at) |
| 任务注册 | `@background_task` 装饰器 | 数据库 CRUD + 动态注册 |
| 创建方式 | 配置文件 | AI 对话 / REST API |
| 环境变量 | `ENABLE_SCHEDULER` | `ENABLE_USER_TASK_SCHEDULER` |

---

## 3. 系统级调度器 (TaskScheduler)

### 3.1 核心类

**文件**: `utils/background_tasks/scheduler.py`

```python
@dataclass
class ScheduledTaskConfig:
    task_name: str            # 任务名（对应 registry 中的注册名）
    enabled: bool = True
    trigger_type: str = "cron"  # cron / interval
    cron: Optional[str] = None
    interval_seconds: Optional[int] = None
    params: Dict[str, Any] = field(default_factory=dict)
    description: str = ""

class TaskScheduler:
    def __init__(self, config_path=None)  # 默认 config/scheduled_tasks.yaml
    async def start()                     # 加载配置 → 创建 APScheduler → 注册 Jobs
    async def shutdown(wait=True)         # 关闭调度器
    async def _run_scheduled_task(config) # 执行单个定时任务
    def get_jobs() -> List[Dict]          # 获取当前所有 Jobs 信息
    def is_running() -> bool
```

### 3.2 启动流程

```
TaskScheduler.start()
  │
  ├── 1. 异步加载 YAML 配置 (_load_config_async)
  │     └── 解析 scheduled_tasks 列表 → List[ScheduledTaskConfig]
  │
  ├── 2. 过滤 enabled=true 的配置
  │
  ├── 3. 校验任务是否在 registry 中已注册
  │
  ├── 4. 根据 trigger_type 创建触发器
  │     ├── cron → CronTrigger.from_crontab(cron_expr)
  │     └── interval → IntervalTrigger(seconds=N)
  │
  ├── 5. 注册到 AsyncIOScheduler
  │     └── add_job(_run_scheduled_task, trigger, args=[config])
  │
  └── 6. scheduler.start()
```

### 3.3 任务执行逻辑

`_run_scheduled_task` 区分两种模式：

- **批量模式** (`params.batch=true`)：调用 `batch_update_all_memories()`，处理所有用户的记忆更新
- **单次模式**：构造 `TaskContext`，从 registry 获取任务函数并执行

### 3.4 配置文件格式

**文件**: `config/scheduled_tasks.yaml`

```yaml
scheduled_tasks:
  - task_name: mem0_update          # 必须是已注册的任务名
    enabled: false                   # 是否启用
    trigger_type: cron               # cron / interval
    cron: "0 2 * * *"               # Cron 表达式（分 时 日 月 周）
    description: "每日凌晨批量更新用户记忆"
    params:
      batch: true                    # 批量模式
      since_hours: 24                # 处理过去 24 小时
      max_concurrent: 5              # 最大并发数
```

### 3.5 单例获取

```python
from utils.background_tasks.scheduler import get_scheduler

scheduler = get_scheduler()  # 全局唯一实例
```

---

## 4. 用户级调度器 (UserTaskScheduler)

### 4.1 核心类

**文件**: `services/user_task_scheduler.py`

```python
class UserTaskScheduler:
    AGENT_TASK_TIMEOUT = 300  # Agent 任务最大执行时间 5 分钟

    async def start()                              # 启动 + 加载活跃任务
    async def shutdown()                           # 关闭 + 取消运行中任务
    async def register_task(task)                  # 动态注册（传入 ORM 对象）
    async def register_task_by_id(task_id)         # 通过 ID 从 DB 读取并注册
    async def unregister_task(task_id)             # 移除任务
    async def _execute_and_reschedule(task_id)     # 三阶段执行核心
    async def _execute_task(task_data)             # 执行具体动作
    async def _broadcast_task_notification(...)    # WebSocket 通知前端
```

### 4.2 启动流程

```
UserTaskScheduler.start()
  │
  ├── 1. 获取 Workspace (从 AGENT_INSTANCE 环境变量)
  │
  ├── 2. 创建 AsyncIOScheduler + 事件监听器
  │     └── 监听: JOB_EXECUTED / JOB_ERROR / JOB_MISSED
  │
  ├── 3. scheduler.start()
  │
  └── 4. _load_active_tasks()
        ├── 查询 DB: status=active & next_run_at IS NOT NULL
        ├── 去重: (title, trigger_type, next_run_at)
        └── 逐个调用 _register_job()
```

### 4.3 Job 注册策略

所有任务统一使用 **DateTrigger(next_run_at)**，而不是直接使用 CronTrigger/IntervalTrigger。这是一个关键设计：

```
_register_job(task)
  │
  ├── 1. 移除同 ID 的旧 Job（避免重复）
  │
  ├── 2. 处理时区：timezone-aware → naive 本地时间
  │
  ├── 3. 过期检测：next_run_at <= now → 延迟 2 秒立即触发
  │
  ├── 4. add_job(
  │       func = _execute_and_reschedule,
  │       trigger = DateTrigger(run_date=next_run_at),
  │       id = "user_task_{task_id}"
  │     )
  │
  └── 5. 验证注册：get_job(job_id) 确认存在
```

执行完成后，由 `_execute_and_reschedule` 根据 trigger_type 重新调度下次执行。

### 4.4 三阶段执行核心

`_execute_and_reschedule` 采用分段式 Session 管理，避免 SQLite pool_size=1 的连接竞争：

```
Phase 1: Session A → 加载任务数据 → 关闭 Session
  ├── 带重试（3 次，指数退避）
  ├── 提取 task_snapshot（id, title, trigger_type, user_id, action）
  └── 状态校验：非 active 则跳过

Phase 2: 执行任务（无 Session 持有）
  ├── asyncio.create_task() + wait_for(timeout=300s)
  ├── send_message → 仅通知，不写会话
  └── agent_task → 创建隔离会话 → 调用 chat_service.process_scheduled_task()

Phase 2.5: WebSocket 广播通知
  └── broadcast_notification("notification", payload)

Phase 3: Session B → 标记执行完成 → 关闭 Session
  ├── mark_task_executed() → 更新 run_count / last_run_at / status
  ├── once → status = completed, next_run_at = None
  ├── cron → croniter 计算下一次时间
  ├── interval → now + interval_seconds
  └── 如果仍 active 且有 next_run_at → 重新 _register_job()
```

### 4.5 动作类型

| 动作 | 说明 | 实现 |
|------|------|------|
| `send_message` | 发送提醒消息 | 仅通过 WebSocket 通知卡片展示，不污染会话记录 |
| `agent_task` | AI 执行任务 | 创建隐藏会话 → 调用 Agent 完整流程 → 返回结果 |

Agent 任务通过 `asyncio.create_task` + `wait_for` 隔离执行，确保不阻塞 Telegram 长轮询和飞书 WebSocket 心跳。

### 4.6 WAL 可见性处理

SQLite WAL 模式下，刚提交的数据可能对新 Session 短暂不可见（pool_size=1 + aiosqlite 线程层）。系统通过以下机制应对：

1. **创建后 WAL Checkpoint**: `PRAGMA wal_checkpoint(PASSIVE)`
2. **注册重试**: 最多 3 次，指数退避 (0.5s → 1s → 2s)
3. **执行前重试**: 最多 3 次，指数退避 (1s → 2s → 4s)
4. **优先传递 ORM 对象**: 避免重新查询

---

## 5. 后台任务框架

### 5.1 整体结构

```
utils/background_tasks/
├── __init__.py              # 包导出 + 触发 tasks 自动导入
├── registry.py              # @background_task 装饰器 + 全局注册表
├── context.py               # TaskContext / Mem0UpdateResult 数据类
├── service.py               # BackgroundTaskService (调度 + 资源管理)
├── scheduler.py             # TaskScheduler (系统级定时调度)
└── tasks/
    ├── __init__.py           # 自动导入所有任务模块
    ├── title_generation.py   # 对话标题生成
    ├── recommended_questions.py  # 推荐问题生成
    ├── memory_flush.py       # 记忆落盘
    ├── mem0_update.py        # Mem0 记忆更新
    ├── persona_build.py      # 用户画像构建
    └── playbook_extraction.py # Playbook 提取
```

### 5.2 任务注册机制

**装饰器**: `@background_task("task_name")`

```python
# registry.py
_TASK_REGISTRY: Dict[str, Callable] = {}

def background_task(name: str):
    def decorator(func):
        _TASK_REGISTRY[name] = func
        return func
    return decorator
```

**任务函数签名统一为**:

```python
async def task_func(ctx: TaskContext, service: BackgroundTaskService) -> None
```

**自动导入**: `tasks/__init__.py` 在模块加载时自动扫描 tasks/ 目录下的所有 .py 文件并导入，触发装饰器注册。PyInstaller 打包环境下使用显式列表 `_KNOWN_TASK_MODULES` 作为 fallback。

### 5.3 TaskContext 上下文

```python
@dataclass
class TaskContext:
    session_id: str
    conversation_id: str
    user_id: str
    message_id: str
    user_message: str
    assistant_response: str = ""
    is_new_conversation: bool = False
    event_manager: Optional[Any] = None
    conversation_service: Optional[Any] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
```

### 5.4 BackgroundTaskService

**文件**: `utils/background_tasks/service.py`

核心职责：
1. **统一调度** (`dispatch_tasks`): 接收任务列表，分为两层策略
2. **资源管理**: 懒加载 LLM 和 Mem0 Pool 实例

#### 两层调度策略

```
dispatch_tasks(task_names, context, wait)
  │
  ├── SSE 依赖任务 (如 title_generation)
  │   └── asyncio.wait() 等待完成后再关闭 SSE 流
  │
  └── 学习任务 (如 memory_flush, playbook_extraction)
      └── fire-and-forget，通过 done_callback 记录日志
```

`_SSE_DEPENDENT_TASKS = {"title_generation"}` 定义了哪些任务必须在 SSE 流关闭前完成。

### 5.5 已注册的后台任务

| 任务名 | 文件 | 触发场景 | 说明 |
|--------|------|----------|------|
| `title_generation` | `tasks/title_generation.py` | 每次对话 | 为新对话生成标题 (SSE 依赖) |
| `recommended_questions` | `tasks/recommended_questions.py` | 每次对话 | 生成推荐后续问题 |
| `memory_flush` | `tasks/memory_flush.py` | 每次对话 | 会话记忆落盘 |
| `mem0_update` | `tasks/mem0_update.py` | 每次对话 / 定时 | 用户长期记忆更新 |
| `persona_build` | `tasks/persona_build.py` | 对话后 | 用户画像构建 |
| `playbook_extraction` | `tasks/playbook_extraction.py` | 对话后 | 对话模式提取 |

---

## 6. 数据模型

### 6.1 ORM 模型 (SQLite)

**文件**: `infra/local_store/models.py`

```
表名: scheduled_tasks

字段:
  id              String(64)    PK       任务 ID（task_{uuid[:12]}）
  user_id         String(64)    INDEX    用户 ID
  title           String(255)            任务标题
  description     Text                   任务描述
  trigger_type    String(20)             once / cron / interval
  run_at          DateTime               单次执行时间
  cron_expr       String(100)            Cron 表达式
  interval_seconds Integer               间隔秒数
  action_json     Text          列名=action  动作 JSON
  status          String(20)    INDEX    active / paused / completed / cancelled
  last_run_at     DateTime               上次执行时间
  next_run_at     DateTime      INDEX    下次执行时间
  run_count       Integer                已执行次数
  created_at      DateTime               创建时间
  updated_at      DateTime               更新时间
  conversation_id String(64)             关联会话 ID
```

`action_json` 通过 `@property` 提供 JSON 序列化/反序列化：

```python
@property
def action(self) -> Dict:
    return json.loads(self.action_json) if self.action_json else {}

@action.setter
def action(self, value: Dict):
    self.action_json = json.dumps(value, ensure_ascii=False)
```

### 6.2 API 模型 (Pydantic)

**文件**: `models/scheduled_task.py`

```python
class TaskTriggerType(str, Enum):     # once / cron / interval
class TaskActionType(str, Enum):      # send_message / agent_task
class TaskStatus(str, Enum):          # active / paused / completed / cancelled

class ScheduledTaskResponse(BaseModel):
    # 完整的任务详情响应模型
    id, user_id, title, description,
    trigger_type, run_at, cron_expr, interval_seconds,
    action, status, next_run_at, last_run_at, run_count,
    created_at, updated_at, conversation_id

class ScheduledTaskListResponse(BaseModel):
    tasks: List[ScheduledTaskResponse]
    total: int
    page: int = 1
    page_size: int = 50
```

### 6.3 任务状态机

```
         create
           │
           ▼
       ┌─────────┐
       │  active  │ ◄──── resume
       └────┬─────┘
            │
     ┌──────┼──────┐
     │      │      │
     ▼      ▼      ▼
  paused  completed cancelled
     │     (once 执行后)  (用户取消)
     │
     └──► active (resume)
```

---

## 7. API 层

### 7.1 REST API 端点

**文件**: `routers/scheduled_tasks.py`

前缀: `/api/v1/scheduled-tasks`

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/` | 任务列表（支持 status 过滤、分页） |
| `GET` | `/{task_id}` | 任务详情 |
| `POST` | `/{task_id}/pause` | 暂停任务（从调度器移除） |
| `POST` | `/{task_id}/resume` | 恢复任务（重新注册调度器，重算 next_run_at） |
| `POST` | `/{task_id}/cancel` | 取消任务（软删除，status=cancelled） |
| `DELETE` | `/{task_id}` | 删除任务（硬删除，从 DB 和调度器同时移除） |

### 7.2 Service 层

**文件**: `services/scheduled_task_service.py`

REST API 的业务逻辑层，职责：
- 封装 CRUD 操作
- 同步 APScheduler 状态（pause → 移除 Job，resume → 重新注册）
- ORM 对象到 Dict 的安全转换（在 Session 内完成）

---

## 8. AI 工具层

### 8.1 ScheduledTaskTool

**文件**: `tools/scheduled_task_tool.py`

AI Agent 通过此工具管理用户定时任务，支持 4 种操作：

| 操作 | 说明 | 关键参数 |
|------|------|----------|
| `create` | 创建任务 | title, trigger_type, trigger_config, action |
| `list` | 查看活跃任务 | - |
| `cancel` | 取消任务 | task_id（缺失时自动列出任务列表） |
| `update` | 更新任务 | task_id, 可更新的字段 |

### 8.2 触发配置示例

```json
// 单次: "明天下午 3 点提醒我打电话"
{
  "trigger_type": "once",
  "trigger_config": { "run_at": "2026-03-02T15:00:00" },
  "action": { "type": "send_message", "content": "记得打电话！" }
}

// Cron: "每天早上 9 点提醒我开会"
{
  "trigger_type": "cron",
  "trigger_config": { "cron": "0 9 * * *" },
  "action": { "type": "send_message", "content": "该开会了！" }
}

// 间隔: "每隔 2 小时提醒我喝水"
{
  "trigger_type": "interval",
  "trigger_config": { "interval_seconds": 7200 },
  "action": { "type": "send_message", "content": "记得喝水！" }
}

// Agent 任务: "每天早上 8 点帮我查天气"
{
  "trigger_type": "cron",
  "trigger_config": { "cron": "0 8 * * *" },
  "action": { "type": "agent_task", "prompt": "查一下今天北京的天气" }
}
```

### 8.3 创建流程

```
ScheduledTaskTool._create_task()
  │
  ├── 1. 去重检查: 同用户、同标题、同触发类型的活跃任务 → 跳过
  │
  ├── 2. 解析触发配置 + 校验
  │     ├── once → 解析 run_at (ISO 8601)
  │     ├── cron → croniter 校验
  │     └── interval → 正整数校验
  │
  ├── 3. Phase 1: 创建任务 (CRUD)
  │     └── create_scheduled_task() → commit → WAL checkpoint
  │
  ├── 4. Phase 2: 验证任务 (新 Session 重新读取)
  │     └── get_scheduled_task() 确认写入成功
  │
  └── 5. Phase 3: 注册到调度器
        └── scheduler.register_task(orm_obj) → _register_job()
```

---

## 9. 前端交互

### 9.1 相关文件

| 文件 | 用途 |
|------|------|
| `frontend/src/views/tasks/ScheduledTasksView.vue` | 定时任务管理页面 |
| `frontend/src/api/scheduledTasks.ts` | API 客户端 |
| `frontend/src/stores/scheduledTask.ts` | Pinia 状态管理 |
| `frontend/src/components/chat/ConversationSidebar.vue` | 侧边栏入口 |

### 9.2 WebSocket 通知

任务执行完成后，通过 WebSocket 广播通知到前端：

```json
{
  "type": "notification",
  "data": {
    "notification_type": "success | message | error",
    "title": "定时任务完成: 查天气",
    "message": "Agent 已执行: 查一下今天北京的天气",
    "task_id": "task_abc123",
    "triggered_at": "08:00",
    "full_content": "今天北京天气晴朗，最高温度 25°C..."
  }
}
```

---

## 10. 生命周期管理

### 10.1 启动顺序 (main.py lifespan)

```python
async def lifespan(app: FastAPI):
    # 启动阶段
    await _init_local_store()              # 数据库初始化
    await _preload_capability_registry()    # 工具注册表（含 scheduled_task tool）
    scheduler = await _start_scheduler()    # 系统级调度器
    user_task_scheduler = await _start_user_task_scheduler()  # 用户级调度器

    yield

    # 关闭阶段（逆序）
    await _stop_user_task_scheduler(user_task_scheduler)
    await _stop_scheduler(scheduler)
    await close_all_workspaces()
```

### 10.2 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `ENABLE_SCHEDULER` | `true` | 启用系统级定时调度器 |
| `ENABLE_USER_TASK_SCHEDULER` | `true` | 启用用户级任务调度器 |
| `AGENT_INSTANCE` | `default` | 当前实例名（用于 Workspace 获取） |

---

## 11. 关键设计决策

### 11.1 统一 DateTrigger 策略

UserTaskScheduler 对所有任务类型（once/cron/interval）都使用 `DateTrigger(next_run_at)`，而非直接使用 CronTrigger/IntervalTrigger。

**原因**: 任务执行后需要更新数据库状态（run_count, last_run_at），然后根据 trigger_type 重新计算 next_run_at 并重新注册。这种方式保证数据库和调度器始终同步。

### 11.2 分段 Session 管理

执行任务时避免长时间持有 SQLite Session：

- Phase 1: 短暂 Session 读取数据
- Phase 2: 释放 Session 执行业务逻辑
- Phase 3: 短暂 Session 更新状态

防止 SQLite pool_size=1 场景下的连接竞争。

### 11.3 Agent 任务隔离

Agent 任务通过 `asyncio.create_task` + `asyncio.wait_for(timeout=300s)` 隔离执行：

- 不阻塞主事件循环
- 不影响 Telegram 长轮询和飞书 WebSocket 心跳
- 超时自动取消
- 每次执行创建独立隐藏会话，不污染原始对话

### 11.4 WAL 可见性保障

SQLite WAL 模式的特殊处理：

- 创建后执行 `PRAGMA wal_checkpoint(PASSIVE)`
- 注册/执行前带重试的查询（指数退避）
- 优先传递 ORM 对象而非 task_id

### 11.5 去重机制

- **创建去重**: 同用户 + 同标题 + 同触发类型 → 视为重复，返回已有任务
- **加载去重**: (title, trigger_type, next_run_at) 组合去重，防止同一逻辑任务重复注册

### 11.6 两层调度策略

BackgroundTaskService 的 `dispatch_tasks` 将任务分为两层：

- **SSE 依赖**: 必须在流关闭前完成（如 title_generation 要通过 SSE 推送标题）
- **学习任务**: fire-and-forget，异步执行不阻塞用户

---

## 12. 文件索引

### 核心模块

| 文件 | 职责 |
|------|------|
| `utils/background_tasks/scheduler.py` | 系统级定时调度器 |
| `utils/background_tasks/service.py` | 后台任务统一调度服务 |
| `utils/background_tasks/registry.py` | 任务装饰器 + 全局注册表 |
| `utils/background_tasks/context.py` | TaskContext + 结果数据类 |
| `utils/background_tasks/tasks/` | 具体任务实现 |
| `services/user_task_scheduler.py` | 用户级定时调度器 |

### 持久化

| 文件 | 职责 |
|------|------|
| `infra/local_store/models.py` | `LocalScheduledTask` ORM 模型 |
| `infra/local_store/crud/scheduled_task.py` | 任务 CRUD 操作 |
| `config/scheduled_tasks.yaml` | 系统级定时任务配置 |

### API / 工具

| 文件 | 职责 |
|------|------|
| `routers/scheduled_tasks.py` | REST API 端点 |
| `services/scheduled_task_service.py` | REST API 业务逻辑 |
| `tools/scheduled_task_tool.py` | AI Tool (create/list/cancel/update) |
| `models/scheduled_task.py` | Pydantic API 模型 |

### 前端

| 文件 | 职责 |
|------|------|
| `frontend/src/views/tasks/ScheduledTasksView.vue` | 任务管理页面 |
| `frontend/src/api/scheduledTasks.ts` | API 客户端 |
| `frontend/src/stores/scheduledTask.ts` | Pinia Store |

### 入口

| 文件 | 职责 |
|------|------|
| `main.py` | lifespan 中启动/关闭两个调度器 |

### 依赖

| 包 | 版本要求 | 用途 |
|------|----------|------|
| `apscheduler` | >=3.10.0 | 核心调度引擎 |
| `croniter` | >=6.0.0 | Cron 表达式解析 |
