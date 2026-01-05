# Context Engineering 优化方案

> 📅 **版本**: V1.0  
> 🎯 **目标**: 基于 Manus AI 实践优化 ZenFlux Agent 上下文管理  
> 📚 **参考**: [Context Engineering for AI Agents - Manus](https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus)

---

## 📋 目录

- [核心原则](#核心原则)
- [Context Reduction](#context-reduction-上下文精简)
- [Context Isolation](#context-isolation-上下文隔离)
- [Context Offloading](#context-offloading-上下文卸载)
- [Cache Optimization](#cache-optimization-缓存优化)
- [实施路线图](#实施路线图)

---

## 🎯 核心原则

### Manus 的智慧

> **"More context ≠ more intelligence"**  
> **"Simplification beats expansion"**  
> **"Build less, understand more"**

### 应用到 ZenFlux

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     ZenFlux Context Engineering 原则                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  1️⃣ 精简优于扩展 (Reduction over Expansion)                                 │
│     • 工具结果返回引用，而非完整内容                                          │
│     • LLM 需要时通过工具显式读取                                             │
│     • 避免在 context 中累积冗余信息                                          │
│                                                                              │
│  2️⃣ 消息传递优于共享内存 (Communication over Sharing)                       │
│     • Plan/Todo 通过明确的工具调用更新                                       │
│     • 避免隐式的状态共享                                                     │
│     • 每次交互都是显式的消息                                                 │
│                                                                              │
│  3️⃣ 分层抽象 (Hierarchical Abstraction)                                    │
│     • Level 1: Function Calling (高频、关键工具)                            │
│     • Level 2: Sandbox Utilities (中频、Shell 命令)                         │
│     • Level 3: Packages & APIs (低频、复杂编排)                             │
│                                                                              │
│  4️⃣ Cache 友好 (Cache-Friendly)                                            │
│     • System Prompt 稳定不变                                                │
│     • 工具定义按优先级分组                                                   │
│     • 避免频繁修改缓存内容                                                   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 🔧 Context Reduction - 上下文精简

### 问题诊断

**当前 ZenFlux 的问题**：

```python
# ❌ 问题 1：工具返回完整内容
# tools/file_operations.py
async def file_read(path: str) -> dict:
    content = read_file(path)
    return {
        "success": True,
        "content": content  # 可能有 100KB+，污染 context
    }

# ❌ 问题 2：浏览器返回完整 HTML
# tools/web_browser.py
async def navigate(url: str) -> dict:
    html = await fetch(url)
    return {
        "success": True,
        "html": html  # 可能有 500KB+
    }

# ❌ 问题 3：数据分析返回完整结果
# tools/data_analysis.py
async def analyze_csv(path: str) -> dict:
    df = pd.read_csv(path)
    summary = df.describe().to_string()  # 可能很长
    return {
        "success": True,
        "summary": summary  # 直接返回完整统计
    }
```

### 优化方案：智能结果精简器

```python
# core/tool/result_compactor.py

from typing import Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum


class CompactionStrategy(Enum):
    """精简策略"""
    NONE = "none"              # 不精简（小结果）
    REFERENCE = "reference"    # 返回引用（文件、URL）
    TRUNCATE = "truncate"      # 截断（长文本）
    SUMMARIZE = "summarize"    # 总结（复杂数据）
    STRUCTURED = "structured"  # 结构化摘要（JSON、表格）


@dataclass
class CompactionRule:
    """精简规则"""
    tool_name: str
    result_type: str  # "file" | "url" | "text" | "json" | "dataframe"
    strategy: CompactionStrategy
    max_size: int = 10000  # 最大保留大小（字符）
    
    # 可选：自定义精简函数
    custom_compactor: Optional[callable] = None


class ResultCompactor:
    """
    工具结果精简器
    
    职责：
    1. 根据工具类型和结果大小选择精简策略
    2. 将大结果转换为引用或摘要
    3. 保留原始结果的访问路径
    
    核心思想（Manus）：
    - 工具结果应该是"指针"而非"内容"
    - LLM 需要时通过工具显式读取
    - 避免 context 被冗余信息占据
    """
    
    def __init__(self):
        self.rules = self._init_rules()
    
    def _init_rules(self) -> Dict[str, CompactionRule]:
        """
        初始化精简规则
        
        规则来源：
        - 工具的元数据（capabilities.yaml）
        - 默认策略（根据返回类型推断）
        """
        return {
            # 文件操作类
            "file_write": CompactionRule(
                tool_name="file_write",
                result_type="file",
                strategy=CompactionStrategy.REFERENCE
            ),
            "file_read": CompactionRule(
                tool_name="file_read",
                result_type="file",
                strategy=CompactionStrategy.TRUNCATE,
                max_size=5000  # 只保留前 5000 字符
            ),
            
            # 网络操作类
            "web_search": CompactionRule(
                tool_name="web_search",
                result_type="json",
                strategy=CompactionStrategy.STRUCTURED,
                max_size=3000
            ),
            "browser_navigate": CompactionRule(
                tool_name="browser_navigate",
                result_type="url",
                strategy=CompactionStrategy.REFERENCE
            ),
            
            # 数据分析类
            "xlsx": CompactionRule(
                tool_name="xlsx",
                result_type="dataframe",
                strategy=CompactionStrategy.STRUCTURED,
                max_size=2000
            ),
            
            # E2B 沙箱类
            "e2b_sandbox": CompactionRule(
                tool_name="e2b_sandbox",
                result_type="mixed",
                strategy=CompactionStrategy.TRUNCATE,
                max_size=10000  # stdout/stderr 截断
            ),
        }
    
    def compact(
        self,
        tool_name: str,
        result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        精简工具结果
        
        Args:
            tool_name: 工具名称
            result: 原始结果
            
        Returns:
            精简后的结果
        """
        # 获取精简规则
        rule = self.rules.get(tool_name)
        if not rule:
            # 没有规则，应用默认策略
            return self._default_compact(result)
        
        # 检查结果大小
        result_size = self._estimate_size(result)
        if result_size <= rule.max_size:
            # 结果很小，不需要精简
            return result
        
        # 根据策略精简
        if rule.strategy == CompactionStrategy.REFERENCE:
            return self._compact_as_reference(tool_name, result)
        
        elif rule.strategy == CompactionStrategy.TRUNCATE:
            return self._compact_by_truncate(result, rule.max_size)
        
        elif rule.strategy == CompactionStrategy.STRUCTURED:
            return self._compact_as_structured(result, rule.max_size)
        
        elif rule.custom_compactor:
            return rule.custom_compactor(result)
        
        return result
    
    def _compact_as_reference(
        self,
        tool_name: str,
        result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        引用式精简（Manus 推荐）
        
        示例：
            原始: {"success": True, "content": "100KB of text..."}
            精简: {"success": True, "message": "File saved to /path/foo.txt", 
                   "reference": "file:///path/foo.txt"}
        """
        compacted = {
            "success": result.get("success", True),
            "message": self._generate_summary_message(tool_name, result)
        }
        
        # 添加引用
        if "path" in result:
            compacted["reference"] = f"file://{result['path']}"
        elif "url" in result:
            compacted["reference"] = result["url"]
        elif "id" in result:
            compacted["reference"] = f"{tool_name}://{result['id']}"
        
        # 提示 LLM 如何访问完整内容
        compacted["access_hint"] = self._generate_access_hint(tool_name, result)
        
        return compacted
    
    def _compact_by_truncate(
        self,
        result: Dict[str, Any],
        max_size: int
    ) -> Dict[str, Any]:
        """
        截断式精简
        
        保留前 N 个字符，添加截断标记
        """
        compacted = result.copy()
        
        # 找到需要截断的字段
        for key, value in result.items():
            if isinstance(value, str) and len(value) > max_size:
                truncated = value[:max_size]
                compacted[key] = truncated
                compacted[f"{key}_truncated"] = True
                compacted[f"{key}_original_size"] = len(value)
                compacted[f"{key}_hint"] = f"Only showing first {max_size} chars. Use appropriate tool to access full content."
        
        return compacted
    
    def _compact_as_structured(
        self,
        result: Dict[str, Any],
        max_size: int
    ) -> Dict[str, Any]:
        """
        结构化摘要
        
        对于 JSON、DataFrame 等结构化数据，提取关键信息
        """
        if "data" in result and isinstance(result["data"], list):
            # 列表数据：只保留前 N 条 + 总数
            data = result["data"]
            if len(data) > 10:
                compacted = result.copy()
                compacted["data"] = data[:10]
                compacted["data_summary"] = {
                    "total_count": len(data),
                    "showing": 10,
                    "truncated": True
                }
                return compacted
        
        elif "dataframe" in result or "summary" in result:
            # DataFrame：只保留统计摘要
            # 省略具体实现...
            pass
        
        return result
    
    def _generate_summary_message(
        self,
        tool_name: str,
        result: Dict[str, Any]
    ) -> str:
        """生成摘要消息"""
        if tool_name == "file_write":
            return f"File saved to {result.get('path', 'unknown path')}"
        elif tool_name == "browser_navigate":
            return f"Navigated to {result.get('url', 'unknown URL')}"
        elif tool_name == "web_search":
            count = len(result.get("results", []))
            return f"Found {count} search results"
        else:
            return f"{tool_name} completed successfully"
    
    def _generate_access_hint(
        self,
        tool_name: str,
        result: Dict[str, Any]
    ) -> str:
        """生成访问提示"""
        if tool_name == "file_write" and "path" in result:
            return f"Use file_read('{result['path']}') to access full content if needed"
        elif tool_name == "browser_navigate" and "url" in result:
            return f"Revisit {result['url']} if needed"
        return "Content available on request"
    
    def _estimate_size(self, result: Dict[str, Any]) -> int:
        """估算结果大小"""
        import json
        return len(json.dumps(result, ensure_ascii=False))
    
    def _default_compact(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """默认精简策略"""
        size = self._estimate_size(result)
        if size > 10000:
            return self._compact_by_truncate(result, 10000)
        return result


# ============================================================
# 集成到 ToolExecutor
# ============================================================

# core/tool/executor.py

class ToolExecutor:
    """工具执行器（增强版）"""
    
    def __init__(self, ...):
        # ... 原有初始化 ...
        
        # 🆕 结果精简器
        self.result_compactor = ResultCompactor()
    
    async def execute(
        self,
        tool_name: str,
        tool_input: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        执行工具并精简结果
        """
        # 1. 执行工具（原有逻辑）
        raw_result = await self._do_execute(tool_name, tool_input)
        
        # 2. 🆕 精简结果
        compacted_result = self.result_compactor.compact(tool_name, raw_result)
        
        # 3. 记录精简前后的大小（用于监控）
        raw_size = self.result_compactor._estimate_size(raw_result)
        compacted_size = self.result_compactor._estimate_size(compacted_result)
        
        if raw_size != compacted_size:
            logger.info(
                f"🔧 Result compacted: {tool_name} "
                f"{raw_size} → {compacted_size} bytes "
                f"({(1 - compacted_size/raw_size)*100:.1f}% reduction)"
            )
        
        return compacted_result
```

### 实际效果对比

```python
# ❌ 优化前：Context 污染
Turn 1:
  User: "分析这个 CSV 文件"
  Tool: xlsx("/data/sales.csv")
  Result: {
    "success": True,
    "summary": """
              count      mean       std  ...  (10KB+ 的统计数据)
    """  # 占用 10KB+ context
  }

Turn 2:
  User: "生成可视化图表"
  # Context 已经被上一轮的完整统计数据占据
  # LLM 可能忘记最初的任务

# ✅ 优化后：Context 清爽
Turn 1:
  User: "分析这个 CSV 文件"
  Tool: xlsx("/data/sales.csv")
  Result: {
    "success": True,
    "message": "Analyzed /data/sales.csv",
    "summary": {
      "row_count": 1000,
      "column_count": 5,
      "key_metrics": {"avg_sales": 12345}  # 只保留关键指标
    },
    "reference": "file:///data/sales_analysis.json",
    "access_hint": "Use file_read('/data/sales_analysis.json') for full stats"
  }  # 只占用 500 bytes

Turn 2:
  User: "生成可视化图表"
  # Context 清爽，LLM 专注于当前任务
  # 需要完整数据时会主动调用 file_read
```

---

## 🔒 Context Isolation - 上下文隔离

### Manus 的原则

> **"Do not communicate by sharing memory; instead, share memory by communicating."**  
> — Go 语言设计哲学

### ZenFlux 当前问题

```python
# ❌ 问题：隐式的状态共享

# Agent 内部
class SimpleAgent:
    def __init__(self):
        self.plan_state = {"plan": None, "todo": None}  # 共享状态
    
    async def _turn(self):
        # 多个方法隐式访问 self.plan_state
        if self.plan_state["plan"]:
            current_step = self._get_current_step()  # 隐式读取
            # ...
            self._update_step_status(...)  # 隐式写入
```

**问题**：
1. 状态变化不可追踪
2. 难以调试（谁修改了状态？）
3. 不利于多 Agent 协作
4. 违反 Memory-First Protocol

### 优化方案：显式消息传递

```python
# ✅ 优化：显式的工具调用

class SimpleAgent:
    """
    改进：Plan/Todo 状态完全通过工具调用管理
    
    原则：
    - 读取状态 → plan_todo.get_plan()
    - 更新状态 → plan_todo.update_step()
    - 不在 Agent 内部缓存状态
    - 所有状态访问都是显式的
    """
    
    def __init__(self):
        # ❌ 删除内部状态
        # self.plan_state = {...}
        
        # ✅ 只保留工具引用
        self.plan_todo_tool = PlanTodoTool(memory=self.memory)
    
    async def _turn(self):
        """
        每轮执行：显式读取状态
        """
        # 1. 🔧 显式读取当前状态（通过工具调用）
        plan_result = self.plan_todo_tool.execute(
            operation="get_plan",
            data={}
        )
        
        current_plan = plan_result.get("plan")
        
        # 2. LLM 推理和执行
        # ...
        
        # 3. 🔧 显式更新状态（通过工具调用）
        if tool_executed:
            update_result = self.plan_todo_tool.execute(
                operation="update_step",
                data={
                    "step_index": current_step_index,
                    "status": "completed",
                    "result": tool_result
                }
            )
```

### 多 Agent 协作场景

```python
# core/agent/multi_agent_coordinator.py

from typing import List, Dict, Any
from dataclasses import dataclass


@dataclass
class AgentMessage:
    """Agent 间消息（显式通信）"""
    from_agent: str
    to_agent: str
    message_type: str  # "task" | "result" | "question"
    content: Dict[str, Any]
    timestamp: str


class MultiAgentCoordinator:
    """
    多 Agent 协调器
    
    原则（Manus）：
    - ❌ 不通过共享 context 通信
    - ✅ 通过显式消息传递通信
    - ✅ 每个 Agent 有独立的 context
    """
    
    def __init__(self):
        self.agents: Dict[str, SimpleAgent] = {}
        self.message_queue: List[AgentMessage] = []
    
    async def delegate_task(
        self,
        from_agent: str,
        to_agent: str,
        task: Dict[str, Any]
    ):
        """
        任务委派：显式消息传递
        
        ✅ 优势：
        - 可追踪：每条消息都有记录
        - 可回溯：出错时可以重放
        - 可测试：消息是可序列化的
        """
        message = AgentMessage(
            from_agent=from_agent,
            to_agent=to_agent,
            message_type="task",
            content=task,
            timestamp=datetime.now().isoformat()
        )
        
        self.message_queue.append(message)
        
        # 通知目标 Agent
        target_agent = self.agents[to_agent]
        result = await target_agent.process_task(task)
        
        # 返回结果消息
        response = AgentMessage(
            from_agent=to_agent,
            to_agent=from_agent,
            message_type="result",
            content={"result": result},
            timestamp=datetime.now().isoformat()
        )
        
        self.message_queue.append(response)
        
        return result
```

---

## 📦 Context Offloading - 上下文卸载

### Manus 的三层抽象

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Hierarchical Action Space                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Level 1: Function Calling（高频、关键工具）                                 │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│  • 标准 Claude Tool Use                                                     │
│  • Schema-safe，类型检查                                                    │
│  • 高频使用（plan_todo, file_read, web_search）                            │
│  • ⚠️ 问题：每次修改都会破坏 cache                                          │
│  • ⚠️ 问题：工具太多会导致 confusion                                        │
│                                                                              │
│  Level 2: Sandbox Utilities（中频、Shell 命令）                             │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│  • E2B 沙箱中的 Shell 命令                                                  │
│  • 灵活扩展（不修改 function 定义）                                         │
│  • 适合大输出（写入文件而非返回）                                           │
│  • 示例：ls, grep, jq, curl                                                 │
│                                                                              │
│  Level 3: Packages & APIs（低频、复杂编排）                                 │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│  • 在沙箱中执行 Python 脚本                                                 │
│  • 调用预授权的 API                                                         │
│  • 适合数据密集型任务（链式调用）                                           │
│  • 示例：多步骤数据处理、API 编排                                           │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### ZenFlux 当前架构映射

| Manus Level | ZenFlux 对应 | 当前实现 | 优化空间 |
|------------|-------------|---------|---------|
| **Level 1** | `tools/*.py` (Function Calling) | ✅ 已实现 | ⚠️ 工具太多（12+） |
| **Level 2** | `e2b_sandbox` (Shell utilities) | ✅ 已实现 | ⚠️ 未充分利用 |
| **Level 3** | `e2b_vibe_coding` (Python scripts) | ✅ 已实现 | ⚠️ 未指导 LLM 使用 |

### 优化方案：动态工具分层

```python
# config/capabilities.yaml（增强版）

capability_categories:
  # ... 已有定义 ...

capabilities:
  # ============================================================
  # 🔥 Level 1: Core Tools（始终可用，高频）
  # ============================================================
  - name: plan_todo
    type: TOOL
    level: 1  # 🆕 层级标记
    capabilities: [task_planning]
    priority: 95
    cache_stable: true  # 🆕 Cache 稳定性标记
    
  - name: bash
    type: TOOL
    level: 1
    capabilities: [file_operations, code_execution]
    priority: 90
    cache_stable: true
  
  # ============================================================
  # 🔧 Level 2: Contextual Tools（按需加载）
  # ============================================================
  - name: web_search
    type: TOOL
    level: 2
    capabilities: [web_search]
    priority: 85
    cache_stable: true
    
  - name: slidespeak_render
    type: TOOL
    level: 2
    capabilities: [ppt_generation, api_calling]
    priority: 80
    cache_stable: false  # API 参数可能变化
  
  # ============================================================
  # 🌟 Level 3: Sandbox Utilities（Shell 命令，通过 bash 调用）
  # ============================================================
  - name: shell_utilities
    type: UTILITY  # 🆕 新类型
    level: 3
    description: |
      Available Shell utilities in E2B sandbox:
      - File operations: ls, cat, grep, sed, awk
      - Network: curl, wget
      - Data: jq, csvkit
      - Compression: zip, tar, gzip
      
      Usage: Call via bash tool
      Example: bash("ls -la /workspace")
    capabilities: [file_operations, data_processing]
    # 不占用 function call slots
  
  # ============================================================
  # 🚀 Level 4: Advanced Orchestration（Python 脚本编排）
  # ============================================================
  - name: advanced_orchestration
    type: ORCHESTRATION  # 🆕 新类型
    level: 4
    description: |
      For complex multi-step tasks, write Python scripts in E2B sandbox.
      
      Use cases:
      - Chained API calls (fetch city → get ID → get weather)
      - Large data processing (>100MB)
      - Custom algorithms
      
      Usage: Use e2b_sandbox or e2b_vibe_coding
    capabilities: [code_execution, api_calling, data_analysis]
```

### System Prompt 动态注入

```python
# prompts/universal_agent_prompt.py（增强版）

def get_tool_usage_guidance(
    task_type: str,
    selected_tools: List[str]
) -> str:
    """
    动态生成工具使用指导（Manus 启发）
    
    根据任务类型，推荐合适的工具层级
    """
    
    guidance = """
## 🔧 Tool Usage Strategy

You have access to tools at different abstraction levels. Choose wisely:

### Level 1: Direct Function Calls（优先使用）
- Use for: Single, well-defined operations
- Examples: `plan_todo.create_plan()`, `file_read()`, `web_search()`
- Advantage: Fast, schema-safe, immediate feedback

### Level 2: Shell Utilities（数据处理）
- Use for: Data manipulation, file operations, quick analysis
- Examples: `bash("jq '.results' data.json")`, `bash("grep 'error' logs.txt")`
- Advantage: Flexible, no schema constraints, great for large outputs

### Level 3: Python Scripts（复杂编排）
- Use for: Multi-step workflows, API orchestration, custom algorithms
- Examples: Write scripts in `e2b_sandbox` or use `e2b_vibe_coding`
- Advantage: Full programming power, can install packages

**🎯 Decision Rules**:
"""
    
    # 根据任务类型添加具体建议
    if task_type == "data_analysis":
        guidance += """
- For data inspection: Use bash + Shell utilities (Level 2)
  Example: `bash("head -20 data.csv | column -t -s,")`
  
- For complex analysis: Write Python script (Level 3)
  Example: Use `e2b_sandbox` to run pandas/numpy scripts
"""
    
    elif task_type == "content_generation":
        guidance += """
- For simple content: Use direct function calls (Level 1)
  Example: `slidespeak_render({...})`
  
- For complex generation: Use Python script + templating (Level 3)
  Example: Jinja2 template rendering in E2B sandbox
"""
    
    return guidance
```

---

## 🚀 Cache Optimization - 缓存优化

### Manus 的策略

> **"All layers still use standard function calls as proxy.  
> Clean interface, cache-friendly, orthogonal design."**

### Claude Prompt Caching 最佳实践

```python
# prompts/cache_optimized_prompt.py

def build_cache_optimized_system_prompt(
    capability_categories: List[Dict],
    selected_tools: List[Dict]
) -> List[Dict]:
    """
    构建 Cache 友好的 System Prompt
    
    策略（Manus 启发）：
    1. 稳定内容放在前面（高 cache hit）
    2. 动态内容放在后面（低 cache hit 影响小）
    3. 按优先级分组工具定义
    """
    
    system_blocks = []
    
    # ============================================================
    # Block 1: Core Principles（极其稳定，几乎不变）
    # ============================================================
    system_blocks.append({
        "type": "text",
        "text": """
You are ZenFlux Agent, a capable AI assistant that follows the RVR protocol.

Core Principles:
- Plan complex tasks using plan_todo tool
- Read plan state before each action
- Validate results after each tool call
- Write updates to memory after each step

（详细的核心原则，稳定不变）
""",
        "cache_control": {"type": "ephemeral"}  # 🔥 Claude Cache 标记
    })
    
    # ============================================================
    # Block 2: Capability Categories（相对稳定）
    # ============================================================
    categories_text = format_capability_categories(capability_categories)
    system_blocks.append({
        "type": "text",
        "text": f"""
## Available Capability Categories

{categories_text}

（能力分类说明，仅在添加新能力时改变）
""",
        "cache_control": {"type": "ephemeral"}
    })
    
    # ============================================================
    # Block 3: Core Tools（按优先级分组，相对稳定）
    # ============================================================
    core_tools = [t for t in selected_tools if t.get("level") == 1]
    core_tools_text = format_tools_for_prompt(core_tools)
    
    system_blocks.append({
        "type": "text",
        "text": f"""
## Core Tools (Always Available)

{core_tools_text}

（核心工具，很少改变）
""",
        "cache_control": {"type": "ephemeral"}
    })
    
    # ============================================================
    # Block 4: Contextual Tools（动态，不缓存）
    # ============================================================
    contextual_tools = [t for t in selected_tools if t.get("level") == 2]
    contextual_tools_text = format_tools_for_prompt(contextual_tools)
    
    system_blocks.append({
        "type": "text",
        "text": f"""
## Contextual Tools (For This Task)

{contextual_tools_text}

（动态选择的工具，每次可能不同，不缓存）
"""
        # 🚫 不添加 cache_control（动态内容）
    })
    
    return system_blocks
```

### Cache Hit Rate 监控

```python
# core/llm/cache_monitor.py

from dataclasses import dataclass
from typing import Dict, List


@dataclass
class CacheStats:
    """缓存统计"""
    total_requests: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    
    # Token 统计
    total_input_tokens: int = 0
    cached_input_tokens: int = 0
    
    @property
    def hit_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return self.cache_hits / self.total_requests
    
    @property
    def cache_efficiency(self) -> float:
        """缓存效率（节省的 token 比例）"""
        if self.total_input_tokens == 0:
            return 0.0
        return self.cached_input_tokens / self.total_input_tokens


class CacheMonitor:
    """缓存监控器"""
    
    def __init__(self):
        self.stats = CacheStats()
    
    def record_request(self, usage: Dict):
        """
        记录请求的缓存使用情况
        
        Args:
            usage: Claude API 返回的 usage 字段
        """
        self.stats.total_requests += 1
        
        input_tokens = usage.get("input_tokens", 0)
        cache_read_tokens = usage.get("cache_read_input_tokens", 0)
        cache_creation_tokens = usage.get("cache_creation_input_tokens", 0)
        
        self.stats.total_input_tokens += input_tokens
        self.stats.cached_input_tokens += cache_read_tokens
        
        if cache_read_tokens > 0:
            self.stats.cache_hits += 1
        else:
            self.stats.cache_misses += 1
        
        # 日志记录
        if cache_read_tokens > 0:
            logger.info(
                f"✅ Cache HIT: {cache_read_tokens} tokens cached "
                f"(saved ${cache_read_tokens * 0.00003:.4f})"  # 90% 折扣
            )
    
    def get_report(self) -> str:
        """生成缓存报告"""
        return f"""
📊 Cache Performance Report
━━━━━━━━━━━━━━━━━━━━━━━━
Total Requests: {self.stats.total_requests}
Cache Hit Rate: {self.stats.hit_rate:.1%}
Token Efficiency: {self.stats.cache_efficiency:.1%}

💰 Cost Savings:
- Total Input: {self.stats.total_input_tokens} tokens
- Cached: {self.stats.cached_input_tokens} tokens
- Saved: ${self.stats.cached_input_tokens * 0.00003 * 0.9:.2f}
"""
```

---

## 📋 实施路线图

### Phase 1: Context Reduction（2 weeks）

**Week 1: 结果精简器**
- [ ] 实现 `ResultCompactor` 核心逻辑
- [ ] 集成到 `ToolExecutor`
- [ ] 为 12 个现有工具定义精简规则

**Week 2: 测试与优化**
- [ ] 端到端测试（PPT 生成、数据分析）
- [ ] 测量 context 减少比例（目标：>50%）
- [ ] 性能基准测试

**成功指标**：
- ✅ Context 大小平均减少 50%+
- ✅ 工具调用准确率不下降
- ✅ LLM 能正确使用 `access_hint` 重新读取数据

---

### Phase 2: Context Isolation（1 week）

**Week 3: 显式消息传递**
- [ ] 移除 `SimpleAgent` 内部状态缓存
- [ ] 强制所有状态访问通过工具调用
- [ ] 更新 System Prompt（强调显式读写）

**成功指标**：
- ✅ 所有状态访问可追踪
- ✅ 支持多 Agent 协作（无状态冲突）
- ✅ Memory-First Protocol 100% 合规

---

### Phase 3: Context Offloading（2 weeks）

**Week 4: 分层工具架构**
- [ ] 在 `capabilities.yaml` 添加 `level` 字段
- [ ] 实现动态工具分层
- [ ] 更新 System Prompt（工具使用指导）

**Week 5: Sandbox Utilities 增强**
- [ ] 文档化 E2B 可用的 Shell 工具
- [ ] 提供 Python 脚本编排示例
- [ ] 训练 LLM 选择合适的层级

**成功指标**：
- ✅ Level 1 工具减少到 5 个以下
- ✅ LLM 能正确选择工具层级
- ✅ 复杂任务使用 Python 脚本编排

---

### Phase 4: Cache Optimization（1 week）

**Week 6: Cache 友好架构**
- [ ] 重构 System Prompt（分块 + cache_control）
- [ ] 实现 `CacheMonitor`
- [ ] 优化工具定义顺序（按稳定性）

**成功指标**：
- ✅ Cache hit rate > 80%
- ✅ Token 成本降低 50%+
- ✅ 响应速度提升（减少重复传输）

---

## 📊 预期收益

| 优化项 | 当前状态 | 目标状态 | 预期收益 |
|-------|---------|---------|---------|
| **Context 大小** | 平均 50KB/turn | 平均 20KB/turn | ↓ 60% |
| **Token 成本** | $0.05/turn | $0.02/turn | ↓ 60% |
| **响应延迟** | 3-5s | 1-2s | ↓ 50% |
| **Cache Hit Rate** | <20% | >80% | ↑ 300% |
| **工具选择准确率** | 85% | 95% | ↑ 11.8% |

**总体成本节省**：预计降低 **50-70%** 的 LLM 成本

---

## 🔗 参考资料

1. [Context Engineering for AI Agents - Manus](https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus)
2. [Claude Prompt Caching - Anthropic](https://docs.anthropic.com/claude/docs/prompt-caching)
3. [Go Concurrency Patterns](https://go.dev/blog/codelab-share)
4. [LangChain Context Engineering](https://twitter.com/rlancemartin/status/context-engineering)

---

## 附录：快速检查清单

### ✅ Context Reduction Checklist

- [ ] 工具结果大小 <10KB
- [ ] 大结果返回引用而非完整内容
- [ ] 提供 `access_hint` 指导 LLM 重新读取
- [ ] 监控 context 大小变化

### ✅ Context Isolation Checklist

- [ ] 无内部状态缓存（除 WorkingMemory）
- [ ] 所有状态访问通过工具调用
- [ ] Plan/Todo 读写显式可见
- [ ] 支持状态回溯和重放

### ✅ Context Offloading Checklist

- [ ] 核心工具 ≤5 个
- [ ] Shell utilities 文档化
- [ ] Python 脚本编排指南
- [ ] LLM 能选择合适层级

### ✅ Cache Optimization Checklist

- [ ] System Prompt 分块
- [ ] 稳定内容添加 cache_control
- [ ] 工具定义按优先级排序
- [ ] Cache hit rate >80%

