# Prompt 模板系统设计

> 📅 **版本**: V1.0  
> 🎯 **核心思想**: **事件驱动** 的 Prompt 管理 - 变量替换 + 事件触发追加  
> 🔗 **相关文档**: [15-FRAMEWORK_PROMPT_CONTRACT.md](./15-FRAMEWORK_PROMPT_CONTRACT.md)

---

## 📋 目录

- [设计目标](#设计目标)
- [事件驱动架构](#事件驱动架构)
- [整体架构](#整体架构)
- [Agent Schema](#agent-schema)
- [Prompt Template](#prompt-template)
- [变量系统](#变量系统)
- [追加规则](#追加规则)
- [Prompt Builder API](#prompt-builder-api)
- [与现有代码集成](#与现有代码集成)
- [目录结构](#目录结构)

---

## 🎯 设计目标

### 核心思想：统一的事件驱动

整个 Agent 运行逻辑是 **事件驱动** 的：

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        统一事件驱动架构                                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   已有的事件驱动                         触发 Prompt 追加的事件               │
│   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│                                                                              │
│   • Session 生命周期                   这些事件触发 PromptManager 追加：      │
│     - session_start                      - intent_analyzed → 意图规范        │
│     - session_end                        - rag_completed → RAG 上下文        │
│                                          - file_uploaded → 文件规范          │
│   • Conversation 生命周期                - task_detected → 任务规范          │
│     - conversation_start                 - tool_selected → 工具规范          │
│     - conversation_delta                 - context_injected → 用户上下文     │
│     - conversation_stop                                                      │
│                                                                              │
│   • Message 生命周期                   事件是触发源，不是结果                 │
│     - message_start                    不需要额外的 "prompt_append" 事件     │
│     - message_delta                                                          │
│     - message_stop                                                           │
│                                                                              │
│   • Content 生命周期                                                         │
│     - content_start                                                          │
│     - content_delta                                                          │
│     - content_stop                                                           │
│                                                                              │
│   数据存储：事件驱动 ✅                 Prompt 追加：事件驱动 ✅              │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 核心需求

1. **事件驱动追加** - Prompt 追加由事件触发，而非写死的规则
2. **变量替换** - 支持前端变量注入（位置、时区、设备等）
3. **Agent 配置化** - 把 Agent 配置拆分，支持多 Agent 管理
4. **离线 vs 在线分离** - 模板定义离线，变量替换/事件处理在线（毫秒级）

### 设计原则

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         离线 vs 在线 分离                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   离线部分（预定义，启动时加载）                                             │
│   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│   • Agent Schema（配置文件）                                                 │
│   • Prompt Template（模板内容）                                              │
│   • Variable Schema（变量定义）                                              │
│   • Prompt Fragments（可追加的片段）                                         │
│                                                                              │
│   → 不调用 LLM，纯配置文件                                                   │
│                                                                              │
│   在线部分（事件驱动，毫秒级）                                               │
│   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│   • 事件触发 → 追加对应 Prompt 片段                                          │
│   • 变量值替换（字符串操作）                                                 │
│   • 最终 Prompt 组装                                                         │
│                                                                              │
│   → 不调用 LLM，纯字符串操作，1-5ms                                          │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 🔄 事件驱动架构

### 与现有 EventManager 集成

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      事件驱动的 Prompt 追加                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   SimpleAgent                                                                │
│        │                                                                     │
│        ▼                                                                     │
│   EventBroadcaster  ← Agent 统一入口                                         │
│        │                                                                     │
│        ├────────────────────┬───────────────────────────────────────┐       │
│        ▼                    ▼                                       ▼       │
│   EventManager         PromptManager（新增）                   其他模块      │
│        │                    │                                               │
│        │                    │  订阅事件                                     │
│        │                    │  ┌────────────────────────────────────┐      │
│        │                    │  │  file_uploaded → 追加文件规范      │      │
│        │                    │  │  rag_completed → 追加 RAG 上下文   │      │
│        │                    │  │  task_detected → 追加任务规范      │      │
│        │                    │  │  tool_selected → 追加工具规范      │      │
│        │                    │  └────────────────────────────────────┘      │
│        │                    │                                               │
│        ├── SessionEventManager                                              │
│        ├── UserEventManager                                                 │
│        ├── ConversationEventManager                                         │
│        ├── MessageEventManager                                              │
│        ├── ContentEventManager                                              │
│        └── SystemEventManager                                               │
│                    │                                                        │
│                    ▼                                                        │
│             EventStorage (Redis/Memory)                                     │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 触发 Prompt 追加的事件

```python
# 这些事件由 Agent 运行过程产生，触发 Prompt 追加
# 不需要额外的 "prompt_append" 事件，事件本身就是触发源

# 事件类型                    触发追加
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# file_uploaded              → 追加文件处理规范
# rag_completed              → 追加 RAG 上下文
# task_detected              → 追加任务规范（PPT/Excel/Code）
# tool_selected              → 追加工具使用规范
# context_injected           → 追加用户上下文
# intent_analyzed            → 追加意图相关规范
```

### 事件流程示例

```python
# Agent 运行过程中的事件流
# 事件触发 → PromptManager 订阅 → 自动追加对应 Prompt 片段

# 1. 意图识别完成 → 追加意图相关规范
await broadcaster.emit_intent_analyzed(
    session_id=session_id,
    intent={
        "task_type": "ppt_generation",
        "complexity": "high",
        "output_format": "pptx"
    }
)
# → PromptManager 自动追加 PPT 生成规范

# 2. RAG 检索完成 → 追加 RAG 上下文
await broadcaster.emit_rag_completed(
    session_id=session_id,
    results="从知识库检索到的内容...",
    source_count=3
)
# → PromptManager 自动追加 RAG 上下文到 System Prompt

# 3. 文件上传 → 追加文件处理规范
await broadcaster.emit_file_uploaded(
    session_id=session_id,
    files=[{"name": "report.xlsx", "type": "excel"}]
)
# → PromptManager 自动追加文件处理规范

# 4. 获取最终 System Prompt（包含所有事件触发的追加）
system_prompt = broadcaster.get_system_prompt(session_id)
```

### PromptManager 事件订阅

```python
# prompts/manager.py

from typing import Dict, Any, List, Callable
from dataclasses import dataclass, field


@dataclass
class PromptAppendRule:
    """Prompt 追加规则"""
    event_type: str                        # 触发事件类型
    fragment_id: str                       # 片段 ID
    condition: Callable[[Dict], bool] = None  # 条件判断函数（可选）
    priority: int = 50                     # 优先级


class PromptManager:
    """
    事件驱动的 Prompt 管理器
    
    职责：
    1. 订阅事件，响应追加
    2. 管理运行时 Prompt 状态
    3. 构建最终 System Prompt
    """
    
    def __init__(self):
        # 运行时 Prompt 状态（每个 session 独立）
        self._session_prompts: Dict[str, "SessionPromptState"] = {}
        
        # 事件订阅规则（事件 → 追加片段）
        self._append_rules: List[PromptAppendRule] = [
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # 意图识别事件 → 追加任务规范
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            PromptAppendRule(
                event_type="intent_analyzed",
                fragment_id="ppt_rules",
                condition=lambda data: data.get("intent", {}).get("task_type") == "ppt_generation"
            ),
            PromptAppendRule(
                event_type="intent_analyzed",
                fragment_id="excel_rules",
                condition=lambda data: data.get("intent", {}).get("task_type") == "excel_generation"
            ),
            PromptAppendRule(
                event_type="intent_analyzed",
                fragment_id="code_rules",
                condition=lambda data: data.get("intent", {}).get("task_type") == "code_task"
            ),
            
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # RAG 检索事件 → 追加 RAG 上下文
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            PromptAppendRule(
                event_type="rag_completed",
                fragment_id="rag_context",
                condition=lambda data: bool(data.get("results"))
            ),
            
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # 文件上传事件 → 追加文件处理规范
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            PromptAppendRule(
                event_type="file_uploaded",
                fragment_id="file_context",
                condition=lambda data: bool(data.get("files"))
            ),
            
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # 前端变量注入事件 → 追加用户上下文
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            PromptAppendRule(
                event_type="context_injected",
                fragment_id="user_context",
                condition=lambda data: bool(data.get("variables"))
            ),
            
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # 工具选择事件 → 追加工具使用规范
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            PromptAppendRule(
                event_type="tool_selected",
                fragment_id="e2b_rules",
                condition=lambda data: data.get("tool_name") == "e2b_sandbox"
            ),
        ]
    
    async def handle_event(
        self,
        session_id: str,
        event_type: str,
        event_data: Dict[str, Any]
    ):
        """
        处理事件，触发 Prompt 追加
        
        Args:
            session_id: 会话 ID
            event_type: 事件类型
            event_data: 事件数据
        """
        state = self._get_or_create_state(session_id)
        
        for rule in self._append_rules:
            if rule.event_type != event_type:
                continue
            
            # 检查条件
            if rule.condition and not rule.condition(event_data):
                continue
            
            # 追加片段
            await self._append_fragment(
                state=state,
                fragment_id=rule.fragment_id,
                event_data=event_data,
                priority=rule.priority
            )
    
    async def _append_fragment(
        self,
        state: "SessionPromptState",
        fragment_id: str,
        event_data: Dict[str, Any],
        priority: int
    ):
        """追加 Prompt 片段"""
        # 加载片段
        fragment = self._load_fragment(fragment_id)
        
        # 替换变量
        rendered = self._render_fragment(fragment, event_data)
        
        # 添加到状态
        state.append(
            fragment_id=fragment_id,
            content=rendered,
            priority=priority
        )
    
    def build_system_prompt(
        self,
        session_id: str,
        agent_id: str = "universal"
    ) -> str:
        """
        构建最终 System Prompt
        
        Args:
            session_id: 会话 ID
            agent_id: Agent ID
            
        Returns:
            完整的 System Prompt
        """
        # 获取基础模板
        base_prompt = self._load_agent_template(agent_id)
        
        # 获取会话状态
        state = self._get_or_create_state(session_id)
        
        # 按优先级排序并组装追加内容
        appended_content = state.get_sorted_content()
        
        # 组装最终 Prompt
        return base_prompt + "\n\n" + appended_content


@dataclass
class SessionPromptState:
    """会话级 Prompt 状态"""
    session_id: str
    appended_fragments: Dict[str, "AppendedFragment"] = field(default_factory=dict)
    
    def append(self, fragment_id: str, content: str, priority: int):
        """追加片段（同 ID 会覆盖）"""
        self.appended_fragments[fragment_id] = AppendedFragment(
            fragment_id=fragment_id,
            content=content,
            priority=priority
        )
    
    def get_sorted_content(self) -> str:
        """获取按优先级排序的内容"""
        sorted_fragments = sorted(
            self.appended_fragments.values(),
            key=lambda f: f.priority,
            reverse=True
        )
        return "\n\n---\n\n".join(f.content for f in sorted_fragments)


@dataclass
class AppendedFragment:
    """已追加的片段"""
    fragment_id: str
    content: str
    priority: int
```

---

## 🏗️ 整体架构

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    事件驱动的 Prompt 模板系统架构                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                        Agent 运行时（事件源）                        │   │
│   │                                                                     │   │
│   │   SimpleAgent._execute_turn()                                       │   │
│   │        │                                                            │   │
│   │        ├── 文件上传 ────────────────→ file_uploaded 事件            │   │
│   │        ├── RAG 检索完成 ────────────→ rag_completed 事件            │   │
│   │        ├── 任务类型识别 ────────────→ task_detected 事件            │   │
│   │        ├── 工具选择 ────────────────→ tool_selected 事件            │   │
│   │        └── 前端变量注入 ────────────→ context_injected 事件         │   │
│   │                                                                     │   │
│   └────────────────────────────────┬────────────────────────────────────┘   │
│                                    │                                        │
│                                    │ 事件                                   │
│                                    ▼                                        │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                        PromptManager（事件订阅）                     │   │
│   │                                                                     │   │
│   │   订阅规则（事件 → 追加片段）：                                      │   │
│   │   ┌─────────────────────────────────────────────────────────────┐  │   │
│   │   │  intent_analyzed   → 追加 ppt_rules / excel_rules / code    │  │   │
│   │   │  rag_completed     → 追加 rag_context.md                    │  │   │
│   │   │  file_uploaded     → 追加 file_context.md                   │  │   │
│   │   │  context_injected  → 追加 user_context.md                   │  │   │
│   │   │  tool_selected     → 追加 e2b_rules.md                      │  │   │
│   │   └─────────────────────────────────────────────────────────────┘  │   │
│   │                                                                     │   │
│   │   SessionPromptState（会话级 Prompt 状态）                          │   │
│   │   ┌─────────────────────────────────────────────────────────────┐  │   │
│   │   │  session_id: "sess_123"                                     │  │   │
│   │   │  base_prompt: "..."          # 基础 Prompt                  │  │   │
│   │   │  appended_fragments: [       # 已追加的片段                 │  │   │
│   │   │    {id: "user_context", priority: 100, content: "..."},     │  │   │
│   │   │    {id: "file_context", priority: 90, content: "..."},      │  │   │
│   │   │    {id: "ppt_rules", priority: 70, content: "..."},         │  │   │
│   │   │  ]                                                          │  │   │
│   │   └─────────────────────────────────────────────────────────────┘  │   │
│   │                                                                     │   │
│   └────────────────────────────────┬────────────────────────────────────┘   │
│                                    │                                        │
│                                    │ build()                                │
│                                    ▼                                        │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                         最终 System Prompt                           │   │
│   │                                                                     │   │
│   │   [基础 Prompt]                                                     │   │
│   │   ───────────────────────────────                                   │   │
│   │   [用户上下文]  ← context_injected 事件触发                         │   │
│   │   [文件信息]    ← file_uploaded 事件触发                            │   │
│   │   [RAG 结果]    ← rag_completed 事件触发                            │   │
│   │   [PPT 规范]    ← task_detected 事件触发                            │   │
│   │   [沙盒上下文]  ← 默认追加（conversation_id 存在时）                │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│                                                                              │
│   离线资源（启动时加载）                                                     │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │   agents/                      │  fragments/                        │   │
│   │   ├── universal/               │  ├── user_context.md               │   │
│   │   │   ├── schema.yaml          │  ├── file_context.md               │   │
│   │   │   ├── prompt.md            │  ├── rag_context.md                │   │
│   │   │   └── variables.yaml       │  ├── ppt_rules.md                  │   │
│   │   └── data_analyst/            │  ├── excel_rules.md                │   │
│   │       └── ...                  │  └── sandbox_context.md            │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 📦 Agent Schema

### Schema 定义

每个 Agent 有一个 `schema.yaml` 文件，定义其配置：

```yaml
# agents/universal/schema.yaml

# 基本信息
id: "universal"
name: "通用智能体"
description: "能够处理各种任务的通用 Agent"
version: "1.0"

# 组件配置
components:
  intent_analyzer:
    enabled: true
    complexity_levels: ["low", "medium", "high"]
    task_types:
      - "information_query"
      - "content_generation"
      - "data_analysis"
      - "code_task"
      - "document_generation"
    output_formats: ["text", "excel", "ppt", "pdf", "code"]
    
  plan_manager:
    enabled: true
    trigger_condition: "complexity == 'high'"
    max_steps: 10
    granularity: "medium"  # fine | medium | coarse
    
  tool_selector:
    enabled: true
    available_tools:
      - "web_search"
      - "e2b_sandbox"
      - "plan_todo"
    selection_strategy: "capability_based"
    allow_parallel: false
    
  memory_manager:
    enabled: true
    retention_policy: "session"  # session | persistent | hybrid
    episodic_memory: false
    working_memory_limit: 10

# Skills 配置
skills:
  - type: "anthropic"
    skill_id: "xlsx"
    version: "latest"
  - type: "anthropic"
    skill_id: "pptx"
    version: "latest"

# 运行时参数
runtime:
  max_turns: 15
  allow_parallel_tools: false
  context_limits:
    max_context_tokens: 200000
    warning_threshold: 0.8

# Prompt 配置
prompt:
  template_file: "prompt.md"
  variables_file: "variables.yaml"
  include_skills_metadata: true
  include_e2b_protocol: true
```

### Agent 注册表

```yaml
# agents/registry.yaml

agents:
  universal:
    path: "agents/universal"
    default: true  # 默认 Agent
    
  data_analyst:
    path: "agents/data_analyst"
    
  ppt_creator:
    path: "agents/ppt_creator"
    
  code_assistant:
    path: "agents/code_assistant"
```

---

## 📝 Prompt Template

### 模板格式

Prompt 模板使用 Markdown 格式，支持变量占位符和注入槽位：

```markdown
<!-- agents/universal/prompt.md -->

# 🎯 核心使命

你是一个**通用智能体**，能够处理任何用户需求。

**你的价值**：基于用户 Query，通过分析、规划、执行、验证、反思，生成**高质量结果**。

---

# 📌 用户上下文

{{@user_context}}

---

# 📋 意图识别协议

{{@intent_protocol}}

---

# 🔧 工具使用规范

{{@tools_protocol}}

---

# 📚 知识库上下文

{{@rag_context}}

---

# 🎨 任务特定规范

{{@task_specific_rules}}

---

# ⚙️ 沙盒上下文

{{@sandbox_context}}

---

# 🛠️ 可用 Skills

{{@skills_metadata}}
```

### 占位符语法

| 语法 | 说明 | 示例 |
|------|------|------|
| `{{variable}}` | 变量替换 | `{{location}}` → `北京` |
| `{{variable.description}}` | 变量描述 | `{{location.description}}` → `用户当前位置` |
| `{{@slot}}` | 注入槽位 | `{{@rag_context}}` → RAG 检索结果 |
| `{{#if condition}}...{{/if}}` | 条件块 | 根据条件决定是否保留内容 |

---

## 🔤 变量系统

### 变量定义

```yaml
# agents/universal/variables.yaml

# 前端变量（来自 ChatRequest.variables）
frontend_variables:
  location:
    type: string
    description: "用户当前位置"
    required: false
    example: "北京市朝阳区"
    
  timezone:
    type: string
    description: "用户时区"
    required: false
    default: "UTC"
    example: "Asia/Shanghai"
    
  currentTime:
    type: datetime
    description: "当前时间"
    required: false
    format: "YYYY-MM-DD HH:mm"
    example: "2026-01-08 10:30"
    
  device:
    type: enum
    description: "设备类型"
    values: ["mobile", "desktop", "tablet"]
    required: false
    
  locale:
    type: string
    description: "用户语言环境"
    required: false
    default: "zh-CN"
    example: "zh-CN"
    
  userAgent:
    type: string
    description: "浏览器 User Agent"
    required: false

# 系统变量（框架自动注入）
system_variables:
  conversation_id:
    type: string
    description: "对话 ID"
    required: true
    
  user_id:
    type: string
    description: "用户 ID"
    required: true
    
  session_id:
    type: string
    description: "会话 ID"
    required: false
    
  message_id:
    type: string
    description: "消息 ID"
    required: false
```

### 变量渲染

变量在 Prompt 中的渲染格式：

```markdown
# 用户上下文（系统自动注入，帮助你理解用户环境）
{{#if location}}
- 位置: {{location}}（{{location.description}}）
{{/if}}
- 时区: {{timezone}}（{{timezone.description}}）
- 当前时间: {{currentTime}}（{{currentTime.description}}）
{{#if device}}
- 设备: {{device}}（{{device.description}}）
{{/if}}
```

渲染结果示例：

```markdown
# 用户上下文（系统自动注入，帮助你理解用户环境）
- 位置: 北京市朝阳区（用户当前位置）
- 时区: Asia/Shanghai（用户时区）
- 当前时间: 2026-01-08 10:30（当前时间）
- 设备: mobile（设备类型）
```

---

## ⏰ 追加规则（上下文驱动）

### 核心思想

**追加规则不是写死的配置，而是由运行时上下文驱动**

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      上下文驱动追加（Context-Driven Append）                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   上下文 Context                           自动追加                          │
│   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│                                                                              │
│   context.variables 存在            →      用户上下文片段                    │
│   context.conversation_id 存在      →      沙盒上下文片段                    │
│   context.files 非空                →      文件处理规范                      │
│   context.rag_results 非空          →      RAG 上下文片段                    │
│   context.task_hints.ppt 存在       →      PPT 生成规范                      │
│   context.task_hints.excel 存在     →      Excel 生成规范                    │
│   context.custom_prompts 存在       →      用户自定义追加                    │
│                                                                              │
│   不是预定义的"规则列表"，而是"上下文里有什么，就追加什么"                   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 上下文结构定义

```python
# 运行时上下文（由调用方传入）
context = {
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 系统变量（框架自动注入）
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    "conversation_id": "conv_123",
    "user_id": "user_456",
    "session_id": "sess_789",
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 前端变量（来自 ChatRequest.variables）
    # 有就追加用户上下文，没有就跳过
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    "variables": {
        "location": {"value": "北京", "description": "用户位置"},
        "timezone": {"value": "Asia/Shanghai", "description": "时区"},
        "device": {"value": "mobile", "description": "设备类型"}
    },
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 文件上下文（有文件时追加文件处理规范）
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    "files": [
        {"name": "report.xlsx", "type": "excel", "size": 1024}
    ],
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # RAG 结果（有检索结果时追加 RAG 上下文）
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    "rag_results": "从知识库检索到的内容...",
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 任务提示（存在哪个 key，就追加对应规范）
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    "task_hints": {
        "ppt": True,      # 追加 PPT 规范
        # "excel": True,  # 如果需要追加 Excel 规范
        # "code": True,   # 如果需要追加代码规范
    },
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 自定义追加（最灵活的方式）
    # 调用方可以直接传入要追加的 Prompt 片段
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    "custom_prompts": [
        {
            "slot": "task_rules",  # 追加到哪个槽位
            "content": "这是自定义的规范内容...",
            "priority": 50         # 优先级（可选）
        }
    ]
}
```

### 追加逻辑（PromptBuilder 内部）

```python
def _apply_context_driven_appends(
    self,
    context: Dict[str, Any],
    variables: Dict[str, Any]
) -> Dict[str, str]:
    """
    上下文驱动的追加逻辑
    
    不是遍历预定义的规则列表，而是检查上下文里有什么
    """
    injections = {}
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 1. conversation_id 存在 → 追加沙盒上下文
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    if context.get("conversation_id"):
        sandbox_content = self._load_fragment("sandbox_context.md")
        sandbox_content = self._replace_variables(sandbox_content, {
            "conversation_id": context["conversation_id"],
            "user_id": context.get("user_id", "")
        })
        injections["sandbox_context"] = sandbox_content
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 2. variables 存在 → 追加用户上下文
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    if context.get("variables"):
        user_context = self._build_user_context(context["variables"])
        injections["user_context"] = user_context
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 3. files 非空 → 追加文件处理规范
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    if context.get("files"):
        file_content = self._load_fragment("file_context.md")
        file_content = self._inject_file_info(file_content, context["files"])
        injections["file_context"] = file_content
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 4. rag_results 非空 → 追加 RAG 上下文
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    if context.get("rag_results"):
        rag_content = self._load_fragment("rag_context.md")
        rag_content = rag_content.replace("{{rag_results}}", context["rag_results"])
        injections["rag_context"] = rag_content
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 5. task_hints 存在 → 追加对应任务规范
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    task_hints = context.get("task_hints", {})
    task_rules_parts = []
    
    if task_hints.get("ppt"):
        task_rules_parts.append(self._load_fragment("ppt_rules.md"))
    
    if task_hints.get("excel"):
        task_rules_parts.append(self._load_fragment("excel_rules.md"))
    
    if task_hints.get("code"):
        task_rules_parts.append(self._load_fragment("code_rules.md"))
    
    if task_rules_parts:
        injections["task_rules"] = "\n\n---\n\n".join(task_rules_parts)
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 6. custom_prompts 存在 → 直接追加自定义内容
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    for custom in context.get("custom_prompts", []):
        slot = custom.get("slot", "custom")
        content = custom.get("content", "")
        if slot in injections:
            injections[slot] += "\n\n" + content
        else:
            injections[slot] = content
    
    return injections
```

### 使用示例

```python
# 示例 1: 最简单的调用（只有会话信息）
prompt = PromptBuilder.build(
    agent_id="universal",
    context={
        "conversation_id": "conv_123",
        "user_id": "user_456"
    }
)
# 结果: 基础 Prompt + 沙盒上下文

# 示例 2: 带前端变量
prompt = PromptBuilder.build(
    agent_id="universal",
    context={
        "conversation_id": "conv_123",
        "user_id": "user_456",
        "variables": {
            "location": {"value": "北京", "description": "用户位置"},
            "timezone": {"value": "Asia/Shanghai", "description": "时区"}
        }
    }
)
# 结果: 基础 Prompt + 沙盒上下文 + 用户上下文

# 示例 3: 带 RAG 结果
prompt = PromptBuilder.build(
    agent_id="universal",
    context={
        "conversation_id": "conv_123",
        "user_id": "user_456",
        "rag_results": "从知识库检索到的相关内容..."
    }
)
# 结果: 基础 Prompt + 沙盒上下文 + RAG 上下文

# 示例 4: PPT 任务
prompt = PromptBuilder.build(
    agent_id="universal",
    context={
        "conversation_id": "conv_123",
        "user_id": "user_456",
        "task_hints": {"ppt": True}
    }
)
# 结果: 基础 Prompt + 沙盒上下文 + PPT 规范

# 示例 5: 完全自定义追加
prompt = PromptBuilder.build(
    agent_id="universal",
    context={
        "conversation_id": "conv_123",
        "user_id": "user_456",
        "custom_prompts": [
            {
                "slot": "custom",
                "content": """
# 项目特定规范

这是针对当前项目的特殊要求：
1. 使用 React + TypeScript
2. 遵循公司代码规范
3. 所有变量使用驼峰命名
"""
            }
        ]
    }
)
# 结果: 基础 Prompt + 沙盒上下文 + 自定义规范
```

### Prompt 片段示例

```markdown
<!-- prompts/fragments/user_context.md -->

# 用户上下文（系统自动注入，帮助你理解用户环境）

{{#if location}}
- 位置: {{location}}（{{location.description}}）
{{/if}}
- 时区: {{timezone}}（{{timezone.description}}）
- 当前时间: {{currentTime}}（{{currentTime.description}}）
{{#if device}}
- 设备: {{device}}（{{device.description}}）
{{/if}}
{{#if locale}}
- 语言: {{locale}}（{{locale.description}}）
{{/if}}
```

```markdown
<!-- prompts/fragments/sandbox_context.md -->

# 📌 当前会话上下文（CRITICAL）

**必须使用以下参数调用 sandbox_* 工具：**

- **conversation_id**: `{{conversation_id}}`
- **user_id**: `{{user_id}}`

当你使用 sandbox_* 工具时，必须使用上面的 conversation_id。

## 沙盒工具使用示例

```json
{
    "conversation_id": "{{conversation_id}}",
    "path": "/home/user/app/index.html",
    "content": "..."
}
```
```

```markdown
<!-- prompts/fragments/rag_context.md -->

# 📚 相关知识（来自知识库）

以下是从知识库检索到的相关信息，请优先参考：

{{rag_results}}

---

**注意**：如果以上知识不足以回答用户问题，可以使用 web_search 工具获取更多信息。
```

```markdown
<!-- prompts/fragments/ppt_rules.md -->

# 🎨 PPT 生成规范

当生成 PPT 时，请遵循以下规范：

## 结构要求
- 包含封面页（标题 + 副标题）
- 包含目录页（概述内容结构）
- 每页 3-5 个要点，不要过于拥挤
- 包含总结页

## 内容要求
- 标题简洁有力
- 要点使用动词开头
- 数据可视化（图表优于纯文字）
- 保持风格一致

## 技术要求
- 使用 pptx Skill 生成
- 文件名使用英文
- 完成后提供下载链接
```

---

## 🔧 Prompt Builder API

### 核心接口

```python
# prompts/builder.py

from typing import Dict, Any, Optional, List
from pathlib import Path
import yaml
import re
from datetime import datetime


class PromptBuilder:
    """
    Prompt 构建器
    
    负责：
    1. 加载 Agent 配置和模板（启动时）
    2. 变量替换（运行时）
    3. 追加规则处理（运行时）
    4. 最终 Prompt 组装（运行时）
    """
    
    _instance = None
    _agents: Dict[str, "AgentConfig"] = {}
    _append_rules: List["AppendRule"] = []
    _fragments: Dict[str, str] = {}
    
    def __init__(self, config_dir: str = "prompts"):
        self.config_dir = Path(config_dir)
        self._load_all()
    
    @classmethod
    def get_instance(cls) -> "PromptBuilder":
        """获取单例实例"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 离线部分：加载配置（启动时执行一次）
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    def _load_all(self):
        """加载所有配置"""
        self._load_agents()
        self._load_append_rules()
        self._load_fragments()
    
    def _load_agents(self):
        """加载所有 Agent 配置"""
        registry_path = self.config_dir / "agents" / "registry.yaml"
        # ... 加载逻辑
        pass
    
    def _load_append_rules(self):
        """加载追加规则"""
        rules_path = self.config_dir / "append_rules.yaml"
        # ... 加载逻辑
        pass
    
    def _load_fragments(self):
        """加载 Prompt 片段"""
        fragments_dir = self.config_dir / "fragments"
        # ... 加载逻辑
        pass
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 在线部分：构建 Prompt（每次请求执行，毫秒级）
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    def build(
        self,
        agent_id: str = "universal",
        variables: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        构建最终 System Prompt
        
        Args:
            agent_id: Agent ID（默认 "universal"）
            variables: 前端变量（ChatRequest.variables）
            context: 上下文信息（conversation_id, files, rag_results 等）
            
        Returns:
            构建好的 System Prompt 字符串
            
        示例:
            prompt = PromptBuilder.get_instance().build(
                agent_id="universal",
                variables={
                    "location": {"value": "北京", "description": "用户位置"},
                    "timezone": {"value": "Asia/Shanghai", "description": "时区"}
                },
                context={
                    "conversation_id": "conv_123",
                    "user_id": "user_456",
                    "files": [...],
                    "rag_results": "...",
                    "task_type": "ppt_generation"
                }
            )
        """
        # 1. 获取 Agent 配置
        agent = self._agents.get(agent_id)
        if not agent:
            agent = self._agents.get("universal")
        
        # 2. 加载基础模板
        base_prompt = agent.prompt_template
        
        # 3. 准备变量
        resolved_variables = self._resolve_variables(
            variables or {},
            context or {},
            agent.variable_schema
        )
        
        # 4. 应用追加规则
        injections = self._apply_append_rules(context or {}, resolved_variables)
        
        # 5. 替换变量和注入槽位
        final_prompt = self._render(base_prompt, resolved_variables, injections)
        
        return final_prompt
    
    def _resolve_variables(
        self,
        frontend_vars: Dict[str, Any],
        context: Dict[str, Any],
        schema: "VariableSchema"
    ) -> Dict[str, Any]:
        """
        解析变量值
        
        处理：
        - 从 frontend_vars 提取值和描述
        - 应用默认值
        - 格式化（如 datetime）
        """
        resolved = {}
        
        # 处理前端变量
        for var_name, var_data in frontend_vars.items():
            if isinstance(var_data, dict):
                # 格式: {"value": "...", "description": "..."}
                resolved[var_name] = var_data.get("value", "")
                resolved[f"{var_name}.description"] = var_data.get("description", "")
            else:
                # 格式: 直接值
                resolved[var_name] = var_data
                # 从 schema 获取描述
                if var_name in schema.frontend_variables:
                    resolved[f"{var_name}.description"] = schema.frontend_variables[var_name].description
        
        # 处理系统变量
        for var_name in ["conversation_id", "user_id", "session_id", "message_id"]:
            if var_name in context:
                resolved[var_name] = context[var_name]
        
        return resolved
    
    def _apply_append_rules(
        self,
        context: Dict[str, Any],
        variables: Dict[str, Any]
    ) -> Dict[str, str]:
        """
        应用追加规则，返回每个槽位的内容
        """
        injections = {}
        
        for rule in self._append_rules:
            # 检查条件
            if not self._evaluate_condition(rule.condition, context):
                continue
            
            # 加载片段内容
            fragment = self._fragments.get(rule.content_file, "")
            
            # 替换片段中的变量
            rendered = self._replace_variables(fragment, variables)
            
            # 处理特殊内容（如 RAG 结果）
            if rule.id == "rag_context" and "rag_results" in context:
                rendered = rendered.replace("{{rag_results}}", context["rag_results"])
            
            # 存储到对应槽位
            slot_name = rule.slot.replace("@", "")
            if slot_name in injections:
                injections[slot_name] += "\n\n" + rendered
            else:
                injections[slot_name] = rendered
        
        return injections
    
    def _evaluate_condition(self, condition: str, context: Dict[str, Any]) -> bool:
        """评估条件表达式"""
        if condition == "always":
            return True
        
        # 简单的条件解析
        # 例如: "context.files is not empty"
        # 例如: "context.task_type == 'ppt_generation'"
        
        # ... 条件解析逻辑
        return True
    
    def _render(
        self,
        template: str,
        variables: Dict[str, Any],
        injections: Dict[str, str]
    ) -> str:
        """
        渲染最终 Prompt
        
        1. 替换变量 {{variable}}
        2. 替换注入槽位 {{@slot}}
        3. 处理条件块 {{#if}}...{{/if}}
        """
        result = template
        
        # 替换变量
        result = self._replace_variables(result, variables)
        
        # 替换注入槽位
        for slot_name, content in injections.items():
            result = result.replace(f"{{{{@{slot_name}}}}}", content)
        
        # 清理未使用的槽位
        result = re.sub(r'\{\{@\w+\}\}', '', result)
        
        # 处理条件块
        result = self._process_conditionals(result, variables)
        
        return result
    
    def _replace_variables(self, text: str, variables: Dict[str, Any]) -> str:
        """替换变量占位符"""
        for var_name, var_value in variables.items():
            text = text.replace(f"{{{{{var_name}}}}}", str(var_value))
        return text
    
    def _process_conditionals(self, text: str, variables: Dict[str, Any]) -> str:
        """处理条件块"""
        # 匹配 {{#if variable}}...{{/if}}
        pattern = r'\{\{#if\s+(\w+)\}\}(.*?)\{\{/if\}\}'
        
        def replacer(match):
            var_name = match.group(1)
            content = match.group(2)
            if var_name in variables and variables[var_name]:
                return content
            return ""
        
        return re.sub(pattern, replacer, text, flags=re.DOTALL)
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 工具方法
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    def get_agent_schema(self, agent_id: str) -> Optional["AgentConfig"]:
        """获取 Agent 配置"""
        return self._agents.get(agent_id)
    
    def get_variable_schema(self, agent_id: str) -> Optional["VariableSchema"]:
        """获取变量 Schema（用于前端展示）"""
        agent = self._agents.get(agent_id)
        return agent.variable_schema if agent else None
    
    def list_agents(self) -> List[Dict[str, str]]:
        """列出所有可用 Agent"""
        return [
            {"id": agent_id, "name": agent.name, "description": agent.description}
            for agent_id, agent in self._agents.items()
        ]
```

### 使用示例

```python
# 在 simple_agent.py 中使用

from prompts.builder import PromptBuilder

async def _execute_turn(self, messages, session_id, ...):
    # 获取会话上下文
    session_context = await self.event_manager.storage.get_session_context(session_id)
    
    # 构建 System Prompt
    system_prompt = PromptBuilder.get_instance().build(
        agent_id=session_context.get("agent_id", "universal"),
        variables=session_context.get("variables"),  # 前端变量
        context={
            "conversation_id": session_context.get("conversation_id"),
            "user_id": session_context.get("user_id"),
            "files": session_context.get("files"),
            "rag_results": await self._get_rag_results(messages),  # 可选
            "task_type": await self._detect_task_type(messages)     # 可选
        }
    )
    
    # 使用构建好的 Prompt
    response = await self.llm.create_message(
        system=system_prompt,
        messages=messages,
        ...
    )
```

---

## 🔗 与现有代码集成

### 核心：与 EventManager 集成

```python
# core/events/broadcaster.py 扩展

class EventBroadcaster:
    """
    事件广播器（Agent 统一入口）
    
    扩展：集成 PromptManager 事件订阅
    """
    
    def __init__(self, event_manager: EventManager):
        self.event_manager = event_manager
        self.prompt_manager = PromptManager()  # 🆕 Prompt 管理器
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 文件上传事件
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    async def emit_file_uploaded(
        self,
        session_id: str,
        files: List[Dict[str, Any]]
    ):
        """文件上传 → 触发 Prompt 追加"""
        # 1. 发送原有事件
        await self.event_manager.emit_custom(
            session_id=session_id,
            event_type="file_uploaded",
            event_data={"files": files}
        )
        
        # 2. 🆕 通知 PromptManager
        await self.prompt_manager.handle_event(
            session_id=session_id,
            event_type="file_uploaded",
            event_data={"files": files}
        )
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # RAG 检索完成事件
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    async def emit_rag_completed(
        self,
        session_id: str,
        results: str,
        source_count: int = 0
    ):
        """RAG 完成 → 触发 Prompt 追加"""
        event_data = {"results": results, "source_count": source_count}
        
        await self.event_manager.emit_custom(
            session_id=session_id,
            event_type="rag_completed",
            event_data=event_data
        )
        
        await self.prompt_manager.handle_event(
            session_id=session_id,
            event_type="rag_completed",
            event_data=event_data
        )
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 任务类型识别事件
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    async def emit_task_detected(
        self,
        session_id: str,
        task_type: str,
        confidence: float = 1.0
    ):
        """任务识别 → 触发 Prompt 追加"""
        event_data = {"task_type": task_type, "confidence": confidence}
        
        await self.event_manager.emit_custom(
            session_id=session_id,
            event_type="task_detected",
            event_data=event_data
        )
        
        await self.prompt_manager.handle_event(
            session_id=session_id,
            event_type="task_detected",
            event_data=event_data
        )
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 前端变量注入事件
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    async def emit_context_injected(
        self,
        session_id: str,
        variables: Dict[str, Any]
    ):
        """前端变量注入 → 触发 Prompt 追加"""
        event_data = {"variables": variables}
        
        await self.event_manager.emit_custom(
            session_id=session_id,
            event_type="context_injected",
            event_data=event_data
        )
        
        await self.prompt_manager.handle_event(
            session_id=session_id,
            event_type="context_injected",
            event_data=event_data
        )
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 获取当前 System Prompt
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    def get_system_prompt(self, session_id: str, agent_id: str = "universal") -> str:
        """获取当前会话的 System Prompt（包含所有已追加的片段）"""
        return self.prompt_manager.build_system_prompt(session_id, agent_id)
```

### SimpleAgent 中使用

```python
# core/agent/simple_agent.py

class SimpleAgent:
    
    async def _execute_turn(self, ...):
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 1. 处理前端变量 → 触发事件
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        if variables:
            await self.broadcaster.emit_context_injected(
                session_id=session_id,
                variables=variables
            )
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 2. 处理文件上传 → 触发事件
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        if files:
            await self.broadcaster.emit_file_uploaded(
                session_id=session_id,
                files=files
            )
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 3. 可选：任务类型识别 → 触发事件
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        task_type = await self._detect_task_type(message)
        if task_type:
            await self.broadcaster.emit_task_detected(
                session_id=session_id,
                task_type=task_type
            )
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 4. 可选：RAG 检索 → 触发事件
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        rag_results = await self._perform_rag(message)
        if rag_results:
            await self.broadcaster.emit_rag_completed(
                session_id=session_id,
                results=rag_results
            )
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 5. 获取最终 System Prompt（包含所有事件触发的追加）
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        system_prompt = self.broadcaster.get_system_prompt(
            session_id=session_id,
            agent_id=agent_id
        )
        
        # 6. 调用 LLM
        response = await self.llm.create_message(
            system=system_prompt,
            messages=messages,
            ...
        )
```

### ChatRequest 扩展

```python
# models/chat.py

class ChatRequest(BaseModel):
    """聊天请求"""
    message: str = Field(..., description="用户消息")
    user_id: str = Field(..., description="用户ID")
    conversation_id: Optional[str] = None
    
    # 🆕 Agent 选择
    agent_id: Optional[str] = Field(
        "universal",
        alias="agentId",
        description="Agent ID（可选，默认使用 universal）"
    )
    
    # 前端变量（触发 context_injected 事件）
    variables: Optional[Dict[str, Any]] = Field(
        None,
        description="前端上下文变量（位置、时区、设备等）"
    )
    
    # 文件（触发 file_uploaded 事件）
    files: Optional[List[FileReference]] = None
    
    # ... 其他字段
```

### 新增接口：列出可用 Agent

```python
# routers/agents.py

from prompts.manager import PromptManager

router = APIRouter(prefix="/api/v1/agents", tags=["agents"])

@router.get("")
async def list_agents():
    """列出所有可用的 Agent"""
    manager = PromptManager.get_instance()
    return manager.list_agents()


@router.get("/{agent_id}/variables")
async def get_agent_variables(agent_id: str):
    """获取 Agent 的变量 Schema"""
    manager = PromptManager.get_instance()
    schema = manager.get_variable_schema(agent_id)
    if not schema:
        raise HTTPException(status_code=404, detail="Agent not found")
    return schema.to_dict()
```

---

## 📁 目录结构

```
prompts/
├── __init__.py
├── builder.py                      # PromptBuilder API
├── models.py                       # 数据模型（AgentConfig, VariableSchema 等）
├── append_rules.yaml               # 追加规则定义
│
├── agents/                         # Agent 配置目录
│   ├── registry.yaml               # Agent 注册表
│   │
│   ├── universal/                  # 通用 Agent
│   │   ├── schema.yaml             # Agent Schema
│   │   ├── prompt.md               # 基础 Prompt 模板
│   │   └── variables.yaml          # 变量定义
│   │
│   ├── data_analyst/               # 数据分析 Agent
│   │   ├── schema.yaml
│   │   ├── prompt.md
│   │   └── variables.yaml
│   │
│   └── ppt_creator/                # PPT 创建 Agent
│       ├── schema.yaml
│       ├── prompt.md
│       └── variables.yaml
│
└── fragments/                      # Prompt 片段（可追加内容）
    ├── user_context.md             # 用户上下文
    ├── sandbox_context.md          # 沙盒上下文
    ├── rag_context.md              # RAG 上下文
    ├── file_context.md             # 文件上下文
    ├── ppt_rules.md                # PPT 生成规范
    ├── excel_rules.md              # Excel 生成规范
    ├── code_rules.md               # 代码任务规范
    └── e2b_rules.md                # E2B 沙盒规范
```

---

## 📊 总结

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    事件驱动的 Prompt 模板系统                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   核心思想：统一事件驱动                                                     │
│   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│                                                                              │
│   ┌────────────────┐   ┌────────────────┐   ┌────────────────┐             │
│   │  数据存储       │   │  SSE 推送       │   │  Prompt 追加   │             │
│   │  EventStorage  │   │  EventManager  │   │  PromptManager │             │
│   └───────┬────────┘   └───────┬────────┘   └───────┬────────┘             │
│           │                    │                    │                       │
│           └────────────────────┴────────────────────┘                       │
│                                │                                            │
│                        统一事件驱动                                          │
│                                                                              │
│   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│                                                                              │
│   事件 → Prompt 追加 映射                                                   │
│   ────────────────────────────────────────────────────────────────────────  │
│                                                                              │
│   事件                           追加片段                                    │
│   ─────────────────────────      ──────────────────────────                 │
│   context_injected               user_context.md                            │
│   file_uploaded                  file_context.md                            │
│   rag_completed                  rag_context.md                             │
│   task_detected (ppt)            ppt_rules.md                               │
│   task_detected (excel)          excel_rules.md                             │
│   tool_selected (e2b)            e2b_rules.md                               │
│   session_start                  sandbox_context.md (默认)                  │
│                                                                              │
│   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│                                                                              │
│   运行时流程                                                                 │
│   ────────────────────────────────────────────────────────────────────────  │
│                                                                              │
│   SimpleAgent._execute_turn()                                               │
│        │                                                                    │
│        ├─── variables 存在? ───→ emit_context_injected() ───┐              │
│        │                                                    │              │
│        ├─── files 存在? ───────→ emit_file_uploaded() ──────┤              │
│        │                                                    │              │
│        ├─── RAG 触发? ─────────→ emit_rag_completed() ──────┤ 事件         │
│        │                                                    │              │
│        ├─── 任务识别? ─────────→ emit_task_detected() ──────┤              │
│        │                                                    │              │
│        │                                                    ▼              │
│        │                                           PromptManager           │
│        │                                                    │              │
│        │                                                    │ 订阅/处理    │
│        │                                                    ▼              │
│        │                                           SessionPromptState      │
│        │                                           (会话级 Prompt 状态)    │
│        │                                                    │              │
│        └─── get_system_prompt() ◀───────────────────────────┘              │
│                    │                                                        │
│                    ▼                                                        │
│             最终 System Prompt                                              │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 关键设计点

| 设计点 | 说明 |
|--------|------|
| **事件驱动** | Prompt 追加由事件触发，不是写死的配置 |
| **会话级状态** | 每个 session 有独立的 PromptState，追加是累积的 |
| **订阅机制** | PromptManager 订阅事件，响应追加 |
| **优先级排序** | 追加片段按优先级排序组装 |
| **与现有架构一致** | 复用 EventManager/Broadcaster 模式 |

---

## 🔗 相关文档

- [15-FRAMEWORK_PROMPT_CONTRACT.md](./15-FRAMEWORK_PROMPT_CONTRACT.md) - Prompt 驱动的 Agent 实例化机制
- [00-ARCHITECTURE-V4.md](./00-ARCHITECTURE-V4.md) - V4 架构总览
- [13-INVOCATION_STRATEGY_V2.md](./13-INVOCATION_STRATEGY_V2.md) - 调用策略

