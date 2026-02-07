# 小搭子 Agent 实例 — 当前实现架构文档

> 基于《小搭子专用实例架构设计》(V9.0) 需求文档，对照当前代码实现的完整状态梳理。
>
> 范围：仅涉及 Python 后端 + 框架核心层，不涉及 Tauri 桌面壳、Vue 前端组件。
>
> 更新时间：2026-02-07

---

## 〇、架构全景图

### 0.1 分层架构总览

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                              前端层 (frontend/)                                         │
│  Vue 3 + TypeScript + Vite + Tauri                                                      │
│                                                                                         │
│  ┌── views/ ──────────────────────────────────────────────────────────────────────────┐  │
│  │ ChatView │ DocsView │ SettingsView │ SkillsView │ RealtimeView │ NodeAgentView    │  │
│  └────┬───────────────────────────────────────────────────────────────────────────────┘  │
│       │                                                                                 │
│  ┌────▼── composables/ ──────────────────────────────────────────────────────────────┐  │
│  │ useChat │ useSSE │ useHITL │ useFileUpload │ useRealtime                          │  │
│  └────┬──────────────────────────────────────────────────────────────────────────────┘  │
│       │                                                                                 │
│  ┌────▼── api/ ──────────────────────────────────────────────────────────────────────┐  │
│  │ chat.ts │ session.ts │ config.ts │ skills.ts │ realtime.ts │ workspace.ts │ ...   │  │
│  └────┬──────────────────────────────────────────────────────────────────────────────┘  │
│       │                                                                                 │
│  ┌── components/ ─────────────────────────────────────────────────────────────────────┐  │
│  │ chat/: ChatHeader │ ChatInputArea │ ConversationSidebar │ MarkdownRenderer        │  │
│  │       MessageContent │ MessageList │ ToolMessage                                  │  │
│  │ modals/: ConfirmModal │ LongRunConfirmModal │ RollbackOptionsModal │ Attachment    │  │
│  │ workspace/: FileExplorer │ FilePreview │ FileTreeNode                             │  │
│  │ realtime/: RealtimeVoice                                                          │  │
│  │ common/: Card                                                                     │  │
│  └────────────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                         │
│  ┌── stores/ ─────────┐ ┌── layouts/ ─────────┐ ┌── types/ ──────────────────────────┐  │
│  │ conversation │ ui  │ │ DashboardLayout     │ │ api │ chat │ realtime │ skills     │  │
│  │ session │ workspace│ │ DefaultLayout       │ │ workspace │ index                  │  │
│  └────────────────────┘ └─────────────────────┘ └────────────────────────────────────┘  │
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
│  chat.py │ agents.py │ conversation.py │ files.py │ skills.py │ tools.py               │
│  mem0_router.py │ tasks.py │ settings.py │ realtime.py │ models.py                     │
│  health.py │ docs.py │ human_confirmation.py                                           │
└───────┬─────────────────────────────────────────────────────────────────────────────────┘
        │
┌───────▼─────────────────────────────────────────────────────────────────────────────────┐
│                          服务层 (services/)  — Business Logic                            │
│                                                                                         │
│  chat_service.py │ session_service.py │ agent_registry.py │ conversation_service.py     │
│  file_service.py │ tool_service.py │ confirmation_service.py │ settings_service.py      │
│  mem0_service.py │ realtime_service.py │ mcp_service.py │ mcp_client.py                │
│  docs_service.py │ task_service.py │ user_task_scheduler.py                             │
└───────┬─────────────────────────────────────────────────────────────────────────────────┘
        │
┌───────▼─────────────────────────────────────────────────────────────────────────────────┐
│                          核心层 (core/)  — Agent Framework                               │
│                                                                                         │
│  ┌─── agent/ ── Agent 引擎 ───────────────────────────────────────────────────────────┐ │
│  │  base.py (797行, SimpleAgent)                                                      │ │
│  │  factory.py (AgentFactory) │ models.py │ protocol.py │ content_handler.py │ errors │ │
│  │                                                                                    │ │
│  │  ┌── execution/ ────────────────────────────────────────────────────────────────┐  │ │
│  │  │  rvr.py (817行, RVR 执行器)                                                  │  │ │
│  │  │  rvrb.py (939行, RVR-B 回溯执行器)                                            │  │ │
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
│  │  intent_analyzer.py (277行, LLM 意图分析, fast_mode/semantic_cache)                │ │
│  │  router.py (AgentRouter) │ intent_cache.py (语义缓存) │ types.py (IntentResult)    │ │
│  └────────────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                         │
│  ┌─── context/ ── 上下文工程 ─────────────────────────────────────────────────────────┐ │
│  │  context_engineering.py │ provider.py │ retriever.py │ runtime.py                  │ │
│  │  failure_summary.py                                                                │ │
│  │  ┌── injectors/ ──────────────────────────────────────────────────────────────┐    │ │
│  │  │  base.py │ orchestrator.py │ context.py                                    │    │ │
│  │  │  phase1/: system_role.py │ history_summary.py │ tool_provider.py            │    │ │
│  │  │  phase2/: user_memory.py                                                   │    │ │
│  │  │  phase3/: gtd_todo.py │ page_editor.py                                     │    │ │
│  │  └────────────────────────────────────────────────────────────────────────────┘    │ │
│  │  ┌── compaction/ ──────────────────┐  ┌── providers/ ───────────────────────┐      │ │
│  │  │  summarizer.py │ tool_result.py │  │  memory.py │ metadata.py            │      │ │
│  │  └─────────────────────────────────┘  └─────────────────────────────────────┘      │ │
│  └────────────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                         │
│  ┌─── memory/ ── 记忆系统 ────────────────────────────────────────────────────────────┐ │
│  │                   ┌─────────────────────────────────────┐                          │ │
│  │                   │ xiaodazi_memory.py (513行)           │                          │ │
│  │                   │ 三层入口: recall / remember / flush  │                          │ │
│  │                   └──────────┬──────────────────────────┘                          │ │
│  │          ┌───────────────────┼──────────────────────┐                              │ │
│  │  ┌───────▼──────┐  ┌────────▼──────┐  ┌────────────▼──────────────────────┐        │ │
│  │  │ Layer 1      │  │ Layer 2       │  │ Layer 3: mem0/                    │        │ │
│  │  │ markdown_    │  │ GenericFTS5   │  │  pool.py (向量搜索)               │        │ │
│  │  │ layer.py     │  │ (全文索引)     │  │  config.py │ sqlite_vec_store.py │        │ │
│  │  │ (MEMORY.md)  │  │              │  │  extraction/: extractor.py        │        │ │
│  │  │ 409行        │  │              │  │  retrieval/: formatter │ reranker  │        │ │
│  │  └──────────────┘  └──────────────┘  │  schemas/: behavior │ emotion     │        │ │
│  │                                       │    explicit_memory │ fragment    │        │ │
│  │  ┌── 通用记忆模块 ──────────┐         │    persona │ plan                │        │ │
│  │  │ base.py │ manager.py    │         │  update/: quality_control (730+行)│        │ │
│  │  │ working.py              │         │    aggregator │ analyzer │ planner│        │ │
│  │  │ system/: cache │ skill  │         │    persona_builder │ prompts     │        │ │
│  │  │ user/: episodic │ plan  │         │    reminder │ reporter           │        │ │
│  │  │        preference       │         └──────────────────────────────────┘        │ │
│  │  └─────────────────────────┘                                                      │ │
│  └────────────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                         │
│  ┌─── knowledge/ ── 知识检索 ─────────────────────────────────────────────────────────┐ │
│  │  local_search.py (298行, FTS5 搜索 + add/remove, 语义搜索接口预留)                  │ │
│  │  file_indexer.py (320行, 增量索引 + 分块, txt/md/pdf/docx)                          │ │
│  └────────────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                         │
│  ┌─── planning/ ────────────┐  ┌─── termination/ ──────────┐  ┌─── state/ ───────────┐ │
│  │  progress_transformer.py │  │  adaptive.py (237行)       │  │  consistency_mgr.py  │ │
│  │  dag_scheduler.py        │  │  五维度终止判断             │  │  (796行 快照/回滚)   │ │
│  │  protocol.py             │  │  protocol.py               │  │  operation_log.py    │ │
│  │  storage.py │ validators │  │  (BaseTerminator)          │  │  (321行 逆操作)      │ │
│  └──────────────────────────┘  └────────────────────────────┘  └──────────────────────┘ │
│                                                                                         │
│  ┌─── llm/ ── LLM 接口 ─────────────────────────────────────────────────────────────┐  │
│  │  base.py (BaseLLM) │ claude.py │ openai.py │ gemini.py │ qwen.py                 │  │
│  │  adaptor.py │ router.py │ model_registry.py │ registry.py                        │  │
│  │  health_monitor.py │ tool_call_utils.py                                          │  │
│  └───────────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                         │
│  ┌─── events/ ── 事件系统 ───────────────────────────────────────────────────────────┐  │
│  │  broadcaster.py (988行) │ base.py │ dispatcher.py │ manager.py │ storage.py       │  │
│  │  content_events │ conversation_events │ message_events │ session_events           │  │
│  │  system_events │ user_events                                                     │  │
│  │  adapters/: dingtalk.py │ feishu.py │ slack.py │ webhook.py │ base.py             │  │
│  └───────────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                         │
│  ┌─── prompt/ ── 提示词工程 ────────────────┐  ┌─── skill/ ── Skill 管理 ────────────┐ │
│  │  runtime_context_builder.py (539行)       │  │  dynamic_loader.py (298行)          │ │
│  │  skill_prompt_builder.py                  │  │  loader.py │ models.py              │ │
│  │  complexity_detector.py │ llm_analyzer.py │  │  os_compatibility.py (110行)        │ │
│  │  framework_rules.py │ prompt_layer.py     │  │  os_skill_merger.py (136行)         │ │
│  │  instance_cache.py                        │  └────────────────────────────────────┘ │
│  │  intent_prompt_generator.py               │                                         │
│  │  prompt_results_writer.py                 │  ┌─── tool/ ── 工具管理 ──────────────┐ │
│  └───────────────────────────────────────────┘  │  registry.py │ executor.py          │ │
│                                                  │  selector.py │ validator.py         │ │
│  ┌─── discovery/ ── 应用发现 ────────────────┐  │  types.py │ loader.py              │ │
│  │  app_scanner.py (64行)                    │  │  llm_description.py                │ │
│  │  macOS ✅  Win32 ❌  Linux ❌               │  │  registry_config.py                │ │
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
│  │  playbook/: manager.py (757行) │ storage.py (308行)                               │  │
│  │  project/: manager.py (40行, 骨架占位)                                            │  │
│  │  schemas/: validator.py                                                          │  │
│  │  config/: loader.py                                                              │  │
│  └───────────────────────────────────────────────────────────────────────────────────┘  │
└───────┬─────────────────────────────────────────────────────────────────────────────────┘
        │
┌───────▼─────────────────────────────────────────────────────────────────────────────────┐
│                          基础设施层 (infra/)                                             │
│                                                                                         │
│  ┌─── local_store/ ────────────────────────────────────────────────────────────────────┐ │
│  │  engine.py (223行)      — aiosqlite + WAL + 7 项 PRAGMA 优化                       │ │
│  │  models.py (350+行)     — ORM 模型 + LocalIndexedFile                              │ │
│  │  fts.py (274行)         — 消息专用 FTS5                                             │ │
│  │  generic_fts.py (615行) — 通用 FTS5（知识/记忆共用，CJK 字符级分割 + 逆向合并）       │ │
│  │  vector.py (192行)      — sqlite-vec 向量搜索                                      │ │
│  │  workspace.py           — 统一管理器                                                │ │
│  │  pools.py               — 连接池                                                   │ │
│  │  session_store.py       — 会话存储                                                 │ │
│  │  skills_cache.py        — Skills 延迟加载缓存                                       │ │
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
│ Reflect (817行)      │            │ (939行)                          │
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
│  │  │ vector embeddings — Mem0 语义搜索 (vector.py)           │  │   │
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

### 0.4 实例配置层

```
instances/
├── xiaodazi/                          ← 小搭子（桌面端主实例）
│   ├── config.yaml (171行)            termination/knowledge/memory/project/skills/state
│   ├── prompt.md (63行)               人格提示词 + Few-Shot
│   └── skills/
│       ├── skill_registry.yaml (86行)
│       └── 40+ Skills 目录:
│           ├── OS 通用: app-recommender / content-reformatter / translator / style-learner
│           │            writing-assistant / writing-analyzer / literature-reviewer
│           │            paper-search / arxiv-search / competitive-intel / trend-spotter
│           │            excel-analyzer / excel-fixer / word-processor / local-search
│           │            medication-tracker / nutrition-analyzer / readwise-rival
│           ├── macOS:   applescript / apple-calendar / macos-clipboard / macos-finder
│           │            macos-notification / macos-open / macos-screenshot / app-scanner
│           ├── Linux:   linux-clipboard / linux-notification / linux-screenshot / xdotool
│           ├── Windows: windows-clipboard / windows-notification / windows-screenshot
│           │            powershell-basic / outlook-cli / onenote
│           └── 文件管理: file-manager
│
├── client_agent/                      ← 通用 Web Agent
│   ├── config.yaml / prompt.md / SOUL.md / TOOLS.md
│   ├── prompt_results/: simple/medium/complex/intent_prompt + _metadata + agent_schema
│   └── skills/: 80+ Skills + skill_registry.yaml
│
├── dazee_agent/                       ← Dazee Agent
│   ├── config.yaml / prompt.md
│   ├── api_desc/: coze-api.md / wenshu-api.md
│   ├── prompt_results/: simple/medium/complex/intent_prompt + _metadata + agent_schema
│   └── skills/: ontology-builder / remotion (含 rules/ 28 个 .md + assets/ 8 个 .tsx)
│
└── _template/                         ← 实例模板
    ├── config.yaml / config_example_full.yaml / config_example_minimal.yaml
    ├── prompt.md / env.example / CONFIGURATION_GUIDE.md / README.md
    ├── api_desc/_template.md │ prompt_results/README.md
    ├── skills/: README.md / skill_registry.yaml / _template/SKILL.md
    └── workers/README.md
```

### 0.5 支撑模块完整清单

```
┌─── models/ (Pydantic 数据模型) ─────────────────────────────────────┐
│  agent.py │ api.py │ chat.py │ chat_request.py │ database.py        │
│  docs.py │ file.py │ hitl.py │ llm.py │ mcp.py │ mem0.py           │
│  realtime.py │ scheduled_task.py │ skill.py │ tool.py │ usage.py   │
└─────────────────────────────────────────────────────────────────────┘

┌─── prompts/ (提示词模板) ───────────────────────────────────────────┐
│  intent_recognition_prompt.py │ plan_generator_prompt.py            │
│  prompt_selector.py │ simple_prompt.py │ standard_prompt.py         │
│  universal_agent_prompt.py │ skills_loader.py │ skills_metadata.txt │
│  MEMORY_PROTOCOL.md                                                 │
│  factory/: schema_generator.md                                      │
│  fragments/: code_rules.md │ excel_rules.md │ ppt_rules.md          │
│  templates/: complex_prompt_generation.md │ medium_prompt_generation │
│              simple_prompt_generation.md │ intent_prompt_generation  │
│              prompt_example.md                                       │
└─────────────────────────────────────────────────────────────────────┘

┌─── tools/ (可调用工具) ────────────────────────────────────────────┐
│  base.py │ api_calling.py │ clue_generation.py │ nodes_tool.py      │
│  plan_todo_tool.py │ request_human_confirmation.py                  │
│  scheduled_task_tool.py │ send_files.py                             │
└─────────────────────────────────────────────────────────────────────┘

┌─── utils/ (工具函数) ──────────────────────────────────────────────┐
│  app_paths.py │ cache_utils.py │ file_handler.py │ file_processor.py│
│  instance_loader.py (1905行) │ json_file_store.py │ json_utils.py   │
│  message_utils.py │ query_utils.py                                  │
│  background_tasks/:                                                 │
│    scheduler.py │ registry.py │ service.py │ context.py             │
│    tasks/: clue_generation.py │ mem0_update.py                      │
│            recommended_questions.py │ title_generation.py           │
└─────────────────────────────────────────────────────────────────────┘

┌─── config/ (配置文件) ─────────────────────────────────────────────┐
│  capabilities.yaml │ context.yaml │ context_compaction.yaml         │
│  prompt_config.yaml │ resilience.yaml │ routing_rules.yaml          │
│  scheduled_tasks.yaml │ tool_registry.yaml                          │
│  llm_config/: __init__.py │ loader.py │ profiles.yaml               │
│               profiles.example.yaml │ README.md │ REORGANIZATION.md │
│               qwen_fallback_optimization.md                         │
│               qwen_recommended_configs.md                           │
└─────────────────────────────────────────────────────────────────────┘

┌─── skills/ (全局技能库) ───────────────────────────────────────────┐
│  library/: 80+ Skills (与 client_agent 共用) │ README.md            │
│  custom_claude_skills/: __init__.py                                 │
└─────────────────────────────────────────────────────────────────────┘

┌─── evaluation/ (评估框架) ─────────────────────────────────────────┐
│  harness.py │ metrics.py │ models.py │ qos_config.py │ calibration  │
│  alerts.py │ dashboard.py │ ci_integration.py                       │
│  promptfoo_adapter.py │ case_converter.py │ case_reviewer.py        │
│  verify_imports.py                                                  │
│  graders/: code_based.py │ human.py │ model_based.py                │
│  config/: settings.yaml                                             │
│  suites/: coding/basic_code_generation.yaml                         │
│           conversation/intent_understanding.yaml                    │
│           intent/haiku_accuracy.yaml                                │
│           promptfoo/README.md │ regression/README.md                │
│  reports/: intent_accuracy_*.json (7 份报告)                        │
└─────────────────────────────────────────────────────────────────────┘

┌─── scripts/ (运维与验证脚本) ──────────────────────────────────────┐
│  verify_v11_architecture.py (119/119 通过)                          │
│  verify_memory_knowledge.py (41/41 通过)                            │
│  verify_e2e_consistency.py (1175行)                                 │
│  sync_capabilities.py │ check_instance_dependencies.py              │
│  build_app.sh │ build_backend.py                                    │
└─────────────────────────────────────────────────────────────────────┘

┌─── 根目录文件 ─────────────────────────────────────────────────────┐
│  main.py (FastAPI 入口) │ .env.development │ zenflux-backend.spec   │
└─────────────────────────────────────────────────────────────────────┘
```

### 0.6 模块完成度热力图

```
██████████  95%  Agent 引擎层 (RVR / RVR-B / 回溯 / 错误分类)
██████████  95%  自适应终止策略 (五维度终止)
██████████  95%  实例骨架与配置
██████████  95%  存储层 (SQLite + FTS5 + sqlite-vec)
█████████░  90%  状态一致性管理 (快照/回滚)
█████████░  90%  意图识别简化
████████░░  85%  记忆系统 (三层架构)
████████░░  85%  进度转换器
████████░░  80%  本地知识检索 (FTS5)
████████░░  80%  Skills 二维分类框架
███████░░░  70%  三大核心能力
███████░░░  70%  Skill 格式规范
████░░░░░░  40%  OS 兼容层 (仅 macOS)
███░░░░░░░  35%  应用发现 (仅 macOS 扫描)
░░░░░░░░░░   5%  项目管理 (骨架占位)
░░░░░░░░░░   0%  Skills 安全验证
░░░░░░░░░░   0%  前端 UI (向导/仪表板/MCP Apps)
```

---

## 一、整体完成度概览

| 架构层 | 设计章节 | 完成度 | 状态 |
|--------|----------|--------|------|
| 实例骨架与配置 | 1.1 | 95% | 已完成 |
| Skills 二维分类 | 3.1.1 | 80% | 框架完成，具体 Skills 待创建 |
| 自适应终止策略 | 3.4 | 95% | 已完成 |
| 状态一致性管理 | 3.3 | 90% | 已完成 |
| Agent 引擎层 | — | 95% | RVR + RVR-B 双引擎，complexity 策略路由 |
| 意图识别简化 | 3.7.1 | 90% | 已完成 |
| 进度转换器 | 3.7.2 | 85% | 已完成 |
| 本地知识检索 | 3.8 | 80% | FTS5 已完成，语义搜索待实现 |
| 记忆系统 | 3.13 | 85% | 三层架构已完成 |
| Nodes 本地操作 | 3.5 | 80% (macOS) | macOS 11 项操作完整，win32/linux 待实现 |
| OS 兼容层 | 3.5 | 40% | 仅 macOS 实现 |
| 应用发现 | 3.11 | 35% | 仅 macOS 扫描 |
| 项目管理 | 3.10 | 5% | 骨架占位 |
| 存储层 | — | 95% | SQLite + FTS5 + sqlite-vec 完整 |
| Skill 格式规范 | 3.2 | 70% | 基础格式已有，xiaodazi 扩展字段待补全 |
| Skills 安全验证 | 3.12 | 0% | 未开始 |
| 大模型配置简化 | 3.1.2 | 0% | 未开始（前端 UI 范畴） |
| 首次启动向导 | 3.1.3 | 0% | 未开始（前端 UI 范畴） |
| 服务状态仪表板 | 3.1.5 | 0% | 未开始（前端 UI 范畴） |
| MCP Apps UI | 3.6 | 0% | 未开始（前端 UI 范畴） |
| 三大核心能力 | 3.9 | 70% | "会干活"完整，"会思考"完整，"会学习"部分完成 |

---

## 二、逐模块详细状态

### 2.1 实例骨架与配置

**设计需求**：创建 `instances/xiaodazi/` 目录，包含配置、提示词、Skills 注册表。

| 文件 | 行数 | 状态 | 说明 |
|------|------|------|------|
| `instances/xiaodazi/config.yaml` | 171 | 已完成 | 包含 termination、knowledge、memory、project、skills 完整配置段 |
| `instances/xiaodazi/prompt.md` | 63 | 已完成 | 小搭子人格提示词，含 Few-Shot 示例 |
| `instances/xiaodazi/skills/skill_registry.yaml` | 86 | 已完成 | Skills 注册表 |
| `utils/instance_loader.py` | 1905 | 已完成 | 支持加载 termination / knowledge / memory / project / state_consistency |

**遗留**：
- `config.yaml` 中 `knowledge` 和 `memory` 配置段完整，但 `skills` 二维分类的 `lightweight`/`external`/`cloud_api` 级别的具体 Skill 条目较少

---

### 2.2 Skills 二维分类体系（3.1.1）

**设计需求**：OS（common/darwin/win32/linux）× 依赖复杂度（builtin/lightweight/external/cloud_api）

| 文件 | 行数 | 状态 | 说明 |
|------|------|------|------|
| `core/skill/os_skill_merger.py` | 136 | 已完成 | `get_enabled_skills()` / `get_unavailable_skills()` |
| `core/skill/os_compatibility.py` | 110 | 已完成 | `CompatibilityStatus`（ready/need_auth/need_setup/unavailable）四状态 |
| `core/skill/dynamic_loader.py` | 298 | 已完成 | 集成 `OSSkillMerger`，支持 `get_eligible_skills()` |
| `core/prompt/runtime_context_builder.py` | 539 | 已完成 | 含 `build_skill_status_prompt()` 注入 Skill 状态 |

**已完成的设计要求**：
- OS 检测 + 合并逻辑
- 四状态管理（ready / need_auth / need_setup / unavailable）
- Skill 状态注入系统提示词
- 依赖检查（bins / env / OS 兼容性）

**遗留**：
- `lightweight` 级别的自动 `pip install` 逻辑未实现（标记为 ready，首次使用时安装）
- `cloud_api` 级别的 API Key 检测逻辑未实现
- 具体的 builtin Skills（如 `summarize`、`canvas`、`translator`）大部分未创建

---

### 2.3 自适应终止策略（3.4）— V12 回溯↔终止联动重构

**设计需求**：八维度终止判断（V12 从五维度扩展为八维度）

| 文件 | 行数 | 状态 | 说明 |
|------|------|------|------|
| `core/termination/protocol.py` | 90+ | 已完成 | V12: 新增 `FinishReason` 枚举（13 个终止原因） |
| `core/termination/adaptive.py` | 320+ | 已完成 | V12.1: 八维度终止 + 回溯感知 + 智能费用感知 |
| `core/agent/execution/rvrb.py` | 1100+ | 已完成 | V12.1: 回溯↔终止联动 + HITL 三选一 + 阶梯式费用提醒 |
| `core/agent/execution/rvr.py` | 817 | 已完成 | 同上（基础 RVR 未改动） |
| `core/context/runtime.py` | 716 | 已完成 | V12: 新增回溯状态字段（信息共享层） |

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

| 文件 | 行数 | 状态 | 说明 |
|------|------|------|------|
| `core/state/consistency_manager.py` | 796 | 已完成 | 快照 / 操作日志 / 回滚 / 提交 / 前置检查 / 后置检查 |
| `core/state/operation_log.py` | 321 | 已完成 | `OperationRecord` + inverse-patch 自动逆操作 |
| `core/agent/base.py` | 797 | 已完成 | `execute()` 中集成快照/提交/异常回滚 |
| `core/events/broadcaster.py` | 988 | 已完成 | `emit_rollback_options()` / `emit_rollback_result()` |

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

### 2.5 Agent 引擎层（策略路由）

**设计**：双执行器 + 基于 LLM 意图识别的策略路由。

| 执行器 | 文件 | 行数 | 特性 |
|--------|------|------|------|
| `RVRExecutor` | `core/agent/execution/rvr.py` | 817 | 标准循环，无回溯开销 |
| `RVRBExecutor` | `core/agent/execution/rvrb.py` | 939 | 带回溯，错误分类 + 候选方案重试 |

**策略路由**（`core/agent/base.py` execute 方法中）：

```
IntentAnalyzer（LLM 语义判断）
        |
        v
  complexity == "simple"  → RVR   （天气/翻译/查询，1-2 轮完成）
  complexity == "medium"  → RVR-B （搜索+总结，可能需回溯）
  complexity == "complex" → RVR-B （调研报告，多步骤+回溯保障）
```

**设计原则**：
- complexity 由 LLM 语义判断（LLM-First），不做关键词匹配
- 策略映射是确定性规则（simple -> RVR，其他 -> RVR-B），符合规范允许的场景
- 默认 RVR-B（未知 complexity 时保守选择）

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

| 文件 | 行数 | 状态 | 说明 |
|------|------|------|------|
| `infra/local_store/generic_fts.py` | 615 | 已完成 | 通用 FTS5 引擎，CJK 字符级分割 + 逆向合并 |
| `core/knowledge/local_search.py` | 298 | 已完成 | `LocalKnowledgeManager`，FTS5 搜索 + add/remove |
| `core/knowledge/file_indexer.py` | 320 | 已完成 | 增量索引，分块，txt/md/pdf/docx |
| `infra/local_store/models.py` | 350+ | 已完成 | 含 `LocalIndexedFile` 元数据模型 |
| `infra/local_store/engine.py` | 223 | 已完成 | WAL + 7 项 PRAGMA 优化 |

**已完成的设计要求**：
- Level 1 全文搜索（SQLite FTS5，零配置零依赖）
- CJK 中文搜索支持（字符级分割 + snippet 逆向合并）
- BM25 排序 + snippet 高亮
- 文件分块（智能句子/段落边界切分）
- 增量索引（SHA256 hash check）
- 多格式支持（txt/md 原生，pdf/docx 可选依赖）
- FTS5 最佳实践（automerge / integrity-check / optimize / 损坏自动恢复）
- 小白用户防御（FTS5 特殊字符自动移除）
- Python 后过滤 UNINDEXED 列（跨 SQLite 版本兼容）

**遗留**：
- Level 2 语义搜索（`_semantic_search()`）未实现（接口已预留）
- 文件夹监听（watchdog）未实现
- 首次使用时 UI 文件夹选择引导未实现（前端范畴）

---

### 2.7 记忆系统（3.13）

**设计需求**：三层架构 — 文件层（MEMORY.md）/ 索引层（FTS5）/ 智能层（Mem0）

| 文件 | 行数 | 状态 | 说明 |
|------|------|------|------|
| `core/memory/markdown_layer.py` | 409 | 已完成 | Layer 1：MEMORY.md 模板 + 段落追加 + 每日日志 + 项目记忆 |
| `core/memory/xiaodazi_memory.py` | 513 | 已完成 | 三层入口：recall 融合搜索 / remember 双写 / flush 提取+日志 |
| `core/memory/mem0/pool.py` | 452 | 已完成 | Layer 3：Mem0 语义搜索 + 向量存储 |
| `core/memory/mem0/update/quality_control.py` | 730+ | 已完成 | 冲突检测 + 更新决策（LLM 驱动） |
| `core/memory/mem0/extraction/extractor.py` | 555 | 已完成 | 碎片记忆提取（FragmentExtractor） |

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

| 文件 | 行数 | 状态 | 说明 |
|------|------|------|------|
| `core/planning/progress_transformer.py` | 90 | 已完成 | `transform()` + `transform_and_emit()` 集成事件系统 |
| `core/events/broadcaster.py` | — | 已完成 | `emit_progress_update()` 事件方法 |

**遗留**：
- `transform()` 当前直接使用 plan_step 描述，未做 LLM 驱动的用户友好化转换（设计要求"内部复杂，外部简单"）
- 未集成到 PlanTodoTool 的执行流程中（需在 plan 步骤完成时自动调用）

---

### 2.9 意图识别简化（3.7.1）

| 文件 | 行数 | 状态 | 说明 |
|------|------|------|------|
| `core/routing/intent_analyzer.py` | 277 | 已完成 | 支持 `fast_mode` / `semantic_cache_threshold` / `simplified_output` |

**已完成**：
- `fast_mode: true` 使用更快模型（如 haiku）
- `semantic_cache_threshold` 可配置（提高到 0.90 减少 LLM 调用）
- `simplified_output: true` 跳过不必要字段

---

### 2.9 OS 兼容层（3.5）

| 文件 | 行数 | 状态 | 说明 |
|------|------|------|------|
| `core/discovery/app_scanner.py` | 64 | 部分实现 | `_scan_darwin()` 有实际逻辑，win32/linux 为空 |
| `core/prompt/runtime_context_builder.py` | 539 | 已完成 | macOS / Linux 能力提示词 |

**遗留**：
- `nodes/local/windows.py` — 不存在
- `nodes/local/linux.py` — 不存在
- `AppScanner._scan_win32()` — 空实现
- `AppScanner._scan_linux()` — 空实现
- `AppScanner.get_capabilities()` — 空实现
- `AppScanner.find_app_for_task()` — 空实现

---

### 2.10 项目管理（3.10）

| 文件 | 行数 | 状态 | 说明 |
|------|------|------|------|
| `core/project/manager.py` | 40 | 骨架占位 | 所有方法为 `pass` / `return []` |

**未实现**：
- `create_project(name, template)` — 项目创建
- `switch_project(project_id)` — 项目切换（上下文/知识库/playbook 隔离）
- `delete_project(project_id)` — 项目删除
- `list_projects()` — 项目列表
- 项目模板系统（写稿搭子/表格搭子/研究搭子/办公搭子）
- 项目数据结构（`~/.xiaodazi/projects/{name}/`）

---

### 2.11 存储层

| 文件 | 行数 | 状态 | 说明 |
|------|------|------|------|
| `infra/local_store/engine.py` | 223 | 已完成 | aiosqlite + WAL + 7 项 PRAGMA |
| `infra/local_store/fts.py` | 274 | 已完成 | 消息专用 FTS5 |
| `infra/local_store/generic_fts.py` | 615 | 已完成 | 通用 FTS5（知识/记忆共用） |
| `infra/local_store/vector.py` | 192 | 已完成 | sqlite-vec 向量搜索 |
| `infra/local_store/models.py` | 350+ | 已完成 | ORM 模型 + LocalIndexedFile |
| `infra/local_store/workspace.py` | — | 已完成 | 统一管理器 |
| `infra/local_store/skills_cache.py` | — | 已完成 | Skills 延迟加载缓存 |

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

### 2.12 Skill 格式规范（3.2）

**已有**：`instances/xiaodazi/skills/` 下已有部分 SKILL.md，遵循 OpenClaw 兼容格式。

**遗留**：
- `metadata.xiaodazi` 扩展字段（`dependency_level` / `ui_template` / `user_facing`）未在现有 Skills 中普及
- Skills 签名验证机制（3.12）完全未实现

---

### 2.13 Nodes 本地操作工具（3.5 OS 兼容层）

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

| 文件 | 行数 | 状态 | 说明 |
|------|------|------|------|
| `tools/nodes_tool.py` | 240 | 已完成 | 工具入口：5 个 action（status/describe/run/notify/which） |
| `core/nodes/manager.py` | 292 | 已完成 | 节点管理器：注册/发现/路由 |
| `core/nodes/protocol.py` | 206 | 已完成 | 协议定义：所有支持的命令类型 |
| `core/nodes/local/base.py` | 183 | 已完成 | 本地节点基类 |
| `core/nodes/local/macos.py` | 352 | 已完成 | macOS 实现（AppleScript/截图/剪贴板等） |
| `core/nodes/executors/shell.py` | 275 | 已完成 | Shell 命令执行器（超时/安全/输出捕获） |

**总计**：约 1,400 行，架构完整。

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

### 2.14 三大核心能力总览（3.9）

| 能力 | 技术实现 | 状态 |
|------|----------|------|
| **会干活** — 工具调用 | `core/tool/` + Skills | 已完成 |
| **会干活** — 文件/系统操作 | `core/nodes/` + `tools/nodes_tool.py` | macOS 完整（11 项操作），win32/linux 待实现（详见 2.13） |
| **会干活** — 应用联动 | `AppScanner` + `RuntimeContextBuilder` | macOS 部分完成 |
| **会思考** — 智能回溯 | `core/agent/execution/rvrb.py` | 已完成 |
| **会思考** — 错误分类 | `core/agent/backtrack/error_classifier.py` | 已完成 |
| **会思考** — 自主规划 | `core/planning/` | 已完成 |
| **会思考** — 环境感知 | `RuntimeContextBuilder` | 已完成 |
| **会学习** — 记忆系统 | `XiaodaziMemoryManager` 三层 | 已完成 |
| **会学习** — Playbook | `core/playbook/` | 框架存在，xiaodazi 未集成（详见 2.14） |
| **会学习** — 奖励归因 | `core/playbook/reward.py` | 框架存在，xiaodazi 未集成（详见 2.14） |

---

### 2.15 Playbook 持续学习引擎

**价值定位**：从成功的任务执行中自动提取可复用策略，下次遇到类似任务时直接套用，让小搭子"用得越久，越聪明"。

**与记忆系统的互补关系**：

| 维度 | 记忆系统（Memory） | Playbook |
|------|-------------------|----------|
| 存什么 | 用户偏好/事实/习惯 | 执行策略/工具序列/质量指标 |
| 谁写入 | 对话中自动提取 | 任务成功后提取，**用户确认**入库 |
| 谁读取 | recall() 注入系统提示词 | find_matching() 注入执行计划 |
| 粒度 | 条目级（"喜欢简洁风格"） | 流程级（"写公众号的完整步骤"） |

#### 当前实现状态

| 组件 | 文件 | 行数 | 状态 |
|------|------|------|------|
| `PlaybookEntry` 数据结构 | `core/playbook/manager.py` | 757 | 已完成：CRUD + 审核流程 + 匹配算法 |
| `extract_from_session()` | 同上 | — | 已完成：从 SessionReward 提取策略 |
| `find_matching()` | 同上 | — | 已完成：按任务上下文匹配最佳策略 |
| `FileStorage` | `core/playbook/storage.py` | 308 | 已完成：JSON 文件持久化 |
| `DatabaseStorage` | 同上 | — | 不可用：依赖已删除的 `infra.database` |
| 状态流转 | 同上 | — | 已完成：DRAFT -> PENDING_REVIEW -> APPROVED/REJECTED |

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

#### 4 条断裂的链路

| 断裂点 | 说明 | 修复方案 |
|--------|------|----------|
| Agent 完成 -> 生成 DRAFT | 无调用者触发提取 | `base.py` execute 结束后调用 `extract_from_session()` |
| DRAFT -> 用户确认 | 无事件推送到前端 | `EventBroadcaster` 新增 `emit_playbook_suggestion()` |
| 用户确认 -> APPROVED | 无确认回调处理 | 新增 API 端点接收用户确认/拒绝 |
| 新任务 -> 匹配策略注入 | Agent 路由/提示词未调用 | 新增 `PlaybookContextProvider`（Phase 1 Injector），注入到 messages 层面而非 system prompt，避免缓存失效 |

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

## 三、不涉及（前端 UI / 桌面应用范畴）

以下模块在架构设计中定义但属于前端/桌面应用团队职责，当前后端不涉及：

| 需求 | 设计章节 | 说明 |
|------|----------|------|
| 首次启动配置向导 | 3.1.3 | Vue 组件 |
| Skill 配置向导 | 3.1.4 | Vue 组件 |
| 服务状态仪表板 | 3.1.5 | Vue 组件 |
| MCP Apps UI | 3.6 | iframe + postMessage |
| 回滚选项 UI | 3.3 | 后端事件已就绪，前端渲染待实现 |
| 进度展示组件 | 3.7.2 | 后端事件已就绪，前端渲染待实现 |
| Playbook 确认 UI | 2.14 | 后端事件待实现，前端渲染待实现 |
| Tauri 桌面框架 | — | 桌面壳 |
| Ollama 安装向导 | 3.1.2 | 跨平台安装 UI |

---

## 四、优先级建议（后端待办）

### P0 — 核心体验缺口

| 项目 | 涉及文件 | 工作量 | 说明 |
|------|----------|--------|------|
| 项目管理器实现 | `core/project/manager.py` | 中 | 从骨架到完整实现，依赖记忆和知识检索 |
| 记忆混合检索权重 | `core/memory/xiaodazi_memory.py` | 小 | config 已声明 `vector_weight`/`bm25_weight`，recall 中应用 |
| ProgressTransformer 集成 | `core/planning/` | 小 | 在 PlanTodoTool 步骤完成时自动调用 |

### P1 — 完善已有功能

| 项目 | 涉及文件 | 工作量 | 说明 |
|------|----------|--------|------|
| 知识检索语义搜索 | `core/knowledge/local_search.py` | 中 | 复用 `infra/local_store/vector.py` |
| 记忆文件监听同步 | `core/memory/` | 中 | watchdog 监听 MEMORY.md 变更 |
| Skill 具体创建 | `instances/xiaodazi/skills/` | 大 | 按二维矩阵创建 builtin + lightweight Skills |
| Playbook 端到端集成 | 见下方独立计划 | 中 | 串联 4 条断裂链路 |

### Playbook 集成实施计划

串联 4 条断裂链路，让 Playbook 从"代码完整但无调用者"变为"端到端可用"。

**Step 1: 存储迁移** — `core/playbook/storage.py`
- 将 `DatabaseStorage` 从已删除的 `infra.database` 迁移到 `infra/local_store` 的 aiosqlite 引擎
- 或标记 `DatabaseStorage` 为不可用，默认使用 `FileStorage`（已完整实现）

**Step 2: 配置声明** — `instances/xiaodazi/config.yaml`
```yaml
playbook:
  enabled: true
  auto_extract: true           # 任务完成后自动 LLM 初筛
  min_reward_threshold: 0.7    # 初筛最低分
  require_user_confirm: true   # 用户确认闸门（核心）
  storage_backend: "file"
  storage_path: "~/.xiaodazi/playbooks"
```

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

**Step 6: 链路 4 — 新任务策略注入（Context Injector 方案）**

核心矛盾：Claude API 的 system prompt 缓存（`cache_control`）要求内容稳定，如果把 Playbook 策略注入 system prompt 会导致缓存全部失效、token 成本翻倍。

解决方案：**注入到 messages 层面（Context Injector），不动 system prompt**。

```
┌──────────────────────────────────────────┐
│ system prompt（固定，缓存命中）            │
│   ├─ 人格提示词（prompt.md）  <- 有缓存   │
│   ├─ 工具定义                 <- 有缓存   │
│   └─ 运行时环境               <- 有缓存   │
├──────────────────────────────────────────┤
│ messages（动态，不影响 system 缓存）       │
│   ├─ ...历史对话...                       │
│   ├─ [injected] Playbook 策略上下文       │
│   └─ user: "帮我写公众号"                 │
└──────────────────────────────────────────┘
```

实现方式：在 `core/context/injectors/` 中新增 `playbook_provider.py` 作为 Phase 1 注入器（与 tool_provider / memory_provider 同级）：

```python
# core/context/injectors/phase1/playbook_provider.py
class PlaybookContextProvider:
    async def inject(self, messages, context):
        matches = playbook_manager.find_matching(context)
        if not matches:
            return messages
        # 在最后一条用户消息之前插入策略上下文
        strategy_msg = {
            "role": "user",
            "content": (
                "[系统上下文 - 历史成功策略参考]\n"
                f"{format_playbook(matches[0])}\n"
                "你可以参考，也可以根据当前情况调整。"
            ),
        }
        messages.insert(-1, strategy_msg)
        return messages
```

效果对比：

| 方案 | system 缓存 | LLM 可见 | 推荐 |
|------|------------|----------|------|
| 注入 system prompt | 缓存失效 | 每轮看到 | 不推荐 |
| **注入 messages（Injector）** | **零影响** | **首轮看到** | **推荐** |
| 仅在 Plan 阶段注入 | 零影响 | 仅 plan | 简单任务漏掉 |

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

## 五、文件清单

### 新建文件（本轮实施）

| 文件 | 行数 | 职责 |
|------|------|------|
| `infra/local_store/generic_fts.py` | 615 | 通用 FTS5 全文搜索引擎 |
| `core/memory/markdown_layer.py` | 409 | MEMORY.md 文件层 |
| `scripts/verify_memory_knowledge.py` | 400+ | 端到端验证脚本（41 项断言） |
| `scripts/verify_v11_architecture.py` | 300+ | 架构完整性验证（119 项断言） |

### 改造文件（本轮实施）

| 文件 | 职责 |
|------|------|
| `core/memory/xiaodazi_memory.py` | 48→513 行，三层架构入口 |
| `core/knowledge/local_search.py` | 59→298 行，FTS5 搜索实现 |
| `core/knowledge/file_indexer.py` | 42→320 行，增量文件索引 |
| `core/termination/adaptive.py` | 五维度终止 + HITL |
| `core/state/consistency_manager.py` | 快照/回滚完整实现 |
| `core/events/broadcaster.py` | 新增 rollback + progress 事件 |
| `core/agent/base.py` | 集成终止策略 + 状态一致性 |
| `infra/local_store/engine.py` | 7 项 PRAGMA 优化 |
| `instances/xiaodazi/config.yaml` | 完整配置段 |

### 验证结果

| 验证脚本 | 结果 |
|----------|------|
| `scripts/verify_v11_architecture.py` | 119/119 通过 |
| `scripts/verify_memory_knowledge.py` | 41/41 通过 |
| `python -c "from main import app"` | 102 路由正常加载 |
