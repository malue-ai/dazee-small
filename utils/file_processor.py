"""
文件处理器 - File Processor

职责：
1. 根据 file_id 或 file_url 获取文件
2. 根据 MIME 类型分类处理
3. 生成 LLM 可用的 content blocks

处理策略：
- 图片 (image/*) → 下载 → base64 → ImageBlock
- 纯文本 (text/plain, text/markdown) → 下载 → 读取内容 → 拼进消息
- 复杂文件 (PDF 等) → 生成预签名 URL → 拼进消息，让 Agent 决定
"""

import base64
import httpx
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

from logger import get_logger
from infra.database import AsyncSessionLocal, crud
from utils.s3_uploader import get_s3_uploader, S3UploaderError

logger = get_logger("file_processor")


class FileCategory(Enum):
    """文件分类"""
    IMAGE = "image"           # 图片：直接传给 LLM
    TEXT = "text"             # 纯文本：读取内容拼进消息
    DOCUMENT = "document"     # 复杂文档：生成 URL，让 Agent 决定


@dataclass
class ProcessedFile:
    """处理后的文件"""
    category: FileCategory
    filename: str
    mime_type: str
    # 根据 category 不同，以下字段有不同含义
    content_block: Optional[Dict[str, Any]] = None  # category=IMAGE 时使用
    text_content: Optional[str] = None              # category=TEXT 时使用
    file_url: Optional[str] = None                  # category=DOCUMENT 时使用
    file_size: Optional[int] = None                 # 文件大小（字节）


class FileProcessorError(Exception):
    """文件处理器异常"""
    pass


class FileNotFoundError(FileProcessorError):
    """文件不存在"""
    pass


class FileProcessor:
    """
    文件处理器
    
    使用方法：
        processor = FileProcessor()
        processed_files = await processor.process_files(files)
        content_blocks, attachment_text = processor.build_message_content(processed_files)
    """
    
    # 图片 MIME 类型
    IMAGE_MIME_TYPES = {
        "image/jpeg", "image/png", "image/gif", "image/webp"
    }
    
    # 纯文本 MIME 类型
    TEXT_MIME_TYPES = {
        "text/plain", "text/markdown", "text/csv", "text/html",
        "application/json", "application/xml"
    }
    
    # 最大图片大小（20MB）
    MAX_IMAGE_SIZE = 20 * 1024 * 1024
    
    # 最大文本大小（1MB）
    MAX_TEXT_SIZE = 1 * 1024 * 1024
    
    def __init__(self):
        self.s3_uploader = get_s3_uploader()
    
    async def process_files(
        self,
        files: List[Dict[str, Any]]
    ) -> List[ProcessedFile]:
        """
        处理文件列表
        
        Args:
            files: 文件引用列表，每个元素包含 file_id 或 file_url
            
        Returns:
            处理后的文件列表
        """
        processed = []
        
        for file_ref in files:
            try:
                file_id = file_ref.get("file_id")
                file_url = file_ref.get("file_url")
                
                if file_id:
                    result = await self._process_by_file_id(file_id)
                elif file_url:
                    result = await self._process_by_url(file_url)
                else:
                    logger.warning("文件引用无效：缺少 file_id 和 file_url")
                    continue
                
                if result:
                    processed.append(result)
                    
            except Exception as e:
                logger.error(f"处理文件失败: {str(e)}", exc_info=True)
                # 继续处理其他文件，不要因为一个失败就全部失败
                continue
        
        return processed
    
    async def _process_by_file_id(self, file_id: str) -> Optional[ProcessedFile]:
        """
        通过 file_id 处理文件
        
        1. 查数据库获取文件信息
        2. 根据 MIME 类型分类
        3. 从 S3 下载内容或生成预签名 URL
        """
        # 1. 查数据库
        async with AsyncSessionLocal() as session:
            file_record = await crud.get_file(session, file_id)
        
        if not file_record:
            raise FileNotFoundError(f"文件不存在: {file_id}")
        
        filename = file_record.filename
        mime_type = file_record.mime_type
        storage_path = file_record.storage_path
        file_size = file_record.file_size
        
        logger.info(f"📎 处理文件: {filename}, MIME={mime_type}, size={file_size}")
        
        # 2. 分类处理
        category = self._categorize_mime_type(mime_type)
        
        if category == FileCategory.IMAGE:
            # 图片：下载 → base64
            if file_size > self.MAX_IMAGE_SIZE:
                logger.warning(f"图片过大，降级为文档处理: {file_size} bytes")
                category = FileCategory.DOCUMENT
            else:
                content = await self._download_from_s3(storage_path)
                content_block = self._build_image_block(content, mime_type)
                return ProcessedFile(
                    category=category,
                    filename=filename,
                    mime_type=mime_type,
                    content_block=content_block,
                    file_size=file_size
                )
        
        if category == FileCategory.TEXT:
            # 纯文本：下载 → 读取内容
            if file_size > self.MAX_TEXT_SIZE:
                logger.warning(f"文本过大，降级为文档处理: {file_size} bytes")
                category = FileCategory.DOCUMENT
            else:
                content = await self._download_from_s3(storage_path)
                text_content = content.decode("utf-8", errors="replace")
                return ProcessedFile(
                    category=category,
                    filename=filename,
                    mime_type=mime_type,
                    text_content=text_content,
                    file_size=file_size
                )
        
        # 复杂文档：生成预签名 URL
        presigned_url = self.s3_uploader.get_presigned_url(
            s3_key=storage_path,
            expires_in=3600  # 1小时有效
        )
        return ProcessedFile(
            category=FileCategory.DOCUMENT,
            filename=filename,
            mime_type=mime_type,
            file_url=presigned_url,
            file_size=file_size
        )
    
    async def _process_by_url(self, url: str) -> Optional[ProcessedFile]:
        """
        通过 URL 处理文件
        
        1. 发送 HEAD 请求获取 MIME 类型和大小
        2. 根据 MIME 类型分类
        3. 下载内容或直接使用 URL
        """
        # 1. 获取文件信息
        mime_type, file_size, filename = await self._get_url_file_info(url)
        
        logger.info(f"📎 处理 URL 文件: {filename}, MIME={mime_type}, size={file_size}")
        
        # 2. 分类处理
        category = self._categorize_mime_type(mime_type)
        
        if category == FileCategory.IMAGE:
            # 图片：可以直接用 URL（Claude 支持）
            # 但为了兼容性，我们也下载转 base64
            if file_size and file_size > self.MAX_IMAGE_SIZE:
                logger.warning(f"图片过大，使用 URL 引用: {file_size} bytes")
                # 对于大图片，直接用 URL（Claude 支持 URL 方式）
                content_block = {
                    "type": "image",
                    "source": {
                        "type": "url",
                        "url": url
                    }
                }
            else:
                # 下载并转 base64
                content = await self._download_from_url(url)
                content_block = self._build_image_block(content, mime_type)
            
            return ProcessedFile(
                category=category,
                filename=filename,
                mime_type=mime_type,
                content_block=content_block,
                file_size=file_size
            )
        
        if category == FileCategory.TEXT:
            # 纯文本：下载内容
            if file_size and file_size > self.MAX_TEXT_SIZE:
                logger.warning(f"文本过大，降级为文档处理: {file_size} bytes")
                category = FileCategory.DOCUMENT
            else:
                content = await self._download_from_url(url)
                text_content = content.decode("utf-8", errors="replace")
                return ProcessedFile(
                    category=category,
                    filename=filename,
                    mime_type=mime_type,
                    text_content=text_content,
                    file_size=file_size
                )
        
        # 复杂文档：直接使用 URL
        return ProcessedFile(
            category=FileCategory.DOCUMENT,
            filename=filename,
            mime_type=mime_type,
            file_url=url,
            file_size=file_size
        )
    
    def _categorize_mime_type(self, mime_type: str) -> FileCategory:
        """根据 MIME 类型分类"""
        if mime_type in self.IMAGE_MIME_TYPES:
            return FileCategory.IMAGE
        if mime_type in self.TEXT_MIME_TYPES:
            return FileCategory.TEXT
        # 其他都当作复杂文档
        return FileCategory.DOCUMENT
    
    async def _download_from_s3(self, storage_path: str) -> bytes:
        """从 S3 下载文件内容"""
        try:
            s3_client = self.s3_uploader.s3_client
            bucket_name = self.s3_uploader.bucket_name
            
            response = s3_client.get_object(
                Bucket=bucket_name,
                Key=storage_path
            )
            content = response['Body'].read()
            
            logger.debug(f"从 S3 下载: {storage_path}, {len(content)} bytes")
            return content
            
        except Exception as e:
            logger.error(f"S3 下载失败: {str(e)}")
            raise FileProcessorError(f"下载文件失败: {str(e)}") from e
    
    async def _download_from_url(self, url: str) -> bytes:
        """从 URL 下载文件内容"""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url)
                response.raise_for_status()
                content = response.content
                
                logger.debug(f"从 URL 下载: {url}, {len(content)} bytes")
                return content
                
        except httpx.HTTPError as e:
            logger.error(f"HTTP 下载失败: {str(e)}")
            raise FileProcessorError(f"下载文件失败: {str(e)}") from e
    
    async def _get_url_file_info(
        self,
        url: str
    ) -> Tuple[str, Optional[int], str]:
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
    
    def _build_image_block(self, content: bytes, mime_type: str) -> Dict[str, Any]:
        """构建图片 content block（Claude 格式）"""
        b64_data = base64.b64encode(content).decode("utf-8")
        return {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": mime_type,
                "data": b64_data
            }
        }
    
    def build_message_content(
        self,
        processed_files: List[ProcessedFile],
        user_message: str
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
            
            elif pf.category == FileCategory.TEXT:
                # 纯文本：拼进附件说明
                if pf.text_content:
                    attachment_texts.append(
                        f"📄 {pf.filename}:\n```\n{pf.text_content}\n```"
                    )
            
            elif pf.category == FileCategory.DOCUMENT:
                # 复杂文档：提供 URL，让 Agent 决定
                if pf.file_url:
                    attachment_texts.append(
                        f"📎 {pf.filename} ({pf.mime_type}): {pf.file_url}"
                    )
        
        # 构建最终的文本消息
        final_text = user_message
        if attachment_texts:
            attachments_section = "\n\n---\n📎 附件:\n" + "\n\n".join(attachment_texts)
            final_text = user_message + attachments_section
        
        # 添加文本 block
        content_blocks.append({
            "type": "text",
            "text": final_text
        })
        
        return content_blocks


# ==================== 便捷函数 ====================

_default_processor: Optional[FileProcessor] = None


def get_file_processor() -> FileProcessor:
    """获取默认文件处理器单例"""
    global _default_processor
    if _default_processor is None:
        _default_processor = FileProcessor()
    return _default_processor

