---
name: cross-app-workflow
description: "Orchestrates multi-step workflows chaining local apps and skills into end-to-end pipelines. Use when a user request spans multiple tools — e.g. extracting email attachments, analyzing data, generating reports, and sending replies in one flow."
metadata:
  xiaodazi:
    dependency_level: builtin
    os: [common]
    backend_type: local
    user_facing: true
---

# 跨应用工作流

编排型 Skill — 指导 Agent 将多个 Skill 串联成端到端自动化任务。本身不执行具体操作。

## 工作流编排步骤

1. **分析目标** → 识别用户请求中所有子任务
2. **映射 Skill** → 每个子任务匹配最佳 Skill（见下方模板）
3. **执行并传递** → 上一步输出作为下一步输入，中间文件存 `~/Desktop/xiaodazi_workflow/`
4. **错误恢复** → 失败时切换替代 Skill 或通知用户

## 常见工作流模板

### 数据分析 → 报告

```
Step 1: [excel-analyzer] 读取并分析数据 → 输出: analysis.json
Step 2: [LLM] 生成洞察和结论 → 输出: insights.md
Step 3: [elegant-reports] 生成格式化报告 → 输出: report.docx
Step 4: [file-manager] 保存到用户指定位置
```

### 邮件处理 → 任务分发

```
Step 1: [himalaya / outlook-cli] 读取邮件 + 附件 → 输出: email_content + attachments
Step 2: [meeting-notes-to-action-items] 结构化行动项 → 输出: action_items.md
Step 3: [apple-calendar] 创建日程提醒
Step 4: [himalaya / outlook-cli] 起草并发送回复（需 HITL 确认）
```

### 内容创作 → 多平台分发

```
Step 1: [writing-assistant] 撰写长文 → 输出: draft.md
Step 2: [humanizer] 润色去 AI 味 → 输出: polished.md
Step 3: [content-reformatter] 适配各平台 → 输出: weixin.md, twitter.md, ...
Step 4: [file-manager] 保存各版本
```

## 错误恢复示例

```
Step 2 失败: [excel-analyzer] 无法解析 .xlsx（文件损坏）
→ 替代方案: 用 Python pandas 直接读取: pd.read_excel("file.xlsx", engine="openpyxl")
→ 如果仍失败: 通知用户「文件可能损坏，请检查是否可以在 Excel 中打开」
→ 继续: 用替代方案输出继续 Step 3
```

## 中间结果管理

- 中间文件统一保存到 `~/Desktop/xiaodazi_workflow/`，按步骤编号命名
- 大数据结果写入文件（不放入上下文），仅传递摘要给下一步
- 工作流完成后提醒用户检查中间文件是否需要保留

## 安全规则

- **执行前展示完整计划**：列出所有步骤，让用户确认再开始
- **敏感操作 HITL 确认**：发送邮件、删除文件前必须确认
- **失败时通知用户**：不静默跳过，提供替代方案让用户选择

## 输出规范

- 开始前展示步骤计划（编号列表 + 对应 Skill）
- 每步完成后报告: `✅ Step N 完成 — 输出: <文件名>`
- 全部完成后总结: 执行了哪些操作、生成了哪些文件、中间文件路径
