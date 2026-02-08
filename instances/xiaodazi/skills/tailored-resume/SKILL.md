---
name: tailored-resume
description: Analyze job descriptions and generate targeted resumes that highlight matching skills, experience, and keywords. Output in Markdown or Word format.
metadata:
  xiaodazi:
    dependency_level: builtin
    os: [common]
    backend_type: local
    user_facing: true
---

# 定制简历生成

分析职位描述，生成针对性简历：突出匹配技能、优化关键词、调整经历描述。

## 使用场景

- 用户说「根据这个 JD 帮我优化简历」「帮我针对这个岗位改简历」
- 用户说「帮我写一份产品经理的简历」「英文简历」
- 用户说「分析一下我的简历和这个职位的匹配度」

## 执行方式

直接使用 LLM 能力分析和生成。可配合 word-processor Skill 输出 Word 格式。

### Step 1: 分析职位描述

从 JD 中提取：
- **核心要求**：必备技能、经验年限、学历
- **加分项**：优先技能、行业经验
- **关键词**：ATS（简历筛选系统）关键词
- **文化信号**：公司文化和价值观暗示

### Step 2: 匹配度分析

```
## 匹配度分析

### 强匹配 ✅
- Python 开发 3 年 → JD 要求 2 年+
- 数据分析经验 → JD 核心要求

### 部分匹配 ⚠️
- 有 MySQL 经验 → JD 要求 PostgreSQL（同类可迁移）

### 缺口 ❌
- JD 要求 Kubernetes 经验 → 建议在项目经历中补充相关描述
```

### Step 3: 生成定制简历

简历结构：

```markdown
# [姓名]

[联系方式] | [邮箱] | [LinkedIn/Portfolio]

## Summary / 个人摘要
[2-3 句，精准匹配 JD 核心需求]

## Experience / 工作经历
### [公司名] — [职位] (起止日期)
- [用 STAR 法则描述成就，嵌入 JD 关键词]
- [量化结果：数字、百分比、规模]

## Skills / 技能
[按 JD 优先级排列，匹配度高的在前]

## Education / 教育背景
[学校、学位、相关课程]
```

### 优化策略

| 策略 | 说明 |
|---|---|
| 关键词嵌入 | JD 中的关键技术词自然融入经历描述 |
| STAR 法则 | Situation→Task→Action→Result 结构化描述 |
| 量化成果 | 用数字说话：提升 30%、管理 10 人团队 |
| 动作动词开头 | Led, Developed, Optimized, Delivered |
| 去除无关经历 | 根据 JD 裁剪不相关内容 |

## 输出规范

- 输出 Markdown 格式（可配合 word-processor 转 Word）
- 附带匹配度分析报告
- 标注 ATS 关键词覆盖率
- 中英文简历分别生成（根据 JD 语言）
- 建议简历控制在 1-2 页
