"""
User 表 CRUD 操作
"""

from typing import Optional
from datetime import datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from infra.database.models import User
from infra.database.crud.base import get_by_id


def generate_user_id() -> str:
    """生成用户 ID（UUID）"""
    return f"user_{uuid4().hex[:16]}"


async def get_user_by_username(
    session: AsyncSession,
    username: str
) -> Optional[User]:
    """根据用户名获取用户"""
    stmt = select(User).where(User.username == username)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_or_create_user(
    session: AsyncSession,
    user_id: str,
    username: Optional[str] = None
) -> User:
    """获取或创建用户（按 user_id）"""
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


async def get_or_create_user_by_username(
    session: AsyncSession,
    username: str
) -> tuple[User, bool]:
    """
    根据用户名获取或创建用户
    
    - 同一个 username 登录，返回相同的 user_id
    - 新 username 登录，生成新的 UUID 作为 user_id
    
    Returns:
        (User, is_new): 用户对象和是否为新创建
    """
    # 先按用户名查找
    user = await get_user_by_username(session, username)
    if user:
        # 更新最后登录时间
        user.updated_at = datetime.now()
        await session.commit()
        return user, False
    
    # 创建新用户，user_id 使用 UUID
    user = User(
        id=generate_user_id(),
        username=username,
        created_at=datetime.now(),
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user, True

