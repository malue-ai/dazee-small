---
name: web-scraper
description: High-performance web scraping powered by Crawl4AI (59k+ GitHub Stars). Playwright-based anti-detection, async concurrent crawling, LLM-optimized Markdown output. Completely free & open-source.
quickstart: |
  # 安装: pip install crawl4ai && crawl4ai-setup
  # 单个URL:
  from crawl4ai import AsyncWebCrawler
  async with AsyncWebCrawler() as crawler:
      result = await crawler.arun("https://example.com")
      print(result.markdown.raw_markdown)
  # 批量并发:
  from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, CacheMode
  config = CrawlerRunConfig(cache_mode=CacheMode.BYPASS)
  async with AsyncWebCrawler() as crawler:
      results = await crawler.arun_many(urls, config=config)
      for r in results:
          if r.success: print(r.url, len(r.markdown.raw_markdown))
metadata:
  xiaodazi:
    dependency_level: lightweight
    os: [common]
    backend_type: local
    user_facing: true
---

# Web Scraper (Crawl4AI)

基于 **Crawl4AI** 的高性能网页爬虫。Crawl4AI 是 2025 年 GitHub #1 Trending 项目（59k+ Stars），专为 AI Agent 和 LLM 设计。

## 核心优势

| 特性 | 说明 |
|---|---|
| 🏆 **业界标杆** | 59k+ GitHub Stars，Apache-2.0 开源 |
| 💰 **完全免费** | 无需任何 API Key |
| 🛡️ **强反爬** | Playwright 浏览器引擎 + stealth 模式 + 随机 UA |
| 🚀 **极速** | 异步并发 + 内存自适应调度，比替代方案快 6x |
| 🎯 **LLM 优化** | 自动输出干净 Markdown，适合 RAG 和 LLM 消费 |
| 📄 **动态页面** | 支持 JavaScript 渲染、无限滚动、SPA |
| 🔧 **智能提取** | PruningContentFilter 自动去除噪声内容 |

## 使用场景

- 用户说「帮我读取这篇文章」「抓取这个网页」
- 用户说「收集最近的新闻」「整理行业资讯」
- 批量抓取搜索结果中的网页完整内容
- 作为 `deep-research` 的内容获取层

## 技术栈

```
Crawl4AI v0.8.x
├── Playwright (Chromium 浏览器引擎)
├── AsyncWebCrawler (异步并发)
├── PruningContentFilter (智能内容过滤)
├── DefaultMarkdownGenerator (Markdown 生成)
└── MemoryAdaptiveDispatcher (内存自适应调度)
```

## 快速开始

### 单个 URL

```python
from crawl4ai import AsyncWebCrawler

async with AsyncWebCrawler() as crawler:
    result = await crawler.arun("https://example.com")
    print(result.markdown)  # 干净的 Markdown
```

### 批量并发

```python
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, CacheMode

urls = [
    "https://36kr.com/article1",
    "https://techcrunch.com/article2",
    "https://theverge.com/article3",
]

config = CrawlerRunConfig(cache_mode=CacheMode.BYPASS)

async with AsyncWebCrawler() as crawler:
    results = await crawler.arun_many(urls, config=config)
    for result in results:
        if result.success:
            print(f"✅ {result.url}: {len(result.markdown.raw_markdown)} chars")
```

### 智能内容过滤

```python
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig
from crawl4ai.content_filter_strategy import PruningContentFilter
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator

config = CrawlerRunConfig(
    cache_mode=CacheMode.BYPASS,
    markdown_generator=DefaultMarkdownGenerator(
        content_filter=PruningContentFilter(threshold=0.4, threshold_type="fixed")
    ),
)

async with AsyncWebCrawler() as crawler:
    result = await crawler.arun("https://news.ycombinator.com", config=config)
    print(result.markdown.fit_markdown)  # 过滤后的高质量内容
```

## 反爬能力

Crawl4AI 内置多层反爬机制:

| 层级 | 机制 | 说明 |
|---|---|---|
| 浏览器 | Playwright Chromium | 真实浏览器渲染，不是 HTTP 请求 |
| User-Agent | `user_agent_mode="random"` | 每次随机 UA |
| Stealth | 内置 stealth 模式 | 隐藏自动化特征 |
| 代理 | `proxy` 参数 | 支持代理池 |
| JavaScript | 完整 JS 渲染 | 支持动态加载页面 |
| Cookies | Session 管理 | 支持登录态保持 |

### 配置反爬

```python
from crawl4ai import BrowserConfig

browser_config = BrowserConfig(
    headless=True,
    user_agent_mode="random",      # 随机 UA
    ignore_https_errors=True,
)
```

## 并发性能

Crawl4AI 使用 `MemoryAdaptiveDispatcher` 根据系统资源自动调整并发:

```python
# 批量抓取 - 自动调整并发度
results = await crawler.arun_many(urls, config=config)

# 流式处理 - 边爬边处理
config = CrawlerRunConfig(stream=True, cache_mode=CacheMode.BYPASS)
async for result in await crawler.arun_many(urls, config=config):
    if result.success:
        process(result)
```

## 输出格式

### Markdown (默认)

```markdown
# Article Title

Published on 2024-01-15 by John Doe

Main content paragraph 1...

## Section Heading

Content with **bold** and [links](https://example.com).

| Column 1 | Column 2 |
|---|---|
| Data | Data |
```

### 输出字段

```python
result.markdown.raw_markdown    # 原始 Markdown
result.markdown.fit_markdown    # 过滤后的 Markdown (需配置 content_filter)
result.extracted_content        # 结构化提取结果 (需配置 extraction_strategy)
result.success                  # 是否成功
result.url                      # 原始 URL
result.error_message            # 错误信息
```

## 典型场景

### 场景 1: 收集一周新闻

```python
# Step 1: 通过 api_calling 调用 Jina Search 获取 URL（参考 ddg-search skill）
results = await api_calling(url="https://s.jina.ai/AI行业新闻 最近一周", method="GET", headers={"Accept": "application/json"})
urls = [r["url"] for r in results]

# Step 2: Crawl4AI 并发抓取 (10个URL约5-10秒)
config = CrawlerRunConfig(
    cache_mode=CacheMode.BYPASS,
    markdown_generator=DefaultMarkdownGenerator(
        content_filter=PruningContentFilter(threshold=0.4)
    ),
)
async with AsyncWebCrawler() as crawler:
    results = await crawler.arun_many(urls, config=config)

# Step 3: 提取成功的文章
articles = [r for r in results if r.success]
for article in articles:
    content = article.markdown.fit_markdown  # 过滤后的干净内容
```

### 场景 2: 处理动态页面 (SPA)

```python
config = CrawlerRunConfig(
    cache_mode=CacheMode.BYPASS,
    wait_until="networkidle",         # 等待网络空闲
    delay_before_return_html=1.0,     # 额外等待 JS 渲染
    scan_full_page=True,              # 滚动到底部
)
```

## CLI 用法

Crawl4AI 还提供 CLI 工具 `crwl`:

```bash
# 基本爬取
crwl https://example.com -o markdown

# 带内容过滤
crwl https://example.com -o markdown-fit

# JSON 输出 + 详细日志
crwl https://example.com -o json -v --bypass-cache
```

## 安装

```bash
pip install crawl4ai
crawl4ai-setup  # 安装 Playwright 浏览器依赖
```

配置为 `auto_install: true`，首次使用自动安装 Python 包。`crawl4ai-setup` 需手动运行一次安装浏览器。

## 对比其他方案

| 方案 | Stars | 反爬 | 动态页面 | 速度 | 成本 |
|---|---|---|---|---|---|
| **Crawl4AI** | **59k** | **Playwright+Stealth** | **✅** | **6x 最快** | **免费** |
| Firecrawl | 77k | 云端浏览器 | ✅ | 快 | 付费 ($83/月) |
| httpx+BS4 | - | ❌ 无 | ❌ | 中等 | 免费 |
| Jina Reader | - | 云端 | ✅ | 快 | 免费额度 |
| Scrapy | 54k | 需插件 | ❌ | 快 | 免费 |

## 最佳实践

### ✅ 推荐

- 新闻网站、博客、技术文章、文档
- 动态加载页面 (React/Vue/SPA)
- 反爬严格的网站
- 批量抓取搜索结果
- 需要完整 JavaScript 渲染的页面

### 配置建议

```python
# 新闻/博客 (轻量)
config = CrawlerRunConfig(cache_mode=CacheMode.BYPASS)

# 重度反爬网站
browser_config = BrowserConfig(
    headless=True,
    user_agent_mode="random",
)

# SPA / 动态页面
config = CrawlerRunConfig(
    wait_until="networkidle",
    scan_full_page=True,
    delay_before_return_html=1.0,
)
```

## 参考资源

- GitHub: https://github.com/unclecode/crawl4ai (59k+ Stars)
- 文档: https://docs.crawl4ai.com/
- 许可证: Apache-2.0 (完全免费商用)
