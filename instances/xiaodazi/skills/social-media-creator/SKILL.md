---
name: social-media-creator
description: Create platform-optimized social media content. Adapts tone, length, formatting, hashtags, and media suggestions for Twitter/X, LinkedIn, Instagram, Medium, and more.
metadata:
  xiaodazi:
    dependency_level: builtin
    os: [common]
    backend_type: local
    user_facing: true
---

# 社交媒体内容创作

根据目标平台自动创作优化的社交媒体内容：适配语气、长度、格式、话题标签和配图建议。

## 使用场景

- 用户说「帮我写一条推广推文」「写个 LinkedIn 帖子宣布新产品」
- 用户说「把这篇文章改成 Instagram 版本」「写个 Medium 文章」
- 用户说「帮我想几条社交媒体文案」「这个话题怎么发」

## 支持的平台

### Twitter / X

```
- 长度: ≤ 280 字符（建议 200 以内更佳）
- 风格: 简洁有力，一句话核心观点
- 格式: 纯文本 + 话题标签 + 可选 thread
- 标签: 1-3 个 #hashtag
- 技巧: 开头 hook 抓注意力，结尾 CTA 引互动
- Thread: 长内容拆成 5-10 条 thread
```

### LinkedIn

```
- 长度: 500-1500 字符
- 风格: 专业但不枯燥，个人故事+专业洞察
- 格式: 短段落（1-2 句），行间留白，emoji 适量
- 标签: 3-5 个 #hashtag
- 技巧: 首句 hook（不要被折叠），结尾提问引评论
```

### Instagram

```
- 长度: 正文 ≤ 2200 字符，建议 300-500
- 风格: 视觉驱动，文字配合图片
- 格式: 短段落 + emoji + 换行
- 标签: 15-30 个 #hashtag（放评论区或正文末尾）
- 配图建议: 1:1 正方形或 4:5 竖图
```

### Medium / Blog

```
- 长度: 800-2500 字
- 风格: 深度思考，有论据和案例
- 格式: 标题 + 小标题 + 引用 + 列表 + 代码块
- SEO: 标题含关键词，正文自然嵌入
- 技巧: 前 100 字决定是否继续阅读
```

### YouTube Community / 视频描述

```
- 描述: 前 2 行最重要（折叠前可见）
- 时间戳: 为长视频添加章节时间戳
- 标签: 相关关键词标签
- CTA: 引导订阅/点赞/评论
```

## 执行方式

直接使用 LLM 能力生成内容，无需外部工具。

### 输出格式

为每个平台生成独立版本：

```markdown
## Twitter/X 版本

**正文**:
（内容）

**标签**: #tag1 #tag2 #tag3

---

## LinkedIn 版本

**正文**:
（内容）

**标签**: #tag1 #tag2 #tag3

---
```

## 输出规范

- 默认根据用户意图判断最合适的单一平台
- 用户说「全平台」时生成 3+ 个版本
- 每个版本标注字符数
- 包含配图/媒体建议
- 如有用户写作风格记忆，按风格适配
