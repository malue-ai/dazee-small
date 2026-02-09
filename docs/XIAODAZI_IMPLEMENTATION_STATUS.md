# 小搭子 Agent 实例 — 实现架构文档

> 基于当前代码实现的完整状态梳理。
>
> 范围：Python 后端 + 框架核心层 + Vue 前端 + Tauri 桌面壳。
>
> 更新时间：2026-02-09

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
│  │ CreateProjectView（创建 + 编辑双模式）                                             │  │
│  └────┬───────────────────────────────────────────────────────────────────────────────┘  │
│       │                                                                                 │
│  ┌────▼── composables/ ──────────────────────────────────────────────────────────────┐  │
│  │ useChat │ useSSE │ useWebSocketChat │ useHITL │ useFileUpload                     │  │
│  └────┬──────────────────────────────────────────────────────────────────────────────┘  │
│       │                                                                                 │
│  ┌────▼── api/ ──────────────────────────────────────────────────────────────────────┐  │
│  │ chat.ts │ session.ts │ config.ts │ settings.ts │ skills.ts │ workspace.ts         │  │
│  │ models.ts │ tauri.ts │ agent.ts │ knowledge.ts                                    │  │
│  └────┬──────────────────────────────────────────────────────────────────────────────┘  │
│       │                                                                                 │
│  ┌── components/ ─────────────────────────────────────────────────────────────────────┐  │
│  │ chat/: ChatHeader │ ChatInputArea │ ConversationSidebar │ MessageList              │  │
│  │       MessageContent │ MarkdownRenderer │ ToolBlock │ ToolMessage                 │  │
│  │ modals/: HITLConfirmModal │ LongRunConfirmModal │ RollbackOptionsModal             │  │
│  │         ConfirmModal │ SimpleConfirmModal │ AttachmentPreview                      │  │
│  │ workspace/: FileExplorer │ FilePreview │ FileTreeNode                              │  │
│  │ sidebar/: PlanWidget                                                               │  │
│  │ common/: Card │ DebugPanel │ SplashScreen │ GuideOverlay │ NotificationCenter      │  │
│  └────────────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                         │
│  ┌── stores/ ─────────────────────────────────────────────────────────────────────────┐  │
│  │ conversation │ session │ ui │ workspace │ knowledge │ connection │ agent │ guide   │  │
│  │ skill │ agentCreation │ notification                                               │  │
│  └────────────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                         │
│  ┌── layouts/ ────────────┐                                                             │
│  │ DashboardLayout        │                                                             │
│  │ DefaultLayout          │                                                             │
│  └────────────────────────┘                                                             │
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
│  chat.py │ agents.py │ conversation.py │ skills.py │ settings.py │ files.py            │
│  models.py │ human_confirmation.py │ websocket.py                                      │
└───────┬─────────────────────────────────────────────────────────────────────────────────┘
        │
┌───────▼─────────────────────────────────────────────────────────────────────────────────┐
│                          服务层 (services/)  — Business Logic                            │
│                                                                                         │
│  chat_service.py │ session_service.py │ agent_registry.py │ conversation_service.py     │
│  confirmation_service.py │ settings_service.py │ knowledge_service.py                   │
│  user_task_scheduler.py                                                                 │
└───────┬─────────────────────────────────────────────────────────────────────────────────┘
        │
┌───────▼─────────────────────────────────────────────────────────────────────────────────┐
│                          核心层 (core/)  — Agent Framework                               │
│                                                                                         │
│  ┌─── agent/ ── Agent 引擎 ───────────────────────────────────────────────────────────┐ │
│  │  base.py (Agent 统一实现)                                                         │ │
│  │  factory.py (AgentFactory) │ models.py │ protocol.py │ content_handler.py │ errors │ │
│  │  execution/: rvr.py │ rvrb.py │ protocol.py                                       │ │
│  │  backtrack/: error_classifier.py │ manager.py                                      │ │
│  │  context/: prompt_builder.py                                                       │ │
│  │  tools/: flow.py │ special.py                                                      │ │
│  │  components/__init__.py                                                             │ │
│  └────────────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                         │
│  ┌─── routing/ ── 意图路由 ───────────────────────────────────────────────────────────┐ │
│  │  intent_analyzer.py (三层缓存：Hash → Semantic → LLM)                              │ │
│  │  router.py (AgentRouter) │ intent_cache.py │ types.py (IntentResult)               │ │
│  └────────────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                         │
│  ┌─── context/ ── 上下文工程 ─────────────────────────────────────────────────────────┐ │
│  │  context_engineering.py │ provider.py │ runtime.py │ failure_summary.py             │ │
│  │  injectors/: base.py │ orchestrator.py │ context.py                                │ │
│  │    phase1/: system_role │ history_summary │ tool_provider │ skill_focus             │ │
│  │    phase2/: user_memory │ playbook_hint │ knowledge_context                        │ │
│  │    phase3/: gtd_todo │ page_editor                                                 │ │
│  │  compaction/: summarizer.py │ tool_result.py                                       │ │
│  │  providers/: metadata.py                                                            │ │
│  └────────────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                         │
│  ┌─── memory/ ── 记忆系统 ────────────────────────────────────────────────────────────┐ │
│  │  instance_memory.py (三层入口: recall / remember / flush)                          │ │
│  │  markdown_layer.py (MEMORY.md)                                                     │ │
│  │  mem0/: pool │ config │ sqlite_vec_store                                           │ │
│  │    extraction/: extractor │ retrieval/: formatter │ reranker                        │ │
│  │    schemas/: behavior │ emotion │ explicit_memory │ fragment │ persona │ plan       │ │
│  │    update/: quality_control │ aggregator │ analyzer │ planner                       │ │
│  │            persona_builder │ prompts │ reminder │ reporter                          │ │
│  │  base.py │ manager.py │ working.py                                                 │ │
│  │  system/: cache │ skill │ user/: episodic │ plan │ preference                      │ │
│  └────────────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                         │
│  ┌─── knowledge/ ── 知识检索 ─────────────────────────────────────────────────────────┐ │
│  │  local_search.py (FTS5 + 向量混合搜索)                                             │ │
│  │  file_indexer.py (增量索引 + 分块 + 批量 embedding)                                │ │
│  │  embeddings.py (Embedding 抽象：OpenAI / 本地 / auto 降级)                         │ │
│  └────────────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                         │
│  ┌─── planning/ ────────────┐  ┌─── termination/ ──────────┐  ┌─── state/ ───────────┐ │
│  │  dag_scheduler.py        │  │  adaptive.py               │  │  consistency_mgr.py  │ │
│  │  progress_transformer.py │  │  八维度终止判断             │  │  (快照/回滚)         │ │
│  │  protocol.py │ storage   │  │  protocol.py               │  │  operation_log.py    │ │
│  │  validators.py           │  │  (BaseTerminator)          │  │  (逆操作)            │ │
│  └──────────────────────────┘  └────────────────────────────┘  └──────────────────────┘ │
│                                                                                         │
│  ┌─── llm/ ── LLM 接口 ─────────────────────────────────────────────────────────────┐  │
│  │  base.py │ claude.py │ openai.py │ gemini.py │ qwen.py                            │  │
│  │  adaptor.py │ router.py │ model_registry.py │ registry.py                         │  │
│  │  health_monitor.py │ tool_call_utils.py                                           │  │
│  └───────────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                         │
│  ┌─── events/ ── 事件系统 ───────────────────────────────────────────────────────────┐  │
│  │  broadcaster.py │ base.py │ dispatcher.py │ manager.py │ storage.py               │  │
│  │  content_events │ conversation_events │ message_events │ session_events            │  │
│  │  system_events │ user_events                                                      │  │
│  │  adapters/: dingtalk │ feishu │ slack │ webhook │ base                             │  │
│  └───────────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                         │
│  ┌─── prompt/ ── 提示词工程 ────────────────┐  ┌─── skill/ ── Skill 管理 ────────────┐ │
│  │  runtime_context_builder.py              │  │  dynamic_loader.py (运行时依赖检查) │ │
│  │  skill_prompt_builder.py                 │  │  loader.py (SkillsLoader)           │ │
│  │  complexity_detector.py │ llm_analyzer   │  │  models.py (SkillEntry/BackendType) │ │
│  │  framework_rules.py │ prompt_layer.py    │  │  os_compatibility.py (OS 四状态)    │ │
│  │  instance_cache.py                       │  │  group_registry.py (分组注册表)     │ │
│  │  intent_prompt_generator.py              │  └────────────────────────────────────┘ │
│  │  prompt_results_writer.py                │                                         │
│  └──────────────────────────────────────────┘  ┌─── tool/ ── 工具管理 ──────────────┐ │
│                                                 │  registry.py │ executor.py          │ │
│  ┌─── discovery/ ── 应用发现 ────────────────┐  │  selector.py │ validator.py         │ │
│  │  app_scanner.py                           │  │  types.py │ loader.py              │ │
│  │  macOS ✅  Win32 ❌  Linux ❌              │  │  llm_description.py                │ │
│  └───────────────────────────────────────────┘  │  registry_config.py                │ │
│                                                  │  capability/: skill_loader.py       │ │
│  ┌─── 其他核心模块 ──────────────────────────────┴────────────────────────────────────┐ │
│  │  nodes/: manager │ protocol │ executors/: base │ shell │ local/: base │ macos      │ │
│  │  orchestration/: code_orchestrator │ code_validator │ pipeline_tracer              │ │
│  │  inference/: semantic_inference                                                    │ │
│  │  guardrails/: adaptive                                                             │ │
│  │  evaluation/: reward_attribution                                                   │ │
│  │  output/: formatter                                                                │ │
│  │  monitoring/: production_monitor │ failure_detector │ failure_case_db              │ │
│  │    quality_scanner │ token_audit │ case_converter                                  │ │
│  │  playbook/: manager.py │ storage.py                                                │ │
│  │  schemas/: validator.py                                                             │ │
│  │  config/: loader.py                                                                 │ │
│  └────────────────────────────────────────────────────────────────────────────────────┘ │
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
│  │  circuit_breaker │ fallback │ retry  │  │  base │ local │ async_writer            │  │
│  │  timeout │ config                    │  │  batch_writer │ storage_manager          │  │
│  └──────────────────────────────────────┘  └──────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

### 0.2 请求处理数据流

```
用户请求 (HTTP/SSE)
   │
   ▼
┌──────────────────────────────────────────────────────────────────────┐
│ routers/chat.py  POST /chat → SSE 流式响应                           │
└──┬───────────────────────────────────────────────────────────────────┘
   │
   ▼
┌──────────────────────────────────────────────────────────────────────┐
│ services/chat_service.py                                             │
│   1. session_service → 获取/创建会话                                   │
│   2. agent_registry → 获取 Agent 实例（原型 + clone_for_session）      │
│   3. 文件处理 (FileProcessor)                                         │
│   4. 意图路由 (IntentAnalyzer)                                        │
│   5. 调用 agent.execute()                                             │
└──┬───────────────────────────────────────────────────────────────────┘
   │
   ▼
┌──────────────────────────────────────────────────────────────────────┐
│ core/routing/ — 意图路由                                              │
│   IntentAnalyzer.analyze() → IntentResult                           │
│     ├── L1 Hash 缓存                                                 │
│     ├── L2 Semantic 缓存                                             │
│     └── L3 LLM 分析                                                  │
│   AgentRouter.route() → 固定 RVR-B                                   │
└──┬───────────────────────────────────────────────────────────────────┘
   │
   ▼
┌──────────────────────────────────────────────────────────────────────┐
│ core/agent/base.py — Agent.execute()                                 │
│   1. 状态快照 (consistency_manager.snapshot())                        │
│   2. 上下文构建 (injectors phase1 → phase2 → phase3)                 │
│   3. RVR-B 执行器                                                     │
│   4. 终止策略评估 (adaptive_terminator.evaluate())                    │
│   5. 成功 → 提交 / 失败 → 回滚                                        │
└──┬───────────────────────────────────────────────────────────────────┘
   │
   ▼
┌──────────────────────────────────────────────────────────────────────┐
│ execution/rvrb.py — RVR-B 主循环                                     │
│   1. LLM 推理                                                        │
│   2. 工具执行                                                        │
│   3. 验证结果                                                        │
│   4. 错误分类 (error_classifier)                                     │
│   5. 智能回溯 (backtrack/manager)                                    │
│   6. 规划调整                                                        │
└──┬───────────────────────────────────────────────────────────────────┘
   │
   ▼
┌──────────────────────────────────────────────────────────────────────┐
│ 并行异步处理                                                          │
│  ├── 记忆提取: memory_flush → FragmentExtractor → 双写               │
│  ├── 事件广播: broadcaster → SSE → 前端                               │
│  ├── 后台任务: title_generation / mem0_update / recommended_questions │
│  └── 知识索引: file_indexer → FTS5 增量索引                           │
└──────────────────────────────────────────────────────────────────────┘
```

### 0.3 存储架构（实例隔离）

所有运行时数据按实例名称隔离，通过 `AGENT_INSTANCE` 环境变量驱动。

```
┌─────────────────────────────────────────────────────────────────────┐
│             SQLite 统一存储 (WAL 模式) — 实例隔离                    │
│                                                                     │
│  路径布局：{user_data_dir}/data/instances/{instance_name}/           │
│  开发时: 项目根/data/instances/xiaodazi/                             │
│  打包后: ~/Library/Application Support/com.zenflux.agent/data/...   │
│                                                                     │
│  ┌── 实例数据库 (db/instance.db) ──────────────────────────────┐   │
│  │  ORM 表: conversations │ messages │ scheduled_tasks          │   │
│  │          agents │ sessions │ local_indexed_files              │   │
│  │  FTS5 虚拟表: messages_fts │ knowledge_fts │ memory_fts      │   │
│  │  sqlite-vec: mem0 vectors │ knowledge_vectors                │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌── 实例文件系统 ──────────────────────────────────────────────┐   │
│  │  db/instance.db         — 主数据库                            │   │
│  │  memory/MEMORY.md       — 用户记忆文件                        │   │
│  │  store/memory_fts.db    — 记忆 FTS 索引                       │   │
│  │  store/mem0_vectors.db  — Mem0 向量库                         │   │
│  │  storage/               — 文件上传存储                        │   │
│  │  playbooks/             — Playbook 策略库                     │   │
│  │  snapshots/             — 状态快照                            │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌── 共享资源（多实例复用）──────────────────────────────────────┐   │
│  │  data/shared/models/ — Embedding 模型（如 bge-m3）            │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌── 路径管理 (utils/app_paths.py) ────────────────────────────┐   │
│  │  get_instance_db_dir(name)       → db/                       │   │
│  │  get_instance_memory_dir(name)   → memory/                   │   │
│  │  get_instance_store_dir(name)    → store/                    │   │
│  │  get_instance_storage_dir(name)  → storage/                  │   │
│  │  get_instance_playbooks_dir(name)→ playbooks/                │   │
│  │  get_instance_snapshots_dir(name)→ snapshots/                │   │
│  │  get_shared_models_dir()         → data/shared/models/       │   │
│  └──────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

### 0.4 实例配置层

```
instances/xiaodazi/                        ← 小搭子（桌面端主实例）
├── .env / .env.example                    API Keys（gitignored）+ 模板
├── config.yaml                            用户配置（persona / agent.provider / memory / planning）
├── config/
│   ├── skills.yaml                        Skills 管理（21 个分组 + 120 个 Skill 条目）
│   ├── llm_profiles.yaml                  LLM Profiles（provider_templates + 13 个 tier-based profile）
│   └── memory.yaml                        记忆配置
├── prompt.md / prompt_desktop.md          人格提示词
├── prompt_results/                        LLM 推断缓存（simple/medium/complex/intent 提示词）
└── skills/                                79 个实例 Skill 目录（每个含 SKILL.md）

Provider 一键切换：agent.provider 改一个值，主 Agent + 13 个内部调用点全部自动适配

  ┌──────────┬───────────────────────────┬──────────────────────────┐
  │ 角色     │ qwen                      │ claude                   │
  ├──────────┼───────────────────────────┼──────────────────────────┤
  │ 主 Agent │ qwen3-max                 │ claude-sonnet-4-5        │
  │ heavy    │ qwen3-max                 │ claude-sonnet-4-5        │
  │ light    │ qwen-plus                 │ claude-haiku-4-5         │
  └──────────┴───────────────────────────┴──────────────────────────┘
```

### 0.5 支撑模块清单

```
┌─── models/ (Pydantic 数据模型) ─────────────────────────────────────┐
│  agent │ api │ chat │ chat_request │ database │ docs │ hitl         │
│  llm │ mcp │ scheduled_task │ skill │ usage                        │
└─────────────────────────────────────────────────────────────────────┘

┌─── prompts/ (提示词模板) ───────────────────────────────────────────┐
│  intent_recognition_prompt │ plan_generator_prompt │ prompt_selector │
│  simple_prompt │ standard_prompt │ universal_agent_prompt            │
│  MEMORY_PROTOCOL.md │ factory/: schema_generator.md                 │
│  fragments/: code_rules │ excel_rules │ ppt_rules                   │
│  templates/: complex/medium/simple/intent_prompt_generation          │
└─────────────────────────────────────────────────────────────────────┘

┌─── tools/ (可调用工具) ────────────────────────────────────────────┐
│  base │ api_calling │ browser │ nodes_tool │ observe_screen         │
│  plan_todo_tool │ request_human_confirmation │ knowledge_search     │
└─────────────────────────────────────────────────────────────────────┘

┌─── utils/ (工具函数) ──────────────────────────────────────────────┐
│  app_paths (双模式路径 + 实例隔离) │ instance_loader                │
│  cache_utils │ file_handler │ file_processor                        │
│  json_file_store │ json_utils │ message_utils │ query_utils         │
│  background_tasks/:                                                 │
│    scheduler │ registry │ service │ context                         │
│    tasks/: mem0_update │ recommended_questions                      │
│            title_generation │ memory_flush                          │
└─────────────────────────────────────────────────────────────────────┘

┌─── config/ (框架级配置) ────────────────────────────────────────────┐
│  capabilities.yaml │ context_compaction.yaml │ prompt_config.yaml   │
│  resilience.yaml │ scheduled_tasks.yaml │ tool_registry.yaml        │
│  llm_config/: __init__.py │ loader.py                               │
└─────────────────────────────────────────────────────────────────────┘

┌─── skills/ (全局技能库) ────────────────────────────────────────────┐
│  library/: 60 个 Skill（框架级，多实例共用）                         │
└─────────────────────────────────────────────────────────────────────┘

┌─── evaluation/ (评估框架) ──────────────────────────────────────────┐
│  harness │ metrics │ models │ qos_config │ calibration │ dashboard  │
│  loop_automation │ alerts │ ci_integration │ promptfoo_adapter       │
│  adapters/: http_agent                                              │
│  graders/: code_based │ human │ model_based                         │
│  config/: settings.yaml │ judge_prompts.yaml                        │
│  suites/: xiaodazi/e2e/ │ xiaodazi/feasibility/ │ xiaodazi/efficiency/ │
│  reports/: e2e_phase1_*.json │ rollback_e2e_*.json                  │
└─────────────────────────────────────────────────────────────────────┘

┌─── scripts/ (运维脚本) ─────────────────────────────────────────────┐
│  run_e2e_auto │ run_e2e_eval │ run_eval │ run_xiaodazi_eval         │
│  verify_* (架构/记忆/知识/E2E 等验证脚本)                            │
│  build_app.sh │ auto_build_app.sh │ build_backend.py                │
│  init_instance_xiaodazi │ migrate_instance_storage                   │
│  switch_provider │ sync_capabilities │ sync_version                  │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 一、模块完成度概览

```
█████████░  90%  Agent 引擎层 (统一 Agent + RVR-B)
█████████░  90%  实例骨架与配置 (三文件分级 + Provider 切换)
█████████░  90%  FastAPI 服务端 (9 路由 + 8 服务 + WebSocket)
█████████░  90%  意图识别 (SkillGroupRegistry + 21 分组)
████████░░  85%  存储层 (SQLite + FTS5 + sqlite-vec，全组件实例隔离)
████████░░  85%  实例存储隔离 (全组件感知 AGENT_INSTANCE)
████████░░  85%  本地知识检索 (FTS5 + 向量混合搜索)
████████░░  85%  上下文注入器 (9 个 Phase Injector)
████████░░  85%  自适应终止策略 (八维度 + 回溯感知 + 费用阶梯)
████████░░  85%  Plan 规划系统 (DAG 调度 + 渐进式展示)
████████░░  85%  Skills 体系 (79 实例 + 60 全局 + 21 分组)
████████░░  80%  记忆系统 (三层架构 + Mem0 + 会话批量提取)
████████░░  80%  状态一致性管理 (快照/回滚，E2E 验证通过)
████████░░  80%  后台任务系统 (两级调度 + 4 个任务)
████████░░  80%  打包与桌面端 (PyInstaller + Tauri sidecar)
███████░░░  75%  前端实现 (23 组件 + 12 Store + 6 Composable + 6 页面)
███████░░░  70%  Nodes 本地操作 (macOS 完整，Win/Linux 待实现)
█████░░░░░  50%  Playbook 持续学习 (策略注入已实现，端到端链路待串联)
████░░░░░░  40%  E2E 评估框架 (框架完整，用例内容待充实)
████░░░░░░  40%  OS 兼容层 (仅 macOS)
███░░░░░░░  35%  应用发现 (仅 macOS 扫描)
░░░░░░░░░░   0%  Skills 安全验证
```

---

## 二、逐模块状态

### 2.1 Agent 引擎层

| 组件 | 文件 | 说明 |
|------|------|------|
| `Agent` | `core/agent/base.py` | 统一智能体类，Strategy 模式通过 Executor 注入 |
| `AgentFactory` | `core/agent/factory.py` | Prompt 驱动的动态初始化，`from_schema()` / `create_agent_from_prompt()` |
| `RVRBExecutor` | `core/agent/execution/rvrb.py` | 统一执行器：回溯 + 错误分类 + 候选方案重试 |
| `RVRExecutor` | `core/agent/execution/rvr.py` | 标准 RVR 循环（保留但所有路径映射到 RVR-B） |
| `ErrorClassifier` | `core/agent/backtrack/error_classifier.py` | 两层错误分类（基础设施 vs 业务逻辑） |
| `BacktrackManager` | `core/agent/backtrack/manager.py` | LLM 驱动的回溯决策 + 渐进升级 |
| `ContentHandler` | `core/agent/content_handler.py` | Content Block 处理（流式/非流式） |

**执行架构**：统一 RVR-B，complexity 通过 `SkillFocusInjector` 影响 Skill 聚焦提示（simple → 直接回答 / complex → 桌面操作模式）。

**回溯流程**：工具执行失败 → ErrorClassifier 分类 → BacktrackManager 决策 → PARAM_ADJUST / TOOL_REPLACE / PLAN_REPLAN / CONTEXT_ENRICH / INTENT_CLARIFY。含 Context Pollution 清理和 Contrastive Reflection。

---

### 2.2 意图识别

| 文件 | 说明 |
|------|------|
| `core/routing/intent_analyzer.py` | 三层缓存（Hash → Semantic → LLM），从 SkillGroupRegistry 动态获取分组描述 |
| `core/routing/router.py` | `AgentRouter` 路由决策（固定 RVR-B） |
| `core/routing/intent_cache.py` | `IntentSemanticCache` 语义缓存 |
| `core/routing/types.py` | `IntentResult` 类型：complexity / skip_memory / is_follow_up / wants_to_stop / relevant_skill_groups |
| `core/skill/group_registry.py` | `SkillGroupRegistry`：分组单一数据源 + CRUD + 描述自动生成 + 孤儿检测 |

**IntentResult 输出**：5 个核心字段（complexity / skip_memory / is_follow_up / wants_to_stop / relevant_skill_groups）。

**数据流**：config/skills.yaml → SkillGroupRegistry → build_groups_description() → intent_recognition_prompt → IntentAnalyzer.analyze() → relevant_skill_groups → SkillsLoader 按需注入。

---

### 2.3 Skills 体系

**规模**：实例 79 个 Skill 目录 + 全局库 60 个 + skills.yaml 配置 120 个条目 + 21 个意图分组。

| 组件 | 文件 | 说明 |
|------|------|------|
| `SkillsLoader` | `core/skill/loader.py` | 解析 skills.yaml → SkillEntry 列表，惰性加载 |
| `SkillEntry` | `core/skill/models.py` | 统一 Skill 模型（BackendType: local/tool/mcp/api） |
| `DynamicSkillLoader` | `core/skill/dynamic_loader.py` | 运行时依赖检查（bins/env/OS） |
| `SkillGroupRegistry` | `core/skill/group_registry.py` | 分组注册表 + CRUD + 描述生成 |
| `CompatibilityStatus` | `core/skill/os_compatibility.py` | 四状态（ready/need_auth/need_setup/unavailable） |

**21 个意图分组**：

| 分组 | 描述 | Skills 数 |
|------|------|----------|
| writing | 写作、润色、PPT 生成与编辑 | 11 |
| content_creation | 社交媒体、Newsletter、视频脚本 | 5 |
| data_analysis | Excel/CSV 分析、发票整理 | 3 |
| file_operation | 文件管理、Word、PDF、批量转换 | 10 |
| translation | 多语言翻译、OCR | 3 |
| research | 论文搜索、竞品、深度调研、网页爬取 | 10 |
| meeting | 会议记录分析、行动项 | 2 |
| career | 求职辅助、简历优化 | 2 |
| learning | 导师、测验、读书伴侣 | 3 |
| creative | 头脑风暴、GIF、Gemini | 3 |
| diagram | 流程图、手绘图表 | 2 |
| image_gen | AI 图像生成 | 2 |
| media | 语音转文字、TTS、音乐、视频 | 7 |
| health | 营养分析、用药管理 | 2 |
| productivity | 笔记/待办/日历/邮件/IM | 20 |
| app_automation | 桌面操作、UI 自动化、浏览器 | 21 |
| system_maintenance | 磁盘、软件、定时任务、WSL | 4 |
| lifestyle | 记账、旅行规划 | 2 |
| security | 隐私审计、文件加密 | 2 |
| code | GitHub 管理 | 1 |
| _always | 始终注入 | 3 |

---

### 2.4 上下文注入器

9 个 Phase Injector 覆盖从系统角色到动态上下文的完整注入链路。

```
Phase 1: System Message（缓存稳定层）
├── system_role.py          — 系统角色提示词
├── history_summary.py      — 历史摘要（压缩旧对话）
├── tool_provider.py        — 工具定义注入
└── skill_focus.py          — 复杂度驱动 Skill 聚焦（DYNAMIC）

Phase 2: User Context（每次对话动态）
├── user_memory.py          — 用户记忆召回
├── playbook_hint.py        — 历史成功策略提示
└── knowledge_context.py    — 本地知识库上下文

Phase 3: Runtime（实时状态）
├── gtd_todo.py             — GTD 待办状态
└── page_editor.py          — 页面编辑器上下文
```

缓存策略：STABLE（几乎不变）/ SESSION（每会话）/ DYNAMIC（每轮）。

---

### 2.5 记忆系统

三层架构：文件层（MEMORY.md）+ 索引层（FTS5）+ 智能层（Mem0）。

| 组件 | 说明 |
|------|------|
| `InstanceMemoryManager` | 三层统一入口：recall 融合搜索 / remember 双写 / flush 批量提取 |
| `MarkdownLayer` | MEMORY.md 模板 + 段落追加 + 每日日志 |
| `Mem0MemoryPool` | 语义搜索 + 向量存储 |
| `FragmentExtractor` | 10 维碎片记忆提取（会话级批量 LLM 调用） |
| `QualityController` | 冲突检测 + 更新决策 |

**记忆提取策略**：每次聊天响应后 → memory_flush 后台任务 → 快速预判 → FragmentExtractor 一次 LLM 调用 → remember 双写。

---

### 2.6 本地知识检索

| 组件 | 说明 |
|------|------|
| `LocalKnowledgeManager` | FTS5 + 向量混合搜索，加权合并去重 |
| `FileIndexer` | 增量索引 + 分块 + 批量 embedding |
| `EmbeddingProvider` | 抽象层（OpenAI / 本地 / auto 降级） |
| `knowledge_search` | Agent 可调用的知识搜索工具 |
| `KnowledgeContextInjector` | Phase 2 自动注入相关知识 |

搜索架构：FTS5 全文（BM25）+ sqlite-vec 向量 → 混合合并（0.6×vec + 0.4×fts）。

---

### 2.7 Plan 规划系统

| 组件 | 说明 |
|------|------|
| `DAGScheduler` | DAG 调度 + 并行执行 + 重规划建议 |
| `ProgressTransformer` | 进度转换 + 事件推送 |
| `PlanStorage` | 持久化（跨 Session） |
| `PlanValidator` | Plan 验证 + 执行顺序 |

Plan 注入采用渐进式展示：已完成折叠、当前步骤突出、未来限 2 步。文件操作自动注入安全提示。

---

### 2.8 自适应终止策略

八维度终止判断 + 回溯感知 + 阶梯式费用 HITL：

| 维度 | 说明 |
|------|------|
| LLM 自主终止 | `stop_reason == "end_turn"` |
| HITL 危险操作 | `require_confirmation` 列表 |
| 用户主动停止 | `stop_requested` |
| 安全兜底 | max_turns / max_duration / idle_timeout / consecutive_failures |
| 费用感知 | 阶梯式 HITL：warn($0.50) → confirm($2.00) → urgent($10.00) |
| 长任务确认 | `long_running_confirm_after_turns` |
| 回溯耗尽 | HITL 三选一（重试/回滚/放弃） |
| 意图澄清 | `intent_clarify_request` |

`FinishReason` 枚举包含 13 个结构化终止原因。

---

### 2.9 状态一致性管理

| 组件 | 说明 |
|------|------|
| `ConsistencyManager` | 快照 / 操作日志 / 回滚 / 提交 / 过期清理 |
| `OperationLog` | `OperationRecord` + inverse-patch 自动逆操作 |

功能：任务前环境快照 → 操作日志（含逆操作闭包）→ 异常时回滚选项推送 → 成功提交清理。支持文件级自动逆操作（write/create/delete/rename）、动态文件捕获、磁盘持久化。

已在 `instances/xiaodazi/config.yaml` 启用 `state_consistency.enabled: true`。Rollback E2E 验证通过（B9/B10 共 6 子场景）。

---

### 2.10 Nodes 本地操作

架构：`tools/nodes_tool.py` → `core/nodes/manager.py` → `core/nodes/local/macos.py` → `core/nodes/executors/shell.py`

**macOS 已实现**：Shell 命令 / which / 通知 / AppleScript / 打开应用 / 打开 URL / 打开路径 / 截图 / 剪贴板读写 / TTS（共 11 项）。

Windows / Linux 本地节点待实现。

---

### 2.11 屏幕观察工具

`tools/observe_screen.py`：peekaboo + Vision OCR 并行执行，返回窗口标题 + 可操作 UI 元素列表 + OCR 文字。仅 macOS。

---

### 2.12 Playbook 持续学习

| 组件 | 状态 | 说明 |
|------|------|------|
| PlaybookManager | 已完成 | CRUD + 审核流程 + 匹配算法 |
| FileStorage | 已完成 | JSON 文件持久化 |
| PlaybookHintInjector | 已完成 | Phase 2 注入到 messages 层（不影响 system prompt 缓存） |
| Agent → 生成 DRAFT | 待串联 | `base.py` 未调用 `extract_from_session()` |
| DRAFT → 用户确认 | 待串联 | 无事件推送到前端 |
| 用户确认 → APPROVED | 待串联 | 无确认回调 API |

策略注入（Phase 2）已实现。端到端链路（任务完成 → 自动初筛 → 用户确认 → 入库）3 条待串联。

---

### 2.13 LLM 接口层

| 文件 | 说明 |
|------|------|
| `core/llm/base.py` | BaseLLM 抽象 |
| `core/llm/claude.py` | Claude 适配器 |
| `core/llm/openai.py` | OpenAI 适配器 |
| `core/llm/gemini.py` | Gemini 适配器 |
| `core/llm/qwen.py` | 通义千问适配器 |
| `core/llm/router.py` | ModelRouter 路由 |
| `core/llm/model_registry.py` | 模型注册 + ModelPricing 定价 |
| `core/llm/health_monitor.py` | 健康监控 |

---

### 2.14 事件系统

`core/events/broadcaster.py` 统一事件广播，支持 SSE 推送。事件类型：content / conversation / message / session / system / user。

适配器：钉钉 / 飞书 / Slack / Webhook。

---

### 2.15 后台任务系统

两级调度：

| 类型 | 任务 | 行为 |
|------|------|------|
| SSE 依赖型（await） | title_generation、recommended_questions | 等待完成后关闭 SSE 流 |
| 学习型（fire-and-forget） | memory_flush、mem0_update | 启动即返回，不阻塞用户 |

`@background_task` 装饰器自动注册。失败隔离：学习型任务失败仅 warning。

---

### 2.16 实例存储隔离与路径管理

`utils/app_paths.py` 提供统一路径管理（双模式：开发 vs PyInstaller 打包）。

全组件已适配 `AGENT_INSTANCE` 环境变量：engine.py / instance_memory.py / local.py / storage.py / consistency_manager.py / mem0 config / sqlite_vec_store.py。

`register_instance_data_dir()` 支持自定义数据目录（通过 `config.yaml` 的 `storage.data_dir`）。

---

### 2.17 打包与桌面端

| 组件 | 说明 |
|------|------|
| `zenflux-backend.spec` | PyInstaller 打包配置 |
| `scripts/build_app.sh` | 全栈构建脚本 |
| `scripts/build_backend.py` | 后端打包脚本 |
| `scripts/sync_version.py` | 版本同步（Python ↔ Tauri） |

双模式路径：开发时 bundle_dir = 项目根；打包后 bundle_dir = sys._MEIPASS，user_data = 平台用户目录。

CLI 参数：`--data-dir`（Tauri sidecar 传入）/ `--port`（默认 18900）。

---

### 2.18 E2E 评估框架

| 组件 | 说明 |
|------|------|
| `evaluation/harness.py` | 评估运行引擎 |
| `evaluation/adapters/http_agent.py` | E2E → FastAPI 桥接 |
| `evaluation/graders/code_based.py` | 代码评分器（确定性检查） |
| `evaluation/graders/model_based.py` | 模型评分器（LLM-as-Judge） |
| `scripts/run_e2e_auto.py` | 自动化运行（自动启动/停止服务） |

三层评估：Phase 0 Rollback 验证 → Phase 1 Agent E2E → 评分报告。

测试套件：`suites/xiaodazi/e2e/phase1_core.yaml`（核心用例） + `feasibility/`（7 个）+ `efficiency/`（4 个）。

---

## 三、前端与服务端

### 3.1 FastAPI 服务端

| 维度 | 数量 |
|------|------|
| 路由模块 | 9 个（chat / websocket / conversation / agents / skills / files / models / settings / human_confirmation） |
| 服务层 | 8 个（chat_service / agent_registry / session_service / conversation_service / knowledge_service / confirmation_service / settings_service / user_task_scheduler） |
| WebSocket | `/api/v1/ws/chat` |

### 3.2 Vue 前端

| 维度 | 数量 |
|------|------|
| Vue 组件 | 23 个 |
| Pinia Store | 12 个（conversation / session / ui / workspace / knowledge / connection / agent / guide / skill / agentCreation / notification / index） |
| Composables | 6 个（useChat / useSSE / useWebSocketChat / useHITL / useFileUpload / index） |
| API 模块 | 10 个 |
| 页面 | 6 个 |
| 布局 | 2 个（DashboardLayout / DefaultLayout） |

**技术栈**：Vue 3.4 + Pinia + Vue Router + Tailwind CSS 4 + Radix Vue + Lucide Vue Next + Markstream Vue（Markdown 流式渲染）+ Mermaid。

**设计系统**：Apple Liquid 毛玻璃 + 琥珀黄主题色 `#F59E0B` + 灰度极简。

**运行模式**：Tauri 桌面应用（localhost:18900）/ 浏览器开发模式（Vite proxy → 127.0.0.1:8000）。

### 3.3 前端路由

| 路由 | 页面 |
|------|------|
| `/` | ChatView（默认聊天） |
| `/c/:conversationId` | ChatView（指定对话） |
| `/agent/:agentId` | ChatView（Agent 项目） |
| `/knowledge` | KnowledgeView |
| `/skills` | SkillsView |
| `/create-project` | CreateProjectView（创建模式） |
| `/edit-project/:agentId` | CreateProjectView（编辑模式） |
| `/settings` | SettingsView |
| `/onboarding` | OnboardingView |

### 3.4 首次启动引导

9 步 2 阶段交互式教程：阶段一（Step 1-4）设置 API Key；阶段二（Step 5-9）创建项目。支持条件跳过、验证回调、步骤回退、持久化。

### 3.5 设置页

多 Provider 批量保存 + 验证 + 激活。脱敏值智能跳过。Provider 卡片手风琴 UI。

### 3.6 项目管理

多实例架构：不同搭子 = 不同实例目录，天然隔离。

已有实例：`xiaodazi`（主实例）/ `_template`（脚手架模板）。

前端支持创建新搭子（CreateProjectView 创建模式）和编辑已有搭子（编辑模式）。

---

## 四、环境配置

### 必填 API Keys

| Key | 用途 |
|-----|------|
| `ANTHROPIC_API_KEY` | Claude（主 Agent 对话模型） |
| `DASHSCOPE_API_KEY` | 通义千问（框架内部 LLM） |
| `OPENAI_API_KEY` | OpenAI（Embedding + Mem0 记忆提取） |

### 可选配置

| Key | 用途 |
|-----|------|
| `QDRANT_URL` / `QDRANT_API_KEY` | 向量数据库 |
| `PAGEINDEX_API_KEY` | 长文档分析 |
| `GOOGLE_PLACES_API_KEY` | 地点搜索 |
| `LOG_LEVEL` | 日志级别 |

### 启动方式

```bash
source /Users/liuyi/Documents/langchain/liuy/bin/activate
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

---

## 五、遗留项

### 链路待串联

| 项目 | 说明 |
|------|------|
| Playbook 端到端 | `base.py` 需调用 `extract_from_session()`；需新增确认事件推送和 API |
| ProgressTransformer 集成 | 未集成到 PlanTodoTool 执行流程 |
| 前端 HITL 事件渲染 | backtrack_exhausted / intent_clarify / cost_limit / cost_warn 前端未处理 |

### 功能待完善

| 项目 | 说明 |
|------|------|
| 记忆文件监听 | watchdog 监听 MEMORY.md 变更 → 自动重建索引 |
| 记忆混合检索权重 | config 已声明 vector_weight/bm25_weight，recall 中未应用 |
| Playbook 语义匹配 | 当前关键词匹配，需替换为 Mem0 语义搜索 |
| DatabaseStorage | 依赖已删除的 `infra.database`，当前使用 FileStorage |

### 跨平台

| 项目 | 说明 |
|------|------|
| Windows 本地节点 | `nodes/local/windows.py` 不存在 |
| Linux 本地节点 | `nodes/local/linux.py` 不存在 |
| AppScanner Win/Linux | 空实现 |
| Windows/Linux 打包 | 未验证 |

### 未开始

| 项目 | 说明 |
|------|------|
| Skills 签名验证 | 官方/社区/未签名三级信任 |
| 服务状态仪表板 | 前端页面 |
| MCP Apps UI | iframe + postMessage |
| Skill 配置向导 | 前端页面 |
