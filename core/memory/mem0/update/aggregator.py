"""
Mem0 数据聚合器

职责：
- 聚合用户指定时间段的情绪轨迹
- 生成带明确时间窗口的摘要
- 支持工作重点、任务进度等聚合

设计原则：
- 时间窗口必须明确，禁止使用模糊词
- 日期格式：X月X日(星期几)
- 异步执行，不阻塞主流程
"""

# 1. 标准库
import json
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

# 3. 本地模块
from core.llm import Message, create_llm_service
from core.memory.mem0.pool import get_mem0_pool
from logger import get_logger

# 2. 第三方库（无）


logger = get_logger("memory.mem0.aggregator")


# ==================== 工具函数 ====================

WEEKDAYS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def format_date_with_weekday(dt: datetime) -> str:
    """
    格式化日期：X月X日(星期几)

    Args:
        dt: datetime 对象

    Returns:
        格式化字符串，如 "1月6日(周一)"
    """
    return f"{dt.month}月{dt.day}日({WEEKDAYS[dt.weekday()]})"


def format_time_window(start: datetime, end: datetime) -> Dict[str, str]:
    """
    格式化时间窗口

    Args:
        start: 开始日期
        end: 结束日期

    Returns:
        时间窗口字典
    """
    return {
        "start": start.strftime("%Y-%m-%d"),
        "end": end.strftime("%Y-%m-%d"),
        "start_weekday": WEEKDAYS[start.weekday()],
        "end_weekday": WEEKDAYS[end.weekday()],
        "display": f"{format_date_with_weekday(start)} - {format_date_with_weekday(end)}",
    }


# ==================== 情绪聚合 ====================

EMOTION_AGGREGATION_PROMPT = """你是用户情绪分析专家。请根据以下用户在指定时间段的记忆，生成情绪轨迹摘要。

时间范围: {time_window}

用户记忆:
{memories}

请分析并输出 JSON 格式（只输出 JSON，不要其他文字）:
{{
    "trajectory": [
        {{"date": "2026-01-06", "weekday": "周一", "emotion": "stressed", "context": "KPI压力"}},
        {{"date": "2026-01-07", "weekday": "周二", "emotion": "positive", "context": "方案获批"}}
    ],
    "summary": "1月6日(周一)至1月10日(周五)期间：周一因KPI压力情绪紧张，周二方案获批后转为积极，整体状态偏正面",
    "dominant": "positive"
}}

重要规则：
1. summary 中必须使用"X月X日(星期几)"格式，禁止使用"本周"、"这周"、"最近"等模糊词
2. 每个情绪变化都要有具体日期和原因
3. dominant 是这段时间的主导情绪
4. 如果记忆中没有明显情绪信息，返回 {{"trajectory": [], "summary": "该时间段无明显情绪记录", "dominant": "neutral"}}"""


async def aggregate_user_emotion(
    user_id: str,
    start_date: datetime,
    end_date: datetime,
    memories: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    聚合用户指定时间段的情绪轨迹

    关键要求：时间窗口必须明确，禁止使用模糊词

    Args:
        user_id: 用户 ID
        start_date: 开始日期
        end_date: 结束日期
        memories: 可选，已检索的记忆列表（如果不提供则自动检索）

    Returns:
        {
            "time_window": {
                "start": "2026-01-06",
                "end": "2026-01-10",
                "display": "1月6日(周一) - 1月10日(周五)"
            },
            "trajectory": [...],
            "summary": "1月6日(周一)至1月10日(周五)期间：...",
            "dominant": "positive"
        }
    """
    time_window = format_time_window(start_date, end_date)

    # 如果没有提供记忆，则检索
    if memories is None:
        try:
            from core.memory.mem0.pool import get_mem0_pool

            pool = get_mem0_pool()
            # 检索该时间段的所有记忆
            memories = pool.get_all(user_id=user_id, limit=100)
            # TODO: 按时间过滤（需要 metadata 中有时间戳）
        except Exception as e:
            logger.error(f"[Aggregator] 检索记忆失败: {e}")
            memories = []

    if not memories:
        return {
            "time_window": time_window,
            "trajectory": [],
            "summary": f"{time_window['display']}期间无记录",
            "dominant": "neutral",
        }

    # 格式化记忆
    memory_texts = []
    for mem in memories:
        content = mem.get("memory", "")
        if content:
            memory_texts.append(f"- {content}")

    if not memory_texts:
        return {
            "time_window": time_window,
            "trajectory": [],
            "summary": f"{time_window['display']}期间无有效记录",
            "dominant": "neutral",
        }

    try:
        # 构建 Prompt
        prompt = EMOTION_AGGREGATION_PROMPT.format(
            time_window=time_window["display"], memories="\n".join(memory_texts)
        )

        # 调用 LLM
        llm = create_llm_service(model="claude-haiku-4-5-20251001")
        response = await llm.create_message_async(
            messages=[Message(role="user", content=prompt)],
            system="你是情绪分析专家，只输出 JSON 格式结果。",
        )

        # 解析响应
        result_text = response.content.strip()

        # 提取 JSON
        if "```json" in result_text:
            result_text = result_text.split("```json")[1].split("```")[0].strip()
        elif "```" in result_text:
            result_text = result_text.split("```")[1].split("```")[0].strip()

        result = json.loads(result_text)
        result["time_window"] = time_window

        logger.info(
            f"[Aggregator] 情绪聚合完成: user={user_id}, "
            f"时间={time_window['display']}, 主导情绪={result.get('dominant', 'unknown')}"
        )
        return result

    except json.JSONDecodeError as e:
        logger.warning(f"[Aggregator] JSON 解析失败: {e}")
        return {
            "time_window": time_window,
            "trajectory": [],
            "summary": f"{time_window['display']}期间情绪分析失败",
            "dominant": "unknown",
        }
    except Exception as e:
        logger.error(f"[Aggregator] 情绪聚合失败: {e}")
        return {
            "time_window": time_window,
            "trajectory": [],
            "summary": f"{time_window['display']}期间情绪分析失败",
            "dominant": "unknown",
        }


# ==================== 工作重点聚合 ====================

WORK_SUMMARY_PROMPT = """你是工作总结专家。请根据以下用户在指定时间段的记忆，生成工作重点摘要。

时间范围: {time_window}

用户记忆:
{memories}

请分析并输出 JSON 格式（只输出 JSON，不要其他文字）:
{{
    "highlights": [
        {{"date": "1月6日(周一)", "event": "永辉超市合同签约", "result": "成功", "amount": "150万"}},
        {{"date": "1月8日(周三)", "event": "撰写周报", "result": "完成"}}
    ],
    "summary": "1月6日(周一)至1月10日(周五)工作重点：周一成功签署永辉超市合同(金额150万)，周三完成周报撰写",
    "next_steps": ["跟进美团项目"]
}}

重要规则：
1. 使用"X月X日(星期几)"格式，禁止使用模糊词
2. 保留具体数字（金额、百分比等）
3. 保留人名和公司名"""


async def aggregate_work_summary(
    user_id: str,
    start_date: datetime,
    end_date: datetime,
    memories: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    聚合用户指定时间段的工作重点

    Args:
        user_id: 用户 ID
        start_date: 开始日期
        end_date: 结束日期
        memories: 可选，已检索的记忆列表

    Returns:
        工作重点摘要
    """
    time_window = format_time_window(start_date, end_date)

    # 如果没有提供记忆，则检索
    if memories is None:
        try:
            from core.memory.mem0.pool import get_mem0_pool

            pool = get_mem0_pool()
            memories = pool.get_all(user_id=user_id, limit=100)
        except Exception as e:
            logger.error(f"[Aggregator] 检索记忆失败: {e}")
            memories = []

    if not memories:
        return {
            "time_window": time_window,
            "highlights": [],
            "summary": f"{time_window['display']}期间无工作记录",
            "next_steps": [],
        }

    # 格式化记忆
    memory_texts = [f"- {m.get('memory', '')}" for m in memories if m.get("memory")]

    if not memory_texts:
        return {
            "time_window": time_window,
            "highlights": [],
            "summary": f"{time_window['display']}期间无有效工作记录",
            "next_steps": [],
        }

    try:
        # 构建 Prompt
        prompt = WORK_SUMMARY_PROMPT.format(
            time_window=time_window["display"], memories="\n".join(memory_texts)
        )

        # 调用 LLM
        llm = create_llm_service(model="claude-haiku-4-5-20251001")
        response = await llm.create_message_async(
            messages=[Message(role="user", content=prompt)],
            system="你是工作总结专家，只输出 JSON 格式结果。",
        )

        # 解析响应
        result_text = response.content.strip()

        # 提取 JSON
        if "```json" in result_text:
            result_text = result_text.split("```json")[1].split("```")[0].strip()
        elif "```" in result_text:
            result_text = result_text.split("```")[1].split("```")[0].strip()

        result = json.loads(result_text)
        result["time_window"] = time_window

        logger.info(
            f"[Aggregator] 工作摘要完成: user={user_id}, "
            f"时间={time_window['display']}, 重点事项={len(result.get('highlights', []))}"
        )
        return result

    except Exception as e:
        logger.error(f"[Aggregator] 工作摘要失败: {e}")
        return {
            "time_window": time_window,
            "highlights": [],
            "summary": f"{time_window['display']}期间工作摘要生成失败",
            "next_steps": [],
        }


# ==================== 便捷函数 ====================


async def aggregate_weekly_summary(user_id: str) -> Dict[str, Any]:
    """
    生成用户本周摘要（情绪 + 工作）

    Args:
        user_id: 用户 ID

    Returns:
        包含情绪和工作摘要的综合报告
    """
    # 计算本周时间窗口
    today = datetime.now()
    # 本周一
    start_of_week = today - timedelta(days=today.weekday())
    start_of_week = start_of_week.replace(hour=0, minute=0, second=0, microsecond=0)

    # 检索记忆
    try:
        pool = get_mem0_pool()
        memories = pool.get_all(user_id=user_id, limit=100)
    except Exception as e:
        logger.error(f"[Aggregator] 检索记忆失败: {e}")
        memories = []

    # 并行聚合
    import asyncio

    emotion_task = aggregate_user_emotion(user_id, start_of_week, today, memories)
    work_task = aggregate_work_summary(user_id, start_of_week, today, memories)

    emotion_result, work_result = await asyncio.gather(emotion_task, work_task)

    return {
        "time_window": format_time_window(start_of_week, today),
        "emotion": emotion_result,
        "work": work_result,
    }
