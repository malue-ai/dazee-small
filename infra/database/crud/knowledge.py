"""
Knowledge 表 CRUD 操作

提供知识库表的数据库操作
"""

from typing import Optional, List
from datetime import datetime
from uuid import uuid4

from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from infra.database.models.knowledge import Knowledge, KnowledgeType, KnowledgeStatus


def generate_knowledge_id() -> str:
    """生成知识库条目 ID"""
    return f"kb_{uuid4().hex[:24]}"


async def create_knowledge(
    session: AsyncSession,
    user_id: str,
    title: str,
    content: str,
    knowledge_id: Optional[str] = None,
    file_id: Optional[str] = None,
    summary: Optional[str] = None,
    type: KnowledgeType = KnowledgeType.DOCUMENT,
    status: KnowledgeStatus = KnowledgeStatus.PENDING,
    source_url: Optional[str] = None,
    source_type: Optional[str] = None,
    metadata: Optional[dict] = None
) -> Knowledge:
    """
    创建知识库条目
    
    Args:
        session: 数据库会话
        user_id: 用户 ID
        title: 标题
        content: 内容
        knowledge_id: 知识库条目 ID（可选，自动生成）
        file_id: 来源文件 ID（可选）
        summary: 摘要（可选）
        type: 类型
        status: 状态
        source_url: 来源 URL
        source_type: 来源类型
        metadata: 元数据
        
    Returns:
        创建的 Knowledge 对象
    """
    kb_id = knowledge_id or generate_knowledge_id()
    
    knowledge = Knowledge(
        id=kb_id,
        user_id=user_id,
        title=title,
        content=content,
        file_id=file_id,
        summary=summary,
        type=type,
        status=status,
        source_url=source_url,
        source_type=source_type,
        token_count=len(content) // 4,  # 粗略估算
        char_count=len(content),
        created_at=datetime.now()
    )
    
    if metadata:
        knowledge.extra_data = metadata
    
    session.add(knowledge)
    await session.commit()
    await session.refresh(knowledge)
    
    return knowledge


async def get_knowledge(
    session: AsyncSession,
    knowledge_id: str
) -> Optional[Knowledge]:
    """
    获取知识库条目
    
    Args:
        session: 数据库会话
        knowledge_id: 知识库条目 ID
        
    Returns:
        Knowledge 对象或 None
    """
    result = await session.execute(
        select(Knowledge).where(Knowledge.id == knowledge_id)
    )
    return result.scalar_one_or_none()


async def update_knowledge(
    session: AsyncSession,
    knowledge_id: str,
    title: Optional[str] = None,
    content: Optional[str] = None,
    summary: Optional[str] = None,
    status: Optional[KnowledgeStatus] = None,
    vector_id: Optional[str] = None,
    embedding_model: Optional[str] = None,
    metadata: Optional[dict] = None
) -> Optional[Knowledge]:
    """
    更新知识库条目
    
    Args:
        session: 数据库会话
        knowledge_id: 知识库条目 ID
        title: 标题（可选）
        content: 内容（可选）
        summary: 摘要（可选）
        status: 状态（可选）
        vector_id: 向量 ID（可选）
        embedding_model: 嵌入模型（可选）
        metadata: 元数据（可选，会合并）
        
    Returns:
        更新后的 Knowledge 对象或 None
    """
    knowledge = await get_knowledge(session, knowledge_id)
    if not knowledge:
        return None
    
    if title is not None:
        knowledge.title = title
    if content is not None:
        knowledge.content = content
        knowledge.char_count = len(content)
        knowledge.token_count = len(content) // 4
    if summary is not None:
        knowledge.summary = summary
    if status is not None:
        knowledge.status = status
        if status == KnowledgeStatus.READY:
            knowledge.indexed_at = datetime.now()
    if vector_id is not None:
        knowledge.vector_id = vector_id
    if embedding_model is not None:
        knowledge.embedding_model = embedding_model
    if metadata is not None:
        existing = knowledge.extra_data or {}
        existing.update(metadata)
        knowledge.extra_data = existing
    
    knowledge.updated_at = datetime.now()
    
    await session.commit()
    await session.refresh(knowledge)
    
    return knowledge


async def delete_knowledge(
    session: AsyncSession,
    knowledge_id: str
) -> bool:
    """
    删除知识库条目
    
    Args:
        session: 数据库会话
        knowledge_id: 知识库条目 ID
        
    Returns:
        是否删除成功
    """
    knowledge = await get_knowledge(session, knowledge_id)
    if not knowledge:
        return False
    
    await session.delete(knowledge)
    await session.commit()
    
    return True


async def list_knowledge_by_user(
    session: AsyncSession,
    user_id: str,
    type: Optional[KnowledgeType] = None,
    status: Optional[KnowledgeStatus] = None,
    limit: int = 20,
    offset: int = 0,
    order_by: str = "created_at",
    order_desc: bool = True
) -> List[Knowledge]:
    """
    获取用户的知识库列表
    
    Args:
        session: 数据库会话
        user_id: 用户 ID
        type: 类型过滤（可选）
        status: 状态过滤（可选）
        limit: 每页数量
        offset: 偏移量
        order_by: 排序字段
        order_desc: 是否降序
        
    Returns:
        Knowledge 列表
    """
    query = select(Knowledge).where(Knowledge.user_id == user_id)
    
    if type:
        query = query.where(Knowledge.type == type)
    if status:
        query = query.where(Knowledge.status == status)
    
    # 排序
    order_column = getattr(Knowledge, order_by, Knowledge.created_at)
    if order_desc:
        query = query.order_by(order_column.desc())
    else:
        query = query.order_by(order_column.asc())
    
    query = query.limit(limit).offset(offset)
    
    result = await session.execute(query)
    return list(result.scalars().all())


async def count_knowledge_by_user(
    session: AsyncSession,
    user_id: str,
    type: Optional[KnowledgeType] = None,
    status: Optional[KnowledgeStatus] = None
) -> int:
    """
    统计用户的知识库数量
    
    Args:
        session: 数据库会话
        user_id: 用户 ID
        type: 类型过滤（可选）
        status: 状态过滤（可选）
        
    Returns:
        数量
    """
    query = select(func.count(Knowledge.id)).where(Knowledge.user_id == user_id)
    
    if type:
        query = query.where(Knowledge.type == type)
    if status:
        query = query.where(Knowledge.status == status)
    
    result = await session.execute(query)
    return result.scalar() or 0


async def search_knowledge(
    session: AsyncSession,
    user_id: str,
    keyword: str,
    limit: int = 10
) -> List[Knowledge]:
    """
    搜索知识库（简单文本匹配）
    
    Args:
        session: 数据库会话
        user_id: 用户 ID
        keyword: 关键词
        limit: 返回数量
        
    Returns:
        匹配的 Knowledge 列表
        
    Note:
        这是简单的 LIKE 搜索，生产环境建议使用向量搜索
    """
    query = select(Knowledge).where(
        and_(
            Knowledge.user_id == user_id,
            Knowledge.status == KnowledgeStatus.READY,
            or_(
                Knowledge.title.ilike(f"%{keyword}%"),
                Knowledge.content.ilike(f"%{keyword}%"),
                Knowledge.summary.ilike(f"%{keyword}%")
            )
        )
    ).limit(limit)
    
    result = await session.execute(query)
    return list(result.scalars().all())


async def get_knowledge_by_file(
    session: AsyncSession,
    file_id: str
) -> List[Knowledge]:
    """
    获取来源于指定文件的知识库条目
    
    Args:
        session: 数据库会话
        file_id: 文件 ID
        
    Returns:
        Knowledge 列表
    """
    query = select(Knowledge).where(Knowledge.file_id == file_id)
    result = await session.execute(query)
    return list(result.scalars().all())


async def bulk_update_status(
    session: AsyncSession,
    knowledge_ids: List[str],
    status: KnowledgeStatus
) -> int:
    """
    批量更新知识库状态
    
    Args:
        session: 数据库会话
        knowledge_ids: 知识库 ID 列表
        status: 新状态
        
    Returns:
        更新的数量
    """
    if not knowledge_ids:
        return 0
    
    query = select(Knowledge).where(Knowledge.id.in_(knowledge_ids))
    result = await session.execute(query)
    knowledge_list = list(result.scalars().all())
    
    for knowledge in knowledge_list:
        knowledge.status = status
        knowledge.updated_at = datetime.now()
        if status == KnowledgeStatus.READY:
            knowledge.indexed_at = datetime.now()
    
    await session.commit()
    
    return len(knowledge_list)

