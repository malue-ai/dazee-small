# 小搭子 Agent 实例 — 当前实现架构文档

> 基于《小搭子专用实例架构设计》(V9.0) 需求文档，对照当前代码实现的完整状态梳理。
>
> 范围：Python 后端 + 框架核心层 + Vue 前端 + Tauri 桌面壳。
>
> 更新时间：2026-02-08（第二次更新：实例存储隔离 + 后台任务 + Skills 扩充 + 路径管理）
>
> 更新时间：2026-02-09（第三次更新：项目编辑 + 多 Provider 批量保存 + Skills 注册格式重构 + Windows 打包）
>
> 更新时间：2026-02-09（第四次更新：测试驱动全面核实——import 验证 + Skills 一致性 + E2E 报告真实性 + 链路断裂检查）

---

### ⚠️ 第四次更新发现的关键问题（测试驱动验证）


| 3 | **Playbook 端到端链路断裂** | 🟡 中 | `base.py` 中虽含 "playbook" 字样但**未调用** `extract_from_session()` 或 `PlaybookManager`。Hint 注入（Phase 2）已实现，但 DRAFT 生成 → 用户确认 → APPROVED 三条链路均断开。 |
| 4 | **文档记忆模块名错误** | 🟡 中 | 文档中 `core.memory.instance_memory` 不存在，实际模块为 `core.memory.instance_memory`（类名 `InstanceMemoryManager`）。 |
| 5 | **tool_registry.yaml 注册为空** | 🟡 中 | 文件存在（720 字符）但仅有注释和空结构，`tools` 列表解析为 0 项。工具注册实际通过 `capabilities.yaml` 完成（9 个工具）。 |
| 6 | **残留垃圾文件** | 🟢 低 | `tools/request_human_confirmation _copy.py`（文件名含空格的副本文件）。 |
| 7 | **实例目录混乱** | 🟡 中 | 存在未清理的实例：`b307fc3d`（仅 1 文件，无 config）、`xiaodazi_backup`（无 prompt）、`42c0dcfb` / `820e1326`（无 config）。 |
| 9 | **旧存储路径残留** | 🟡 中 | `data/local_store/xiaodazi/` 仍存在（3 文件），应已迁移到 `data/instances/xiaodazi/db/`。 |

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
│  │                   │ instance_memory.py                   │                          │ │
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
│  ├── 记忆提取: instance_memory.flush → FragmentExtractor → 双写      │
│  ├── 事件广播: broadcaster → SSE → 前端                               │
│  ├── 后台任务: title_generation / mem0_update / recommended_questions │
│  └── 知识索引: file_indexer → generic_fts → FTS5 增量索引             │
└──────────────────────────────────────────────────────────────────────┘
```

### 0.3 存储架构（实例隔离）

**设计原则**：所有运行时数据按实例名称隔离，通过 `AGENT_INSTANCE` 环境变量驱动。共享资源（如 Embedding 模型）单独目录复用。

```
┌─────────────────────────────────────────────────────────────────────┐
│             SQLite 统一存储 (WAL 模式) — 实例隔离                    │
│                                                                     │
│  路径布局：{user_data_dir}/data/instances/{instance_name}/           │
│  开发时: 项目根/data/instances/xiaodazi/                             │
│  打包后: ~/Library/Application Support/com.zenflux.agent/data/...   │
│                                                                     │
│  ┌── 实例数据库 (db/instance.db) ──────────────────────────────┐   │
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
│  ┌── 实例文件系统（按实例隔离）─────────────────────────────────┐   │
│  │  data/instances/{name}/db/instance.db     — 主数据库          │   │
│  │  data/instances/{name}/memory/MEMORY.md   — 用户记忆文件      │   │
│  │  data/instances/{name}/store/memory_fts.db — 记忆 FTS 索引    │   │
│  │  data/instances/{name}/store/mem0_vectors.db — Mem0 向量库    │   │
│  │  data/instances/{name}/storage/           — 文件上传存储      │   │
│  │  data/instances/{name}/playbooks/         — Playbook 策略库   │   │
│  │  data/instances/{name}/snapshots/         — 状态快照          │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌── 共享资源（多实例复用）─────────────────────────────────────┐   │
│  │  data/shared/models/          — Embedding 模型（如 bge-m3）  │   │
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
│  app_paths.py (统一路径管理：双模式 + 实例隔离)                      │
│  cache_utils.py │ file_handler.py │ file_processor.py               │
│  instance_loader.py │ json_file_store.py │ json_utils.py            │
│  message_utils.py │ query_utils.py                                  │
│  background_tasks/:                                                 │
│    scheduler.py │ registry.py │ service.py (两级调度) │ context.py  │
│    tasks/: mem0_update.py │ recommended_questions.py                │
│            title_generation.py │ memory_flush.py (会话记忆提取)     │
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

### 0.6 模块完成度热力图（测试驱动验证，2026-02-09）

> 以下百分比基于 import 验证 + 链路测试 + 数据一致性检查，**非自评**。

```
████████░░  85%  Agent 引擎层 (V10.0 统一 Agent + RVR-B，但 Playbook 链路断)
████████░░  85%  自适应终止策略 (八维度完整，但前端 HITL 事件渲染全部未实现)
█████████░  90%  实例骨架与配置 (三文件分级 + Provider 切换，但实例目录有残留)
████████░░  85%  存储层 (SQLite + FTS5 + sqlite-vec，但旧路径 data/local_store 残留)
████████░░  80%  状态一致性管理 (已启用实例配置 + 路径/持久化修复；Rollback E2E 最新 2/2 PASS)
████████░░  85%  实例存储隔离 (全组件感知 AGENT_INSTANCE，但旧路径未清理)
█████████░  90%  FastAPI 服务端 (9 路由 + 8 服务 + 72 端点 + WebSocket，import 通过)
███████░░░  75%  前端实现 (31 Vue + 9 Store + 5 Composables，但未验证构建/运行)
████████░░  85%  意图识别 (V12.0 SkillGroupRegistry 链路验证通过)
████████░░  80%  上下文注入器 (7 个 Injector import 通过，Playbook 注入无数据源)
█████████░  85%  Plan 规划系统 (渐进式展示已实现)
████████░░  80%  记忆系统 (三层架构 import 通过，模块名不一致: instance_memory 非 instance_memory)
████████░░  80%  进度转换与事件推送 (ProgressTransformer 已实现，未集成到 PlanTodo 流程)
██████░░░░  60%  Skills 体系 (68 目录 / 76 注册 / 99 配置 — 三处数据严重不一致 ⚠️)
████████░░  85%  本地知识检索 (FTS5 + 向量混合搜索 import 通过)
████░░░░░░  40%  E2E 评估框架 (6 用例定义但 turns=0；报告 6/6 PASS 但无评分详情 ⚠️)
████████░░  80%  后台任务系统 (两级调度 + 4 个任务，memory_flush 链路验证通过)
████████░░  80%  打包与桌面端路径 (双模式路径，Win/Linux 未验证)
███████░░░  70%  项目管理 (多实例架构，但实例目录混乱: 残留测试实例未清理)
████████░░  80%  前端 Settings (多 Provider 批量保存)
████████░░  75%  首次启动引导 (9 步引导)
█████░░░░░  50%  Playbook 持续学习 (Hint 注入已实现，但 3/4 链路断裂且无调用者)
████░░░░░░  40%  OS 兼容层 (仅 macOS)
███░░░░░░░  35%  应用发现 (仅 macOS 扫描)
████████░░  80%  三大核心能力 (Rollback 已修复并启用，Playbook 链路仍断)
░░░░░░░░░░   0%  Skills 安全验证
```

---

## 一、当前智能体与 LLM（要点）

| 项 | 说明 |
|----|------|
| **Agent 架构** | V10.0 统一 Agent 类（`core/agent/base.py`），Strategy 模式通过 Executor 注入。`AgentFactory` 从 `AgentSchema` 动态初始化。⚠️ `base.py` 引用了 playbook 概念但**未实际调用** `PlaybookManager.extract_from_session()`。 |
| **LLM 切换** | `config.yaml` 的 `agent.provider` 一键切换。Provider 模板在 `config/llm_profiles.yaml`（heavy/light 分级）。**13 个**内部调用点（验证: intent_analyzer / semantic_inference / tool_capability_inference / background_task / plan_generator / plan_manager / fragment_extractor / behavior_analyzer / memory_update / llm_analyzer / schema_generator / prompt_merger / prompt_decomposer）。 |
| **意图路由** | `IntentAnalyzer` 三层缓存（Hash → Semantic → LLM）。V12.0 从 `SkillGroupRegistry` 动态获取分组描述（链路验证通过）。输出: complexity + skip_memory + is_follow_up + wants_to_stop + relevant_skill_groups（21 个分组）。 |
| **执行策略** | V11.0 固定 RVR-B（`AgentRouter` 不再路由到 RVR）。RVR-B 支持错误分类 + 回溯 + Context Pollution 清理。⚠️ 前端 HITL 事件（backtrack_exhausted_confirm / intent_clarify / cost_limit 等）渲染**全部未实现**。 |
| **记忆** | 三层架构：`InstanceMemoryManager`（⚠️ 文档原写 `InstanceMemoryManager` 不准确，实际类名为 `InstanceMemoryManager`，模块为 `core.memory.instance_memory`）。recall/remember/flush 统一入口。memory_flush 后台任务链路验证通过。 |
| **Playbook** | ⚠️ **链路断裂**：PlaybookHintInjector（Phase 2）已实现注入，但无数据源。`base.py` 不调用 `extract_from_session()`，DRAFT 生成 / 用户确认 / APPROVED 三条链路均断开。FileStorage 存在但数据库为空。 |

---

## 二、整体完成度概览（测试驱动修正）

> 以下完成度基于 import 验证、链路测试、数据一致性检查。标 ⚠️ 的表示实测与原文档声称不符。

| 架构层 | 设计章节 | 完成度 | 验证方式 | 状态 |
|--------|----------|--------|----------|------|
| Agent 引擎层 | — | 85% | import ✅ 链路 ⚠️ | V10.0 统一 Agent + RVR-B，但 Playbook 提取链路未接入 |
| FastAPI 服务端 | — | 90% | import ✅ 路由 ✅ | 9 路由 + 8 服务 + 72 端点 + WebSocket，全部加载正常 |
| 实例骨架与配置 | 1.1 | 90% | import ✅ 数据 ⚠️ | 三文件分级 + Provider 切换。⚠️ 实例目录有 4 个残留测试实例 |
| ⚠️ Skills 体系 | 3.1.1 | **60%** | 数据 ❌ | **目录 68 / 注册 76 / 配置 99 三处不一致。20个有目录无注册，28个注册无目录** |
| 自适应终止策略 | 3.4 | 85% | import ✅ 前端 ❌ | 后端八维度完整，前端 HITL 事件渲染全部未实现 |
| 状态一致性管理 | 3.3 | **80%** | import ✅ E2E ✅ | 已修复：实例启用 state_consistency、相对路径捕获、动态快照落盘；Rollback E2E 最新 2/2 PASS |
| 实例存储隔离 | — | 85% | import ✅ 数据 ⚠️ | 全组件感知 AGENT_INSTANCE，⚠️ 旧 `data/local_store/xiaodazi/` 未清理 |
| 意图识别 | 3.7.1 | 85% | import ✅ 链路 ✅ | V12.0 SkillGroupRegistry 动态生成描述，链路验证通过 |
| 上下文注入器 | — | 80% | import ✅ 数据 ⚠️ | 7 个 Injector 全部可导入，PlaybookHintInjector 无数据源（无 APPROVED Playbook） |
| 记忆系统 | 3.13 | 80% | import ✅ 命名 ⚠️ | 三层架构 import 通过。⚠️ 实际模块 `instance_memory` 非文档中的 `instance_memory` |
| 本地知识检索 | 3.8 | 85% | import ✅ | FTS5 + 向量混合搜索 + Embedding 抽象层 import 通过 |
| Plan 规划系统 | — | 85% | import ✅ | 渐进式展示 + 桌面工具表 + 文件安全提示 |
| 后台任务系统 | — | 80% | import ✅ 链路 ✅ | 两级调度 + 4 个任务，memory_flush 链路验证通过 |
| 前端实现 | — | 75% | 文件 ✅ 构建 ? | 31 Vue + 10 API + 9 Store + 5 Composables，**构建和运行未验证** |
| 进度转换器 | 3.7.2 | 75% | import ✅ | 已实现但**未集成到 PlanTodoTool 执行流程** |
| Nodes 本地操作 | 3.5 | 80% | macOS ✅ | macOS 11 项完整，win32/linux 不存在 |
| 打包与桌面端 | — | 80% | 文件 ✅ | PyInstaller + Tauri sidecar，Win/Linux 未验证 |
| 项目管理 | 3.10 | 70% | 文件 ⚠️ | 多实例架构，⚠️ 残留测试实例（b307fc3d/xiaodazi_backup/42c0dcfb/820e1326） |
| ⚠️ E2E 评估框架 | — | **40%** | E2E ❌ | **6 用例定义但 turns=0，报告 6/6 PASS 但无评分详情——可信度存疑** |
| ⚠️ Playbook | 2.14 | **50%** | 链路 ❌ | Hint 注入已实现，**但 DRAFT 生成/用户确认/APPROVED 三条链路全部断开** |
| 屏幕观察工具 | 3.5 | 80% | macOS ✅ | peekaboo + Vision OCR，仅 macOS |
| 前端 Settings | 3.1.2 | 80% | 文件 ✅ | 多 Provider 批量保存 |
| 首次启动引导 | 3.1.3 | 75% | 文件 ✅ | 9 步引导 |
| OS 兼容层 | 3.5 | 40% | 代码 ✅ | 仅 macOS |
| 应用发现 | 3.11 | 35% | 代码 ✅ | 仅 macOS 扫描 |
| 前端通用弹窗 | — | 90% | 文件 ✅ | SimpleConfirmModal 4 种类型 |
| 三大核心能力 | 3.9 | 80% | 链路 ⚠️ | 会干活(回滚已启用+修复)，会思考(完整)，会学习(Playbook断) |
| Skills 安全验证 | 3.12 | 0% | — | 未开始 |
| 服务状态仪表板 | 3.1.5 | 0% | — | 未开始 |
| MCP Apps UI | 3.6 | 0% | — | 未开始 |

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

**Skills-First 架构（V12.0 重构 — SkillGroupRegistry 单一数据源）**：

```
config/skills.yaml (唯一数据源)
    │
    ├── skill_groups — 富格式（description + skills 列表）
    │   ├── writing:        "写作、润色、改写..." → [writing-assistant, ...8 个]
    │   ├── data_analysis:  "Excel/CSV 数据分析..." → [excel-analyzer, ...3 个]
    │   ├── file_operation:  "本地文件管理..." → [file-manager, word-processor, nano-pdf]
    │   ├── translation:    "多语言翻译..." → [translator]
    │   ├── research:       "学术论文搜索..." → [literature-reviewer, ...8 个]
    │   ├── meeting:        "会议记录分析..." → [meeting-insights-analyzer, ...]
    │   ├── career:         "求职辅助..." → [job-application-optimizer]
    │   ├── learning:       "个人导师..." → [skill-tutor, quiz-maker]
    │   ├── creative:       "头脑风暴..." → [brainstorming, gifgrep]
    │   ├── diagram:        "流程图、架构图..." → [draw-io, excalidraw]
    │   ├── image_gen:      "AI 图像生成..." → [openai-image-gen, nano-banana-pro]
    │   ├── media:          "语音转文字..." → [openai-whisper, ...4 个]
    │   ├── health:         "营养分析..." → [nutrition-analyzer, medication-tracker]
    │   ├── productivity:   "笔记/待办/日历/邮件..." → [notion, ...14 个]
    │   ├── app_automation: "桌面应用操作..." → [applescript, ...14 个]
    │   ├── code:           "GitHub 仓库管理..." → [github]
    │   └── _always:        "始终注入" → [local-search, app-recommender, weather]
    │
    ├── SkillGroupRegistry (core/skill/group_registry.py)
    │   ├── build_groups_description()  → IntentAnalyzer（自动生成意图提示词）
    │   ├── get_skills_for_groups()     → SkillsLoader（按意图过滤 Skills）
    │   ├── validate()                  → 启动时检测孤儿 skill
    │   └── CRUD: add_group / add_skill / remove_skill / remove_group
    │
    ├── SkillsLoader → SkillEntry 列表
    │   ├── backend_type: local/tool/mcp/api（Agent 不感知）
    │   ├── dependency_level: builtin/lightweight/external/cloud_api
    │   └── os: common/darwin/win32/linux
    │
    └── loading_mode: "lazy", os_aware: true
```

**已创建 68 个 Skill 目录**（`instances/xiaodazi/skills/`，全部含 SKILL.md）：

> ⚠️ **数据一致性警告**：目录 68 个 / skill_registry.yaml 注册 76 个 / config/skills.yaml 配置 99 个。
> 20 个有目录但未在 registry 注册（如 deep-research、pdf-toolkit、smart-email-assistant）。
> 28 个已注册但无目录（如 notion、github、weather 等，多为 MCP 远程 Skill）。

| 分类 | Skills |
|------|--------|
| 写作 | writing-assistant, writing-analyzer, style-learner, content-reformatter, translator, humanizer |
| 数据 | excel-analyzer, excel-fixer, word-processor |
| 研究 | literature-reviewer, paper-search, arxiv-search, readwise-rival |
| 可视化 | draw-io, excalidraw, elegant-reports |
| 会议 | meeting-insights-analyzer, meeting-notes-to-action-items |
| 效率 | brainstorming, quiz-maker, skill-tutor, invoice-organizer, job-application-optimizer |
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
- 过期快照自动清理（24 小时，`_cleanup_expired_snapshots`）
- 磁盘持久化（JSON 序列化/反序列化，`~/.xiaodazi/snapshots/`）
- 动态文件捕获（`ensure_file_captured()` 懒加载，工具执行前自动备份）
- 工具执行流集成（`_pre_capture_files` + `_post_record_operation`，`core/agent/tools/flow.py`）
- **实例配置启用**（`instances/xiaodazi/config.yaml` 的 `state_consistency.enabled: true`）

**E2E 验证（B9/B10 — 6 个子场景全部 PASS）**：
- B9.1 多文件修改异常 → 自动回滚（字节级恢复）
- B9.2 快照磁盘持久化 → 进程崩溃后恢复
- B9.3 动态文件捕获 → 未预先声明的文件也能回滚
- B10.1 用户中止 → 全部回滚
- B10.2 选择性回滚（仅回滚部分文件）
- B10.3 保留已完成（不回滚，commit 清理快照）
- 独立验证脚本：`scripts/verify_rollback_e2e.py`

**遗留**：
- 一致性检查中的 `app_availability`（依赖应用是否可用）检查未实现
- `clipboard` 状态备份/恢复未实现（设计中提到）
- 回滚选项的前端 UI 交互未实现

**「根本没有快照恢复」根因与修复（2026-02-09）**：

| 根因 | 说明 | 修复 |
|------|------|------|
| **实例未启用** | `instances/xiaodazi/config.yaml` 此前**无** `state_consistency` 段，加载后 `enabled=False`，快照/回滚流程从不执行 | 已在 config.yaml 中增加 `state_consistency.enabled: true` 及 snapshot/rollback 配置 |
| **路径提取过严** | `_extract_file_paths` 只认绝对路径和 `~`，相对路径（如 `docs/README.md`）不捕获 → 工具写相对路径时无备份 | `core/agent/tools/flow.py` 已支持相对路径（基于 cwd 解析，仅接受存在且像路径的字符串） |
| **动态捕获未落盘** | `ensure_file_captured` 只更新内存，不调用 `_persist_snapshot`，进程崩溃后动态捕获的文件无法从磁盘恢复 | `consistency_manager.py` 在动态捕获后调用 `_persist_snapshot(snap)` |

- **Rollback E2E 报告**：历史 3 份（20260208）为 0/2 PASS；**最新** `rollback_e2e_20260209_160621.json` 为 **2/2 PASS**（B9/B10 共 6 个子场景通过）。用户侧「没有快照恢复」主要因实例未启用，与 E2E 脚本结果无关。

---

### 2.5 Agent 引擎层（V10.0 统一 Agent + V11.0 固定 RVR-B）

**设计**：V10.0 统一为单一 `Agent` 类（Strategy 模式），V11.0 固定 RVR-B 执行器。

> ⚠️ **链路断裂**：`base.py` 中引用了 playbook 概念但**未实际调用** `PlaybookManager.extract_from_session()`。

| 组件 | 文件 | 特性 |
|------|------|------|
| `Agent` | `core/agent/base.py` | V10.0 统一智能体类（Strategy 模式，Executor 注入） |
| `AgentFactory` | `core/agent/factory.py` | Prompt 驱动的动态初始化 |
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
| **HITL pending 暂停** | `rvrb.py` stream + non-stream | 检测工具返回 `pending_user_input` 后设置 `ctx.stop_reason = "hitl_pending"` 暂停执行，修复 HITL 连续调用 2 次 bug |

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
| `core/memory/instance_memory.py` | 已完成 | 三层入口：recall 融合搜索 / remember 双写 / flush 提取+日志 |
| `core/memory/mem0/pool.py` | 已完成 | Layer 3：Mem0 语义搜索 + 向量存储 |
| `core/memory/mem0/update/quality_control.py` | 已完成 | 冲突检测 + 更新决策（LLM 驱动） |
| `core/memory/mem0/extraction/extractor.py` | 已完成 | 碎片记忆提取（FragmentExtractor） |

**已完成的设计要求**：
- Layer 1 文件层：MEMORY.md 自动创建模板 + 段落定位追加 + 每日日志
- Layer 2 索引层：独立 `memory_fts.db`（不共享 zenflux.db），带 3 次重试
- Layer 3 智能层：Mem0MemoryPool 语义搜索 + QualityController 冲突检测 + FragmentExtractor 10 维碎片提取
- recall 融合搜索：FTS5（BM25）+ Mem0（向量），结果合并去重
- remember 双写：MEMORY.md + FTS5 索引 + Mem0 向量存储
- flush 会话级批量提取：整个对话打包一次 LLM 调用 → 10 维碎片 → remember 双写 → 每日日志
- 分类体系：preference / fact / workflow / style / tool → MEMORY.md 段落映射
- 实例级存储隔离：所有数据路径按 `AGENT_INSTANCE` 自动隔离
- 降级策略：Mem0 不可用时降级到文件层全文扫描；FTS5 失败时 3 次重试后降级

**E2E 验证修复的 Bug（2026-02-08）**：
- SqliteVecVectorStore：`check_same_thread=False` 解决线程安全 + `k=?` 替代 `LIMIT`（sqlite-vec 0.1.6+）
- SqliteVecVectorStore.list()：返回 `[results, count]` 适配 Mem0 `delete_all` 协议
- UserMemoryInjector：导入路径从 `core.memory.system.profile` 修正到 `core.agent.context.prompt_builder`
- QualityController.should_reject()：加空内容/短文本格式校验 + detect_conflicts 移除错误 await
- FragmentExtractor：LLM Profile 加载需要 `set_instance_profiles()` 预初始化
- MemorySource 枚举：新增 `XIAODAZI_REMEMBER` 值
- _extract_from_conversation()：完整重写，正确对接 FragmentMemory 10 维 hint 字段

**记忆提取策略（会话级批量 + memory_flush 后台任务）**：

```
每条消息 → 零成本，不调 LLM
  ↓ 累积到会话消息池
  ↓
每次聊天响应后 → memory_flush 后台任务 (fire-and-forget)
  ↓
快速预判（硬规则，<1ms）：
  - 对话总长 < 30 字 → 跳过（信息量不足，中文 3x 信息密度）
  - 仅 1 轮且用户消息 < 15 字 → 跳过（简单问答）
  ↓ 通过预判
FragmentExtractor 一次 LLM 调用（~3000 tokens）：
  - 接收完整多轮对话（user+assistant 交替）
  - 在完整上下文中提取 10 维碎片
  - 比单条消息提取质量更高、成本更低
  ↓
remember() 双写 → MEMORY.md + FTS5 + Mem0
```

**memory_flush 后台任务**（`utils/background_tasks/tasks/memory_flush.py`）：
- 触发时机：每次聊天响应后（fire-and-forget，永不阻塞用户）
- 快速预过滤：格式/长度检查（_MIN_TOTAL_CHARS=30, _MIN_SINGLE_TURN_CHARS=15）
- 自动实例化 `InstanceMemoryManager`，调用 `flush(session_id, messages)`
- 失败不抛异常（non-fatal warning）

**后台任务两级调度**（`utils/background_tasks/service.py`）：
- SSE 依赖型（await）：`title_generation`、`recommended_questions` — 必须在流关闭前完成
- 学习型（fire-and-forget）：`memory_flush`、`mem0_update` — 不阻塞用户响应

**遗留**：
- 记忆同步机制（文件监听 MEMORY.md 变更 → 自动重建索引）未实现
- 混合检索加权配置（`vector_weight` / `bm25_weight`）已在 config 中声明但未在 recall 中实际应用权重计算
- 用户可编辑 MEMORY.md 后的冲突合并（用户修改 vs 自动提取）未实现
- Playbook 自动提取（RewardAttribution → PlaybookManager.extract）未接入聊天流程

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

### 2.9 意图识别（3.7.1）— V12.0（SkillGroupRegistry 驱动）

| 文件 | 状态 | 说明 |
|------|------|------|
| `core/routing/intent_analyzer.py` | **已更新** | V12.0 从 SkillGroupRegistry 动态获取分组描述 |
| `core/routing/intent_cache.py` | 已完成 | 语义缓存（`IntentSemanticCache`） |
| `core/routing/router.py` | 已完成 | `AgentRouter`：路由决策 |
| `core/routing/types.py` | 已完成 | `IntentResult` / `Complexity` 类型定义 |
| `prompts/intent_recognition_prompt.py` | **V12.0** | 动态 `{skill_groups_description}` 占位符 + 17 个 Few-Shot 示例 |
| `core/skill/group_registry.py` | **新增** | `SkillGroupRegistry`：分组单一数据源 + CRUD + 自动生成描述 |
| `core/prompt/intent_prompt_generator.py` | **已更新** | 对接 SkillGroupRegistry.build_groups_description() |

**V12.0 输出字段（5 个核心字段）**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `complexity` | SIMPLE/MEDIUM/COMPLEX | 任务复杂度 → 影响规划深度和 Skill 聚焦 |
| `skip_memory` | bool | 是否跳过记忆召回 |
| `is_follow_up` | bool | 是否追问（复用 plan_cache） |
| `wants_to_stop` | bool | 用户停止意图 |
| `relevant_skill_groups` | List[str] | LLM 语义多选（17 个分组，从 SkillGroupRegistry 动态生成） |

**V12.0 关键改进**：

```
旧链路（V11.0）：
  skill_groups 定义在 skills.yaml（扁平列表格式）
    ↓ 手动维护分组描述
  IntentAnalyzer 硬编码分组列表到提示词

新链路（V12.0 — 单一数据源）：
  config/skills.yaml (skill_groups 富格式: description + skills)
    ↓ 加载
  SkillGroupRegistry
    ↓ build_groups_description()
  intent_recognition_prompt.py（{skill_groups_description} 动态注入）
    ↓
  IntentAnalyzer.analyze() → relevant_skill_groups
    ↓ get_skills_for_groups()
  SkillsLoader（仅注入相关 Skills 到系统提示词）
```

**SkillGroupRegistry 能力**：

| 方法 | 说明 |
|------|------|
| `build_groups_description()` | 自动生成 `- **writing**: 写作、润色...` 格式的 Markdown 描述 |
| `get_skills_for_groups(["writing", "meeting"])` | 返回选中分组 + _always 的所有 skill 名称 |
| `get_groups_for_skill("excel-analyzer")` | 反向查询：skill 属于哪些分组 |
| `validate(all_skill_names)` | 检测不在任何分组的孤儿 skill |
| `add_group / add_skill / remove_skill` | CRUD 操作 |
| `to_config_dict()` | 导出为 config/skills.yaml 格式 |

**17 个技能分组（V12.0）**：

| 分组 | 描述 | Skills 数 |
|------|------|----------|
| writing | 写作、润色、改写、PDF 报告 | 8 |
| data_analysis | Excel/CSV 数据分析、发票整理 | 3 |
| file_operation | 文件管理、Word、PDF | 3 |
| translation | 多语言翻译 | 1 |
| research | 论文搜索、文献综述、竞品、RSS | 8 |
| meeting | 会议记录分析、行动项 | 2 |
| career | 求职辅助、简历优化 | 1 |
| learning | 个人导师、测验出题 | 2 |
| creative | 头脑风暴、GIF 搜索 | 2 |
| diagram | 流程图、架构图 | 2 |
| image_gen | AI 图像生成 | 2 |
| media | 语音转文字、TTS、音乐 | 4 |
| health | 营养分析、用药管理 | 2 |
| productivity | 笔记/待办/日历/邮件 | 14 |
| app_automation | 桌面操作、UI 自动化 | 14 |
| code | GitHub 管理 | 1 |
| _always | 始终注入 | 3 |

**已完成**：
- `fast_mode: true` 使用更快模型（如 haiku）
- `semantic_cache_threshold` 可配置（提高到 0.90 减少 LLM 调用）
- `simplified_output: true` 跳过不必要字段
- 消息过滤 `_filter_for_intent()`：仅最近 5 条 user + 最后 1 条 assistant（截断 100 字符），O(n) < 0.1ms
- `relevant_skill_groups` 语义多选：LLM 从 17 个分组中选择相关技能组
- 提示词来源优先从 `InstancePromptCache` 获取（用户自定义），Fallback 到默认
- 保守 Fallback：LLM 失败时返回 MEDIUM 复杂度
- **V12.0 新增**：`SkillGroupRegistry` 单一数据源，消除分组描述手动同步
- **V12.0 新增**：17 个 Few-Shot 示例覆盖所有分组场景
- **V12.0 新增**：孤儿 skill 检测（`validate_and_warn()`）

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
1. 前端提供"创建新搭子"界面 → 用户选模板、填名称、选 Skills → 后端创建实例
2. 前端提供"编辑搭子"界面 → 加载已有配置 → 修改后保存
3. 后端从 `_template/` 脚手架创建新实例目录 → 写入配置文件
4. `main` 加载指定实例 → Agent 启动
5. 切换搭子 = 切换实例

**优势**：
- 零代码隔离：配置/记忆/Skills/提示词天然独立
- 简单可靠：不需要复杂的上下文切换、知识库隔离逻辑
- 可组合：每个实例可以有完全不同的 provider/模型/温度配置

**已有实例**：

```
instances/
├── _template/          ← 脚手架模板（创建新实例时复制）
├── xiaodazi/           ← 通用搭子（默认，全技能）
└── daa22480/           ← 用户创建的自定义实例
```

| 文件 | 状态 | 说明 |
|------|------|------|
| `instances/_template/` | 已有 | 实例脚手架模板 |
| `instances/daa22480/` | **新增** | 用户创建的自定义实例（含 config/prompt/skills/prompt_results） |
| `utils/instance_loader.py` | 已完成 | 加载任意实例的配置/提示词/Skills |
| `core/project/` | 已删除 | 整个目录已移除，多实例架构取代 |
| 前端创建界面 | **已完成** | CreateProjectView（创建模式） |
| 前端编辑界面 | **已完成** | CreateProjectView（编辑模式，路由 `/edit-project/:agentId`） |

**已删除实例**：
- `instances/b307fc3d/` — 测试实例，已清理

---

### 2.12 存储层（实例隔离改造完成）

| 文件 | 状态 | 说明 |
|------|------|------|
| `infra/local_store/engine.py` | **已改造** | aiosqlite + WAL + 7 项 PRAGMA；DB 路径从 `AGENT_INSTANCE` 自动解析 |
| `infra/local_store/fts.py` | 已完成 | 消息专用 FTS5 |
| `infra/local_store/generic_fts.py` | 已完成 | 通用 FTS5（知识/记忆共用） |
| `infra/local_store/vector.py` | 已完成 | sqlite-vec 向量搜索 |
| `infra/local_store/models.py` | 已完成 | ORM 模型 + LocalIndexedFile |
| `infra/local_store/workspace.py` | 已完成 | 统一管理器 |
| `infra/local_store/skills_cache.py` | 已完成 | Skills 延迟加载缓存 |
| `infra/storage/local.py` | **已改造** | 文件上传存储，从 `AGENT_INSTANCE` 自动解析实例存储路径 |

**实例隔离改造**：

所有存储组件已从全局路径迁移到实例隔离路径：

| 组件 | 旧路径（已废弃） | 新路径 |
|------|-----------------|--------|
| 主数据库 | `data/local_store/zenflux.db` | `data/instances/{name}/db/instance.db` |
| 记忆文件 | `~/.xiaodazi/MEMORY.md` | `data/instances/{name}/memory/MEMORY.md` |
| Mem0 向量 | 全局路径 | `data/instances/{name}/store/mem0_vectors.db` |
| FTS 索引 | 全局路径 | `data/instances/{name}/store/memory_fts.db` |
| 文件上传 | `data/storage/` | `data/instances/{name}/storage/` |
| Playbook | `~/.xiaodazi/playbooks/` | `data/instances/{name}/playbooks/` |
| 快照 | `~/.xiaodazi/snapshots/` | `data/instances/{name}/snapshots/` |

**路径解析流程**（`engine.py`）：
```python
# 1. 优先环境变量覆盖
env_override = os.getenv("LOCAL_STORE_DIR")
# 2. 从 AGENT_INSTANCE 自动解析
instance = os.environ["AGENT_INSTANCE"]
db_dir = get_instance_db_dir(instance)
# 3. 数据库文件名默认 instance.db
db_name = os.getenv("LOCAL_STORE_DB", "instance.db")
```

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

#### Canvas 与 Remotion 结论

- **Canvas**：不需要 Moltbot 方案。用已有的「**本地 HTML + open_url / preview_url**」即可实现内容展示（Agent 生成 HTML → 写入临时目录或通过预览 API 返回 URL → `open_url` 或前端 `window.open(preview_url)`）。
- **Remotion**：未接入。仅在 `docs/xiaodazi_skills_recommendation.md` 中作为 P1 推荐；后续可按需新增 Skill（参考 [remotion-dev/skills](https://github.com/remotion-dev/remotion/tree/main/packages/skills) 与 `npx remotion render`）。

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
| **会学习** — 记忆系统 | `InstanceMemoryManager` 三层 | 已完成 |
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

### 2.20 E2E 评估框架（V2 — 三层验证）

> ⚠️ **第四次更新严重警告**：E2E 评估框架存在根本性问题——6 个测试用例 `turns=0`（对话流程为空），最新报告 6/6 PASS 但 `grade_results` 为空。Rollback E2E 3 份报告全部 0/2 PASS。**当前 E2E 框架无法作为质量保证手段。**

**价值定位**：端到端质量验证 — 从状态管理层到 Agent 交互到 LLM-as-Judge 诊断，三层自动化。

| 文件 | 状态 | 说明 |
|------|------|------|
| `evaluation/adapters/http_agent.py` | 已完成 | E2E → FastAPI 桥接适配器 |
| `evaluation/graders/code_based.py` | 已完成 | 代码评分器（CodeBasedGraders 类） |
| `evaluation/graders/model_based.py` | 已完成 | 模型评分器（ModelBasedGraders 类） |
| `evaluation/harness.py` | 已完成 | 评估运行引擎（import 通过） |
| `evaluation/suites/xiaodazi/e2e/phase1_core.yaml` | ⚠️ 有缺陷 | **6 个用例定义但 turns=0（对话流程为空）** |
| `evaluation/config/judge_prompts.yaml` | 已完成 | 含 `grade_rollback_safety` 回滚安全专项评估 |
| `scripts/run_e2e_auto.py` | 已完成 | 自动化运行器 |
| `scripts/verify_rollback_e2e.py` | ⚠️ 待验证 | 声称 6/6 通过但报告显示 0/2 |

**Phase 1 测试用例（6 个）**：

| ID | 场景 | Graders | Turns | ⚠️ 问题 |
|-----|------|---------|-------|--------|
| A1 | 格式混乱 Excel 分析 | check_no_tool_errors + model | 0 | ❌ 对话为空 |
| B1 | 跨会话记忆 | model | 0 | ❌ 对话为空 |
| D4 | 连续错误恢复 | check_no_tool_errors + model | 0 | ❌ 对话为空 |
| C1 | 简单问答 token 对比 | check_token_limit + model | 0 | ❌ 对话为空 |
| B9 | 文件修改异常退出回滚 | check_no_tool_errors + 2× model | 0 | ❌ 对话为空 |
| B10 | 文件修改用户中止回滚 | 2× model | 0 | ❌ 对话为空 |

**评估报告现状（13 份报告分析）**：

| 报告类型 | 数量 | 结果 | 可信度 |
|---------|------|------|--------|
| e2e_phase1 | 10 份 | 均为 6/6 PASS | ❌ 不可信（grade_results 为空） |
| rollback_e2e | 4 份 | 3 份 0/2、**1 份 2/2**（`rollback_e2e_20260209_160621.json`） | 最新 2/2 PASS；用户侧无快照因实例未启用，已修复 |

**三层评估架构**：

```
scripts/run_e2e_auto.py
    │
    ├── Phase 0: run_rollback_verification()
    │   ├── verify_rollback_e2e.py（6 个子场景，确定性验证）
    │   └── 任何 FAIL → 阻断后续 Agent 测试
    │
    ├── Phase 1: 启动 uvicorn（端口 18234，避免冲突）
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

### 2.21 Plan 规划系统优化（桌面端适配）

**价值定位**：让 Plan 机制从"通用云端风格"转变为"桌面端 AI 搭子风格"，核心差异：文件安全自动提示、渐进式展示、桌面本地工具表。

**设计参考**：
- **Claude Code Checkpointing**：每步有检查点，Agent 知道框架自动备份
- **Interactive Speculative Planning (ICLR 2025)**：渐进式披露，降低认知负荷
- **Cocoa Co-Planning**：失败时支持调整计划而非只重试

| 文件 | 状态 | 变更 |
|------|------|------|
| `prompts/plan_generator_prompt.py` | 已更新 | `DEFAULT_TOOLS_REFERENCE` 从云端 API 改为桌面本地能力表；示例从"贪吃蛇"改为"端口批量修改"；新增"安全机制"栏 |
| `tools/plan_todo_tool.py` | 已更新 | `format_plan_for_prompt` 重写为渐进式展示：已完成步骤折叠、当前步骤突出、未来只显示 2 步；文件操作自动注入安全提示 |
| `instances/xiaodazi/prompt.md` | 已更新 | 新增"文件修改安全"协议：事务语义、自动备份、反馈模板 |
| `instances/xiaodazi/prompt_results/complex_prompt.md` | 已更新 | 规划要素新增"文件安全"；执行原则新增"渐进式反馈"和"文件修改放心做" |

**Plan 注入格式（优化后 — 渐进式展示）**：

```
## 当前任务计划

**目标**: 端口统一修改：3000 → 8080
**概要**: 将 3 个配置文件中的端口号从 3000 统一改为 8080
**进度**: 2/5 完成

  ✅ 步骤 1-2 已完成
  ▶ 3. 修改 nginx.conf 的端口为 8080
  ⏳ 4. 修改 README.md 的端口说明
  ... 还有 1 步

请继续执行当前步骤。完成后使用 plan 工具更新状态。
📦 文件安全网已激活：修改前自动备份，出错自动恢复，不需要手动备份。
```

**关键改进对比**：

| 维度 | 优化前 | 优化后 |
|------|--------|--------|
| 工具表 | `api_calling`、`PPT Skill`（云端风格） | `nodes`、`observe_screen`、`knowledge_search`（桌面本地） |
| Plan 注入 | 全量展示所有步骤 | 渐进式：已完成折叠、当前突出、未来限 2 步 |
| 安全提示 | 无 | 检测到文件操作时自动注入"安全网已激活" |
| 示例 | "贪吃蛇游戏开发" | "端口批量修改"（贴合桌面端文件操作场景） |
| 备份策略 | Agent 手动创建 .backup | 提示词告知"框架自动备份，不需要手动" |

---

### 2.22 实例存储隔离与路径管理

**价值定位**：所有运行时数据按实例名称完全隔离，切换搭子 = 切换存储空间，零数据泄漏。

| 文件 | 状态 | 说明 |
|------|------|------|
| `utils/app_paths.py` | **新增** | 统一路径管理器：bundle_dir（只读）+ user_data_dir（可写）+ 实例隔离 |
| `utils/instance_loader.py` | **已改造** | `create_agent_from_instance()` 启动时设置 `AGENT_INSTANCE` 环境变量 |
| `infra/local_store/engine.py` | **已改造** | DB 路径从 `AGENT_INSTANCE` 自动解析到实例目录 |
| `infra/storage/local.py` | **已改造** | 文件上传路径从 `AGENT_INSTANCE` 解析 |
| `core/playbook/storage.py` | **已改造** | FileStorage 路径从 `AGENT_INSTANCE` 解析 |
| `core/memory/instance_memory.py` | **已改造** | 记忆路径从 `AGENT_INSTANCE` 解析 |
| `core/state/consistency_manager.py` | **已改造** | 快照路径从 `AGENT_INSTANCE` 解析 |
| `core/memory/mem0/config.py` | **已改造** | Mem0 向量库路径实例隔离 |
| `core/memory/mem0/sqlite_vec_store.py` | **已改造** | 向量存储路径实例隔离 |
| `scripts/migrate_instance_storage.py` | **新增** | 一次性迁移脚本：从旧全局路径迁移到实例隔离路径 |

**隔离机制**：

```
instance_loader.create_agent_from_instance("xiaodazi")
    │
    ├── os.environ["AGENT_INSTANCE"] = "xiaodazi"  ← 设置环境变量
    │
    ├── engine.py → get_instance_db_dir("xiaodazi")
    │   → data/instances/xiaodazi/db/instance.db
    │
    ├── instance_memory.py → get_instance_memory_dir("xiaodazi")
    │   → data/instances/xiaodazi/memory/MEMORY.md
    │
    ├── local.py → get_instance_storage_dir("xiaodazi")
    │   → data/instances/xiaodazi/storage/
    │
    ├── storage.py → get_instance_playbooks_dir("xiaodazi")
    │   → data/instances/xiaodazi/playbooks/
    │
    └── consistency_manager.py → get_instance_snapshots_dir("xiaodazi")
        → data/instances/xiaodazi/snapshots/
```

**路径函数清单**（`utils/app_paths.py`）：

| 函数 | 返回路径 | 说明 |
|------|---------|------|
| `get_bundle_dir()` | 项目根 / sys._MEIPASS | 只读资源（config/prompts/instances/） |
| `get_user_data_dir()` | 项目根 / 平台用户目录 | 可写数据（DB/日志/用户配置） |
| `get_instance_data_dir(name)` | `{user_data}/data/instances/{name}/` | 实例数据根 |
| `get_instance_db_dir(name)` | `.../db/` | 数据库 |
| `get_instance_memory_dir(name)` | `.../memory/` | 记忆文件 |
| `get_instance_store_dir(name)` | `.../store/` | 向量/索引 |
| `get_instance_storage_dir(name)` | `.../storage/` | 文件上传 |
| `get_instance_playbooks_dir(name)` | `.../playbooks/` | 策略库 |
| `get_instance_snapshots_dir(name)` | `.../snapshots/` | 状态快照 |
| `get_shared_models_dir()` | `{user_data}/data/shared/models/` | 共享模型 |

**已完成的设计要求**：
- 全组件 `AGENT_INSTANCE` 感知（DB/Memory/Mem0/Storage/Playbook/Snapshot）
- 旧全局路径（`~/.xiaodazi/`）完全清除，无向后兼容代码
- `instance_loader` 在加载实例时自动设置环境变量
- `main.py` 单实例时自动检测，无需手动设置
- 一次性迁移脚本（`scripts/migrate_instance_storage.py`）

---

### 2.23 后台任务系统

**价值定位**：统一调度 SSE 依赖型任务和学习型任务，确保用户体验（标题/推荐问题立即返回）同时不阻塞记忆提取等学习任务。

| 文件 | 状态 | 说明 |
|------|------|------|
| `utils/background_tasks/service.py` | **已改造** | 两级调度：SSE-dependent（await）+ fire-and-forget |
| `utils/background_tasks/registry.py` | 已完成 | `@background_task` 装饰器自动注册 |
| `utils/background_tasks/context.py` | 已完成 | `TaskContext` 统一上下文 |
| `utils/background_tasks/tasks/title_generation.py` | 已完成 | 标题生成（SSE 依赖型） |
| `utils/background_tasks/tasks/recommended_questions.py` | 已完成 | 推荐问题生成（SSE 依赖型） |
| `utils/background_tasks/tasks/mem0_update.py` | 已完成 | Mem0 向量更新（学习型） |
| `utils/background_tasks/tasks/memory_flush.py` | **新增** | 会话记忆提取（学习型） |

**两级调度策略**：

```
dispatch_tasks(task_names, context)
    │
    ├── SSE-dependent tasks (await):
    │   ├── title_generation      → 生成对话标题 → 推送 SSE 事件
    │   └── recommended_questions → 生成推荐问题 → 推送 SSE 事件
    │   └── ⏳ 等待完成后才关闭 SSE 流
    │
    └── Learning tasks (fire-and-forget):
        ├── memory_flush   → 提取记忆碎片 → 双写 MEMORY.md + Mem0
        └── mem0_update    → 更新 Mem0 向量存储
        └── 🔥 启动即返回，不阻塞用户
```

**设计原则**：
- 任务自动注册：`@background_task("name")` 装饰器
- 共享资源管理：LLM 和 Mem0 Pool 懒加载，供所有 task 复用
- 失败隔离：学习型任务失败仅 warning，不影响用户体验
- SSE 依赖型任务超时也不阻断（`asyncio.wait` 带超时）

---

### 2.24 打包与桌面端路径管理

**价值定位**：支持 PyInstaller 打包 + Tauri sidecar 部署，开发/打包环境自动切换路径。

| 文件 | 状态 | 说明 |
|------|------|------|
| `utils/app_paths.py` | **新增** | 双模式路径解析（开发 vs 打包） |
| `zenflux-backend.spec` | 已完成 | PyInstaller 打包配置 |
| `scripts/build_backend.py` | 已完成 | 后端打包脚本 |
| `scripts/build_app.sh` | 已完成 | 全栈构建脚本 |
| `scripts/sync_version.py` | 已完成 | 版本同步（Python ↔ Tauri） |
| `main.py` | **已改造** | 端口从 `get_cli_port()` 获取，支持 `--port` 参数 |

**双模式路径架构**：

```
┌─────────────────────────────────────────────────────────┐
│                    开发模式                               │
│  bundle_dir  = 项目根目录 (只读资源: config/, prompts/)   │
│  user_data   = 项目根目录 (可写数据: data/, logs/)        │
│                                                          │
│  → 零配置，直接 `python main.py` 启动                     │
├─────────────────────────────────────────────────────────┤
│                    打包模式 (PyInstaller)                  │
│  bundle_dir  = sys._MEIPASS (临时解压目录, 只读)           │
│  user_data   = 平台用户数据目录 (可写)                     │
│                                                          │
│  macOS:   ~/Library/Application Support/com.zenflux.agent│
│  Windows: %APPDATA%/zenflux_agent/                       │
│  Linux:   ~/.local/share/zenflux_agent/                  │
│                                                          │
│  → Tauri sidecar 可通过 --data-dir 覆盖                   │
└─────────────────────────────────────────────────────────┘
```

**CLI 参数支持（Tauri sidecar 传入）**：

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--data-dir` | 用户数据目录覆盖 | 平台标准目录 |
| `--port` | 服务监听端口 | 18900 |

**环境变量优先级**：

```
1. 命令行参数 --data-dir （最高优先级，Tauri sidecar 传入）
2. 环境变量 ZENFLUX_DATA_DIR
3. 开发模式：项目根目录
4. 打包模式：平台标准用户数据目录
```

**已完成**：
- PyInstaller 打包配置（`zenflux-backend.spec`）
- 版本同步（`VERSION` 文件 → `main.py` + `Cargo.toml`）
- 跨平台用户数据目录（macOS / Windows / Linux）
- Tauri sidecar 集成（`--data-dir` + `--port`）
- 路径缓存（避免重复计算）

**遗留**：
- Windows 打包测试未验证
- Linux 打包测试未验证
- 自动更新机制（Tauri updater）未实现

---

## 四、前端与服务端实现详情

### 4.0 实现规模概览（测试驱动验证）

#### FastAPI 服务端

| 维度 | 数量 | 验证状态 |
|------|------|----------|
| 路由模块 | 9 个 | ✅ 全部 import 通过 |
| 服务层 | 8 个 | ✅ 全部 import 通过 |
| API 端点 | 72 个 | ✅ `from main import app` 加载正常 |
| WebSocket | 1 个 (`/api/v1/ws/chat`) | ✅ |
| 工具文件 | 10 个（含 1 个残留副本） | ⚠️ `request_human_confirmation _copy.py` 需删除 |
| capabilities 注册 | 9 个核心工具 | ✅ |

**路由模块清单**：`chat.py` / `websocket.py` / `conversation.py` / `agents.py` / `skills.py` / `files.py` / `models.py` / `settings.py` / `human_confirmation.py`

**服务层清单**：`chat_service.py` / `agent_registry.py` / `session_service.py` / `conversation_service.py` / `knowledge_service.py` / `confirmation_service.py` / `settings_service.py` / `user_task_scheduler.py`

#### Vue 前端

| 维度 | 数量 | 验证状态 |
|------|------|----------|
| Vue 组件 | 31 个 | ✅ 文件存在 |
| TypeScript 文件 | 39 个 | ✅ |
| API 层 | 10 个模块 | ✅ |
| Pinia Store | 9 个 | ✅ |
| Composables | 5 个 | ✅ |
| 视图页面 | 6 个 | ✅ |
| **前端构建** | **未验证** | ⚠️ 未运行 `npm run build` |

**组件分布**：

| 目录 | 数量 | 主要组件 |
|------|------|---------|
| `components/chat/` | 8 | ChatHeader, ChatInputArea, ConversationSidebar, MessageList, MessageContent, MarkdownRenderer, ToolBlock, ToolMessage |
| `components/modals/` | 6 | HITLConfirmModal, LongRunConfirmModal, RollbackOptionsModal, ConfirmModal, SimpleConfirmModal, AttachmentPreview |
| `components/common/` | 4 | Card, DebugPanel, GuideOverlay, SplashScreen |
| `components/workspace/` | 3 | FileExplorer, FilePreview, FileTreeNode |
| `components/sidebar/` | 1 | PlanWidget |
| `views/` | 6 | ChatView, SettingsView, SkillsView, KnowledgeView, OnboardingView, CreateProjectView |
| `layouts/` | 2 | DashboardLayout, DefaultLayout |

**Store 清单**：`conversation` / `session` / `agent` / `skill` / `workspace` / `connection` / `knowledge` / `ui` / `guide`

**API 层清单**：`chat.ts` / `session.ts` / `agent.ts` / `skills.ts` / `models.ts` / `settings.ts` / `workspace.ts` / `config.ts` / `tauri.ts` / `index.ts`

---

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

### 4.2 设置页（多 Provider 批量保存 + 激活）

**设计需求**：基于 Models API 的结构化 Provider 配置，支持多个 Provider 同时保存和激活。

| 文件 | 状态 | 说明 |
|------|------|------|
| `frontend/src/views/settings/SettingsView.vue` | **已更新** | 多 Provider 批量保存 + 激活 + 验证 |
| `frontend/src/api/models.ts` | **已更新** | 新增 `ProviderActivateResult` + `activateProvider()` 批量激活 API |
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
├── 验证并保存按钮（多 Provider 批量处理）
│   ├── Step 1: 收集所有填写了 Key 的 Provider
│   ├── Step 2: 批量验证所有新填写的 Key（已配置且未修改的跳过）
│   ├── Step 3: 验证失败的汇总展示
│   ├── Step 4: 批量保存 API Keys + Base URLs
│   ├── Step 5: 批量激活所有新 Provider 的模型（activateProvider API）
│   └── Step 6: 自动设置默认模型 = 第一个验证通过 Provider 的首个模型
│
└── 返回聊天按钮
```

**关键设计（V2 重构）**：
- **多 Provider 批量保存**：不再要求选中单个 Provider，收集所有填写了 Key 的 Provider 一次性保存
- **批量验证**：对所有新填写的 Key 逐个验证，汇总展示失败结果
- **批量激活**：保存后调用 `modelApi.activateProvider()` 批量激活新 Provider 的模型
- **脱敏值智能跳过**：已配置且未修改的 Key（脱敏值 `sk-***...***`）自动跳过验证和激活
- 移除了自动展开已配置 Provider 的逻辑
- 引导验证简化：仅检查"是否有任何 Provider 填写了 Key"
- 保存失败时显示错误提示 + 引导步骤自动回退

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

### 4.5 项目编辑功能（CreateProjectView 双模式）

**设计需求**：复用 CreateProjectView 组件，通过路由参数区分创建/编辑模式，实现项目配置的编辑保存。

| 文件 | 状态 | 说明 |
|------|------|------|
| `frontend/src/views/project/CreateProjectView.vue` | **已更新** | 创建+编辑双模式，自定义模型下拉框 |
| `frontend/src/router/index.ts` | **已更新** | 新增 `/edit-project/:agentId` 路由 |
| `frontend/src/components/chat/ConversationSidebar.vue` | **已更新** | 项目列表新增编辑按钮（Pencil 图标） |
| `frontend/src/views/chat/ChatView.vue` | **已更新** | 新增 `handleEditAgent()` 编辑跳转 |

**双模式路由**：

```
/create-project       → CreateProjectView（创建模式）
/edit-project/:agentId → CreateProjectView（编辑模式）
```

**编辑模式流程**：

```
侧边栏项目列表 → 点击编辑按钮（Pencil 图标）
    │
    ▼
ChatView.handleEditAgent(agentId)
    │ router.push({ name: 'edit-project', params: { agentId } })
    ▼
CreateProjectView（编辑模式）
    │
    ├── loadAgentData()  → 调用 getAgentDetail(agentId) 加载基本信息
    │   └── 调用 GET /v1/agents/{agentId}/prompt 加载 instructions
    │
    ├── 表单预填充：name / description / model / instructions
    │
    └── handleSave() → agentStore.updateAgent(agentId, updates)
        └── 成功后跳转到 Agent 对话页
```

**创建 vs 编辑模式差异**：

| 维度 | 创建模式 | 编辑模式 |
|------|---------|---------|
| 路由 | `/create-project` | `/edit-project/:agentId` |
| 页面标题 | "新建项目" | "编辑项目" |
| 按钮文本 | "创建" / "创建中..." | "保存" / "保存中..." |
| 按钮图标 | `Plus` | `Save` |
| 表单状态标签 | "Draft" | "Editing" |
| 初始消息 | 引导用户描述项目需求 | 提示编辑配置方式 |
| 提交动作 | `handleCreate()` | `handleSave()` |

**自定义模型下拉框**：
- 替换原生 `<select>` 为自定义下拉组件（解决跨浏览器样式不一致问题）
- 支持动画过渡（Transition 组件）
- 已选中项显示勾选图标
- 点击外部自动关闭（`handleClickOutside` 事件监听）

**侧边栏编辑入口**：
- 项目列表 hover 时显示两个操作按钮：编辑（Pencil）+ 删除（Trash2）
- 新增 `edit-agent` emit 事件传递到 ChatView

---

### 4.6 尚未实现的前端模块

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

## 五、优先级建议（测试驱动更新）

### P0 — 必须立即修复（测试暴露的 🔴 高严重度问题）

| # | 项目 | 涉及文件 | 工作量 | 说明 |
|---|------|----------|--------|------|
| 1 | **Skills 三处数据对齐** | `instances/xiaodazi/skills/` + `skill_registry.yaml` + `config/skills.yaml` | 中 | 目录 68 / 注册 76 / 配置 99 严重不一致。需要：(a) 为 28 个已注册无目录的 Skill 创建 SKILL.md 或从注册中移除；(b) 为 20 个有目录无注册的 Skill 补充注册；(c) config 中 99 个配置与实际对齐 |
| 2 | **E2E 测试用例实质化** | `evaluation/suites/xiaodazi/e2e/phase1_core.yaml` + `scripts/run_e2e_auto.py` | 大 | turns=0 说明对话流程未定义。报告 6/6 PASS 但 grade_results 为空——需排查是评估引擎跳过了评分还是报告写入有 bug。**目前 E2E 无法作为质量保证手段** |
| 3 | **Rollback E2E 修复** | `scripts/verify_rollback_e2e.py` + 测试数据 | 中 | 3 份 rollback_e2e 报告均 0/2 PASS。原文档声称"6/6 通过"需要重新验证。检查 B9/B10 是否因环境原因失败 |
| 4 | **残留实例清理** | `instances/` | 小 | 清理 `b307fc3d`（仅1文件无config）、`xiaodazi_backup`（无prompt）、`42c0dcfb`、`820e1326`。删除 `tools/request_human_confirmation _copy.py` |
| 5 | **旧存储路径清理** | `data/local_store/` | 小 | `data/local_store/xiaodazi/`（3文件）应已迁移到 `data/instances/xiaodazi/db/`，需确认后删除 |

### P1 — 链路断裂修复

| # | 项目 | 涉及文件 | 工作量 | 说明 |
|---|------|----------|--------|------|
| 6 | Playbook 端到端串联 | `core/agent/base.py` + `core/events/broadcaster.py` + `routers/` | 中 | `base.py` 需调用 `PlaybookManager.extract_from_session()`。3条链路：DRAFT生成→用户确认→APPROVED |
| 7 | 停止生成功能修复 | `frontend/src/composables/useChat.ts` + `stores/session.ts` | 小 | 暂停按钮无效果 |
| 8 | 记忆混合检索权重 | `core/memory/instance_memory.py` | 小 | config 已声明 `vector_weight`/`bm25_weight`，recall 中未应用 |
| 9 | ProgressTransformer 集成 | `core/planning/` + `tools/plan_todo_tool.py` | 小 | PlanTodoTool 步骤完成时未调用 `transform_and_emit()` |
| 10 | 前端 HITL 事件渲染 | `frontend/src/components/modals/` | 中 | backtrack_exhausted / intent_clarify / cost_limit / cost_warn 四类事件前端全部未处理 |

### P2 — 已有功能完善

| # | 项目 | 涉及文件 | 工作量 | 说明 |
|---|------|----------|--------|------|
| 11 | 记忆文件监听同步 | `core/memory/` | 中 | watchdog 监听 MEMORY.md 变更 |
| 12 | Playbook 语义匹配 | `core/playbook/manager.py` | 小 | 替换关键词匹配为 Mem0 语义搜索（LLM-First） |
| 13 | DatabaseStorage 迁移 | `core/playbook/storage.py` | 小 | DatabaseStorage 依赖已删除的 `infra.database`，需迁移或标记不可用 |
| 14 | tool_registry.yaml 清理 | `config/tool_registry.yaml` | 小 | 文件仅有注释无内容（720字符空壳），工具注册实际在 capabilities.yaml。需决定保留还是删除 |
| 15 | 文档模块名修正 | 本文档 + 所有引用 | 小 | `instance_memory` → `instance_memory` / `InstanceMemoryManager` → `InstanceMemoryManager` |

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

### 本轮新增/修改文件（项目编辑 + 多 Provider 批量保存 + Skills 格式重构）

| 文件 | 修改内容 |
|------|----------|
| `frontend/src/api/models.ts` | 新增 `ProviderActivateResult` 接口 + `activateProvider()` 批量激活 API |
| `frontend/src/views/settings/SettingsView.vue` | 重构为多 Provider 批量保存+验证+激活，移除单 Provider 选中限制 |
| `frontend/src/views/project/CreateProjectView.vue` | 新增编辑模式（`isEditMode`）+ `handleSave()` + `loadAgentData()` + 自定义模型下拉框 |
| `frontend/src/views/chat/ChatView.vue` | 新增 `handleEditAgent()` 编辑跳转 + `@edit-agent` 事件绑定 |
| `frontend/src/components/chat/ConversationSidebar.vue` | 项目列表新增编辑按钮（Pencil 图标）+ `edit-agent` emit 事件 |
| `frontend/src/router/index.ts` | 新增 `/edit-project/:agentId` 路由 |
| `instances/xiaodazi/skills/skill_registry.yaml` | 格式重构：紧凑单行 → 展开式 YAML + description 字段，移除 status/os |
| `instances/xiaodazi/skills/apple-notes/SKILL.md` | 新增 Apple Notes Skill（通过 `memo` CLI 管理） |
| `instances/daa22480/` | 新增用户创建的自定义实例（config + prompt + skills + prompt_results） |
| `frontend/src-tauri/binaries/zenflux-backend-x86_64-pc-windows-msvc.exe` | 新增 Windows 后端二进制（Tauri sidecar） |

**本轮删除文件**：

| 文件 | 原因 |
|------|------|
| `instances/b307fc3d/` （整个目录） | 测试实例清理（config + prompt + skills + prompt_results） |

---

### 早期轮次新增文件（实例隔离 + 后台任务 + Skills 扩充 + SkillGroupRegistry）

| 文件 | 职责 |
|------|------|
| `core/skill/group_registry.py` | **SkillGroupRegistry**：Skill 分组单一数据源（CRUD + 描述生成 + 孤儿检测） |
| `utils/app_paths.py` | 统一路径管理器（双模式：开发 vs PyInstaller，实例隔离路径函数） |
| `utils/background_tasks/tasks/memory_flush.py` | 会话级记忆提取后台任务（fire-and-forget） |
| `scripts/migrate_instance_storage.py` | 一次性迁移脚本：旧全局路径 → 实例隔离路径 |
| `scripts/verify_memory_persona_e2e.py` | 记忆 + 人格 E2E 验证脚本 |
| `scripts/verify_session_memory_e2e.py` | 会话记忆 E2E 验证脚本 |
| `docs/xiaodazi_skills_recommendation.md` | Skills 推荐与规划文档 |
| `instances/xiaodazi/skills/brainstorming/` | 头脑风暴 Skill |
| `instances/xiaodazi/skills/draw-io/` | Draw.io 绘图 Skill |
| `instances/xiaodazi/skills/elegant-reports/` | 优雅报告生成 Skill |
| `instances/xiaodazi/skills/excalidraw/` | Excalidraw 绘图 Skill |
| `instances/xiaodazi/skills/humanizer/` | 文本人性化 Skill |
| `instances/xiaodazi/skills/invoice-organizer/` | 发票整理 Skill |
| `instances/xiaodazi/skills/job-application-optimizer/` | 求职优化 Skill |
| `instances/xiaodazi/skills/meeting-insights-analyzer/` | 会议洞察分析 Skill |
| `instances/xiaodazi/skills/meeting-notes-to-action-items/` | 会议纪要转待办 Skill |
| `instances/xiaodazi/skills/quiz-maker/` | 测验生成 Skill |
| `instances/xiaodazi/skills/skill-tutor/` | 技能教学 Skill |

### 早期轮次修改文件（实例隔离 + 记忆系统 + 存储改造）

| 文件 | 修改内容 |
|------|----------|
| `core/skill/__init__.py` | 导出 SkillGroupRegistry |
| `core/routing/intent_analyzer.py` | V12.0 从 SkillGroupRegistry 动态获取分组描述 |
| `core/prompt/intent_prompt_generator.py` | 对接 SkillGroupRegistry.build_groups_description() |
| `core/context/injectors/phase1/tool_provider.py` | 按 skill_groups 过滤 Skills 注入 |
| `prompts/intent_recognition_prompt.py` | V12.0 动态占位符 + 17 个 Few-Shot |
| `utils/instance_loader.py` | `create_agent_from_instance()` 设置 `os.environ["AGENT_INSTANCE"]` |
| `infra/local_store/engine.py` | DB 路径从 `AGENT_INSTANCE` 自动解析到 `get_instance_db_dir()` |
| `infra/storage/local.py` | 文件上传路径从 `AGENT_INSTANCE` 解析到 `get_instance_storage_dir()` |
| `core/playbook/storage.py` | FileStorage 路径从 `AGENT_INSTANCE` 解析到 `get_instance_playbooks_dir()` |
| `core/memory/instance_memory.py` | 记忆路径从 `AGENT_INSTANCE` 解析到 `get_instance_memory_dir()` |
| `core/memory/markdown_layer.py` | 适配实例隔离路径 |
| `core/memory/mem0/config.py` | Mem0 配置适配实例隔离 |
| `core/memory/mem0/pool.py` | Mem0 Pool 适配实例隔离 |
| `core/memory/mem0/sqlite_vec_store.py` | 向量存储路径实例隔离 + `check_same_thread=False` |
| `core/memory/mem0/extraction/extractor.py` | FragmentExtractor 修复 LLM Profile 初始化 |
| `core/memory/mem0/update/quality_control.py` | 空内容/短文本格式校验 + detect_conflicts 修复 |
| `core/memory/mem0/schemas/fragment.py` | FragmentMemory 10 维 hint 字段修复 |
| `core/context/injectors/phase2/user_memory.py` | 导入路径修正 |
| `core/context/runtime.py` | 回溯状态字段支持 |
| `core/agent/execution/rvrb.py` | HITL pending 检测 + 回溯状态联动 |
| `core/state/consistency_manager.py` | 快照路径适配实例隔离 |
| `core/knowledge/embeddings.py` | Embedding 模型路径适配共享目录 |
| `core/skill/loader.py` | SkillsLoader 适配新增 Skills |
| `core/tool/types.py` | 工具类型定义更新 |
| `services/chat_service.py` | 后台任务调度集成 memory_flush |
| `services/settings_service.py` | 设置服务更新 |
| `utils/background_tasks/service.py` | 两级调度策略重构（SSE-dependent vs fire-and-forget） |
| `main.py` | 端口从 `get_cli_port()` 获取 + 实例自动检测 |
| `instances/xiaodazi/config.yaml` | 各项配置更新 |
| `instances/xiaodazi/prompt.md` | 提示词优化 |
| `instances/xiaodazi/skills/skill_registry.yaml` | 新增 Skills 注册 |

### 早期轮次新增文件（B9/B10 回滚安全 + Plan 优化）

| 文件 | 职责 |
|------|------|
| `scripts/verify_rollback_e2e.py` | B9/B10 状态层独立验证（6 个子场景，秒级完成） |
| `docs/benchmark/data/rollback_test/` | B9/B10 合成测试数据（config.json / nginx.conf / README.md / docs/*.md 共 8 文件） |
| `docs/benchmark/test_cases.md` (B9/B10 章节) | B9 异常自动回滚 + B10 用户中止回滚测试用例 |

### 早期轮次新增文件（仍有效）

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

### 早期轮次修改的前端文件

| 文件 | 修改内容 |
|------|----------|
| `frontend/src/views/settings/SettingsView.vue` | 重构为 Provider 卡片式 UI + Models API 集成 + 验证保存 + 引导集成 |
| `frontend/src/views/chat/ChatView.vue` | 引导启动入口 + SimpleConfirmModal 替代 alert/confirm + 步骤编号调整 |
| `frontend/src/views/skills/SkillsView.vue` | 技能管理页重构 |
| `frontend/src/components/chat/MessageList.vue` | 移除 3 张建议卡片 + 未使用图标导入 |
| `frontend/src/components/chat/ConversationSidebar.vue` | 引导步骤编号调整 |
| `frontend/src/components/chat/ChatInputArea.vue` | 停止生成按钮 loading/stopping 状态传递 |

### 早期轮次删除文件

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
| `core/memory/instance_memory.py` | 三层记忆架构入口 |
| `core/knowledge/local_search.py` | FTS5 搜索实现 |
| `core/knowledge/file_indexer.py` | 增量文件索引 |
| `core/termination/adaptive.py` | 八维度终止 + HITL |
| `core/state/consistency_manager.py` | 快照/回滚完整实现 |
| `core/events/broadcaster.py` | rollback + progress 事件 |

### 验证结果（第四次更新 — 2026-02-09 测试驱动）

#### 自动化 import 验证

| 验证项 | 结果 | 详情 |
|--------|------|------|
| 核心模块 import（64 个） | **63/64 通过** | ❌ `core.memory.instance_memory` 模块不存在（实际为 `core.memory.instance_memory`） |
| FastAPI app 路由加载 | ✅ 72 端点正常 | 9 路由 + 8 服务 + WebSocket |

#### Skills 数据一致性验证

| 数据源 | 数量 | 状态 |
|--------|------|------|
| `instances/xiaodazi/skills/` 目录 | 68 个（全部含 SKILL.md） | ✅ |
| `skill_registry.yaml` 注册 | 76 个 | ⚠️ 28 个已注册但无目录（多为 MCP 远程 Skill） |
| `config/skills.yaml` 配置 | 99 个 | ⚠️ 与目录差距 31 个 |
| `skill_groups` 分组覆盖 | 92 个（21 个分组） | ⚠️ |
| 有目录但未在 registry 注册 | 20 个 | ❌ 如 deep-research, pdf-toolkit, smart-email-assistant 等 |
| 已注册但无目录 | 28 个 | ⚠️ 如 notion, github, weather, peekaboo, browser 等（多为 MCP 或远程工具） |

#### 关键链路断裂验证

| 链路 | 状态 | 详情 |
|------|------|------|
| IntentAnalyzer → SkillGroupRegistry | ✅ 通过 | V12.0 链路正常 |
| ChatService → memory_flush | ✅ 通过 | 后台任务链路正常 |
| main.py → knowledge 索引 | ✅ 通过 | 启动时调用 index_configured |
| base.py → PlaybookManager | ❌ 断裂 | base.py 不调用 extract_from_session()，Playbook 无数据源 |
| PlaybookHintInjector → Playbook 数据 | ⚠️ 空转 | 注入器代码正常，但无 APPROVED Playbook 可注入 |

#### E2E 评估报告验证

| 报告 | 结果 | 问题 |
|------|------|------|
| `e2e_phase1_20260209_125850.json` | 6/6 PASS | ⚠️ **grade_results 为空**，无评分详情 |
| `e2e_phase1_20260209_123315.json` | 6/6 PASS | ⚠️ **同上** |
| `rollback_e2e_20260208_212613.json` | 0/2 PASS | ❌ 历史 |
| `rollback_e2e_20260208_212759.json` | 0/2 PASS | ❌ 历史 |
| `rollback_e2e_20260208_222803.json` | 0/2 PASS | ❌ 历史 |
| `rollback_e2e_20260209_160621.json` | **2/2 PASS** | ✅ B9/B10 共 6 子场景通过 |
| E2E tasks turns | 6 个用例 turns=0 | ❌ **对话流程未定义** |

> **结论**：E2E 报告的 6/6 PASS 不可信——用例对话为空，评分详情缺失。Rollback E2E 最新报告（20260209_160621）已 2/2 PASS；用户侧「没有快照恢复」根因是实例未启用 state_consistency，已通过 config.yaml 修复。

#### 实例目录状态

| 实例 | config.yaml | prompt.md | .env | 文件数 | 状态 |
|------|-------------|-----------|------|--------|------|
| `xiaodazi` | ✅ | ✅ | ✅ | 9 | 主实例 |
| `_template` | ✅ | ✅ | — | 6 | 脚手架模板 |
| `42c0dcfb` | ❌ | ✅ | — | 3 | ⚠️ 残留，缺 config |
| `820e1326` | ❌ | ✅ | — | 3 | ⚠️ 残留，缺 config |
| `xiaodazi_backup` | ✅ | ❌ | ✅ | 3 | ⚠️ 残留备份 |
| `b307fc3d` | ❌ | ❌ | — | 1 | ⚠️ 残留，仅 1 文件 |

#### 遗留文件

| 文件 | 问题 |
|------|------|
| `tools/request_human_confirmation _copy.py` | 文件名含空格的副本文件，应删除 |
| `data/local_store/xiaodazi/` | 旧存储路径残留（3 文件），应已迁移到 `data/instances/` |

#### 之前的验证结果（未重新运行，仅供参考）

| 验证脚本 | 历史结果 | 本次是否验证 |
|----------|---------|-------------|
| `scripts/verify_v11_architecture.py` | 119/119 通过 | 未重新运行 |
| `scripts/verify_memory_knowledge.py` | 41/41 通过 | 未重新运行 |
| `scripts/verify_rollback_e2e.py` | 声称 6/6 通过 | ⚠️ 与报告矛盾，需重跑 |

### 实例存储隔离改造涉及文件汇总

| 组件 | 文件 | 路径函数 |
|------|------|---------|
| 主数据库 | `infra/local_store/engine.py` | `get_instance_db_dir()` |
| 文件上传 | `infra/storage/local.py` | `get_instance_storage_dir()` |
| 记忆文件 | `core/memory/instance_memory.py` | `get_instance_memory_dir()` |
| Mem0 向量 | `core/memory/mem0/sqlite_vec_store.py` | `get_instance_store_dir()` |
| FTS 索引 | `core/memory/mem0/config.py` | `get_instance_store_dir()` |
| Playbook | `core/playbook/storage.py` | `get_instance_playbooks_dir()` |
| 快照 | `core/state/consistency_manager.py` | `get_instance_snapshots_dir()` |
| Embedding | `core/knowledge/embeddings.py` | `get_shared_models_dir()` |
| 路径管理 | `utils/app_paths.py` | （所有路径函数定义处） |
| 实例加载 | `utils/instance_loader.py` | 设置 `AGENT_INSTANCE` 环境变量 |
