"""
Dazee 5W1H 行为分析器

基于 LLM 语义理解，从碎片记忆中聚合分析用户行为模式
5W1H: What（做什么）、When（什么时候）、Where（在哪里）、
      Who（和谁）、Why（为什么）、How（怎么做）

使用 llm_config 配置系统管理模型参数
"""

# 1. 标准库
import uuid
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

# 3. 本地模块
from core.llm import Message
from logger import get_logger

from ..schemas import (
    BehaviorPattern,
    Collaborator,
    ConflictDetection,
    DateRange,
    DayOfWeek,
    FragmentMemory,
    Motivation,
    PeriodicityAnalysis,
    PreferenceStability,
    RoutineTask,
    TimePattern,
    TimeSlot,
    WorkContext,
    WorkStyle,
)

# 2. 第三方库（无）


logger = get_logger("dazee.analyzer")


# ==================== LLM Profile 名称 ====================

ANALYZER_PROFILE_NAME = "behavior_analyzer"


# ==================== LLM Prompts ====================

BEHAVIOR_ANALYSIS_PROMPT = """你是 Dazee 智能助理的行为分析系统。请分析用户的碎片记忆，总结其工作行为模式（5W1H）。

## 碎片记忆数据
{fragments_json}

## 分析周期
{date_range}

## 请从 5W1H 角度分析并输出 JSON：

```json
{{
  "what": {{
    "routine_tasks": [
      {{
        "name": "常规任务名称（如：处理客户反馈）",
        "category": "任务类别",
        "frequency": "执行频率（daily/weekly/ad_hoc）",
        "avg_duration_hours": 预估平均耗时,
        "confidence": 0.0-1.0
      }}
    ],
    "main_work_focus": "主要工作重心描述"
  }},
  "when": {{
    "work_start": "通常开始工作时间（如 09:00）",
    "work_end": "通常结束工作时间（如 18:00）",
    "peak_hours": ["高效工作时段"],
    "meeting_slots": ["常见会议时段"],
    "preferred_deep_work_time": "偏好的深度工作时间段"
  }},
  "where": {{
    "primary_context": "主要工作场景（office/remote/hybrid）",
    "tools_mentioned": ["提到的工具/平台"]
  }},
  "who": {{
    "frequent_collaborators": [
      {{
        "name": "协作者名称或称呼",
        "relationship": "关系类型（supervisor/colleague/client）",
        "interaction_frequency": "互动频率（daily/weekly/occasionally）"
      }}
    ],
    "reporting_to": "汇报对象"
  }},
  "why": {{
    "primary_goals": ["主要工作目标"],
    "motivations": ["工作动力/驱动因素"],
    "pain_points": ["工作痛点/困扰"]
  }},
  "how": {{
    "work_style": "工作风格（structured/flexible/deadline_driven）",
    "communication_preference": "沟通偏好（async/sync/mixed）",
    "decision_style": "决策风格（data_driven/intuitive/collaborative）",
    "response_format_preference": "响应格式偏好（detailed/concise/structured）"
  }},
  "inferred_role": "推断的职业角色（product_manager/developer/sales/operations/designer/analyst/unknown）",
  "role_confidence": 0.0-1.0,
  "preference_stability": {{
    "stable_preferences": {{"偏好项": "偏好值"}},  // 多次出现一致的偏好
    "evolving_preferences": {{"偏好项": ["值1", "值2"]}},  // 随时间变化的偏好
    "preference_confidence": 0.0-1.0  // 偏好置信度
  }},
  "periodicity": {{
    "patterns": {{"任务名": {{"frequency": "daily/weekly", "days": [1,2,3]}}}},  // 周期模式
    "frequency_distribution": {{"daily": 3, "weekly": 1}},  // 频率分布
    "consistency_score": 0.0-1.0  // 一致性得分
  }},
  "conflict_detection": {{
    "detected_conflicts": [
      {{"type": "fact_contradiction/preference_change", "old": "旧值", "new": "新值", "confidence": 0.0-1.0}}
    ],
    "conflict_count": 0  // 冲突数量
  }}
}}
```

## 分析原则：
1. 只基于碎片记忆中的实际数据进行推断
2. 没有足够证据的字段设为 null 或空对象
3. confidence 反映推断的确定性
4. 偏好稳定性：分析偏好项是否多次一致出现，还是随时间变化
5. 周期性：分析任务和行为的周期性模式
6. 冲突检测：检测新旧事实或偏好的矛盾
7. 只输出 JSON

请分析："""


class BehaviorAnalyzer:
    """
    5W1H 行为分析器

    基于 LLM 语义理解，从碎片记忆中聚合分析用户行为模式
    """

    def __init__(self, profile_name: Optional[str] = None, **profile_overrides):
        """
        初始化行为分析器

        Args:
            profile_name: LLM Profile 名称，默认使用 "behavior_analyzer"
            **profile_overrides: 覆盖 Profile 中的参数
        """
        self.profile_name = profile_name or ANALYZER_PROFILE_NAME
        self._profile_overrides = profile_overrides
        self._profile: Optional[Dict[str, Any]] = None
        self._llm_service = None

        # 用户行为模式缓存（user_id -> BehaviorPattern）
        self._user_patterns: Dict[str, BehaviorPattern] = {}

        logger.info(f"[BehaviorAnalyzer] 初始化: profile={self.profile_name}")

    async def get_profile(self) -> Dict[str, Any]:
        """懒加载 LLM Profile 配置"""
        if self._profile is None:
            from config.llm_config import get_llm_profile

            self._profile = await get_llm_profile(self.profile_name, **self._profile_overrides)
            logger.info(f"[BehaviorAnalyzer] 加载配置: model={self._profile.get('model')}")
        return self._profile

    async def get_llm_service(self) -> Any:
        """懒加载 LLM 服务"""
        if self._llm_service is None:
            from core.llm import create_llm_service

            profile = await self.get_profile()
            self._llm_service = create_llm_service(**profile)
        return self._llm_service

    async def analyze(
        self, user_id: str, fragments: List[FragmentMemory], analysis_days: int = 7
    ) -> BehaviorPattern:
        """
        分析用户行为模式

        Args:
            user_id: 用户 ID
            fragments: 碎片记忆列表
            analysis_days: 分析周期（天）

        Returns:
            BehaviorPattern 行为模式
        """
        if not fragments:
            logger.warning(f"[BehaviorAnalyzer] 没有碎片记忆可分析: user={user_id}")
            return self._create_empty_pattern(user_id)

        # 过滤分析周期内的碎片
        cutoff = datetime.now() - timedelta(days=analysis_days)
        recent_fragments = [f for f in fragments if f.timestamp >= cutoff]

        if not recent_fragments:
            recent_fragments = fragments[-20:]  # 至少取最近20条

        # 构建分析 Prompt
        fragments_json = self._format_fragments_for_prompt(recent_fragments)
        date_range = f"{cutoff.strftime('%Y-%m-%d')} 至 {datetime.now().strftime('%Y-%m-%d')}"

        prompt = BEHAVIOR_ANALYSIS_PROMPT.format(
            fragments_json=fragments_json, date_range=date_range
        )

        try:
            response = await self._call_llm(prompt)
            result = self._parse_json_response(response)

            # 构建 BehaviorPattern
            pattern = self._build_pattern(user_id, result, recent_fragments)

            # 缓存
            self._user_patterns[user_id] = pattern

            logger.info(
                f"[BehaviorAnalyzer] 分析完成: user={user_id}, "
                f"role={pattern.inferred_role}, confidence={pattern.role_confidence:.0%}"
            )
            return pattern

        except Exception as e:
            logger.error(f"[BehaviorAnalyzer] 分析失败: {e}")
            return self._create_empty_pattern(user_id)

    def get_cached_pattern(self, user_id: str) -> Optional[BehaviorPattern]:
        """获取缓存的行为模式"""
        return self._user_patterns.get(user_id)

    # ==================== 快速统计（不依赖 LLM）====================

    def quick_stats(self, fragments: List[FragmentMemory]) -> Dict[str, Any]:
        """
        快速统计碎片记忆（不调用 LLM）

        Args:
            fragments: 碎片记忆列表

        Returns:
            统计数据字典
        """
        if not fragments:
            return {}

        stats = {
            "total_fragments": len(fragments),
            "date_range": {
                "start": min(f.timestamp for f in fragments).isoformat(),
                "end": max(f.timestamp for f in fragments).isoformat(),
            },
            "time_distribution": self._count_by_time_slot(fragments),
            "day_distribution": self._count_by_day(fragments),
            "task_categories": self._count_task_categories(fragments),
            "emotion_summary": self._summarize_emotions(fragments),
            "mentioned_people": self._extract_mentioned_people(fragments),
        }

        return stats

    def _count_by_time_slot(self, fragments: List[FragmentMemory]) -> Dict[str, int]:
        """按时间段统计"""
        counts: Dict[str, int] = defaultdict(int)
        for f in fragments:
            counts[f.time_slot.value] += 1
        return dict(counts)

    def _count_by_day(self, fragments: List[FragmentMemory]) -> Dict[str, int]:
        """按星期统计"""
        counts: Dict[str, int] = defaultdict(int)
        for f in fragments:
            counts[f.day_of_week.value] += 1
        return dict(counts)

    def _count_task_categories(self, fragments: List[FragmentMemory]) -> Dict[str, int]:
        """统计任务类别"""
        counts: Dict[str, int] = defaultdict(int)
        for f in fragments:
            if f.task_hint:
                counts[f.task_hint.category] += 1
        return dict(counts)

    def _summarize_emotions(self, fragments: List[FragmentMemory]) -> Dict[str, Any]:
        """汇总情绪状态"""
        signals: Dict[str, int] = defaultdict(int)
        stress_levels = []

        for f in fragments:
            if f.emotion_hint:
                signals[f.emotion_hint.signal] += 1
                stress_levels.append(f.emotion_hint.stress_level)

        avg_stress = sum(stress_levels) / len(stress_levels) if stress_levels else 0.0

        return {"signal_distribution": dict(signals), "average_stress_level": round(avg_stress, 2)}

    def _extract_mentioned_people(self, fragments: List[FragmentMemory]) -> List[str]:
        """提取提到的人"""
        people = set()
        for f in fragments:
            if f.relation_hint and f.relation_hint.mentioned:
                people.update(f.relation_hint.mentioned)
        return list(people)

    # ==================== 内部方法 ====================

    async def _call_llm(self, prompt: str) -> str:
        """调用 LLM"""
        messages = [Message(role="user", content=prompt)]
        llm_service = await self.get_llm_service()
        response = await llm_service.create_message_async(messages)

        if hasattr(response, "text"):
            return response.text
        elif hasattr(response, "content"):
            return response.content
        return str(response)

    def _parse_json_response(self, response: str) -> Dict[str, Any]:
        """解析 LLM JSON 响应"""
        import json

        try:
            json_start = response.find("{")
            json_end = response.rfind("}") + 1
            if json_start != -1 and json_end > json_start:
                return json.loads(response[json_start:json_end])
        except json.JSONDecodeError as e:
            logger.warning(f"[BehaviorAnalyzer] JSON 解析失败: {e}")
        return {}

    def _format_fragments_for_prompt(self, fragments: List[FragmentMemory]) -> str:
        """格式化碎片记忆为 Prompt 输入"""
        import json

        formatted = []
        for f in fragments:
            item = {
                "timestamp": f.timestamp.isoformat(),
                "time_slot": f.time_slot.value,
                "day_of_week": f.day_of_week.value,
                "message": f.message[:200],  # 截断过长消息
            }

            if f.task_hint:
                item["task"] = {"content": f.task_hint.content, "category": f.task_hint.category}

            if f.emotion_hint:
                item["emotion"] = {
                    "signal": f.emotion_hint.signal,
                    "stress_level": f.emotion_hint.stress_level,
                }

            if f.relation_hint:
                item["relations"] = f.relation_hint.mentioned

            if f.todo_hint:
                item["todo"] = f.todo_hint.content

            # 新增维度
            if f.preference_hint:
                item["preference"] = {
                    "response_format": f.preference_hint.response_format,
                    "preferred_tools": f.preference_hint.preferred_tools,
                }
            if f.topic_hint:
                item["topics"] = f.topic_hint.topics
                item["projects"] = f.topic_hint.projects
            if f.tool_hint:
                item["tools"] = f.tool_hint.tools_mentioned
            if f.goal_hint:
                item["goals"] = f.goal_hint.goals
                item["risks"] = f.goal_hint.risks

            formatted.append(item)

        return json.dumps(formatted, ensure_ascii=False, indent=2)

    def _build_pattern(
        self, user_id: str, result: Dict[str, Any], fragments: List[FragmentMemory]
    ) -> BehaviorPattern:
        """构建 BehaviorPattern"""

        # What - 常规任务
        what_data = result.get("what", {})
        routine_tasks = []
        for task in what_data.get("routine_tasks", []):
            routine_tasks.append(
                RoutineTask(
                    name=task.get("name", ""),
                    category=task.get("category", "general"),
                    frequency=task.get("frequency", "ad_hoc"),
                    avg_duration_hours=task.get("avg_duration_hours"),
                    confidence=task.get("confidence", 0.5),
                )
            )

        # When - 时间模式
        when_data = result.get("when", {})
        time_pattern = TimePattern(
            work_start=when_data.get("work_start"),
            work_end=when_data.get("work_end"),
            peak_hours=when_data.get("peak_hours", []),
            meeting_slots=when_data.get("meeting_slots", []),
            preferred_deep_work_time=when_data.get("preferred_deep_work_time"),
        )

        # Where - 工作场景
        where_data = result.get("where", {})
        work_context = WorkContext(
            primary_context=where_data.get("primary_context", "unknown"),
            tools_mentioned=where_data.get("tools_mentioned", []),
        )

        # Who - 协作者
        who_data = result.get("who", {})
        collaborators = []
        for collab in who_data.get("frequent_collaborators", []):
            collaborators.append(
                Collaborator(
                    name=collab.get("name", ""),
                    relationship=collab.get("relationship", "colleague"),
                    interaction_frequency=collab.get("interaction_frequency", "occasionally"),
                )
            )

        # Why - 动机
        why_data = result.get("why", {})
        motivation = Motivation(
            primary_goals=why_data.get("primary_goals", []),
            motivations=why_data.get("motivations", []),
            pain_points=why_data.get("pain_points", []),
        )

        # How - 工作风格
        how_data = result.get("how", {})
        work_style = WorkStyle(
            work_style=how_data.get("work_style", "flexible"),
            communication_preference=how_data.get("communication_preference", "mixed"),
            decision_style=how_data.get("decision_style", "collaborative"),
            response_format_preference=how_data.get("response_format_preference", "concise"),
        )

        # 分析周期
        if fragments:
            date_range = DateRange(
                start=min(f.timestamp for f in fragments), end=max(f.timestamp for f in fragments)
            )
        else:
            date_range = DateRange(start=datetime.now(), end=datetime.now())

        # 新增维度：偏好稳定性
        pref_stability_data = result.get("preference_stability", {})
        preference_stability = None
        if pref_stability_data:
            preference_stability = PreferenceStability(
                stable_preferences=pref_stability_data.get("stable_preferences", {}),
                evolving_preferences=pref_stability_data.get("evolving_preferences", {}),
                preference_confidence=pref_stability_data.get("preference_confidence", 0.0),
            )

        # 新增维度：周期性分析
        periodicity_data = result.get("periodicity", {})
        periodicity = None
        if periodicity_data:
            periodicity = PeriodicityAnalysis(
                patterns=periodicity_data.get("patterns", {}),
                frequency_distribution=periodicity_data.get("frequency_distribution", {}),
                consistency_score=periodicity_data.get("consistency_score", 0.0),
            )

        # 新增维度：冲突检测
        conflict_data = result.get("conflict_detection", {})
        conflict_detection = None
        if conflict_data:
            conflict_detection = ConflictDetection(
                detected_conflicts=conflict_data.get("detected_conflicts", []),
                conflict_count=conflict_data.get("conflict_count", 0),
                resolved_conflicts=conflict_data.get("resolved_conflicts", []),
            )

        return BehaviorPattern(
            id=str(uuid.uuid4()),
            user_id=user_id,
            analysis_period=date_range,
            fragment_count=len(fragments),
            # 5W1H
            routine_tasks=routine_tasks,
            main_work_focus=what_data.get("main_work_focus", ""),
            time_pattern=time_pattern,
            work_context=work_context,
            collaborators=collaborators,
            reporting_to=who_data.get("reporting_to"),
            motivation=motivation,
            work_style=work_style,
            # 推断角色
            inferred_role=result.get("inferred_role", "unknown"),
            role_confidence=result.get("role_confidence", 0.0),
            # 新增分析维度
            preference_stability=preference_stability,
            periodicity=periodicity,
            conflict_detection=conflict_detection,
            # 元数据
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )

    def _create_empty_pattern(self, user_id: str) -> BehaviorPattern:
        """创建空的行为模式"""
        return BehaviorPattern(
            id=str(uuid.uuid4()),
            user_id=user_id,
            analysis_period=DateRange(start=datetime.now(), end=datetime.now()),
            fragment_count=0,
            routine_tasks=[],
            main_work_focus="",
            time_pattern=TimePattern(),
            work_context=WorkContext(),
            collaborators=[],
            reporting_to=None,
            motivation=Motivation(),
            work_style=WorkStyle(),
            inferred_role="unknown",
            role_confidence=0.0,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )


# ==================== 工厂函数 ====================

_analyzer_instance: Optional[BehaviorAnalyzer] = None


def get_behavior_analyzer() -> BehaviorAnalyzer:
    """获取行为分析器单例"""
    global _analyzer_instance
    if _analyzer_instance is None:
        _analyzer_instance = BehaviorAnalyzer()
    return _analyzer_instance


def reset_behavior_analyzer() -> None:
    """重置行为分析器（用于测试）"""
    global _analyzer_instance
    _analyzer_instance = None
