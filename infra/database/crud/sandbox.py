"""
Sandbox 表 CRUD 操作

职责：封装所有沙盒相关的数据库操作
Service 层只调用这里的函数，不直接写 SQLAlchemy 查询
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from infra.database.models.sandbox import Sandbox
from infra.database.crud.base import get_by_id, delete_by_id


async def create_sandbox(
    session: AsyncSession,
    conversation_id: str,
    user_id: str,
    e2b_sandbox_id: Optional[str] = None,
    status: str = "creating",
    stack: Optional[str] = None,
    preview_url: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> Sandbox:
    """
    创建沙盒记录
    
    Args:
        session: 数据库会话
        conversation_id: 对话 ID
        user_id: 用户 ID
        e2b_sandbox_id: E2B 沙盒 ID
        status: 状态 (creating/running/paused/killed)
        stack: 技术栈 (streamlit/gradio/python)
        preview_url: 预览 URL
        metadata: 元数据
        
    Returns:
        创建的沙盒记录
    """
    sandbox = Sandbox(
        id=str(uuid4()),
        conversation_id=conversation_id,
        user_id=user_id,
        e2b_sandbox_id=e2b_sandbox_id,
        status=status,
        stack=stack,
        preview_url=preview_url,
        created_at=datetime.now(),
        updated_at=datetime.now(),
        last_active_at=datetime.now()
    )
    if metadata:
        sandbox.extra_data = metadata
    
    session.add(sandbox)
    await session.commit()
    await session.refresh(sandbox)
    return sandbox


async def get_sandbox(
    session: AsyncSession,
    sandbox_id: str
) -> Optional[Sandbox]:
    """根据 ID 获取沙盒"""
    return await get_by_id(session, Sandbox, sandbox_id)


async def get_sandbox_by_conversation(
    session: AsyncSession,
    conversation_id: str
) -> Optional[Sandbox]:
    """
    根据 conversation_id 获取沙盒
    
    Args:
        session: 数据库会话
        conversation_id: 对话 ID
        
    Returns:
        沙盒记录，不存在返回 None
    """
    result = await session.execute(
        select(Sandbox).where(Sandbox.conversation_id == conversation_id)
    )
    return result.scalar_one_or_none()


async def get_sandbox_by_e2b_id(
    session: AsyncSession,
    e2b_sandbox_id: str
) -> Optional[Sandbox]:
    """
    根据 E2B sandbox_id 获取沙盒
    
    Args:
        session: 数据库会话
        e2b_sandbox_id: E2B 沙盒 ID
        
    Returns:
        沙盒记录，不存在返回 None
    """
    result = await session.execute(
        select(Sandbox).where(Sandbox.e2b_sandbox_id == e2b_sandbox_id)
    )
    return result.scalar_one_or_none()


async def update_sandbox(
    session: AsyncSession,
    sandbox_id: str,
    e2b_sandbox_id: Optional[str] = None,
    status: Optional[str] = None,
    stack: Optional[str] = None,
    preview_url: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> Optional[Sandbox]:
    """
    更新沙盒信息
    
    Args:
        session: 数据库会话
        sandbox_id: 沙盒记录 ID
        e2b_sandbox_id: E2B 沙盒 ID
        status: 状态
        stack: 技术栈
        preview_url: 预览 URL
        metadata: 元数据
        
    Returns:
        更新后的沙盒记录
    """
    sandbox = await get_sandbox(session, sandbox_id)
    if not sandbox:
        return None
    
    if e2b_sandbox_id is not None:
        sandbox.e2b_sandbox_id = e2b_sandbox_id
    if status is not None:
        sandbox.status = status
        # 如果状态变为 paused，记录暂停时间
        if status == "paused":
            sandbox.paused_at = datetime.now()
        # 如果从 paused 变为其他状态，清除暂停时间
        elif sandbox.paused_at:
            sandbox.paused_at = None
    if stack is not None:
        sandbox.stack = stack
    if preview_url is not None:
        sandbox.preview_url = preview_url
    if metadata is not None:
        sandbox.extra_data = metadata
    
    sandbox.updated_at = datetime.now()
    
    await session.commit()
    await session.refresh(sandbox)
    return sandbox


async def update_sandbox_status(
    session: AsyncSession,
    conversation_id: str,
    status: str,
    preview_url: Optional[str] = None
) -> Optional[Sandbox]:
    """
    更新沙盒状态（按 conversation_id）
    
    Args:
        session: 数据库会话
        conversation_id: 对话 ID
        status: 新状态
        preview_url: 预览 URL（可选）
        
    Returns:
        更新后的沙盒记录
    """
    sandbox = await get_sandbox_by_conversation(session, conversation_id)
    if not sandbox:
        return None
    
    sandbox.status = status
    sandbox.updated_at = datetime.now()
    
    if status == "paused":
        sandbox.paused_at = datetime.now()
    elif sandbox.paused_at:
        sandbox.paused_at = None
    
    if preview_url is not None:
        sandbox.preview_url = preview_url
    
    await session.commit()
    await session.refresh(sandbox)
    return sandbox


async def update_sandbox_e2b_id(
    session: AsyncSession,
    conversation_id: str,
    e2b_sandbox_id: str,
    status: str = "running",
    preview_url: Optional[str] = None
) -> Optional[Sandbox]:
    """
    更新沙盒的 E2B sandbox_id（按 conversation_id）
    
    通常在创建 E2B 沙盒成功后调用
    
    Args:
        session: 数据库会话
        conversation_id: 对话 ID
        e2b_sandbox_id: E2B 沙盒 ID
        status: 状态
        preview_url: 预览 URL
        
    Returns:
        更新后的沙盒记录
    """
    sandbox = await get_sandbox_by_conversation(session, conversation_id)
    if not sandbox:
        return None
    
    sandbox.e2b_sandbox_id = e2b_sandbox_id
    sandbox.status = status
    sandbox.updated_at = datetime.now()
    sandbox.last_active_at = datetime.now()
    
    if preview_url:
        sandbox.preview_url = preview_url
    
    await session.commit()
    await session.refresh(sandbox)
    return sandbox


async def update_sandbox_activity(
    session: AsyncSession,
    conversation_id: str
) -> Optional[Sandbox]:
    """
    更新沙盒活跃时间
    
    Args:
        session: 数据库会话
        conversation_id: 对话 ID
        
    Returns:
        更新后的沙盒记录
    """
    sandbox = await get_sandbox_by_conversation(session, conversation_id)
    if not sandbox:
        return None
    
    sandbox.last_active_at = datetime.now()
    sandbox.updated_at = datetime.now()
    
    await session.commit()
    await session.refresh(sandbox)
    return sandbox


async def update_sandbox_project(
    session: AsyncSession,
    conversation_id: str,
    project_path: Optional[str],
    project_stack: Optional[str],
    preview_url: Optional[str] = None
) -> Optional[Sandbox]:
    """
    更新沙盒的当前运行项目信息
    
    用于记录/清除当前沙盒中运行的项目，
    在暂停/恢复时自动管理项目生命周期
    
    Args:
        session: 数据库会话
        conversation_id: 对话 ID
        project_path: 项目路径（传 None 表示清除）
        project_stack: 项目技术栈（传 None 表示清除）
        preview_url: 预览 URL（可选）
        
    Returns:
        更新后的沙盒记录
    """
    sandbox = await get_sandbox_by_conversation(session, conversation_id)
    if not sandbox:
        return None
    
    sandbox.active_project_path = project_path
    sandbox.active_project_stack = project_stack
    sandbox.updated_at = datetime.now()
    sandbox.last_active_at = datetime.now()
    
    if preview_url is not None:
        sandbox.preview_url = preview_url
    
    await session.commit()
    await session.refresh(sandbox)
    return sandbox


async def list_sandboxes_by_user(
    session: AsyncSession,
    user_id: str,
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0
) -> List[Sandbox]:
    """
    获取用户的沙盒列表
    
    Args:
        session: 数据库会话
        user_id: 用户 ID
        status: 状态过滤（可选）
        limit: 数量限制
        offset: 偏移量
        
    Returns:
        沙盒列表
    """
    query = select(Sandbox).where(Sandbox.user_id == user_id)
    
    if status:
        query = query.where(Sandbox.status == status)
    
    query = query.order_by(Sandbox.updated_at.desc()).limit(limit).offset(offset)
    
    result = await session.execute(query)
    return list(result.scalars().all())


async def list_sandboxes_by_status(
    session: AsyncSession,
    status: str,
    limit: int = 100
) -> List[Sandbox]:
    """
    根据状态获取沙盒列表
    
    Args:
        session: 数据库会话
        status: 状态
        limit: 数量限制
        
    Returns:
        沙盒列表
    """
    result = await session.execute(
        select(Sandbox)
        .where(Sandbox.status == status)
        .order_by(Sandbox.updated_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def delete_sandbox(
    session: AsyncSession,
    sandbox_id: str
) -> bool:
    """删除沙盒记录"""
    return await delete_by_id(session, Sandbox, sandbox_id)


async def delete_sandbox_by_conversation(
    session: AsyncSession,
    conversation_id: str
) -> bool:
    """
    根据 conversation_id 删除沙盒记录
    
    Args:
        session: 数据库会话
        conversation_id: 对话 ID
        
    Returns:
        是否删除成功
    """
    sandbox = await get_sandbox_by_conversation(session, conversation_id)
    if not sandbox:
        return False
    
    await session.delete(sandbox)
    await session.commit()
    return True

