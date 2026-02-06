# Core Tool 模块

工具管理和执行的核心模块，提供统一的能力抽象、工具选择和执行。

## 架构概述

```
core/tool/
├── types.py              # 统一类型定义（Capability, ToolContext, BaseTool 等）
├── registry.py           # 统一注册表（CapabilityRegistry, InstanceRegistry）
├── selector.py           # 工具选择器（含路由和 Skill Fallback）
├── executor.py           # 工具执行器（含调用策略选择）
├── loader.py             # 工具加载器（便利层）
├── registry_config.py    # 配置加载器
├── validator.py          # 安全验证
├── llm_description.py    # LLM 描述生成
├── capability/           # 能力子包
│   └── skill_loader.py   # Skill 内容加载器
└── __init__.py           # 模块导出
```

## 核心概念

### 术语定义

| 术语 | 说明 | 示例 |
|-----|------|-----|
| **Capability** | 抽象能力描述（包含能力标签、优先级、约束等） | `ppt_generation` |
| **Tool** | 具体的可调用实现（`type=TOOL`） | `api_calling`, `exa_search` |
| **Skill** | Claude Skills 或本地工作流（`type=SKILL`） | `pptx`, `xlsx` |

### 工具分层

| 层级 | 说明 | 配置 |
|-----|------|-----|
| Level 1 | 核心工具，始终加载 | `level: 1` |
| Level 2 | 动态工具，按需加载 | `level: 2`（默认）|

## 快速开始

### 基本使用

```python
from core.tool import (
    get_capability_registry,
    ToolSelector,
    ToolExecutor,
    create_tool_context
)

# 1. 获取注册表（单例）
registry = get_capability_registry()
await registry.initialize()

# 2. 创建选择器和执行器
selector = ToolSelector(registry)
executor = ToolExecutor(registry)

# 3. 选择工具
result = selector.select(
    required_capabilities=["web_search", "ppt_generation"],
    context={"task_type": "content_generation"}
)

# 4. 执行工具
ctx = create_tool_context(session_id="xxx", user_id="user123")
result = await executor.execute("api_calling", {"url": "..."}, ctx)
```

### 智能路由

```python
# 智能推荐最佳能力
routing = selector.route(
    keywords=["PPT", "演示"],
    task_type="ppt_generation"
)
print(f"推荐: {routing.capability.name}, 评分: {routing.score}")
```

### 流式执行

```python
async for chunk in executor.execute_stream("api_calling", params):
    print(chunk)
```

### 调用策略选择

```python
strategy = executor.select_invocation_strategy(
    task_type="multi_tool",
    selected_tools=["tool1", "tool2", "tool3"]
)
# InvocationStrategy(type=PROGRAMMATIC, ...)
```

## 模块职责

### types.py

统一类型定义，合并自 `base.py` 和 `capability/types.py`：

| 类型 | 说明 |
|-----|------|
| `CapabilityType` | 能力类型枚举（SKILL/TOOL/MCP/CODE）|
| `CapabilitySubtype` | 子类型枚举（PREBUILT/CUSTOM/...）|
| `Capability` | 统一能力定义 |
| `ToolContext` | 工具执行上下文（显式依赖注入）|
| `ToolResult` | 标准化执行结果 |
| `BaseTool` | 工具基类 |
| `LegacyToolAdapter` | 旧工具适配器 |
| `InvocationType` | 调用方式枚举 |
| `InvocationStrategy` | 调用策略 |

### registry.py

统一注册表，合并自 `capability/registry.py` 和 `instance_registry.py`：

| 类 | 说明 |
|---|------|
| `CapabilityRegistry` | 全局能力注册表（单例）|
| `InstanceRegistry` | 实例级工具注册表（MCP/REST API）|

### selector.py

工具选择器，合并自 `selector.py`、`capability/router.py`、`unified_tool_caller.py`：

| 方法 | 说明 |
|-----|------|
| `select()` | 根据能力需求选择工具 |
| `select_for_task_type()` | 根据任务类型选择 |
| `resolve_capabilities()` | 三级优先级能力解析 |
| `route()` | 智能路由推荐（原 CapabilityRouter）|
| `route_multiple()` | 返回前 K 个最佳能力 |
| `ensure_skill_fallback()` | Skill fallback 处理（原 UnifiedToolCaller）|

### executor.py

工具执行器，合并自 `executor.py` 和 `capability/invocation.py`：

| 方法 | 说明 |
|-----|------|
| `execute()` | 执行工具 |
| `execute_stream()` | 流式执行 |
| `select_invocation_strategy()` | 选择调用策略（原 InvocationSelector）|
| `get_tools_config_for_strategy()` | 根据策略配置工具 |

## 配置文件

### capabilities.yaml

主配置文件，包含：

- `task_type_mappings`: 任务类型 → 能力映射
- `capability_categories`: 能力分类定义
- `tool_classification`: 工具分类（常用工具、类别展开）
- `capabilities`: 所有能力详细配置

## 设计原则

1. **LLM-First**: 关键词匹配仅作为辅助排序，最终决策交给 LLM
2. **显式依赖**: 通过 `ToolContext` 传递依赖，不使用反射魔法
3. **配置驱动**: 所有能力从 YAML 配置加载
4. **单一职责**: 每个模块职责清晰

## 功能特性

| 特性 | 支持 | 说明 |
|-----|------|-----|
| 流式输出 | ✅ | `executor.execute_stream()` |
| 并行调用 | ✅ | 在 Agent 层实现（`ToolExecutionMixin`）|
| 结果精简 | ✅ | `ResultCompactor` |
| Skill Fallback | ✅ | `selector.ensure_skill_fallback()` |
| 调用策略 | ✅ | Direct/Programmatic/Streaming |
