"""
Mem0 记忆更新任务 - 更新用户的长期记忆

触发条件：
- 有用户 ID

实现：
- 单用户记忆更新
- 批量更新（定时任务用）
- 数据库查询
- 情绪聚合
"""

import asyncio
import json
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from logger import get_logger

from ..context import Mem0BatchUpdateResult, Mem0UpdateResult
from ..registry import background_task

if TYPE_CHECKING:
    from ..context import TaskContext
    from ..service import BackgroundTaskService

logger = get_logger("background_tasks.mem0_update")


@background_task("mem0_update")
async def update_mem0_memories_task(ctx: "TaskContext", service: "BackgroundTaskService") -> None:
    """
    Mem0 记忆更新任务

    更新用户在最近一段时间内的会话记忆
    """
    if not ctx.user_id:
        logger.debug("○ 跳过 Mem0 更新（无用户 ID）")
        return

    # Check mem0_enabled config before proceeding
    try:
        import os
        import yaml
        from utils.app_paths import get_instances_dir
        _inst = os.getenv("AGENT_INSTANCE", "default")
        _cfg_path = get_instances_dir() / _inst / "config" / "memory.yaml"
        if _cfg_path.exists():
            with open(_cfg_path) as _f:
                _mem_section = (yaml.safe_load(_f) or {}).get("memory", {})
            if not _mem_section.get("mem0_enabled", True):
                logger.debug("○ 跳过 Mem0 更新（mem0_enabled=false）")
                return
            if not _mem_section.get("enabled", True):
                logger.debug("○ 跳过 Mem0 更新（memory.enabled=false）")
                return
    except Exception:
        pass  # Fallback: continue with update

    await update_user_memories(
        user_id=ctx.user_id,
        since_hours=24,
        session_id=ctx.session_id,
        event_manager=ctx.event_manager,
        service=service,
    )


# ==================== 单用户记忆更新 ====================


async def update_user_memories(
    user_id: str,
    since_hours: int = 24,
    session_id: Optional[str] = None,
    event_manager=None,
    service: "BackgroundTaskService" = None,
) -> Mem0UpdateResult:
    """
    更新单个用户的 Mem0 记忆（后台任务）

    从数据库获取用户在指定时间范围内的会话，提取记忆并更新
    """
    start_time = datetime.now()

    try:
        logger.info(f"🧠 开始更新用户记忆: user_id={user_id}, since={since_hours}h")

        pool = service.get_mem0_pool() if service else None
        if not pool:
            return Mem0UpdateResult(
                user_id=user_id,
                success=False,
                error="mem0 模块未安装",
                duration_ms=_calc_duration_ms(start_time),
            )

        # 获取用户会话
        since = datetime.now() - timedelta(hours=since_hours)
        conversations = await _fetch_user_conversations(user_id, since)

        if not conversations:
            logger.info(f"○ 用户 {user_id} 无需更新（无符合条件的会话）")
            return Mem0UpdateResult(
                user_id=user_id,
                success=True,
                memories_added=0,
                conversations_processed=0,
                duration_ms=_calc_duration_ms(start_time),
            )

        # 提取所有消息
        all_messages = []
        for conv in conversations:
            all_messages.extend(conv.get("messages", []))

        if not all_messages:
            return Mem0UpdateResult(
                user_id=user_id,
                success=True,
                memories_added=0,
                conversations_processed=len(conversations),
                duration_ms=_calc_duration_ms(start_time),
            )

        # 调用 Mem0 添加记忆（在线程池中执行）
        result = await asyncio.to_thread(pool.add, user_id=user_id, messages=all_messages)

        memories_added = len(result.get("results", []))

        logger.info(
            f"✅ 用户 {user_id} 记忆更新完成: "
            f"会话数={len(conversations)}, 消息数={len(all_messages)}, "
            f"新增记忆={memories_added}"
        )

        return Mem0UpdateResult(
            user_id=user_id,
            success=True,
            memories_added=memories_added,
            conversations_processed=len(conversations),
            duration_ms=_calc_duration_ms(start_time),
        )

    except Exception as e:
        logger.warning(f"⚠️ 更新用户记忆失败: user_id={user_id}, error={str(e)}")
        return Mem0UpdateResult(
            user_id=user_id, success=False, error=str(e), duration_ms=_calc_duration_ms(start_time)
        )


# ==================== 批量记忆更新 ====================


async def batch_update_all_memories(
    since_hours: int = 24, max_concurrent: int = 5, service: "BackgroundTaskService" = None
) -> Mem0BatchUpdateResult:
    """
    批量更新所有用户的 Mem0 记忆（后台任务）

    典型用途：定时任务（如凌晨批量处理当天会话）
    """
    batch_result = Mem0BatchUpdateResult(
        total_users=0, successful=0, failed=0, start_time=datetime.now()
    )

    try:
        logger.info(
            f"🚀 开始批量更新用户记忆: since={since_hours}h, max_concurrent={max_concurrent}"
        )

        pool = service.get_mem0_pool() if service else None
        if not pool:
            batch_result.failed = 1
            batch_result.end_time = datetime.now()
            batch_result.results.append(
                Mem0UpdateResult(user_id="batch", success=False, error="mem0 模块未安装")
            )
            return batch_result

        # 获取所有用户的会话
        since = datetime.now() - timedelta(hours=since_hours)
        user_conversations = await _fetch_all_user_conversations(since)

        if not user_conversations:
            logger.info(f"○ 无需更新（无符合条件的会话）")
            batch_result.end_time = datetime.now()
            return batch_result

        batch_result.total_users = len(user_conversations)

        # 使用信号量控制并发
        semaphore = asyncio.Semaphore(max_concurrent)

        async def update_with_limit(user_id: str, convs: List[Dict]):
            async with semaphore:
                return await _update_user_memories_internal(user_id, convs, service)

        # 并发执行
        tasks = [update_with_limit(user_id, convs) for user_id, convs in user_conversations.items()]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, Exception):
                batch_result.failed += 1
                batch_result.results.append(
                    Mem0UpdateResult(user_id="unknown", success=False, error=str(result))
                )
            elif isinstance(result, Mem0UpdateResult):
                batch_result.results.append(result)
                if result.success:
                    batch_result.successful += 1
                    batch_result.total_memories_added += result.memories_added
                else:
                    batch_result.failed += 1

        batch_result.end_time = datetime.now()

        logger.info(
            f"✅ 批量更新完成: "
            f"总数={batch_result.total_users}, "
            f"成功={batch_result.successful}, "
            f"失败={batch_result.failed}, "
            f"新增记忆={batch_result.total_memories_added}, "
            f"耗时={batch_result.duration_seconds:.2f}s"
        )

        # 情绪聚合：为成功更新的用户生成周汇总
        await _aggregate_weekly_summaries(
            user_ids=[r.user_id for r in batch_result.results if r.success], pool=pool
        )

        return batch_result

    except Exception as e:
        logger.warning(f"⚠️ 批量更新失败: {str(e)}")
        batch_result.failed = 1
        batch_result.end_time = datetime.now()
        batch_result.results.append(Mem0UpdateResult(user_id="batch", success=False, error=str(e)))
        return batch_result


async def _update_user_memories_internal(
    user_id: str, conversations: List[Dict[str, Any]], service: "BackgroundTaskService"
) -> Mem0UpdateResult:
    """内部方法：更新单用户记忆（已有会话数据）"""
    start_time = datetime.now()

    try:
        pool = service.get_mem0_pool() if service else None
        if not pool:
            return Mem0UpdateResult(
                user_id=user_id,
                success=False,
                error="mem0 模块未安装",
                duration_ms=_calc_duration_ms(start_time),
            )

        all_messages = []
        for conv in conversations:
            all_messages.extend(conv.get("messages", []))

        if not all_messages:
            return Mem0UpdateResult(
                user_id=user_id,
                success=True,
                memories_added=0,
                conversations_processed=len(conversations),
                duration_ms=_calc_duration_ms(start_time),
            )

        result = await asyncio.to_thread(pool.add, user_id=user_id, messages=all_messages)

        memories_added = len(result.get("results", []))

        return Mem0UpdateResult(
            user_id=user_id,
            success=True,
            memories_added=memories_added,
            conversations_processed=len(conversations),
            duration_ms=_calc_duration_ms(start_time),
        )

    except Exception as e:
        return Mem0UpdateResult(
            user_id=user_id, success=False, error=str(e), duration_ms=_calc_duration_ms(start_time)
        )


# ==================== 数据库查询 ====================


async def _fetch_user_conversations(user_id: str, since: datetime) -> List[Dict[str, Any]]:
    """从数据库获取单个用户的会话"""
    try:
        # TODO: 迁移到 local_store
        from infra.database import AsyncSessionLocal, crud
    except ImportError:
        logger.warning("⚠️ 数据库模块已删除，无法获取用户会话")
        return []

    try:
        async with AsyncSessionLocal() as session:
            conversations = await crud.get_conversations_since(
                session, since=since, user_id=user_id
            )

            result = []
            for conv in conversations:
                messages = await crud.get_messages_by_conversation(session, conversation_id=conv.id)
                result.append(
                    {
                        "id": conv.id,
                        "created_at": conv.created_at.isoformat() if conv.created_at else None,
                        "messages": [
                            {"role": msg.role, "content": msg.content} for msg in messages
                        ],
                    }
                )

            return result

    except Exception as e:
        logger.warning(f"⚠️ 获取用户会话失败: {e}")
        return []


async def _fetch_all_user_conversations(since: datetime) -> Dict[str, List[Dict[str, Any]]]:
    """从数据库获取所有用户的会话（按用户分组）"""
    try:
        # TODO: 迁移到 local_store
        from infra.database import AsyncSessionLocal, crud
    except ImportError:
        logger.warning("⚠️ 数据库模块已删除，无法获取所有用户会话")
        return {}

    try:
        async with AsyncSessionLocal() as session:
            conversations = await crud.get_conversations_since(session, since=since)

            user_conversations: Dict[str, List[Dict[str, Any]]] = {}

            for conv in conversations:
                user_id = conv.user_id
                if not user_id:
                    continue

                messages = await crud.get_messages_by_conversation(session, conversation_id=conv.id)

                conv_data = {
                    "id": conv.id,
                    "created_at": conv.created_at.isoformat() if conv.created_at else None,
                    "messages": [{"role": msg.role, "content": msg.content} for msg in messages],
                }

                if user_id not in user_conversations:
                    user_conversations[user_id] = []
                user_conversations[user_id].append(conv_data)

            return user_conversations

    except Exception as e:
        logger.warning(f"⚠️ 获取所有用户会话失败: {e}")
        return {}


# ==================== 情绪聚合 ====================


async def _aggregate_weekly_summaries(user_ids: List[str], pool) -> None:
    """
    为用户生成周汇总（情绪 + 工作重点）

    在批量更新后调用，将聚合结果存入 Mem0

    Args:
        user_ids: 需要聚合的用户 ID 列表
        pool: Mem0 Pool 实例
    """
    if not user_ids:
        return

    try:
        from core.memory.mem0.aggregator import (
            aggregate_user_emotion,
            aggregate_work_summary,
        )

        # 计算本周时间窗口
        today = datetime.now()
        start_of_week = today - timedelta(days=today.weekday())
        start_of_week = start_of_week.replace(hour=0, minute=0, second=0, microsecond=0)

        logger.info(f"📊 开始情绪聚合: {len(user_ids)} 个用户")

        for user_id in user_ids:
            try:
                # 检索用户记忆
                memories = pool.get_all(user_id=user_id, limit=100)

                if not memories:
                    continue

                # 聚合情绪
                emotion_result = await aggregate_user_emotion(
                    user_id=user_id, start_date=start_of_week, end_date=today, memories=memories
                )

                # 聚合工作重点
                work_result = await aggregate_work_summary(
                    user_id=user_id, start_date=start_of_week, end_date=today, memories=memories
                )

                # 存储情绪摘要
                if emotion_result.get("summary") and emotion_result.get("dominant") != "neutral":
                    pool.add(
                        user_id=user_id,
                        messages=[
                            {"role": "user", "content": f"[情绪摘要] {emotion_result['summary']}"}
                        ],
                        metadata={
                            "type": "emotion_weekly",
                            "time_window": emotion_result.get("time_window"),
                            "dominant": emotion_result.get("dominant"),
                        },
                    )

                # 存储工作摘要
                if work_result.get("summary") and work_result.get("highlights"):
                    pool.add(
                        user_id=user_id,
                        messages=[
                            {"role": "user", "content": f"[工作摘要] {work_result['summary']}"}
                        ],
                        metadata={
                            "type": "work_weekly",
                            "time_window": work_result.get("time_window"),
                            "next_steps": work_result.get("next_steps", []),
                        },
                    )

                logger.debug(f"  ✓ 用户 {user_id} 聚合完成")

            except Exception as e:
                logger.warning(f"  ⚠️ 用户 {user_id} 聚合失败: {e}")
                continue

        logger.info(f"✅ 情绪聚合完成")

    except ImportError:
        logger.debug("情绪聚合模块未加载，跳过")
    except Exception as e:
        logger.warning(f"⚠️ 情绪聚合失败: {e}")


# ==================== 工具方法 ====================


def _calc_duration_ms(start_time: datetime) -> int:
    """计算耗时（毫秒）"""
    return int((datetime.now() - start_time).total_seconds() * 1000)
