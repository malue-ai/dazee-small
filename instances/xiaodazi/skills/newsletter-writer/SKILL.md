---
name: newsletter-writer
description: Write professional newsletters, weekly updates, company announcements, and periodic reports. Supports both internal and external audience formats.
metadata:
  xiaodazi:
    dependency_level: builtin
    os: [common]
    backend_type: local
    user_facing: true
---

# 通讯与周报写作

帮助用户撰写各类周期性通讯：邮件 Newsletter、团队周报、公司公告、项目更新。

## 使用场景

- 用户说「帮我写这周的项目周报」「写一份团队月报」
- 用户说「写一封 Newsletter 给订阅者」「写个公司内部通知」
- 用户说「帮我写一份状态更新邮件」「总结本周进展」

## 支持的通讯类型

### 团队周报 / 项目周报

```
结构:
1. 本周亮点（1-3 句总结）
2. 已完成事项（列表）
3. 进行中事项（列表 + 进度百分比）
4. 遇到的问题 / 阻塞项
5. 下周计划
6. 需要的支持 / 决策

风格: 简洁务实，重点突出
长度: 300-800 字
```

### 邮件 Newsletter

```
结构:
1. 开头 Hook（吸引打开继续阅读）
2. 核心内容（2-3 个主题）
3. 精选推荐 / 资源链接
4. 结尾 CTA（引导行动）

风格: 专业但有温度，像给朋友写信
长度: 500-1500 字
```

### 公司内部通知

```
结构:
1. 通知标题（一句话说清楚）
2. 背景说明（为什么发这个通知）
3. 具体内容（要点清晰）
4. 影响范围（谁需要关注）
5. 行动要求（需要做什么）
6. 联系方式（有问题找谁）

风格: 正式清晰
长度: 200-500 字
```

### 产品更新 / Changelog

```
结构:
1. 版本号 + 日期
2. New（新功能）
3. Improved（优化改进）
4. Fixed（修复问题）
5. Breaking Changes（如有）

风格: 技术但易懂
```

## 执行方式

直接使用 LLM 能力生成，无需外部工具。

### 信息收集

如果用户没有提供足够信息，主动询问：
- 时间范围（本周？本月？）
- 目标读者（团队？管理层？客户？）
- 关键事项（完成了什么？遇到什么问题？）
- 语气偏好（正式？轻松？）

## 输出规范

- 根据类型选择合适的结构模板
- 保持信息准确，不编造具体数据
- 标注需要用户补充的信息（用 `[待补充: ...]` 标记）
- 如有用户的写作风格记忆，自动适配
