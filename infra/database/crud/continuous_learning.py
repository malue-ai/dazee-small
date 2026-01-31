"""
持续学习数据存储层

V9.4 新增

提供：
- SessionReward CRUD
- StepReward CRUD
- Playbook CRUD
- IntentCache CRUD
"""

import uuid
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Tuple

from sqlalchemy import select, update, delete, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from infra.database.models.continuous_learning import (
    SessionRewardRecord,
    StepRewardRecord,
    PlaybookRecord,
    IntentCacheRecord,
    PlaybookStatus,
    RewardSignal,
    AttributionMethod,
)
from logger import get_logger

logger = get_logger("continuous_learning_crud")


def generate_id() -> str:
    """生成唯一 ID"""
    return str(uuid.uuid4()).replace("-", "")[:16]


# ============================================================
# SessionReward CRUD
# ============================================================

async def create_session_reward(
    session: AsyncSession,
    session_id: str,
    total_reward: float,
    outcome_success: bool = True,
    attribution_method: AttributionMethod = AttributionMethod.DECAY,
    **kwargs
) -> SessionRewardRecord:
    """
    创建会话奖励记录
    
    Args:
        session: 数据库会话
        session_id: Agent 会话 ID
        total_reward: 总奖励值
        outcome_success: 是否成功
        attribution_method: 归因方法
        **kwargs: 其他字段
        
    Returns:
        SessionRewardRecord
    """
    record = SessionRewardRecord(
        id=generate_id(),
        session_id=session_id,
        total_reward=total_reward,
        outcome_success=outcome_success,
        attribution_method=attribution_method,
        **kwargs
    )
    
    session.add(record)
    await session.commit()
    await session.refresh(record)
    
    logger.info(f"📊 创建会话奖励记录: session={session_id}, reward={total_reward:.2f}")
    return record


async def get_session_reward(
    session: AsyncSession,
    record_id: str
) -> Optional[SessionRewardRecord]:
    """获取会话奖励记录"""
    result = await session.execute(
        select(SessionRewardRecord).where(SessionRewardRecord.id == record_id)
    )
    return result.scalar_one_or_none()


async def get_session_reward_by_session_id(
    session: AsyncSession,
    session_id: str
) -> Optional[SessionRewardRecord]:
    """根据会话 ID 获取奖励记录"""
    result = await session.execute(
        select(SessionRewardRecord)
        .where(SessionRewardRecord.session_id == session_id)
        .order_by(SessionRewardRecord.created_at.desc())
    )
    return result.scalar_one_or_none()


async def list_session_rewards(
    session: AsyncSession,
    min_reward: Optional[float] = None,
    task_type: Optional[str] = None,
    limit: int = 100,
    offset: int = 0
) -> List[SessionRewardRecord]:
    """
    列出会话奖励记录
    
    Args:
        session: 数据库会话
        min_reward: 最低奖励阈值
        task_type: 任务类型过滤
        limit: 返回数量
        offset: 偏移量
        
    Returns:
        SessionRewardRecord 列表
    """
    query = select(SessionRewardRecord)
    
    conditions = []
    if min_reward is not None:
        conditions.append(SessionRewardRecord.total_reward >= min_reward)
    if task_type:
        conditions.append(SessionRewardRecord.task_type == task_type)
    
    if conditions:
        query = query.where(and_(*conditions))
    
    query = query.order_by(SessionRewardRecord.created_at.desc())
    query = query.limit(limit).offset(offset)
    
    result = await session.execute(query)
    return list(result.scalars().all())


async def get_high_quality_sessions(
    session: AsyncSession,
    min_reward: float = 0.8,
    limit: int = 50
) -> List[SessionRewardRecord]:
    """
    获取高质量会话（用于策略提取）
    
    Args:
        session: 数据库会话
        min_reward: 最低奖励阈值
        limit: 返回数量
        
    Returns:
        高质量会话列表
    """
    result = await session.execute(
        select(SessionRewardRecord)
        .where(
            and_(
                SessionRewardRecord.total_reward >= min_reward,
                SessionRewardRecord.outcome_success == True
            )
        )
        .order_by(SessionRewardRecord.total_reward.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


# ============================================================
# StepReward CRUD
# ============================================================

async def create_step_reward(
    session: AsyncSession,
    session_reward_id: str,
    step_index: int,
    action_type: str,
    action_name: str,
    reward_value: float = 0.0,
    **kwargs
) -> StepRewardRecord:
    """创建步骤奖励记录"""
    record = StepRewardRecord(
        id=generate_id(),
        session_reward_id=session_reward_id,
        step_index=step_index,
        action_type=action_type,
        action_name=action_name,
        reward_value=reward_value,
        **kwargs
    )
    
    session.add(record)
    await session.commit()
    await session.refresh(record)
    
    return record


async def create_step_rewards_batch(
    session: AsyncSession,
    session_reward_id: str,
    steps: List[Dict[str, Any]]
) -> List[StepRewardRecord]:
    """
    批量创建步骤奖励记录
    
    Args:
        session: 数据库会话
        session_reward_id: 会话奖励 ID
        steps: 步骤数据列表
        
    Returns:
        StepRewardRecord 列表
    """
    records = []
    for step in steps:
        record = StepRewardRecord(
            id=generate_id(),
            session_reward_id=session_reward_id,
            **step
        )
        records.append(record)
        session.add(record)
    
    await session.commit()
    
    for record in records:
        await session.refresh(record)
    
    logger.debug(f"📊 批量创建 {len(records)} 条步骤奖励记录")
    return records


async def get_step_rewards_by_session(
    session: AsyncSession,
    session_reward_id: str
) -> List[StepRewardRecord]:
    """获取会话的所有步骤奖励"""
    result = await session.execute(
        select(StepRewardRecord)
        .where(StepRewardRecord.session_reward_id == session_reward_id)
        .order_by(StepRewardRecord.step_index)
    )
    return list(result.scalars().all())


async def get_critical_steps(
    session: AsyncSession,
    session_reward_id: str
) -> List[StepRewardRecord]:
    """获取关键步骤"""
    result = await session.execute(
        select(StepRewardRecord)
        .where(
            and_(
                StepRewardRecord.session_reward_id == session_reward_id,
                StepRewardRecord.is_critical == True
            )
        )
        .order_by(StepRewardRecord.step_index)
    )
    return list(result.scalars().all())


# ============================================================
# Playbook CRUD
# ============================================================

async def create_playbook(
    session: AsyncSession,
    name: str,
    description: str,
    trigger: Dict[str, Any],
    strategy: Dict[str, Any],
    tool_sequence: List[Dict[str, Any]] = None,
    quality_metrics: Dict[str, float] = None,
    source: str = "auto",
    source_session_id: str = None
) -> PlaybookRecord:
    """
    创建策略记录
    
    Args:
        session: 数据库会话
        name: 策略名称
        description: 描述
        trigger: 触发条件
        strategy: 执行策略
        tool_sequence: 工具序列
        quality_metrics: 质量指标
        source: 来源
        source_session_id: 来源会话 ID
        
    Returns:
        PlaybookRecord
    """
    record = PlaybookRecord(
        id=generate_id(),
        name=name,
        description=description,
        trigger=trigger,
        strategy=strategy,
        tool_sequence=tool_sequence or [],
        quality_metrics=quality_metrics or {},
        source=source,
        source_session_id=source_session_id,
        status=PlaybookStatus.DRAFT if source == "auto" else PlaybookStatus.PENDING_REVIEW
    )
    
    session.add(record)
    await session.commit()
    await session.refresh(record)
    
    logger.info(f"📝 创建策略记录: name={name}, source={source}")
    return record


async def get_playbook(
    session: AsyncSession,
    playbook_id: str
) -> Optional[PlaybookRecord]:
    """获取策略记录"""
    result = await session.execute(
        select(PlaybookRecord).where(PlaybookRecord.id == playbook_id)
    )
    return result.scalar_one_or_none()


async def list_playbooks(
    session: AsyncSession,
    status: Optional[PlaybookStatus] = None,
    source: Optional[str] = None,
    limit: int = 100,
    offset: int = 0
) -> List[PlaybookRecord]:
    """
    列出策略记录
    
    Args:
        session: 数据库会话
        status: 状态过滤
        source: 来源过滤
        limit: 返回数量
        offset: 偏移量
        
    Returns:
        PlaybookRecord 列表
    """
    query = select(PlaybookRecord)
    
    conditions = []
    if status:
        conditions.append(PlaybookRecord.status == status)
    if source:
        conditions.append(PlaybookRecord.source == source)
    
    if conditions:
        query = query.where(and_(*conditions))
    
    query = query.order_by(PlaybookRecord.created_at.desc())
    query = query.limit(limit).offset(offset)
    
    result = await session.execute(query)
    return list(result.scalars().all())


async def get_approved_playbooks(
    session: AsyncSession
) -> List[PlaybookRecord]:
    """获取所有已审核通过的策略"""
    result = await session.execute(
        select(PlaybookRecord)
        .where(PlaybookRecord.status == PlaybookStatus.APPROVED)
        .order_by(PlaybookRecord.usage_count.desc())
    )
    return list(result.scalars().all())


async def update_playbook_status(
    session: AsyncSession,
    playbook_id: str,
    status: PlaybookStatus,
    reviewer: str = None,
    notes: str = None
) -> Optional[PlaybookRecord]:
    """
    更新策略状态
    
    Args:
        session: 数据库会话
        playbook_id: 策略 ID
        status: 新状态
        reviewer: 审核人
        notes: 审核备注
        
    Returns:
        更新后的 PlaybookRecord
    """
    record = await get_playbook(session, playbook_id)
    if not record:
        return None
    
    record.status = status
    if reviewer:
        record.reviewed_by = reviewer
    if notes:
        record.review_notes = notes
    if status in (PlaybookStatus.APPROVED, PlaybookStatus.REJECTED):
        record.reviewed_at = datetime.now()
    
    await session.commit()
    await session.refresh(record)
    
    logger.info(f"📝 更新策略状态: id={playbook_id}, status={status.value}")
    return record


async def increment_playbook_usage(
    session: AsyncSession,
    playbook_id: str
) -> None:
    """增加策略使用次数"""
    await session.execute(
        update(PlaybookRecord)
        .where(PlaybookRecord.id == playbook_id)
        .values(
            usage_count=PlaybookRecord.usage_count + 1,
            last_used_at=datetime.now()
        )
    )
    await session.commit()


async def find_matching_playbooks(
    session: AsyncSession,
    task_type: str,
    complexity_score: float,
    keywords: List[str] = None,
    top_k: int = 3
) -> List[Tuple[PlaybookRecord, float]]:
    """
    查找匹配的策略
    
    简化版匹配：仅基于 task_type 过滤，后续在内存中计算匹配分数
    
    Args:
        session: 数据库会话
        task_type: 任务类型
        complexity_score: 复杂度评分
        keywords: 关键词列表
        top_k: 返回前 k 个
        
    Returns:
        [(PlaybookRecord, 匹配分数), ...]
    """
    # 获取所有已审核策略
    playbooks = await get_approved_playbooks(session)
    
    # 计算匹配分数
    candidates = []
    for playbook in playbooks:
        score = 0.0
        max_score = 0.0
        
        trigger = playbook.trigger or {}
        
        # 任务类型匹配
        if "task_types" in trigger:
            max_score += 1.0
            if task_type in trigger["task_types"]:
                score += 1.0
        
        # 复杂度范围匹配
        if "complexity_range" in trigger:
            max_score += 1.0
            range_min, range_max = trigger["complexity_range"]
            if range_min <= complexity_score <= range_max:
                score += 1.0
        
        # 关键词匹配
        if keywords and "keywords" in trigger:
            max_score += 1.0
            trigger_keywords = trigger["keywords"]
            matched = sum(1 for kw in keywords if kw.lower() in [k.lower() for k in trigger_keywords])
            if trigger_keywords:
                score += matched / len(trigger_keywords)
        
        final_score = score / max_score if max_score > 0 else 0.0
        if final_score > 0:
            candidates.append((playbook, final_score))
    
    # 按分数排序
    candidates.sort(key=lambda x: x[1], reverse=True)
    
    return candidates[:top_k]


async def delete_playbook(
    session: AsyncSession,
    playbook_id: str
) -> bool:
    """删除策略"""
    result = await session.execute(
        delete(PlaybookRecord).where(PlaybookRecord.id == playbook_id)
    )
    await session.commit()
    return result.rowcount > 0


# ============================================================
# IntentCache CRUD
# ============================================================

async def create_intent_cache(
    session: AsyncSession,
    query_hash: str,
    query_text: str,
    embedding: List[float],
    intent_result: Dict[str, Any],
    ttl_hours: int = 24
) -> IntentCacheRecord:
    """
    创建意图缓存记录
    
    Args:
        session: 数据库会话
        query_hash: 查询 hash
        query_text: 查询文本
        embedding: 向量
        intent_result: 意图结果
        ttl_hours: 过期时间（小时）
        
    Returns:
        IntentCacheRecord
    """
    record = IntentCacheRecord(
        id=generate_id(),
        query_hash=query_hash,
        query_text=query_text,
        embedding=embedding,
        intent_result=intent_result,
        expires_at=datetime.now() + timedelta(hours=ttl_hours)
    )
    
    session.add(record)
    await session.commit()
    await session.refresh(record)
    
    return record


async def get_intent_cache_by_hash(
    session: AsyncSession,
    query_hash: str
) -> Optional[IntentCacheRecord]:
    """根据 hash 获取意图缓存"""
    result = await session.execute(
        select(IntentCacheRecord)
        .where(
            and_(
                IntentCacheRecord.query_hash == query_hash,
                or_(
                    IntentCacheRecord.expires_at == None,
                    IntentCacheRecord.expires_at > datetime.now()
                )
            )
        )
    )
    record = result.scalar_one_or_none()
    
    if record:
        # 更新命中次数
        await session.execute(
            update(IntentCacheRecord)
            .where(IntentCacheRecord.id == record.id)
            .values(
                hit_count=IntentCacheRecord.hit_count + 1,
                last_hit_at=datetime.now()
            )
        )
        await session.commit()
    
    return record


async def get_all_intent_cache_embeddings(
    session: AsyncSession,
    limit: int = 10000
) -> List[Tuple[str, List[float], Dict[str, Any]]]:
    """
    获取所有意图缓存的向量（用于相似度搜索）
    
    Returns:
        [(id, embedding, intent_result), ...]
    """
    result = await session.execute(
        select(
            IntentCacheRecord.id,
            IntentCacheRecord.embedding,
            IntentCacheRecord.intent_result
        )
        .where(
            or_(
                IntentCacheRecord.expires_at == None,
                IntentCacheRecord.expires_at > datetime.now()
            )
        )
        .limit(limit)
    )
    return [(row[0], row[1], row[2]) for row in result.all()]


async def cleanup_expired_intent_cache(
    session: AsyncSession
) -> int:
    """清理过期的意图缓存"""
    result = await session.execute(
        delete(IntentCacheRecord)
        .where(IntentCacheRecord.expires_at < datetime.now())
    )
    await session.commit()
    
    count = result.rowcount
    if count > 0:
        logger.info(f"🧹 清理 {count} 条过期意图缓存")
    
    return count


# ============================================================
# 统计查询
# ============================================================

async def get_learning_stats(
    session: AsyncSession
) -> Dict[str, Any]:
    """
    获取持续学习统计信息
    
    Returns:
        统计信息字典
    """
    # 会话奖励统计
    session_count = await session.execute(
        select(func.count(SessionRewardRecord.id))
    )
    session_total = session_count.scalar_one()
    
    avg_reward = await session.execute(
        select(func.avg(SessionRewardRecord.total_reward))
    )
    avg_reward_value = avg_reward.scalar_one() or 0.0
    
    # 策略统计
    playbook_stats = {}
    for status in PlaybookStatus:
        count = await session.execute(
            select(func.count(PlaybookRecord.id))
            .where(PlaybookRecord.status == status)
        )
        playbook_stats[status.value] = count.scalar_one()
    
    # 意图缓存统计
    cache_count = await session.execute(
        select(func.count(IntentCacheRecord.id))
    )
    cache_total = cache_count.scalar_one()
    
    total_hits = await session.execute(
        select(func.sum(IntentCacheRecord.hit_count))
    )
    total_hits_value = total_hits.scalar_one() or 0
    
    return {
        "session_rewards": {
            "total": session_total,
            "avg_reward": round(avg_reward_value, 4),
        },
        "playbooks": playbook_stats,
        "intent_cache": {
            "total": cache_total,
            "total_hits": total_hits_value,
        }
    }
