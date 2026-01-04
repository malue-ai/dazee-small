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

from infra.database import AsyncSessionLocal, crud
from utils import get_s3_uploader

logger = get_logger("file_service")


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
        category: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 20,
        offset: int = 0
    ) -> Dict[str, Any]:
        """
        获取用户文件列表
        
        Args:
            user_id: 用户ID
            category: 分类过滤（可选）
            status: 状态过滤（可选）
            limit: 每页数量
            offset: 偏移量
            
        Returns:
            {"user_id": str, "total": int, "files": [...], "has_more": bool}
        """
        async with AsyncSessionLocal() as session:
            # 转换状态
            db_status = crud.convert_api_status_to_db(status)
            
            # 查询文件列表
            files = await crud.list_files_by_user(
                session=session,
                user_id=user_id,
                category=category,
                status=db_status,
                limit=limit,
                offset=offset,
                order_by="created_at",
                order_desc=True
            )
            
            # 查询总数
            total = await crud.count_files_by_user(
                session=session,
                user_id=user_id,
                category=category,
                status=db_status
            )
        
        has_more = (offset + len(files)) < total
        
        logger.info(f"✅ 获取文件列表: user_id={user_id}, total={total}, returned={len(files)}")
        
        return {
            "user_id": user_id,
            "total": total,
            "files": files,
            "has_more": has_more
        }
    
    async def get_file(self, file_id: str) -> Dict[str, Any]:
        """
        获取文件详情
        
        Args:
            file_id: 文件ID
            
        Returns:
            文件信息字典
            
        Raises:
            FileNotFoundError: 文件不存在
        """
        async with AsyncSessionLocal() as session:
            file_record = await crud.get_file(session, file_id)
        
        if not file_record:
            raise FileNotFoundError(f"文件不存在: {file_id}")
        
        # 转换为字典
        return {
            "id": file_record.id,
            "user_id": file_record.user_id,
            "filename": file_record.filename,
            "file_size": file_record.file_size,
            "content_type": file_record.content_type,
            "storage_type": file_record.storage_type.value if file_record.storage_type else None,
            "storage_path": file_record.storage_path,
            "storage_url": file_record.storage_url,
            "status": file_record.status.value if file_record.status else None,
            "created_at": file_record.created_at.isoformat() if file_record.created_at else None,
            "updated_at": file_record.updated_at.isoformat() if file_record.updated_at else None,
        }
    
    async def get_user_stats(self, user_id: str) -> Dict[str, Any]:
        """
        获取用户文件统计
        
        Args:
            user_id: 用户ID
            
        Returns:
            统计信息
        """
        async with AsyncSessionLocal() as session:
            # 获取统计信息
            stats = await crud.get_user_file_stats(session, user_id)
            
            # 获取最近上传的文件
            recent_files = await crud.list_files_by_user(
                session=session,
                user_id=user_id,
                limit=5,
                offset=0,
                order_by="created_at",
                order_desc=True
            )
        
        logger.info(f"✅ 获取用户统计: user_id={user_id}, total={stats.get('total_count', 0)}")
        
        return {
            **stats,
            "recent_uploads": recent_files
        }
    
    # ==================== 文件操作 ====================
    
    async def get_download_url(self, file_id: str) -> Dict[str, Any]:
        """
        获取文件下载 URL（预签名 URL）
        
        Args:
            file_id: 文件ID
            
        Returns:
            {"file_id": str, "filename": str, "url": str, "expires_at": str}
            
        Raises:
            FileNotFoundError: 文件不存在
        """
        async with AsyncSessionLocal() as session:
            file_record = await crud.get_file(session, file_id)
            
            if not file_record:
                raise FileNotFoundError(f"文件不存在: {file_id}")
            
            # 生成预签名 URL（24小时有效）
            presigned_url = await self.s3_uploader.get_presigned_url(
                object_name=file_record.storage_path,
                expiration=86400
            )
            
            # TODO: 更新下载计数
            
            logger.info(f"✅ 生成下载链接: file_id={file_id}")
            
            return {
                "file_id": file_id,
                "filename": file_record.filename,
                "url": presigned_url,
                "expires_at": datetime.now().isoformat()
            }
    
    async def delete_file(self, file_id: str) -> Dict[str, Any]:
        """
        删除文件
        
        Args:
            file_id: 文件ID
            
        Returns:
            {"file_id": str, "filename": str, "deleted": bool}
            
        Raises:
            FileNotFoundError: 文件不存在
        """
        async with AsyncSessionLocal() as session:
            # 获取文件记录
            file_record = await crud.get_file(session, file_id)
            
            if not file_record:
                raise FileNotFoundError(f"文件不存在: {file_id}")
            
            filename = file_record.filename
            storage_path = file_record.storage_path
            
            # 从 S3 删除文件
            try:
                await self.s3_uploader.delete_file(storage_path)
                logger.info(f"✅ S3 文件已删除: {storage_path}")
            except Exception as s3_error:
                logger.warning(f"⚠️ S3 删除失败（继续删除数据库记录）: {str(s3_error)}")
            
            # 软删除数据库记录
            success = await crud.soft_delete_file(session, file_id)
        
        logger.info(f"✅ 文件删除成功: file_id={file_id}, filename={filename}")
        
        return {
            "file_id": file_id,
            "filename": filename,
            "deleted": success
        }
    
    async def increment_view_count(self, file_id: str) -> bool:
        """
        增加文件查看次数
        
        Args:
            file_id: 文件ID
            
        Returns:
            是否成功
        """
        # TODO: 实现计数功能（需要在 File 模型中添加 view_count 字段）
        logger.debug(f"📊 查看计数: file_id={file_id}")
        return True


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

