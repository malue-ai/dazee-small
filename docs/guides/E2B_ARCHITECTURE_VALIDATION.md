# E2B 集成架构验证文档

> **核心问题**: LLM 如何主动发现 E2B 工具？  
> **答案**: 通过能力抽象层 + 推理，而不是强制规则  

## 🎯 正确的架构设计（已实现）

### Plan 阶段：LLM 只看到能力分类

```python
# core/capability_registry.py - get_categories_for_prompt()

## 🏷️ Available Capability Categories

When creating a plan, specify which capability each step needs:

| Category | Description | Use When |
|----------|-------------|----------|
| `web_search` | 搜索互联网信息 | 需要查找资料、新闻、数据 |
| `code_sandbox` | 在安全沙箱中执行Python代码 | 需要网络访问、第三方包、文件持久化 | ← 🆕
| `code_execution` | 执行代码和脚本 | 需要运行Python/Bash脚本、计算逻辑 |
| `ppt_generation` | 生成演示文稿 | 需要创建 PowerPoint/Slides |
| ...

⚠️ **Important**: Only specify capability categories, NOT specific tool names.
The Router will automatically select the best tools for each capability.
                 ↑ 关键提示：不要指定工具名
```

**LLM 在 Plan 阶段的视角**：
- ✅ **知道**：有8个能力分类（code_sandbox, web_search等）
- ✅ **知道**：每个能力的描述和使用场景
- ❌ **不知道**：具体有哪些工具（e2b_python_sandbox, slidespeak等）

### 推理示例（Extended Thinking）

```
用户输入: "爬取 Hacker News 并分析数据"

<thinking>
分析任务需求：
1. 需要爬取网页 → 需要 requests 库
2. 需要解析 HTML → 需要 beautifulsoup4
3. 需要分析数据 → 需要 pandas

检查可用能力：
- code_execution: 不支持网络和第三方包 ❌
- code_sandbox: 支持网络、第三方包、文件持久化 ✅

决策：使用 code_sandbox 能力
</thinking>

Plan:
{
  "goal": "爬取并分析HN数据",
  "steps": [
    {
      "action": "爬取网页数据",
      "capability": "code_sandbox"  ← 只标记能力，不指定工具
    },
    {
      "action": "分析数据",
      "capability": "code_sandbox"
    }
  ],
  "required_capabilities": ["code_sandbox"]
}
```

### Router 阶段：能力 → 工具映射

```python
# core/capability_router.py - select_tools_for_capabilities()

输入: required_capabilities = ["code_sandbox"]

查询 capabilities.yaml:
  code_sandbox → 哪些工具声明了这个能力？
  
结果:
  - e2b_python_sandbox (priority: 85, 支持网络/包/文件)  ✅
  - code_execution (priority: 40, 不支持网络)  ✅
  
筛选后传给 LLM:
  [e2b_python_sandbox, code_execution, bash, ...]
```

### 执行阶段：LLM 选择具体工具

```python
LLM 看到:
  - e2b_python_sandbox: 
      description: "支持网络访问、任意第三方包、文件持久化"
      preferred_for: ["网络请求", "数据爬取", "数据分析"]
  
  - code_execution:
      description: "执行代码"
      preferred_for: ["配置生成", "简单计算"]

LLM 推理:
  "需要 requests 库...e2b_python_sandbox 更合适"

LLM 调用:
  e2b_python_sandbox({
    "code": "import requests\nfrom bs4 import BeautifulSoup\n..."
  })
```

---

## ✅ 架构验证清单

### 1. 能力抽象层

| 验证项 | 实现位置 | 状态 |
|-------|---------|------|
| 能力分类定义 | `config/capabilities.yaml` - capability_categories | ✅ code_sandbox 已添加 |
| 动态生成 Prompt | `core/capability_registry.py` - get_categories_for_prompt() | ✅ 已实现 |
| 注入到 System Prompt | `core/agent.py` - _build_system_prompt() | ✅ 已集成 |
| 不显示工具名 | System Prompt 提示 | ✅ "Only specify categories" |

### 2. Router 映射

| 验证项 | 实现位置 | 状态 |
|-------|---------|------|
| 能力 → 工具映射 | `config/capabilities.yaml` - capabilities字段 | ✅ e2b声明了code_sandbox |
| 动态筛选 | `core/capability_router.py` - select_tools_for_capabilities() | ✅ 已实现 |
| 优先级排序 | Router 逻辑 | ✅ priority: 85 |

### 3. LLM 自主决策

| 验证项 | 实现方式 | 状态 |
|-------|---------|------|
| Plan 阶段推理 | Extended Thinking | ✅ Sonnet 4.5支持 |
| 能力选择 | capability 字段（可选） | ✅ 不强制 |
| 工具选择 | 执行阶段自主选择 | ✅ LLM 推理 |

---

## 🎯 关键设计点回顾

### 问题 1: LLM 在 Plan 阶段需要知道什么？

**✅ 正确答案（已实现）**：
- 知道：有哪些**能力分类**（code_sandbox, web_search等）
- 知道：每个能力的**使用场景**
- 不知道：具体有哪些**工具名**

**代码实现**：
```python
# core/agent.py - _build_system_prompt()
capability_categories = self.capability_registry.get_categories_for_prompt()
# → 生成能力分类表格（不包含工具名）

return f"{base_prompt}\n\n{capability_categories}\n\n{skills_metadata}"
```

### 问题 2: LLM 如何主动发现 E2B？

**✅ 正确答案（已实现）**：
1. **Plan 阶段**：通过 Extended Thinking 推理需要哪些能力
2. **Router 阶段**：根据能力自动筛选工具
3. **执行阶段**：LLM 看到具体工具并选择

**不是通过强制规则**（如 IF task==爬虫 THEN use E2B）

### 问题 3: capability 字段是必需的吗？

**✅ 正确答案（已实现）**：
- **可选**：LLM 可以标注 capability（推荐，优化性能）
- **也可以不标注**：Router 会通过 task_type 推断
- **最灵活**：LLM 直接调用工具，Router 兜底

**代码实现**：
```python
# core/agent.py - chat()
if plan:
    required_capabilities = plan.get('required_capabilities', [])
    if not required_capabilities:  # 🔑 如果 Plan 中没有，自动推断
        required_capabilities = list(set([
            step.get('capability', '') 
            for step in plan.get('steps', [])
        ]))

if not required_capabilities:  # 🔑 兜底：从 task_type 推断
    required_capabilities = self._infer_capabilities_from_task_type(
        intent_analysis['task_type']
    )
```

---

## 📊 E2B 在架构中的位置

```
Plan 阶段（Sonnet Extended Thinking）
    ↓
LLM 推理："需要网络访问和 pandas...应该是 code_sandbox 能力"
    ↓
Plan输出: {"capability": "code_sandbox"}  ← 只知道抽象能力
    ↓
    ↓
Router 阶段（能力映射）
    ↓
查询 capabilities.yaml:
  code_sandbox → [e2b_python_sandbox (85), code_execution (40)]
    ↓
筛选: [e2b_python_sandbox, code_execution, bash]  ← 传给LLM
    ↓
    ↓
执行阶段（LLM 选择）
    ↓
LLM 看到工具列表和描述
    ↓
LLM 推理："需要 requests...e2b_python_sandbox 支持网络"
    ↓
调用: e2b_python_sandbox({"code": "..."})  ← 最终选择
```

---

## ✅ 架构完全符合 V3.7 原则

| 原则 | 实现验证 | 状态 |
|-----|---------|------|
| **Prompt-Driven** | 逻辑在 System Prompt，不在代码 | ✅ |
| **能力抽象** | LLM 只知道 code_sandbox，不知道 E2B | ✅ |
| **配置驱动** | 所有定义在 YAML，单一数据源 | ✅ |
| **LLM 自主决策** | 通过推理选择，不是规则强制 | ✅ |
| **Memory-First** | 状态持久化在 WorkingMemory | ✅ |
| **动态路由** | Router 根据 capability 筛选 | ✅ |

---

## 🎉 总结

**您的问题**：
> "在 Plan 阶段，要知道我们有什么能力（不用知道具体工具叫什么），需要什么？"

**答案**：
✅ **已正确实现**！

**Plan 阶段 LLM 看到的**：
```markdown
## 🏷️ Available Capability Categories

| Category | Description | Use When |
|----------|-------------|----------|
| code_sandbox | 在安全沙箱中执行Python代码 | 需要网络访问、第三方包 |
| code_execution | 执行代码和脚本 | 需要运行Python/Bash脚本 |
| ...

⚠️ Important: Only specify capability categories, NOT specific tool names.
```

**LLM 推理流程**：
1. 分析任务 → "需要 pandas 和网络"
2. 查看能力列表 → "code_sandbox 支持第三方包"
3. 标记 Plan → `"capability": "code_sandbox"`
4. Router 自动映射 → e2b_python_sandbox
5. LLM 执行时选择 → 调用 e2b_python_sandbox

**不需要 LLM 知道**：
- ❌ e2b_python_sandbox 这个工具存在
- ❌ E2B 是什么
- ❌ 如何创建沙箱

**Router 负责**：
- ✅ 能力 → 工具的映射
- ✅ 工具筛选和排序
- ✅ 传递给 LLM

---

**现在万事俱备！只需添加 E2B_API_KEY 即可测试！** 🚀

