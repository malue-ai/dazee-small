# ZenFlux Agent — TODO

---

## 一、MVP

---

### 1. 引导页（Onboarding）

| # | 功能点 | 前端 (FE) | 后端 (BE) |
|---|--------|-----------|-----------|
| 1.1 | [ ] 3 步引导 UI | 欢迎 → 配置 → 完成 步骤导航、步骤指示器（进度条）、步骤切换滑动动画、跳过按钮 | — |
| 1.2 | [ ] 多模型 Key 配置表单 | 多提供商输入框（Claude / GPT / Qwen / Gemini / DeepSeek），每个带状态标记（已配置 ✓ / 未配置） | Settings schema 扩展支持多提供商，`PUT /settings` 保存多 Key |
| 1.3 | [ ] 默认模型选择 | 配置完 Key 后展示可用模型列表，选择默认模型 | `GET /settings/available-models` 返回当前可用模型列表 |
| 1.4 | [ ] 配置状态检测 | 调用 API 判断：①有用户 Key → 可完成引导 ②无可用 Key → 禁止完成引导 | `GET /settings/status` 返回 configured / missing |
| 1.5 | [ ] 配置成功反馈 | 填入 Key 后显示成功/失败提示 | — |
| 1.6 | [ ] 完成标记 + 跳转 | `localStorage` 标记完成、`router.replace('/')` 跳转聊天页 | — |

---

### 2. 聊天页（Chat）

| # | 功能点 | 前端 (FE) | 后端 (BE) |
|---|--------|-----------|-----------|
| 2.1 | [ ] 对话列表侧边栏 | `ConversationSidebar.vue`：搜索、创建新对话、删除对话、选择对话、折叠/展开（70px/260px） | `POST /conversations`、`GET /conversations`、`DELETE /conversations/{id}`、`GET /conversations/{id}` |
| 2.2 | [ ] 消息列表 | `MessageList.vue`：消息渲染（用户/助手）、自动滚动（用户滚动检测）、向上滚动加载历史 | `GET /conversations/{id}/messages`（游标分页） |
| 2.3 | [ ] 消息内容块 | `MessageContent.vue`：文本块、思考块（展开/折叠 + 计时器）、工具块、图片/文件块、流式状态 | 消息事件流：`message_start` / `message_delta` / `message_stop` |
| 2.4 | [ ] Markdown 渲染 | `MarkdownRenderer.vue`：`markstream-vue` 渲染、Mermaid 图表支持、流式渲染 | — |
| 2.5 | [ ] WebSocket 通信 | `useWebSocketChat.ts`：连接建立、心跳（30s）、指数退避重连（800ms-15s，最多 8 次）、请求/响应匹配 | `routers/websocket.py`：帧协议（req/res/event）、心跳、delta 节流（150ms） |
| 2.7 | [ ] 消息输入区 | `ChatInputArea.vue`：自动伸缩 textarea（max 150px）、IME 输入法处理、Enter 发送 / Shift+Enter 换行 | — |
| 2.8 | [ ] 发送消息 | `useChat.ts`：拼装消息内容、WebSocket 发送、清空输入、刷新对话列表、滚动到底部 | `chat.send` WebSocket 方法 → `chat_service.chat()` 编排（意图分析 → 上下文压缩 → Agent 调度） |
| 2.9 | [ ] 停止生成 | 前端停止按钮 + `useChat.stopGeneration()` | `POST /session/{id}/stop`、`chat.abort` WebSocket 方法 |
| 2.10 | [ ] 文件附件（纯本地） | Tauri 原生文件选择对话框获取本地路径、文件预览 chips（移除文件）、附件预览弹窗 `AttachmentPreview.vue` | 本地文件直读（`aiofiles.open()`）、图片 → base64 → `source.type=base64` 传 LLM、文本直读内容拼入消息。移除整条 S3 链路（`file_service.py` / `routers/files.py`） |
| 2.11 | [ ] 工具通用样式 | `ToolMessage.vue`：工具图标 + 标题 + 状态、展开/折叠输入参数和执行结果、流式指示器、错误状态 | 工具执行事件流（tool_use → tool_result） |
| 2.12 | [ ] 工具专属样式 — `web_search` | 搜索结果卡片：标题 + URL + 摘要，可点击跳转 | 搜索结果结构化返回（title / url / snippet 字段） |
| 2.13 | [ ] 工具专属样式 — `read_file` | 代码预览：语法高亮 + 文件名 + 行号 | — |
| 2.14 | [ ] 工具专属样式 — `write_file` / `create_file` | 文件写入预览：文件名 + 内容预览（语法高亮），点击可在 Workspace 打开 | — |
| 2.15 | [ ] 工具专属样式 — `str_replace_editor` | Diff 视图：旧内容 → 新内容，红绿对比 | — |
| 2.16 | [ ] 工具专属样式 — `api_calling` | 请求/响应卡片：方法 + URL + 状态码 + 响应体折叠 | — |
| 2.17 | [ ] 工具专属样式 — `observe_screen` | 截图预览：内嵌截图图片 + OCR 文本结果 | — |
| 2.18 | [ ] 工具专属样式 — `knowledge_search` | 知识检索卡片：匹配片段 + 来源文件 + 相关度 | — |
| 2.19 | [ ] Plan 展示 | `PlanWidget.vue`：计划标题 + 概述、可折叠详细计划（Markdown）、任务列表（完成/进行中/待办）、进度计数 | `plan_todo` 工具事件、`conversation_metadata` 中的 plan 数据 |
| 2.20 | [ ] Workspace 文件树 | `FileExplorer.vue`：文件树展开/折叠、项目卡片 + 运行按钮、刷新/全部展开、文件数量和大小统计 | `GET /workspace/{conversation_id}/files`、`POST /workspace/{conversation_id}/run` |
| 2.21 | [ ] Workspace 文件预览 | `FilePreview.vue`：HTML 预览（iframe）、代码语法高亮、图片预览、下载和新窗口打开 | `GET /workspace/{conversation_id}/files/{path}` |
| 2.22 | [ ] HITL 人类确认 | `ConfirmModal.vue`：多种确认类型（yes_no / single_choice / multiple_choice / text_input / form）、表单构建与验证 | `POST /session/{id}/hitl_confirm`、`wait_hitl_confirm()` 阻塞等待 |
| 2.23 | [ ] Agent 回溯（文件级） | `RollbackOptionsModal.vue`：可回溯操作列表、确认/取消 | `POST /session/{id}/rollback`、`StateConsistencyManager` 状态快照 + 文件恢复、`OperationLog` 操作日志 |
| 2.24 | [ ] Agent 回退决策 | — | `BacktrackManager`（LLM 驱动）：错误分类 → 回退类型决策（PLAN_REPLAN / TOOL_REPLACE / PARAM_ADJUST / CONTEXT_ENRICH / INTENT_CLARIFY）、RVR-B 执行器集成 |
| 2.25 | [ ] 用户操作撤销 | 对话删除后支持撤销（toast 提示 + 撤销按钮，30s 内可恢复）、消息删除撤销 | 软删除机制：删除标记 + 定时清理，`POST /conversations/{id}/restore` 恢复接口 |
| 2.26 | [ ] 长任务确认 | `LongRunConfirmModal.vue`：继续/停止对话框 | `POST /session/{id}/confirm_continue` |
| 2.27 | [ ] 欢迎页建议 | `MessageList.vue`：欢迎标语 + 快捷建议按钮，点击填入输入框 | — |
| 2.28 | [ ] ChatHeader 清理 | 删除 `ChatHeader.vue` 组件文件、`ChatView.vue` 中的注释代码（26-31行）和 import（220行） | — |
| 2.29 | [ ] 右侧面板 Tab 切换 | 任务 / 工作区 两个 Tab，关闭按钮，面板滑入/滑出动画 | — |

---

### 3. 设置页（Settings）

| # | 功能点 | 前端 (FE) | 后端 (BE) |
|---|--------|-----------|-----------|
| 3.1 | [ ] 设置入口 | `ConversationSidebar.vue` 底部固定区域：用户头像 + 齿轮图标，点击跳转 `/settings` | — |
| 3.2 | [ ] 动态表单渲染 | 基于后端 schema 动态生成表单字段（input / secret / select） | `GET /settings/schema` 返回字段定义（label / required / secret / default） |
| 3.3 | [ ] 分组显示 | API Keys、LLM 配置、应用设置 三组分区展示 | Schema 中 `api_keys` / `llm` / `app` 分组 |
| 3.4 | [ ] Secret 字段切换 | 密钥字段显示/隐藏 toggle | 返回设置时密钥脱敏处理 |
| 3.5 | [ ] 保存配置 | 提交表单、保存成功反馈、loading 状态 | `PUT /settings` 写入 `config.yaml` |
| 3.6 | [ ] 配置状态检测 | 未配置时显示警告 banner，已配置显示 ✓ | `GET /settings/status` 返回 `configured` / `missing` / `summary` |
| 3.7 | [ ] 返回聊天入口 | 页面顶部"返回聊天"链接 | — |

---

### 4. 助手管理页（Assistants）

| # | 功能点 | 前端 (FE) | 后端 (BE) |
|---|--------|-----------|-----------|
| 4.1 | [ ] 移除知识库页 | 删除 `KnowledgeView.vue`、`/knowledge` 路由、`stores/knowledge.ts` | — |
| 4.2 | [ ] 助手管理页路由 | 新建 `AssistantsView.vue`，路由 `/assistants` | — |
| 4.3 | [ ] 助手列表 — 我的助手 | 卡片式展示：名称、描述、状态（草稿/已发布）、技能数量 | `GET /agents` 返回实例列表（读取 `instances/` 目录） |
| 4.4 | [ ] 助手列表 — 助手社区 | 预置模板浏览 Tab，一键克隆到"我的助手" | `GET /agents/templates` 返回预置模板 |
| 4.5 | [ ] 创建助手 | 引导式创建：①名称和描述 ②编写 `prompt.md` ③选择模型和工具 ④预览配置 | `POST /agents` 创建新 `instances/{name}/` 目录（`prompt.md` + `config.yaml`），触发 `prompt_results/` 自动生成 |
| 4.6 | [ ] 删除助手 | 删除确认弹窗 + 调用 API | `DELETE /agents/{id}` 删除 `instances/{name}/` 目录 |
| 4.7 | [ ] 助手切换 | 聊天页侧边栏或输入区显示当前助手，点击切换 | 切换当前活跃实例，重新加载 Agent 配置 |
| 4.8 | [ ] 助手内技能管理 | 助手详情页中：技能列表展示、ZIP 上传新技能、删除技能 | `GET /skills/{agent_id}`、`POST /skills/upload`、`DELETE /skills/{agent_id}/{skill_name}` |
| 4.9 | [ ] 侧边栏助手入口 | `ConversationSidebar.vue` 顶部加助手管理入口按钮 | — |

---

### 5. 全局 / 侧边栏

| # | 功能点 | 前端 (FE) | 后端 (BE) |
|---|--------|-----------|-----------|
| 5.1 | [ ] 侧边栏导航重构 | `ConversationSidebar.vue`：移除知识库/技能/文档/实时语音四个入口，顶部加助手入口，底部加设置齿轮 + 用户头像 | — |
| 5.2 | [ ] SplashScreen 启动画面 | `SplashScreen.vue`：Logo + 品牌名 + 状态文字 + 加载动画、Tauri `sidecar-status` 事件监听、最小显示 1s、淡出动画 | 后端就绪检查接口、Tauri sidecar 启动状态上报 |
| 5.3 | [ ] 首次使用检测 | `App.vue`：Splash 结束后检查 `localStorage` onboarding 状态，未完成则跳转 `/onboarding` | — |
| 5.4 | [ ] 布局系统 | `DefaultLayout.vue`（全屏容器，聊天页用）、`DashboardLayout.vue`（侧边栏 + 内容区）、`layout: 'none'`（独立全屏页） | — |
| 5.5 | [ ] DebugPanel 调试面板 | 浮动触发按钮、日志过滤（模块/级别）、自动滚动、数据展开 | — |
| 5.6 | [ ] 后端技能注册 | — | `utils/instance_loader.py` `_register_skills()` 函数实现（当前空函数） |

---

### 6. Playbook 策略学习

| # | 功能点 | 前端 (FE) | 后端 (BE) |
|---|--------|-----------|-----------|
| 6.1 | [ ] Playbook 自动提取 | — | 成功会话结束后自动触发 `PlaybookManager.extract_from_session()`，从高质量会话中提取可复用策略。需在 `chat_service._run_agent()` 完成后调用 |
| 6.2 | [ ] Playbook 确认 UI | 提取完成后弹窗提示用户："学到了新技巧，是否记住？"，显示策略摘要，用户确认/拒绝 | `emit_playbook_suggestion()` 事件推送（broadcaster 已有），确认后状态从 DRAFT → APPROVED |
| 6.3 | [ ] Playbook 匹配注入 | — | `PlaybookHintInjector`（Phase 2 注入器）：任务执行前匹配相似 Playbook，注入到上下文中指导 Agent。两层匹配：task_type 预过滤 + 语义搜索 |
| 6.4 | [ ] Playbook 状态管理 | — | 状态流转：DRAFT → PENDING_REVIEW → APPROVED / REJECTED / DEPRECATED。`PlaybookStorage` 文件存储 |
| 6.5 | [ ] Playbook 与评估系统集成 | — | 与 `RewardAttribution` 集成：高奖励会话（`total_reward >= 0.7`）自动触发提取 |

---

## 二、优化项

---

### 第一梯队：体验补全

#### 引导页

| # | 功能点 | 前端 (FE) | 后端 (BE) |
|---|--------|-----------|-----------|
| O1.1 | [ ] 内置 API Key + 免费额度 | 零配置可直接使用，内置 Key 额度耗尽时弹窗提示用户配置自己的 Key | Key 安全存储（配置/环境变量，不硬编码源码）、按设备 ID 追踪用量、额度检查中间件、额度耗尽返回特定错误码 |
| O1.2 | [ ] API Key 有效性验证 | 输入后显示"验证中…" → "可用" / "无效"反馈 | 验证 API：用 Key 实际调一次模型，返回 valid / invalid |
| O1.3 | [ ] 免费额度进度展示 | 展示已用 / 总量 / 剩余百分比 | `GET /settings/quota` 返回用量数据 |
| O1.4 | [ ] 模型能力对比 | 配置多 Key 后展示各模型差异简介（速度/能力/价格） | — |
| O1.5 | [ ] 引导完成智能跳转 | 有可用 Key → 聊天页；无可用 Key → 设置页高亮缺失项 | — |
| O1.6 | [ ] 引导页视觉升级 | 产品截图、能力演示动画、插图 | — |

#### 聊天页

| # | 功能点 | 前端 (FE) | 后端 (BE) |
|---|--------|-----------|-----------|
| O2.1 | [ ] 对话全文搜索 | `ConversationSidebar` 搜索框接入后端全文搜索（当前仅本地标题过滤） | `GET /conversations/search`（FTS5 已实现） |
| O2.2 | [ ] 对话导出 | 导出当前对话为 Markdown / JSON | `GET /conversations/{id}/messages` 全量获取（已有） |
| O2.3 | [ ] 代码块增强 | 一键复制按钮、行号显示、语法高亮 | — |
| O2.4 | [ ] 欢迎页建议可配置 | 从后端或实例配置加载，不同助手展示不同建议 | `GET /agents/{id}/suggestions` 或配置中定义 |
| O2.5 | [ ] 消息编辑与重发 | 编辑已发消息，重新生成回复 | 消息更新 API + 重新触发 Agent |
| O2.6 | [ ] 消息分支 | 从某条消息创建分支对话 | 分支对话 API |
| O2.7 | [ ] 对话分类 / 文件夹 | 对话列表分组管理（按时间/标签/手动） | 对话 metadata 中增加 folder/tag 字段 |
| O2.8 | [ ] Thinking 块优化 | 增加 token 消耗显示 | 在 usage delta 中返回 thinking token 数 |
| O2.9 | [ ] 删除确认优化 | 原生 `confirm()` 替换为自定义弹窗 | — |
| O2.10 | [ ] WebSocket 参数可配置 | 心跳间隔、退避参数、最大重连次数支持通过设置调整 | — |
| O2.11 | [ ] 文件附件格式扩展 | 支持 docx / xlsx / py 等更多文件类型 | 对应 MIME 类型处理扩展 |
| O2.12 | [ ] 工作区默认路径 | 从后端动态获取，不硬编码 `/home/user/project` | 返回当前实例的工作区路径 |
| O2.13 | [ ] 回溯可视化增强 | `RollbackOptionsModal` 增强：展示每个操作的详细 diff（文件变更前后对比），而非仅操作列表 | `get_rollback_options()` 返回操作详情 + 文件 diff |
| O2.14 | [ ] 回溯超时反馈 | 回溯部分成功时给出明确反馈（哪些恢复了、哪些失败了） | 回溯结果分条返回（success / partial / failed） |

#### Playbook 增强

| # | 功能点 | 前端 (FE) | 后端 (BE) |
|---|--------|-----------|-----------|
| O7.1 | [ ] Playbook 管理页 | 查看所有已学习的策略列表、状态筛选（APPROVED / DRAFT / DEPRECATED）、删除/弃用操作 | `GET /playbooks`、`DELETE /playbooks/{id}`、`PUT /playbooks/{id}/status` |
| O7.2 | [ ] Playbook 详情查看 | 查看策略详情：触发条件、执行步骤、来源会话、成功率 | `GET /playbooks/{id}` 返回完整策略信息 |
| O7.3 | [ ] Playbook 项目级隔离 | — | 按项目隔离存储 `projects/{id}/playbook/`，不同项目的策略不交叉 |
| O7.4 | [ ] Playbook 手动创建 | 用户手动编写策略规则，不仅依赖自动提取 | `POST /playbooks` 手动创建 |

#### 设置页

| # | 功能点 | 前端 (FE) | 后端 (BE) |
|---|--------|-----------|-----------|
| O3.1 | [ ] API Key 保存前验证 | 保存时调后端验证有效性，即时反馈 | Key 验证 API |
| O3.2 | [ ] 模型可用性检测 | 根据已配置 Key 显示可用模型列表 | `GET /settings/available-models` |
| O3.3 | [ ] 重新查看引导 | 添加"重新进入引导"按钮 | — |
| O3.4 | [ ] 配置导入/导出 | 导出 `config.yaml`，从文件导入 | `GET /settings/export`、`POST /settings/import` |
| O3.5 | [ ] 重置为默认值 | 单项或全部重置 | `POST /settings/reset` |

#### 助手 & 技能

| # | 功能点 | 前端 (FE) | 后端 (BE) |
|---|--------|-----------|-----------|
| O4.1 | [ ] 助手编辑 | 修改 prompt.md、模型配置、工具选择 | `PUT /agents/{id}` 更新实例文件 |
| O4.2 | [ ] 助手详情页 | 完整配置查看：人设、技能列表、对话统计、使用次数 | `GET /agents/{id}` 返回详细信息 + 统计 |
| O4.3 | [ ] 助手导入/导出 | 导出为 ZIP（prompt.md + config.yaml + skills），支持 ZIP 导入 | `GET /agents/{id}/export`、`POST /agents/import` |
| O4.4 | [ ] 助手状态管理 | 草稿 / 已发布状态切换，草稿不在聊天页展示 | 实例 metadata 中增加 status 字段 |
| O4.5 | [ ] 技能在线编辑 | 页面内编辑 SKILL.md 和脚本文件 | `PUT /skills/{agent_id}/{skill_name}/files/{path}` |
| O4.6 | [ ] 技能启用/禁用 | 控制哪些技能在对话中可用 | `PUT /skills/{agent_id}/{skill_name}/status` |
| O4.7 | [ ] 技能模板 | 从模板快速创建技能 | `GET /skills/templates`、`POST /skills/{agent_id}/from-template` |
| O4.8 | [ ] 技能版本管理 | 更新时保留历史版本 | 版本化存储 |

#### 后端

| # | 功能点 | 前端 (FE) | 后端 (BE) |
|---|--------|-----------|-----------|
| O5.1 | [ ] local_store 迁移 | — | `instance_loader`、`agent_registry`、`reward_attribution` 多处 TODO 迁移 |
| O5.2 | [ ] Token 计算精确化 | — | 接入 Qwen / Claude 官方 tokenizer 替代估算 |
| O5.3 | [ ] MCP 连接数恢复 | — | `routers/tools.py:671` MCP pool 功能恢复 |
| O5.4 | [ ] chat_service 导入规范 | — | `chat_service.py:1168` 函数内 import 移至文件顶部 |
| O5.5 | [ ] WebSocket 帧协议文档 | — | `routers/websocket.py` req/res/event 协议正式文档 |

#### 全局

| # | 功能点 | 前端 (FE) | 后端 (BE) |
|---|--------|-----------|-----------|
| O6.1 | [ ] 全局通知系统 | 统一 toast / notification 组件 | — |
| O6.2 | [ ] Loading Skeleton | 各页面骨架屏 | — |
| O6.3 | [ ] 错误边界 | 全局错误捕获与友好提示页面 | — |
| O6.4 | [ ] 用户信息 | 侧边栏用户信息不再硬编码 "local" | 用户标识 API |

---

## 附录

### A. 聊天页架构图

```
ChatView.vue（页面容器）
├── ConversationSidebar — 左侧对话列表
├── MessageList — 消息列表
│   ├── MessageContent — 消息内容块
│   │   ├── MarkdownRenderer — Markdown 渲染
│   │   └── ToolBlock → ToolMessage / 专属组件
│   └── 欢迎页
├── ChatInputArea — 输入区
├── 右侧面板
│   ├── PlanWidget — 任务计划
│   └── Workspace（FileExplorer + FilePreview）
├── AttachmentPreview — 附件预览弹窗
├── ConfirmModal — HITL 确认弹窗
├── RollbackOptionsModal — 回溯弹窗
└── LongRunConfirmModal — 长任务确认弹窗

Composables:
├── useChat — 聊天逻辑
├── useWebSocketChat — WebSocket 连接
├── useFileUpload → 改为 useFileAttachment — 本地文件选择
└── useHITL — 人类确认

Stores:
├── conversation — 对话与消息
├── session — 会话状态
├── workspace — 工作区
├── connection — WebSocket 连接池
└── ui — UI 状态

Backend:
├── routers/websocket.py — WebSocket 帧协议
├── routers/chat.py — HTTP 聊天端点
├── routers/conversation.py — 对话 CRUD + FTS5 搜索
├── services/chat_service.py — 核心编排
├── services/conversation_service.py — 对话与消息管理
├── services/session_service.py — 会话生命周期
└── infra/local_store/crud/ — SQLite 数据层
```

### B. 工具专属样式参考

| 工具 ID | 专属样式 |
|---------|----------|
| `web_search` | 搜索结果卡片（标题 + URL + 摘要，可点击跳转） |
| `read_file` | 代码预览（语法高亮 + 文件名 + 行号） |
| `write_file` / `create_file` | 文件写入预览（文件名 + 内容预览，点击在 Workspace 打开） |
| `str_replace_editor` | Diff 视图（红绿对比） |
| `api_calling` | 请求/响应卡片（方法 + URL + 状态码 + 响应体） |
| `observe_screen` | 截图预览（内嵌图片 + OCR 文本） |
| `knowledge_search` | 知识检索卡片（匹配片段 + 来源 + 相关度） |
| `plan_todo` | 保持简洁（已有 PlanWidget 展示） |
| `request_human_confirmation` | 保持简洁（已有 ConfirmModal 处理） |

### C. 侧边栏导航目标结构

```
ConversationSidebar
├── 顶部
│   ├── Logo + 品牌名
│   ├── 折叠/展开按钮
│   ├── 助手管理入口 → /assistants
│   └── 新建对话按钮
├── 中部
│   ├── 搜索框
│   └── 对话列表
└── 底部（固定）
    ├── 用户头像
    └── 设置齿轮 → /settings
```
