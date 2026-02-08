---
name: cross-app-workflow
description: Chain multiple local apps and skills into complex multi-step workflows. Orchestrate file operations, document generation, email, and app automation into seamless pipelines.
metadata:
  xiaodazi:
    dependency_level: builtin
    os: [common]
    backend_type: local
    user_facing: true
---

# 跨应用工作流

将多个本地应用和 Skill 串联成复杂的多步骤工作流，完成端到端的自动化任务。

## 使用场景

- 用户说「把邮件里的附件提取出来，分析 Excel，生成报告，再回复邮件」
- 用户说「从这 5 个 PDF 里提取数据，汇总到 Excel，做个图表」
- 用户说「把会议纪要整理成行动项，加到日历，通知参会者」
- 用户说「分析这个文件夹的数据，生成 PPT，保存到桌面」

## 执行方式

这是一个**编排型 Skill**，本身不执行具体操作，而是指导 Agent 如何将多个 Skill 串联使用。

### 工作流编排原则

1. **理解完整目标**：分析用户请求，识别需要的所有步骤
2. **拆解任务链**：将目标分解为有序的子任务
3. **选择合适 Skill**：每个子任务匹配最佳 Skill
4. **传递中间结果**：上一步的输出作为下一步的输入
5. **错误恢复**：某步失败时尝试替代方案

### 常见工作流模板

#### 数据分析 → 报告生成

```
Step 1: [excel-analyzer] 读取并分析数据文件
Step 2: [LLM] 基于分析结果生成洞察和结论
Step 3: [elegant-reports / word-processor] 生成格式化报告
Step 4: [file-manager] 保存到用户指定位置
```

#### 邮件处理 → 任务分发

```
Step 1: [himalaya / outlook-cli] 读取邮件内容和附件
Step 2: [LLM] 提取关键信息和行动项
Step 3: [meeting-notes-to-action-items] 结构化行动项
Step 4: [apple-calendar / outlook-cli] 创建日程提醒
Step 5: [himalaya / outlook-cli] 起草并发送回复
```

#### 内容创作 → 多平台分发

```
Step 1: [writing-assistant] 撰写长文
Step 2: [humanizer] 去 AI 味润色
Step 3: [content-reformatter] 适配各平台格式
Step 4: [file-manager] 保存各版本到对应文件夹
```

#### 文献调研 → 报告

```
Step 1: [paper-search / arxiv-search] 搜索相关论文
Step 2: [deep-doc-reader] 深度阅读关键论文
Step 3: [literature-reviewer] 对比分析多篇文献
Step 4: [word-processor] 生成文献综述报告
```

### 中间结果管理

- 每步产生的文件保存到 `~/Desktop/xiaodazi_workflow/` 临时目录
- 工作流完成后提醒用户检查中间文件是否需要保留
- 大数据中间结果写入文件，不全部放入上下文

## 安全规则

- **每步执行前展示计划**：让用户了解接下来的操作
- **敏感操作需确认**：发送邮件、删除文件等需用 HITL 确认
- **错误不静默跳过**：某步失败时通知用户并提供替代方案

## 输出规范

- 开始前展示完整工作流计划（步骤列表）
- 每步完成后报告进度
- 全部完成后给出总结：执行了哪些操作、生成了哪些文件
