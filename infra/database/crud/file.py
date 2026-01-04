"""
File 表 CRUD 操作

职责：封装所有文件相关的数据库操作
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import uuid4

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from infra.database.models import File
from infra.database.models.file import FileStatus, StorageType
from infra.database.crud.base import get_by_id


def convert_api_status_to_db(api_status: Optional[str]) -> Optional[FileStatus]:
    """
    将 API 层的状态字符串转换为数据库枚举
    
    Args:
        api_status: API 层的状态字符串（如 "uploading", "ready"）
        
    Returns:
        数据库层的 FileStatus 枚举，或 None
    """
    if api_status is None:
        return None
    
    status_map = {
        "uploading": FileStatus.UPLOADING,
        "uploaded": FileStatus.PROCESSING,  # API 的 UPLOADED 映射到 DB 的 PROCESSING
        "processing": FileStatus.PROCESSING,
        "pending": FileStatus.PENDING,
        "ready": FileStatus.READY,
        "failed": FileStatus.FAILED,
        "deleted": FileStatus.DELETED,
    }
    return status_map.get(api_status.lower())


def generate_file_id() -> str:
    """生成文件 ID"""
    return f"file_{uuid4().hex[:24]}"


async def create_file(
    session: AsyncSession,
    user_id: str,
    filename: str,
    file_size: int,
    content_type: str,
    storage_path: str,
    storage_type: StorageType = StorageType.LOCAL,
    status: FileStatus = FileStatus.PENDING,
    **kwargs
) -> File:
    """创建文件记录"""
    file = File(
        id=generate_file_id(),
        user_id=user_id,
        filename=filename,
        file_size=file_size,
        content_type=content_type,
        storage_path=storage_path,
        storage_type=storage_type,
        status=status,
        created_at=datetime.now(),
    )
    
    # 设置其他可选字段
    for key, value in kwargs.items():
        if hasattr(file, key):
            setattr(file, key, value)
    
    session.add(file)
    await session.commit()
    await session.refresh(file)
    return file


async def get_file(
    session: AsyncSession,
    file_id: str
) -> Optional[File]:
    """获取文件"""
    return await get_by_id(session, File, file_id)


async def update_file(
    session: AsyncSession,
    file_id: str,
    **kwargs
) -> Optional[File]:
    """更新文件"""
    file = await get_file(session, file_id)
    if not file:
        return None
    
    for key, value in kwargs.items():
        if hasattr(file, key):
            setattr(file, key, value)
    
    file.updated_at = datetime.now()
    
    await session.commit()
    await session.refresh(file)
    return file


async def list_files(
    session: AsyncSession,
    user_id: str,
    limit: int = 100,
    offset: int = 0
) -> List[File]:
    """获取用户的文件列表"""
    result = await session.execute(
        select(File)
        .where(File.user_id == user_id)
        .where(File.status != FileStatus.DELETED)
        .order_by(File.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all())


async def list_files_by_user(
    session: AsyncSession,
    user_id: str,
    category: Optional[str] = None,
    status: Optional[FileStatus] = None,
    limit: int = 100,
    offset: int = 0,
    order_by: str = "created_at",
    order_desc: bool = True
) -> List[Dict[str, Any]]:
    """
    获取用户的文件列表（带过滤）
    
    返回字典列表（兼容老 API）
    """
    query = select(File).where(File.user_id == user_id)
    
    # 默认排除已删除
    if status is None:
        query = query.where(File.status != FileStatus.DELETED)
    else:
        query = query.where(File.status == status)
    
    # TODO: category 过滤需要在 File 模型中添加 category 字段
    
    # 排序
    order_column = getattr(File, order_by, File.created_at)
    if order_desc:
        query = query.order_by(order_column.desc())
    else:
        query = query.order_by(order_column.asc())
    
    query = query.limit(limit).offset(offset)
    
    result = await session.execute(query)
    files = result.scalars().all()
    
    # 转换为字典列表
    return [
        {
            "id": f.id,
            "user_id": f.user_id,
            "filename": f.filename,
            "file_size": f.file_size,
            "content_type": f.content_type,
            "storage_type": f.storage_type.value if f.storage_type else None,
            "storage_path": f.storage_path,
            "storage_url": f.storage_url,
            "status": f.status.value if f.status else None,
            "created_at": f.created_at.isoformat() if f.created_at else None,
            "updated_at": f.updated_at.isoformat() if f.updated_at else None,
            "metadata": f.extra_data,
        }
        for f in files
    ]


async def count_files_by_user(
    session: AsyncSession,
    user_id: str,
    category: Optional[str] = None,
    status: Optional[FileStatus] = None
) -> int:
    """统计用户的文件数量"""
    query = select(func.count(File.id)).where(File.user_id == user_id)
    
    if status is None:
        query = query.where(File.status != FileStatus.DELETED)
    else:
        query = query.where(File.status == status)
    
    result = await session.execute(query)
    return result.scalar() or 0


async def get_user_file_stats(
    session: AsyncSession,
    user_id: str
) -> Dict[str, Any]:
    """获取用户文件统计"""
    # 总数
    total_count = await count_files_by_user(session, user_id)
    
    # 总大小
    size_result = await session.execute(
        select(func.sum(File.file_size))
        .where(File.user_id == user_id)
        .where(File.status != FileStatus.DELETED)
    )
    total_size = size_result.scalar() or 0
    
    # 按状态统计
    status_counts = {}
    for status in FileStatus:
        if status == FileStatus.DELETED:
            continue
        count = await count_files_by_user(session, user_id, status=status)
        status_counts[status.value] = count
    
    return {
        "user_id": user_id,
        "total_count": total_count,
        "total_size": total_size,
        "by_status": status_counts,
    }


async def soft_delete_file(
    session: AsyncSession,
    file_id: str
) -> bool:
    """软删除文件"""
    file = await get_file(session, file_id)
    if not file:
        return False
    
    file.status = FileStatus.DELETED
    file.updated_at = datetime.now()
    
    await session.commit()
    return True

