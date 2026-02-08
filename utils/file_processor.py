"""
文件处理器 - File Processor（本地 + URL 双模式，无数据库）

职责：
1. 根据 file_url 处理文件（支持本地路径和远程 URL）
2. 根据 MIME 类型分类处理
3. 生成 LLM 可用的 content blocks

处理策略：
- 图片 (image/*) → 本地文件使用 base64 / 远程使用 URL → ImageBlock
- 纯文本 (text/plain, text/markdown) → 读取内容 → 拼进消息
- 复杂文件 (PDF 等) → 提供路径/URL → 拼进消息，让 Agent 决定
"""

import base64
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import aiofiles
import httpx

from logger import get_logger
from utils.app_paths import get_storage_dir

logger = get_logger("file_processor")


class FileCategory(Enum):
    """文件分类"""

    IMAGE = "image"  # 图片：直接传给 LLM
    TEXT = "text"  # 纯文本：读取内容拼进消息
    DOCUMENT = "document"  # 复杂文档：提供 URL，让 Agent 决定


@dataclass
class ProcessedFile:
    """处理后的文件"""

    category: FileCategory
    filename: str
    mime_type: str
    # 根据 category 不同，以下字段有不同含义
    content_block: Optional[Dict[str, Any]] = None  # category=IMAGE 时使用
    text_content: Optional[str] = None  # category=TEXT 时使用
    file_url: Optional[str] = None  # 文件 URL
    file_size: Optional[int] = None  # 文件大小（字节）


class FileProcessorError(Exception):
    """文件处理器异常"""

    pass


class FileProcessor:
    """
    文件处理器（本地 + URL 双模式）

    支持两种文件来源：
    - 本地文件：URL 以 /api/v1/files/ 开头，从本地存储目录读取
    - 远程文件：HTTP(S) URL，通过网络下载

    使用方法：
        processor = FileProcessor()
        processed_files = await processor.process_files(files)
        content_blocks = processor.build_message_content(processed_files, user_message)
    """

    # 本地文件 URL 前缀
    LOCAL_FILE_PREFIX = "/api/v1/files/"

    # 图片 MIME 类型
    IMAGE_MIME_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}

    # 纯文本 MIME 类型
    TEXT_MIME_TYPES = {
        "text/plain",
        "text/markdown",
        "text/csv",
        "text/html",
        "application/json",
        "application/xml",
    }

    # 最大文本大小（50KB）
    MAX_TEXT_SIZE = 50 * 1024

    # 预览文本最大字符数
    MAX_PREVIEW_CHARS = 200

    def _is_local_file(self, url: str) -> bool:
        """Check if the URL points to a local file."""
        return url.startswith(self.LOCAL_FILE_PREFIX)

    def _resolve_local_path(self, url: str) -> Path:
        """
        Resolve a local file URL to an absolute filesystem path.

        /api/v1/files/uploads/20260208/abc_test.txt
        -> {storage_dir}/uploads/20260208/abc_test.txt
        """
        relative_path = url[len(self.LOCAL_FILE_PREFIX):]
        return get_storage_dir() / relative_path

    async def _read_local_file(self, local_path: Path) -> bytes:
        """Read file content from local filesystem."""
        if not local_path.exists():
            raise FileProcessorError(f"本地文件不存在: {local_path}")
        async with aiofiles.open(local_path, "rb") as f:
            return await f.read()

    async def process_files(self, files: List[Dict[str, Any]]) -> List[ProcessedFile]:
        """
        处理文件列表

        Args:
            files: 文件引用列表，每个元素包含 file_url + 元数据

        Returns:
            处理后的文件列表
        """
        processed = []

        for file_ref in files:
            try:
                file_url = file_ref.get("file_url")

                if not file_url:
                    logger.warning("文件引用无效：缺少 file_url")
                    continue

                # 从文件引用中获取元数据（前端已传递）
                file_name = file_ref.get("file_name") or file_ref.get("filename")
                file_type = file_ref.get("file_type") or file_ref.get("mime_type")
                file_size = file_ref.get("file_size")

                result = await self._process_by_url(
                    url=file_url, filename=file_name, mime_type=file_type, file_size=file_size
                )

                if result:
                    processed.append(result)

            except Exception as e:
                logger.error(f"处理文件失败: {str(e)}", exc_info=True)
                # 继续处理其他文件，不要因为一个失败就全部失败
                continue

        return processed

    async def _process_by_url(
        self,
        url: str,
        filename: Optional[str] = None,
        mime_type: Optional[str] = None,
        file_size: Optional[int] = None,
    ) -> Optional[ProcessedFile]:
        """
        Process a file by URL (supports both local and remote).

        For local files (/api/v1/files/...), reads directly from filesystem.
        For remote files (http/https), downloads via HTTP.

        Args:
            url: File URL (local path or remote URL).
            filename: Filename (optional, from frontend).
            mime_type: MIME type (optional, from frontend).
            file_size: File size in bytes (optional, from frontend).
        """
        is_local = self._is_local_file(url)

        # Resolve metadata
        if is_local:
            local_path = self._resolve_local_path(url)
            if not filename:
                filename = local_path.name
            if not mime_type:
                mime_type = self._guess_mime_type_from_filename(filename)
            if not file_size and local_path.exists():
                file_size = local_path.stat().st_size
        else:
            if not mime_type or not filename:
                detected_mime, detected_size, detected_name = await self._get_url_file_info(url)
                mime_type = mime_type or detected_mime
                file_size = file_size or detected_size
                filename = filename or detected_name

        logger.info(
            f"📎 处理文件: {filename}, MIME={mime_type}, "
            f"size={file_size}, local={is_local}"
        )

        # Categorize by MIME type
        category = self._categorize_mime_type(mime_type)

        if category == FileCategory.IMAGE:
            if is_local:
                # Local image: use base64 encoding for LLM
                try:
                    content = await self._read_local_file(self._resolve_local_path(url))
                    b64_data = base64.standard_b64encode(content).decode("utf-8")
                    content_block = {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": mime_type,
                            "data": b64_data,
                        },
                    }
                    logger.info(f"🖼️ 本地图片使用 base64: {filename}")
                except Exception as e:
                    logger.warning(f"读取本地图片失败: {e}, 降级为文档")
                    return ProcessedFile(
                        category=FileCategory.DOCUMENT,
                        filename=filename,
                        mime_type=mime_type,
                        file_url=url,
                        file_size=file_size,
                    )
            else:
                # Remote image: use URL directly (Claude supports URL mode)
                content_block = {"type": "image", "source": {"type": "url", "url": url}}
                logger.info(f"🖼️ 远程图片使用 URL: {filename}")

            return ProcessedFile(
                category=category,
                filename=filename,
                mime_type=mime_type,
                content_block=content_block,
                file_size=file_size,
                file_url=url,
            )

        if category == FileCategory.TEXT:
            # Text files: read content
            if file_size and file_size > self.MAX_TEXT_SIZE:
                logger.warning(f"文本过大，降级为文档处理: {file_size} bytes")
                category = FileCategory.DOCUMENT
            else:
                try:
                    content = await self._read_file_content(url)
                    # Try multiple encodings
                    try:
                        text_content = content.decode("utf-8-sig")
                    except UnicodeDecodeError:
                        try:
                            text_content = content.decode("gb18030")
                        except UnicodeDecodeError:
                            text_content = content.decode("utf-8", errors="replace")

                    return ProcessedFile(
                        category=category,
                        filename=filename,
                        mime_type=mime_type,
                        text_content=text_content,
                        file_size=file_size,
                        file_url=url,
                    )
                except Exception as e:
                    logger.warning(f"读取文本失败，降级为文档处理: {str(e)}")
                    category = FileCategory.DOCUMENT

        # Document: provide URL/path reference
        return ProcessedFile(
            category=FileCategory.DOCUMENT,
            filename=filename,
            mime_type=mime_type,
            file_url=url,
            file_size=file_size,
        )

    def _categorize_mime_type(self, mime_type: str) -> FileCategory:
        """根据 MIME 类型分类"""
        if mime_type in self.IMAGE_MIME_TYPES:
            return FileCategory.IMAGE
        if mime_type in self.TEXT_MIME_TYPES:
            return FileCategory.TEXT
        # 其他都当作复杂文档
        return FileCategory.DOCUMENT

    async def _read_file_content(self, url: str) -> bytes:
        """
        Read file content from local path or remote URL.

        Automatically routes to local read or HTTP download.
        """
        if self._is_local_file(url):
            local_path = self._resolve_local_path(url)
            return await self._read_local_file(local_path)
        return await self._download_from_url(url)

    async def _download_from_url(self, url: str) -> bytes:
        """Download file content from a remote URL."""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url)
                response.raise_for_status()
                content = response.content

                logger.debug(f"从 URL 下载: {len(content)} bytes")
                return content

        except httpx.HTTPError as e:
            logger.error(f"HTTP 下载失败: {str(e)}")
            raise FileProcessorError(f"下载文件失败: {str(e)}") from e

    async def _get_url_file_info(self, url: str) -> Tuple[str, Optional[int], str]:
        """
        获取 URL 文件信息

        Returns:
            (mime_type, file_size, filename)
        """
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.head(url, follow_redirects=True)

                # 获取 MIME 类型
                content_type = response.headers.get("content-type", "application/octet-stream")
                mime_type = content_type.split(";")[0].strip()

                # 获取文件大小
                content_length = response.headers.get("content-length")
                file_size = int(content_length) if content_length else None

                # 从 URL 提取文件名
                filename = url.split("/")[-1].split("?")[0] or "unknown"

                return mime_type, file_size, filename

        except Exception as e:
            logger.warning(f"获取文件信息失败，使用默认值: {str(e)}")
            # 从 URL 猜测
            filename = url.split("/")[-1].split("?")[0] or "unknown"
            mime_type = self._guess_mime_type_from_filename(filename)
            return mime_type, None, filename

    def _guess_mime_type_from_filename(self, filename: str) -> str:
        """从文件名猜测 MIME 类型"""
        ext_to_mime = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".webp": "image/webp",
            ".pdf": "application/pdf",
            ".txt": "text/plain",
            ".md": "text/markdown",
            ".csv": "text/csv",
            ".json": "application/json",
            ".xml": "application/xml",
            ".html": "text/html",
        }

        ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        return ext_to_mime.get(ext, "application/octet-stream")

    def _format_file_size(self, size_bytes: int) -> str:
        """
        格式化文件大小为可读字符串

        Args:
            size_bytes: 文件大小（字节）

        Returns:
            格式化后的字符串，如 "1.5 KB", "2.3 MB"
        """
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"

    def build_message_content(
        self, processed_files: List[ProcessedFile], user_message: str
    ) -> List[Dict[str, Any]]:
        """
        构建最终的 message content blocks

        Args:
            processed_files: 处理后的文件列表
            user_message: 用户原始消息

        Returns:
            content blocks 列表，可直接传给 LLM
        """
        content_blocks = []
        attachment_texts = []

        for pf in processed_files:
            if pf.category == FileCategory.IMAGE:
                # 图片：直接作为 content block
                if pf.content_block:
                    content_blocks.append(pf.content_block)

                # 同时也把 URL 放到文本里，方便 Tool 调用（如视频生成工具需要 URL）
                if pf.file_url:
                    attachment_texts.append(f"🖼️ {pf.filename} ({pf.mime_type}): {pf.file_url}")

            elif pf.category == FileCategory.TEXT:
                # 纯文本：拼进附件说明，同时保留原始元数据
                if pf.text_content:
                    # 构建元数据行（文件名 | MIME类型 | 大小）
                    meta_parts = [pf.filename]
                    if pf.mime_type:
                        meta_parts.append(pf.mime_type)
                    if pf.file_size:
                        # 格式化文件大小
                        size_str = self._format_file_size(pf.file_size)
                        meta_parts.append(size_str)
                    meta_line = " | ".join(meta_parts)

                    # 构建附件文本
                    content_preview = pf.text_content
                    if len(content_preview) > self.MAX_PREVIEW_CHARS:
                        content_preview = (
                            content_preview[: self.MAX_PREVIEW_CHARS] + "\n... (内容过长已截断)"
                        )

                    attachment_text = f"📄 {meta_line}:\n```\n{content_preview}\n```"

                    # 保留原始 URL（如果有）
                    if pf.file_url:
                        attachment_text += f"\n   原始文件: {pf.file_url}"

                    attachment_texts.append(attachment_text)

            elif pf.category == FileCategory.DOCUMENT:
                # 复杂文档：提供 URL，让 Agent 决定
                if pf.file_url:
                    attachment_texts.append(f"📎 {pf.filename} ({pf.mime_type}): {pf.file_url}")

        # 构建最终的文本消息
        final_text = user_message
        if attachment_texts:
            attachments_section = "\n\n---\n📎 附件:\n" + "\n\n".join(attachment_texts)
            final_text = user_message + attachments_section

        # 添加文本 block
        content_blocks.append({"type": "text", "text": final_text})

        return content_blocks


# ==================== 便捷函数 ====================

_default_processor: Optional[FileProcessor] = None


def get_file_processor() -> FileProcessor:
    """获取默认文件处理器单例"""
    global _default_processor
    if _default_processor is None:
        _default_processor = FileProcessor()
    return _default_processor
