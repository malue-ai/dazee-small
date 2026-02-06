"""
Partition API文档解析工具

功能说明：
- 本工具通过Unstructured Partition API解析各种格式的文档（PDF、Word、PPT等）
- 支持通过URL获取文档
- 自动选择最佳解析策略，也可手动指定
- 提供文档内容的结构化输出，便于大模型处理

注意：
- PyPDF2/python-docx/openpyxl 等库本身是同步的，无异步版本
- 使用 asyncio.to_thread() 将这些 CPU-bound 操作放到线程池
- 文件 I/O 使用 aiofiles 实现异步
"""

import asyncio
import hashlib
import json
import logging
import os
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import aiofiles
import aiofiles.os
import aiohttp

from core.tool.types import BaseTool, ToolContext

logger = logging.getLogger(__name__)


@dataclass
class PartitionConfig:
    """Partition API配置"""

    api_key: str
    api_url: str = "https://api.unstructuredapp.io/general/v0/general"
    timeout_download: int = 30
    timeout_api: int = 60
    max_retries: int = 3
    default_strategy: str = "auto"
    cache_enabled: bool = False
    cache_dir: str = "./cache/partition"
    recommended_size_mb: int = 20
    max_size_mb: int = 50
    chunk_size_mb: int = 10
    pages_batch_size: int = 5


class DocumentPartitionTool(BaseTool):
    """Partition API文档解析工具"""

    name = "document_partition_tool"

    def __init__(self, **kwargs):
        super().__init__()

        if "config" in kwargs and kwargs["config"]:
            self.config = kwargs["config"]
        else:
            api_key = os.getenv("UNSTRUCTURED_API_KEY", "")
            if not api_key:
                logger.warning("未配置 UNSTRUCTURED_API_KEY，工具将无法使用")

            self.config = PartitionConfig(
                api_key=api_key,
                api_url=os.getenv(
                    "UNSTRUCTURED_API_URL", "https://api.unstructuredapp.io/general/v0/general"
                ),
                cache_enabled=os.getenv("PARTITION_CACHE_ENABLED", "false").lower() == "true",
                cache_dir=os.getenv("PARTITION_CACHE_DIR", "./cache/partition"),
            )

        self.is_available = bool(self.config.api_key)
        self.event_manager = kwargs.get("event_manager")
        self.memory = kwargs.get("memory")
        self.workspace_dir = kwargs.get("workspace_dir")

        if self.config.cache_enabled:
            Path(self.config.cache_dir).mkdir(parents=True, exist_ok=True)

        self.RECOMMENDED_SIZE = self.config.recommended_size_mb * 1024 * 1024
        self.MAX_SIZE = self.config.max_size_mb * 1024 * 1024
        self.CHUNK_SIZE = self.config.chunk_size_mb * 1024 * 1024

    # ============================================================================
    # 文档信息获取（CPU-bound，使用线程池）
    # ============================================================================

    @staticmethod
    def _get_pdf_info(file_path: str) -> Dict[str, Any]:
        """同步获取 PDF 信息（在线程池中运行）"""
        try:
            import PyPDF2

            with open(file_path, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                total_pages = len(reader.pages)
                metadata = {}
                if reader.metadata:
                    metadata = {
                        "title": reader.metadata.get("/Title", ""),
                        "author": reader.metadata.get("/Author", ""),
                        "subject": reader.metadata.get("/Subject", ""),
                    }
                return {"total_pages": total_pages, "metadata": metadata}
        except Exception as e:
            logger.warning(f"获取 PDF 信息失败: {e}")
            return {}

    @staticmethod
    def _get_docx_info(file_path: str) -> Dict[str, Any]:
        """同步获取 Word 信息（在线程池中运行）"""
        try:
            from docx import Document

            doc = Document(file_path)
            paragraph_count = len([p for p in doc.paragraphs if p.text.strip()])
            total_pages = max(1, paragraph_count // 8)
            metadata = {}
            if doc.core_properties:
                metadata = {
                    "title": doc.core_properties.title or "",
                    "author": doc.core_properties.author or "",
                    "subject": doc.core_properties.subject or "",
                }
            return {"total_pages": total_pages, "metadata": metadata}
        except Exception as e:
            logger.warning(f"获取 Word 信息失败: {e}")
            return {}

    @staticmethod
    def _extract_pdf_pages(file_path: str, pages: str) -> Optional[str]:
        """同步提取 PDF 页码（在线程池中运行）"""
        try:
            import PyPDF2
            from PyPDF2 import PdfWriter

            start_page = int(pages.split("-")[0])
            end_page = int(pages.split("-")[1]) if "-" in pages else start_page

            reader = PyPDF2.PdfReader(file_path)
            writer = PdfWriter()

            for page_num in range(start_page - 1, end_page):
                writer.add_page(reader.pages[page_num])

            temp_file = file_path.replace(".pdf", f'_pages_{pages.replace("-", "_")}.pdf')
            with open(temp_file, "wb") as f:
                writer.write(f)

            return temp_file
        except Exception as e:
            logger.warning(f"PDF 页码提取失败: {e}")
            return None

    async def _get_document_info(self, temp_file: str) -> Dict[str, Any]:
        """
        异步获取文档信息

        说明：PyPDF2/python-docx 等库本身是同步的，使用 asyncio.to_thread 放到线程池
        """
        file_type = Path(temp_file).suffix.lower()
        file_size = await aiofiles.os.path.getsize(temp_file)

        result = {
            "total_pages": None,
            "file_size": file_size,
            "file_type": file_type,
            "metadata": {},
        }

        # PDF 文件
        if file_type == ".pdf":
            info = await asyncio.to_thread(self._get_pdf_info, temp_file)
            result.update(info)
            if result["total_pages"]:
                logger.info(f"📄 PDF 文档: 共 {result['total_pages']} 页")

        # Word 文档
        elif file_type in [".docx", ".doc"]:
            info = await asyncio.to_thread(self._get_docx_info, temp_file)
            result.update(info)
            if result["total_pages"]:
                logger.info(f"📄 Word 文档: 估算 {result['total_pages']} 页")

        # 图片文件
        elif file_type.lower() in {
            ".png",
            ".jpg",
            ".jpeg",
            ".gif",
            ".webp",
            ".bmp",
            ".tif",
            ".tiff",
        }:
            result["total_pages"] = 1
            logger.info("🖼️ 图片文件: 视为 1 页")

        # 其他格式暂不支持详细信息
        else:
            logger.info(f"📄 文档类型: {file_type}, 大小: {file_size / (1024 * 1024):.2f} MB")

        return result

    # ============================================================================
    # 网络 I/O（异步）
    # ============================================================================

    async def _get_file_size_from_url(self, url: str) -> Optional[int]:
        """异步获取文件大小"""
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.head(url, allow_redirects=True) as response:
                    if response.status == 200:
                        content_length = response.headers.get("Content-Length")
                        if content_length:
                            return int(content_length)
        except Exception as e:
            logger.warning(f"HEAD 请求失败: {e}")
        return None

    async def _download_url_file(self, url: str) -> str:
        """异步下载文件"""
        ext = self._get_file_extension_from_url(url)

        # 创建临时文件
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tf:
            temp_path = tf.name

        for attempt in range(self.config.max_retries):
            try:
                timeout = aiohttp.ClientTimeout(total=self.config.timeout_download * 2)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(url) as response:
                        response.raise_for_status()

                        # 异步写入文件
                        chunk_size = min(self.CHUNK_SIZE, 10 * 1024 * 1024)
                        async with aiofiles.open(temp_path, "wb") as f:
                            async for chunk in response.content.iter_chunked(chunk_size):
                                await f.write(chunk)

                        logger.info(f"✅ 下载成功: {temp_path}")
                        return temp_path
            except Exception as e:
                if attempt == self.config.max_retries - 1:
                    if await aiofiles.os.path.exists(temp_path):
                        await aiofiles.os.remove(temp_path)
                    raise
                logger.warning(f"下载失败，重试 {attempt + 1}: {e}")
                await asyncio.sleep(2**attempt)

        return temp_path

    async def _call_partition_api(
        self, file_path: str, strategy: str, user_id: str, pages: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """异步调用 Partition API"""
        temp_extracted_file = None

        # PDF 页码提取（使用线程池）
        if pages and file_path.lower().endswith(".pdf"):
            temp_extracted_file = await asyncio.to_thread(self._extract_pdf_pages, file_path, pages)
            if temp_extracted_file:
                file_path = temp_extracted_file
                pages = None

        try:
            for attempt in range(self.config.max_retries):
                try:
                    file_name = os.path.basename(file_path)
                    timeout_seconds = (
                        180 if strategy == "hi_res" else (120 if strategy == "auto" else 60)
                    )

                    # 准备表单数据
                    form_data = aiohttp.FormData()
                    form_data.add_field("strategy", strategy)
                    form_data.add_field("output_format", "application/json")

                    if pages:
                        start, *end = pages.split("-")
                        form_data.add_field("starting_page_number", start)
                        if end:
                            form_data.add_field("ending_page_number", end[0])

                    # 异步读取文件
                    async with aiofiles.open(file_path, "rb") as f:
                        file_content = await f.read()

                    form_data.add_field(
                        "files",
                        file_content,
                        filename=file_name,
                        content_type=self._get_mime_type(file_path),
                    )

                    headers = {
                        "unstructured-api-key": self.config.api_key,
                        "accept": "application/json",
                        "User-Agent": f"DocumentPartitionTool/1.0 (user:{user_id})",
                    }

                    timeout = aiohttp.ClientTimeout(total=timeout_seconds)
                    async with aiohttp.ClientSession(timeout=timeout) as session:
                        async with session.post(
                            self.config.api_url, data=form_data, headers=headers
                        ) as response:
                            if response.status == 200:
                                result = await response.json()
                                logger.info(f"API 调用成功，返回 {len(result)} 个元素")
                                return result
                            elif response.status == 429:
                                wait_time = 10 * (attempt + 1)
                                logger.warning(f"速率限制，等待 {wait_time}秒")
                                await asyncio.sleep(wait_time)
                                continue
                            elif response.status == 422:
                                error_text = await response.text()
                                if "fast strategy is not available for image files" in error_text:
                                    logger.warning("🖼️ 图片不支持 fast 策略，自动升级为 hi_res")
                                    strategy = "hi_res"
                                    continue
                                raise Exception(f"API 错误 422: {error_text[:200]}")
                            else:
                                error_text = await response.text()
                                raise Exception(f"API 错误 {response.status}: {error_text[:200]}")

                except asyncio.TimeoutError:
                    if attempt == self.config.max_retries - 1:
                        raise Exception(f"API 调用超时（{timeout_seconds}秒）")
                    logger.warning(f"超时，重试 {attempt + 1}")
                except Exception as e:
                    if attempt == self.config.max_retries - 1:
                        raise
                    logger.warning(f"API 调用失败，重试 {attempt + 1}: {e}")
                    await asyncio.sleep(2**attempt)

            raise Exception("API 调用失败，达到最大重试次数")

        finally:
            # 清理临时文件
            if temp_extracted_file and await aiofiles.os.path.exists(temp_extracted_file):
                try:
                    await aiofiles.os.remove(temp_extracted_file)
                except Exception as e:
                    logger.warning(f"清理临时文件失败: {e}")

    # ============================================================================
    # 批处理逻辑（统一处理）
    # ============================================================================

    async def _process_batch(
        self, temp_file: str, page_ranges: List[Tuple[int, int]], strategy: str, user_id: str
    ) -> Tuple[List[Dict], List[Dict]]:
        """统一的批处理逻辑"""
        batch_size = self.config.pages_batch_size
        all_elements = []
        details = []

        # 生成批次
        batches = []
        for start, end in page_ranges:
            count = end - start + 1
            if count > batch_size:
                # 大范围拆分成多个批次
                for i in range(0, count, batch_size):
                    batch_start = start + i
                    batch_end = min(start + i + batch_size - 1, end)
                    batches.append((batch_start, batch_end))
            else:
                batches.append((start, end))

        total_batches = len(batches)

        # 逐批处理
        for idx, (start, end) in enumerate(batches, 1):
            pages_str = f"{start}-{end}"
            logger.info(f"📦 批次 {idx}/{total_batches}: 第 {pages_str} 页")

            try:
                result = await self._call_partition_api(temp_file, strategy, user_id, pages_str)
                all_elements.extend(result)
                details.append(
                    {
                        "pages": pages_str,
                        "element_count": len(result),
                        "status": "success",
                        "batch_info": f"批次 {idx}/{total_batches}",
                    }
                )
                logger.info(f"   ✅ 成功: {len(result)} 个元素")
            except Exception as e:
                logger.error(f"   ❌ 失败: {e}")
                details.append(
                    {
                        "pages": pages_str,
                        "status": "failed",
                        "error": str(e),
                        "batch_info": f"批次 {idx}/{total_batches}",
                    }
                )

        return all_elements, details

    # ============================================================================
    # 缓存操作（异步文件 I/O）
    # ============================================================================

    async def _load_from_cache(self, cache_key: str) -> Optional[Dict]:
        """异步加载缓存"""
        if not self.config.cache_enabled:
            return None

        cache_file = Path(self.config.cache_dir) / f"{cache_key}.json"
        if not await aiofiles.os.path.exists(cache_file):
            return None

        try:
            async with aiofiles.open(cache_file, "r", encoding="utf-8") as f:
                content = await f.read()
                data = json.loads(content)

                # 检查缓存是否过期（24小时）
                cache_age = time.time() - data.get("metadata", {}).get("timestamp", 0)
                if cache_age < 24 * 3600:
                    data["cached"] = True
                    return data
        except Exception as e:
            logger.warning(f"读取缓存失败: {e}")

        return None

    async def _save_to_cache(self, cache_key: str, data: Dict):
        """异步保存缓存"""
        if not self.config.cache_enabled:
            return

        cache_file = Path(self.config.cache_dir) / f"{cache_key}.json"
        try:
            async with aiofiles.open(cache_file, "w", encoding="utf-8") as f:
                await f.write(json.dumps(data, ensure_ascii=False, indent=2))
        except Exception as e:
            logger.warning(f"保存缓存失败: {e}")

    # ============================================================================
    # 主执行入口
    # ============================================================================

    async def execute(self, params: Dict[str, Any], context: ToolContext) -> Dict[str, Any]:
        """执行文档解析"""
        source = params.get("source", "")
        mode = params.get("mode", "overview")
        pages_param = params.get("pages")
        strategy = params.get("strategy", self.config.default_strategy)
        use_cache = params.get("use_cache", True)

        user_id = context.user_id or "unknown"

        # 1. 基础验证
        if not self.is_available:
            return {"success": False, "error": "工具未配置 UNSTRUCTURED_API_KEY"}

        if not source or not source.startswith(("http://", "https://", "ftp://")):
            return {"success": False, "error": "source 必须是有效的 URL"}

        if mode not in ["overview", "pages", "full"]:
            return {"success": False, "error": f"无效的模式: {mode}"}

        if mode == "pages" and not pages_param:
            return {"success": False, "error": "mode='pages' 必须提供 pages 参数"}

        if strategy not in ["auto", "fast", "hi_res"]:
            return {"success": False, "error": f"无效的策略: {strategy}"}

        # 2. 缓存检查
        cache_key = None
        if use_cache and self.config.cache_enabled:
            cache_key = hashlib.md5(
                f"{source}_{mode}_{pages_param}_{strategy}".encode()
            ).hexdigest()
            cached = await self._load_from_cache(cache_key)
            if cached:
                logger.info(f"💾 使用缓存结果: {cache_key}")
                return cached

        temp_file = None
        start_time = time.time()

        try:
            # 3. 下载文件
            temp_file = await self._download_url_file(source)

            # 4. 获取文档信息
            doc_info = await self._get_document_info(temp_file)
            total_pages = doc_info.get("total_pages")
            file_size_mb = doc_info.get("file_size", 0) / (1024 * 1024)

            # 5. 确定处理范围
            if mode == "pages" and pages_param:
                page_ranges = self._parse_page_ranges(pages_param, total_pages)
            elif total_pages:
                page_ranges = [(1, total_pages)]
            else:
                page_ranges = []

            # 6. 执行解析
            if not page_ranges:
                # 未知页数，一次性解析
                all_elements = await self._call_partition_api(temp_file, strategy, user_id)
                details = [
                    {"pages": "all", "status": "success", "element_count": len(all_elements)}
                ]
            else:
                all_elements, details = await self._process_batch(
                    temp_file, page_ranges, strategy, user_id
                )

            # 7. 后处理
            result_data = {"elements": all_elements}
            if mode == "overview":
                result_data["outline"] = self._extract_outline(all_elements)
                result_data["summary"] = self._generate_summary(all_elements)

            # 8. 构建返回
            success_count = sum(1 for d in details if d["status"] == "success")
            response = {
                "success": True,
                "mode": mode,
                "message": f"解析完成，共 {len(all_elements)} 个元素",
                "data": result_data,
                "metadata": {
                    "source": source,
                    "total_pages": total_pages,
                    "file_size_mb": round(file_size_mb, 2),
                    "file_type": doc_info.get("file_type"),
                    "strategy": strategy,
                    "processing_time": round(time.time() - start_time, 2),
                    "batch_stats": f"{success_count}/{len(details)} success",
                    "details": details,
                },
            }

            # 9. 保存缓存
            if cache_key and response["success"]:
                await self._save_to_cache(cache_key, response)

            return response

        except Exception as e:
            logger.error(f"执行失败: {e}", exc_info=True)
            return {"success": False, "error": str(e), "message": "文档解析失败"}

        finally:
            # 清理临时文件
            if temp_file and await aiofiles.os.path.exists(temp_file):
                try:
                    await aiofiles.os.remove(temp_file)
                except Exception:
                    pass

    # ============================================================================
    # 辅助方法
    # ============================================================================

    def _parse_page_ranges(self, pages: str, total_pages: Optional[int]) -> List[Tuple[int, int]]:
        """解析页码范围"""
        ranges = []
        for part in pages.split(","):
            part = part.strip()
            if "-" in part:
                start, end = map(int, part.split("-"))
            else:
                start = end = int(part)

            if start < 1 or (total_pages and end > total_pages) or start > end:
                raise ValueError(f"无效的页码范围: {part}")

            ranges.append((start, end))
        return ranges

    def _extract_outline(self, elements: List[Dict]) -> List[Dict]:
        """提取文档大纲"""
        outline = []
        for elem in elements:
            if elem.get("type") in ["Title", "Header"]:
                text = elem.get("text", "").strip()
                level = 1 if elem.get("type") == "Title" else 2
                page = elem.get("metadata", {}).get("page_number")
                outline.append({"title": text[:100], "level": level, "page": page})
        return outline

    def _generate_summary(self, elements: List[Dict]) -> str:
        """生成文档摘要"""
        texts = [
            e.get("text", "").strip()
            for e in elements[:50]
            if e.get("type") in ["Title", "NarrativeText", "Header"] and e.get("text")
        ]
        summary = " ".join(texts)
        return summary[:500] + "..." if len(summary) > 500 else summary

    def _get_mime_type(self, file_path: str) -> str:
        """获取 MIME 类型"""
        ext = Path(file_path).suffix.lower()
        mime_map = {
            ".pdf": "application/pdf",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".doc": "application/msword",
            ".txt": "text/plain",
            ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            ".ppt": "application/vnd.ms-powerpoint",
            ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ".xls": "application/vnd.ms-excel",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
        }
        return mime_map.get(ext, "application/octet-stream")

    def _get_file_extension_from_url(self, url: str) -> str:
        """从 URL 获取文件扩展名"""
        import re

        patterns = {
            r"\.pdf($|\?|#)": ".pdf",
            r"\.docx($|\?|#)": ".docx",
            r"\.doc($|\?|#)": ".doc",
            r"\.txt($|\?|#)": ".txt",
            r"\.pptx($|\?|#)": ".pptx",
            r"\.ppt($|\?|#)": ".ppt",
            r"\.xlsx($|\?|#)": ".xlsx",
            r"\.xls($|\?|#)": ".xls",
            r"\.png($|\?|#)": ".png",
            r"\.jpe?g($|\?|#)": ".jpg",
        }
        for pattern, ext in patterns.items():
            if re.search(pattern, url, re.IGNORECASE):
                return ext
        return ".tmp"


# 工厂函数
def create_document_partition_tool(**kwargs) -> DocumentPartitionTool:
    """创建文档解析工具实例"""
    return DocumentPartitionTool(**kwargs)


# 尝试创建默认实例
try:
    document_partition_tool = DocumentPartitionTool()
    if not document_partition_tool.is_available:
        logger.info("DocumentPartitionTool 已加载，但需要配置 UNSTRUCTURED_API_KEY 才能使用")
except Exception as e:
    logger.warning(f"无法创建默认工具实例: {e}")
    document_partition_tool = None
