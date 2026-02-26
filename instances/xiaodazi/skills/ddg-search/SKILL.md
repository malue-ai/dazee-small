---
name: ddg-search
description: Search the web using DuckDuckGo. Privacy-friendly, no API key required.
metadata:
  xiaodazi:
    dependency_level: builtin
    os: [common]
    backend_type: local
    user_facing: true
---

# DuckDuckGo 网络搜索

通过 DuckDuckGo 搜索互联网，隐私友好，无需 API Key。

## 使用场景

- 用户说「帮我搜一下…」「查查…最新消息」
- 用户需要了解某个话题的最新信息
- 需要为其他任务（写作、调研）收集背景资料
- 用户问了一个需要实时信息的问题（天气之外的时事、产品价格等）

## 执行方式

通过 `web_search` 工具搜索 DuckDuckGo，获取搜索结果摘要。

### 基本搜索

```python
results = await web_search("搜索关键词")
```

### 搜索策略

1. **关键词优化**：将用户的自然语言查询转换为高效搜索关键词
   - 去掉口语化表达，保留核心概念
   - 中文话题可同时搜索中英文关键词以扩大覆盖面
2. **多轮搜索**：复杂话题拆分为多个子查询
3. **结果筛选**：优先选择权威来源（官方网站、知名媒体、学术机构）

### 搜索结果处理

```
对每条搜索结果，提取：
- title: 页面标题
- url: 链接
- snippet: 摘要片段

综合多条结果，给用户一个结构化的回答。
```

## 输出规范

- 回答时标注信息来源（附链接）
- 区分「事实」和「推测/观点」
- 如果搜索结果不充分，告知用户并建议更精确的搜索方式
- 时效性信息标注日期
