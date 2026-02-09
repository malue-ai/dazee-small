---
name: smart-email-assistant
description: Intelligent email management - draft replies, classify by priority, summarize inbox, and compose professional emails with appropriate tone.
metadata:
  xiaodazi:
    dependency_level: builtin
    os: [common]
    backend_type: local
    user_facing: true
---

# 智能邮件助手

帮助用户高效管理邮件：起草回复、分类优先级、摘要收件箱、撰写专业邮件。

## 使用场景

- 用户说「帮我回复这封邮件」「起草一封正式的商务邮件」
- 用户说「帮我看看收件箱有什么重要的」「总结一下未读邮件」
- 用户说「写一封拒绝的邮件，但要委婉」「follow up 邮件」

## 执行方式

直接使用 LLM 能力生成邮件内容。如用户配置了邮件工具（himalaya / outlook-cli），可直接操作收发。

### 邮件类型模板

#### 商务正式邮件

```
Subject: [简洁明确的主题]

Dear [Name],

[开头: 说明写信目的，1-2 句]

[正文: 核心内容，分段清晰]

[结尾: 期望的下一步行动]

Best regards,
[Name]
```

#### 跟进邮件 (Follow-up)

```
Subject: Following up: [原始主题]

Hi [Name],

I wanted to follow up on [之前的事项].

[简要回顾上下文]

[明确的下一步请求]

Thanks,
[Name]
```

#### 委婉拒绝

```
Subject: Re: [原始主题]

Hi [Name],

Thank you for [对方的提议/请求].

[表示理解和认可]

Unfortunately, [给出拒绝理由].

[如果可能，提供替代方案]

I appreciate your understanding.

Best,
[Name]
```

#### 感谢邮件

```
Subject: Thank you for [具体事项]

Dear [Name],

[具体感谢内容]

[说明影响/价值]

[展望未来合作]

Warm regards,
[Name]
```

### 邮件优先级分类

当用户要求整理收件箱时，按以下维度分类：

| 优先级 | 特征 | 建议行动 |
|---|---|---|
| Urgent | 截止日期临近、上级/客户来信 | 立即回复 |
| Important | 项目相关、需要决策 | 当天处理 |
| Normal | 信息通知、常规沟通 | 有空处理 |
| Low | 营销邮件、订阅通讯 | 批量处理或忽略 |

### 语气适配

根据场景自动调整语气：

- **上级/客户**: 正式、尊重、简洁
- **同事**: 半正式、友好、直接
- **下属/团队**: 清晰、鼓励、有条理
- **外部合作**: 专业、礼貌、明确边界

## 输出规范

- 邮件包含 Subject + Body 完整格式
- 标注语气等级（formal / semi-formal / casual）
- 如涉及敏感内容，提醒用户检查后再发送
- 多封邮件时用分隔线区分
