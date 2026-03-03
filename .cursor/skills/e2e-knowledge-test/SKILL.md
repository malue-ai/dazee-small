---
name: e2e-knowledge-test
description: 知识库全链路端到端测试（gRPC 同步→索引→检索→Chat 工具调用→清理）。用于验证知识库功能、排查同步/索引/检索问题、测试 knowledge_search 工具在 Chat 中的表现时。
---

# e2e-knowledge-test

## 适用场景（触发词）

- 测试知识库、知识库端到端、knowledge E2E
- 验证 SyncDocuments / RemoveDocuments / DestroyKnowledgeBase / GenerateTerms
- 排查：文档索引卡住、检索无结果、DB 状态不更新、knowledge_search 工具不生效
- 修改了以下文件后需要回归验证：
  - `services/knowledge_sync_service.py`
  - `services/knowledge_service.py`
  - `grpc_server/knowledge_servicer.py`
  - `tools/knowledge_search.py`
  - `routers/knowledge.py`
  - `routers/chat.py`（knowledge_ids 相关）

## 前置条件

- gRPC 服务运行中（`localhost:50051`）
- HTTP 服务运行中（`localhost:8000`）
- PostgreSQL / Redis / Ragie API 可用

## 测试脚本

### 1. zen0 gRPC 接口测试（4 个接口）

```bash
bash .cursor/skills/e2e-knowledge-test/scripts/run.sh grpc
```

覆盖：
- `SyncDocuments`（note / link / 幂等）
- `GenerateTerms`（词条提取）
- `RemoveDocuments`（删除 + 边界）
- `DestroyKnowledgeBase`（销毁 + 边界）

### 2. 真实文档全链路测试

```bash
bash .cursor/skills/e2e-knowledge-test/scripts/run.sh real
```

覆盖：
- 创建知识库 → 同步 3 个项目 md 文件（7K-35K 字符）
- 幂等验证（重复同步 → 全部 skipped）
- 等待索引完成（`refresh=True` 刷新 DB 状态）
- 语义检索验证（3 条查询，验证 top1 命中）
- 删除单文档 + 文档数验证
- 销毁知识库

### 3. 知识库 + Chat 端到端测试

```bash
bash .cursor/skills/e2e-knowledge-test/scripts/run.sh chat
```

覆盖：
- 同步文档 → 等待索引 → DB 状态自动更新到 READY
- HTTP Chat（`feature=knowledgeQA`，SSE 流式）
- 验证 Agent 调用 knowledge_search 工具
- 验证回答包含知识库内容

### 4. 全部测试

```bash
bash .cursor/skills/e2e-knowledge-test/scripts/run.sh all
```

## 排障工作流

### 文档索引卡在 INDEXING

1. 检查 `_poll_document_statuses` 后台任务是否启动（看日志 `启动状态轮询`）
2. 用 `ListDocuments(refresh=True)` 手动刷新：确认 Ragie 侧是否已完成
3. 确认 Ragie API 配额未超限（402 错误）

### 检索无结果

1. 确认文档状态为 READY（不是 INDEXING）
2. 确认 partition_id 正确（`ListDocuments` 能看到文档）
3. 检查 `MIN_RELEVANCE_SCORE`（当前 0.1，在 `tools/knowledge_search.py`）

### Chat 中 knowledge_search 工具未触发

1. 确认请求传了 `knowledge_ids` 和 `feature: "knowledgeQA"`
2. 检查 `_inject_knowledge_description` 日志（是否成功生成动态描述）
3. 确认工具未被 `_apply_feature_focus` 过滤

## 输出要求

- **执行的命令**（可复制）
- **结果摘要**：通过/失败/跳过（失败给出复现命令和日志片段）
- **DB 状态验证**：文档状态是否正确更新
- **下一步**：若失败，列出最可能原因
