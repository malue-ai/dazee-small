---
name: tavily
description: AI-optimized web search via Tavily API. Returns clean, structured results ideal for LLM consumption.
metadata:
  xiaodazi:
    dependency_level: cloud_api
    os: [common]
    backend_type: local
    user_facing: true
---

# Tavily AI 搜索

专为 AI Agent 优化的搜索 API，返回干净、结构化的结果，适合 LLM 直接消费。

## 使用场景

- 需要高质量搜索结果用于调研、写作等复杂任务
- ddg-search 结果不够精确时的升级选项
- deep-research 流程中的搜索后端

## 前置条件

需要设置环境变量 `TAVILY_API_KEY`：
1. 访问 https://tavily.com/ 注册（免费套餐每月 1000 次）
2. 设置：`export TAVILY_API_KEY="tvly-xxxxx"`

## 执行方式

### 基本搜索

```bash
curl -s -X POST "https://api.tavily.com/search" \
  -H "Content-Type: application/json" \
  -d '{
    "api_key": "'$TAVILY_API_KEY'",
    "query": "搜索内容",
    "search_depth": "basic",
    "max_results": 5
  }'
```

### 深度搜索

```bash
curl -s -X POST "https://api.tavily.com/search" \
  -H "Content-Type: application/json" \
  -d '{
    "api_key": "'$TAVILY_API_KEY'",
    "query": "搜索内容",
    "search_depth": "advanced",
    "max_results": 10,
    "include_raw_content": true
  }'
```

### Python SDK

```python
from tavily import TavilyClient

client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])

response = client.search(
    query="AI agent 市场分析 2026",
    search_depth="advanced",
    max_results=10,
)

for result in response["results"]:
    print(f"Title: {result['title']}")
    print(f"URL: {result['url']}")
    print(f"Content: {result['content'][:200]}")
    print("---")
```

### 参数说明

| 参数 | 值 | 说明 |
|---|---|---|
| `search_depth` | `basic` / `advanced` | basic 快但浅，advanced 慢但全 |
| `max_results` | 1-20 | 返回结果数量 |
| `include_raw_content` | bool | 是否返回网页原始内容 |
| `include_domains` | list | 限定搜索域名 |
| `exclude_domains` | list | 排除域名 |

## 输出规范

- 搜索结果标注来源 URL 和相关度分数
- advanced 搜索用于深度调研，basic 用于快速查询
- 免费额度有限，简单查询优先用 ddg-search
