---
name: brave-search
description: High-quality web search and content extraction via Brave Search API. Requires BRAVE_API_KEY.
metadata:
  xiaodazi:
    dependency_level: cloud_api
    os: [common]
    backend_type: local
    user_facing: true
---

# Brave 搜索

通过 Brave Search API 进行高质量网络搜索，支持内容提取和摘要。

## 使用场景

- 用户需要高质量的搜索结果（比 DuckDuckGo 更精确）
- 需要获取网页完整内容（而不仅是摘要）
- 深度调研、市场分析等需要可靠信息源的场景

## 前置条件

需要设置环境变量 `BRAVE_API_KEY`：
1. 访问 https://brave.com/search/api/ 注册获取 API Key
2. 设置环境变量：`export BRAVE_API_KEY="your-key"`

## 执行方式

### 搜索 API

```bash
curl -s "https://api.search.brave.com/res/v1/web/search?q=查询内容&count=10" \
  -H "Accept: application/json" \
  -H "X-Subscription-Token: $BRAVE_API_KEY"
```

### 响应解析

```python
import json

response = json.loads(result)
web_results = response.get("web", {}).get("results", [])

for item in web_results:
    title = item["title"]
    url = item["url"]
    description = item["description"]
    # 可选：item.get("extra_snippets") 提供更多上下文
```

### 搜索技巧

- 使用 `count` 参数控制结果数量（默认 10，最大 20）
- 使用 `freshness` 参数过滤时效：`pd`(24h), `pw`(周), `pm`(月), `py`(年)
- 使用 `search_lang` 指定语言：`zh-hans`(中文), `en`(英文)

## 输出规范

- 标注所有信息来源 URL
- 搜索结果以结构化格式呈现
- 提供信息时效性说明
