---
name: ddg-search
description: Search the web using Jina Search API. Privacy-friendly, no API key required.
metadata:
  xiaodazi:
    dependency_level: builtin
    os: [common]
    backend_type: local
    user_facing: true
---

# 网络搜索

通过 Jina Search API 搜索互联网，免费，无需 API Key，返回干净的 Markdown 格式结果。

## 使用场景

- 用户说「帮我搜一下…」「查查…最新消息」
- 用户需要了解某个话题的最新信息
- 需要为其他任务（写作、调研）收集背景资料
- 用户问了一个需要实时信息的问题（时事、产品价格等）

## 执行方式

通过 `api_calling` 工具调用 Jina Search API。

### 基本搜索

```json
{
  "url": "https://s.jina.ai/搜索关键词",
  "method": "GET",
  "headers": {
    "Accept": "application/json"
  }
}
```

返回 JSON 格式的搜索结果，每条包含 `title`、`url`、`description`、`content` 字段。

### 搜索策略

1. **关键词优化**：将用户的自然语言查询转换为高效搜索关键词
   - 去掉口语化表达，保留核心概念
   - 中文话题可同时搜索中英文关键词以扩大覆盖面
2. **多轮搜索**：复杂话题拆分为多个子查询
3. **结果筛选**：优先选择权威来源（官方网站、知名媒体、学术机构）

## 输出规范

- 回答时标注信息来源（附链接）
- 区分「事实」和「推测/观点」
- 如果搜索结果不充分，告知用户并建议更精确的搜索方式
- 时效性信息标注日期
