"""
File 服务层 - 文件上传服务（纯 S3，无数据库）

职责：
1. 上传文件到 S3
2. 生成预签名 URL
3. MIME 类型检测

设计原则：
- 不使用数据库存储文件元数据
- 直接返回 S3 预签名 URL
- 前端通过 file_url 方式使用文件
"""

import uuid
from datetime import datetime
from typing import Any, Dict, Optional

import filetype

from logger import get_logger
from utils import get_s3_uploader

logger = get_logger("file_service")


def detect_mime_type(file_content: bytes, filename: str) -> str:
    """
    检测文件的真实 MIME 类型（基于文件头）

    Args:
        file_content: 文件内容（字节）
        filename: 文件名

    Returns:
        MIME 类型
    """
    # 使用 filetype 检测
    kind = filetype.guess(file_content)

    if kind is not None:
        mime = kind.mime
        logger.debug(f"检测 MIME: {filename} -> {mime}")
        return mime

    # 如果无法检测，使用简单的后缀名映射
    fallback_mime = _get_mime_from_extension(filename)
    logger.debug(f"检测 MIME（后备）: {filename} -> {fallback_mime}")
    return fallback_mime


def _get_mime_from_extension(filename: str) -> str:
    """根据文件扩展名返回 MIME 类型（后备方案）"""
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
    """文件服务异常基类"""

    pass


class FileService:
    """
    文件服务（纯 S3，无数据库）

    只提供文件上传到 S3 并返回预签名 URL 的功能
    """

    def __init__(self) -> None:
        """初始化文件服务"""
        self.s3_uploader = get_s3_uploader()

    async def upload_file(
        self, file_content: bytes, filename: str, mime_type: str, user_id: str
    ) -> Dict[str, Any]:
        """
        上传文件到 S3（不保存到数据库）

        Args:
            file_content: 文件内容（字节）
            filename: 文件名
            mime_type: 前端传来的 MIME 类型（会被后端验证）
            user_id: 用户 ID

        Returns:
            { "file_url", "file_name", "file_size", "file_type" }
        """
        file_size = len(file_content)

        # 后端检测真实的 MIME 类型
        detected_mime = detect_mime_type(file_content, filename)
        logger.info(f"MIME 验证: 前端={mime_type}, 后端={detected_mime}")

        # 构建存储路径：chat-attachments/{user_id}/{date}/{unique_id}_{filename}
        date_str = datetime.now().strftime("%Y%m%d")
        unique_id = str(uuid.uuid4())
        safe_filename = "".join(c for c in filename if c.isalnum() or c in "._-")
        storage_path = f"chat-attachments/{user_id}/{date_str}/{unique_id}_{safe_filename}"

        try:
            # 上传到 S3（使用检测到的 MIME 类型）
            await self.s3_uploader.upload_bytes(
                file_content=file_content, object_name=storage_path, content_type=detected_mime
            )

            # 生成预签名 URL（24小时有效，足够完成对话）
            file_url = await self.s3_uploader.get_presigned_url(
                s3_key=storage_path, expires_in=86400  # 24小时
            )

            logger.info(f"✅ 上传成功: {filename}, {file_size}B, {detected_mime}")

            return {
                "file_url": file_url,
                "file_name": filename,
                "file_size": file_size,
                "file_type": detected_mime,
            }

        except Exception as e:
            logger.error(f"❌ 上传失败: {str(e)}", exc_info=True)
            raise FileServiceError(f"上传失败: {str(e)}")


# ==================== 便捷函数 ====================

_default_file_service: Optional[FileService] = None


def get_file_service() -> FileService:
    """
    获取默认的 File Service 实例（单例）

    Returns:
        FileService 实例
    """
    global _default_file_service
    if _default_file_service is None:
        _default_file_service = FileService()
    return _default_file_service
