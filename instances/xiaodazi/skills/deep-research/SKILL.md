---
name: deep-research
description: Conduct multi-step autonomous research on any topic. Iteratively search, analyze, synthesize, and produce comprehensive research reports. Powered by Crawl4AI for high-speed content extraction.
metadata:
  xiaodazi:
    dependency_level: builtin
    os: [common]
    backend_type: local
    user_facing: true
---

# 深度调研

执行多步骤自主调研：市场分析、竞品研究、行业报告、文献综述。自动搜索、分析、综合，生成完整调研报告。

## 使用场景

- 用户说「帮我调研 AI 办公助手市场」「分析前 5 名竞品」
- 用户说「做一份行业趋势报告」「调研这个赛道的机会」
- 用户说「帮我深入研究这个话题，写一份完整报告」
- 用户说「收集整理过去一周AI行业的热点新闻资讯」

## 执行方式

使用 `web-scraper` (Crawl4AI) 快速获取完整网页内容，大幅缩短调研时间。

### 调研流程

```
Step 1: 理解调研目标
  ↓ 明确范围、深度、输出格式

Step 2: 制定调研计划
  ↓ 拆解为 3-5 个子课题

Step 3: 批量搜索 + 内容抓取 (核心)
  ↓ 3.1 web_search 获取相关 URL 列表 (10-20个)
  ↓ 3.2 web-scraper (Crawl4AI) 并发抓取完整内容
  ↓     Playwright 浏览器引擎 → 突破反爬
  ↓     PruningContentFilter → 去除噪声
  ↓     自动输出干净 Markdown

Step 4: 交叉验证
  ↓ 多个来源互相印证

Step 5: 综合分析
  ↓ 发现趋势、对比、洞察

Step 6: 生成报告
  ↓ 结构化输出
```

### 实现示例

```python
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, CacheMode
from crawl4ai.content_filter_strategy import PruningContentFilter
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator

# Step 1: 搜索获取 URL
search_queries = ["AI 办公助手 市场分析", "AI 办公助手 竞品对比"]

all_urls = []
for query in search_queries:
    results = await web_search(query)
    all_urls.extend([r["url"] for r in results[:5]])

unique_urls = list(set(all_urls))[:15]

# Step 2: Crawl4AI 并发抓取完整内容
config = CrawlerRunConfig(
    cache_mode=CacheMode.BYPASS,
    markdown_generator=DefaultMarkdownGenerator(
        content_filter=PruningContentFilter(threshold=0.4)
    ),
)

async with AsyncWebCrawler() as crawler:
    results = await crawler.arun_many(unique_urls, config=config)

# Step 3: 提取成功的文章
valid = [r for r in results if r.success]

# Step 4: 构建上下文给 LLM 分析
context = ""
for article in valid:
    content = article.markdown.fit_markdown or article.markdown.raw_markdown
    context += f"来源: {article.url}\n\n"
    context += f"{content[:2000]}\n\n---\n\n"

# Step 5: LLM 综合分析 (基于完整内容，质量远高于搜索摘要)
```

### 报告结构

```markdown
# [调研主题] 调研报告

**调研日期**: YYYY-MM-DD
**调研范围**: [描述]

## Executive Summary
[1-2 段核心发现]

## 1. 背景与现状
[行业/市场背景]

## 2. 主要发现
### 2.1 [子课题 1]
[详细分析]

### 2.2 [子课题 2]
[详细分析]

## 3. 对比分析
[表格对比、优劣势分析]

## 4. 趋势与预测
[基于数据的趋势判断]

## 5. 建议与行动项
[可执行的建议]

## 参考来源
[标注所有信息来源 URL]
```

### 调研质量标准

| 维度 | 要求 |
|---|---|
| 来源多样性 | 至少 5 个不同来源 |
| 时效性 | 优先最近 12 个月的数据 |
| 交叉验证 | 关键数据至少 2 个来源确认 |
| 客观性 | 呈现多方观点，不偏颇 |
| 可追溯 | 所有数据标注来源 |
| 内容完整性 | 基于完整文章（非搜索摘要） |

## 输出规范

- 报告长度根据主题复杂度自适应（1000-5000 字）
- 使用表格、对比矩阵增强可读性
- 所有数据标注来源链接
- 明确区分「事实」和「分析/推测」
- 报告末尾附信息来源列表
