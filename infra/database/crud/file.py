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
from infra.database.crud.base import get_by_id


async def create_file(
    session: AsyncSession,
    user_id: str,
    filename: str,
    file_size: int,
    mime_type: str,
    storage_path: str
) -> File:
    """
    创建文件记录
    
    Args:
        session: 数据库会话
        user_id: 用户 ID
        filename: 文件名
        file_size: 文件大小（字节）
        mime_type: MIME 类型
        storage_path: S3 路径
        
    Returns:
        File 对象
    """
    file = File(
        id=str(uuid4()),
        user_id=user_id,
        filename=filename,
        file_size=file_size,
        mime_type=mime_type,
        storage_path=storage_path,
        created_at=datetime.now(),
    )
    
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


async def list_files_by_user(
    session: AsyncSession,
    user_id: str,
    limit: int = 100,
    offset: int = 0,
    order_by: str = "created_at",
    order_desc: bool = True
) -> List[Dict[str, Any]]:
    """获取用户的文件列表"""
    query = select(File).where(File.user_id == user_id)
    
    order_column = getattr(File, order_by, File.created_at)
    query = query.order_by(order_column.desc() if order_desc else order_column.asc())
    query = query.limit(limit).offset(offset)
    
    result = await session.execute(query)
    files = result.scalars().all()
    
    return [
        {
            "file_id": f.id,
            "filename": f.filename,
            "file_size": f.file_size,
            "mime_type": f.mime_type,
            "created_at": f.created_at.isoformat() if f.created_at else None,
        }
        for f in files
    ]


async def count_files_by_user(
    session: AsyncSession,
    user_id: str
) -> int:
    """统计用户的文件数量"""
    result = await session.execute(
        select(func.count(File.id)).where(File.user_id == user_id)
    )
    return result.scalar() or 0


async def delete_file(
    session: AsyncSession,
    file_id: str
) -> bool:
    """删除文件"""
    file = await get_file(session, file_id)
    if not file:
        return False
    
    await session.delete(file)
    await session.commit()
    return True
