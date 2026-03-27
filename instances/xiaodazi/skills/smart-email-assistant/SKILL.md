---
name: smart-email-assistant
description: "Drafts, classifies, and manages emails — compose replies, prioritize inbox, and generate professional correspondence. Use when a user asks to draft, reply to, summarize, or organize emails."
metadata:
  xiaodazi:
    dependency_level: builtin
    os: [common]
    backend_type: local
    user_facing: true
---

# 智能邮件助手

帮助用户高效管理邮件：起草回复、分类优先级、摘要收件箱、撰写专业邮件。如用户配置了邮件工具（himalaya / outlook-cli），可直接操作收发。

## 工作流程

1. **确认需求** → 收件人关系、邮件目的、语气偏好（用户未指定时询问）
2. **生成邮件** → Subject + Body 完整格式
3. **用户确认** → 展示完整邮件，等待确认后发送（如已配置邮件工具）

## 邮件起草

根据类型选择合适结构：

**商务正式:**
```
Subject: [简洁主题]
Dear [Name],
[目的 1-2 句] → [核心内容] → [期望的下一步]
Best regards, [Name]
```

**跟进 Follow-up:**
```
Subject: Following up: [原始主题]
Hi [Name],
I wanted to follow up on [事项]. [简要回顾] → [明确请求]
Thanks, [Name]
```

**委婉拒绝:**
```
Subject: Re: [原始主题]
Hi [Name],
Thank you for [提议]. [理解和认可] → Unfortunately, [理由] → [替代方案（如有）]
Best, [Name]
```

## 收件箱分类

用 himalaya/outlook-cli 获取邮件列表后，按优先级分类输出：

| 优先级 | 特征 | 建议行动 |
|--------|------|----------|
| 🔴 Urgent | 截止日期临近、上级/客户来信 | 立即回复 |
| 🟡 Important | 项目相关、需要决策 | 当天处理 |
| 🟢 Normal | 信息通知、常规沟通 | 有空处理 |
| ⚪ Low | 营销邮件、订阅通讯 | 批量处理或忽略 |

**示例输出：**
```
收件箱摘要（12 封未读）:
🔴 [2] 客户 A 合同截止 3/28、VP 要求周报
🟡 [3] 项目 X 设计评审、预算审批、团队调整
🟢 [4] 周报通知、会议纪要...
⚪ [3] SaaS 续费提醒、Newsletter...
```

## 安全规则

- **发送前必须 HITL 确认**：展示完整邮件，用户确认后才发送
- **敏感内容提醒**：涉及薪资、合同、机密信息时明确提醒用户检查

## 输出规范

- 每封邮件包含完整 Subject + Body
- 标注语气等级：`[formal]` / `[semi-formal]` / `[casual]`
- 多封邮件用 `---` 分隔
