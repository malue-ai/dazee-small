# ZenFlux Agent V4 架构总览

> 📅 **最后更新**: 2026-01-08  
> 🎯 **当前版本**: V4.6 - 智能记忆检索决策（Intent-Driven Memory Retrieval）  
> 🔗 **前版本**: [V3.7 架构](./ARCHITECTURE_V3.7_E2B.md)
> ✅ **优化状态**: Schema 驱动 + Context Reduction + **工具分层** + Code-First 编排 + E2E 追踪 + Re-Plan + 统一能力注册 + **长时运行支持** + **Skills/Tools 分层调用** + **Mem0用户画像** + **🆕 智能记忆检索**
> 📊 **文档特点**: 参考 V3.7 风格的详细架构图 + 完整 7 阶段用户流程管道图

---

## 📋 目录

- [版本演进](#版本演进)
- [核心理念](#核心理念)
- [整体架构](#整体架构)
- [模块详解](#模块详解)
  - [PlanMemory 详解（V4.3）](#41-planmemory-详解v43)
  - [Mem0 用户画像详解（V4.5）](#42-mem0-用户画像详解v45)
  - [🆕 智能记忆检索决策（V4.6）](#43-智能记忆检索决策v46)
- [数据流](#数据流)
- [文件结构](#文件结构)

---

## 🚀 版本演进

### V4.5 → V4.6 核心变化（🆕 智能记忆检索决策）

| 维度 | V4.5 | V4.6 | 改进 |
|------|------|------|------|
| **记忆检索** | 每次请求都检索 | ✅ 按需检索 | 基于意图分析决定是否检索Mem0 |
| **决策方式** | 硬编码规则 | ✅ Few-shot推理 | LLM自主推理，可扩展无需改代码 |
| **性能优化** | 无 | ✅ 跳过冗余检索 | 通用查询（天气/百科）不检索，节省~200ms |
| **Token成本** | 固定开销 | ✅ 动态优化 | 非个性化场景减少Embedding调用 |

**核心理念**（参考 [Mem0 论文](https://arxiv.org/abs/2504.19413) 的 Selective Memory）：
- **按需检索**：不是每次请求都需要用户记忆。"今天天气怎么样？"这类通用查询不需要个性化
- **LLM自主推理**：通过 Few-shot 示例引导 Haiku 在意图识别阶段判断 `skip_memory_retrieval`
- **可扩展性**：新增场景只需添加 Few-shot 示例，无需修改代码逻辑
- **默认安全**：不确定时默认检索（`skip_memory_retrieval=false`），宁可多检索也不漏掉个性化

**实现细节**：
```
Phase 2: Intent Analysis (Haiku)
├── task_type, complexity, needs_plan  # 原有字段
└── skip_memory_retrieval              # 🆕 V4.6 新增
    ├── true: 跳过Mem0检索（天气/百科/汇率等通用查询）
    └── false: 执行Mem0检索（PPT生成/代码编写/推荐等个性化场景）

Phase 4: System Prompt Assembly
├── if skip_memory_retrieval == true:
│   └── 直接使用基础Prompt，不调用Mem0
└── else:
    └── _fetch_user_profile() → 注入用户画像
```

**Few-shot 示例**（位于 `prompts/intent_recognition_prompt.py`）：

| 查询 | skip_memory_retrieval | 理由 |
|------|----------------------|------|
| "今天上海天气怎么样？" | true | 实时信息查询，与用户历史无关 |
| "帮我生成一个产品介绍PPT" | false | 用户可能有PPT风格偏好 |
| "Python的列表推导式怎么用？" | true | 通用技术问题，无需个性化 |
| "帮我推荐一家餐厅" | false | 需要了解用户口味偏好 |
| "把这段话翻译成英文" | true | 简单翻译任务，无需个性化 |
| "帮我写一段Python代码" | false | 用户可能有编码风格偏好 |

**🆕 Mem0 增量更新整合**（位于 `utils/background_tasks.py`）：

V4.6 将 Mem0 异步更新功能整合到 `BackgroundTaskService`，遵循"不重复造轮子"原则：

| 维度 | Before (V4.5) | After (V4.6) |
|------|---------------|--------------|
| **服务架构** | 独立 `mem0_update_service.py` | 整合到 `BackgroundTaskService` |
| **懒加载** | 独立实现 | 复用 `_get_mem0_pool()` |
| **静默失败** | 独立实现 | 复用统一机制 |
| **单例模式** | 独立 `get_mem0_update_service()` | 复用 `get_background_task_service()` |
| **SSE推送** | 独立实现 | 复用 `EventManager` |
| **并发控制** | 独立实现 | 统一 `asyncio.Semaphore` |

```python
# 新增数据类
@dataclass
class Mem0UpdateResult:
    user_id: str
    success: bool
    memories_added: int = 0
    conversations_processed: int = 0

@dataclass
class Mem0BatchUpdateResult:
    total_users: int
    successful: int
    failed: int
    total_memories_added: int = 0
    results: List[Mem0UpdateResult]
```

### V4.4 → V4.5 核心变化（Mem0 用户画像层）

| 维度 | V4.4 | V4.5 | 改进 |
|------|------|------|------|
| **用户记忆** | PlanMemory（任务级） | ✅ Mem0（用户级） | 跨Session用户画像与偏好记忆 |
| **个性化** | 无 | ✅ 自动个性化 | 基于历史交互提供个性化响应 |
| **向量数据库** | 无 | ✅ 多数据库支持 | Qdrant、腾讯云VectorDB |
| **LLM支持** | Claude | ✅ 多LLM支持 | OpenAI、Anthropic、Ollama |
| **Agent透明** | - | ✅ 完全透明 | Prompt模块封装，Agent无需感知 |
| **API层** | 无 | ✅ 异步批量更新 | REST API支持批量记忆更新 |
| **后台任务** | 独立服务 | ✅ 复用统一机制 | 🆕 整合到BackgroundTaskService（V4.6）|

**设计理念**：
- **用户画像自动注入**：框架在Phase 4自动从Mem0获取用户画像并注入System Prompt
- **Agent完全透明**：`simple_agent.py`只传递`user_id`和`user_query`，无需关心Mem0逻辑
- **多向量数据库**：支持Qdrant、腾讯云VectorDB，易于扩展其他向量数据库
- **异步批量更新**：🆕 复用 `BackgroundTaskService` 统一后台任务机制，支持凌晨批量更新

**参考来源**：
- [Mem0 官方文档](https://docs.mem0.ai/)
- [Mem0 GitHub](https://github.com/mem0ai/mem0)
- [Mem0 论文: Building Production-Ready AI Agents with Scalable Long-Term Memory](https://arxiv.org/abs/2504.19413)

### V4.3 → V4.4 核心变化（Skills + Tools 整合）

| 维度 | V4.3 | V4.4 | 改进 |
|------|------|------|------|
| **能力分层** | Skills/Tools 混合 | ✅ 明确分层 | Claude Skills (container.skills) vs Tools (DIRECT) |
| **E2B 定位** | 未明确 | ✅ 作为 Tool | E2B 是 DIRECT tool_use，Claude 自主推理调用 |
| **InvocationSelector** | 预留未集成 | ✅ 条件激活 | 无匹配 Skill 时启用，选择调用模式 |
| **调用路径** | 单一路径 | ✅ 双路径分流 | Skill 路径 vs Tool 路径 |

**参考来源**：
- [Anthropic Blog: Advanced Tool Use](https://www.anthropic.com/engineering/advanced-tool-use)
- [Claude Skills and MCP](https://claude.com/blog/extending-claude-capabilities-with-skills-mcp-servers)

### V4.2.4 → V4.3 核心变化（Plan 持久化 + Session 恢复）

| 维度 | V4.2.4 | V4.3 | 改进 |
|------|--------|------|------|
| **Plan 持久化** | 会话级丢失 | ✅ 跨 Session 持久化 | PlanMemory 支持任务恢复 |
| **Session 恢复** | 无 | ✅ 自动恢复协议 | 动态注入恢复 Prompt |
| **复杂度检测** | 无 | ✅ 自动检测 | IntentAnalyzer 判断 needs_persistence |
| **用户透明** | 手动区分 Prompt | 框架自动处理 | 运营人员无需感知 Session 类型 |

**参考来源**：
- [Anthropic Blog: Effective harnesses for long-running agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)
- Claude 官方 `autonomous-coding` 示例的 Two-Agent Pattern

### V4.2.3 → V4.2.4 核心变化（工具分层选择）

| 维度 | V4.2.3 | V4.2.4 | 改进 |
|------|--------|--------|------|
| **工具分层** | 配置存在未实现 | ✅ 完整实现 | Level 1/2 分层选择生效 |
| **核心工具** | 硬编码列表 | 配置驱动 | 从 capabilities.yaml 读取 level=1 |
| **缓存支持** | 配置存在未解析 | ✅ cache_stable 解析 | 支持 Prompt Cache 优化 |
| **类型定义** | 缺少字段 | Capability 添加字段 | level + cache_stable |

### V4.2.1 → V4.2.2 核心变化（Re-Plan 自适应重规划）

| 维度 | V4.2.1 | V4.2.2 | 改进 |
|------|--------|--------|------|
| **计划执行** | 固定计划 | 自适应重规划 | ✅ Claude 自主决定是否 replan |
| **失败处理** | 手动重试 | 智能重规划 | ✅ 保留已完成步骤，重新生成剩余 |
| **工具封装** | Agent 管理 | 工具内部闭环 | ✅ plan_todo 内置 Claude + Extended Thinking |
| **Schema 配置** | 基础配置 | Re-Plan 配置 | ✅ replan_enabled/max_attempts/strategy |

### V4.2 → V4.2.1 核心变化（Code-First + E2E Pipeline）

| 维度 | V4.2 | V4.2.1 | 改进 |
|------|------|------|------|
| **代码编排** | LLM 自由生成 | Code-First 编排器 | ✅ 结构化代码生成与验证 |
| **代码验证** | 无 | `CodeValidator` | ✅ 语法/依赖/安全自动验证 |
| **执行追踪** | 分散日志 | `E2EPipelineTracer` | ✅ 全链路可观测 |
| **E2B 集成** | 工具调用 | CodeOrchestrator | ✅ 代码生成-验证-执行闭环 |

### V4.1 → V4.2 核心变化

| 维度 | V4.1 | V4.2 | 改进 |
|------|------|------|------|
| **工具选择** | Intent 推断 | Schema 驱动优先 | ✅ 优先使用 Schema 配置 |
| **选择优先级** | Plan > Intent | Schema > Plan > Intent | ✅ 符合 Prompt 驱动设计 |

### V4.0 → V4.1 核心变化

| 维度 | V4.0 | V4.1 | 改进 |
|------|------|------|------|
| **Result Compaction** | 无 | `ResultCompactor` | ✅ 搜索结果减少 76.6% |
| **状态管理** | `plan_state` | `_plan_cache` | ✅ 明确是缓存非隐式状态 |
| **工具分层** | 无 | `level` + `cache_stable` | ✅ 支持工具分层加载 |
| **Cache 监控** | 无 | 实时日志 | ✅ 显示 Cache HIT/节省 |
| **配置驱动** | 部分 | 完全 YAML | ✅ 精简规则自动加载 |

### V3.7 → V4.0 核心变化

| 维度 | V3.7 | V4.0 | 改进 |
|------|------|------|------|
| **Agent** | 单文件 `agent.py` (1000+行) | `core/agent/` 模块化 | ✅ 拆分为 3 个独立文件 |
| **Context** | 分散在 Agent 内部 | `core/context/` 独立模块 | ✅ Runtime + Conversation 分离 |
| **Tool** | `tools/executor.py` | `core/tool/` 独立模块 | ✅ Selector + Executor 解耦 |
| **Memory** | 单文件 `memory.py` | `core/memory/` 层级化 | ✅ user/ + system/ 分层 |
| **LLM** | `llm_service.py` | `core/llm/` 多提供商 | ✅ Claude/OpenAI/Gemini |
| **Events** | 分散的事件发射 | `core/events/` 统一管理 | ✅ 6 类事件统一接口 |

### 🎯 V4.5 优化重点（🆕 Mem0 用户画像层）

1. **Mem0 集成** - 基于Mem0框架的用户记忆层，支持跨Session用户画像
2. **多向量数据库** - 支持Qdrant、腾讯云VectorDB，统一VectorStoreBase接口
3. **腾讯云VectorDB适配器** - 完整适配腾讯云SDK，支持CRUD和语义搜索
4. **Agent透明设计** - Prompt模块封装Mem0逻辑，Agent无需修改代码
5. **异步批量更新API** - REST API支持后台批量更新用户记忆

### 🎯 V4.4 优化重点（Skills + Tools 整合）

1. **能力分层清晰化** - Claude Skills (SKILL.md + container.skills) vs Tools (DIRECT tool_use)
2. **E2B 明确定位** - E2B 是 Tool，通过 DIRECT tool_use 调用，Claude 自主推理选择
3. **InvocationSelector 条件激活** - 仅在无匹配 Skill 时启用，选择 DIRECT/PROGRAMMATIC/TOOL_SEARCH
4. **双路径分流** - SimpleAgent 实现 Skill 路径 vs Tool 路径分流逻辑

### 🎯 V4.3 优化重点（Plan 持久化 + Session 恢复）

1. **PlanMemory** - 新增用户级记忆，跨 Session 持久化任务计划
2. **自动复杂度检测** - IntentAnalyzer 自动判断 `needs_persistence`
3. **动态 Prompt 注入** - 框架自动注入恢复协议，用户无需编写特殊 Prompt
4. **借鉴 autonomous-coding** - 参考 Claude 官方示例的 Two-Agent Pattern

### 🎯 V4.2.2 优化重点（Re-Plan 自适应重规划）

1. **Re-Plan 机制** - Claude 自主决定是否调用 replan，无需 Agent 硬规则
2. **工具封装闭环** - plan_todo 内部调用 Claude + Extended Thinking 生成计划
3. **增量/全量策略** - incremental 保留已完成步骤，full 全量重新生成
4. **失败阈值控制** - failure_threshold 配置触发重规划的失败率阈值

### 🎯 V4.2.1 优化重点（Code-First + E2E Pipeline）

1. **Code-First 编排** - 参考先进 Agent 架构，代码先行策略
2. **E2E Pipeline 追踪** - 全链路可观测，每阶段输入-处理-输出
3. **代码验证闭环** - 语法检查→依赖检查→安全检查→执行
4. **CodeOrchestrator** - 统一代码生成-验证-执行流程

### 🎯 V4.2 优化重点

1. **Schema 驱动** - 工具选择优先使用 Schema 配置
2. **Context Reduction** - 工具结果精简，减少 70%+ Context
3. **配置驱动** - 精简规则在 YAML 中配置，自动生效
4. **Cache 友好** - 工具分层 + 稳定性标记

### 🎯 V4.0 设计目标

1. **模块化** - 每个模块单一职责，可独立测试
2. **层级化** - 清晰的依赖方向，避免循环依赖
3. **可扩展** - 新功能通过配置添加，不修改核心代码
4. **可观测** - 统一事件系统，完整的执行追踪

### ✨ V4.5 核心成就（🆕 Mem0 用户画像层）

|| 改进项 | 实现状态 | 具体成果 |
||-------|---------|---------|
|| **Mem0 核心模块** | ✅ 完成 | `core/memory/mem0/` - config/pool/formatter/tencent_vectordb |
|| **向量数据库支持** | ✅ 完成 | Qdrant + 腾讯云VectorDB，统一VectorStoreBase接口 |
|| **腾讯云适配器** | ✅ 完成 | `tencent_vectordb.py` - 完整CRUD + 语义搜索 |
|| **Prompt自动注入** | ✅ 完成 | `universal_agent_prompt.py` - 自动获取并注入用户画像 |
|| **Agent透明集成** | ✅ 完成 | `simple_agent.py` Phase 4 - 只传user_id/query |
|| **异步更新服务** | ✅ 完成 | `utils/background_tasks.py`（🆕 V4.6整合）+ `mem0_router.py` - 批量更新API |
|| **配置管理** | ✅ 完成 | `env.template` - 多LLM/Embedding/VectorDB配置 |
|| **文档完善** | ✅ 完成 | 设置指南 + Embedding选择指南 + E2E测试脚本 |

### ✨ V4.4 核心成就（Skills + Tools 整合）

| 改进项 | 实现状态 | 具体成果 |
|-------|---------|---------|
| **架构文档 V4.4 章节** | ✅ 完成 | Claude Skills vs Tools 关系图 + E2B 定位说明 |
| **E2B 明确定位** | ✅ 完成 | 文档明确 E2B 通过 DIRECT tool_use 调用 |
| **InvocationSelector 激活** | ✅ 完成 | 添加 Skill 跳过逻辑，无 Skill 时生效 |
| **SimpleAgent 分流** | ✅ 完成 | Skill 路径 vs Tool 路径分流逻辑 |
| **capabilities.yaml 标注** | ✅ 完成 | 添加 invocation_hint 字段 |
| **术语修正** | ✅ 完成 | 修正"7级优先级表"为"决策树+选择矩阵" |

### ✨ V4.3 核心成就（Plan 持久化 + Session 恢复）

| 改进项 | 实现状态 | 具体成果 |
|-------|---------|---------|
| **PlanMemory 类** | ✅ 完成 | core/memory/user/plan.py - 跨 Session 任务持久化 |
| **MemoryManager 集成** | ✅ 完成 | 懒加载 plan 属性，统一入口访问 |
| **plan_todo 自动持久化** | ✅ 完成 | create_plan/update_step 自动调用 PlanMemory |
| **IntentAnalyzer.needs_persistence** | ✅ 完成 | 自动检测任务复杂度决定是否持久化 |
| **动态恢复协议注入** | ✅ 完成 | universal_agent_prompt.py 自动注入进度摘要 |
| **用户完全透明** | ✅ 完成 | 运营人员无需编写特殊 Session 类型 Prompt |

### ✨ V4.2.4 核心成就（工具分层选择）

| 改进项 | 实现状态 | 具体成果 |
|-------|---------|---------|
| **Capability.level 字段** | ✅ 完成 | types.py 添加 level: int = 2 |
| **Capability.cache_stable 字段** | ✅ 完成 | types.py 添加 cache_stable: bool = False |
| **Registry 解析 level** | ✅ 完成 | _parse_capability() 解析分层配置 |
| **Registry 分层查询** | ✅ 完成 | get_core_tools() / get_dynamic_tools() / get_cacheable_tools() |
| **Selector 分层选择** | ✅ 完成 | 优先加载 Level 1，按需选择 Level 2 |

### ✨ V4.2.3 核心成就（统一能力注册）

| 改进项 | 实现状态 | 具体成果 |
|-------|---------|---------|
| **capabilities.yaml 唯一真相来源** | ✅ 完成 | Tools/Skills/MCP/API 统一配置，包含 skill_id |
| **skill_cli.py** | ✅ 完成 | CLI 工具：register/unregister/list/update/sync |
| **自动回写 skill_id** | ✅ 完成 | 注册后 skill_id 自动写入 capabilities.yaml |
| **Plan 阶段统一发现** | ✅ 完成 | 从 capabilities.yaml 读取已注册 Skills |
| **运行时只读** | ✅ 完成 | 不做任何注册操作，直接使用配置 |
| **升级到 Haiku 4.5** | ✅ 完成 | IntentAnalyzer 升级到 claude-haiku-4-5-20251001（64K tokens） |

### ✨ V4.2.2 核心成就（Re-Plan 自适应重规划）

| 改进项 | 实现状态 | 具体成果 |
|-------|---------|---------|
| **PlanManagerConfig 扩展** | ✅ 完成 | replan_enabled/max_replan_attempts/replan_strategy/failure_threshold |
| **plan_todo.replan 操作** | ✅ 完成 | 增量(incremental)/全量(full)两种重规划策略 |
| **工具封装闭环** | ✅ 完成 | plan_todo 内部调用 Claude + Extended Thinking |
| **capabilities.yaml 更新** | ✅ 完成 | plan_todo 新增 replan/adaptive_planning 能力 |
| **Re-Plan 测试脚本** | ✅ 完成 | `scripts/test_replan.py` |

### ✨ V4.2.1 核心成就（Code-First + E2E Pipeline）

| 改进项 | 实现状态 | 具体成果 |
|-------|---------|---------|
| **E2EPipelineTracer** | ✅ 完成 | 全链路追踪，输入-处理-输出可视化 |
| **CodeValidator** | ✅ 完成 | 语法/依赖/安全多级验证 |
| **CodeOrchestrator** | ✅ 完成 | 代码生成-验证-执行编排器 |
| **SimpleAgent 集成** | ✅ 完成 | chat() 自动追踪各阶段 |
| **E2E 验证脚本** | ✅ 完成 | `scripts/e2e_code_first_verify.py` |

### ✨ V4.2 核心成就

| 改进项 | 实现状态 | 具体成果 |
|-------|---------|---------|
| **Schema 驱动工具选择** | ✅ 完成 | 优先级：Schema > Plan > Intent |
| **ResultCompactor** | ✅ 完成 | 搜索结果 Context 减少 76.6% |
| **配置驱动精简** | ✅ 完成 | 精简规则在 YAML 中配置 |
| **工具分层** | ✅ 完成 | Level 1/2/3 + cache_stable |
| **状态缓存标记** | ✅ 完成 | `_plan_cache` 明确语义 |

### ✨ V4.0 核心成就

| 改进项 | 实现状态 | 具体成果 |
|-------|---------|---------|
| **Agent 模块化** | ✅ 完成 | 从 1000+ 行拆分为 3 个独立文件 |
| **Context 独立** | ✅ 完成 | Runtime + Conversation 分离 |
| **Tool 层重构** | ✅ 完成 | Selector + Executor + Capability 解耦 |
| **Capability 子包** | ✅ 完成 | Registry/Router/Invocation/SkillLoader 统一管理 |
| **Memory 层级化** | ✅ 完成 | user/ + system/ 分层 |
| **Event 统一** | ✅ 完成 | 6 类事件统一接口 |
| **LLM 多提供商** | ✅ 完成 | Claude/OpenAI/Gemini 支持 |

**关键突破**：
- 🎯 **单一职责原则**：每个模块职责明确，不再有"上帝类"
- 🎯 **依赖注入**：所有依赖通过构造函数注入，易于测试
- 🎯 **配置驱动**：能力定义在 YAML，代码只负责执行
- 🎯 **类型安全**：完整的类型定义和接口规范
- 🎯 **Context Engineering**：基于先进上下文管理原则优化

---

## 🎯 核心理念

### 1. 编排模式（Orchestrator Pattern）

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│   SimpleAgent = 编排者（Orchestrator）                          │
│   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│   • 协调各模块工作                                              │
│   • 不包含业务逻辑                                              │
│   • 不直接调用 LLM                                              │
│                                                                 │
│   独立模块 = 专家（Specialists）                                │
│   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│   • IntentAnalyzer  → 意图分析专家                              │
│   • ToolSelector    → 工具选择专家                              │
│   • ToolExecutor    → 工具执行专家                              │
│   • EventManager    → 事件管理专家                              │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 2. 分层架构（Layered Architecture）

```
┌─────────────────────────────────────────────────────────────────┐
│                      API Layer (FastAPI)                        │
│   routers/chat.py, routers/session.py, routers/health.py       │
└───────────────────────────────┬─────────────────────────────────┘
                                │
┌───────────────────────────────▼─────────────────────────────────┐
│                     Service Layer                               │
│   services/chat_service.py, services/session_service.py        │
└───────────────────────────────┬─────────────────────────────────┘
                                │
┌───────────────────────────────▼─────────────────────────────────┐
│                      Core Layer                                 │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │
│  │ core/agent/ │  │ core/tool/  │  │core/memory/ │             │
│  └─────────────┘  └─────────────┘  └─────────────┘             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │
│  │ core/llm/   │  │core/events/ │  │core/context/│             │
│  └─────────────┘  └─────────────┘  └─────────────┘             │
└───────────────────────────────┬─────────────────────────────────┘
                                │
┌───────────────────────────────▼─────────────────────────────────┐
│                   Infrastructure Layer                          │
│   models/ (SQLAlchemy), config/ (YAML), tools/ (实现)          │
└─────────────────────────────────────────────────────────────────┘
```

### 3. 依赖方向（Dependency Direction）

```
                    ┌─────────────────┐
                    │   SimpleAgent   │
                    └────────┬────────┘
                             │ depends on
        ┌────────────────────┼────────────────────┐
        │                    │                    │
        ▼                    ▼                    ▼
┌───────────────┐    ┌───────────────┐    ┌───────────────┐
│IntentAnalyzer │    │ ToolSelector  │    │ ToolExecutor  │
└───────┬───────┘    └───────┬───────┘    └───────┬───────┘
        │                    │                    │
        │              depends on                 │
        │                    │                    │
        │                    ▼                    │
        │         ┌─────────────────────┐         │
        └────────►│CapabilityRegistry  │◄────────┘
                  └─────────────────────┘
                             │
                             ▼
                  ┌─────────────────────┐
                  │  capabilities.yaml  │
                  └─────────────────────┘
```

---

## 🏗️ 整体架构

### V4.4 架构图（详细版）

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                                 User Query                                       │
│                           "帮我生成一个产品PPT"                                   │
└─────────────────────────────────────┬───────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              API Layer (FastAPI)                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐        │
│  │ POST /chat   │  │GET /sessions │  │ POST /confirm│  │ GET /health  │        │
│  │   (主入口)   │  │  (会话管理)  │  │   (HITL)    │  │  (健康检查)  │        │
│  └──────┬───────┘  └──────────────┘  └──────────────┘  └──────────────┘        │
└─────────┼───────────────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              Service Layer                                       │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │                          SessionService                                  │   │
│  │  • get_or_create_agent(session_id) → 获取或创建 Agent                   │   │
│  │  • Agent 池管理（复用已有 Agent）                                       │   │
│  │  • Session 生命周期（30分钟过期）                                       │   │
│  │  • Redis 事件缓冲                                                        │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │                          ChatService                                     │   │
│  │  • 消息持久化（DB）                                                      │   │
│  │  • 调用 agent.chat() 获取流式响应                                        │   │
│  │  • SSE 事件流推送                                                        │   │
│  │  • Plan 更新监听                                                         │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────┬───────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                         SimpleAgent (V4.4 核心编排器)                            │
│                                                                                  │
│  ┌────────────────────────────────────────────────────────────────────────────┐│
│  │                      初始化阶段 (Schema 驱动)                               ││
│  │  ┌───────────────────────────────────────────────────────────────────────┐ ││
│  │  │ AgentFactory                                                          │ ││
│  │  │   input: system_prompt (用户定义或框架默认)                           │ ││
│  │  │   process: LLM 根据 Prompt 关键词推断配置 (Haiku)                     │ ││
│  │  │   output: AgentSchema {                                               │ ││
│  │  │     intent_analyzer: {enabled, llm_model},                            │ ││
│  │  │     plan_manager: {enabled, max_steps, replan_enabled, ...},          │ ││
│  │  │     tools: [...],  // ⚠️ 根据 Prompt 推断，非全量发现                 │ ││
│  │  │     skills: [...]  // ⚠️ 根据 Prompt 推断，非全量发现                 │ ││
│  │  │   }                                                                   │ ││
│  │  │                                                                       │ ││
│  │  │   推断规则（来自 SCHEMA_GENERATOR_PROMPT）：                          │ ││
│  │  │   • "数据分析"/"pandas" → tools=["e2b_sandbox"]                      │ ││
│  │  │   • "搜索"/"查找"      → tools=["web_search", "exa_search"]          │ ││
│  │  │   • "PPT"/"演示"       → skills=[{skill_id: "pptx"}]                 │ ││
│  │  │   • "Excel"/"表格"     → skills=[{skill_id: "xlsx"}]                 │ ││                                                                   │ ││
│  │  └───────────────────────────────────────────────────────────────────────┘ ││
│  └────────────────────────────────────────────────────────────────────────────┘│
│                                                                                  │
│  ┌────────────────────────────────────────────────────────────────────────────┐│
│  │                      核心组件（实际使用中）                                 ││
│  │                                                                             ││
│  │  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐         ││
│  │  │ IntentAnalyzer   │  │  ToolSelector    │  │  ToolExecutor    │         ││
│  │  │ ━━━━━━━━━━━━━━━ │  │ ━━━━━━━━━━━━━━━  │  │ ━━━━━━━━━━━━━━━ │         ││
│  │  │ ✅ 实际使用      │  │ ✅ 实际使用      │  │ ✅ 实际使用      │         ││
│  │  │ • analyze()      │  │ • select()       │  │ • execute()      │         ││
│  │  │ Model: Haiku 4.5 │  │ 来源: Schema优先 │  │ 动态加载工具     │         ││
│  │  │ 输出: IntentResult│ │ 备用: capability │  │ ResultCompactor  │         ││
│  │  └──────────────────┘  └──────────────────┘  └──────────────────┘         ││
│  │                                                                             ││
│  │  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐         ││
│  │  │CapabilityRegistry│  │ EventBroadcaster │  │  LLMService      │         ││
│  │  │ ━━━━━━━━━━━━━━━ │  │ ━━━━━━━━━━━━━━━  │  │ ━━━━━━━━━━━━━━━ │         ││
│  │  │ ✅ 实际使用      │  │ ✅ 实际使用      │  │ ✅ 实际使用      │         ││
│  │  │ YAML 单一数据源  │  │ Agent 事件入口   │  │ Claude Sonnet    │         ││
│  │  │ Tools/Skills/MCP │  │ SSE 事件推送     │  │ Skills Container │         ││
│  │  │ skill_id 读取    │  │ Plan 更新通知    │  │ Extended Thinking│         ││
│  │  └──────────────────┘  └──────────────────┘  └──────────────────┘         ││
│  │                                                                             ││
│  │  ┌──────────────────┐  ┌──────────────────┐                                ││
│  │  │ E2EPipelineTracer│  │   _plan_cache    │                                ││
│  │  │ ━━━━━━━━━━━━━━━ │  │ ━━━━━━━━━━━━━━━  │                                ││
│  │  │ ✅ 实际使用      │  │ ✅ 实际使用      │                                ││
│  │  │ 全链路追踪       │  │ Plan 状态缓存    │                                ││
│  │  │ 输入-处理-输出   │  │ 步骤进度管理     │                                ││
│  │  └──────────────────┘  └──────────────────┘                                ││
│  └────────────────────────────────────────────────────────────────────────────┘│
│                                                                                  │
│  ┌────────────────────────────────────────────────────────────────────────────┐│
│  │                      预留组件（代码存在但未集成）                            ││
│  │                                                                             ││
│  │  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐         ││
│  │  │CapabilityRouter  │  │InvocationSelector│  │ CodeOrchestrator │         ││
│  │  │ ━━━━━━━━━━━━━━━ │  │ ━━━━━━━━━━━━━━━  │  │ ━━━━━━━━━━━━━━━ │         ││
│  │  │ ⚠️ 未集成        │  │ ⚠️ 未集成        │  │ ⚠️ 未集成        │         ││
│  │  │ 评分算法路由     │  │ 5种调用方式选择  │  │ 代码生成-验证    │         ││
│  │  │ 位置:router.py  │  │ 位置:invocation.py│ │ 位置:orchestration│         ││
│  │  └──────────────────┘  └──────────────────┘  └──────────────────┘         ││
│  │                                                                             ││
│  │  ⚠️ 设计说明：                                                             ││
│  │  • V4 简化了工具选择逻辑，直接从 Schema/capability_tag 匹配                ││
│  │  • CapabilityRouter 的评分算法预留给未来"智能路由"场景                    ││
│  │  • InvocationSelector 的 5 种调用方式由 System Prompt 指导 Claude 选择     ││
│  │  • CodeOrchestrator 的代码验证逻辑可按需集成                               ││
│  └────────────────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                                Core Layer                                        │
│                                                                                  │
│  ┌────────────────────────────────────────────────────────────────────────────┐│
│  │                         core/agent/ (编排层)                                ││
│  │  ┌──────────────────────────────────────────────────────────────────────┐  ││
│  │  │                        SimpleAgent                                    │  ││
│  │  │   • RVR Loop 编排（Read-Reason-Act-Observe-Validate-Write）          │  ││
│  │  │   • 模块协调（无业务逻辑）                                            │  ││
│  │  │   • Plan Cache 管理（_plan_cache）                                    │  ││
│  │  │   • E2E Pipeline 追踪（E2EPipelineTracer）                            │  ││
│  │  │   • Skills Container 启用（enable_skills）                            │  ││
│  │  └──────────────────────────────────────────────────────────────────────┘  ││
│  │  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐         ││
│  │  │ IntentAnalyzer   │  │     types.py     │  │   factory.py     │         ││
│  │  │  • 意图识别      │  │  • TaskType      │  │  • Schema 驱动   │         ││
│  │  │  • 复杂度判断    │  │  • Complexity    │  │  • 动态初始化    │         ││
│  │  │  • needs_plan    │  │  • IntentResult  │  │  • Prompt→Schema │         ││
│  │  └──────────────────┘  └──────────────────┘  └──────────────────┘         ││
│  └────────────────────────────────────────────────────────────────────────────┘│
│                                                                                  │
│  ┌────────────────────────────────────────────────────────────────────────────┐│
│  │                     core/orchestration/ (编排层)                            ││
│  │  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐         ││
│  │  │ pipeline_tracer  │  │  code_validator  │  │ code_orchestrator│         ││
│  │  │  ✅ E2E 追踪     │  │  ⚠️ 预留         │  │  ⚠️ 预留         │         ││
│  │  │  • 阶段记录      │  │  • 语法检查      │  │  • 代码生成      │         ││
│  │  │  • 统计报告      │  │  • 依赖验证      │  │  • 验证执行      │         ││
│  │  └──────────────────┘  └──────────────────┘  └──────────────────┘         ││
│  └────────────────────────────────────────────────────────────────────────────┘│
│                                                                                  │
│  ┌────────────────────────────────────────────────────────────────────────────┐│
│  │                          core/tool/ (工具层)                                ││
│  │  ┌──────────────────────────────────────────────────────────────────────┐  ││
│  │  │                        ToolSelector                                   │  ││
│  │  │   ⚠️ 核心职责：根据 capability_tag 从 Registry 匹配工具              │  ││
│  │  │   • Level 1 核心工具（如 plan_todo）：始终加载                        │  ││
│  │  │   • Level 2 动态工具：按 capability_tag 匹配                          │  ││
│  │  │   • 原生工具（bash, web_search）：自动添加                            │  ││
│  │  │                                                                       │  ││
│  │  │   ⚠️ 注意：优先级逻辑在 SimpleAgent.chat() 实现：                     │  ││
│  │  │   Skill 路径 > Schema.tools > Plan.capabilities > Intent 推断        │  ││
│  │  └──────────────────────────────────────────────────────────────────────┘  ││
│  │  ┌──────────────────────────────────────────────────────────────────────┐  ││
│  │  │                        ToolExecutor                                   │  ││
│  │  │   • 动态加载工具实例（从 tools/ 目录）                                │  ││
│  │  │   • 依赖注入（event_manager, workspace_dir）                          │  ││
│  │  │   • ResultCompactor 自动精简结果                                      │  ││
│  │  └──────────────────────────────────────────────────────────────────────┘  ││
│  │  ┌──────────────────────────────────────────────────────────────────────┐  ││
│  │  │              core/tool/capability/ (能力管理子包)                     │  ││
│  │  │   ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐  │  ││
│  │  │   │  registry.py     │  │   router.py      │  │ invocation.py    │  │  ││
│  │  │   │ ✅ (能力注册表)  │  │ ⚠️ (智能路由)   │  │ ⚠️ (调用策略)   │  │  ││
│  │  │   └──────────────────┘  └──────────────────┘  └──────────────────┘  │  ││
│  │  │   ┌──────────────────┐  ┌──────────────────┐                        │  ││
│  │  │   │ skill_loader.py  │  │    types.py      │                        │  ││
│  │  │   │ ✅ (Skills加载器)│  │ ✅ (类型定义)   │                        │  ││
│  │  │   └──────────────────┘  └──────────────────┘                        │  ││
│  │  └──────────────────────────────────────────────────────────────────────┘  ││
│  └────────────────────────────────────────────────────────────────────────────┘│
│                                                                                  │
│  ┌────────────────────────────────────────────────────────────────────────────┐│
│  │                        core/memory/ (记忆层)                                ││
│  │                                                                             ││
│  │  ┌───────────────────┐                                                     ││
│  │  │   MemoryManager   │ ← 统一入口                                          ││
│  │  └─────────┬─────────┘                                                     ││
│  │            │                                                                ││
│  │  ┌─────────┴─────────┬─────────────────┬─────────────────┐                 ││
│  │  │                   │                 │                 │                 ││
│  │  ▼                   ▼                 ▼                 ▼                 ││
│  │  ┌─────────┐   ┌───────────┐   ┌───────────┐   ┌───────────┐              ││
│  │  │Working  │   │  user/    │   │  user/    │   │ system/   │              ││
│  │  │Memory   │   │ episodic  │   │   e2b     │   │  skill    │              ││
│  │  │(会话级) │   │ (用户级)  │   │ (用户级)  │   │ (系统级)  │              ││
│  │  └─────────┘   └───────────┘   └───────────┘   └───────────┘              ││
│  │                                                                             ││
│  └────────────────────────────────────────────────────────────────────────────┘│
│                                                                                  │
│  ┌─────────────────────────────┐  ┌─────────────────────────────┐              │
│  │       core/context/         │  │        core/events/         │              │
│  │  ┌───────────────────────┐  │  │  ┌───────────────────────┐  │              │
│  │  │   RuntimeContext      │  │  │  │    EventManager       │  │              │
│  │  │   • Block 状态        │  │  │  │    • session_events   │  │              │
│  │  │   • Stream 累积       │  │  │  │    • message_events   │  │              │
│  │  │   • Turn 管理         │  │  │  │    • content_events   │  │              │
│  │  └───────────────────────┘  │  │  │    • system_events    │  │              │
│  │  ┌───────────────────────┐  │  │  │    • user_events      │  │              │
│  │  │  ConversationContext  │  │  │  │    • conversation_    │  │              │
│  │  │   • Token 计数        │  │  │  │      events           │  │              │
│  │  │   • 历史压缩          │  │  │  └───────────────────────┘  │              │
│  │  └───────────────────────┘  │  └─────────────────────────────┘              │
│  └─────────────────────────────┘                                               │
│                                                                                  │
│  ┌─────────────────────────────┐  ┌─────────────────────────────┐              │
│  │        core/llm/            │  │      core/schemas/          │              │
│  │  ┌───────────────────────┐  │  │  ┌───────────────────────┐  │              │
│  │  │   ClaudeLLMService    │  │  │  │    validator.py       │  │              │
│  │  │   • Stream 支持       │  │  │  │  • AgentSchema        │  │              │
│  │  │   • Tool 格式转换     │  │  │  │  • PlanManagerConfig  │  │              │
│  │  │   • Extended Thinking │  │  │  │  • Re-Plan 配置       │  │              │
│  │  └───────────────────────┘  │  │  └───────────────────────┘  │              │
│  │  ┌─────────┐ ┌─────────┐   │  │                              │              │
│  │  │ OpenAI  │ │ Gemini  │   │  │                              │              │
│  │  └─────────┘ └─────────┘   │  │                              │              │
│  └─────────────────────────────┘  └─────────────────────────────┘              │
│                                                                                  │
└──────────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           Infrastructure Layer                                   │
│                                                                                  │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐                 │
│  │     tools/      │  │     config/     │  │     models/     │                 │
│  │                 │  │                 │  │                 │                 │
│  │ • plan_todo     │  │ • capabilities  │  │ • Conversation  │                 │
│  │   (含 replan)   │  │   .yaml         │  │ • Message       │                 │
│  │ • exa_search    │  │ • routing_rules │  │ • Session       │                 │
│  │ • e2b_sandbox   │  │   .yaml         │  │ • User          │                 │
│  │ • e2b_vibe      │  │                 │  │                 │                 │
│  │ • slidespeak    │  │                 │  │                 │                 │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘                 │
│                                                                                  │
└──────────────────────────────────────────────────────────────────────────────────┘
```

---

## 📦 模块详解

### 1. core/agent/ - 编排层

```
core/agent/
├── __init__.py          # 导出 SimpleAgent, IntentAnalyzer
├── simple_agent.py      # 核心编排器
├── intent_analyzer.py   # 意图分析
├── factory.py           # Schema 驱动的 Agent 工厂
└── types.py             # 类型定义
```

**SimpleAgent 职责**：
```python
class SimpleAgent:
    """
    编排器 - 协调各模块完成任务（无业务逻辑）
    
    不做：
    - ❌ 直接调用 LLM API
    - ❌ 直接执行工具
    - ❌ 业务逻辑判断
    - ❌ 硬编码工具调用规则
    
    只做：
    - ✅ 协调 IntentAnalyzer 分析意图
    - ✅ 协调 ToolSelector 选择工具
    - ✅ 协调 ToolExecutor 执行工具
    - ✅ 管理 RVR 循环
    - ✅ 发射事件到 EventManager
    - ✅ 管理 Plan Cache（_plan_cache）
    - ✅ E2E Pipeline 追踪（E2EPipelineTracer）
    """
```

**IntentAnalyzer 职责**：
```python
class IntentAnalyzer:
    """
    意图分析器
    
    输入: 用户消息列表（包含上下文）
    输出: IntentResult {
        task_type: TaskType,      # 任务类型
        complexity: Complexity,    # 复杂度
        needs_plan: bool,         # 是否需要 Plan
        keywords: List[str]       # 提取的关键词
    }
    
    注意：
    - 不负责 Prompt 选择（由 AgentFactory 在创建时确定）
    - 使用 Haiku 快速分析，支持规则降级
    """
```

**AgentFactory 职责**：
```python
class AgentFactory:
    """
    Schema 驱动的 Agent 工厂
    
    功能：
    - 从 System Prompt 动态生成 Schema
    - 根据 Schema 配置初始化 Agent
    - 支持 Re-Plan 相关配置（PlanManagerConfig）
    """
```

### 2. core/orchestration/ - 编排层（🆕 V4.2.1）

```
core/orchestration/
├── __init__.py           # 统一导出
├── pipeline_tracer.py    # 🆕 E2E Pipeline 追踪器
├── code_validator.py     # 🆕 代码验证器
└── code_orchestrator.py  # 🆕 代码执行编排器
```

**E2EPipelineTracer 职责**：
```python
class E2EPipelineTracer:
    """
    端到端管道追踪器 - 全链路可观测
    
    职责：
    - 追踪 Agent 执行各阶段（意图分析/工具选择/代码执行等）
    - 记录每阶段输入-处理-输出
    - 生成执行报告（耗时/状态/错误）
    - 支持调试和问题定位
    
    使用方式：
        tracer = create_pipeline_tracer(session_id)
        stage = tracer.create_stage("intent_analysis")
        stage.start()
        stage.set_input({"messages": messages})
        # ... 执行处理 ...
        stage.complete({"task_type": "code_generation"})
        tracer.finish()
        print(tracer.to_dict())  # 获取完整报告
    """
```

**CodeValidator 职责**：
```python
class CodeValidator:
    """
    代码验证器 - 多级验证保障
    
    验证流程：
    1. 语法检查 - AST 解析验证
    2. 依赖检查 - import 模块可用性
    3. 安全检查 - 危险操作检测（可选）
    
    返回：ValidationResult
    - is_valid: 是否通过验证
    - errors: 错误列表
    - suggestions: 修复建议
    """
```

**CodeOrchestrator 职责**：
```python
class CodeOrchestrator:
    """
    代码执行编排器 - 代码先行策略
    
    编排流程：
    1. 代码生成（LLM）
    2. 代码验证（CodeValidator）
    3. 代码执行（E2B Sandbox）
    4. 结果验证
    5. 错误修复（自动重试）
    
    设计原则：
    - 参考先进 Agent 的 Code-First 策略
    - 结构化的代码生成与验证
    - 自动错误修复和重试
    """
```

### 2.5 统一能力注册与发现机制（V4.2.3+）

**设计理念**：
- **capabilities.yaml = 唯一真相来源**：所有脚手架（Tools/Skills/MCP/API）统一配置
- **开发时注册**：Custom Skill 由开发人员一次性注册，skill_id 自动回写到配置
- **运行时只读**：Agent 运行时直接从配置读取，不做任何注册操作
- **Plan 阶段统一发现**：从 capabilities.yaml 发现并动态路由

**核心原则**：
```
❌ 错误：每次用户请求都注册 Skill（浪费时间）
✅ 正确：开发人员一次性注册，运行时直接使用
```

**完整生命周期**：
```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                          Skill 完整生命周期                                      │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  ┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓   │
│  ┃ 阶段 1: 开发阶段（开发人员 one-time 操作）                                ┃   │
│  ┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛   │
│                                                                                  │
│  开发人员编写 Claude Custom Skill                                                │
│      │                                                                           │
│      ▼                                                                           │
│  skills/custom_claude_skills/my-skill/    ← Claude Custom Skills 专用目录        │
│  ├── SKILL.md                                                                    │
│  ├── scripts/                                                                    │
│  └── resources/                                                                  │
│      │                                                                           │
│      ▼                                                                           │
│  运行 CLI 注册（一次性）                                                         │
│  $ python scripts/skill_cli.py register --skill my-skill                        │
│      │                                                                           │
│      ▼                                                                           │
│  Claude API 返回 skill_id → 自动回写到 capabilities.yaml                        │
│                                                                                  │
│  ┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓   │
│  ┃ 阶段 2: 运行时（每次用户 Query）                                          ┃   │
│  ┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛   │
│                                                                                  │
│  用户 Query                                                                      │
│      │                                                                           │
│      ▼                                                                           │
│  ┌──────────────────────────────────────────────────────────────────────────┐   │
│  │ 1. 能力发现（从 capabilities.yaml 读取）                                  │   │
│  │    CapabilityRegistry.get_all_capabilities()                              │   │
│  │    → 返回所有 Tools + Skills + MCP（含 skill_id）                        │   │
│  └───────────────────────────────────┬──────────────────────────────────────┘   │
│                                      │                                           │
│                                      ▼                                           │
│  ┌──────────────────────────────────────────────────────────────────────────┐   │
│  │ 2. Plan 阶段匹配（plan_todo.create_plan）                                 │   │
│  │    ├─ match_capabilities_for_query() → 匹配用户需求                      │   │
│  │    ├─ 获取已配置的 skill_id（直接从配置读取）                            │   │
│  │    └─ 注入 Skills 信息到 PLAN_GENERATION_PROMPT                          │   │
│  │    → Plan 包含 recommended_skill + skill_ids                             │   │
│  └───────────────────────────────────┬──────────────────────────────────────┘   │
│                                      │                                           │
│                                      ▼                                           │
│  ┌──────────────────────────────────────────────────────────────────────────┐   │
│  │ 3. 执行阶段（Claude API 调用）                                            │   │
│  │    container = {                                                          │   │
│  │        "skills": [                                                        │   │
│  │            {"type": "custom", "skill_id": "skill_abc123", "version": "latest"},│
│  │            {"type": "anthropic", "skill_id": "pptx", "version": "latest"} │   │
│  │        ]                                                                  │   │
│  │    }                                                                      │   │
│  │    → Claude 知道可以使用这些 Skill                                        │   │
│  └──────────────────────────────────────────────────────────────────────────┘   │
│                                                                                  │
│  ┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓   │
│  ┃ 阶段 3: 维护阶段（开发人员按需操作）                                      ┃   │
│  ┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛   │
│                                                                                  │
│  $ python scripts/skill_cli.py update --skill my-skill     # 更新版本          │
│  $ python scripts/skill_cli.py unregister --skill my-skill # 注销              │
│  $ python scripts/skill_cli.py sync                        # 同步状态          │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

**capabilities.yaml 统一配置示例**：
```yaml
capabilities:
  # ==================== Claude Custom Skills ====================
  - name: professional-ppt-generator
    type: SKILL
    subtype: CUSTOM               # Claude Custom Skill
    provider: user
    skill_id: "skill_abc123xyz"   # 🔑 由 skill_cli.py 自动回写
    skill_path: "skills/custom_claude_skills/professional-ppt-generator"  # ← 正确目录
    registered_at: "2026-01-06T10:00:00Z"
    capabilities:
      - ppt_generation
      - presentation_creation
    priority: 80
    
  # ==================== Pre-built Skills (Anthropic) ====================
  - name: pptx
    type: SKILL
    subtype: PREBUILT
    provider: anthropic
    skill_id: "pptx"  # Anthropic 官方 ID
    fallback_tool: slidespeak_render
    
  # ==================== Custom Tools ====================
  - name: exa_search
    type: TOOL
    subtype: CUSTOM
    capabilities:
      - web_search
      - semantic_search
```

**CLI 工具**（scripts/skill_cli.py）：
```bash
# 注册 Skill（自动回写 skill_id 到 capabilities.yaml）
python scripts/skill_cli.py register --skill professional-ppt-generator

# 列出所有 Skills 状态
python scripts/skill_cli.py list

# 更新 Skill 版本
python scripts/skill_cli.py update --skill professional-ppt-generator

# 注销 Skill
python scripts/skill_cli.py unregister --skill professional-ppt-generator

# 同步本地配置与 Claude 服务器
python scripts/skill_cli.py sync
```

### 2.6 Plan 创建流程详解（plan_todo_tool）

**工具封装闭环设计**：
```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                       plan_todo_tool 内部流程                                    │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  用户 Query: "帮我生成一个产品PPT"                                               │
│      │                                                                           │
│      ▼                                                                           │
│  ┌──────────────────────────────────────────────────────────────────────────┐   │
│  │ Step 1: 能力发现                                                          │   │
│  │   get_registered_skills_from_config()                                     │   │
│  │   → 从 capabilities.yaml 读取已注册的能力（Tools + Claude Skills）        │   │
│  │   → 返回 [{name, skill_id, capabilities, ...}, ...]                       │   │
│  └───────────────────────────────────┬──────────────────────────────────────┘   │
│                                      │                                           │
│                                      ▼                                           │
│  ┌──────────────────────────────────────────────────────────────────────────┐   │
│  │ Step 2: 能力匹配                                                          │   │
│  │   match_skills_for_query(user_query, capabilities)                        │   │
│  │   → 关键词匹配（ppt, 演示, slides...）                                    │   │
│  │   → 返回 top 3 匹配的能力（按相关性排序）                                  │   │
│  └───────────────────────────────────┬──────────────────────────────────────┘   │
│                                      │                                           │
│                                      ▼                                           │
│  ┌──────────────────────────────────────────────────────────────────────────┐   │
│  │ Step 3: 构建 PLAN_GENERATION_PROMPT                                       │   │
│  │   注入：                                                                   │   │
│  │   • user_query: 用户需求                                                  │   │
│  │   • capabilities: 可用能力分类                                            │   │
│  │   • tools_section: 匹配的工具/能力信息（含 skill_id 如有）               │   │
│  └───────────────────────────────────┬──────────────────────────────────────┘   │
│                                      │                                           │
│                                      ▼                                           │
│  ┌──────────────────────────────────────────────────────────────────────────┐   │
│  │ Step 4: Claude + Extended Thinking                                        │   │
│  │   Model: claude-sonnet-4-5-20250929                                       │   │
│  │   enable_thinking: True                                                    │   │
│  │   → 生成智能计划（深度推理）                                              │   │
│  └───────────────────────────────────┬──────────────────────────────────────┘   │
│                                      │                                           │
│                                      ▼                                           │
│  ┌──────────────────────────────────────────────────────────────────────────┐   │
│  │ Step 5: 返回 Plan                                                         │   │
│  │   {                                                                        │   │
│  │     "goal": "生成产品PPT",                                                │   │
│  │     "recommended_tool": {                                                 │   │
│  │       "name": "ppt_generator",                                           │   │
│  │       "skill_id": "skill_xxx",  // 仅当是 Claude Skill 时                │   │
│  │       "reason": "高质量 PPT 生成工具"                                    │   │
│  │     },                                                                     │   │
│  │     "steps": [...]                                                        │   │
│  │   }                                                                        │   │
│  └──────────────────────────────────────────────────────────────────────────┘   │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

**关键函数**（tools/plan_todo_tool.py）：
- `get_registered_skills_from_config()` - 从 capabilities.yaml 读取已注册能力
- `discover_skills()` - 发现可用能力（优先从配置，备用扫描目录）
- `match_skills_for_query()` - 根据查询匹配能力（关键词 + 评分排序）
- `_create_plan_smart()` - 核心计划生成（调用 Claude + Extended Thinking）

**术语说明**：
- **Claude Custom Skills**: 真正向 Claude API 注册的 Skills，存放在 `skills/custom_claude_skills/`
- **本地指南包**: `skills/library/` 下的工具使用指南，提供 SKILL.md 和辅助脚本
- **capabilities.yaml**: 统一配置所有能力（Tools/Claude Skills/MCP/API）

### 2.7 Re-Plan 机制（🆕 V4.2.2）

**设计理念**：
- Claude 在 RVR 循环中**自主决定**是否调用 replan
- Agent 层**无硬规则**，保持简洁的编排职责
- **工具封装闭环**：plan_todo 内部调用 Claude + Extended Thinking

**架构流程**：
```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                            Re-Plan 决策流程                                      │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  RVR 循环执行中                                                                  │
│      │                                                                           │
│      ▼                                                                           │
│  ┌──────────────────────────────────────────────────────────────────────────┐   │
│  │ 步骤执行 → 更新状态                                                       │   │
│  │   • plan_todo.update_step({step_index, status: "completed|failed"})      │   │
│  └───────────────────────────────────┬──────────────────────────────────────┘   │
│                                      │                                           │
│                                      ▼                                           │
│  ┌──────────────────────────────────────────────────────────────────────────┐   │
│  │ Claude 自主评估（基于 System Prompt 指导）                                │   │
│  │   触发条件：                                                               │   │
│  │   • 多个步骤连续失败                                                       │   │
│  │   • 发现原计划遗漏关键信息                                                 │   │
│  │   • 用户需求发生变化                                                       │   │
│  │   • 执行过程中发现更优方案                                                 │   │
│  └───────────────────────────────────┬──────────────────────────────────────┘   │
│                                      │                                           │
│              ┌───────────────────────┴───────────────────────┐                  │
│              │                                               │                  │
│              ▼                                               ▼                  │
│  ┌──────────────────────────┐               ┌──────────────────────────┐       │
│  │ 继续执行当前计划          │               │ 调用 plan_todo.replan    │       │
│  │ • update_step            │               │ • reason: "失败原因"     │       │
│  │ • 下一步骤               │               │ • strategy: incremental  │       │
│  └──────────────────────────┘               └────────────┬─────────────┘       │
│                                                          │                      │
│                                                          ▼                      │
│                                              ┌──────────────────────────┐       │
│                                              │ plan_todo 内部处理        │       │
│                                              │ • 调用 Claude + Thinking  │       │
│                                              │ • 保留已完成步骤          │       │
│                                              │ • 生成新的剩余步骤        │       │
│                                              │ • 返回新计划              │       │
│                                              └────────────┬─────────────┘       │
│                                                          │                      │
│                                                          ▼                      │
│                                              ┌──────────────────────────┐       │
│                                              │ Agent 更新 plan 缓存     │       │
│                                              │ 继续 RVR 循环            │       │
│                                              └──────────────────────────┘       │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

**PlanManagerConfig 配置**（core/schemas/validator.py）：
```python
class PlanManagerConfig(ComponentConfig):
    """计划管理器配置"""
    
    # 基础配置
    enabled: bool = True
    max_steps: int = 10
    granularity: str = "medium"  # fine/medium/coarse
    
    # 🆕 Re-Plan 配置（V4.2.2）
    replan_enabled: bool = True           # 是否允许重新规划
    max_replan_attempts: int = 2          # 最大重规划次数（0-5）
    replan_strategy: str = "incremental"  # full: 全量 / incremental: 保留已完成
    failure_threshold: float = 0.3        # 失败率阈值（超过时建议重规划）
```

**plan_todo 工具操作**（tools/plan_todo_tool.py）：
```python
# 操作类型
operations = [
    "create_plan",   # 创建计划（调用 Claude + Extended Thinking）
    "update_step",   # 更新步骤状态
    "add_step",      # 动态添加步骤
    "replan",        # 🆕 重新规划（V4.2.2）
    "get_plan",      # 获取当前计划
]

# replan 参数
{
    "operation": "replan",
    "data": {
        "reason": "步骤2失败，CSS框架无法加载",  # 必需
        "strategy": "incremental"                # 可选，默认 incremental
    }
}

# replan 策略
- incremental: 保留已完成步骤，只重新生成剩余步骤
- full: 全量重新生成计划（保存历史记录）
```

### 3. core/tool/ - 工具层

```
core/tool/
├── __init__.py          # 导出 ToolSelector, ToolExecutor
├── selector.py          # 工具选择器
├── executor.py          # 工具执行器
├── result_compactor.py  # 🆕 结果精简器
└── capability/          # ✅ 能力管理子包（已完成重构）
    ├── __init__.py      # 统一导出
    ├── registry.py      # 能力注册表
    ├── router.py        # 智能路由器
    ├── invocation.py    # 调用策略选择器
    ├── skill_loader.py  # Skills 加载器
    └── types.py         # 类型定义
```

**ToolSelector 职责**：
```python
class ToolSelector:
    """
    工具选择器（高层接口）
    
    输入: required_capabilities (如 ["web_search", "ppt_generation"])
    输出: ToolSelectionResult {
        tools: List[Capability],   # 选中的工具
        tool_names: List[str],     # 工具名称
        base_tools: List[str],     # 基础工具（Level 1）
        dynamic_tools: List[str]   # 动态选择的工具（Level 2）
    }
    
    V4.2.4 选择策略（分层版）：
    1. 始终加载 Level 1 核心工具（从 capabilities.yaml 读取 level=1）
    2. 根据能力需求从 Level 2 动态工具中选择
    3. 按优先级排序
    4. 支持 cache_stable 标记（用于 Prompt Cache 优化）
    """
```

### 🆕 工具分层设计（V4.2.4）

**分层配置**（capabilities.yaml）：
```yaml
capabilities:
  # Level 1: 核心工具 - 始终加载
  - name: plan_todo
    level: 1              # 核心工具（需显式配置）
    cache_stable: true    # 结果稳定，可缓存
    
  # Level 2: 动态工具 - 按需加载（默认）
  - name: exa_search
    level: 2              # 动态工具（不配置时默认为 2）
    cache_stable: true    # 搜索结果相对稳定
    
  # 新注册工具示例 - 不指定 level 时默认为 2
  - name: my_new_tool
    type: TOOL
    # level: 不配置时自动为 2（动态工具）
    # cache_stable: 不配置时自动为 false
```

**字段默认值**：
| 字段 | 默认值 | 说明 |
|------|--------|------|
| `level` | `2` | 动态工具，按需加载。核心工具需显式设置 `level: 1` |
| `cache_stable` | `false` | 默认不缓存。稳定输出的工具可设置为 `true` |

**分层选择流程**：
```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                          工具分层选择流程                                        │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  用户 Query 输入                                                                 │
│      │                                                                           │
│      ▼                                                                           │
│  ┌──────────────────────────────────────────────────────────────────────────┐   │
│  │ Step 1: 加载 Level 1 核心工具（始终）                                     │   │
│  │   get_core_tools() → [plan_todo, ...]                                    │   │
│  │   • 任务规划必需                                                          │   │
│  │   • 不受意图/Schema 影响                                                  │   │
│  └───────────────────────────────────┬──────────────────────────────────────┘   │
│                                      │                                           │
│                                      ▼                                           │
│  ┌──────────────────────────────────────────────────────────────────────────┐   │
│  │ Step 2: 根据能力需求选择 Level 2 动态工具                                 │   │
│  │   find_by_capability_tag(capability) → 匹配工具                          │   │
│  │   按优先级排序 → 选择最合适的                                             │   │
│  └───────────────────────────────────┬──────────────────────────────────────┘   │
│                                      │                                           │
│                                      ▼                                           │
│  ┌──────────────────────────────────────────────────────────────────────────┐   │
│  │ Step 3: 返回分层选择结果                                                  │   │
│  │   ToolSelectionResult {                                                   │   │
│  │     base_tools: ["plan_todo"],            // Level 1                     │   │
│  │     dynamic_tools: ["exa_search", "ppt_generator"],  // Level 2          │   │
│  │     cacheable: ["plan_todo", "exa_search"]           // cache_stable     │   │
│  │   }                                                                       │   │
│  └──────────────────────────────────────────────────────────────────────────┘   │
│                                                                                  │
│  💡 优势：                                                                       │
│  • Level 1 工具不重复选择，提升性能                                             │
│  • cache_stable 工具可使用 Prompt Cache                                         │
│  • 配置驱动，无需修改代码即可调整分层                                           │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

**Schema.tools 与 capabilities.yaml 的关系**：
```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                        工具发现与加载流程                                        │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  System Prompt                                                                   │
│      │                                                                           │
│      ▼                                                                           │
│  ┌──────────────────────────────────────────────────────────────────────────┐   │
│  │ AgentFactory._generate_schema()                                          │   │
│  │   根据 Prompt 关键词推断期望的工具名称                                    │   │
│  │   例如："搜索" → ["exa_search", "web_search"]                            │   │
│  │                                                                           │   │
│  │   ⚠️ 注意：这是"期望列表"，不是"全量发现"                                │   │
│  │   ⚠️ Schema.tools 可能为空（简单任务）                                   │   │
│  └───────────────────────────────────┬──────────────────────────────────────┘   │
│                                      │                                           │
│                                      ▼                                           │
│  AgentSchema.tools = ["exa_search", "web_search"]  // 期望列表                  │
│                                      │                                           │
│                                      ▼                                           │
│  ┌──────────────────────────────────────────────────────────────────────────┐   │
│  │ ToolSelector.select(intent_result)                                       │   │
│  │                                                                           │   │
│  │   1️⃣ 加载 capabilities.yaml → CapabilityRegistry                        │   │
│  │      (包含所有注册的 Tools/Skills/MCP)                                   │   │
│  │                                                                           │   │
│  │   2️⃣ 选择优先级：                                                        │   │
│  │      Schema.tools 非空 → 匹配 Registry 中同名工具                        │   │
│  │      Schema.tools 为空 → 按 Intent.capability_tag 匹配                   │   │
│  │                                                                           │   │
│  │   3️⃣ 返回实际可用的工具列表                                              │   │
│  └──────────────────────────────────────────────────────────────────────────┘   │
│                                                                                  │
│  💡 关键点：                                                                     │
│  • capabilities.yaml 是"能力仓库"（所有可用工具）                              │
│  • Schema.tools 是"期望清单"（根据 Prompt 推断）                               │
│  • ToolSelector 将两者匹配，返回"实际可用"的工具                               │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

**ToolExecutor 职责**：
```python
class ToolExecutor:
    """
    工具执行器
    
    职责：
    - 动态加载工具实例（从 tools/ 目录）
    - 依赖注入（event_manager, workspace_dir）
    - 执行工具并格式化结果
    - 错误处理和日志记录
    """
```

**capability/ 子包职责**：
```python
# ✅ registry.py - 能力注册表（实际使用）
class CapabilityRegistry:
    """
    从 capabilities.yaml 加载并管理所有能力
    - 提供能力查询接口
    - 管理能力元数据
    - 支持 TOOL/SKILL/CUSTOM 类型
    - 🆕 get_core_tools() → 获取 Level 1 核心工具
    - 🆕 get_dynamic_tools() → 获取 Level 2 动态工具
    - 🆕 get_cacheable_tools() → 获取可缓存工具列表
    - get_registered_skills() → 获取已注册的 Claude Skills
    """

# ⚠️ router.py - 智能路由器（代码存在，预留未集成）
class CapabilityRouter:
    """
    基于需求智能选择工具
    
    核心算法：
    Score = base_priority           # 基础优先级 (0-100)
          + type_weight × 5         # 类型权重（SKILL > TOOL > MCP > CODE）
          + subtype_weight × 5      # 子类型权重（CUSTOM > PREBUILT > NATIVE）
          + keyword_match × 2       # 关键词匹配度
          + quality_match × 20      # 质量要求匹配
          + context_bonus           # 上下文加分（连续使用、历史成功）
          - cost_penalty            # 成本惩罚
    
    ⚠️ V4 状态：代码完整，但 SimpleAgent 未调用
    
    📊 专业评估 - 是否启用？
    ──────────────────────────────────────────────────
    适用场景：
    • 多工具竞争场景（同一能力有 3+ 候选工具）
    • 需要精细化成本控制（金钱/时间权衡）
    • 动态上下文感知（根据历史成功率调整）
    
    当前替代方案：
    • Schema 驱动：AgentFactory 推断工具
    • priority 排序：简单优先级选择
    • System Prompt：指导 Claude 自主决策
    
    🎯 启用建议：
    • 当工具数量 > 15 且同一能力有多个候选时启用
    • 当需要成本优化（如选择免费工具优先）时启用
    • 当需要上下文连续性（偏好最近成功的工具）时启用
    """

# ⚠️ invocation.py - 调用策略选择器（代码存在，预留未集成）
class InvocationSelector:
    """
    选择最优的工具调用方式
    
    5 种调用方式：
    1. Direct Tool Call      - 单工具+简单参数（默认）
    2. Code Execution        - 配置生成/计算逻辑（复杂结构）
    3. Programmatic Calling  - 多工具编排+循环（批量任务）
    4. Fine-grained Streaming - 大参数 >10KB（流式传输）
    5. Tool Search           - 工具数量 >30（动态发现）
    
    选择规则：
    • 工具数量 > 30 → Tool Search（defer_loading）
    • 输入参数 > 10KB → Fine-grained Streaming
    • 配置生成任务 → Code Execution
    • 多工具编排（>2工具）→ Programmatic Calling
    • 其他 → Direct Tool Call
    
    ⚠️ V4 状态：由 System Prompt 工具选择决策树指导 Claude 自主选择
    
    📊 专业评估 - 是否启用？
    ──────────────────────────────────────────────────
    适用场景：
    • 大规模工具库（>30 工具）需要 Tool Search
    • 频繁处理大参数（>10KB）需要流式传输
    • 复杂批量任务需要程序化调用
    
    当前替代方案：
    • System Prompt 工具选择决策树指导 Claude 选择
    • 工具内部自行处理复杂调用逻辑
    
    🎯 启用建议：
    • 当工具数量接近 30 且需要动态发现时启用
    • 当频繁处理超大输入（>10KB）时启用
    • 需要框架级强制调用方式（而非 Claude 决策）时启用
    """

# ✅ skill_loader.py - 工具指南包加载器（实际使用）
class SkillLoader:
    """
    加载本地工具指南包（Guidance Packages）
    - 从 skills/library/ 发现指南包（PPT 生成指南、SlideSpeak 指南等）
    - 解析元数据（SKILL.md 或 skill.yaml）
    - 加载 prompt/config/resources
    
    ⚠️ 注意：此处的 skills/library/ 是本地指南包，不是 Claude Skills
    真正的 Claude Custom Skills 应放在 skills/custom_claude_skills/
    """
```

### 4. core/memory/ - 记忆层

```
core/memory/
├── __init__.py          # 统一导出
├── base.py              # 基类和类型定义
├── working.py           # WorkingMemory (会话级)
├── manager.py           # MemoryManager (统一入口)
├── user/                # 用户级记忆
│   ├── episodic.py      # 情景记忆（历史总结）
│   ├── e2b.py           # E2B 沙箱记忆
│   ├── plan.py          # 🆕 任务计划持久化（V4.3）
│   └── preference.py    # 用户偏好（预留）
├── mem0/                # 🆕 Mem0 用户画像层（V4.5）
│   ├── __init__.py      # 统一导出
│   ├── config.py        # 配置管理（多VectorDB/LLM/Embedding）
│   ├── pool.py          # Memory实例池（单例模式）
│   ├── formatter.py     # 记忆格式化为Prompt片段
│   └── tencent_vectordb.py  # 腾讯云VectorDB适配器
└── system/              # 系统级记忆
    ├── skill.py         # Skill 记忆
    └── cache.py         # 系统缓存（预留）
```

**记忆层级**：
```
┌─────────────────────────────────────────────────────────────────────┐
│                         Memory Hierarchy                             │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  Session Level (会话级)                                              │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│  WorkingMemory                                                       │
│  • messages: 当前对话消息                                            │
│  • tool_calls: 工具调用记录                                          │
│  • metadata: 元数据                                                  │
│  生命周期: session 结束时清除                                         │
│                                                                      │
│  User Level (用户级)                                                 │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│  EpisodicMemory                                                      │
│  • 用户历史总结                                                      │
│  • 长期经验                                                          │
│                                                                      │
│  E2BMemory                                                           │
│  • 临时沙箱会话                                                      │
│  • 持久沙箱（命名）                                                  │
│  • 执行历史                                                          │
│                                                                      │
│  🆕 PlanMemory (V4.3)                                                │
│  • 跨 Session 任务计划持久化                                         │
│  • 步骤完成状态                                                      │
│  • 进度摘要生成                                                      │
│  • 存储路径: storage/users/{user_id}/plans/                         │
│                                                                      │
│  🆕 Mem0Memory (V4.5) - 用户画像层                                   │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│  • 跨 Session 用户画像与偏好记忆                                     │
│  • 基于向量数据库的语义搜索                                          │
│  • LLM 自动提取事实（fact extraction）                               │
│  • 存储后端: Qdrant / 腾讯云VectorDB                                 │
│  • 特点: 自动个性化，Agent 完全透明                                  │
│                                                                      │
│  System Level (系统级)                                               │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│  SkillMemory                                                         │
│  • 已加载的 Skills                                                   │
│  • Skill 资源缓存                                                    │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### 4.1 PlanMemory 详解（🆕 V4.3）

**设计原则**（借鉴 [autonomous-coding](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)）：
- 步骤只能标记 `passes: true`，永不删除（保证进度单调递增）
- 自动生成进度摘要用于 Prompt 注入
- 对用户透明，框架自动处理

**存储结构**：
```json
{
  "task_id": "task_xxx",
  "goal": "生成产品PPT",
  "user_query": "帮我生成一个关于AI产品的PPT",
  "created_at": "2026-01-07T10:00:00",
  "updated_at": "2026-01-07T10:30:00",
  "status": "in_progress",
  "steps": [
    {"action": "搜索AI产品资料", "status": "completed", "result": "..."},
    {"action": "生成PPT内容", "status": "in_progress"},
    {"action": "渲染PPT文件", "status": "pending"}
  ],
  "completion_rate": 0.33,
  "session_count": 2
}
```

**架构流程**：
```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                       Plan 持久化 + Session 恢复流程                             │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  Session 1: 用户发起复杂任务                                                     │
│      │                                                                           │
│      ▼                                                                           │
│  ┌──────────────────────────────────────────────────────────────────────────┐   │
│  │ IntentAnalyzer.analyze()                                                 │   │
│  │   → needs_persistence = True（复杂度 complex + 多步骤）                  │   │
│  └───────────────────────────────────┬──────────────────────────────────────┘   │
│                                      │                                           │
│                                      ▼                                           │
│  ┌──────────────────────────────────────────────────────────────────────────┐   │
│  │ plan_todo.create_plan()                                                  │   │
│  │   → 自动调用 PlanMemory.save_plan()                                      │   │
│  │   → 存储到 storage/users/{user_id}/plans/{task_id}.json                 │   │
│  └───────────────────────────────────┬──────────────────────────────────────┘   │
│                                      │                                           │
│                                      ▼                                           │
│  执行部分步骤... → plan_todo.update_step() → PlanMemory.update_step()           │
│      │                                                                           │
│      ▼                                                                           │
│  ⚠️ Context Window 耗尽 / 用户中断                                              │
│                                                                                  │
│  ═══════════════════════════════════════════════════════════════════════════════│
│                                                                                  │
│  Session 2: 用户继续任务（新的 Context Window）                                  │
│      │                                                                           │
│      ▼                                                                           │
│  ┌──────────────────────────────────────────────────────────────────────────┐   │
│  │ get_universal_agent_prompt(memory_manager=...)                           │   │
│  │   → 检测到 PlanMemory 有未完成任务                                       │   │
│  │   → 自动注入恢复协议到 System Prompt                                     │   │
│  └───────────────────────────────────┬──────────────────────────────────────┘   │
│                                      │                                           │
│                                      ▼                                           │
│  System Prompt 动态注入:                                                         │
│  ┌──────────────────────────────────────────────────────────────────────────┐   │
│  │ ## 📋 Session 恢复协议                                                   │   │
│  │                                                                          │   │
│  │ 检测到未完成的任务，请优先恢复执行：                                      │   │
│  │                                                                          │   │
│  │ **任务**: 生成产品PPT                                                    │   │
│  │ **进度**: 1/3 完成 (33%)                                                 │   │
│  │ **已完成**: 搜索AI产品资料 ✓                                             │   │
│  │ **待执行**: 生成PPT内容, 渲染PPT文件                                     │   │
│  │                                                                          │   │
│  │ 请从"生成PPT内容"步骤继续执行。                                          │   │
│  └──────────────────────────────────────────────────────────────────────────┘   │
│                                      │                                           │
│                                      ▼                                           │
│  Claude 自动从中断点继续执行                                                     │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

**关键 API**：
```python
# PlanMemory 核心方法
class PlanMemory(BaseScopedMemory):
    def save_plan(self, plan: Dict) -> str           # 保存计划，返回 task_id
    def load_plan(self, task_id: str) -> Dict        # 加载计划
    def update_step(self, task_id, step_index, status, result)  # 更新步骤
    def get_active_plans(self) -> List[Dict]         # 获取所有未完成计划
    def generate_progress_summary(self, task_id) -> str  # 生成进度摘要
    def mark_completed(self, task_id: str)           # 标记任务完成

# MemoryManager 统一访问
memory.plan.save_plan(plan_data)
memory.plan.get_active_plans()
memory.plan.generate_progress_summary(task_id)
```

**用户透明设计**：
| 传统方式 | V4.3 方式 |
|----------|-----------|
| 用户编写 initializer_prompt.md | 框架自动检测 |
| 用户编写 coding_prompt.md | 框架自动注入恢复协议 |
| 手动区分 Session 类型 | IntentAnalyzer 自动判断 |
| 运营人员需要理解 Two-Agent Pattern | 完全透明，无感知 |

### 4.2 Mem0 用户画像详解（🆕 V4.5）

**设计理念**：
- **跨Session用户记忆**：基于Mem0框架实现用户画像与偏好的长期存储
- **语义搜索**：基于向量数据库的相关性检索，提供个性化上下文
- **Agent透明**：Prompt模块封装所有Mem0逻辑，Agent无需感知
- **多数据库支持**：支持Qdrant、腾讯云VectorDB等多种向量数据库

**架构流程**：
```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                       Mem0 用户画像注入流程                                      │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  用户 Query                                                                      │
│      │                                                                           │
│      ▼                                                                           │
│  ┌──────────────────────────────────────────────────────────────────────────┐   │
│  │ Phase 4: System Prompt 组装（simple_agent.py）                           │   │
│  │   get_universal_agent_prompt(user_id=xxx, user_query="...")             │   │
│  └───────────────────────────────────┬──────────────────────────────────────┘   │
│                                      │                                           │
│                                      ▼                                           │
│  ┌──────────────────────────────────────────────────────────────────────────┐   │
│  │ _fetch_user_profile() 内部函数（universal_agent_prompt.py）              │   │
│  │   1. 调用 get_mem0_pool().search(user_id, query, limit=10)              │   │
│  │   2. 获取相关用户记忆（MemoryItem 列表）                                 │   │
│  │   3. 调用 format_memories_for_prompt(memories)                          │   │
│  │   4. 返回格式化后的用户画像字符串                                        │   │
│  └───────────────────────────────────┬──────────────────────────────────────┘   │
│                                      │                                           │
│                                      ▼                                           │
│  ┌──────────────────────────────────────────────────────────────────────────┐   │
│  │ 自动注入到 System Prompt                                                 │   │
│  │                                                                          │   │
│  │   prompt = UNIVERSAL_AGENT_PROMPT                                        │   │
│  │   if user_profile:                                                       │   │
│  │       prompt += "\n\n---\n\n" + user_profile                            │   │
│  │                                                                          │   │
│  │   注入内容示例：                                                          │   │
│  │   ### 用户画像与偏好 (Mem0)                                              │   │
│  │   - 用户是Python开发者，主要使用FastAPI框架                              │   │
│  │   - 用户喜欢测试驱动开发(TDD)方法                                        │   │
│  │   - 用户偏好简洁的代码风格                                               │   │
│  └───────────────────────────────────┬──────────────────────────────────────┘   │
│                                      │                                           │
│                                      ▼                                           │
│  Claude 根据用户画像提供个性化响应                                              │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

**核心模块**：

```python
# core/memory/mem0/config.py - 配置管理
@dataclass
class Mem0Config:
    """Mem0 配置"""
    version: str = "v1.1"
    
    # 向量数据库配置
    vector_store_provider: str = "qdrant"  # qdrant | tencent
    qdrant: QdrantConfig = field(default_factory=QdrantConfig)
    tencent_vectordb: TencentVectorDBConfig = field(default_factory=TencentVectorDBConfig)
    
    # Embedding 配置
    embedder: EmbedderConfig = field(default_factory=EmbedderConfig)
    
    # LLM 配置（用于 fact extraction）
    llm: LLMConfig = field(default_factory=LLMConfig)

# core/memory/mem0/pool.py - Memory 实例池（单例模式）
class Mem0MemoryPool:
    """Mem0 Memory 实例池"""
    
    def search(self, user_id: str, query: str, limit: int = 10) -> List[Dict]
    def add(self, user_id: str, messages: List[Dict]) -> List[Dict]
    def get_all(self, user_id: str) -> List[Dict]
    def update(self, memory_id: str, data: str, user_id: str) -> Dict
    def delete(self, memory_id: str, user_id: str) -> Dict

# core/memory/mem0/formatter.py - 格式化记忆
def format_memories_for_prompt(memories: List[MemoryItem]) -> str:
    """将 Mem0 记忆列表格式化为 System Prompt 片段"""
    ...

# core/memory/mem0/tencent_vectordb.py - 腾讯云 VectorDB 适配器
class TencentVectorDB(VectorStoreBase):
    """腾讯云向量数据库适配器"""
    
    def insert(self, vectors, payloads, ids) -> None
    def search(self, query, vectors, limit, filters) -> List[OutputData]
    def delete(self, vector_id) -> None
    def update(self, vector_id, vector, payload) -> None
    def get(self, vector_id) -> OutputData
    def list(self, filters, limit) -> List[OutputData]
```

**环境配置**（env.template）：
```bash
# ==================== Mem0 + 向量数据库配置 ====================
VECTOR_STORE_PROVIDER=tencent  # qdrant | tencent

# Qdrant 配置（如果使用 Qdrant）
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=

# 腾讯云 VectorDB 配置（如果使用腾讯云）
TENCENT_VDB_URL=http://your-instance.sql.tencentcdb.com:6333
TENCENT_VDB_USERNAME=root
TENCENT_VDB_API_KEY=your-api-key
TENCENT_VDB_DATABASE=mem0_db

# 集合名称
MEM0_COLLECTION_NAME=mem0_user_memories

# ==================== Embedding 配置 ====================
EMBEDDING_PROVIDER=openai
OPENAI_API_KEY=sk-...
EMBEDDING_MODEL=text-embedding-3-small

# ==================== Mem0 内部 LLM 配置 ====================
MEM0_LLM_PROVIDER=openai  # openai | anthropic
MEM0_LLM_MODEL=gpt-4o-mini
```

**Agent透明设计**：
| 传统方式 | V4.5 方式（Mem0） |
|----------|-------------------|
| Agent 直接调用 Mem0 API | Prompt 模块封装 Mem0 逻辑 |
| 需要手动管理用户画像 | 自动获取并注入 |
| Agent 需要理解 Mem0 结构 | Agent 只传 user_id + query |
| 复杂的异步更新逻辑 | 框架提供批量更新 API |

**API 层支持**（🆕 V4.6 整合到 BackgroundTaskService）：
```python
# utils/background_tasks.py - 统一后台任务服务（🆕 V4.6 整合 Mem0）
class BackgroundTaskService:
    # 原有任务
    async def generate_conversation_title(...)  # 对话标题生成
    async def generate_recommended_questions(...) # 推荐问题生成
    
    # 🆕 V4.6 新增：Mem0 记忆增量更新
    async def update_user_memories(
        self,
        user_id: str,
        since_hours: int = 24,
        session_id: Optional[str] = None,
        event_manager: Optional[EventManager] = None
    ) -> Mem0UpdateResult
    
    async def batch_update_all_memories(
        self,
        since_hours: int = 24,
        max_concurrent: int = 5
    ) -> Mem0BatchUpdateResult

# routers/mem0_router.py - REST API（复用 BackgroundTaskService）
@router.post("/batch-update")
async def batch_update_memories(request: BatchUpdateRequest)

@router.post("/user/{user_id}/update")
async def update_user_memories(user_id: str, since_hours: int = 24)
```

### 4.3 智能记忆检索决策（🆕 V4.6）

**核心理念**：基于 Mem0 论文的 Selective Memory 思想，不是每次请求都需要检索用户记忆。通过在意图识别阶段让 LLM 自主推理决定是否需要个性化。

**设计原则**：
- **按需检索**：通用知识查询（天气/百科/汇率）不需要个性化，跳过 Mem0 检索
- **Few-shot 引导**：使用示例引导 Haiku 进行推理，而非硬编码规则
- **可扩展性**：新增场景只需添加 Few-shot 示例，无需修改代码
- **默认安全**：不确定时默认检索（`skip_memory_retrieval=false`）

**架构流程**：
```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                       智能记忆检索决策流程（V4.6）                                │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  用户 Query: "今天上海天气怎么样？"                                               │
│      │                                                                           │
│      ▼                                                                           │
│  ┌──────────────────────────────────────────────────────────────────────────┐   │
│  │ Phase 2: Intent Analysis (Haiku)                                         │   │
│  │   - 分析 task_type, complexity, needs_plan（原有）                        │   │
│  │   - 🆕 分析 skip_memory_retrieval（V4.6 新增）                           │   │
│  │                                                                          │   │
│  │   Few-shot 推理:                                                         │   │
│  │   "天气查询是实时信息，与用户历史无关" → skip_memory_retrieval: true      │   │
│  └───────────────────────────────────┬──────────────────────────────────────┘   │
│                                      │                                           │
│                                      ▼                                           │
│  ┌──────────────────────────────────────────────────────────────────────────┐   │
│  │ Phase 4: System Prompt Assembly                                          │   │
│  │                                                                          │   │
│  │   if intent.skip_memory_retrieval == true:                               │   │
│  │       # 跳过 Mem0 检索，节省 ~200ms + Embedding 成本                     │   │
│  │       system_prompt = UNIVERSAL_AGENT_PROMPT                             │   │
│  │   else:                                                                  │   │
│  │       # 执行 Mem0 检索，注入用户画像                                      │   │
│  │       user_profile = _fetch_user_profile(user_id, user_query)            │   │
│  │       system_prompt = UNIVERSAL_AGENT_PROMPT + user_profile              │   │
│  └───────────────────────────────────┬──────────────────────────────────────┘   │
│                                      │                                           │
│                                      ▼                                           │
│  Claude 执行响应（根据是否有用户画像提供不同级别的个性化）                         │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

**Few-shot 示例表**（位于 `prompts/intent_recognition_prompt.py`）：

| 查询 | skip_memory_retrieval | 推理理由 |
|------|----------------------|----------|
| "今天上海天气怎么样？" | `true` | 实时信息查询，与用户历史无关 |
| "帮我生成一个产品介绍PPT" | `false` | 用户可能有PPT风格偏好、常用配色 |
| "Python的列表推导式怎么用？" | `true` | 通用技术问题，无需个性化 |
| "帮我推荐一家餐厅" | `false` | 需要了解用户口味偏好、饮食限制 |
| "把这段话翻译成英文" | `true` | 简单翻译任务，无需个性化 |
| "帮我写一段Python代码" | `false` | 用户可能有编码风格偏好、常用框架 |
| "1美元等于多少人民币？" | `true` | 汇率查询是客观事实，无需个性化 |
| "按照我之前说的风格写邮件" | `false` | 明确引用了历史偏好 |
| "帮我做一个数据分析报告" | `false` | 用户可能有报告格式、图表风格偏好 |
| "什么是机器学习？" | `true` | 百科知识问答，无需个性化 |

**关键代码变更**：

```python
# core/agent/types.py - 新增字段
@dataclass
class IntentResult:
    task_type: TaskType
    complexity: Complexity
    needs_plan: bool
    needs_persistence: bool = False
    skip_memory_retrieval: bool = False  # 🆕 V4.6

# prompts/intent_recognition_prompt.py - 新增输出字段
{
  "task_type": "...",
  "complexity": "...",
  "needs_plan": true|false,
  "skip_memory_retrieval": true|false  # 🆕 V4.6
}

# prompts/universal_agent_prompt.py - 条件检索
def get_universal_agent_prompt(
    ...,
    skip_memory_retrieval: bool = False  # 🆕 V4.6
) -> str:
    prompt = UNIVERSAL_AGENT_PROMPT
    if not skip_memory_retrieval:  # 只有不跳过时才检索
        user_profile = _fetch_user_profile(user_id, user_query)
        if user_profile:
            prompt += "\n\n---\n\n" + user_profile
    ...

# core/agent/simple_agent.py - 传递意图结果
skip_memory = getattr(intent, 'skip_memory_retrieval', False)
system_prompt = get_universal_agent_prompt(
    user_id=user_id,
    user_query=user_query,
    skip_memory_retrieval=skip_memory  # 🆕 V4.6
)
```

**性能优化收益**：
| 指标 | V4.5 | V4.6 | 改进 |
|------|------|------|------|
| 通用查询延迟 | +200ms (Mem0 检索) | 0ms (跳过) | **~200ms↓** |
| Embedding API 调用 | 每次请求 | 按需调用 | **成本节省** |
| Token 消耗 | 固定开销 | 动态优化 | **按需消耗** |

### 5. core/context/ - 上下文层

```
core/context/
├── __init__.py              # 导出 RuntimeContext, Context, ContextEngineeringManager
├── runtime.py               # 运行时上下文（单次 chat 调用）
├── conversation.py          # 会话上下文（历史管理、压缩）
└── context_engineering.py   # 🆕 上下文工程优化模块（V4.4）
```

**RuntimeContext 职责**：
```python
@dataclass
class RuntimeContext:
    """
    运行时上下文 - 管理单次 chat() 调用的状态
    
    包含：
    - session_id: 会话 ID
    - block: BlockState (当前输出块状态)
    - stream: StreamAccumulator (流式内容累积)
    - current_turn: 当前轮次
    - completed: 是否完成
    """
```

**ContextEngineeringManager 职责**（🆕 V4.4）：
```python
class ContextEngineeringManager:
    """
    上下文工程整合管理器 - 基于先进上下文管理原则
    
    核心组件：
    - CacheOptimizer: KV-Cache 优化，保持前缀稳定性
    - TodoRewriter: Todo 重写，注意力锚定到上下文末尾
    - ToolMasker: 工具遮蔽，状态感知的动态控制
    - RecoverableCompressor: 可恢复压缩，保留引用丢弃内容
    - StructuralVariation: 结构化变异，打破模式匹配
    - ErrorRetention: 错误保留，学习历史失败经验
    
    使用方式：
        manager = create_context_engineering_manager()
        # KV-Cache 优化
        hash = manager.cache_optimizer.calculate_prefix_hash(messages)
        # Todo 重写
        messages = manager.todo_rewriter.inject_todo(messages, plan)
        # 工具遮蔽
        visible_tools = manager.tool_masker.get_visible_tools(state)
    """
```

### 6. core/events/ - 事件层

```
core/events/
├── __init__.py              # 导出 EventManager, EventBroadcaster
├── base.py                  # 基类
├── manager.py               # EventManager (统一入口)
├── broadcaster.py           # EventBroadcaster (Agent 统一入口)
├── dispatcher.py            # 🆕 事件分发器（V4.4）
├── storage.py               # EventStorage (Redis/Memory)
├── session_events.py        # 会话事件
├── message_events.py        # 消息事件
├── content_events.py        # 内容事件（流式）
├── conversation_events.py   # 对话事件
├── user_events.py           # 用户事件
├── system_events.py         # 系统事件
└── adapters/                # 🆕 事件适配器子目录（V4.4）
    ├── __init__.py
    ├── base.py              # 适配器基类
    ├── dingtalk.py          # 钉钉适配器
    ├── feishu.py            # 飞书适配器
    ├── slack.py             # Slack 适配器
    ├── webhook.py           # 通用 Webhook 适配器
    └── zeno.py              # Zeno 适配器
```

**EventBroadcaster 职责**：
```python
class EventBroadcaster:
    """
    Agent 统一事件入口 - 封装增强逻辑
    
    职责：
    - Agent 使用此类发射事件（不直接使用 EventManager）
    - 封装特殊工具的 message_delta 处理
    - 统一事件格式和增强逻辑
    """
```

**EventManager 职责**：
```python
class EventManager:
    """
    统一事件管理器
    
    子管理器：
    - session: SessionEventManager    # start, end, status
    - message: MessageEventManager    # start, stop, tool_call
    - content: ContentEventManager    # start, delta, stop
    - conversation: ConversationEventManager
    - user: UserEventManager
    - system: SystemEventManager      # plan_update, error
    """
```

**EventStorage 职责**：
```python
# storage.py - 事件存储
class RedisEventStorage:
    """Redis 事件存储 - 生产环境"""

class InMemoryEventStorage:
    """内存事件存储 - 开发/测试"""
```

### 7. core/llm/ - LLM 层

```
core/llm/
├── __init__.py     # 导出 create_claude_service, etc.
├── base.py         # BaseLLMService
├── claude.py       # ClaudeLLMService (含 Skills/Files/Citations API)
├── openai.py       # OpenAILLMService
├── gemini.py       # GeminiLLMService
└── adaptor.py      # 🆕 LLM 适配器（统一接口转换）
```

---

## 🔄 数据流

### RVR 循环数据流

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              RVR Loop 数据流                                     │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  User Input                                                                      │
│      │                                                                           │
│      ▼                                                                           │
│  ┌──────────────────────────────────────────────────────────────────────────┐   │
│  │ 1. Intent Analysis                                                        │   │
│  │    IntentAnalyzer.analyze(messages)  # 使用完整消息列表理解上下文         │   │
│  │    → IntentResult { task_type, complexity, needs_plan }                   │   │
│  └───────────────────────────────────┬──────────────────────────────────────┘   │
│                                      │                                           │
│                                      ▼                                           │
│  ┌──────────────────────────────────────────────────────────────────────────┐   │
│  │ 2. Tool Selection + Skill Discovery 🆕                                    │   │
│  │    ToolSelector.select(required_capabilities)                             │   │
│  │    → ToolSelectionResult { tools, tool_names, dynamic_tools }            │   │
│  │                                                                           │   │
│  │    📚 关键：Plan 阶段包含工具发现和动态选择                               │   │
│  │    ├─ discover_skills() → 读取 capabilities.yaml 已注册能力              │   │
│  │    ├─ match_skills_for_query() → 匹配用户需求                            │   │
│  │    └─ get_skill_ids() → 获取已注册的 Claude Skill ID                     │   │
│  └───────────────────────────────────┬──────────────────────────────────────┘   │
│                                      │                                           │
│                                      ▼                                           │
│  ┌──────────────────────────────────────────────────────────────────────────┐   │
│  │ 3. Plan Creation (if needs_plan) 🆕 包含能力发现                          │   │
│  │    plan_todo.create_plan(user_query)                                      │   │
│  │    内部流程：                                                              │   │
│  │    ├─ discover_skills() → 从 capabilities.yaml 发现已注册能力            │   │
│  │    ├─ match_skills_for_query() → 匹配相关工具/指南包                     │   │
│  │    ├─ 获取 skill_id（如有已注册的 Claude Custom Skill）                  │   │
│  │    ├─ 注入能力信息到 PLAN_GENERATION_PROMPT                              │   │
│  │    └─ Claude + Extended Thinking → 生成包含推荐工具的 Plan               │   │
│  │    → Plan { goal, steps[], recommended_tool, skill_ids[] }               │   │
│  └───────────────────────────────────┬──────────────────────────────────────┘   │
│                                      │                                           │
│                                      ▼                                           │
│  ┌──────────────────────────────────────────────────────────────────────────┐   │
│  │ 4. RVR Turn Loop                                                          │   │
│  │    for turn in range(max_turns):                                          │   │
│  │        ┌─────────────────────────────────────────────────────────────┐    │   │
│  │        │ [Read]   ← Plan 状态（含 skill_hint）                        │    │   │
│  │        │ [Reason] ← LLM Extended Thinking                             │    │   │
│  │        │ [Act]    ← LLM Tool Calls（可调用 Skill）                    │    │   │
│  │        │              │                                               │    │   │
│  │        │              ▼                                               │    │   │
│  │        │          ToolExecutor.execute(tool_name, input)             │    │   │
│  │        │          或 Skill.execute（通过 skill_id 激活）              │    │   │
│  │        │              │                                               │    │   │
│  │        │              ▼                                               │    │   │
│  │        │ [Observe] ← Tool/Skill Result                                │    │   │
│  │        │ [Validate] ← 验证结果（在 thinking 中）                      │    │   │
│  │        │ [Write]   ← 更新 Plan 状态                                   │    │   │
│  │        │ [Repeat]  ← if stop_reason == "tool_use"                    │    │   │
│  │        └─────────────────────────────────────────────────────────────┘    │   │
│  └───────────────────────────────────┬──────────────────────────────────────┘   │
│                                      │                                           │
│                                      ▼                                           │
│  ┌──────────────────────────────────────────────────────────────────────────┐   │
│  │ 5. Complete                                                               │   │
│  │    emit_message_stop()                                                    │   │
│  │    → Final Response                                                       │   │
│  └──────────────────────────────────────────────────────────────────────────┘   │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### 事件流

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              Event Flow                                          │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  SimpleAgent                    EventManager                    Frontend         │
│      │                              │                              │             │
│      │  emit_message_start()        │                              │             │
│      │─────────────────────────────►│  message_start               │             │
│      │                              │─────────────────────────────►│             │
│      │                              │                              │             │
│      │  emit_content_start()        │                              │             │
│      │─────────────────────────────►│  content_start (thinking)    │             │
│      │                              │─────────────────────────────►│             │
│      │                              │                              │             │
│      │  emit_content_delta()        │                              │             │
│      │─────────────────────────────►│  content_delta               │             │
│      │         (多次)               │─────────────────────────────►│             │
│      │                              │         (SSE)                │             │
│      │                              │                              │             │
│      │  emit_content_stop()         │                              │             │
│      │─────────────────────────────►│  content_stop                │             │
│      │                              │─────────────────────────────►│             │
│      │                              │                              │             │
│      │  emit_tool_call_start()      │                              │             │
│      │─────────────────────────────►│  tool_call_start             │             │
│      │                              │─────────────────────────────►│             │
│      │                              │                              │             │
│      │  emit_tool_call_complete()   │                              │             │
│      │─────────────────────────────►│  tool_call_complete          │             │
│      │                              │─────────────────────────────►│             │
│      │                              │                              │             │
│      │  emit_plan_update()          │                              │             │
│      │─────────────────────────────►│  plan_update                 │             │
│      │                              │─────────────────────────────►│             │
│      │                              │                              │             │
│      │  emit_message_stop()         │                              │             │
│      │─────────────────────────────►│  message_stop                │             │
│      │                              │─────────────────────────────►│             │
│      │                              │                              │             │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### 以 Agent 为中心的完整流程图（V4.4）

```
                            👤 用户输入
                                │
                    "帮我生成一个产品PPT"
                                │
                                ▼
        ┌───────────────────────────────────────────────────────────────┐
        │                阶段 1: Session/Agent 初始化                    │
        ├───────────────────────────────────────────────────────────────┤
        │  SessionService.get_or_create_agent(session_id)              │
        │                                                               │
        │  1️⃣ 检查 Agent 池是否已有该 session 的 Agent                 │
        │  2️⃣ 如果没有，调用 AgentFactory 创建：                        │
        │     AgentFactory.create(system_prompt) → AgentSchema          │
        │                                                               │
        │  3️⃣ 初始化核心组件：                                          │
        │     • CapabilityRegistry.load("capabilities.yaml")            │
        │     • IntentAnalyzer(llm_model="claude-haiku-4-5-20251001")   │
        │     • ToolSelector(registry, schema.tools)                   │
        │     • ToolExecutor(tools_dir="tools/")                       │
        │     • EventBroadcaster(event_manager)                        │
        │     • E2EPipelineTracer(session_id, conversation_id)         │
        │                                                               │
        │  4️⃣ 启用已注册的 Claude Skills：                              │
        │     registered_skills = registry.get_registered_skills()     │
        │     llm.enable_skills(registered_skills)                     │
        │     → Skills Container 准备就绪                               │
        └───────────────────────┬───────────────────────────────────────┘
                                │
                                ▼
        ┌───────────────────────────────────────────────────────────────┐
        │            阶段 2: Intent Analysis (Haiku 快速分析)            │
        ├───────────────────────────────────────────────────────────────┤
        │  Tracer: stage("intent_analysis").start()                    │
        │                                                               │
        │  IntentAnalyzer.analyze(messages)                            │
        │  Model: claude-haiku-4-5-20251001 (快速+便宜)                 │
        │                                                               │
        │  Output:                                                      │
        │  IntentResult {                                               │
        │    task_type: "content_generation",                          │
        │    complexity: "complex",                                     │
        │    needs_plan: true,                                         │
        │    keywords: ["产品", "PPT", "生成"]                         │
        │  }                                                            │
        │                                                               │
        │  → 发送 intent 事件给前端展示                                 │
        │  Tracer: stage.complete(intent_result)                       │
        └───────────────────────┬───────────────────────────────────────┘
                                │
                                ▼
        ┌───────────────────────────────────────────────────────────────┐
        │            阶段 3: Tool Selection (Schema 驱动优先)            │
        ├───────────────────────────────────────────────────────────────┤
        │  ToolSelector.select(intent_result)                          │
        │                                                               │
        │  选择优先级：                                                  │
        │  ┌─────────────────────────────────────────────────────────┐ │
        │  │ 1️⃣ Schema 驱动（最高优先级）                             │ │
        │  │    if schema.tools 已配置:                               │ │
        │  │        return schema.tools                               │ │
        │  │                                                          │ │
        │  │ 2️⃣ Plan 缓存                                             │ │
        │  │    if _plan_cache["required_capabilities"]:              │ │
        │  │        return match_by_capability(...)                   │ │
        │  │                                                          │ │
        │  │ 3️⃣ Intent 推断（最后备用）                               │ │
        │  │    caps = intent_to_capabilities(task_type)              │ │
        │  │    return registry.find_by_capabilities(caps)            │ │
        │  └─────────────────────────────────────────────────────────┘ │
        │                                                               │
        │  Output:                                                      │
        │  ToolSelectionResult {                                        │
        │    base_tools: ["plan_todo", "bash"],                        │
        │    dynamic_tools: ["exa_search", "slidespeak_render",        │
        │                    "ppt_generator", "e2b_python_sandbox"]    │
        │  }                                                            │
        │                                                               │
        │  ⚠️ 设计说明：                                                │
        │  • V4 简化了选择逻辑，未使用 CapabilityRouter 评分算法        │
        │  • 调用方式选择由 System Prompt 指导 Claude 自主决定          │
        └───────────────────────┬───────────────────────────────────────┘
                                │
                                ▼
        ┌───────────────────────────────────────────────────────────────┐
        │          阶段 4: System Prompt 组装 + LLM 调用准备             │
        ├───────────────────────────────────────────────────────────────┤
        │  组装内容：                                                    │
        │                                                               │
        │  ① Base Prompt (universal_agent_prompt.py)                   │
        │     • RVR 循环规则                                            │
        │     • 工具选择决策树（Skill/E2B/Code Execution 选择逻辑）     │
        │     • Code-First 场景强制规则                                 │
        │                                                               │
        │  ② Tool Definitions (Claude API tools 参数)                  │
        │     • plan_todo (含 replan 操作)                             │
        │     • exa_search, slidespeak_render                          │
        │     • e2b_python_sandbox, ppt_generator                      │
        │                                                               │
        │  ③ Skills Container (如果有已注册的 Skills)                  │
        │     container = {                                             │
        │       "skills": [                                             │
        │         {"type": "custom", "skill_id": "skill_xxx"}          │
        │       ]                                                       │
        │     }                                                         │
        │                                                               │
        │  → LLM 调用准备就绪                                           │
        └───────────────────────┬───────────────────────────────────────┘
                                │
                                ▼
        ┌───────────────────────────────────────────────────────────────┐
        │    阶段 5: Plan Creation (System Prompt 约束 + Claude 自主触发) │
        ├───────────────────────────────────────────────────────────────┤
        │  设计理念：                                                    │
        │  • Plan 创建不是框架强制触发，而是由 System Prompt 约束     │
        │  • Claude 在 RVR Turn 1 根据任务复杂度自主判断是否调用       │
        │  • 利用 Claude 推理能力，避免硬编码规则                       │
        │                                                               │
        │  触发机制：                                                    │
        │  ┌─────────────────────────────────────────────────────────┐ │
        │  │ 1. IntentAnalyzer 提供 needs_plan 提示                  │ │
        │  │    needs_plan=true → 建议创建 Plan                      │ │
        │  │                                                          │ │
        │  │ 2. System Prompt 强制规则（UNIVERSAL_AGENT_PROMPT）     │ │
        │  │    "复杂任务的第一个工具调用必须是 plan_todo.create_plan()" │ │
        │  │                                                          │ │
        │  │ 3. Claude Extended Thinking 分析                        │ │
        │  │    判断: 这是复杂任务 (complexity=complex) 吗？         │ │
        │  │    如果是 → 第一个工具调用: plan_todo.create_plan()     │ │
        │  │    如果不是 → 直接执行（如 web_search）                 │ │
        │  └─────────────────────────────────────────────────────────┘ │
        │                                                               │
        │  执行位置: 阶段 6 (RVR 循环) Turn 1 内部                      │
        │                                                               │
        │  验证机制:                                                     │
        │  • E2EPipelineTracer 监控第一个 tool_call                     │
        │  • 如果 needs_plan=true 但未创建 Plan → 记录警告             │
        │                                                               │
        │  plan_todo 工具内部流程（封装闭环）：                          │
        │  ┌─────────────────────────────────────────────────────────┐ │
        │  │ 1. discover_skills(user_query)                          │ │
        │  │    → 从 capabilities.yaml 发现相关 Skills                │ │
        │  │                                                          │ │
        │  │ 2. 构建 PLAN_GENERATION_PROMPT                          │ │
        │  │    注入：用户query + 可用skills + 工具信息               │ │
        │  │                                                          │ │
        │  │ 3. Claude + Extended Thinking                            │ │
        │  │    Model: claude-sonnet-4-5-20250929                     │ │
        │  │    enable_thinking=True                                  │ │
        │  │                                                          │ │
        │  │ 4. 返回 Plan                                             │ │
        │  └─────────────────────────────────────────────────────────┘ │
        │                                                               │
        │  Output:                                                      │
        │  Plan {                                                       │
        │    goal: "生成产品PPT",                                       │
        │    steps: [                                                   │
        │      {action: "搜索产品信息", capability: "web_search"},     │
        │      {action: "生成PPT", capability: "ppt_generation"}       │
        │    ],                                                         │
        │    recommended_skill: "ppt_generator"                        │
        │  }                                                            │
        │                                                               │
        │  → Agent 更新 _plan_cache                                    │
        │  → EventBroadcaster.emit_plan_update()                       │
        └───────────────────────┬───────────────────────────────────────┘
                                │
                                ▼
        ┌───────────────────────────────────────────────────────────────┐
        │  📊 用户看到 Todo 进度显示（实时 SSE 推送）                   │
        ├───────────────────────────────────────────────────────────────┤
        │  ┌─────────────────────────────────────────────────────────┐ │
        │  │ 📋 Todo Progress: 0/2 completed                         │ │
        │  │                                                          │ │
        │  │ 🎯 Goal: 生成产品PPT                                    │ │
        │  │                                                          │ │
        │  │ - [ ] 搜索产品信息                                       │ │
        │  │ - [ ] 生成PPT                                            │ │
        │  │                                                          │ │
        │  │ [░░░░░░░░░░░░░░░░░░░░] 0%                               │ │
        │  └─────────────────────────────────────────────────────────┘ │
        └───────────────────────┬───────────────────────────────────────┘
                                │
                                ▼
        ┌───────────────────────────────────────────────────────────────┐
        │                  阶段 6: RVR Loop (核心执行)                   │
        ├───────────────────────────────────────────────────────────────┤
        │                                                               │
        │  for turn in range(max_turns):                               │
        │                                                               │
        │  ═══════════════ Turn 1: 执行步骤 1 ═══════════════          │
        │                                                               │
        │  1️⃣ [Read] plan_todo.get_plan()                              │
        │     → current_step: "搜索产品信息"                            │
        │                                                               │
        │  2️⃣ [Reason] LLM Extended Thinking                           │
        │     "需要搜索产品信息，使用 exa_search 工具"                  │
        │     → 发送 thinking 事件                                      │
        │                                                               │
        │  3️⃣ [Act] Tool Call                                          │
        │     Tracer: stage("tool_execution_exa_search").start()       │
        │     exa_search({query: "产品名称 功能特点"})                  │
        │     → EventBroadcaster.emit_tool_call_start()                │
        │                                                               │
        │  4️⃣ [Observe] 获取搜索结果                                   │
        │     ResultCompactor.compact(search_results)                  │
        │     → 结果精简 76.6%                                          │
        │     → EventBroadcaster.emit_tool_call_complete()             │
        │     Tracer: stage.complete(result)                           │
        │                                                               │
        │  5️⃣ [Validate] 验证结果质量                                  │
        │     ✅ 信息完整、相关性高                                     │
        │                                                               │
        │  6️⃣ [Write] plan_todo.update_step()                          │
        │     → status: "completed"                                     │
        │     → EventBroadcaster.emit_plan_update()                    │
        │                                                               │
        │  📊 更新进度显示: 1/2 (50%)                                   │
        │                                                               │
        │  ═══════════════ Turn 2: 执行步骤 2 ═══════════════          │
        │                                                               │
        │  1️⃣ [Read] plan_todo.get_plan()                              │
        │     → current_step: "生成PPT"                                 │
        │                                                               │
        │  2️⃣ [Reason] LLM Extended Thinking                           │
        │     根据工具选择决策树选择调用方式：                           │
        │     ┌─────────────────────────────────────────────────────┐  │
        │     │ 决策树：                                            │  │
        │     │ 内置 Skill 能满足？ → Yes → Claude Skill            │  │
        │     │                    ↓ No                            │  │
        │     │ 需要网络/复杂编排？ → Yes → E2B + 自定义工具        │  │
        │     │                    ↓ No                            │  │
        │     │ 简单计算/配置？ → Yes → code_execution              │  │
        │     └─────────────────────────────────────────────────────┘  │
        │     决策: 使用 ppt_generator 工具（高质量闭环）               │
        │                                                               │
        │  3️⃣ [Act] Tool Call                                          │
        │     ppt_generator({                                          │
        │       topic: "产品介绍",                                      │
        │       audience: "客户",                                       │
        │       style: "business",                                     │
        │       search_queries: ["产品功能", "市场数据"]                │
        │     })                                                        │
        │                                                               │
        │     ppt_generator 内部流程：                                  │
        │     ┌─────────────────────────────────────────────────────┐  │
        │     │ 1. _analyze_requirements() → 需求分析               │  │
        │     │ 2. _collect_materials()    → 调用 exa_search        │  │
        │     │ 3. _plan_content()         → Claude 内容规划        │  │
        │     │ 4. _render_ppt()           → SlideSpeak API         │  │
        │     │ 5. _perform_quality_check()→ 质量检查               │  │
        │     └─────────────────────────────────────────────────────┘  │
        │                                                               │
        │  4️⃣ [Observe] PPT 文件生成完成                               │
        │     → /workspace/outputs/ppt/product_intro.pptx              │
        │                                                               │
        │  5️⃣ [Validate] 验证 PPT 质量                                 │
        │     ✅ 文件存在、格式正确                                     │
        │                                                               │
        │  6️⃣ [Write] plan_todo.update_step()                          │
        │     → status: "completed"                                     │
        │                                                               │
        │  📊 最终进度: 2/2 (100%)                                      │
        │                                                               │
        │  ═══════════════ Re-Plan 决策点 (可选) ═══════════════        │
        │                                                               │
        │  if 步骤失败 && failure_rate > threshold:                    │
        │      Claude 自主决定调用 plan_todo.replan()                   │
        │      策略: incremental (保留已完成步骤)                       │
        │      → 生成新的剩余步骤                                       │
        │                                                               │
        │  🎉 RVR Loop 完成                                             │
        └───────────────────────┬───────────────────────────────────────┘
                                │
                                ▼
        ┌───────────────────────────────────────────────────────────────┐
        │              阶段 7: Final Output & Tracing Report            │
        ├───────────────────────────────────────────────────────────────┤
        │  1️⃣ 生成最终响应                                              │
        │     final_response = "已为您生成产品PPT，下载链接：..."       │
        │                                                               │
        │  2️⃣ 发送完成事件                                              │
        │     EventBroadcaster.emit_message_stop(final_response)       │
        │                                                               │
        │  3️⃣ E2E Pipeline 追踪报告                                     │
        │     Tracer.finish_trace()                                    │
        │     ┌─────────────────────────────────────────────────────┐  │
        │     │ 📊 E2E Pipeline Report                              │  │
        │     │ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │  │
        │     │ Session: 20260107_143052                            │  │
        │     │ User Query: "帮我生成一个产品PPT"                   │  │
        │     │                                                      │  │
        │     │ Stages:                                              │  │
        │     │   ✅ intent_analysis    | 120ms  | success          │  │
        │     │   ✅ tool_exa_search    | 2.3s   | success          │  │
        │     │   ✅ tool_ppt_generator | 15.2s  | success          │  │
        │     │                                                      │  │
        │     │ Statistics:                                          │  │
        │     │   - Total stages: 3                                  │  │
        │     │   - Tool calls: 2                                    │  │
        │     │   - Total time: 17.6s                                │  │
        │     └─────────────────────────────────────────────────────┘  │
        │                                                               │
        │  4️⃣ 返回给用户                                                │
        │     SSE: {type: "message_stop", content: "...", files: [...]}│
        └───────────────────────────────────────────────────────────────┘
                                │
                                ▼
                           ✅ 任务完成
```

---

## 📁 文件结构

### V4.5 目录结构（已同步校验）

```
zenflux_agent/
│
├── core/                           # 核心模块（模块化）
│   ├── __init__.py                 # 统一导出
│   │
│   ├── agent/                      # Agent 模块
│   │   ├── __init__.py
│   │   ├── simple_agent.py         # 编排器
│   │   ├── intent_analyzer.py      # 意图分析
│   │   ├── factory.py              # Schema 驱动的 Agent 工厂
│   │   └── types.py                # 类型定义
│   │
│   ├── tool/                       # 工具模块
│   │   ├── __init__.py
│   │   ├── selector.py             # 工具选择器
│   │   ├── executor.py             # 工具执行器
│   │   ├── result_compactor.py     # 结果精简器
│   │   ├── validator.py            # 工具验证器（V4.4）
│   │   ├── README.md               # 工具模块说明
│   │   └── capability/             # 能力管理子包
│   │       ├── __init__.py
│   │       ├── registry.py         # 能力注册表
│   │       ├── router.py           # 智能路由器
│   │       ├── invocation.py       # 调用策略选择
│   │       ├── skill_loader.py     # Skills 加载器
│   │       └── types.py            # 类型定义
│   │
│   ├── memory/                     # 记忆模块（层级化）
│   │   ├── __init__.py
│   │   ├── base.py                 # 基类
│   │   ├── working.py              # 工作记忆
│   │   ├── manager.py              # 统一管理器
│   │   ├── user/                   # 用户级
│   │   │   ├── episodic.py
│   │   │   ├── e2b.py
│   │   │   ├── plan.py             # 任务计划持久化（V4.3）
│   │   │   └── preference.py
│   │   ├── mem0/                   # 🆕 Mem0 用户画像层（V4.5）
│   │   │   ├── __init__.py         # 统一导出
│   │   │   ├── config.py           # 配置管理（多VectorDB/LLM）
│   │   │   ├── pool.py             # Memory实例池（单例）
│   │   │   ├── formatter.py        # 记忆格式化
│   │   │   └── tencent_vectordb.py # 🆕 腾讯云VectorDB适配器
│   │   └── system/                 # 系统级
│   │       ├── skill.py
│   │       └── cache.py
│   │
│   ├── context/                    # 上下文模块
│   │   ├── __init__.py
│   │   ├── runtime.py              # 运行时上下文
│   │   ├── conversation.py         # 会话上下文
│   │   └── context_engineering.py  # 🆕 上下文工程优化（V4.4）
│   │
│   ├── events/                     # 事件模块
│   │   ├── __init__.py
│   │   ├── manager.py              # 统一管理器
│   │   ├── broadcaster.py          # Agent 统一入口
│   │   ├── dispatcher.py           # 🆕 事件分发器（V4.4）
│   │   ├── storage.py              # Redis/Memory 存储
│   │   ├── base.py                 # 基类
│   │   ├── session_events.py
│   │   ├── message_events.py
│   │   ├── content_events.py
│   │   ├── conversation_events.py
│   │   ├── user_events.py
│   │   ├── system_events.py
│   │   └── adapters/               # 🆕 事件适配器子目录（V4.4）
│   │       ├── __init__.py
│   │       ├── base.py
│   │       ├── dingtalk.py
│   │       ├── feishu.py
│   │       ├── slack.py
│   │       ├── webhook.py
│   │       └── zeno.py
│   │
│   ├── llm/                        # LLM 模块
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── claude.py               # Claude (含 Skills/Files/Citations API)
│   │   ├── openai.py
│   │   ├── gemini.py
│   │   └── adaptor.py              # LLM 适配器
│   │
│   ├── orchestration/              # 编排模块
│   │   ├── __init__.py
│   │   ├── pipeline_tracer.py      # E2E Pipeline 追踪器
│   │   ├── code_validator.py       # 代码验证器
│   │   └── code_orchestrator.py    # 代码执行编排器
│   │
│   ├── schemas/                    # Schema 定义
│   │   ├── __init__.py
│   │   └── validator.py            # 含 Re-Plan 配置
│   │
│   ├── skill/                      # Skill 模块（预留）
│   │   └── __init__.py
│   │
│   ├── agent_manager.py            # Multi-Agent 中央调度器
│   ├── confirmation_manager.py     # HITL 确认管理器
│   └── workspace_manager.py        # 工作空间管理器
│
├── tools/                          # 工具实现
│   ├── __init__.py
│   ├── base.py                     # 工具基类
│   ├── plan_todo_tool.py           # 计划管理（含 replan）
│   ├── exa_search.py               # Exa 语义搜索
│   ├── e2b_sandbox.py              # E2B Python 沙箱
│   ├── e2b_enhanced_sandbox.py     # E2B 增强沙箱
│   ├── e2b_vibe_coding.py          # E2B Vibe Coding
│   ├── e2b_template_manager.py     # E2B 模板管理
│   ├── slidespeak.py               # SlideSpeak PPT 渲染
│   ├── ppt_generator.py            # 高质量闭环 PPT 工具
│   ├── knowledge_search.py         # 知识库搜索
│   ├── api_calling.py              # 通用 API 调用
│   ├── request_human_confirmation.py # HITL 确认请求
│   ├── sandbox_file_tools.py       # 🆕 沙箱文件工具（V4.4）
│   └── workspace_tools.py          # 工作空间工具
│
├── services/                       # 服务层
│   ├── __init__.py
│   ├── chat_service.py             # 聊天服务
│   ├── session_service.py          # 会话服务
│   ├── conversation_service.py     # 对话服务
│   ├── file_service.py             # 文件服务
│   ├── knowledge_service.py        # 知识库服务
│   ├── sandbox_service.py          # 沙箱服务（V4.4）
│   ├── tool_service.py             # 工具服务（V4.4）
│   └── redis_manager.py            # Redis 管理
│
├── routers/                        # API 路由
│   ├── __init__.py
│   ├── chat.py                     # 聊天 + Session 路由（合并）
│   ├── conversation.py             # 对话路由
│   ├── files.py                    # 文件路由
│   ├── knowledge.py                # 知识库路由
│   ├── human_confirmation.py       # HITL 确认路由
│   ├── tools.py                    # 工具路由（V4.4）
│   ├── mem0_router.py              # 🆕 Mem0 记忆管理路由（V4.5）
│   └── workspace.py                # 工作空间路由
│   # 注：health 路由在 main.py 中定义
│
├── models/                         # 数据模型（Pydantic）
│   ├── __init__.py
│   ├── api.py                      # API 通用响应模型
│   ├── chat.py                     # 聊天相关模型
│   ├── database.py                 # 数据库模型
│   ├── file.py                     # 文件模型
│   ├── knowledge.py                # 知识库模型
│   ├── ragie.py                    # Ragie 集成模型
│   └── tool.py                     # 🆕 工具模型（V4.4）
│
├── prompts/                        # 提示词
│   ├── __init__.py
│   ├── universal_agent_prompt.py   # 主要 Agent 提示词
│   ├── e2b_sandbox_protocol.py     # E2B 沙箱协议
│   ├── sandbox_file_protocol.py    # 🆕 沙箱文件协议（V4.4）
│   ├── simple_prompt.py            # 简化提示词
│   ├── standard_prompt.py          # 标准提示词
│   ├── intent_recognition_prompt.py # 意图识别提示词
│   ├── prompt_selector.py          # 提示词选择器
│   ├── skills_loader.py            # Skills 加载器
│   ├── skills_metadata.txt         # 🆕 Skills 元数据
│   ├── MEMORY_PROTOCOL.md          # 🆕 Memory 协议文档
│   └── templates/                  # 🆕 提示词模板子目录
│       └── prompt_example.md
│
├── config/                         # 配置
│   ├── capabilities.yaml           # 能力配置（单一数据源）
│   ├── routing_rules.yaml          # 路由规则
│   ├── e2b_templates.yaml          # E2B 模板配置
│   ├── storage.yaml                # 存储配置
│   └── webhooks.yaml               # 🆕 Webhook 配置（V4.4）
│
├── skills/                         # Skills & 指南包
│   ├── __init__.py
│   ├── custom_claude_skills/       # ✅ Claude Custom Skills 目录（向 Claude API 注册）
│   │   └── __init__.py             #    使用 skill_cli.py 注册后获得 skill_id
│   └── library/                    # 本地工具指南包（非 Claude Skills）
│       ├── planning-task/          #    提供 SKILL.md 指南和辅助脚本
│       ├── ppt-generator/          #    用于 Plan 阶段发现和推荐
│       ├── slidespeak-generator/   #    不向 Claude API 注册
│       ├── slidespeak-editor/      
│       └── slidespeak-slide-editor/
│
├── scripts/                        # 测试脚本 & CLI 工具
│   ├── skill_cli.py                # Skill 注册/注销 CLI
│   ├── e2e_*.py                    # E2E 测试脚本
│   ├── test_*.py                   # 单元测试脚本
│   └── ...
│
├── utils/                          # 🆕 工具模块（V4.6 重构）
│   ├── __init__.py
│   ├── background_tasks.py         # 🆕 统一后台任务服务（整合 Mem0 更新）
│   │                               #    - 对话标题生成
│   │                               #    - 推荐问题生成
│   │                               #    - Mem0 记忆增量更新（V4.6）
│   └── json_utils.py               # JSON 工具函数
│
├── infra/                          # 基础设施（🆕 V4.4 重构）
│   ├── __init__.py
│   ├── cache/                      # 缓存子目录
│   │   ├── __init__.py
│   │   └── redis.py                # Redis 缓存
│   ├── database/                   # 数据库子目录
│   │   ├── __init__.py
│   │   ├── base.py                 # 数据库基类
│   │   ├── engine.py               # 数据库引擎
│   │   ├── tool_repository.py      # 工具仓库
│   │   ├── crud/                   # CRUD 操作
│   │   │   ├── __init__.py
│   │   │   ├── base.py
│   │   │   ├── conversation.py
│   │   │   ├── file.py
│   │   │   ├── knowledge.py
│   │   │   ├── message.py
│   │   │   ├── sandbox.py
│   │   │   └── user.py
│   │   └── models/                 # 数据库模型
│   │       ├── __init__.py
│   │       ├── conversation.py
│   │       ├── file.py
│   │       ├── knowledge.py
│   │       ├── message.py
│   │       ├── sandbox.py
│   │       └── user.py
│   └── storage/                    # 存储子目录
│       ├── __init__.py
│       ├── base.py                 # 存储基类
│       └── local.py                # 本地存储
│
├── main.py                         # FastAPI 入口（含 /health 路由）
│
├── env.template                    # 🆕 环境变量模板（V4.5）
│
└── docs/                           # 文档
    ├── 00-ARCHITECTURE-V4.md       # 本文档
    ├── MEM0_SETUP_GUIDE.md         # 🆕 Mem0 设置指南（V4.5）
    ├── MEM0_EMBEDDING_GUIDE.md     # 🆕 Mem0 Embedding 选择指南（V4.5）
    └── ...
```

---

## 🔮 下一步计划

### ✅ 已完成：V4.5 Mem0 用户画像层

```
✅ 已完成（2026-01-08）

新增模块：
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
core/memory/mem0/__init__.py       ← 统一导出
core/memory/mem0/config.py         ← 配置管理（多VectorDB/LLM/Embedding）
core/memory/mem0/pool.py           ← Memory实例池（单例模式）
core/memory/mem0/formatter.py      ← 记忆格式化为Prompt片段
core/memory/mem0/tencent_vectordb.py ← 🆕 腾讯云VectorDB适配器
utils/background_tasks.py          ← 🆕 V4.6 整合 Mem0 异步批量更新
routers/mem0_router.py             ← REST API 端点（复用 BackgroundTaskService）
prompts/universal_agent_prompt.py  ← 添加 _fetch_user_profile() + 自动注入
core/agent/simple_agent.py         ← Phase 4 用户画像注入（Agent透明）
env.template                       ← 环境变量模板
test_mem0_e2e.py                   ← 端对端测试脚本
docs/MEM0_SETUP_GUIDE.md           ← 设置指南
docs/MEM0_EMBEDDING_GUIDE.md       ← Embedding 选择指南

收益：
✅ 跨 Session 用户画像与偏好记忆
✅ 多向量数据库支持（Qdrant、腾讯云VectorDB）
✅ Agent 完全透明（Prompt 模块封装）
✅ 异步批量更新 API
✅ 完整的配置管理和测试支持
```

### ✅ 已完成：V4.3 Plan 持久化 + Session 恢复

```
✅ 已完成（2026-01-07）

新增模块：
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
core/memory/user/plan.py       ← 🆕 PlanMemory 类
core/memory/user/__init__.py   ← 添加导出
core/memory/manager.py         ← 集成 plan 属性（懒加载）
core/agent/types.py            ← 添加 needs_persistence 字段
core/agent/intent_analyzer.py  ← 自动检测是否需要持久化
tools/plan_todo_tool.py        ← 自动调用 PlanMemory 持久化
prompts/universal_agent_prompt.py ← 动态注入恢复协议

收益：
✅ 跨 Session 任务恢复（借鉴 autonomous-coding）
✅ 用户完全透明（运营人员无需感知 Session 类型）
✅ 框架自动处理（复杂度检测 + Prompt 注入）
✅ 利用现有 Memory 架构（无需引入新存储后端）
```

### ✅ 已完成：core/tool/capability/ 重构

```
✅ 已完成模块化重构（2025-12-30）

原分散模块                        新统一子包
━━━━━━━━━━━━━━━━━━━━━━━━━━      ━━━━━━━━━━━━━━━━━━━━━━━━━━
capability_registry.py    ─┐
capability_router.py      ─┼─→  core/tool/capability/
invocation_selector.py    ─┤       ├── registry.py    ✅
skills_manager.py         ─┘       ├── router.py      ✅
                                   ├── invocation.py  ✅
                                   ├── skill_loader.py✅
                                   └── types.py       ✅

收益：
✅ 统一"能力"概念（Tool | Skill | Custom）
✅ 清晰的模块边界
✅ 完整的类型定义
✅ 易于扩展和测试
```

### 🎯 后续优化方向

1. **增强 Memory 系统**
   - 完善 user/episodic.py（历史总结）
   - 实现智能压缩策略

2. **多 LLM 提供商支持**
   - 完善 OpenAI 和 Gemini 适配器
   - 统一接口和错误处理

3. **性能优化**
   - 能力匹配缓存
   - Skills 元数据预加载
   - 并发工具调用

4. **代码整理（可选）**
   - 考虑将 `core/agent_manager.py` 移入 `core/agent/`
   - 考虑将 `core/workspace_manager.py` 移入 `services/`

5. **长时运行增强**（V4.3+）
   - E2B 沙箱验证集成
   - Git 提交进度保存
   - 多用户并发任务隔离

---

## 📊 模块依赖图

```
                              ┌─────────────────┐
                              │   SimpleAgent   │
                              └────────┬────────┘
                                       │
           ┌───────────────────────────┼───────────────────────────┐
           │                           │                           │
           ▼                           ▼                           ▼
    ┌──────────────┐           ┌──────────────┐           ┌──────────────┐
    │IntentAnalyzer│           │ ToolSelector │           │ ToolExecutor │
    │  ✅ 使用     │           │  ✅ 使用     │           │  ✅ 使用     │
    └──────┬───────┘           └──────┬───────┘           └──────┬───────┘
           │                          │                          │
           │                          └────────────┬─────────────┘
           │                                       │
           │                                       ▼
           │                          ┌────────────────────────────────┐
           │                          │  core/tool/capability/         │
           │                          │  ┌────────────────────────┐    │
           │                          │  │ CapabilityRegistry ✅   │    │
           │                          │  ├────────────────────────┤    │
           │                          │  │ CapabilityRouter  ⚠️   │    │
           │                          │  ├────────────────────────┤    │
           │                          │  │ InvocationSelector ⚠️  │    │
           │                          │  ├────────────────────────┤    │
           │                          │  │ SkillLoader       ✅   │    │
           │                          │  └────────────────────────┘    │
           │                          └────────────┬───────────────────┘
           │                                       │
           │                                       ▼
           │                          ┌───────────────────────┐
           │                          │  capabilities.yaml    │
           │                          │  (唯一真相来源)        │
           │                          └───────────────────────┘
           │
           │         ┌────────────────────────────────────────────┐
           │         │                                            │
           ▼         ▼                                            ▼
    ┌──────────────────────┐                            ┌──────────────┐
    │  ClaudeLLMService    │                            │EventBroadcaster│
    │  (Haiku for intent)  │                            │  ✅ 使用     │
    │  (Sonnet for exec)   │                            └──────────────┘
    └──────────────────────┘

图例：
─────▶  依赖方向
✅      实际使用中
⚠️      代码存在但未集成
```

---

## 🔀 V4.4 Skills + Tools 整合（🆕）

### 5.1 Claude Skills vs Tools 关系

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                         能力调用分层架构                                         │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  用户 Query                                                                      │
│      │                                                                           │
│      ▼                                                                           │
│  ┌──────────────────────────────────────────────────────────────────────────┐   │
│  │ Plan 阶段：匹配能力                                                       │   │
│  │   plan_todo.create_plan() → 分析用户需求，推荐能力                        │   │
│  └───────────────────────────────────┬──────────────────────────────────────┘   │
│                                      │                                           │
│          ┌───────────────────────────┴───────────────────────┐                  │
│          │                                                   │                  │
│          ▼                                                   ▼                  │
│  ┌───────────────────────────────┐       ┌───────────────────────────────┐     │
│  │    Skill 路径                  │       │    Tool 路径                  │     │
│  │    (Plan 匹配到 Skill)         │       │    (无匹配 Skill)             │     │
│  ├───────────────────────────────┤       ├───────────────────────────────┤     │
│  │                               │       │                               │     │
│  │  • 配置: container.skills     │       │  • InvocationSelector 选择    │     │
│  │  • 工作流: SKILL.md 定义      │       │  • 调用: DIRECT tool_use      │     │
│  │  • 执行: Anthropic code_exec  │       │  • Claude 自主推理选择        │     │
│  │                               │       │                               │     │
│  │  示例:                        │       │  示例:                        │     │
│  │  - pptx (快速PPT)            │       │  - e2b_python_sandbox         │     │
│  │  - xlsx (Excel处理)          │       │  - exa_search                 │     │
│  │  - docx (Word文档)           │       │  - ppt_generator              │     │
│  │  - pdf (PDF生成)             │       │  - api_calling                │     │
│  │                               │       │                               │     │
│  └───────────────────────────────┘       └───────────────────────────────┘     │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### 5.2 E2B Sandbox 定位（明确为 Tool）

**核心定位**：E2B 是一个 **Tool**，通过 **DIRECT tool_use** 方式调用，由 **Claude 自主推理** 决定是否使用。

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                        E2B Sandbox vs Claude Skills 对比                         │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  ┌────────────────────────────────┐     ┌────────────────────────────────┐     │
│  │      Claude Skills             │     │      E2B Sandbox               │     │
│  │      (container.skills)        │     │      (DIRECT tool_use)         │     │
│  ├────────────────────────────────┤     ├────────────────────────────────┤     │
│  │                                │     │                                │     │
│  │  调用方式:                     │     │  调用方式:                     │     │
│  │  container = {                 │     │  tool_use: e2b_python_sandbox  │     │
│  │    "skills": [                 │     │  input: {code: "..."}          │     │
│  │      {"type": "anthropic",     │     │                                │     │
│  │       "skill_id": "pptx"}      │     │                                │     │
│  │    ]                           │     │                                │     │
│  │  }                             │     │                                │     │
│  │                                │     │                                │     │
│  │  执行环境:                     │     │  执行环境:                     │     │
│  │  Anthropic 托管                │     │  E2B 云沙箱                    │     │
│  │                                │     │                                │     │
│  │  能力限制:                     │     │  能力优势:                     │     │
│  │  • 网络受限                    │     │  • ✅ 完整网络访问             │     │
│  │  • 包受限                      │     │  • ✅ 任意第三方包             │     │
│  │  • 内置能力固定                │     │  • ✅ 文件持久化               │     │
│  │                                │     │  • ✅ 长时运行 (24h)           │     │
│  │                                │     │                                │     │
│  │  决策者: Plan 阶段匹配         │     │  决策者: Claude 自主推理       │     │
│  │                                │     │                                │     │
│  └────────────────────────────────┘     └────────────────────────────────┘     │
│                                                                                  │
│  ⚠️ 关键点：                                                                    │
│  • E2B 属于 InvocationType.DIRECT，不是 CODE_EXECUTION                         │
│  • CODE_EXECUTION 指 Anthropic 的 code_execution，不是 E2B                      │
│  • Claude 根据任务需求（网络/包/持久化）自主决定是否调用 E2B                    │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

**Claude 何时选择 E2B**：

根据 System Prompt 中的决策树指导，Claude 自主判断：
- 需要 **网络访问**（requests, httpx, 爬虫）→ E2B
- 需要 **第三方包**（pandas, numpy, beautifulsoup）→ E2B
- 需要 **文件持久化**（跨调用保持状态）→ E2B
- 需要 **长时间运行**（超过 code_execution 限制）→ E2B

### 5.3 InvocationSelector 激活条件

**设计原则**：InvocationSelector 仅在 **无匹配 Skill** 时生效。

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                       InvocationSelector 激活流程                                │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  Plan 阶段结果                                                                   │
│      │                                                                           │
│      ▼                                                                           │
│  ┌──────────────────────────────────────────────────────────────────────────┐   │
│  │ 检查: plan_result.recommended_skill 是否存在？                            │   │
│  └───────────────────────────────────┬──────────────────────────────────────┘   │
│                                      │                                           │
│          ┌───────────────────────────┴───────────────────────┐                  │
│          │ YES                                               │ NO               │
│          ▼                                                   ▼                  │
│  ┌───────────────────────────────┐       ┌───────────────────────────────┐     │
│  │ 跳过 InvocationSelector       │       │ 启用 InvocationSelector       │     │
│  │ → 使用 Skill 路径             │       │ → 选择调用模式                │     │
│  │ → container.skills 配置       │       │                               │     │
│  │                               │       │   工具数量 > 30?              │     │
│  │                               │       │   → TOOL_SEARCH               │     │
│  │                               │       │                               │     │
│  │                               │       │   多工具编排 (>2)?            │     │
│  │                               │       │   → PROGRAMMATIC              │     │
│  │                               │       │                               │     │
│  │                               │       │   其他                        │     │
│  │                               │       │   → DIRECT                    │     │
│  └───────────────────────────────┘       └───────────────────────────────┘     │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

**InvocationType 定义**（保持不变）：

```python
class InvocationType(Enum):
    DIRECT = "direct"                   # 标准 tool_use（包括 E2B）
    CODE_EXECUTION = "code_execution"   # Anthropic code_execution
    PROGRAMMATIC = "programmatic"       # 程序化多工具调用
    STREAMING = "streaming"             # 大参数流式
    TOOL_SEARCH = "tool_search"         # 工具发现
```

### 5.4 SimpleAgent 双路径分流

```python
# SimpleAgent._prepare_execution() 伪代码

if plan and plan.get("recommended_skill"):
    # ========== Skill 路径 ==========
    # 1. 配置 container.skills
    skills_container = self._build_skills_container(plan)
    
    # 2. 跳过 InvocationSelector
    invocation_strategy = None
    
    # 3. LLM 调用使用 Skills Container
    response = await llm.create_message_with_skills(
        messages=messages,
        skills=skills_container
    )
    
else:
    # ========== Tool 路径 ==========
    # 1. 启用 InvocationSelector
    strategy = invocation_selector.select_strategy(
        task_type=intent.task_type,
        selected_tools=selected_tools,
        total_available_tools=len(registry.get_all())
    )
    
    # 2. 根据策略配置工具
    tools_config = invocation_selector.get_tools_config(tools, strategy)
    
    # 3. Claude 自主选择工具（包括 E2B）
    response = await llm.create_message_async(
        messages=messages,
        tools=tools_config["tools"]
    )
```

### 5.5 术语规范

| 术语 | 含义 | ZenFlux 对应 |
|------|------|-------------|
| **Claude Skills** | Anthropic 官方 Skills API 机制 | `skills/custom_claude_skills/` + `container.skills` |
| **本地工具指南包** | 框架内工作流指南文档 | `skills/library/` |
| **Tools** | 标准 tool_use 调用的工具 | `tools/` 目录下的工具实现 |
| **连接层** | 任意外部能力接入（不仅是 MCP） | Tools + REST API + E2B + MCP + ... |
| **DIRECT** | 标准 tool_use 调用方式 | 包括 E2B、exa_search 等所有 Tool |
| **CODE_EXECUTION** | Anthropic code_execution | 仅指 Anthropic 托管的代码执行环境 |

### 5.6 System Prompt 决策机制（修正说明）

**说明**：架构文档之前提到的"7级优先级表"实际上是 **决策树 + 选择矩阵** 模式。

Claude 根据 System Prompt (`universal_agent_prompt.py`) 中的决策树自主选择：

```
决策树结构：

内置 Skill 能满足？ ──Yes──→ Claude Skill（优先：快速、便宜）
      │
      No（需要复杂工作流、搜索、质量检查）
      ↓
需要网络/复杂编排？ ──Yes──→ E2B + 自定义工具（如 ppt_generator）
      │
      No
      ↓
简单计算/配置？ ──Yes──→ code_execution（内置沙箱）
      │
      No
      ↓
→ 直接调用标准工具
```

**核心原则**：
- **Skill 优先** — 内置能力可满足时，优先使用（快速、便宜）
- **E2B + 自定义工具** — 需要复杂工作流、网络访问、质量控制时使用
- **场景驱动** — 根据用户需求选择最合适的方案，而非固定优先级

---

## 🧹 清理状态

### ✅ 已完成的清理（V4.4）

以下旧文件已删除：
- `core/capability_registry.py` → 已迁移到 `core/tool/capability/registry.py`
- `core/capability_router.py` → 已迁移到 `core/tool/capability/router.py`
- `core/invocation_selector.py` → 已迁移到 `core/tool/capability/invocation.py`
- `core/skills_manager.py` → 已迁移到 `core/tool/capability/skill_loader.py`
- `core/agent_old.py` → 已删除

### ⚠️ 组件集成状态说明（V4.4 更新）

| 组件 | 位置 | 状态 | 设计用途 | 说明 |
|------|------|------|----------|------|
| `CapabilityRouter` | `core/tool/capability/router.py` | ⚠️ 预留 | 评分算法智能路由 | Schema 驱动 + capability_tag 匹配 |
| `InvocationSelector` | `core/tool/capability/invocation.py` | ✅ 条件激活 | 5种调用方式选择 | 🆕 V4.4: 无匹配 Skill 时启用 |
| `CodeOrchestrator` | `core/orchestration/code_orchestrator.py` | ⚠️ 预留 | 代码生成-验证闭环 | 工具内部自行处理（如 ppt_generator） |
| `CodeValidator` | `core/orchestration/code_validator.py` | ⚠️ 预留 | 语法/依赖/安全验证 | 工具内部自行处理 |

**V4.4 设计决策说明**：

1. **Schema 驱动优先**：AgentFactory 根据 System Prompt 生成 AgentSchema，直接指定工具列表
2. **Claude 自主决策**：工具选择由 System Prompt 工具选择决策树指导
3. **双路径分流**：
   - **Skill 路径**：Plan 匹配到 Skill → container.skills 配置 → 跳过 InvocationSelector
   - **Tool 路径**：无匹配 Skill → InvocationSelector 选择调用模式 → Claude 自主选择工具
4. **E2B 明确定位**：E2B 是 Tool，通过 DIRECT tool_use 调用，Claude 自主推理决定是否使用

**组件启用场景**：
- `InvocationSelector` → 🆕 V4.4 已条件激活（无 Skill 时生效）
- `CapabilityRouter` → 多工具竞争评分场景启用
- `CodeValidator` → 统一代码验证场景启用

### 导入路径参考

```python
# ✅ 当前推荐导入方式
from core.tool.capability import (
    CapabilityRegistry,
    CapabilityRouter,      # ⚠️ 预留
    InvocationSelector,    # ⚠️ 预留
    SkillLoader
)
```

---

## 🔗 相关文档

| 文档 | 说明 | 状态 |
|------|------|------|
| [00-ARCHITECTURE-OVERVIEW.md](./00-ARCHITECTURE-OVERVIEW.md) | V3.7 架构（旧版） | ⚠️ 待删除 |
| [ARCHITECTURE_V3.7_E2B.md](./ARCHITECTURE_V3.7_E2B.md) | V3.7+E2B 详细架构 | 📦 归档 |
| [01-MEMORY-PROTOCOL.md](./01-MEMORY-PROTOCOL.md) | Memory Protocol | ✅ 有效 |
| [02-CAPABILITY-ROUTING.md](./02-CAPABILITY-ROUTING.md) | 能力路由 | 🔄 待更新（V4） |
| [03-EVENT-PROTOCOL.md](./03-EVENT-PROTOCOL.md) | 统一事件协议（SSE/WebSocket） | ✅ 有效 |
| [08-DATA_STORAGE_ARCHITECTURE.md](./08-DATA_STORAGE_ARCHITECTURE.md) | 数据存储 | ✅ 有效 |
| [12-CONTEXT_ENGINEERING_OPTIMIZATION.md](./12-CONTEXT_ENGINEERING_OPTIMIZATION.md) | Context Engineering 优化 | ✅ V4.4 |
| [RESULT_COMPACTOR_IMPLEMENTATION.md](./RESULT_COMPACTOR_IMPLEMENTATION.md) | ResultCompactor 实施 | ✅ V4.1 |
| [MEM0_SETUP_GUIDE.md](./MEM0_SETUP_GUIDE.md) | 🆕 Mem0 设置指南 | ✅ V4.5 |
| [MEM0_EMBEDDING_GUIDE.md](./MEM0_EMBEDDING_GUIDE.md) | 🆕 Mem0 Embedding 选择指南 | ✅ V4.5 |

## 🔗 外部参考

| 参考来源 | 说明 |
|----------|------|
| [Mem0 官方文档](https://docs.mem0.ai/) | 🆕 V4.5 Mem0 框架参考 |
| [Mem0 GitHub](https://github.com/mem0ai/mem0) | 🆕 V4.5 Mem0 开源实现 |
| [腾讯云向量数据库](https://cloud.tencent.com/document/product/1709) | 🆕 V4.5 腾讯云VectorDB文档 |
| [Anthropic Blog: Advanced Tool Use](https://www.anthropic.com/engineering/advanced-tool-use) | V4.4 设计参考 |
| [Claude Skills and MCP](https://claude.com/blog/extending-claude-capabilities-with-skills-mcp-servers) | V4.4 Skills 机制参考 |
| [Anthropic Blog: Effective harnesses for long-running agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents) | V4.3 设计参考 |
| [Claude autonomous-coding 示例](https://github.com/anthropics/anthropic-cookbook/tree/main/claude-quickstarts/autonomous-coding) | Two-Agent Pattern 原型 |

