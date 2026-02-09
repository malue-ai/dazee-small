"""
Web Scraper Skill - Powered by Crawl4AI

基于 Crawl4AI (59k+ GitHub Stars) 的高性能网页爬虫。
Playwright 浏览器引擎 + stealth 反爬 + 异步并发 + LLM 优化 Markdown。
完全免费开源 (Apache-2.0)。
"""

import asyncio
from typing import Any, Dict, List, Optional

from crawl4ai import (
    AsyncWebCrawler,
    BrowserConfig,
    CacheMode,
    CrawlerRunConfig,
)
from crawl4ai.content_filter_strategy import PruningContentFilter
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator

from logger import get_logger

logger = get_logger("web-scraper")

# ============================================================
# 默认配置
# ============================================================

# 浏览器配置 (反爬)
DEFAULT_BROWSER_CONFIG = BrowserConfig(
    headless=True,
    user_agent_mode="random",       # 随机 User-Agent
    ignore_https_errors=True,
    verbose=False,
)

# 爬取配置 (内容提取)
DEFAULT_CRAWLER_CONFIG = CrawlerRunConfig(
    cache_mode=CacheMode.BYPASS,    # 不缓存，获取最新内容
    page_timeout=30000,             # 页面超时 30 秒
    markdown_generator=DefaultMarkdownGenerator(
        content_filter=PruningContentFilter(
            threshold=0.4,
            threshold_type="fixed",
        )
    ),
)


class WebScraperSkill:
    """
    基于 Crawl4AI 的高性能网页爬虫

    特性:
    - Playwright 浏览器引擎 (真实渲染, 支持 JS)
    - stealth 模式 + 随机 UA (反爬)
    - 异步并发 + 内存自适应调度 (高性能)
    - PruningContentFilter 智能过滤 (高质量)
    - 自动 Markdown 输出 (LLM 友好)
    """

    def __init__(
        self,
        browser_config: Optional[BrowserConfig] = None,
        crawler_config: Optional[CrawlerRunConfig] = None,
    ):
        self.browser_config = browser_config or DEFAULT_BROWSER_CONFIG
        self.crawler_config = crawler_config or DEFAULT_CRAWLER_CONFIG

    async def fetch_url(
        self,
        url: str,
        use_fit_markdown: bool = True,
    ) -> Dict[str, Any]:
        """
        抓取单个 URL

        Args:
            url: 目标 URL
            use_fit_markdown: 是否使用过滤后的 Markdown (推荐 True)

        Returns:
            {
                "success": bool,
                "url": str,
                "content": str,       # Markdown 内容
                "raw_content": str,   # 原始 Markdown (未过滤)
                "text_length": int,
                "error": str          # 仅失败时
            }
        """
        try:
            async with AsyncWebCrawler(config=self.browser_config) as crawler:
                result = await crawler.arun(url=url, config=self.crawler_config)

                if not result.success:
                    logger.warning(f"⚠️ 抓取失败: {url} - {result.error_message}")
                    return {
                        "success": False,
                        "url": url,
                        "error": result.error_message or "抓取失败",
                    }

                # 提取 Markdown
                raw_md = result.markdown.raw_markdown if result.markdown else ""
                fit_md = result.markdown.fit_markdown if result.markdown else ""
                content = fit_md if (use_fit_markdown and fit_md) else raw_md

                if not content or len(content) < 50:
                    return {
                        "success": False,
                        "url": url,
                        "error": "无法提取有效内容(内容过短)",
                    }

                logger.info(f"✅ 成功: {url} ({len(content)} 字符)")
                return {
                    "success": True,
                    "url": url,
                    "content": content,
                    "raw_content": raw_md,
                    "text_length": len(content),
                }

        except Exception as e:
            logger.error(f"❌ 异常: {url} - {e}", exc_info=True)
            return {"success": False, "url": url, "error": str(e)}

    async def fetch_batch(
        self,
        urls: List[str],
        use_fit_markdown: bool = True,
        stream: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        并发抓取多个 URL (使用 Crawl4AI 内置的 MemoryAdaptiveDispatcher)

        Args:
            urls: URL 列表
            use_fit_markdown: 是否使用过滤后的 Markdown
            stream: 是否使用流式模式 (边爬边处理)

        Returns:
            结果列表
        """
        logger.info(f"📡 批量抓取: {len(urls)} 个 URL")

        output: List[Dict[str, Any]] = []

        try:
            async with AsyncWebCrawler(config=self.browser_config) as crawler:
                if stream:
                    # 流式模式: 边爬边收集
                    stream_config = self.crawler_config.clone(stream=True)
                    async for result in await crawler.arun_many(
                        urls, config=stream_config
                    ):
                        output.append(self._parse_result(result, use_fit_markdown))
                else:
                    # 批量模式: 等待全部完成
                    results = await crawler.arun_many(
                        urls, config=self.crawler_config
                    )
                    for result in results:
                        output.append(self._parse_result(result, use_fit_markdown))

        except Exception as e:
            logger.error(f"❌ 批量抓取异常: {e}", exc_info=True)
            # 对于未处理的 URL，标记为失败
            processed_urls = {r["url"] for r in output}
            for url in urls:
                if url not in processed_urls:
                    output.append({"success": False, "url": url, "error": str(e)})

        success_count = sum(1 for r in output if r.get("success"))
        logger.info(f"✅ 完成: {success_count}/{len(urls)} 成功")
        return output

    def _parse_result(self, result, use_fit_markdown: bool) -> Dict[str, Any]:
        """解析单个 CrawlResult"""
        if not result.success:
            return {
                "success": False,
                "url": result.url,
                "error": result.error_message or "抓取失败",
            }

        raw_md = result.markdown.raw_markdown if result.markdown else ""
        fit_md = result.markdown.fit_markdown if result.markdown else ""
        content = fit_md if (use_fit_markdown and fit_md) else raw_md

        if not content or len(content) < 50:
            return {
                "success": False,
                "url": result.url,
                "error": "内容过短或无法提取",
            }

        return {
            "success": True,
            "url": result.url,
            "content": content,
            "raw_content": raw_md,
            "text_length": len(content),
        }


# ============================================================
# Skill 执行入口
# ============================================================

async def execute(params: Dict[str, Any], context: Any) -> str:
    """
    Skill 执行入口

    参数:
        url: 单个 URL
        urls: URL 列表 (批量模式)
        use_fit_markdown: 是否使用过滤后的 Markdown (默认 true)

    返回:
        Markdown 格式的抓取结果
    """
    skill = WebScraperSkill()

    url = params.get("url")
    urls = params.get("urls")
    use_fit = params.get("use_fit_markdown", True)

    # 单个 URL
    if url and not urls:
        result = await skill.fetch_url(url, use_fit_markdown=use_fit)

        if not result.get("success"):
            return f"❌ 抓取失败: {result.get('error')}\n\nURL: {url}"

        return (
            f"**来源**: {url}\n"
            f"**长度**: {result['text_length']} 字符\n\n"
            f"---\n\n"
            f"{result['content']}"
        )

    # 批量 URL
    elif urls and isinstance(urls, list):
        results = await skill.fetch_batch(urls, use_fit_markdown=use_fit)

        success = [r for r in results if r.get("success")]
        failed = [r for r in results if not r.get("success")]

        report = f"# 批量抓取完成\n\n"
        report += f"- **成功**: {len(success)}/{len(urls)}\n"

        if failed:
            report += f"- **失败**: {len(failed)}\n\n"
            report += "## ❌ 失败\n\n"
            for r in failed[:5]:
                report += f"- {r['url']}: {r.get('error')}\n"
            report += "\n"

        report += "## ✅ 抓取内容\n\n"
        for i, r in enumerate(success, 1):
            excerpt = r["content"][:300].replace("\n", " ")
            report += (
                f"### {i}. {r['url']}\n\n"
                f"*({r['text_length']} 字符)*\n\n"
                f"{excerpt}...\n\n---\n\n"
            )

        return report

    else:
        return "❌ 参数错误: 必须提供 url 或 urls 参数"
