---
name: locale-aware-formatter
description: Automatically adapt document formatting to cultural conventions - date formats, currency symbols, letter styles, number separators, and honorifics based on detected language/locale.
metadata:
  xiaodazi:
    dependency_level: builtin
    os: [common]
    backend_type: local
    user_facing: true
---

# 文化自适应格式化

根据语言和文化环境自动适配文档格式：日期格式、货币符号、信函样式、数字分隔符、称谓礼仪。

## 使用场景

- 用户说「帮我写一封商务信」→ 自动适配对应语言的信函格式
- 用户说「格式化这份报告」→ 日期、数字、货币按用户 locale 呈现
- 用户说「把这个文档转成正式格式」→ 适配对应文化的正式规范

## 执行方式

通过 LLM 结合系统 locale 检测，自动适配文化规范。

### Locale 检测

```bash
# 检测系统语言设置
echo $LANG
# macOS 额外检测
defaults read NSGlobalDomain AppleLanguages 2>/dev/null
```

### 格式适配规则

#### 日期格式

| Locale | 格式 | 示例 |
|---|---|---|
| en-US | MM/DD/YYYY | 02/09/2026 |
| en-GB | DD/MM/YYYY | 09/02/2026 |
| zh-CN | YYYY年MM月DD日 | 2026年02月09日 |
| ja-JP | YYYY年MM月DD日 | 2026年02月09日 |
| de-DE | DD.MM.YYYY | 09.02.2026 |

#### 数字与货币

| Locale | 千位分隔 | 小数点 | 货币 |
|---|---|---|---|
| en-US | 1,000.00 | . | $1,000.00 |
| de-DE | 1.000,00 | , | 1.000,00 € |
| zh-CN | 1,000.00 | . | ¥1,000.00 |
| ja-JP | 1,000 | . | ¥1,000 |

#### 商务信函格式

**English (formal)**:
```
Dear Mr./Ms. [Last Name],

[Body]

Sincerely,
[Full Name]
[Title]
```

**中文（正式）**:
```
[职务] [姓名] ：

[正文]

此致
敬礼

[署名]
[日期]
```

**日本語（敬語）**:
```
[会社名]
[部署名] [役職] [名前] 様

[本文]

敬具

[署名]
[日付]
```

#### 称谓礼仪

| 文化 | 规范 |
|---|---|
| English | Mr./Ms./Dr. + Last Name（首次），First Name（熟悉后） |
| 中文 | 姓 + 职务（王总、李经理），或 姓 + 先生/女士 |
| 日本語 | 姓 + 様/さん，职务时 姓 + 役職 |
| 한국어 | 성 + 님/씨 |

## 输出规范

- 自动检测对话语言，适配格式
- 如检测到 OS locale 与对话语言不同，询问用户偏好
- 保持核心内容不变，只调整格式和礼仪层
- 不强制转换——用户明确指定格式时优先用户要求
