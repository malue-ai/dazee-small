"""
通用 CRUD 操作
"""

from typing import Optional, Dict, Any, Type, TypeVar

from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from infra.database.base import Base

T = TypeVar("T", bound=Base)


async def get_by_id(
    session: AsyncSession,
    model: Type[T],
    id: str
) -> Optional[T]:
    """根据 ID 获取实体"""
    result = await session.execute(
        select(model).where(model.id == id)
    )
    return result.scalar_one_or_none()


async def create(
    session: AsyncSession,
    model: Type[T],
    **kwargs
) -> T:
    """创建实体"""
    instance = model(**kwargs)
    session.add(instance)
    await session.commit()
    await session.refresh(instance)
    return instance


async def update_by_id(
    session: AsyncSession,
    model: Type[T],
    id: str,
    **kwargs
) -> Optional[T]:
    """更新实体"""
    await session.execute(
        update(model).where(model.id == id).values(**kwargs)
    )
    await session.commit()
    return await get_by_id(session, model, id)


async def delete_by_id(
    session: AsyncSession,
    model: Type[T],
    id: str
) -> bool:
    """删除实体"""
    result = await session.execute(
        delete(model).where(model.id == id)
    )
    await session.commit()
    return result.rowcount > 0

