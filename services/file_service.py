"""
File 服务层 - 文件上传服务（本地存储）

职责：
1. 保存上传的文件到本地磁盘
2. 返回可访问的本地路径
3. MIME 类型检测

设计原则：
- 桌面端直接保存到本地 data/ 目录
- 返回绝对路径，Agent 工具可直接读取
- 无需数据库存储文件元数据
"""

import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import aiofiles
import filetype

from logger import get_logger

logger = get_logger("file_service")

# 本地存储根目录（项目 data/ 下）
_DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def detect_mime_type(file_content: bytes, filename: str) -> str:
    """
    Detect real MIME type from file header.

    Args:
        file_content: Raw file bytes.
        filename: Original filename.

    Returns:
        MIME type string.
    """
    kind = filetype.guess(file_content)

    if kind is not None:
        mime = kind.mime
        logger.debug(f"检测 MIME: {filename} -> {mime}")
        return mime

    fallback_mime = _get_mime_from_extension(filename)
    logger.debug(f"检测 MIME（后备）: {filename} -> {fallback_mime}")
    return fallback_mime


def _get_mime_from_extension(filename: str) -> str:
    """Fallback MIME detection by file extension."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    mime_map = {
        "txt": "text/plain",
        "pdf": "application/pdf",
        "json": "application/json",
        "xml": "application/xml",
        "html": "text/html",
        "css": "text/css",
        "js": "application/javascript",
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "gif": "image/gif",
        "webp": "image/webp",
        "svg": "image/svg+xml",
        "mp4": "video/mp4",
        "mp3": "audio/mpeg",
        "zip": "application/zip",
        "gz": "application/gzip",
        "md": "text/markdown",
        "csv": "text/csv",
    }

    return mime_map.get(ext, "application/octet-stream")


class FileServiceError(Exception):
    """File service exception."""

    pass


class FileService:
    """
    File service (local storage for desktop).

    Saves uploaded files to data/chat-attachments/ and returns
    absolute local paths that Agent tools can directly access.
    """

    def __init__(self) -> None:
        """Initialize file service with local storage root."""
        self._base_dir = _DATA_DIR / "chat-attachments"

    async def upload_file(
        self, file_content: bytes, filename: str, mime_type: str, user_id: str
    ) -> Dict[str, Any]:
        """
        Save uploaded file to local disk.

        Args:
            file_content: Raw file bytes.
            filename: Original filename.
            mime_type: MIME type from frontend (re-validated by backend).
            user_id: User ID for directory isolation.

        Returns:
            { "file_url", "file_name", "file_size", "file_type" }
        """
        file_size = len(file_content)

        # Verify MIME
        detected_mime = detect_mime_type(file_content, filename)
        logger.info(f"MIME 验证: 前端={mime_type}, 后端={detected_mime}")

        # Build storage path: chat-attachments/{user_id}/{date}/{uuid}_{filename}
        date_str = datetime.now().strftime("%Y%m%d")
        unique_id = str(uuid.uuid4())
        safe_filename = "".join(c for c in filename if c.isalnum() or c in "._-")
        rel_path = Path(user_id) / date_str / f"{unique_id}_{safe_filename}"
        abs_path = self._base_dir / rel_path

        try:
            # Ensure parent directory exists
            abs_path.parent.mkdir(parents=True, exist_ok=True)

            # Write file content to disk (async)
            async with aiofiles.open(abs_path, "wb") as f:
                await f.write(file_content)

            # Return absolute path so Agent tools can directly read the file
            file_url = f"file://{abs_path}"

            logger.info(
                f"✅ 上传成功: {filename}, {file_size}B, {detected_mime}, "
                f"path={abs_path}"
            )

            return {
                "file_url": file_url,
                "file_name": filename,
                "file_size": file_size,
                "file_type": detected_mime,
            }

        except Exception as e:
            logger.error(f"❌ 上传失败: {str(e)}", exc_info=True)
            raise FileServiceError(f"上传失败: {str(e)}")


# ==================== Singleton ====================

_default_file_service: Optional[FileService] = None


def get_file_service() -> FileService:
    """Get default FileService singleton."""
    global _default_file_service
    if _default_file_service is None:
        _default_file_service = FileService()
    return _default_file_service
