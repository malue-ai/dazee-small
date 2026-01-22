# 工具系统端到端审查报告

> 端到端验证工具发现-匹配-选择-调用流程，识别问题和优化空间

---

## 🚨 发现的问题和优化建议

### P0 严重问题

#### 1. Level 1 核心工具定义不一致

**问题**: 核心工具定义分散在三个地方，且列表不一致：

| 位置 | 定义 |
|------|------|
| `core/tool/selector.py` L79 | `["plan_todo", "bash", "request_human_confirmation"]` |
| `core/tool/loader.py` L58-68 | `["plan_todo", "api_calling", "request_human_confirmation", "file_read", "sandbox_write_file", "sandbox_run_command", "sandbox_create_project", "sandbox_run_project"]` |
| `capabilities.yaml` (level:1) | `plan_todo, api_calling, request_human_confirmation, sandbox_*` (7个) |

**影响**: 
- `bash` 在 selector 中是核心工具，但 capabilities.yaml 中没有定义为 level:1
- `file_read` 在 loader 中是核心工具，但 capabilities.yaml 和 selector 中都没有
- 导致不同路径加载的核心工具不一致

**建议**:
```python
# 统一定义，单一数据源
# 方案1: 完全从 capabilities.yaml 读取 (推荐)
# 方案2: 在一个地方定义常量，其他地方引用
```

#### 2. plan_todo_tool 内部调用 LLM 但缺乏错误边界

**问题**: `PlanTodoTool._create_plan_smart()` 内部调用 LLM，但:
- 没有超时控制
- LLM 失败降级到单步计划，信息丢失严重
- 没有对 `self._llm` 初始化失败的处理

```python
# tools/plan_todo_tool.py L874-923
response = await self._llm.create_message_async(
    messages=[Message(role="user", content=prompt)],
    system="..."
)
# 缺少: timeout, retry, fallback 策略
```

**建议**:
```python
async def _create_plan_smart(self, data: Dict) -> Dict:
    try:
        response = await asyncio.wait_for(
            self._llm.create_message_async(...),
            timeout=30.0  # 合理超时
        )
    except asyncio.TimeoutError:
        logger.warning("Plan LLM 超时，使用轻量级规划")
        return self._create_simple_plan(data)  # 不丢失信息的降级
```

#### 3. 工具选择三级优先级存在覆盖盲区

**问题**: `_select_tools()` 中的优先级逻辑:

```python
# L822-860
if self.schema.tools:  # Schema 优先
    required_capabilities = valid_tools
elif plan and plan.get('required_capabilities'):  # Plan 次之
    required_capabilities = plan['required_capabilities']
else:  # Intent 兜底
    required_capabilities = intent_capabilities
```

这是**互斥选择**，但如果:
- Schema 配置了 `["web_search"]`
- Plan 推荐了 `["e2b_sandbox"]` (代码执行需要)
- 实际任务需要两者

结果只会使用 Schema 的 `["web_search"]`，sandbox 工具不会被加载。

**建议**: 改为合并策略（Schema 覆盖 + Plan 补充）:
```python
required_capabilities = []
# 1. Schema 优先级最高，直接使用
if self.schema.tools:
    required_capabilities.extend(valid_tools)
    selection_source = "schema"
# 2. Plan 补充（非覆盖）
if plan and plan.get('required_capabilities'):
    for cap in plan['required_capabilities']:
        if cap not in required_capabilities:
            required_capabilities.append(cap)
# 3. Intent 兜底
if not required_capabilities:
    required_capabilities = intent_capabilities
```

---

### P1 重要问题

#### 4. ToolExecutor 工具加载时机问题

**问题**: `ToolExecutor.__init__()` 在构造时就加载所有工具:

```python
# core/tool/executor.py L93
def __init__(self, ...):
    ...
    self._load_tools()  # 同步加载所有工具
```

如果某个工具依赖外部服务（如 E2B API），初始化失败会导致整个 Agent 无法启动。

**建议**: 惰性加载 + 隔离失败:
```python
def _load_tools(self):
    for cap in tool_caps:
        try:
            self._load_custom_tool(cap)
        except Exception as e:
            logger.warning(f"⚠️ 工具 {cap.name} 加载失败，跳过: {e}")
            self._tool_instances[cap.name] = None  # 标记为不可用
```

#### 5. HITL 工具缺少前端断连处理

**问题**: `RequestHumanConfirmationTool.execute()` 等待用户响应:

```python
# L275
result = await manager.wait_for_response(request.request_id, timeout)
```

如果前端断连（用户关闭页面），Agent 会一直等到超时（60-120秒），浪费资源。

**建议**: 添加 session 存活检测:
```python
async def wait_for_response(self, request_id: str, timeout: int):
    while time.time() - start < timeout:
        if not self._is_session_alive(session_id):
            return {"timed_out": True, "reason": "session_disconnected"}
        # ...
```

#### 6. plan_todo_tool 的 Skill 发现与工具选择重复

**问题**: `PlanTodoTool._create_plan_smart()` 内部做了一次 Skill 发现和匹配:

```python
# L840-841
all_skills = discover_skills()
matched_skills = match_skills_for_query(user_query, all_skills)
```

而在 `SimpleAgent._select_tools()` 中又做了一次工具选择。两处逻辑重复且可能不一致。

**建议**: 
- Plan 阶段只做高层能力规划（capability 维度）
- 具体工具选择统一在 `ToolSelector` 完成
- 或者 Plan 返回的 `recommended_skill` 直接传递给 ToolSelector

---

### P2 改进建议

#### 7. 工具 Schema 验证时机过晚

**问题**: 工具 Schema 验证在 `_select_tools()` 运行时才做:

```python
# L825-836
for tool_name in self.schema.tools:
    if self.capability_registry.get(tool_name):
        valid_tools.append(tool_name)
    else:
        invalid_tools.append(tool_name)
```

无效配置只有在用户请求时才会发现。

**建议**: Agent 原型创建时就验证:
```python
# AgentFactory.create_prototype()
def _validate_schema_tools(self, schema, registry):
    for tool_name in schema.tools or []:
        if not registry.get(tool_name):
            raise ConfigError(f"Schema 配置了无效工具: {tool_name}")
```

#### 8. 缺少工具执行指标监控

**问题**: 工具执行没有统计指标:
- 各工具调用次数
- 各工具平均延迟
- 各工具失败率

**建议**: 添加指标收集:
```python
async def execute(self, tool_name: str, tool_input: Dict) -> Dict:
    start = time.time()
    try:
        result = await self._do_execute(tool_name, tool_input)
        self._metrics.record_success(tool_name, time.time() - start)
        return result
    except Exception as e:
        self._metrics.record_failure(tool_name, e)
        raise
```

#### 9. 核心工具没有健康检查

**问题**: Level 1 核心工具（如 sandbox）如果外部服务不可用，没有主动健康检查机制。

**建议**: 添加 healthcheck 接口:
```python
class PlanTodoTool:
    async def healthcheck(self) -> bool:
        try:
            # 验证 LLM 连接
            await self._llm.ping()
            return True
        except:
            return False
```

---

## 📋 端到端调用链路

```
用户 Query
    ↓
ChatService.chat()
    ↓
AgentRouter.route()  ←─ IntentAnalyzer (任务分类 + 复杂度)
    ↓
SimpleAgent.chat() / MultiAgentOrchestrator.execute()
    ↓
┌─ 阶段 3.2: _select_tools() ─────────────────────────────────┐
│  1. 三级优先级判断: Schema > Plan > Intent                   │
│  2. ToolSelector.select():                                   │
│     - 添加核心工具 (Level 1): plan_todo, HITL, sandbox_*     │
│     - 匹配动态工具 (Level 2): 按 capability 标签查找         │
│     - 约束检查 + 优先级排序                                  │
│  3. 转换为 Claude API 格式                                   │
└──────────────────────────────────────────────────────────────┘
    ↓
┌─ 阶段 3.4: RVR 循环 ─────────────────────────────────────────┐
│  for turn in range(max_turns):                               │
│    1. LLM.create_message_stream() → tool_use / end_turn      │
│    2. if tool_use:                                           │
│       _execute_tools_stream() → ToolExecutor.execute()       │
│       append tool_results to messages                        │
│       continue                                               │
│    3. if end_turn: break                                     │
└──────────────────────────────────────────────────────────────┘
    ↓
返回结果
```

---

## Level 1 核心工具验证

### 当前 capabilities.yaml 中的 Level 1 工具

| 工具名 | 行号 | 职责 | 问题 |
|--------|------|------|------|
| `api_calling` | L440 | REST API 调用 | ✅ |
| `request_human_confirmation` | L909 | HITL 人工确认 | ✅ |
| `plan_todo` | L1015 | 任务规划 | ⚠️ 内部 LLM 无超时 |
| `sandbox_write_file` | L1171 | 沙盒写文件 | ✅ |
| `sandbox_run_command` | L1200 | 沙盒执行命令 | ✅ |
| `sandbox_create_project` | L1231 | 沙盒创建项目 | ✅ |
| `sandbox_run_project` | L1266 | 沙盒运行项目 | ✅ |

### 代码定义对比

```python
# core/tool/selector.py L79 - 默认核心工具（备用）
DEFAULT_CORE_TOOLS = ["plan_todo", "bash", "request_human_confirmation"]
# 问题: bash 不在 capabilities.yaml 的 level:1 列表中

# core/tool/loader.py L58-68 - 核心工具常量
CORE_TOOLS = [
    "plan_todo",
    "api_calling",
    "request_human_confirmation",
    "file_read",  # ❌ 不存在于 capabilities.yaml
    "sandbox_write_file",
    "sandbox_run_command",
    "sandbox_create_project",
    "sandbox_run_project",
]
```

### 修复建议

1. **删除 `file_read`**: loader.py 中引用了不存在的工具
2. **统一数据源**: 从 capabilities.yaml 动态读取，不在代码中硬编码
3. **移除 selector 的 `bash`**: bash 是 Claude 原生工具，不应在核心工具列表

---

## plan_todo_tool 深度审查

### 问题 1: LLM 调用无超时保护

```python
# tools/plan_todo_tool.py L876-879
response = await self._llm.create_message_async(
    messages=[Message(role="user", content=prompt)],
    system="..."
)
# ❌ 没有 timeout，如果 LLM 卡住会无限等待
```

### 问题 2: 降级策略信息丢失

```python
# L912-920
except json.JSONDecodeError as e:
    # 降级：使用简单的默认计划
    return self._create_plan_from_data({
        "goal": user_query,
        "steps": [{"action": user_query, "capability": "task_planning"}],
        # ❌ 丢失了所有 matched_skills、information_gaps 信息
    })
```

### 问题 3: replan 次数限制硬编码

```python
# L1150-1151
max_replan = 3  # 默认最大重规划次数
# ❌ 应该从配置读取，不同任务类型可能需要不同限制
```

### 问题 4: Skill 发现与工具选择重复

```python
# L840-841 - plan_todo 内部做 Skill 发现
all_skills = discover_skills()
matched_skills = match_skills_for_query(user_query, all_skills)

# simple_agent.py L800-802 - 工具选择时又做一次
intent_capabilities = self.capability_registry.get_capabilities_for_task_type(...)
```

两处逻辑独立，可能产生不一致的推荐。

---

## 工具选择三级优先级问题

### 当前逻辑（互斥选择）

```python
# simple_agent.py L822-860
if self.schema.tools:
    required_capabilities = valid_tools     # 只用 Schema
elif plan and plan.get('required_capabilities'):
    required_capabilities = plan_caps       # 只用 Plan
else:
    required_capabilities = intent_caps     # 只用 Intent
```

### 问题场景

| Schema 配置 | Plan 推荐 | 实际需要 | 结果 |
|-------------|-----------|----------|------|
| `["web_search"]` | `["e2b_sandbox"]` | 两者都需要 | ❌ 只加载 web_search |
| `[]` (空) | `["ppt_generator"]` | ppt_generator | ✅ 正确 |
| `["api_calling"]` | - | api_calling | ✅ 正确 |

### 建议改为合并策略

```python
required_capabilities = []

# 1. Schema 配置（最高优先级，直接使用）
if self.schema.tools:
    required_capabilities.extend(valid_tools)

# 2. Plan 推荐（补充，不覆盖）
if plan and plan.get('required_capabilities'):
    for cap in plan['required_capabilities']:
        if cap not in required_capabilities:
            required_capabilities.append(cap)

# 3. Intent 推断（兜底，当前面都为空时使用）
if not required_capabilities:
    required_capabilities = intent_capabilities
```

---

## 工具执行链路验证

### ToolExecutor.execute() 调用路径

```
_execute_single_tool()
    ├─ tool_name == "plan_todo"
    │   └─ _execute_plan_todo() → PlanTodoTool.execute()
    │
    ├─ tool_name == "request_human_confirmation"
    │   └─ _handle_human_confirmation() → wait_for_response()
    │
    └─ 其他工具
        └─ UnifiedToolCaller.call()
            ├─ SKILL 类型 → _call_skill() / fallback
            └─ TOOL 类型 → ToolExecutor.execute()
                ├─ CLAUDE_SERVER_TOOLS → 返回 handled_by: anthropic
                ├─ CLAUDE_CLIENT_TOOLS → _execute_client_tool() → Sandbox
                └─ 自定义工具 → tool_instance.execute()
```

### 潜在问题

1. **嵌套调用**: `UnifiedToolCaller.call()` 调用 `ToolExecutor.execute()`，形成间接递归
2. **错误边界不清晰**: 异常在哪一层处理？当前在 `_execute_single_tool` 统一 catch
3. **Sandbox 工具依赖 conversation_id**: 如果未注入会失败

---

## 优化优先级排序

| 优先级 | 问题 | 影响范围 | 修复复杂度 |
|--------|------|----------|------------|
| P0 | Level 1 工具定义不一致 | 全局 | 低 |
| P0 | plan_todo LLM 无超时 | 规划阶段 | 低 |
| P0 | 三级优先级覆盖盲区 | 工具选择 | 中 |
| P1 | 工具加载隔离失败 | Agent 启动 | 低 |
| P1 | HITL 前端断连处理 | 用户体验 | 中 |
| P1 | Skill 发现重复 | 性能 | 中 |
| P2 | Schema 验证时机 | 配置错误发现 | 低 |
| P2 | 工具执行指标监控 | 可观测性 | 中 |
| P2 | 核心工具健康检查 | 可靠性 | 中 |

---

## 附录: 关键文件索引

| 文件 | 职责 |
|------|------|
| `config/capabilities.yaml` | 工具配置中心（Level 1/2、Schema、约束） |
| `core/tool/capability/registry.py` | 能力注册表（加载、查询、过滤） |
| `core/tool/capability/types.py` | Capability 数据模型 |
| `core/tool/selector.py` | 工具选择器（三级优先级） |
| `core/tool/executor.py` | 工具执行器（动态加载、统一执行） |
| `core/tool/loader.py` | 工具加载器（类别展开、核心工具） |
| `core/tool/unified_tool_caller.py` | 统一调用器（Skill 降级） |
| `core/agent/simple/simple_agent.py` | Agent 主入口（_select_tools） |
| `core/agent/simple/simple_agent_tools.py` | 工具执行 Mixin |
| `tools/plan_todo_tool.py` | 任务规划工具（Level 1） |
| `tools/request_human_confirmation.py` | HITL 确认工具（Level 1） |
| `tools/sandbox_tools.py` | 沙盒工具集（Level 1） |

---

**审查日期**: 2026-01-22  
**审查范围**: 工具发现→匹配→选择→调用全链路  
**待修复项**: 9 个（P0: 3, P1: 3, P2: 3）
