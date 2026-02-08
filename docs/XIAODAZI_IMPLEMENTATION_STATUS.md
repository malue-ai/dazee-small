# 小搭子 Agent 实例 — 当前实现架构文档

> 基于《小搭子专用实例架构设计》(V9.0) 需求文档，对照当前代码实现的完整状态梳理。
>
> 范围：仅涉及 Python 后端 + 框架核心层，不涉及 Tauri 桌面壳、Vue 前端组件。
>
> 更新时间：2026-02-08

---

## 〇、架构全景图

### 0.1 分层架构总览

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                              前端层 (frontend/)                                         │
│  Vue 3 + TypeScript + Vite + Tauri                                                      │
│                                                                                         │
│  ┌── views/ ──────────────────────────────────────────────────────────────────────────┐  │
│  │ ChatView │ SettingsView │ SkillsView │ KnowledgeView │ OnboardingView             │  │
│  │ CreateProjectView                                                                 │  │
│  └────┬───────────────────────────────────────────────────────────────────────────────┘  │
│       │                                                                                 │
│  ┌────▼── composables/ ──────────────────────────────────────────────────────────────┐  │
│  │ useChat │ useSSE │ useWebSocketChat │ useHITL │ useFileUpload                     │  │
│  └────┬──────────────────────────────────────────────────────────────────────────────┘  │
│       │                                                                                 │
│  ┌────▼── api/ ──────────────────────────────────────────────────────────────────────┐  │
│  │ chat.ts │ session.ts │ config.ts │ settings.ts │ skills.ts │ workspace.ts         │  │
│  │ models.ts │ tauri.ts │ agent.ts                                                   │  │
│  └────┬──────────────────────────────────────────────────────────────────────────────┘  │
│       │                                                                                 │
│  ┌── components/ ─────────────────────────────────────────────────────────────────────┐  │
│  │       MessageContent │ MessageList │ ToolMessage │ ToolBlock                      │  │
│  │ modals/: ConfirmModal │ SimpleConfirmModal │ LongRunConfirmModal │ Rollback...    │  │
│  │         AttachmentPreview                                                         │  │
│  │ workspace/: FileExplorer │ FilePreview │ FileTreeNode                             │  │
│  │ sidebar/: PlanWidget                                                              │  │
│  │ common/: Card │ DebugPanel │ SplashScreen │ GuideOverlay                          │  │
│  └────────────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                         │
│  ┌── stores/ ──────────────────┐ ┌── layouts/ ─────────┐                                │
│  │ conversation │ session │ ui │ │ DashboardLayout     │                                │
│  │ workspace │ knowledge       │ │ DefaultLayout       │                                │
│  │ connection │ agent │ guide  │ └─────────────────────┘                                │
│  │ skill                       │                                                        │
│  └─────────────────────────────┘                                                        │
│                                                                                         │
│  ┌── src-tauri/ (桌面壳) ─────────────────────────────────────────────────────────────┐  │
│  │ main.rs │ Cargo.toml │ tauri.conf.json │ build.rs │ icons/ │ binaries/             │  │
│  └────────────────────────────────────────────────────────────────────────────────────┘  │
│       │  HTTP / SSE / WebSocket                                                         │
└───────┼─────────────────────────────────────────────────────────────────────────────────┘
        │
┌───────▼─────────────────────────────────────────────────────────────────────────────────┐
│                          路由层 (routers/)  — FastAPI Endpoints                          │
│                                                                                         │
│  chat.py │ agents.py │ conversation.py │ skills.py │ settings.py                       │
│  models.py │ human_confirmation.py │ websocket.py                                      │
└───────┬─────────────────────────────────────────────────────────────────────────────────┘
        │
┌───────▼─────────────────────────────────────────────────────────────────────────────────┐
│                          服务层 (services/)  — Business Logic                            │
│                                                                                         │
│  chat_service.py │ session_service.py │ agent_registry.py │ conversation_service.py     │
│  confirmation_service.py │ settings_service.py │ knowledge_service.py                   │
│  mcp_client.py │ user_task_scheduler.py                                                 │
└───────┬─────────────────────────────────────────────────────────────────────────────────┘
        │
┌───────▼─────────────────────────────────────────────────────────────────────────────────┐
│                          核心层 (core/)  — Agent Framework                               │
│                                                                                         │
│  ┌─── agent/ ── Agent 引擎 ───────────────────────────────────────────────────────────┐ │
│  │  base.py (SimpleAgent)                                                             │ │
│  │  factory.py (AgentFactory) │ models.py │ protocol.py │ content_handler.py │ errors │ │
│  │                                                                                    │ │
│  │  ┌── execution/ ────────────────────────────────────────────────────────────────┐  │ │
│  │  │  rvr.py (RVR 执行器)  │  rvrb.py (RVR-B 回溯执行器)                         │  │ │
│  │  │  protocol.py (ExecutionStrategy)                                             │  │ │
│  │  └──────────────────────────────────────────────────────────────────────────────┘  │ │
│  │  ┌── backtrack/ ────────────────────────────────────────────────────────────────┐  │ │
│  │  │  error_classifier.py (错误分类) │ manager.py (回溯管理)                       │  │ │
│  │  └──────────────────────────────────────────────────────────────────────────────┘  │ │
│  │  ┌── context/ ──────────┐  ┌── tools/ ──────────────────────────────────────────┐ │ │
│  │  │  prompt_builder.py   │  │  flow.py │ special.py                              │ │ │
│  │  └──────────────────────┘  └────────────────────────────────────────────────────┘ │ │
│  │  components/__init__.py                                                            │ │
│  └────────────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                         │
│  ┌─── routing/ ── 意图路由 ───────────────────────────────────────────────────────────┐ │
│  │  intent_analyzer.py (LLM 意图分析, fast_mode/semantic_cache)                       │ │
│  │  router.py (AgentRouter) │ intent_cache.py (语义缓存) │ types.py (IntentResult)    │ │
│  └────────────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                         │
│  ┌─── context/ ── 上下文工程 ─────────────────────────────────────────────────────────┐ │
│  │  context_engineering.py │ provider.py │ runtime.py │ failure_summary.py             │ │
│  │  ┌── injectors/ ──────────────────────────────────────────────────────────────┐    │ │
│  │  │  base.py │ orchestrator.py │ context.py                                    │    │ │
│  │  │  phase1/: system_role.py │ history_summary.py │ tool_provider.py            │    │ │
│  │  │          skill_focus.py (复杂度驱动 Skill 聚焦)                             │    │ │
│  │  │  phase2/: user_memory.py │ playbook_hint.py │ knowledge_context.py          │    │ │
│  │  │  phase3/: gtd_todo.py │ page_editor.py                                     │    │ │
│  │  └────────────────────────────────────────────────────────────────────────────┘    │ │
│  │  ┌── compaction/ ──────────────────┐  ┌── providers/ ───────────────────────┐      │ │
│  │  │  summarizer.py │ tool_result.py │  │  metadata.py                        │      │ │
│  │  └─────────────────────────────────┘  └─────────────────────────────────────┘      │ │
│  └────────────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                         │
│  ┌─── memory/ ── 记忆系统 ────────────────────────────────────────────────────────────┐ │
│  │                   ┌─────────────────────────────────────┐                          │ │
│  │                   │ xiaodazi_memory.py                   │                          │ │
│  │                   │ 三层入口: recall / remember / flush  │                          │ │
│  │                   └──────────┬──────────────────────────┘                          │ │
│  │          ┌───────────────────┼──────────────────────┐                              │ │
│  │  ┌───────▼──────┐  ┌────────▼──────┐  ┌────────────▼──────────────────────┐        │ │
│  │  │ Layer 1      │  │ Layer 2       │  │ Layer 3: mem0/                    │        │ │
│  │  │ markdown_    │  │ GenericFTS5   │  │  pool.py (向量搜索)               │        │ │
│  │  │ layer.py     │  │ (全文索引)    │  │  config.py │ sqlite_vec_store.py  │        │ │
│  │  │ (MEMORY.md)  │  │              │  │  extraction/: extractor.py        │        │ │
│  │  └──────────────┘  └──────────────┘  │  retrieval/: formatter │ reranker  │        │ │
│  │                                       │  schemas/: behavior │ emotion     │        │ │
│  │                                       │    explicit_memory │ fragment     │        │ │
│  │  ┌── 通用记忆模块 ──────────┐         │    persona │ plan                │        │ │
│  │  │ base.py │ manager.py    │         │  update/: quality_control          │        │ │
│  │  │ working.py              │         │    aggregator │ analyzer │ planner │        │ │
│  │  │ system/: cache │ skill  │         │    persona_builder │ prompts      │        │ │
│  │  │ user/: episodic │ plan  │         │    reminder │ reporter            │        │ │
│  │  │        preference       │         └──────────────────────────────────┘        │ │
│  │  └─────────────────────────┘                                                      │ │
│  └────────────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                         │
│  ┌─── knowledge/ ── 知识检索 ─────────────────────────────────────────────────────────┐ │
│  │  local_search.py (FTS5 + 向量混合搜索，加权合并去重)                               │ │
│  │  file_indexer.py (增量索引 + 分块 + 批量 embedding)                                │ │
│  │  embeddings.py (Embedding 提供商抽象：OpenAI / 本地模型 / auto 降级)               │ │
│  └────────────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                         │
│  ┌─── planning/ ────────────┐  ┌─── termination/ ──────────┐  ┌─── state/ ───────────┐ │
│  │  progress_transformer.py │  │  adaptive.py               │  │  consistency_mgr.py  │ │
│  │  dag_scheduler.py        │  │  八维度终止判断             │  │  (快照/回滚)         │ │
│  │  protocol.py             │  │  protocol.py               │  │  operation_log.py    │ │
│  │  storage.py │ validators │  │  (BaseTerminator)          │  │  (逆操作)            │ │
│  └──────────────────────────┘  └────────────────────────────┘  └──────────────────────┘ │
│                                                                                         │
│  ┌─── llm/ ── LLM 接口 ─────────────────────────────────────────────────────────────┐  │
│  │  base.py (BaseLLM) │ claude.py │ openai.py │ gemini.py │ qwen.py                 │  │
│  │  adaptor.py │ router.py │ model_registry.py │ registry.py                        │  │
│  │  health_monitor.py │ tool_call_utils.py                                          │  │
│  └───────────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                         │
│  ┌─── events/ ── 事件系统 ───────────────────────────────────────────────────────────┐  │
│  │  broadcaster.py │ base.py │ dispatcher.py │ manager.py │ storage.py               │  │
│  │  content_events │ conversation_events │ message_events │ session_events           │  │
│  │  system_events │ user_events                                                     │  │
│  │  adapters/: dingtalk.py │ feishu.py │ slack.py │ webhook.py │ base.py             │  │
│  └───────────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                         │
│  ┌─── prompt/ ── 提示词工程 ────────────────┐  ┌─── skill/ ── Skill 管理 ────────────┐ │
│  │  runtime_context_builder.py              │  │  dynamic_loader.py (运行时依赖检查) │ │
│  │  skill_prompt_builder.py                 │  │  loader.py (SkillsLoader 解析配置)  │ │
│  │  complexity_detector.py │ llm_analyzer.py│  │  models.py (SkillEntry/BackendType) │ │
│  │  framework_rules.py │ prompt_layer.py    │  │  os_compatibility.py (OS 四状态)    │ │
│  │  instance_cache.py                       │  └────────────────────────────────────┘ │
│  │  intent_prompt_generator.py              │                                         │
│  │  prompt_results_writer.py                │  ┌─── tool/ ── 工具管理 ──────────────┐ │
│  └──────────────────────────────────────────┘  │  registry.py │ executor.py          │ │
│                                                 │  selector.py │ validator.py         │ │
│  ┌─── discovery/ ── 应用发现 ────────────────┐  │  types.py │ loader.py              │ │
│  │  app_scanner.py                           │  │  llm_description.py                │ │
│  │  macOS ✅  Win32 ❌  Linux ❌              │  │  registry_config.py                │ │
│  └───────────────────────────────────────────┘  │  capability/: skill_loader.py       │ │
│                                                  └────────────────────────────────────┘ │
│  ┌─── 其他核心模块 ──────────────────────────────────────────────────────────────────┐  │
│  │  nodes/: manager.py │ protocol.py                                                │  │
│  │    executors/: base.py │ shell.py                                                │  │
│  │    local/: base.py │ macos.py                                                    │  │
│  │  orchestration/: code_orchestrator.py │ code_validator.py │ pipeline_tracer.py    │  │
│  │  inference/: semantic_inference.py                                               │  │
│  │  guardrails/: adaptive.py                                                        │  │
│  │  evaluation/: reward_attribution.py                                              │  │
│  │  output/: formatter.py                                                           │  │
│  │  monitoring/: production_monitor │ failure_detector │ failure_case_db             │  │
│  │    quality_scanner │ token_audit │ case_converter                                │  │
│  │  playbook/: manager.py │ storage.py                                              │  │
│  │  schemas/: validator.py                                                          │  │
│  │  config/: loader.py                                                              │  │
│  └───────────────────────────────────────────────────────────────────────────────────┘  │
└───────┬─────────────────────────────────────────────────────────────────────────────────┘
        │
┌───────▼─────────────────────────────────────────────────────────────────────────────────┐
│                          基础设施层 (infra/)                                             │
│                                                                                         │
│  ┌─── local_store/ ────────────────────────────────────────────────────────────────────┐ │
│  │  engine.py — aiosqlite + WAL + 7 项 PRAGMA 优化                                   │ │
│  │  models.py — ORM 模型 + LocalIndexedFile                                          │ │
│  │  fts.py — 消息专用 FTS5                                                           │ │
│  │  generic_fts.py — 通用 FTS5（知识/记忆共用，CJK 字符级分割 + 逆向合并）            │ │
│  │  vector.py — sqlite-vec 向量搜索（知识 + Mem0 共用）                               │ │
│  │  workspace.py — 统一管理器    │  pools.py — 连接池                                 │ │
│  │  session_store.py — 会话存储  │  skills_cache.py — Skills 延迟加载缓存             │ │
│  │  crud/: conversation.py │ message.py │ scheduled_task.py                           │ │
│  └─────────────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                         │
│  ┌─── resilience/ ──────────────────────┐  ┌─── storage/ ────────────────────────────┐  │
│  │  circuit_breaker.py │ fallback.py    │  │  base.py │ local.py │ async_writer.py   │  │
│  │  retry.py │ timeout.py │ config.py   │  │  batch_writer.py │ storage_manager.py   │  │
│  └──────────────────────────────────────┘  └──────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

### 0.2 请求处理数据流

```
用户请求 (HTTP/SSE)
   │
   ▼
┌──────────────────────────────────────────────────────────────────────┐
│ routers/chat.py  POST /chat  →  SSE 流式响应                         │
└──┬───────────────────────────────────────────────────────────────────┘
   │
   ▼
┌──────────────────────────────────────────────────────────────────────┐
│ services/chat_service.py                                             │
│   1. session_service → 获取/创建会话                                   │
│   2. agent_registry → 获取 Agent 实例                                 │
│   3. 调用 agent.chat()                                                │
└──┬───────────────────────────────────────────────────────────────────┘
   │
   ▼
┌──────────────────────────────────────────────────────────────────────┐
│ core/routing/  — 意图路由                                             │
│   IntentAnalyzer.analyze()  →  IntentResult                          │
│     ├── fast_mode (haiku 快速分析)                                    │
│     ├── semantic_cache (语义缓存)                                     │
│     └── simplified_output                                            │
│   AgentRouter.route()  →  选择执行策略                                 │
└──┬───────────────────────────────────────────────────────────────────┘
   │
   ▼
┌──────────────────────────────────────────────────────────────────────┐
│ core/agent/base.py  — SimpleAgent.execute()                          │
│   1. 状态快照 (consistency_manager.snapshot())                        │
│   2. 上下文构建 (context_engineering + injectors phase1→2→3)         │
│   3. 选择执行策略 → RVR 或 RVR-B                                      │
│   4. 终止策略评估 (adaptive_terminator.evaluate())                    │
│   5. 成功 → 提交 / 失败 → 回滚                                        │
└──┬───────────────────────────────────────────────────────────────────┘
   │
   ├──────────────────────────────────────────────┐
   ▼                                              ▼
┌──────────────────────┐            ┌──────────────────────────────────┐
│ execution/rvr.py     │            │ execution/rvrb.py                │
│ React-Validate-      │            │ React-Validate-Reflect-Backtrack │
│ Reflect              │            │ RVR-B                           │
│  1. LLM 推理         │            │  1. LLM 推理                     │
│  2. 工具执行         │            │  2. 工具执行                     │
│  3. 验证结果         │            │  3. 验证结果                     │
│  4. 反思改进         │            │  4. 错误分类 (error_classifier)  │
│                      │            │  5. 智能回溯 (backtrack/manager) │
│                      │            │  6. 规划调整                     │
└──────────────────────┘            └──────────────────────────────────┘
   │
   ▼
┌──────────────────────────────────────────────────────────────────────┐
│ 并行异步处理                                                          │
│  ├── 记忆提取: xiaodazi_memory.flush → FragmentExtractor → 双写      │
│  ├── 事件广播: broadcaster → SSE → 前端                               │
│  ├── 后台任务: title_generation / mem0_update / recommended_questions │
│  └── 知识索引: file_indexer → generic_fts → FTS5 增量索引             │
└──────────────────────────────────────────────────────────────────────┘
```

### 0.3 存储架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                    SQLite 统一存储 (WAL 模式)                        │
│                                                                     │
│  ┌── 主数据库 (zenflux.db / xiaodazi.db) ───────────────────────┐   │
│  │                                                              │   │
│  │  ┌── ORM 表 ──────────────────────────────────────────────┐  │   │
│  │  │ conversations │ messages │ scheduled_tasks              │  │   │
│  │  │ agents │ sessions │ local_indexed_files                 │  │   │
│  │  └────────────────────────────────────────────────────────┘  │   │
│  │                                                              │   │
│  │  ┌── FTS5 虚拟表 ─────────────────────────────────────────┐  │   │
│  │  │ messages_fts  — 消息全文搜索 (fts.py)                   │  │   │
│  │  │ knowledge_fts — 知识检索 (generic_fts.py)               │  │   │
│  │  │ memory_fts    — 记忆索引 (generic_fts.py)               │  │   │
│  │  │ CJK 字符级分割 + BM25 排序 + snippet 逆向合并           │  │   │
│  │  └────────────────────────────────────────────────────────┘  │   │
│  │                                                              │   │
│  │  ┌── sqlite-vec 向量表 ───────────────────────────────────┐  │   │
│  │  │ mem0 vectors     — Mem0 语义搜索 (vector.py)           │  │   │
│  │  │ knowledge_vectors — 知识检索语义搜索 (vector.py)        │  │   │
│  │  └────────────────────────────────────────────────────────┘  │   │
│  │                                                              │   │
│  │  PRAGMA: synchronous=NORMAL │ temp_store=MEMORY              │   │
│  │          busy_timeout=5000  │ mmap_size=256MB                │   │
│  │          journal_mode=WAL   │ cache_size=-64000              │   │
│  │          foreign_keys=ON                                     │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌── 文件系统存储 ──────────────────────────────────────────────┐   │
│  │  ~/.xiaodazi/MEMORY.md              — 用户记忆文件            │   │
│  │  ~/.xiaodazi/projects/*/MEMORY.md   — 项目级记忆              │   │
│  │  workspace/*.json                   — 工作区配置              │   │
│  │  data/local_store/                  — SQLite 数据库文件       │   │
│  └──────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

### 0.4 实例配置层（分级配置架构）

**设计原则**：桌面端 peer 节点，非 server 中心化管理。每个配置项只出现在一个文件中，零冲突。

```
instances/xiaodazi/                        ← 小搭子（桌面端主实例）
├── .env                                   敏感信息（API Keys），gitignored
├── .env.example                           .env 模板（提交到 git）
│
├── config.yaml                            用户配置（~200 行，用户唯一需要关心的文件）
│   ├── instance / persona / user_prompt   基础信息 + 个性化 + 自定义指令
│   ├── agent.provider                     一键切换所有模型（"qwen" / "claude"）
│   └── memory / planning / playbook       记忆 / 规划 / 策略学习
│
├── config/                                分级配置（按需查看）
│   ├── skills.yaml                        Skills 管理（~170 行）
│   │   ├── skill_groups                   意图驱动按需注入分组
│   │   └── skills                         OS × 复杂度 二维分类清单
│   │       ├── common (builtin/lightweight/external/cloud_api)
│   │       ├── darwin / win32 / linux
│   │       └── MCP Skills 连接信息内聚在 skill 条目内（无独立 mcp_tools）
│   │
│   └── llm_profiles.yaml                  框架内部 LLM 配置（~190 行，高级）
│       ├── provider_templates             Provider 模板（qwen/claude 一键切换）
│       │   ├── agent_model + agent_llm    主 Agent 模型 + LLM 参数（随 provider 切换）
│       │   ├── heavy / light              复杂/轻量任务模型分配
│       │   └── temperature 规范           0=精准 / 0.8=生成 / thinking 时框架自动
│       └── llm_profiles                   13 个内部调用点（tier + 专属参数）
│
├── prompt.md / prompt_desktop.md          人格提示词 + Few-Shot
├── prompt_results/                        LLM 推断缓存（simple/medium/complex 提示词）
└── skills/                                Skill 目录（每个 Skill 一个 SKILL.md）
    └── 40+ Skills（MCP 也封装为 Skill，用户只看到 Skill 名称）

Provider 一键切换模型分配：

  ┌──────────┬───────────────────────────┬──────────────────────────┐
  │ 角色     │ qwen                      │ claude                   │
  ├──────────┼───────────────────────────┼──────────────────────────┤
  │ 主 Agent │ qwen3-max                 │ claude-sonnet-4-5        │
  │ heavy    │ qwen3-max                 │ claude-sonnet-4-5        │
  │ light    │ qwen-plus                 │ claude-haiku-4-5         │
  └──────────┴───────────────────────────┴──────────────────────────┘
  可选覆盖: agent.model: "claude-opus-4-6"（Opus 4.6，最强但贵）
```

### 0.5 支撑模块完整清单

```
┌─── models/ (Pydantic 数据模型) ─────────────────────────────────────┐
│  agent.py │ api.py │ chat.py │ chat_request.py │ database.py        │
│  docs.py │ hitl.py │ llm.py │ mcp.py                               │
│  scheduled_task.py │ skill.py │ usage.py                            │
└─────────────────────────────────────────────────────────────────────┘

┌─── prompts/ (提示词模板) ───────────────────────────────────────────┐
│  intent_recognition_prompt.py │ plan_generator_prompt.py            │
│  prompt_selector.py │ simple_prompt.py │ standard_prompt.py         │
│  universal_agent_prompt.py │ MEMORY_PROTOCOL.md                     │
│  factory/: schema_generator.md                                      │
│  fragments/: code_rules.md │ excel_rules.md │ ppt_rules.md          │
│  templates/: complex_prompt_generation.md │ medium_prompt_generation │
│              simple_prompt_generation.md │ intent_prompt_generation  │
└─────────────────────────────────────────────────────────────────────┘

┌─── tools/ (可调用工具) ────────────────────────────────────────────┐
│  base.py │ api_calling.py │ nodes_tool.py │ observe_screen.py      │
│  plan_todo_tool.py │ request_human_confirmation.py                  │
│  scheduled_task_tool.py │ knowledge_search.py                       │
└─────────────────────────────────────────────────────────────────────┘

┌─── utils/ (工具函数) ──────────────────────────────────────────────┐
│  app_paths.py │ cache_utils.py │ file_handler.py │ file_processor.py│
│  instance_loader.py │ json_file_store.py │ json_utils.py            │
│  message_utils.py │ query_utils.py                                  │
│  background_tasks/:                                                 │
│    scheduler.py │ registry.py │ service.py │ context.py             │
│    tasks/: mem0_update.py │ recommended_questions.py                │
│            title_generation.py                                      │
└─────────────────────────────────────────────────────────────────────┘

┌─── config/ (框架级配置) ──────────────────────────────────────────────┐
│  capabilities.yaml │ context_compaction.yaml │ prompt_config.yaml    │
│  resilience.yaml │ scheduled_tasks.yaml │ tool_registry.yaml        │
│  custom_models.yaml                                                  │
│  llm_config/: __init__.py │ loader.py（set_instance_profiles 注入） │
│               qwen_recommended_configs.md                            │
│                                                                      │
│  注：LLM Profiles 已迁移到实例级 config/llm_profiles.yaml，           │
│      框架级 llm_config/loader.py 仅负责注入/查询，不存储配置。        │
│      context.yaml / routing_rules.yaml 已删除（配置内聚到实例级）。   │
└──────────────────────────────────────────────────────────────────────┘

┌─── skills/ (全局技能库) ───────────────────────────────────────────┐
│  library/: 80+ Skills (与 client_agent 共用)                        │
└─────────────────────────────────────────────────────────────────────┘

┌─── evaluation/ (评估框架) ─────────────────────────────────────────┐
│  harness.py │ metrics.py │ models.py │ qos_config.py │ calibration │
│  dashboard.py │ loop_automation.py │ alerts.py │ ci_integration.py │
│  promptfoo_adapter.py │ case_converter.py │ case_reviewer.py        │
│  verify_imports.py                                                  │
│  adapters/: http_agent.py (E2E → FastAPI 桥接)                     │
│  graders/: code_based.py │ human.py │ model_based.py                │
│  config/: settings.yaml │ judge_prompts.yaml                        │
│  suites/: coding/ │ conversation/ │ intent/                         │
│           xiaodazi/e2e/phase1_core.yaml (4 个 E2E 用例)             │
│           xiaodazi/feasibility/ (7 个可行性测试)                     │
│           xiaodazi/efficiency/ (4 个效率测试)                        │
│           xiaodazi/e2e_regression_*.yaml (回归测试)                  │
│  reports/: e2e_phase1_*.json │ e2e_phase1_*.md                      │
└─────────────────────────────────────────────────────────────────────┘

┌─── scripts/ (运维与验证脚本) ──────────────────────────────────────┐
│  verify_v11_architecture.py │ verify_memory_knowledge.py            │
│  verify_e2e_consistency.py │ verify_eval_loop.py                    │
│  sync_capabilities.py │ switch_provider.py (Claude↔Qwen 一键切换)  │
│  check_instance_dependencies.py │ init_instance_xiaodazi.py         │
│  run_e2e_auto.py (自动化 E2E 测试) │ run_e2e_eval.py               │
│  run_eval.py │ run_xiaodazi_eval.py │ generate_eval_report.py       │
│  build_app.sh │ build_backend.py │ sync_version.py                  │
└─────────────────────────────────────────────────────────────────────┘

┌─── 根目录文件 ─────────────────────────────────────────────────────┐
│  main.py (FastAPI 入口) │ config.yaml (应用配置) │ zenflux-backend.spec │
└─────────────────────────────────────────────────────────────────────┘
```

### 0.6 模块完成度热力图

```
██████████  95%  Agent 引擎层 (V11.0 统一 RVR-B / 回溯 / 错误分类)
██████████  95%  自适应终止策略 (八维度 + 费用阶梯 HITL)
██████████  95%  实例骨架与配置 (三文件分级 + Provider 一键切换)
██████████  95%  存储层 (SQLite + FTS5 + sqlite-vec)
█████████░  90%  状态一致性管理 (快照/回滚)
█████████░  90%  意图识别简化 (V11.0 极简输出 + skill_groups 语义多选)
█████████░  90%  上下文注入器 (7 个 Phase Injector 全部就绪)
████████░░  85%  记忆系统 (三层架构)
████████░░  85%  进度转换与事件推送 (ProgressTransformer + emit_progress_update)
████████░░  85%  Skills 二维分类框架 (38 个 Skill 已创建 + SkillsLoader)
█████████░  90%  本地知识检索 (FTS5 + 向量混合搜索)
████████░░  80%  E2E 评估框架 (4 个端到端用例 + 自动化运行器)
███████░░░  75%  三大核心能力
███████░░░  75%  Skill 格式规范 (SKILL.md + 二维元数据)
███████░░░  70%  Playbook 持续学习 (Hint 注入已实现，端到端链路待串联)
████░░░░░░  40%  OS 兼容层 (仅 macOS)
███░░░░░░░  35%  应用发现 (仅 macOS 扫描)
████████░░  80%  项目管理 (多实例架构，前端创建项目流程已实现)
████████░░  80%  前端 Settings (Provider 卡片 + API Key 验证 + 保存)
████████░░  80%  首次启动引导 (9 步交互式引导教程)
░░░░░░░░░░   0%  Skills 安全验证
```

---

## 一、当前智能体与 LLM（要点）

| 项 | 说明 |
|----|------|
| **LLM 切换** | `config.yaml` 的 `agent.provider` 一键切换所有模型（qwen/claude）。Provider 模板定义在 `config/llm_profiles.yaml`，包含 agent_model + agent_llm + heavy/light 分级。13 个内部 LLM 调用点通过 `tier` 字段自动解析为对应 provider 的模型。temperature 规范：0（精准）/ 0.8（生成）/ thinking 开启时框架自动设置。 |
| **Profile 解析** | `instance_loader.py` 的 `_resolve_llm_profiles()` 将 tier-based 配置展开为完整 profile dict，注入 `set_instance_profiles()`。各 profile 可通过显式 provider/model 跳过模板解析（单点覆盖）。 |
| **意图路由** | 单一入口：`IntentAnalyzer`（`core/routing/intent_analyzer.py`）。V11.0 极简输出（complexity + skip_memory + is_follow_up + wants_to_stop + relevant_skill_groups），上下文过滤 &lt;200ms。`relevant_skill_groups` 由 LLM 语义多选，驱动按需 Skill 注入。 |
| **执行策略** | V11.0 统一 RVR-B（错误分类 + BacktrackManager + 终止联动）。complexity 仅影响规划深度和 Skill 聚焦（通过 `SkillFocusInjector`），不再路由到不同执行器。终止：八维度 + 费用阶梯 HITL + 回溯耗尽/意图澄清。 |
| **记忆** | 三层：MEMORY.md 文件层、GenericFTS5 索引层、Mem0 向量层；recall/remember/flush 统一入口。Playbook 已配置（auto_extract、require_user_confirm、FileStorage）。 |

---

## 二、整体完成度概览

| 架构层 | 设计章节 | 完成度 | 状态 |
|--------|----------|--------|------|
| 实例骨架与配置 | 1.1 | 95% | 已完成（三文件分级 + Provider 一键切换） |
| Skills 二维分类 | 3.1.1 | 85% | 框架完成，38 个 Skill 已创建，SkillsLoader 统一加载 |
| 自适应终止策略 | 3.4 | 95% | 已完成 |
| 状态一致性管理 | 3.3 | 90% | 已完成 |
| Agent 引擎层 | — | 95% | V11.0 统一 RVR-B，complexity 仅影响规划深度 |
| 意图识别简化 | 3.7.1 | 90% | 已完成（V11.0 极简输出 + `relevant_skill_groups` 语义多选） |
| 上下文注入器 | — | 90% | 7 个 Phase Injector（含 skill_focus + playbook_hint + knowledge_context） |
| 进度转换器 | 3.7.2 | 85% | 已完成 |
| 本地知识检索 | 3.8 | 90% | FTS5 + 向量混合搜索已完成，知识工具 + 上下文注入器已实现 |
| 记忆系统 | 3.13 | 85% | 三层架构已完成 |
| Nodes 本地操作 | 3.5 | 80% (macOS) | macOS 11 项操作完整，win32/linux 待实现 |
| OS 兼容层 | 3.5 | 40% | 仅 macOS 实现 |
| 应用发现 | 3.11 | 35% | 仅 macOS 扫描 |
| 项目管理 | 3.10 | 80% | 多实例架构 + 前端创建项目流程（CreateProjectView） |
| 存储层 | — | 95% | SQLite + FTS5 + sqlite-vec 完整 |
| Playbook 持续学习 | 2.14 | 70% | Hint 注入器已实现，端到端链路 4 条断 2 条 |
| Skill 格式规范 | 3.2 | 75% | 基础格式 + SKILL.md 二维元数据，38 个 Skill 已适配 |
| E2E 评估框架 | — | 80% | 4 个端到端用例 + 自动化运行器 + 评分体系 |
| 屏幕观察工具 | 3.5 | 80% | peekaboo + Vision OCR 并行，macOS 就绪 |
| 前端 Settings UI | 3.1.2 | 80% | Provider 卡片式设置 + API Key 在线验证 + 自动保存默认模型 |
| 首次启动引导 | 3.1.3 | 80% | 9 步交互式引导（设置→创建项目），含跳过控制和回退机制 |
| 前端通用弹窗 | — | 100% | SimpleConfirmModal 替代 confirm/alert，支持 4 种类型 |
| Skills 安全验证 | 3.12 | 0% | 未开始 |
| 服务状态仪表板 | 3.1.5 | 0% | 未开始（前端 UI 范畴） |
| MCP Apps UI | 3.6 | 0% | 未开始（前端 UI 范畴） |
| 三大核心能力 | 3.9 | 75% | "会干活"完整，"会思考"完整，"会学习"部分完成 |

---

## 三、逐模块详细状态

### 2.1 实例骨架与配置

**设计需求**：桌面端 peer 节点配置，所有用户配置集中在实例目录，零冲突分级管理。

| 文件 | 状态 | 说明 |
|------|------|------|
| `config.yaml` | 已完成 | 用户配置（~200 行）：persona / agent.provider / memory / planning / playbook / project |
| `config/skills.yaml` | 已完成 | Skills 管理（~170 行）：skill_groups + OS × 复杂度二维分类，MCP 连接信息内聚在 skill 条目 |
| `config/llm_profiles.yaml` | 已完成 | 框架 LLM（~190 行）：provider_templates（qwen/claude 一键切换）+ 13 个 tier-based profile |
| `.env` / `.env.example` | 已完成 | API Keys（gitignored）+ 模板 |
| `prompt.md` / `prompt_desktop.md` | 已完成 | 人格提示词 + Few-Shot |
| `utils/instance_loader.py` | 已完成 | 3 文件合并加载 + provider 模板解析 + MCP 从 skill 提取 |

**配置分级架构**：

```
config.yaml（必看）         → 用户配置，对话体验直接相关
config/skills.yaml（按需）   → 启用/禁用 Skill 时查看
config/llm_profiles.yaml（高级） → 框架内部 LLM 路由，普通用户不需要改
```

**关键设计决策**：
- `agent.provider` 一键切换：改一个字段，主 Agent + 13 个内部调用点 + LLM 参数（max_tokens/caching）全部自动适配
- MCP 工具统一为 Skill：`backend_type: mcp` 的 skill 条目内聚连接信息（server_url/auth），对用户和 Agent 不暴露 MCP 概念
- 每个配置 key 只出现在一个文件中：config.yaml vs skills.yaml vs llm_profiles.yaml 零键重叠
- temperature 规范：0（精准）/ 0.8（生成）/ thinking 开启时框架自动设置（Claude 强制 1.0）

---

### 2.2 Skills 二维分类体系（3.1.1）

**设计需求**：OS（common/darwin/win32/linux）× 依赖复杂度（builtin/lightweight/external/cloud_api）

| 文件 | 状态 | 说明 |
|------|------|------|
| `core/skill/loader.py` | 已完成 | `SkillsLoader`：解析 config/skills.yaml → `SkillEntry` 列表，替代原 `OSSkillMerger` |
| `core/skill/models.py` | 已完成 | `SkillEntry` / `BackendType`(local/tool/mcp/api) / `DependencyLevel` / `SkillStatus` |
| `core/skill/os_compatibility.py` | 已完成 | `CompatibilityStatus`（ready/need_auth/need_setup/unavailable）四状态 |
| `core/skill/dynamic_loader.py` | 已完成 | 运行时依赖检查（bins/env/os），`get_eligible_skills()` |
| `core/prompt/runtime_context_builder.py` | 已完成 | 含 `build_skill_status_prompt()` 注入 Skill 状态 |
| `instances/xiaodazi/config/skills.yaml` | 已完成 | Skills 管理配置（skill_groups 意图分组 + 二维分类清单） |

**Skills-First 架构（V11.0 重构）**：

```
SkillsLoader (config/skills.yaml 解析)
    ├── SkillEntry — Agent 看到的唯一能力单元
    │   ├── backend_type: local/tool/mcp/api（Agent 不感知）
    │   ├── dependency_level: builtin/lightweight/external/cloud_api
    │   └── os: common/darwin/win32/linux
    │
    ├── skill_groups — 意图驱动按需注入
    │   ├── writing: writing-assistant, writing-analyzer, style-learner, content-reformatter
    │   ├── data_analysis: excel-analyzer, excel-fixer
    │   ├── file_operation: file-manager, word-processor
    │   ├── translation: translator
    │   ├── research: literature-reviewer, paper-search, arxiv-search
    │   ├── app_automation: applescript, macos-open, macos-screenshot, app-scanner, macos-notification
    │   └── _always: local-search, app-recommender（始终注入）
    │
    └── loading_mode: "lazy", os_aware: true
```

**已创建 38 个 Skills**（`instances/xiaodazi/skills/`）：

| 分类 | Skills |
|------|--------|
| 写作 | writing-assistant, writing-analyzer, style-learner, content-reformatter, translator |
| 数据 | excel-analyzer, excel-fixer, word-processor |
| 研究 | literature-reviewer, paper-search, arxiv-search, readwise-rival |
| macOS | macos-clipboard, macos-finder, macos-notification, macos-open, macos-screenshot, applescript, apple-calendar |
| Windows | windows-clipboard, windows-notification, windows-screenshot, powershell-basic, outlook-cli, onenote |
| Linux | linux-clipboard, linux-notification, linux-screenshot, xdotool |
| 通用 | app-recommender, app-scanner, local-search, file-manager, deep-doc-reader |
| 领域 | competitive-intel, trend-spotter, nutrition-analyzer, medication-tracker |

**已完成的设计要求**：
- OS 检测 + 自动过滤（`os_aware: true`）
- 四状态管理（ready / need_auth / need_setup / unavailable）
- Skill 状态注入系统提示词
- 依赖检查（bins / env / OS 兼容性）
- 意图驱动分组注入（`skill_groups` → `IntentResult.relevant_skill_groups`）
- Skills-First 统一抽象（Agent 不感知 backend_type）
- 惰性加载（`loading_mode: "lazy"`）

**遗留**：
- `lightweight` 级别的自动 `pip install` 逻辑未实现（标记为 ready，首次使用时安装）
- `cloud_api` 级别的 API Key 检测逻辑未实现

---

### 2.3 自适应终止策略（3.4）— V12 回溯↔终止联动重构

**设计需求**：八维度终止判断（V12 从五维度扩展为八维度）

| 文件 | 状态 | 说明 |
|------|------|------|
| `core/termination/protocol.py` | 已完成 | V12: 新增 `FinishReason` 枚举（13 个终止原因） |
| `core/termination/adaptive.py` | 已完成 | V12.1: 八维度终止 + 回溯感知 + 阶梯式费用 HITL |
| `core/agent/execution/rvrb.py` | 已完成 | V12.1: 回溯↔终止联动 + HITL 三选一 |
| `core/agent/execution/rvr.py` | 已完成 | 标准 RVR 循环 |
| `core/context/runtime.py` | 已完成 | 回溯状态字段（total_backtracks / backtracks_exhausted） |

**V12 新增的设计要求**：
- 回溯感知维度（6.5）：回溯耗尽时 → `backtrack_exhausted_confirm` HITL 三选一（重试/回滚/放弃）
- 意图澄清维度（6.5）：`INTENT_CLARIFY` 回溯类型 → `intent_clarify_request` HITL 询问用户
- 回溯↔终止信息共享：`RuntimeContext.total_backtracks` / `backtracks_exhausted` / `backtrack_escalation`
- `FinishReason` 枚举：13 个结构化终止原因，统一散落的字符串（借鉴 LobeHub）
- `max_turns` 语义统一：`AdaptiveTerminatorConfig.max_turns` 对齐为 30（与 `ExecutorConfig` 一致）
- `RVRBState.max_turns` 字段移除（冗余，统一由 `ExecutorConfig` 管理）
- 回溯事件附带累计信息（`attempt`、`cumulative_backtrack_tokens`）

**V12.1 费用感知重构**：
- 移除 `max_cost_usd` / `on_cost_exceeded` 用户配置，改为智能体自主阶梯式 HITL 提醒
- 新增 `ModelPricing` 定价数据（`core/llm/model_registry.py`），各模型注册时声明真实价格
- 新增 `UsageTracker.estimate_cost()` 方法，按模型实际定价计算费用（支持混合模型调用）
- 新增 `CostAlertConfig` 阶梯阈值：`warn_threshold`($0.50) → `confirm_threshold`($2.00) → `urgent_threshold`($10.00)
- 阶梯 1（预警）：`cost_warn` SSE 事件，非阻塞提示前端
- 阶梯 2（确认）：`cost_limit_confirm` HITL 暂停询问，用户选择继续/停止
- 阶梯 3（紧急）：`cost_urgent_confirm` HITL 再次询问，决定权在用户（不强制终止）
- **原则：所有阶梯都是 HITL 询问，智能体不会主动替用户终止任务**
- 私有化部署（pricing 未知）自动跳过费用检查

**已完成的设计要求（V11 + V12 + V12.1）**：
- LLM 自主终止（`stop_reason == "end_turn"`）
- HITL 危险操作确认（`HITLConfig.require_confirmation` 列表）
- 用户主动停止（`stop_requested` 参数）
- 安全兜底（`max_turns` / `max_duration` / `idle_timeout` / `consecutive_failures`）
- 智能费用感知（`CostAlertConfig` 阶梯式 HITL 提醒，V12.1 重构）
- 长任务确认（`long_running_confirm_after_turns`）
- 连续失败时提供回滚选项（`ROLLBACK_OPTIONS` 动作）
- 回溯耗尽时 HITL 三选一（`backtrack_exhausted_confirm`，V12 新增）
- 意图澄清请求（`intent_clarify_request`，V12 新增）
- 费用超限确认（`cost_limit_confirm`，V12.1 阶梯式）
- terminator 调用包裹 `try-except`（不阻断执行）

**遗留**：
- 用户停止关键词检测（"停止"/"算了"/"取消"）未在 terminator 内实现（由上层处理）
- `on_rejection` 策略的完整前端 UI 交互未实现
- 前端 `backtrack_exhausted_confirm` / `intent_clarify_request` / `cost_limit_confirm` / `cost_warn` SSE 事件渲染待实现
- `wait_backtrack_confirm_async` / `wait_intent_clarify_async` / `wait_cost_confirm_async` 回调函数待上层注入

---

### 2.4 状态一致性管理（3.3）

**设计需求**：任务前快照 → 操作日志 → 成功提交 / 异常回滚

| 文件 | 状态 | 说明 |
|------|------|------|
| `core/state/consistency_manager.py` | 已完成 | 快照 / 操作日志 / 回滚 / 提交 / 前置检查 / 后置检查 |
| `core/state/operation_log.py` | 已完成 | `OperationRecord` + inverse-patch 自动逆操作 |
| `core/agent/base.py` | 已完成 | `execute()` 中集成快照/提交/异常回滚 |
| `core/events/broadcaster.py` | 已完成 | `emit_rollback_options()` / `emit_rollback_result()` |

**已完成的设计要求**：
- 任务前环境快照（磁盘空间/权限/应用可用性检查）
- 操作日志（`OperationRecord` 含逆操作闭包）
- 自动逆操作生成（file_write / file_create / file_delete / file_rename）
- 异常时回滚选项事件推送
- 任务成功后提交清理
- 过期快照自动清理
- 磁盘持久化（JSON 序列化/反序列化）

**遗留**：
- 一致性检查中的 `app_availability`（依赖应用是否可用）检查未实现
- `clipboard` 状态备份/恢复未实现（设计中提到）
- 回滚选项的前端 UI 交互未实现

---

### 2.5 Agent 引擎层（V11.0 统一 RVR-B）

**设计**：V11.0 统一使用 RVR-B 执行器，complexity 仅影响规划深度和 Skill 聚焦。

| 组件 | 文件 | 特性 |
|------|------|------|
| `RVRBExecutor` | `core/agent/execution/rvrb.py` | 统一执行器：回溯 + 错误分类 + 候选方案重试 |
| `RVRExecutor` | `core/agent/execution/rvr.py` | 保留但不再独立使用（所有路径映射到 RVR-B） |
| `AgentFactory` | `core/agent/factory.py` | V11.0 固定注册 RVR-B：`rvr`/`rvr-b`/`rvrb`/`simple` 全部映射到 `RVRBExecutor` |

**V11.0 架构变更**：

```
V11.0 之前（已废弃）：
  complexity == "simple"  → RVR    ← 不再使用
  complexity == "medium"  → RVR-B
  complexity == "complex" → RVR-B

V11.0 当前（统一 RVR-B）：
  所有 complexity    → RVR-B  （统一执行器）
  complexity 影响：
    - simple  → planning_depth: none, Skill 聚焦: "直接回答"
    - medium  → planning_depth: minimal（默认行为）
    - complex → planning_depth: full, Skill 聚焦: 桌面操作模式
```

**设计原则**：
- complexity 由 LLM 语义判断（LLM-First），不做关键词匹配
- 统一 RVR-B 避免策略分叉的维护成本，简单任务回溯开销可忽略
- complexity 通过 `SkillFocusInjector` 影响 Skill 聚焦提示（见 2.18）

#### RVR-B 回溯机制（Backtrack）

**核心架构**：

| 组件 | 文件 | 职责 |
|------|------|------|
| `ErrorClassifier` | `core/agent/backtrack/error_classifier.py` | 两层错误分类（基础设施 vs 业务逻辑） |
| `BacktrackManager` | `core/agent/backtrack/manager.py` | LLM 驱动的回溯决策 + 规则回退 |
| `RVRBState` | `core/agent/execution/rvrb.py` | 回溯状态（计数/失败历史/检查点） |

**回溯流程**：
```
工具执行失败
    |
    v
ErrorClassifier 分类
    ├─ 基础设施层错误（API超时/Rate Limit）→ 由 resilience 机制处理，不回溯
    └─ 业务逻辑层错误（工具选错/参数错/结果不满足）
        |
        v
BacktrackManager 决策（LLM 驱动）
    ├─ TOOL_REPLACE → 尝试替代工具
    ├─ PARAM_ADJUST → 参数调整
    ├─ PLAN_REPLAN → 重新规划
    ├─ CONTEXT_ENRICH → 补充上下文
    └─ INTENT_CLARIFY → 澄清意图

渐进式升级：PARAM_ADJUST → TOOL_REPLACE → PLAN_REPLAN → INTENT_CLARIFY
```

**2025 最新优化（已实现）**：

| 优化项 | 方法 | 原理 |
|--------|------|------|
| Context Pollution 清理 | `_clean_backtrack_results()` | 回溯后移除失败的 tool_result，替换为简洁摘要，避免错误信息污染 LLM 后续推理 |
| Contrastive Reflection | `_build_reflection_summary()` | 在重试前注入"发生了什么 + 失败的方法 + 请用不同策略"，引导 LLM 避免重复犯错 |
| 回溯消息压缩 | 同上 | 多次失败压缩为一条汇总（节省 token 预算） |
| 策略路由 | `base.py` execute | 简单任务跳过回溯开销，直接用 RVR |

---

### 2.6 本地知识检索（3.8）

**设计需求**：以文件为中心，Level 1 FTS5 零配置 / Level 2 语义搜索可选

| 文件 | 状态 | 说明 |
|------|------|------|
| `infra/local_store/generic_fts.py` | 已完成 | 通用 FTS5 引擎，CJK 字符级分割 + 逆向合并 |
| `infra/local_store/vector.py` | 已完成 | sqlite-vec 向量搜索，动态维度 |
| `core/knowledge/local_search.py` | 已完成 | `LocalKnowledgeManager`，FTS5 + 向量混合搜索 |
| `core/knowledge/file_indexer.py` | 已完成 | 增量索引 + 分块 + 批量 embedding 生成 |
| `core/knowledge/embeddings.py` | **新增** | Embedding 提供商抽象层（OpenAI / 本地 / auto 降级） |
| `tools/knowledge_search.py` | **新增** | `knowledge_search` 工具（Agent 可调用） |
| `services/knowledge_service.py` | **新增** | 知识管理器生命周期管理（单例 + 配置读取） |
| `core/context/injectors/phase2/knowledge_context.py` | **新增** | 知识库上下文自动注入器（Phase 2） |
| `infra/local_store/models.py` | 已完成 | 含 `LocalIndexedFile` 元数据模型 |
| `infra/local_store/engine.py` | 已完成 | WAL + 7 项 PRAGMA 优化 |

**搜索架构**：

```
用户查询
    │
    ▼
LocalKnowledgeManager.search()
    │
    ├── FTS5 全文搜索（Level 1，零配置，始终启用）
    │   └── BM25 排序 → bm25_rank_to_score() 归一化到 [0, 1]
    │
    ├── sqlite-vec 向量搜索（Level 2，可选）
    │   └── EmbeddingProvider.embed(query) → 余弦距离 → 相似度 [0, 1]
    │
    └── 混合合并 _merge_hybrid_results()
        ├── 以 doc_id 去重
        ├── 加权排序：score = 0.6 × vec_score + 0.4 × fts_score
        └── 最小分数阈值过滤（默认 0.05）
```

**Embedding 提供商架构**：

```
EmbeddingProvider (抽象接口)
    ├── OpenAIEmbeddingProvider
    │   └── text-embedding-3-small（1536 维），批量 API
    ├── LocalEmbeddingProvider
    │   └── sentence-transformers（推荐 BAAI/bge-m3，1024 维）
    └── create_embedding_provider("auto")
        └── 本地优先 → OpenAI 降级（无可用时报错）
```

**已完成的设计要求**：
- Level 1 全文搜索（SQLite FTS5，零配置零依赖）
- Level 2 语义搜索（sqlite-vec 向量相似度）
- 混合搜索（FTS5 + 向量并行执行 → 加权合并去重）
- BM25 分数归一化到 [0, 1]（`bm25_rank_to_score()`）
- Embedding 提供商抽象（OpenAI / 本地 / auto 降级）
- 批量 embedding 生成（`embed_batch()`，本地 10-100x 提速）
- L2 归一化（保证余弦相似度正确）
- CJK 中文搜索支持（字符级分割 + snippet 逆向合并）
- 文件分块（智能句子/段落边界切分）
- 增量索引（SHA256 hash check）
- 多格式支持（txt/md 原生，pdf/docx 可选依赖）
- FTS5 最佳实践（automerge / integrity-check / optimize / 损坏自动恢复）
- 小白用户防御（FTS5 特殊字符自动移除）
- Python 后过滤 UNINDEXED 列（跨 SQLite 版本兼容）
- `knowledge_search` 工具（Agent 可通过 tool_use 主动调用）
- `KnowledgeContextInjector`（Phase 2 自动注入相关知识到上下文）
- `knowledge_service` 服务层（单例管理 + 配置驱动初始化）
- 实例配置扩展（`semantic_enabled` / `embedding_provider` / `embedding_model`）

**遗留**：
- 文件夹监听（watchdog）未实现
- 首次使用时 UI 文件夹选择引导未实现（前端范畴）
- `knowledge_service` 尚未在 `main.py` 启动时调用 `index_configured_directories()`

---

### 2.7 记忆系统（3.13）

**设计需求**：三层架构 — 文件层（MEMORY.md）/ 索引层（FTS5）/ 智能层（Mem0）

| 文件 | 状态 | 说明 |
|------|------|------|
| `core/memory/markdown_layer.py` | 已完成 | Layer 1：MEMORY.md 模板 + 段落追加 + 每日日志 + 项目记忆 |
| `core/memory/xiaodazi_memory.py` | 已完成 | 三层入口：recall 融合搜索 / remember 双写 / flush 提取+日志 |
| `core/memory/mem0/pool.py` | 已完成 | Layer 3：Mem0 语义搜索 + 向量存储 |
| `core/memory/mem0/update/quality_control.py` | 已完成 | 冲突检测 + 更新决策（LLM 驱动） |
| `core/memory/mem0/extraction/extractor.py` | 已完成 | 碎片记忆提取（FragmentExtractor） |

**已完成的设计要求**：
- Layer 1 文件层：MEMORY.md 自动创建模板 + 段落定位追加 + 每日日志
- Layer 2 索引层：GenericFTS5 全文索引（与知识检索共用引擎）
- Layer 3 智能层：复用 Mem0MemoryPool 语义搜索 + QualityController 冲突检测 + FragmentExtractor 记忆提取
- recall 融合搜索：FTS5（BM25）+ Mem0（向量），结果合并去重
- remember 双写：MEMORY.md + FTS5 索引 + Mem0 向量存储
- flush 会话刷新：FragmentExtractor 提取 → QualityController 过滤 → remember 双写 → 每日日志
- 分类体系：preference / fact / workflow / style → MEMORY.md 段落映射
- 项目级记忆隔离（`projects/{project_id}/MEMORY.md`）
- 降级策略：Mem0 不可用时降级到文件层全文扫描

**遗留**：
- 记忆同步机制（文件监听 MEMORY.md 变更 → 自动重建索引）未实现
- 混合检索加权配置（`vector_weight` / `bm25_weight`）已在 config 中声明但未在 recall 中实际应用权重计算
- 用户可编辑 MEMORY.md 后的冲突合并（用户修改 vs 自动提取）未实现

---

### 2.8 进度转换器（3.7.2）

| 文件 | 状态 | 说明 |
|------|------|------|
| `core/planning/progress_transformer.py` | 已完成 | `transform()` + `transform_and_emit()` 集成事件系统 |
| `core/events/broadcaster.py` | — | 已完成 | `emit_progress_update()` 事件方法 |

**遗留**：
- `transform()` 当前直接使用 plan_step 描述，未做 LLM 驱动的用户友好化转换（设计要求"内部复杂，外部简单"）
- 未集成到 PlanTodoTool 的执行流程中（需在 plan 步骤完成时自动调用）

---

### 2.9 意图识别简化（3.7.1）— V11.0

| 文件 | 状态 | 说明 |
|------|------|------|
| `core/routing/intent_analyzer.py` | 已完成 | V11.0 极简输出 + skill_groups 语义多选 |
| `core/routing/intent_cache.py` | 已完成 | 语义缓存（`IntentSemanticCache`） |
| `core/routing/router.py` | 已完成 | `AgentRouter`：路由决策 |
| `core/routing/types.py` | 已完成 | `IntentResult` / `Complexity` 类型定义 |

**V11.0 输出字段（极简）**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `complexity` | SIMPLE/MEDIUM/COMPLEX | 任务复杂度 → 影响规划深度和 Skill 聚焦 |
| `skip_memory` | bool | 是否跳过记忆召回 |
| `is_follow_up` | bool | 是否追问（复用 plan_cache） |
| `wants_to_stop` | bool | 用户停止意图 |
| `relevant_skill_groups` | List[str] | **新增**：LLM 语义多选的技能组（对应 skills.yaml 中的 skill_groups） |

**已完成**：
- `fast_mode: true` 使用更快模型（如 haiku）
- `semantic_cache_threshold` 可配置（提高到 0.90 减少 LLM 调用）
- `simplified_output: true` 跳过不必要字段
- 消息过滤 `_filter_for_intent()`：仅最近 5 条 user + 最后 1 条 assistant（截断 100 字符），O(n) < 0.1ms
- `relevant_skill_groups` 语义多选：LLM 从 skill_groups 列表中选择与用户意图相关的技能组
- 提示词来源优先从 `InstancePromptCache` 获取（用户自定义），Fallback 到默认
- 保守 Fallback：LLM 失败时返回 MEDIUM 复杂度

---

### 2.10 OS 兼容层（3.5）

| 文件 | 状态 | 说明 |
|------|------|------|
| `core/discovery/app_scanner.py` | 部分实现 | `_scan_darwin()` 有实际逻辑，win32/linux 为空 |
| `core/prompt/runtime_context_builder.py` | 已完成 | macOS / Linux 能力提示词 |

**遗留**：
- `nodes/local/windows.py` — 不存在
- `nodes/local/linux.py` — 不存在
- `AppScanner._scan_win32()` — 空实现
- `AppScanner._scan_linux()` — 空实现
- `AppScanner.get_capabilities()` — 空实现
- `AppScanner.find_app_for_task()` — 空实现

---

### 2.11 项目管理（3.10）— 多实例架构

**架构决策**：不同搭子 = 不同实例（instance），天然隔离。

```
不需要复杂的 core/project/（已删除）。
每个"项目"就是一个独立的实例目录，有自己的：
  - config.yaml（模型/记忆/规划配置）
  - prompt.md（人格提示词）
  - config/skills.yaml（仅启用该场景需要的 Skills）
  - .env（共享或独立的 API Keys）
  - ~/.xiaodazi/{instance_name}/MEMORY.md（独立记忆）

instances/
├── xiaodazi/           ← 通用搭子（默认，全技能）
├── writing-buddy/      ← 写稿搭子（写作 + 风格学习 + 格式转换）
├── data-buddy/         ← 表格搭子（Excel + 数据分析 + 图表）
├── research-buddy/     ← 研究搭子（论文 + 文献 + 学术写作）
└── office-buddy/       ← 办公搭子（PPT + 邮件 + 会议纪要）
```

**工作流**：
1. 前端提供"创建新搭子"界面 → 用户选模板、填名称、选 Skills
2. 后端从 `_template/` 脚手架创建新实例目录 → 写入配置文件
3. `main` 加载指定实例 → Agent 启动
4. 切换搭子 = 切换实例

**优势**：
- 零代码隔离：配置/记忆/Skills/提示词天然独立
- 简单可靠：不需要复杂的上下文切换、知识库隔离逻辑
- 可组合：每个实例可以有完全不同的 provider/模型/温度配置

| 文件 | 状态 | 说明 |
|------|------|------|
| `instances/_template/` | 已有 | 实例脚手架模板 |
| `utils/instance_loader.py` | 已完成 | 加载任意实例的配置/提示词/Skills |
| `core/project/` | 已删除 | 整个目录已移除，多实例架构取代 |
| 前端创建界面 | 未实现 | 前端范畴 |

---

### 2.12 存储层

| 文件 | 状态 | 说明 |
|------|------|------|
| `infra/local_store/engine.py` | 已完成 | aiosqlite + WAL + 7 项 PRAGMA |
| `infra/local_store/fts.py` | 已完成 | 消息专用 FTS5 |
| `infra/local_store/generic_fts.py` | 已完成 | 通用 FTS5（知识/记忆共用） |
| `infra/local_store/vector.py` | 已完成 | sqlite-vec 向量搜索 |
| `infra/local_store/models.py` | 已完成 | ORM 模型 + LocalIndexedFile |
| `infra/local_store/workspace.py` | 已完成 | 统一管理器 |
| `infra/local_store/skills_cache.py` | 已完成 | Skills 延迟加载缓存 |

**SQLite 最佳实践合规**：
- WAL 模式（并发读写）
- `synchronous=NORMAL`（WAL 安全配置）
- `busy_timeout=5000`（避免 SQLITE_BUSY）
- `temp_store=MEMORY`（桌面端优化）
- `mmap_size=256MB`（内存映射 I/O）
- FTS5 `automerge=8`（自动后台合并）
- FTS5 `integrity-check`（完整性检查）
- CJK 字符级分割 + 逆向合并

---

### 2.13 Skill 格式规范（3.2）

**已有**：`instances/xiaodazi/skills/` 下已有部分 SKILL.md，遵循 OpenClaw 兼容格式。

**遗留**：
- `metadata.xiaodazi` 扩展字段（`dependency_level` / `ui_template` / `user_facing`）未在现有 Skills 中普及
- Skills 签名验证机制（3.12）完全未实现

---

### 2.14 Nodes 本地操作工具（3.5 OS 兼容层）

**价值定位**：Nodes 是小搭子"会干活"能力的底层执行器 — 通过它调用 shell 命令、操作剪贴板、截图、发通知、打开应用，是连接 LLM 和用户电脑的桥梁。

#### 架构

```
LLM 决策 -> tools/nodes_tool.py（NodesTool）
                |
                v
           core/nodes/manager.py（NodeManager，节点注册与路由）
                |
                v
           core/nodes/local/macos.py（MacOSLocalNode，平台实现）
                |
                v
           core/nodes/executors/shell.py（ShellExecutor，命令执行）
```

#### 文件清单

| 文件 | 状态 | 说明 |
|------|------|------|
| `tools/nodes_tool.py` | 已完成 | 工具入口：5 个 action（status/describe/run/notify/which） |
| `core/nodes/manager.py` | 已完成 | 节点管理器：注册/发现/路由 |
| `core/nodes/protocol.py` | 已完成 | 协议定义：所有支持的命令类型 |
| `core/nodes/local/base.py` | 已完成 | 本地节点基类 |
| `core/nodes/local/macos.py` | 已完成 | macOS 实现（AppleScript/截图/剪贴板等） |
| `core/nodes/executors/shell.py` | 已完成 | Shell 命令执行器（超时/安全/输出捕获） |

**总计**：架构完整。

#### macOS 已实现操作

| 操作 | 命令 | 实现 |
|------|------|------|
| Shell 命令执行 | `system.run` | 已完成 |
| 检查可执行文件 | `system.which` | 已完成 |
| 系统通知 | `system.notify` | 已完成（AppleScript） |
| AppleScript | `applescript` | 已完成 |
| 打开应用 | `open_app` | 已完成 |
| 打开 URL | `open_url` | 已完成 |
| 打开路径 | `open_path` | 已完成 |
| 屏幕截图 | `screenshot` | 已完成（screencapture） |
| 剪贴板读取 | `clipboard.get` | 已完成（pbpaste） |
| 剪贴板写入 | `clipboard.set` | 已完成（pbcopy） |
| 文字转语音 | `say` | 已完成（macOS say） |

#### 集成状态

- `config/capabilities.yaml` 中注册为 `level: 1` 核心工具（始终启用）
- 通过工具注册表动态加载，LLM 可直接调用
- `cache_stable: true`，`requires_api: false`

#### 遗留

- Windows 本地节点（`WindowsLocalNode`）— 不存在，需新建
- Linux 本地节点（`LinuxLocalNode`）— 不存在，需新建
- 协议中已定义但未实现的命令：`camera.snap`、`screen.record`、`location.get`、`canvas.present`、`browser.proxy`
- 远程节点通信（WebSocket）— 接口预留，未实现

---

### 2.15 三大核心能力总览（3.9）

| 能力 | 技术实现 | 状态 |
|------|----------|------|
| **会干活** — 工具调用 | `core/tool/` + 38 个 Skills | 已完成 |
| **会干活** — 文件/系统操作 | `core/nodes/` + `tools/nodes_tool.py` | macOS 完整（11 项操作），win32/linux 待实现（详见 2.14） |
| **会干活** — 屏幕观察 | `tools/observe_screen.py` (peekaboo + Vision OCR) | macOS 已完成（详见 2.17） |
| **会干活** — 应用联动 | `AppScanner` + `RuntimeContextBuilder` | macOS 部分完成 |
| **会思考** — 智能回溯 | `core/agent/execution/rvrb.py`（V11.0 统一） | 已完成 |
| **会思考** — 错误分类 | `core/agent/backtrack/error_classifier.py` | 已完成 |
| **会思考** — 自主规划 | `core/planning/` | 已完成 |
| **会思考** — 环境感知 | `RuntimeContextBuilder` | 已完成 |
| **会思考** — Skill 聚焦 | `SkillFocusInjector`（按 complexity 聚焦） | 已完成（详见 2.18） |
| **会学习** — 记忆系统 | `XiaodaziMemoryManager` 三层 | 已完成 |
| **会学习** — Playbook | `core/playbook/` + `PlaybookHintInjector` | 策略注入已实现，端到端链路待串联（详见 2.16） |
| **会学习** — 奖励归因 | `core/evaluation/reward_attribution.py` | 框架存在，调用链路待串联 |

---

### 2.16 Playbook 持续学习引擎

**价值定位**：从成功的任务执行中自动提取可复用策略，下次遇到类似任务时直接套用，让小搭子"用得越久，越聪明"。

**与记忆系统的互补关系**：

| 维度 | 记忆系统（Memory） | Playbook |
|------|-------------------|----------|
| 存什么 | 用户偏好/事实/习惯 | 执行策略/工具序列/质量指标 |
| 谁写入 | 对话中自动提取 | 任务成功后提取，**用户确认**入库 |
| 谁读取 | recall() 注入系统提示词 | find_matching() 注入执行计划 |
| 粒度 | 条目级（"喜欢简洁风格"） | 流程级（"写公众号的完整步骤"） |

#### 当前实现状态

| 组件 | 文件 | 状态 |
|------|------|------|
| `PlaybookEntry` 数据结构 | `core/playbook/manager.py` | 已完成：CRUD + 审核流程 + 匹配算法 |
| `extract_from_session()` | 同上 | 已完成：从 SessionReward 提取策略 |
| `find_matching()` | 同上 | 已完成：按任务上下文匹配最佳策略 |
| `FileStorage` | `core/playbook/storage.py` | 已完成：JSON 文件持久化 |
| `DatabaseStorage` | 同上 | 不可用：依赖已删除的 `infra.database` |
| 状态流转 | 同上 | 已完成：DRAFT -> PENDING_REVIEW -> APPROVED/REJECTED |

#### 关键设计问题：奖励信号来源

当前 `RewardAttribution` 用 LLM 自评判断"做得好不好"，但这是机器猜测用户满意度，不可靠。

**奖励信号来源（按可靠度排序）**：

| 来源 | 可靠度 | 实现方式 |
|------|--------|----------|
| 用户显式反馈 | 最高 | "这个结果很好！" / 点击 thumbs-up/thumbs-down |
| 用户隐式行为 | 高 | 直接使用结果 / 复制 / 保存 / 关闭不改 |
| LLM 自评 | 中 | 机器评估，仅作为初筛建议 |

**核心原则**：LLM 自评只能作为初筛生成草稿（DRAFT），最终必须经过用户确认才能入库（APPROVED）。

#### 正确的端到端链路

```
任务完成
  |
  v
LLM 自评（初筛）-> 生成候选 PlaybookEntry（DRAFT 状态）
  |
  v
推送确认事件到前端（emit_playbook_suggestion）
  |
  v
用户确认闸门：
  - 显式确认："记住这个方法吗？" -> [记住] / [不用了]
  - 隐式信号：thumbs-up -> 自动提取；大幅修改 -> 不提取
  - 延迟验证：同类任务第 2 次使用相同策略成功 -> 自动升级
  |
  v
APPROVED -> find_matching() -> 下次任务注入系统提示词
```

#### 4 条链路状态（2 条已通、2 条待串联）

| 链路 | 说明 | 状态 |
|------|------|------|
| Agent 完成 -> 生成 DRAFT | 无调用者触发提取 | ❌ 待实现：`base.py` execute 结束后调用 `extract_from_session()` |
| DRAFT -> 用户确认 | 无事件推送到前端 | ❌ 待实现：`EventBroadcaster` 新增 `emit_playbook_suggestion()` |
| 用户确认 -> APPROVED | 无确认回调处理 | ❌ 待实现：新增 API 端点接收用户确认/拒绝 |
| 新任务 -> 匹配策略注入 | **已实现** `PlaybookHintInjector` | ✅ 已完成：Phase 2 注入器，注入到 messages 层面 |

#### 匹配机制改进（LLM-First）

当前 `PlaybookEntry.matches()` 使用关键词子串匹配，**违反 LLM-First 设计原则**。改为两层语义匹配：

```
用户 query
    |
    v
Layer 1: task_type 预筛（<1ms，确定性规则，允许）
  - 过滤出同类型 APPROVED Playbook（如 content_generation）
    |
    v
Layer 2: Mem0 语义搜索（复用已有向量存储，零额外 LLM 调用）
  - 用 query 对 Playbook 描述做向量相似度匹配
  - 返回 top_k 最相关策略 + 置信度
```

优势：
- "帮我写推文" 和 "写公众号" 语义相同 -> 能匹配到同一 Playbook
- 复用 Mem0 Pool 语义搜索，零额外 LLM 调用成本
- 保留 task_type 预筛（确定性规则，符合规范允许的场景）

#### 遗留问题

- `DatabaseStorage` 依赖已删除的 `infra.database`，调用会抛 `NotImplementedError`
- LLM 描述生成提示词硬编码在方法内（应移到 prompts/ 管理）
- 项目级 Playbook 隔离（`projects/{id}/playbook/`）未实现

---

### 2.17 屏幕观察工具 — ObserveScreen

**价值定位**：让 Agent "看见"用户屏幕，获取 UI 元素和文字信息，是桌面操作自动化的感知层。

| 文件 | 状态 | 说明 |
|------|------|------|
| `tools/observe_screen.py` | 已完成 | peekaboo + Vision OCR 并行执行，macOS 就绪 |

**架构**：

```
Agent 决策："我需要看看屏幕上有什么"
    │
    ▼
tools/observe_screen.py（ObserveScreen Tool）
    │
    ├─── peekaboo see（~1.5s，本地执行）
    │    └── 返回 UI 元素 + 可交互 ID + 窗口信息
    │
    └─── macOS Vision OCR（~0.7s，本地执行）
         └── 返回 peekaboo 未捕获的文字内容
    │
    ├── 两者并行执行，结果合并
    └── 返回：窗口标题 + 可操作 UI 元素列表 + OCR 文字
```

**设计原则**：
- **工具只做本地工作**，不调用 LLM（调度是 Agent 的职责）
- **peekaboo 优先**：工业级屏幕自动化，返回可操作的元素 ID
- **上下文工程**：只在上下文中放文字描述，零图片 token 开销
- **临时文件**：截图是临时的，用完清理

**参数**：`app`（目标应用）、`window_title`（窗口标题）、`mode`（screen/window/frontmost）、`description`（描述）

**后续交互**：Agent 根据观察结果调度 Skills 操作：
- `peekaboo click --on <element_id>` — 点击元素
- `peekaboo type` — 输入文字
- `peekaboo see --analyze` — 深度分析

**平台**：仅 macOS（依赖 macOS Vision 框架）

---

### 2.18 Skill 聚焦注入器 — SkillFocusInjector

**价值定位**：根据任务复杂度减少 Agent 的认知负荷（38 个 Skills 太多，聚焦最相关的）。

| 文件 | 状态 | 说明 |
|------|------|------|
| `core/context/injectors/phase1/skill_focus.py` | 已完成 | 复杂度驱动的 Skill 聚焦提示 |

**设计原则**：
- **缓存友好**：完整 Skills 列表在缓存层（Layer 3.5），此注入器只在 DYNAMIC 层添加轻量提示
- **零额外 LLM 调用**：基于 `IntentResult.complexity`，O(1) 操作
- **降低认知负荷**：引导 Agent 聚焦最相关的能力

**复杂度 → 聚焦行为**：

| complexity | 注入内容 | 效果 |
|------------|---------|------|
| `simple` | "直接回答即可，无需读取 SKILL.md" | 跳过 Skill 加载开销 |
| `medium` | 无注入（默认行为） | Agent 自主选择 |
| `complex` | 桌面 UI 操作模式（observe → interact → verify → app management） | 引导多步骤 UI 自动化 |

**注入参数**：
- Phase 1（System Message），priority 70
- 缓存策略：DYNAMIC（每轮可能变化）

---

### 2.19 上下文注入器总览（Context Injectors）

**7 个 Phase Injector 全部就绪**，覆盖从系统角色到动态上下文的完整注入链路。

```
Phase 1: System Message 注入（缓存稳定层）
├── system_role.py          — 系统角色提示词（固定，优先缓存）
├── history_summary.py      — 历史摘要（压缩旧对话）
├── tool_provider.py        — 工具定义注入
└── skill_focus.py          — 复杂度驱动 Skill 聚焦（DYNAMIC）

Phase 2: User Context 注入（每次对话动态）
├── user_memory.py          — 用户记忆召回（recall 融合搜索）
├── playbook_hint.py        — 历史成功策略提示（SESSION 缓存）
└── knowledge_context.py    — 本地知识库上下文（DYNAMIC，≤800 tokens）

Phase 3: Runtime 注入（实时状态）
├── gtd_todo.py             — GTD 待办状态
└── page_editor.py          — 页面编辑器上下文
```

**缓存策略分层**：

| 缓存策略 | 变化频率 | 代表注入器 |
|---------|---------|-----------|
| STABLE | 几乎不变 | system_role, tool_provider |
| SESSION | 每会话变 | playbook_hint, history_summary |
| DYNAMIC | 每轮可变 | skill_focus, user_memory, knowledge_context |

---

### 2.20 E2E 评估框架

**价值定位**：端到端质量验证 — 从用户输入到 Agent 输出，自动化评分 + 根因分析。

| 文件 | 状态 | 说明 |
|------|------|------|
| `evaluation/adapters/http_agent.py` | 已完成 | E2E → FastAPI 桥接适配器 |
| `evaluation/graders/code_based.py` | 已完成 | 代码评分器（确定性检查） |
| `evaluation/graders/model_based.py` | 已完成 | 模型评分器（LLM 质量判断） |
| `evaluation/harness.py` | 已完成 | 评估运行引擎 |
| `evaluation/suites/xiaodazi/e2e/phase1_core.yaml` | 已完成 | 4 个 E2E 用例 |
| `scripts/run_e2e_auto.py` | 已完成 | 自动化运行器（启动服务 → 执行 → 报告 → 停止） |

**Phase 1 测试用例**：

| ID | 场景 | 验证点 | 评分方式 |
|-----|------|--------|---------|
| A1 | 格式混乱 Excel 分析 | RVR-B 回溯处理 + 结果质量 | code + model(≥4) |
| B1 | 跨会话记忆 | 记忆持久化 + 风格召回 | model(≥3) |
| D4 | 连续错误恢复 | ErrorClassifier + BacktrackManager | code + model(≥3) |
| C1 | 简单问答 token 对比 | Prompt Caching 命中率 | code(≤20K tokens) + model(≥3) |

**评估链路**：

```
scripts/run_e2e_auto.py
    │
    ├── 启动 uvicorn（端口 18234，避免冲突）
    ├── 等待服务就绪（轮询 /health）
    │
    ▼
evaluation/harness.py（评估引擎）
    ├── 加载 suites/xiaodazi/e2e/phase1_core.yaml
    ├── 逐用例执行：
    │   ├── adapters/http_agent.py → POST /api/v1/chat
    │   ├── 轮询 session 状态直到完成
    │   ├── 获取 messages + tool_calls + token_usage
    │   └── 运行 graders：
    │       ├── code_based: check_no_tool_errors, check_token_limit
    │       └── model_based: grade_response_quality
    │
    ▼
evaluation/reports/e2e_phase1_*.json（评分报告）
    ├── 每个用例的 grade_results
    ├── passed / score / explanation / details
    └── weaknesses → 优化方向
```

**运行方式**：

```bash
# 全量运行
python scripts/run_e2e_auto.py --clean

# 单用例调试
python scripts/run_e2e_auto.py --case A1

# 使用已运行的服务
python scripts/run_e2e_auto.py --no-start --port 8000

# 指定 Provider
python scripts/run_e2e_auto.py --provider claude
```

**扩展测试套件**（已有但非 E2E）：

| 套件 | 位置 | 说明 |
|------|------|------|
| 可行性测试 | `suites/xiaodazi/feasibility/` | 7 个场景（内容生成/桌面操作/错误恢复等） |
| 效率测试 | `suites/xiaodazi/efficiency/` | 4 个维度（路径优化/规划深度/Skill选择/Token效率） |
| 意图准确度 | `suites/intent/haiku_accuracy.yaml` | 意图识别准确率 |
| 编码能力 | `suites/coding/basic_code_generation.yaml` | 基础代码生成 |

---

## 四、前端实现详情

### 4.1 首次启动引导（3.1.3）— 9 步交互式教程

**设计需求**：新用户首次打开应用时，通过交互式引导完成 API Key 配置和首个项目创建。

| 文件 | 状态 | 说明 |
|------|------|------|
| `frontend/src/stores/guide.ts` | 已完成 | 引导状态管理（Pinia Store），9 步配置 + 2 阶段 + 验证回调 |
| `frontend/src/components/common/GuideOverlay.vue` | 已完成 | 全局引导浮层（Teleport），高亮目标元素 + tooltip + 步骤进度 |
| `frontend/src/views/settings/SettingsView.vue` | 已完成 | 集成 Step 1-4 引导目标 + 验证逻辑 |
| `frontend/src/views/chat/ChatView.vue` | 已完成 | 引导启动入口 + Step 5 引导目标 |
| `frontend/src/components/chat/ConversationSidebar.vue` | 已完成 | Step 5 创建项目按钮引导目标 |
| `frontend/src/views/project/CreateProjectView.vue` | 已完成 | Step 6-9 项目创建流程引导目标 |

**引导流程（9 步 2 阶段）**：

```
阶段一：设置配置（Step 1-4）
  Step 1: 点击设置按钮进入设置页
  Step 2: 选择一个 Provider，填写 API Key
  Step 3: 点击"验证并保存"（后端实时验证 Key 有效性）
  Step 4: 点击"返回聊天"回到主界面

阶段二：创建项目（Step 5-9）
  Step 5: 点击创建项目按钮
  Step 6: 与 AI 对话描述项目需求
  Step 7: AI 生成项目表单后填写确认
  Step 8: 确认创建项目
  Step 9: 引导完成
```

**核心机制**：

| 机制 | 说明 |
|------|------|
| 条件跳过控制 | `canSkip`：无有效 API Key 时禁止跳过引导，已配置后允许 |
| 验证回调 | `setBeforeNextStep()`：组件注册自定义验证逻辑，验证通过才允许下一步 |
| 步骤回退 | `goToStep(n)`：API Key 验证失败时自动回退到 Step 2 |
| 自动展开 | 已配置的 Provider 自动展开卡片，但高亮整个区域供用户选择 |
| 持久化 | 引导完成状态存储到 `localStorage`，刷新不重复 |
| 动态定位 | `getBoundingClientRect()` + `requestAnimationFrame` 精准定位高亮区域 |
| 浮动模式 | 部分步骤使用 `floating: true` 避免遮挡内容 |

---

### 4.2 设置页（Provider 卡片式 API Key 管理）

**设计需求**：基于 Models API 的结构化 Provider 配置，替代旧的扁平化 Key-Value 设置。

| 文件 | 状态 | 说明 |
|------|------|------|
| `frontend/src/views/settings/SettingsView.vue` | 已完成 | Provider 卡片 + 手风琴展开 + 验证保存 |
| `frontend/src/api/models.ts` | 已完成 | Models API 调用（`getSupportedProviders`, `validateKey`） |
| `frontend/src/api/settings.ts` | 已完成 | Settings API 调用（`getSettings`, `updateSettings`, `getSettingsStatus`） |

**UI 结构**：

```
SettingsView
├── Provider 卡片列表（手风琴/Accordion）
│   ├── OpenAI（展开后显示 API Key 输入框 + 已配置状态）
│   ├── Anthropic
│   ├── Qwen
│   └── ...（由 Models API 动态返回）
│
├── 验证并保存按钮（多阶段验证）
│   ├── Step 1: 检查是否选中 Provider
│   ├── Step 2: 检查 Key 是否填写
│   ├── Step 3: 调用 validateKey() 后端验证
│   ├── Step 4: 确认返回可用模型列表
│   └── Step 5: 自动设置默认模型 = 验证通过 Provider 的第一个模型
│
└── 返回聊天按钮
```

**关键设计**：
- 移除了"默认模型选择"下拉框 — 默认模型由保存时自动从当前选中 Provider 获取
- 移除了"其他设置 (Application)"区段
- 保存失败时显示错误提示 + 引导步骤自动回退
- 原生 `<select>` 下拉使用 `appearance-none` + 自定义 SVG 箭头修复样式

---

### 4.3 通用确认弹窗（SimpleConfirmModal）

**设计需求**：替代原生 `alert()` / `confirm()`，统一 UI 风格。

| 文件 | 状态 | 说明 |
|------|------|------|
| `frontend/src/components/modals/SimpleConfirmModal.vue` | 已完成 | 可复用弹窗组件，支持 4 种类型 |

**Props**：

| Prop | 类型 | 说明 |
|------|------|------|
| `show` | boolean | 是否显示 |
| `title` | string | 弹窗标题 |
| `message` | string | 弹窗内容 |
| `type` | `'confirm' \| 'warning' \| 'info' \| 'error'` | 弹窗类型（影响图标和按钮颜色） |
| `confirmText` | string | 确认按钮文本 |
| `cancelText` | string | 取消按钮文本 |
| `showCancel` | boolean | 是否显示取消按钮（`error` 类型默认隐藏） |

**使用方式（Promise 封装）**：

```typescript
// ChatView.vue 中的 showConfirm 辅助函数
const showConfirm = (opts): Promise<boolean> => {
  simpleModal.show = true;
  simpleModal.title = opts.title;
  simpleModal.message = opts.message;
  simpleModal.type = opts.type || 'confirm';
  // ...
  return new Promise(resolve => { simpleModal.resolve = resolve; });
};
```

**已替换的调用点**（ChatView.vue）：
- 删除对话 → `showConfirm({ type: 'warning' })`
- 删除历史记录 → `showConfirm({ type: 'warning' })`
- 删除项目 → `showConfirm({ type: 'warning' })`
- 启动项目（新窗口提示）→ `showConfirm({ type: 'info' })`
- 文件上传错误 → `showConfirm({ type: 'error' })`
- 项目启动失败 → `showConfirm({ type: 'error' })`

---

### 4.4 聊天欢迎页简化

| 文件 | 状态 | 说明 |
|------|------|------|
| `frontend/src/components/chat/MessageList.vue` | 已完成 | 移除了 3 张建议卡片 |

**移除内容**：
- "生成贪吃蛇游戏"、"分析项目依赖"、"搜索 RAG 论文" 三张快捷建议卡片及对应的 `suggestions` 数组
- 移除未使用的 Lucide 图标导入（`Gamepad2`, `BarChart3`, `Search`）

---

### 4.5 尚未实现的前端模块

以下模块在架构设计中定义但尚未实现：

| 需求 | 设计章节 | 说明 |
|------|----------|------|
| Skill 配置向导 | 3.1.4 | Vue 组件 |
| 服务状态仪表板 | 3.1.5 | Vue 组件 |
| MCP Apps UI | 3.6 | iframe + postMessage |
| 回滚选项 UI | 3.3 | 后端事件已就绪，前端渲染待实现 |
| 进度展示组件 | 3.7.2 | 后端事件已就绪，前端渲染待实现 |
| Playbook 确认 UI | 2.14 | 后端事件待实现，前端渲染待实现 |
| Tauri 桌面框架 | — | 桌面壳 |
| Ollama 安装向导 | 3.1.2 | 跨平台安装 UI |

---

## 五、优先级建议（后端待办）

### P0 — 核心体验缺口

| 项目 | 涉及文件 | 工作量 | 说明 |
|------|----------|--------|------|
| 停止生成功能修复 | `frontend/src/composables/useChat.ts` + `stores/session.ts` + `api/session.ts` | 小 | 暂停按钮点击后无效果，需排查 stopSession API 调用链路 |
| Playbook 端到端串联 | `core/agent/base.py` + `core/events/broadcaster.py` + `routers/` | 中 | 串联剩余 3 条链路：DRAFT 生成 → 用户确认 → APPROVED（Hint 注入已完成） |
| 实例创建 API | `routers/` + `utils/instance_loader.py` | 小 | 前端调用 → 从模板脚手架创建新实例目录 |
| 记忆混合检索权重 | `core/memory/xiaodazi_memory.py` | 小 | config 已声明 `vector_weight`/`bm25_weight`，recall 中应用 |
| ProgressTransformer 集成 | `core/planning/` | 小 | 在 PlanTodoTool 步骤完成时自动调用 |

### P1 — 完善已有功能

| 项目 | 涉及文件 | 工作量 | 说明 |
|------|----------|--------|------|
| ~~知识检索语义搜索~~ | ~~`core/knowledge/local_search.py`~~ | ~~中~~ | ✅ 已完成（FTS5 + 向量混合搜索 + Embedding 抽象层） |
| 记忆文件监听同步 | `core/memory/` | 中 | watchdog 监听 MEMORY.md 变更 |
| E2E 测试用例扩展 | `evaluation/suites/xiaodazi/e2e/` | 中 | 扩展 Phase 1 用例覆盖更多场景（当前 4 个） |
| Playbook 语义匹配 | `core/playbook/manager.py` | 小 | 替换关键词匹配为 Mem0 语义搜索（LLM-First） |

### Playbook 集成实施计划

串联 4 条断裂链路，让 Playbook 从"代码完整但无调用者"变为"端到端可用"。

**Step 1: 存储迁移** — `core/playbook/storage.py`
- 将 `DatabaseStorage` 从已删除的 `infra.database` 迁移到 `infra/local_store` 的 aiosqlite 引擎
- 或标记 `DatabaseStorage` 为不可用，默认使用 `FileStorage`（已完整实现）

**Step 2: 配置声明 ✅ 已完成** — `instances/xiaodazi/config.yaml`
```yaml
playbook:
  enabled: true
  auto_extract: true           # 任务完成后自动 LLM 初筛
  min_reward_threshold: 0.7    # 初筛最低分
  require_user_confirm: true   # 用户确认闸门（核心）
  storage_backend: "file"
  storage_path: "~/.xiaodazi/playbooks"
```
> 配置已在 `instances/xiaodazi/config.yaml` 中声明。

**Step 3: 链路 1 — 任务完成自动初筛** — `core/agent/base.py`
- 在 `execute()` 结束后、状态提交前，调用 `PlaybookManager.extract_from_session()`
- 生成 DRAFT 状态的候选策略
- 仅在 `playbook.enabled` 且 `auto_extract` 为 true 时执行

**Step 4: 链路 2 — 推送确认事件** — `core/events/broadcaster.py`
- 新增 `emit_playbook_suggestion(session_id, entry)` 事件方法
- DRAFT 生成后推送到前端，展示："小搭子学到了一个新技巧，要记住吗？"

**Step 5: 链路 3 — 确认回调 API** — `routers/` 或已有端点
- 接收用户确认/拒绝 → 调用 `PlaybookManager.approve()` 或 `reject()`
- 隐式信号处理：thumbs-up → 自动 approve，大幅修改 → 不提取

**Step 6: 链路 4 — 新任务策略注入 ✅ 已实现**

`core/context/injectors/phase2/playbook_hint.py` — `PlaybookHintInjector`

核心矛盾：Claude API 的 system prompt 缓存（`cache_control`）要求内容稳定，如果把 Playbook 策略注入 system prompt 会导致缓存全部失效、token 成本翻倍。

解决方案：**注入到 messages 层面（Phase 2 Context Injector），不动 system prompt**。

```
┌──────────────────────────────────────────┐
│ system prompt（固定，缓存命中）            │
│   ├─ 人格提示词（prompt.md）  <- 有缓存   │
│   ├─ 工具定义                 <- 有缓存   │
│   └─ 运行时环境               <- 有缓存   │
├──────────────────────────────────────────┤
│ messages（动态，不影响 system 缓存）       │
│   ├─ ...历史对话...                       │
│   ├─ [Phase 2] user_memory 注入           │
│   ├─ [Phase 2] <playbook_hint> 策略注入   │  ← 已实现
│   └─ user: "帮我写公众号"                 │
└──────────────────────────────────────────┘
```

**已实现细节**：
- 注入位置：Phase 2（User Context Message），priority 80（低于 user_memory）
- 缓存策略：SESSION（每个会话重新匹配）
- 匹配规则：query + task_type → top_k=1, min_score=0.3, only_approved
- 注入格式：`<playbook_hint>` 标签包裹，含 description / tool_sequence / quality_metrics / confidence
- LLM 引导：明确标注"仅供参考"，LLM 自主决定是否采纳

核心优势：
- system prompt 缓存命中率不受影响（成本可控）
- 复用已有 `core/context/injectors/` 架构（不新增概念）
- 注入内容受 `max_tokens` 预算控制（避免策略文本过长）
- LLM 自主决定是否采纳策略（LLM-First 原则）

**Step 7: 验证**
- 端到端测试：创建 DRAFT -> 模拟用户确认 -> 新任务匹配 -> 策略注入到 messages
- 验证 system prompt 缓存不受影响（对比注入前后的 `cache_read_tokens`）
- 验证 FileStorage 持久化 -> 重启后策略仍存在

### P2 — 跨平台扩展

| 项目 | 涉及文件 | 工作量 | 说明 |
|------|----------|--------|------|
| Windows 本地节点 | `nodes/local/windows.py` | 大 | PowerShell + WinAPI |
| Linux 本地节点 | `nodes/local/linux.py` | 中 | X11/Wayland + xdotool |
| AppScanner Win/Linux | `core/discovery/app_scanner.py` | 中 | registry/dpkg 扫描 |

### P3 — 安全与信任

| 项目 | 涉及文件 | 工作量 | 说明 |
|------|----------|--------|------|
| Skills 签名验证 | 新建 | 中 | 官方/社区/未签名三级信任 |

---

## 六、文件变更清单

### 本轮新增文件

| 文件 | 职责 |
|------|------|
| `tools/observe_screen.py` | 屏幕观察工具（peekaboo + Vision OCR） |
| `core/context/injectors/phase1/skill_focus.py` | 复杂度驱动 Skill 聚焦注入器 |
| `core/context/injectors/phase2/playbook_hint.py` | 历史成功策略 Hint 注入器 |
| `routers/websocket.py` | WebSocket 路由 |
| `evaluation/adapters/http_agent.py` | E2E → FastAPI 桥接适配器 |
| `evaluation/loop_automation.py` | 评估循环自动化 |
| `evaluation/suites/xiaodazi/e2e/phase1_core.yaml` | E2E Phase 1 测试用例（4 个） |
| `scripts/run_e2e_auto.py` | 自动化 E2E 测试运行器 |
| `scripts/run_e2e_eval.py` | E2E 评估执行器 |
| `instances/xiaodazi/.env.example` | 环境变量模板 |
| `instances/xiaodazi/config/skills.yaml` | Skills 管理配置（从 config.yaml 分离） |
| `instances/xiaodazi/config/llm_profiles.yaml` | LLM Profiles 配置（从 config.yaml 分离） |
| `instances/_template/config/skills.yaml` | 模板 Skills 配置 |
| `instances/_template/config/llm_profiles.yaml` | 模板 LLM Profiles 配置 |
| `core/knowledge/embeddings.py` | Embedding 提供商抽象层（OpenAI / 本地 / auto） |
| `tools/knowledge_search.py` | 本地知识库搜索工具 |
| `services/knowledge_service.py` | 知识管理器生命周期服务 |
| `core/context/injectors/phase2/knowledge_context.py` | 知识库上下文自动注入器 |
| `frontend/src/stores/guide.ts` | 引导状态管理（9 步 + 验证 + 跳过控制） |
| `frontend/src/stores/agent.ts` | 助手/实例状态管理 |
| `frontend/src/stores/skill.ts` | 技能状态管理 |
| `frontend/src/components/common/GuideOverlay.vue` | 全局引导浮层（Teleport + 高亮 + tooltip） |
| `frontend/src/components/modals/SimpleConfirmModal.vue` | 通用确认弹窗（替代 alert/confirm） |
| `frontend/src/api/agent.ts` | Agent API 调用层 |
| `frontend/src/types/agent.ts` | Agent 类型定义 |
| `frontend/src/views/project/CreateProjectView.vue` | 创建项目/助手页面 |

### 本轮修改的前端文件

| 文件 | 修改内容 |
|------|----------|
| `frontend/src/views/settings/SettingsView.vue` | 重构为 Provider 卡片式 UI + Models API 集成 + 验证保存 + 引导集成 |
| `frontend/src/views/chat/ChatView.vue` | 引导启动入口 + SimpleConfirmModal 替代 alert/confirm + 步骤编号调整 |
| `frontend/src/views/skills/SkillsView.vue` | 技能管理页重构 |
| `frontend/src/components/chat/MessageList.vue` | 移除 3 张建议卡片 + 未使用图标导入 |
| `frontend/src/components/chat/ConversationSidebar.vue` | 引导步骤编号调整 |
| `frontend/src/components/chat/ChatInputArea.vue` | 停止生成按钮 loading/stopping 状态传递 |

### 本轮删除文件

| 文件 | 原因 |
|------|------|
| `core/project/__init__.py` / `manager.py` / `models.py` | 多实例架构取代，不再需要独立项目管理模块 |
| `core/skill/os_skill_merger.py` | 功能并入 `SkillsLoader`（`core/skill/loader.py`） |
| `routers/projects.py` | 随 `core/project/` 一同移除 |
| `services/mcp_service.py` / `docs_service.py` | 功能重构，MCP 统一为 `mcp_client.py` |
| `routers/health.py` / `docs.py` | 路由精简 |
| `tools/send_files.py` / `clue_generation.py` | 工具整合 |
| `utils/background_tasks/tasks/clue_generation.py` | 后台任务精简 |
| `config/context.yaml` / `routing_rules.yaml` | 配置内聚到实例级 |
| `config/llm_config/README.md` / `REORGANIZATION.md` / `profiles.example.yaml` | 文档清理 |

### 早期基础文件（仍有效）

| 文件 | 职责 |
|------|------|
| `infra/local_store/generic_fts.py` | 通用 FTS5 全文搜索引擎 |
| `core/memory/markdown_layer.py` | MEMORY.md 文件层 |
| `core/memory/xiaodazi_memory.py` | 三层记忆架构入口 |
| `core/knowledge/local_search.py` | FTS5 搜索实现 |
| `core/knowledge/file_indexer.py` | 增量文件索引 |
| `core/termination/adaptive.py` | 八维度终止 + HITL |
| `core/state/consistency_manager.py` | 快照/回滚完整实现 |
| `core/events/broadcaster.py` | rollback + progress 事件 |

### 验证结果

| 验证脚本 | 结果 |
|----------|------|
| `scripts/verify_v11_architecture.py` | 119/119 通过 |
| `scripts/verify_memory_knowledge.py` | 41/41 通过 |
| `python -c "from main import app"` | 路由正常加载 |
| `scripts/run_e2e_auto.py` | E2E Phase 1 可执行（需配置 LLM） |
