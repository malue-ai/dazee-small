# Agent V3.7 + E2B 完整架构图

> 📅 **最后更新**: 2025-12-29  
> 🎯 **当前版本**: V3.7 + E2B Vibe Coding Integration  

---

## 🏗️ 完整架构图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              User Query                                     │
│                       "帮我创建一个数据可视化应用"                            │
└──────────────────────────────────┬──────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                       SimpleAgent (V3.7 + E2B)                               │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │                      System Prompt (大脑)                               │ │
│  │  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │ │
│  │  • Intent Recognition Protocol                                         │ │
│  │  • Planning Protocol (Memory-First, LLM自主决定)                       │ │
│  │  • RVR Protocol (可选，取决于Plan)                                     │ │
│  │  • Final Validation Protocol                                           │ │
│  │  • 🆕 E2B Sandbox Protocol (Vibe Coding指南)                          │ │
│  │  • 🆕 动态注入能力分类（来自 CapabilityRegistry）                      │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │             WorkingMemory (Short Memory + E2B Session)                  │ │
│  │  ┌──────────────┐  ┌──────────────┐  ┌───────────────────┐            │ │
│  │  │   messages   │  │  plan.json   │  │   E2B Sessions    │            │ │
│  │  │   (对话历史) │  │  (可选)      │  │  (沙箱状态)        │            │ │
│  │  └──────────────┘  └──────↑───────┘  └─────────↑─────────┘            │ │
│  │                           │ CRUD                │                       │ │
│  │  ┌────────────────────────┴─────────────────────┴──────────────────┐  │ │
│  │  │              plan_todo Tool (动态 Schema)                        │  │ │
│  │  │  • create_plan → 写入 Memory (LLM可选调用)                      │  │ │
│  │  │  • get_plan → 读取 Memory (RVR循环使用)                         │  │ │
│  │  │  • update_step → 更新 Memory (步骤完成时)                       │  │ │
│  │  └──────────────────────────────────────────────────────────────────┘  │ │
│  │  ┌──────────────────────────────────────────────────────────────────┐  │ │
│  │  │         🆕 E2B Session Management (Memory-First)                 │  │ │
│  │  │  • E2BSandboxSession: 沙箱元数据                                │  │ │
│  │  │  • 沙箱复用（跨工具调用，节省启动时间）                          │  │ │
│  │  │  • 执行历史追踪（代码、结果、时间）                              │  │ │
│  │  │  • 文件同步状态（workspace ↔ sandbox）                          │  │ │
│  │  │  • 已安装包列表（避免重复安装）                                  │  │ │
│  │  └──────────────────────────────────────────────────────────────────┘  │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │               🆕 CapabilityRegistry (能力注册表)                        │ │
│  │  ┌──────────────────┐                                                  │ │
│  │  │capabilities.yaml │ ← 唯一数据源（Single Source of Truth）          │ │
│  │  │                  │                                                   │ │
│  │  │ [配置内容]       │                                                   │ │
│  │  │ • task_type_mappings                                                │ │
│  │  │   - information_query, content_generation, data_analysis            │ │
│  │  │   - code_task, app_creation, other                                  │ │
│  │  │                                                                      │ │
│  │  │ • capability_categories (11个)                                      │ │
│  │  │   - knowledge_base, web_search, ppt_generation                      │ │
│  │  │   - document_creation, data_analysis, file_operations               │ │
│  │  │   - code_execution, 🆕 code_sandbox, 🆕 app_generation             │ │
│  │  │   - api_calling, task_planning                                      │ │
│  │  │                                                                      │ │
│  │  │ • capabilities (工具/Skills 定义)                                   │ │
│  │  │   [Native Tools]                                                    │ │
│  │  │   - bash, web_search, plan_todo                                     │ │
│  │  │   [🆕 E2B Tools]                                                    │ │
│  │  │   - e2b_python_sandbox (code_sandbox, code_execution)              │ │
│  │  │   - e2b_vibe_coding (app_generation)                                │ │
│  │  │   [Custom Tools]                                                    │ │
│  │  │   - exa_search, slidespeak, api_calling                             │ │
│  │  └──────────┬───────┘                                                  │ │
│  │             │ 加载配置                                                  │ │
│  │             ▼                                                           │ │
│  │  [核心方法]                                                              │ │
│  │  • get_categories_for_prompt() → System Prompt                         │ │
│  │  • get_category_ids() → plan_todo Schema enum                          │ │
│  │  • get_capabilities_for_task_type() → 能力推断                         │ │
│  │  • 🆕 _get_available_apis() → 自动检测API可用性（零硬编码）            │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────┐  ┌─────────────────┐ │
│  │ Intent LLM  │  │ Execution    │  │ Capability   │  │   Skills        │ │
│  │  (Haiku)    │  │ LLM (Sonnet) │  │   Router     │  │   Manager       │ │
│  │ ───────────  │  │ ──────────── │  │ ──────────── │  │  ──────────────  │ │
│  │ 快速分类    │  │ 深度推理     │  │ 动态筛选     │  │ Skills发现      │ │
│  │ 判断needs   │  │ Extended     │  │ 工具子集     │  │ + E2B Templates │ │
│  │ _plan       │  │ Thinking     │  │              │  │                 │ │
│  └─────────────┘  └──────────────┘  └──────────────┘  └─────────────────┘ │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │             🆕 InvocationSelector (调用方式选择器)                      │ │
│  │  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │ │
│  │  select_strategy() - 根据任务特征智能选择：                            │ │
│  │                                                                          │ │
│  │  1. Direct Tool Call (单工具+简单参数)                                 │ │
│  │     └→ 示例：web_search("天气"), bash("ls")                            │ │
│  │                                                                          │ │
│  │  2. Code Execution (配置生成/计算逻辑)                                  │ │
│  │     └→ 示例：生成PPT配置、数据处理                                     │ │
│  │                                                                          │ │
│  │  3. Programmatic Tool Calling (多工具编排>2)                            │ │
│  │     └→ 示例：循环调用搜索工具、批量处理                                 │ │
│  │                                                                          │ │
│  │  4. Fine-grained Streaming (大参数>10KB)                                │ │
│  │     └→ 示例：流式传输大型配置                                          │ │
│  │                                                                          │ │
│  │  5. Tool Search (工具数量>30)                                           │ │
│  │     └→ 示例：动态工具发现                                              │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │                     Tool Executor (动态加载)                            │ │
│  │  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │ │
│  │  ┌────────────────┐  ┌────────────────┐  ┌──────────────────┐         │ │
│  │  │  Native Tools  │  │  🆕 E2B Tools  │  │  Custom Tools    │         │ │
│  │  ├────────────────┤  ├────────────────┤  ├──────────────────┤         │ │
│  │  │ bash           │  │ e2b_python     │  │ exa_search       │         │ │
│  │  │ web_search     │  │ _sandbox       │  │ slidespeak       │         │ │
│  │  │ str_replace    │  │                │  │ _render          │         │ │
│  │  │ _edit          │  │ e2b_vibe       │  │ api_calling      │         │ │
│  │  │ plan_todo      │  │ _coding        │  │ request_human    │         │ │
│  │  │                │  │                │  │ _confirmation    │         │ │
│  │  └────────────────┘  └────────────────┘  └──────────────────┘         │ │
│  │                                                                          │ │
│  │  执行筛选后的工具子集（动态，Router筛选后的5-10个）🎯                   │ │
│  │  原理：Router根据required_capabilities动态筛选，非全部工具              │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │            🆕 E2B Integration Layer (Vibe Coding)                       │ │
│  │  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │ │
│  │  ┌──────────────────────────────────────────────────────────────────┐  │ │
│  │  │ E2BPythonSandbox                                                 │  │ │
│  │  │ ──────────────────────────────────────────────────────────────── │  │ │
│  │  │ 功能：                                                            │  │ │
│  │  │ • 代码执行（完整网络访问+第三方包）                               │  │ │
│  │  │ • 流式输出（实时stdout/stderr反馈）                              │  │ │
│  │  │ • 文件同步（workspace/inputs ↔ sandbox/input_data）             │  │ │
│  │  │            (workspace/outputs ↔ sandbox/output_data)            │  │ │
│  │  │ • 沙箱复用（Memory-First，跨调用保持）                           │  │ │
│  │  │ • 自动安装包（检测imports并安装）                                │  │ │
│  │  │ • Template支持（base/data-analysis/web-scraping）               │  │ │
│  │  │                                                                   │  │ │
│  │  │ 关键方法：                                                        │  │ │
│  │  │ • execute() - 主入口，协调所有操作                               │  │ │
│  │  │ • _get_or_create_sandbox() - 获取或创建沙箱                      │  │ │
│  │  │ • _execute_code_stream() - 流式执行                              │  │ │
│  │  │ • _auto_install_packages() - 自动包管理                          │  │ │
│  │  │ • _auto_sync_workspace() - 文件同步                              │  │ │
│  │  └──────────────────────────────────────────────────────────────────┘  │ │
│  │                                                                          │ │
│  │  ┌──────────────────────────────────────────────────────────────────┐  │ │
│  │  │ E2BVibeCoding                                                    │  │ │
│  │  │ ──────────────────────────────────────────────────────────────── │  │ │
│  │  │ 功能：                                                            │  │ │
│  │  │ • 应用生成（Streamlit/Gradio/Next.js/Vue）                       │  │ │
│  │  │ • 实时预览URL（https://PORT-SANDBOX_ID.e2b.app）                │  │ │
│  │  │ • 热重载支持（修改代码自动刷新）                                  │  │ │
│  │  │ • 生命周期管理（心跳保活、自动清理）                              │  │ │
│  │  │                                                                   │  │ │
│  │  │ 支持的技术栈：                                                    │  │ │
│  │  │ • streamlit (端口8501) - 数据可视化应用                         │  │ │
│  │  │ • gradio (端口7860) - ML模型界面                                │  │ │
│  │  │ • nextjs (端口3000) - 全栈Web应用                               │  │ │
│  │  │ • vue (端口5173) - 前端应用                                     │  │ │
│  │  │                                                                   │  │ │
│  │  │ 关键方法：                                                        │  │ │
│  │  │ • execute() - 路由到具体操作                                     │  │ │
│  │  │ • create_app() - 创建并部署应用                                  │  │ │
│  │  │ • update_app() - 热更新应用代码                                  │  │ │
│  │  │ • get_app_logs() - 获取应用日志                                  │  │ │
│  │  │ • terminate_app() - 清理资源                                     │  │ │
│  │  └──────────────────────────────────────────────────────────────────┘  │ │
│  │                                                                          │ │
│  │  ┌──────────────────────────────────────────────────────────────────┐  │ │
│  │  │ E2BTemplateManager                                               │  │ │
│  │  │ ──────────────────────────────────────────────────────────────── │  │ │
│  │  │ 模板配置（config/e2b_templates.yaml）：                          │  │ │
│  │  │ • base: 纯净Python环境（按需安装）                               │  │ │
│  │  │ • data-analysis: 预装pandas/numpy/matplotlib/plotly             │  │ │
│  │  │ • web-scraping: 预装requests/beautifulsoup4/lxml                │  │ │
│  │  │                                                                   │  │ │
│  │  │ 路由规则：                                                        │  │ │
│  │  │ • data_analysis → data-analysis模板（快速启动）                  │  │ │
│  │  │ • web_scraping → web-scraping模板                                │  │ │
│  │  │ • app_creation → data-analysis模板（Streamlit）                  │  │ │
│  │  │ • 其他 → base模板                                                │  │ │
│  │  └──────────────────────────────────────────────────────────────────┘  │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │                     EventManager (实时反馈)                             │ │
│  │  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │ │
│  │  事件类型：                                                              │ │
│  │  • intent_analysis - 意图识别结果                                       │ │
│  │  • tool_selection - Router筛选结果                                      │ │
│  │  • thinking - LLM思考过程（Extended Thinking）                         │ │
│  │  • tool_call_start - 工具调用开始                                       │ │
│  │  • tool_call_complete - 工具执行完成                                    │ │
│  │  • plan_update - Plan进度更新（如果有Plan）                            │ │
│  │  • complete - 任务完成                                                  │ │
│  │  • error - 错误信息                                                     │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 🔄 实际执行流程（Vibe Coding场景）

### 用户请求
```
"帮我创建一个数据可视化应用，要求：
1. 生成随机的销售数据
2. 显示交互式图表
3. 计算统计指标
4. 支持多种图表类型切换"
```

### Agent执行流程

```
┌─────────────────────────────────────────────────────────────────┐
│ 阶段1: Intent Analysis (Haiku)                                  │
├─────────────────────────────────────────────────────────────────┤
│ Input: 用户查询                                                  │
│ Output:                                                          │
│   • task_type: "code_task"                                       │
│   • complexity: "complex"                                        │
│   • needs_plan: true  (但LLM可以选择跳过)                       │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ 阶段2: Router (Dynamic Tool Selection)                          │
├─────────────────────────────────────────────────────────────────┤
│ Input: task_type → required_capabilities                        │
│   ['code_execution', 'code_sandbox', 'app_generation',         │
│    'file_operations', 'task_planning']                          │
│                                                                  │
│ Router查询capabilities.yaml:                                     │
│   • code_sandbox → e2b_python_sandbox ✅                        │
│   • app_generation → e2b_vibe_coding ✅                         │
│   • file_operations → file_read                                 │
│   • task_planning → plan_todo, planning-task                   │
│                                                                  │
│ Output: 筛选后的工具列表（5个）                                  │
│   ['plan_todo', 'e2b_vibe_coding', 'file_read',               │
│    'e2b_python_sandbox', 'planning-task']                      │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ 阶段3: LLM Execution (Sonnet)                                   │
├─────────────────────────────────────────────────────────────────┤
│ LLM判断：不需要Plan，直接执行                                    │
│ (任务虽复杂，但只需1个工具调用即可完成)                          │
│                                                                  │
│ Tool Call: e2b_vibe_coding                                      │
│ {                                                                │
│   "action": "create",                                            │
│   "stack": "streamlit",                                          │
│   "description": "数据可视化应用",                               │
│   "code": "...(生成的Streamlit代码)..."                        │
│ }                                                                │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ 阶段4: E2B Tool Execution                                        │
├─────────────────────────────────────────────────────────────────┤
│ e2b_vibe_coding.execute():                                      │
│   1. 创建沙箱 (Sandbox.create())                                │
│      └→ sandbox_id: ia57wwkowkauwhy1i7hms                       │
│                                                                  │
│   2. 安装依赖 (streamlit, pandas, numpy, ...)                   │
│      └→ 耗时: ~10秒                                             │
│                                                                  │
│   3. 写入代码 (/home/user/app.py)                               │
│      └→ 281行Streamlit应用                                      │
│                                                                  │
│   4. 启动应用 (nohup streamlit run app.py &)                    │
│      └→ 后台运行                                                │
│                                                                  │
│   5. 生成预览URL                                                 │
│      └→ https://8501-ia57wwkowkauwhy1i7hms.e2b.app             │
│                                                                  │
│   6. 启动心跳保活                                                │
│      └→ 保持沙箱1小时                                           │
│                                                                  │
│ Output:                                                          │
│ {                                                                │
│   "success": true,                                               │
│   "app_id": "app_20251229_144919",                              │
│   "preview_url": "https://8501-ia57wwkowkauwhy1i7hms.e2b.app", │
│   "sandbox_id": "ia57wwkowkauwhy1i7hms",                        │
│   "port": 8501,                                                  │
│   "message": "✅ Streamlit App 应用已创建！\n🔗 访问: ..."      │
│ }                                                                │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ 阶段5: 用户收到结果                                              │
├─────────────────────────────────────────────────────────────────┤
│ ✅ 任务完成（2轮对话）                                           │
│ 🔗 预览URL: https://8501-ia57wwkowkauwhy1i7hms.e2b.app         │
│ ⏱️  耗时: ~30秒                                                 │
│ 📊 功能: 完整可交互的数据可视化应用                              │
│                                                                  │
│ 用户可以立即访问URL并使用应用：                                  │
│ • 调整数据参数                                                   │
│ • 切换图表类型（6种）                                            │
│ • 查看统计指标                                                   │
│ • 导出数据                                                       │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🎯 核心架构原则验证

### ✅ 1. Prompt-Driven Architecture
```
System Prompt = 大脑（定义所有逻辑规则）
Agent Code = 骨架（框架管理，不含业务规则）

验证：
- ✅ LLM自主决定是否创建Plan
- ✅ LLM自主选择工具（e2b_vibe_coding）
- ✅ Agent代码不包含业务判断
```

### ✅ 2. Memory-First Protocol
```
ASSUME INTERRUPTION - Context window可能随时reset

验证：
- ✅ E2B Session存储在WorkingMemory
- ✅ 沙箱可跨调用复用
- ✅ Plan状态持久化（如果创建）
```

### ✅ 3. Configuration-Driven
```
capabilities.yaml = 唯一数据源

验证：
- ✅ 所有工具定义在YAML
- ✅ 能力分类动态加载
- ✅ API自动发现（零硬编码）
```

### ✅ 4. Dynamic Tool Selection
```
Router根据required_capabilities筛选工具

验证：
- ✅ Vibe Coding场景：筛选5/12个工具
- ✅ PPT场景：筛选12个工具（不同组合）
- ✅ 减少LLM选择困难
```

### ⚠️ 5. RVR Protocol (可选)
```
LLM可选择是否使用完整RVR循环

实际行为：
- ✅ 简单任务：LLM跳过Plan，直接执行
- ✅ 复杂任务：LLM可能创建Plan
- ⚠️ 用户进度可见性：取决于是否有Plan

改进建议：
- 考虑在无Plan时也提供进度反馈
- 或者更严格要求复杂任务必须创建Plan
```

---

## 📊 测试验证结果

### 端到端测试（test_e2e_full_agent.py）

```
测试场景: 创建数据可视化应用（Vibe Coding）
执行时间: ~30秒
轮次: 2轮

结果:
✅ Intent Analysis: 已执行
✅ Router: 筛选5个工具（包含E2B）
✅ LLM主动发现: ['e2b_vibe_coding']
✅ Vibe Coding: https://8501-ia57wwkowkauwhy1i7hms.e2b.app
❌ Plan Creation: 未执行（LLM选择跳过）

成功率: 80% (4/5)
```

### 架构验证清单

| 验证项 | 状态 | 说明 |
|--------|------|------|
| ✅ 自动API发现 | 通过 | 零硬编码，从运行时推断 |
| ✅ Router动态筛选 | 通过 | 根据能力筛选工具子集 |
| ✅ LLM主动选择 | 通过 | 自主调用e2b_vibe_coding |
| ✅ E2B沙箱集成 | 通过 | 创建、执行、文件同步正常 |
| ✅ Vibe Coding | 通过 | 生成可访问的应用URL |
| ✅ Memory-First | 通过 | E2B Session正确存储 |
| ⚠️ Plan/RVR | 可选 | LLM可选择是否使用 |

---

## 🔧 文件结构

```
zenflux_agent/
├── core/
│   ├── agent.py                    # SimpleAgent主类
│   ├── capability_registry.py      # 能力注册表
│   ├── capability_router.py        # Router动态筛选
│   ├── invocation_selector.py      # 调用方式选择
│   ├── memory.py                   # WorkingMemory + E2B Session
│   └── llm_service.py              # LLM封装 + 重试机制
│
├── tools/
│   ├── executor.py                 # 工具执行器（动态加载）
│   ├── e2b_sandbox.py              # E2BPythonSandbox
│   ├── e2b_vibe_coding.py          # E2BVibeCoding
│   ├── e2b_template_manager.py     # E2BTemplateManager
│   └── plan_todo_tool.py           # Plan/Todo CRUD
│
├── config/
│   ├── capabilities.yaml           # 能力+工具配置（唯一数据源）
│   └── e2b_templates.yaml          # E2B模板配置
│
├── prompts/
│   ├── universal_prompt.py         # 完整System Prompt
│   ├── e2b_sandbox_protocol.py     # E2B使用指南
│   └── intent_recognition_prompt.py# Intent分析Prompt
│
└── tests/
    ├── test_e2e_full_agent.py      # 端到端测试
    ├── test_simple_e2b.py          # E2B功能测试
    └── test_router_e2b.py          # Router筛选测试
```

---

## 🚀 使用示例

### 1. 创建Streamlit应用

```python
from core import create_simple_agent, create_event_manager

# 创建Agent
agent = create_simple_agent(
    workspace_dir="/path/to/workspace",
    event_manager=create_event_manager()
)

# 用户查询
user_query = """
帮我创建一个数据可视化应用，要求：
1. 生成随机销售数据
2. 显示交互式图表
3. 计算统计指标
"""

# 执行（流式）
async for event in agent.stream(
    user_input=user_query,
    session_id="test_session",
    enable_stream=False
):
    if event['event_type'] == 'tool_call_complete':
        if event['data']['tool_name'] == 'e2b_vibe_coding':
            result = event['data']['result']
            print(f"🔗 预览URL: {result['preview_url']}")
```

### 2. 执行Python代码（E2B沙箱）

```python
# LLM会自动选择e2b_python_sandbox
user_query = """
请分析这个CSV文件的数据：
/workspace/inputs/sales.csv
生成统计报告并保存图表
"""

# Agent会：
# 1. Router筛选：选择e2b_python_sandbox
# 2. 上传CSV到沙箱
# 3. 执行Python分析代码
# 4. 下载结果到workspace/outputs/
```

---

## 📝 更新日志

### 2025-12-29
- ✅ 修复重复的`_execute_tools`方法定义
- ✅ 移除"简化版"注释，使用完整实现
- ✅ 验证端到端测试（80%成功率）
- ✅ 完成E2B + Vibe Coding集成文档

### 关键改进
1. **零硬编码API发现**：`_get_available_apis()`从运行时推断
2. **完整工具执行**：移除简化版，使用完整实现
3. **Memory-First E2B**：沙箱Session正确管理
4. **LLM自主决策**：Plan创建完全由LLM决定
5. **Router正确筛选**：动态筛选工具子集，验证通过

---

## 🎉 总结

V3.7 + E2B架构已完整实现并验证：
- ✅ **配置驱动**：capabilities.yaml单一数据源
- ✅ **动态筛选**：Router根据能力筛选工具
- ✅ **自动发现**：API可用性自动检测
- ✅ **LLM自主**：Plan/工具选择由LLM决定
- ✅ **Vibe Coding**：完整应用生成+实时预览

**架构稳定，可扩展至100+工具！** 🚀

