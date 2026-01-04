"""
User 表 CRUD 操作
"""

from typing import Optional
from datetime import datetime
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from infra.database.models import User
from infra.database.crud.base import get_by_id


def generate_user_id() -> str:
    """生成用户 ID"""
    return f"user_{uuid4().hex[:24]}"


async def get_or_create_user(
    session: AsyncSession,
    user_id: str,
    username: Optional[str] = None
) -> User:
    """获取或创建用户"""
    user = await get_by_id(session, User, user_id)
    if user:
        return user
    
    # 创建新用户
    user = User(
        id=user_id,
        username=username or f"user_{user_id[:8]}",
        created_at=datetime.now(),
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user

