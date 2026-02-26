---
name: jina-reader
description: Extract clean readable content from any URL using Jina Reader API. No API key required.
metadata:
  xiaodazi:
    dependency_level: builtin
    os: [common]
    backend_type: local
    user_facing: true
---

# Jina Reader — 网页内容提取

将任意网页 URL 转换为干净的 Markdown 文本，去除广告、导航栏等噪声。免费，无需 API Key。

## 使用场景

- 用户说「帮我读一下这个链接的内容」「总结这篇文章」
- 需要获取网页完整内容用于分析、翻译、摘要
- deep-research 流程中需要抓取网页正文
- 用户分享了一个 URL，想了解内容

## 执行方式

### 基本用法

在目标 URL 前加上 `https://r.jina.ai/` 前缀即可：

```bash
curl -s "https://r.jina.ai/https://example.com/article" \
  -H "Accept: text/markdown"
```

返回干净的 Markdown 格式正文内容。

### 搜索功能

Jina Reader 也支持搜索：

```bash
curl -s "https://s.jina.ai/搜索关键词" \
  -H "Accept: text/markdown"
```

### 使用建议

1. **优先用于长文章**：短页面直接搜索摘要即可，长文用 Jina Reader 获取完整内容
2. **配合搜索使用**：先用 `ddg-search` 找到 URL，再用 Jina Reader 提取正文
3. **超时处理**：某些网页可能加载慢，设置合理超时（15 秒）
4. **内容截断**：超长文章（>50000 字）只取前部分，避免上下文溢出

## 输出规范

- 提取的内容保持原文结构（标题、段落、列表）
- 标注来源 URL
- 如果提取失败，回退到搜索摘要方式
