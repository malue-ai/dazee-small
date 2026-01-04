# Core Tool 模块

工具管理的核心模块，负责能力注册、路由选择、工具执行等功能。

## 📁 目录结构

```
core/tool/
├── README.md              # 本文档
├── __init__.py            # 模块导出
├── selector.py            # 工具选择器
├── executor.py            # 工具执行器
└── capability/            # 能力管理子包
    ├── __init__.py        # 子包导出
    ├── types.py           # 类型定义
    ├── registry.py        # 能力注册表
    ├── router.py          # 能力路由器
    ├── invocation.py      # 调用策略选择器
    └── skill_loader.py    # Skill 内容加载器
```

## 🧩 模块职责

### 1. `capability/` 子包 - 能力管理

#### `types.py` - 类型定义
```python
- CapabilityType      # 能力类型枚举 (SKILL/TOOL/MCP/CODE)
- CapabilitySubtype   # 能力子类型枚举
- Capability          # 统一能力数据类
```

#### `registry.py` - 能力注册表
```python
- CapabilityRegistry  # 统一管理所有能力
  - 从 config/capabilities.yaml 加载 Tools/MCP 配置
  - 自动扫描 skills/library/ 发现 Skills
  - 提供查询接口 (get, find_by_type, find_by_capability_tag)
  - 支持动态注册
```

#### `router.py` - 能力路由器
```python
- CapabilityRouter    # 智能选择最合适的能力
  - 基于关键词匹配、优先级、成本等因素评分
  - 返回最佳能力及备选方案
- extract_keywords()  # 从文本提取关键词
```

#### `invocation.py` - 调用策略选择器
```python
- InvocationSelector  # 根据任务特性选择调用方式
  - Direct Tool Call     # 标准工具调用
  - Code Execution       # 代码执行
  - Programmatic         # 程序化工具调用
  - Streaming            # 细粒度流式
  - Tool Search          # 工具搜索（>30个工具时）
```

#### `skill_loader.py` - Skill 内容加载器
```python
- SkillLoader         # 渐进式加载 Skill 内容
  - Level 1: 元数据（由 Registry 负责）
  - Level 2: SKILL.md 完整内容
  - Level 3: 资源文件
```

### 2. `selector.py` - 工具选择器

```python
- ToolSelector        # 根据能力需求选择具体工具
  - select()               # 根据能力标签选择工具
  - select_for_task_type() # 根据任务类型选择
  - get_tools_for_llm()    # 转换为 LLM API 格式
```

**核心功能**：将抽象的能力需求映射到具体的工具列表

```python
# 示例
selector = ToolSelector(registry)
result = selector.select(["web_search", "ppt_generation"])
# result.tool_names = ["plan_todo", "bash", "exa_search", "slidespeak_render", ...]
```

### 3. `executor.py` - 工具执行器

```python
- ToolExecutor        # 执行工具调用
  - 工具实例管理
  - 参数验证
  - 执行结果处理
```

## 🔄 模块关系

```
┌─────────────────────────────────────────────────────────────┐
│                        Agent                                 │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                     ToolSelector                             │
│  • 输入: 能力需求 ["web_search", "ppt_generation"]           │
│  • 输出: 工具列表 + Claude API 格式                          │
└─────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│CapabilityRegistry│  │CapabilityRouter │  │InvocationSelector│
│  • 能力存储      │  │  • 智能评分     │  │  • 调用策略     │
│  • Skills 发现   │  │  • 最佳推荐     │  │  • 批量/流式    │
└─────────────────┘  └─────────────────┘  └─────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────┐
│                     ToolExecutor                             │
│  • 工具实例化                                                │
│  • 参数处理                                                  │
│  • 执行调用                                                  │
└─────────────────────────────────────────────────────────────┘
```

## 📝 使用示例

### 基础用法

```python
from core.tool.capability import (
    CapabilityRegistry,
    CapabilityRouter,
    create_capability_registry
)
from core.tool.selector import ToolSelector

# 1. 创建 Registry（自动加载配置和扫描 Skills）
registry = create_capability_registry()

# 2. 创建 Selector
selector = ToolSelector(registry)

# 3. 根据能力需求选择工具
result = selector.select(
    required_capabilities=["web_search", "ppt_generation"],
    context={"available_apis": ["slidespeak"]}
)

print(result.tool_names)      # ["plan_todo", "bash", "exa_search", ...]
print(result.base_tools)      # ["plan_todo", "bash"]
print(result.dynamic_tools)   # ["exa_search", "slidespeak_render"]
```

### 加载 Skill 内容

```python
from core.tool.capability import SkillLoader

loader = SkillLoader()

# 获取 Skill 路径（从 Registry）
skill = registry.get("slidespeak-generator")
skill_path = skill.metadata.get('skill_path')

# 加载完整内容
content = loader.load_skill_content(skill_path)
resources = loader.load_skill_resources(skill_path)
scripts = loader.get_skill_scripts(skill_path)
```

## ⚠️ 迁移说明

以下模块已迁移到此目录，旧路径已废弃：

| 旧路径 | 新路径 | 状态 |
|--------|--------|------|
| `core/capability_registry.py` | `core/tool/capability/registry.py` | ✅ 可删除 |
| `core/capability_router.py` | `core/tool/capability/router.py` | ✅ 可删除 |
| `core/skills_manager.py` | `core/tool/capability/skill_loader.py` | ✅ 可删除 |
| `core/invocation_selector.py` | `core/tool/capability/invocation.py` | ✅ 可删除 |

**推荐导入方式**：

```python
# ✅ 推荐
from core.tool.capability import CapabilityRegistry, CapabilityRouter
from core.tool.selector import ToolSelector

# ❌ 已废弃（仍可用但会有警告）
from core.capability_registry import CapabilityRegistry
```

## 📚 相关文档

- `docs/CAPABILITY_REFACTOR_PLAN.md` - 能力重构计划
- `docs/v3/02-CAPABILITY-ROUTING.md` - 能力路由设计
- `config/capabilities.yaml` - 能力配置文件

