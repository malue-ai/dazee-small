"""
File 服务层 - 文件管理业务逻辑

职责：
1. 文件 CRUD 业务逻辑
2. 文件统计和查询
3. 与 S3 存储交互
4. 权限检查

设计原则：
- Service 层只调用 crud.xxx() 函数
- 不直接写 SQLAlchemy 查询
- 不直接导入数据库模型
"""

from logger import get_logger
from typing import Dict, Any, Optional, List
from datetime import datetime
import filetype  # 纯 Python 文件类型检测，无需系统依赖
from infra.database import AsyncSessionLocal, crud
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
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    
    mime_map = {
        'txt': 'text/plain',
        'pdf': 'application/pdf',
        'json': 'application/json',
        'xml': 'application/xml',
        'html': 'text/html',
        'css': 'text/css',
        'js': 'application/javascript',
        'png': 'image/png',
        'jpg': 'image/jpeg',
        'jpeg': 'image/jpeg',
        'gif': 'image/gif',
        'svg': 'image/svg+xml',
        'mp4': 'video/mp4',
        'mp3': 'audio/mpeg',
        'zip': 'application/zip',
        'gz': 'application/gzip',
    }
    
    return mime_map.get(ext, 'application/octet-stream')


class FileServiceError(Exception):
    """文件服务异常基类"""
    pass


class FileNotFoundError(FileServiceError):
    """文件不存在异常"""
    pass


class FileService:
    """
    文件服务
    
    提供文件的完整生命周期管理
    """
    
    def __init__(self):
        """初始化文件服务"""
        self.s3_uploader = get_s3_uploader()
    
    # ==================== 文件查询 ====================
    
    async def list_files(
        self,
        user_id: str,
        limit: int = 20,
        offset: int = 0
    ) -> Dict[str, Any]:
        """获取用户文件列表"""
        async with AsyncSessionLocal() as session:
            files = await crud.list_files_by_user(
                session=session,
                user_id=user_id,
                limit=limit,
                offset=offset,
                order_by="created_at",
                order_desc=True
            )
            
            total = await crud.count_files_by_user(session=session, user_id=user_id)
        
        return {
            "user_id": user_id,
            "total": total,
            "files": files,
            "has_more": (offset + len(files)) < total
        }
    
    async def get_file(self, file_id: str) -> Dict[str, Any]:
        """获取文件详情"""
        async with AsyncSessionLocal() as session:
            file_record = await crud.get_file(session, file_id)
        
        if not file_record:
            raise FileNotFoundError(f"文件不存在: {file_id}")
        
        return {
            "file_id": file_record.id,
            "file_name": file_record.filename,
            "file_size": file_record.file_size,
            "file_type": file_record.mime_type,
            "created_at": file_record.created_at.isoformat() if file_record.created_at else None,
        }
    
    # ==================== 文件操作 ====================
    
    async def get_download_url(self, file_id: str) -> Dict[str, Any]:
        """获取下载 URL（预签名，24小时有效）"""
        async with AsyncSessionLocal() as session:
            file_record = await crud.get_file(session, file_id)
            
            if not file_record:
                raise FileNotFoundError(f"文件不存在: {file_id}")
            
            url = self.s3_uploader.get_presigned_url(
                s3_key=file_record.storage_path,
                expires_in=86400
            )
            
            return {
                "file_id": file_id,
                "file_name": file_record.filename,
                "file_url": url
            }
    
    async def delete_file(self, file_id: str) -> Dict[str, Any]:
        """删除文件"""
        async with AsyncSessionLocal() as session:
            file_record = await crud.get_file(session, file_id)
            
            if not file_record:
                raise FileNotFoundError(f"文件不存在: {file_id}")
            
            # 删除 S3 文件
            try:
                await self.s3_uploader.delete_file(file_record.storage_path)
            except Exception as e:
                logger.warning(f"⚠️ S3 删除失败: {str(e)}")
            
            # 删除数据库记录
            await crud.delete_file(session, file_id)
        
        return {"file_id": file_id, "success": True}
    
    # ==================== 文件上传 ====================
    
    async def upload_file(
        self,
        file_content: bytes,
        filename: str,
        mime_type: str,
        user_id: str
    ) -> Dict[str, Any]:
        """
        上传文件到 S3 并保存记录到数据库
        
        Args:
            file_content: 文件内容（字节）
            filename: 文件名
            mime_type: 前端传来的 MIME 类型（会被后端验证）
            user_id: 用户 ID
            
        Returns:
            { "file_id", "file_name", "file_size", "file_type", "file_url", "created_at" }
        """
        import uuid
        from datetime import datetime
        
        file_size = len(file_content)
        
        # 后端检测真实的 MIME 类型
        detected_mime = detect_mime_type(file_content, filename)
        logger.info(f"MIME 验证: 前端={mime_type}, 后端={detected_mime}")
        
        # 构建存储路径
        date_str = datetime.now().strftime("%Y%m%d")
        unique_id = uuid.uuid4().hex[:12]
        safe_filename = "".join(c for c in filename if c.isalnum() or c in "._-")
        storage_path = f"{user_id}/{date_str}/{unique_id}_{safe_filename}"
        
        try:
            # 上传到 S3（使用检测到的 MIME 类型）
            await self.s3_uploader.upload_bytes(
                file_content=file_content,
                object_name=storage_path,
                content_type=detected_mime
            )
            
            # 保存到数据库
            async with AsyncSessionLocal() as session:
                file_record = await crud.create_file(
                    session=session,
                    user_id=user_id,
                    filename=filename,
                    file_size=file_size,
                    mime_type=detected_mime,
                    storage_path=storage_path
                )
            
            logger.info(f"✅ 上传: {file_record.id}, {filename}, {file_size}B, {detected_mime}")
            
            # 生成访问 URL
            file_url = self.s3_uploader.get_presigned_url(
                s3_key=storage_path,
                expires_in=3600
            )
            
            return {
                "file_id": file_record.id,
                "file_name": filename,
                "file_size": file_size,
                "file_type": detected_mime,
                "file_url": file_url,
                "created_at": datetime.now().isoformat()
            }
        
        except Exception as e:
            logger.error(f"❌ 上传失败: {str(e)}", exc_info=True)
            raise FileServiceError(f"上传失败: {str(e)}")
    
    async def get_file_url(self, file_id: str, expiration: int = 3600) -> str:
        """获取文件访问 URL"""
        async with AsyncSessionLocal() as session:
            file_record = await crud.get_file(session, file_id)
            
            if not file_record:
                raise FileNotFoundError(f"文件不存在: {file_id}")
            
            return self.s3_uploader.get_presigned_url(
                s3_key=file_record.storage_path,
                expires_in=expiration
            )
    
    async def get_file_content(self, file_id: str) -> tuple[bytes, str, str]:
        """
        获取文件内容（用于代理预览）
        
        Args:
            file_id: 文件 ID
            
        Returns:
            (文件内容, MIME 类型, 文件名)
        """
        async with AsyncSessionLocal() as session:
            file_record = await crud.get_file(session, file_id)
            
            if not file_record:
                raise FileNotFoundError(f"文件不存在: {file_id}")
            
            # 从 S3 下载文件内容
            s3_client = self.s3_uploader.s3_client
            bucket_name = self.s3_uploader.bucket_name
            
            response = s3_client.get_object(
                Bucket=bucket_name,
                Key=file_record.storage_path
            )
            content = response['Body'].read()
            
            logger.info(f"📥 获取文件内容: {file_record.filename}, {len(content)} bytes")
            
            return content, file_record.mime_type, file_record.filename


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

