---
name: commit-message
description: 基于本仓库 git diff 与近期提交风格生成高质量 commit message，并提醒敏感文件与变更范围。用于用户要求“写提交信息/生成 commit message/准备 git commit”时。
---

# commit-message

## 适用场景（触发词）

- 生成提交信息：commit message、`git commit -m`
- 需要根据 `git diff --staged` 总结变更并写“为什么/影响”
- 需要匹配本仓库已有提交风格（如 `update:`、`refactor(scope):` 等）

## 强约束（必须遵守）

- **不得包含敏感信息**：token/key/账号、私有 URL、业务数据等都不能出现在提交信息里
- **不要误提交配置文件**：除非用户明确要求，否则应提示将 `config.yaml` 移出提交/还原
- **贴合仓库风格**：先看近期提交（`git log -20 --oneline`）再定前缀与 scope

## 工作流（按顺序执行）

### 1) 收集上下文（推荐脚本）

```bash
bash .cursor/skills/commit-message/scripts/git_context.sh
```

至少要拿到：
- `git status`
- `git diff --staged`（核心）
- 近期提交风格（`git log -20 --oneline`）

### 2) 决定类型与范围

- **update**：常规增强、配置调整、非破坏性改动
- **fix(scope)**：修 bug（scope 选模块：如 `frontend`、`chat_service` 等）
- **refactor(scope)**：重构/整理结构但不改外部行为
- **docs**：文档
- **test**：测试

### 3) 写标题（必须）

- 单行，尽量 ≤ 72 字符
- 结构优先参考仓库：`type` + 可选 `(scope)` + `: ` + 摘要
- 摘要写“变更带来的结果”，避免堆细节文件名

### 4) 写正文（可选但推荐）

用 1-3 行说明：
- 为什么要改（原因/问题）
- 改动带来的行为变化（影响）
- 如果有风险/迁移步骤，简单写清

## 输出要求（必须提供）

- **候选 commit message**：标题 + 可选正文
- **敏感文件提醒**：如果包含 `config.yaml` 或疑似密钥文件，必须显式提醒
- **简短解释**：1 句话说明为何这样命名/为何选这个 type/scope

## 示例（按仓库风格）

```text
update: 增强能力管理与模板

补齐配置与默认值，减少运行时分支与异常路径
```

```text
refactor(chat_service): 优化代码结构并修复边界 bug

统一错误处理与返回结构，降低后续维护成本
```

