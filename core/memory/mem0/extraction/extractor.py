"""
Dazee 碎片记忆提取器

基于 LLM 语义理解能力，从对话中提取碎片记忆
使用 llm_config 配置系统管理模型参数，无需硬编码
"""

# 1. 标准库
import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

# 3. 本地模块
from core.llm import Message
from logger import get_logger

from ..schemas import (
    ConstraintHint,
    DayOfWeek,
    EmotionHint,
    FragmentMemory,
    GoalHint,
    PreferenceHint,
    RelationHint,
    TaskHint,
    TimeHint,
    TimeSlot,
    TodoHint,
    ToolHint,
    TopicHint,
)

# 2. 第三方库（无）


logger = get_logger("dazee.extractor")


# ==================== LLM Profile 名称 ====================

# 在 config/llm_config/profiles.yaml 中配置
EXTRACTOR_PROFILE_NAME = "fragment_extractor"


# ==================== LLM 提取 Prompt ====================

FRAGMENT_EXTRACTION_PROMPT = """你是 Dazee 智能助理的记忆分析系统。请分析以下用户对话，提取隐性信息。

注意：用户不会直接告诉你这些信息，你需要从对话内容和上下文中推断。

## 对话信息
- 用户消息: "{message}"
- 对话时间: {timestamp}
- 时间段: {time_slot}
- 星期: {day_of_week}

## 请分析并提取以下信息（以 JSON 格式输出）：

```json
{{
  "task_hint": {{
    "content": "用户可能在做什么任务（如：处理客户反馈、写代码、准备会议等）",
    "category": "任务类别（customer_support/report/meeting/development/document/analysis/coordination/general）",
    "confidence": 0.0-1.0
  }},
  "time_hint": {{
    "pattern": "时间模式（如：morning_routine/afternoon_meeting/deadline_task/ad_hoc）",
    "inferred_schedule": "推断的时间段（如：09:00-10:00）或 null",
    "confidence": 0.0-1.0
  }},
  "emotion_hint": {{
    "signal": "情绪信号（neutral/positive/fatigue/stressed/frustrated）",
    "stress_level": 0.0-1.0,
    "keywords_detected": ["检测到的情绪相关表达"]
  }},
  "relation_hint": {{
    "mentioned": ["提到的人（如：老板、客户A、小王）"],
    "relationship_type": "关系类型（supervisor/colleague/client/external）或 null"
  }},
  "todo_hint": {{
    "content": "如果用户提到了待办事项，描述是什么",
    "deadline_text": "原文中的截止时间表述（如：下周三、明天）",
    "priority": "low/medium/high/urgent",
    "confidence": 0.0-1.0
  }},
  "preference_hint": {{
    "response_format": "响应格式偏好（structured/concise/detailed）或 null",
    "communication_style": "沟通风格（formal/casual/professional）或 null",
    "preferred_tools": ["偏好的工具/平台（如：Python、Excel、Slack）"],
    "work_preferences": {{"其他工作偏好": "具体内容"}},
    "verbatim_preferences": ["用户原话中明确表达的偏好，原样摘录（如：'我喜欢毒舌但有干货的风格'、'输出格式要简洁'、'不要用 plotly'）"],
    "confidence": 0.0-1.0
  }},
  "topic_hint": {{
    "topics": ["讨论的主题（如：产品规划、数据分析）"],
    "projects": ["涉及的项目（如：Q1产品发布）"],
    "keywords": ["关键词"],
    "confidence": 0.0-1.0
  }},
  "constraint_hint": {{
    "constraints": ["约束条件（如：不能使用外部API、必须使用Python）"],
    "taboos": ["禁忌事项（如：不要提及XX话题）"],
    "limitations": ["限制条件（如：时间限制、资源限制）"],
    "confidence": 0.0-1.0
  }},
  "tool_hint": {{
    "tools_mentioned": ["提到的工具（如：GitHub、Jira、Notion）"],
    "platforms_mentioned": ["提到的平台（如：AWS、腾讯云）"],
    "preferred_workflow": "偏好的工作流程（如：敏捷开发、瀑布模型）或 null",
    "confidence": 0.0-1.0
  }},
  "goal_hint": {{
    "goals": ["提到的目标（如：提升用户体验、完成季度KPI）"],
    "risks": ["风险信号（如：时间紧迫、资源不足）"],
    "blockers": ["阻碍因素（如：缺少数据、依赖未完成）"],
    "achievements": ["成就/成果（如：成功上线、获得认可）"],
    "confidence": 0.0-1.0
  }}
}}
```

## 提取原则：
1. 如果某项信息无法从对话中推断，对应字段设为 null 或空数组
2. confidence 反映你的推断确定性
3. 从语气、用词、上下文推断情绪，而不是简单匹配关键词
4. 待办事项需要有明确的行动指向（如"要做XXX"、"得完成XXX"）
5. 偏好和工具信息可以从用户的选择和使用习惯中推断
6. **verbatim_preferences 必须原样摘录用户原话**，不要抽象化。如用户说"我喜欢毒舌但有干货的风格"，直接保留这句话，不要改写为 "casual"
7. 约束和禁忌可以从用户的明确要求或限制中提取
8. 目标可以从用户的表述和意图中推断
9. 只输出 JSON，不要其他解释

请分析并输出 JSON："""


class FragmentExtractor:
    """
    碎片记忆提取器

    基于 LLM 语义理解，从单次对话中提取隐性信息
    使用 llm_config 配置系统管理模型参数
    """

    def __init__(self, profile_name: Optional[str] = None, **profile_overrides):
        """
        初始化提取器

        Args:
            profile_name: LLM Profile 名称，默认使用 "fragment_extractor"
            **profile_overrides: 覆盖 Profile 中的参数（如 max_tokens=2048）
        """
        self.profile_name = profile_name or EXTRACTOR_PROFILE_NAME
        self._profile_overrides = profile_overrides
        self._profile: Optional[Dict[str, Any]] = None
        self._llm_service = None

        logger.info(f"[Extractor] 初始化: profile={self.profile_name}")

    async def get_profile(self) -> Dict[str, Any]:
        """懒加载 LLM Profile 配置"""
        if self._profile is None:
            from config.llm_config import get_llm_profile

            self._profile = await get_llm_profile(self.profile_name, **self._profile_overrides)
            logger.info(f"[Extractor] 加载配置: model={self._profile.get('model')}")
        return self._profile

    async def get_llm_service(self) -> Any:
        """懒加载 LLM 服务"""
        if self._llm_service is None:
            from core.llm import create_llm_service

            profile = await self.get_profile()
            self._llm_service = create_llm_service(**profile)
        return self._llm_service

    def _get_time_slot(self, dt: datetime) -> TimeSlot:
        """根据时间获取时间段"""
        hour = dt.hour
        if 6 <= hour < 12:
            return TimeSlot.MORNING
        elif 12 <= hour < 18:
            return TimeSlot.AFTERNOON
        elif 18 <= hour < 22:
            return TimeSlot.EVENING
        else:
            return TimeSlot.NIGHT

    def _get_day_of_week(self, dt: datetime) -> DayOfWeek:
        """获取星期"""
        days = [
            DayOfWeek.MONDAY,
            DayOfWeek.TUESDAY,
            DayOfWeek.WEDNESDAY,
            DayOfWeek.THURSDAY,
            DayOfWeek.FRIDAY,
            DayOfWeek.SATURDAY,
            DayOfWeek.SUNDAY,
        ]
        return days[dt.weekday()]

    def _time_slot_to_chinese(self, slot: TimeSlot) -> str:
        """时间段转中文"""
        mapping = {
            TimeSlot.MORNING: "上午",
            TimeSlot.AFTERNOON: "下午",
            TimeSlot.EVENING: "晚上",
            TimeSlot.NIGHT: "深夜",
        }
        return mapping.get(slot, "未知")

    def _day_to_chinese(self, day: DayOfWeek) -> str:
        """星期转中文"""
        mapping = {
            DayOfWeek.MONDAY: "周一",
            DayOfWeek.TUESDAY: "周二",
            DayOfWeek.WEDNESDAY: "周三",
            DayOfWeek.THURSDAY: "周四",
            DayOfWeek.FRIDAY: "周五",
            DayOfWeek.SATURDAY: "周六",
            DayOfWeek.SUNDAY: "周日",
        }
        return mapping.get(day, "未知")

    async def extract(
        self, user_id: str, session_id: str, message: str, timestamp: Optional[datetime] = None
    ) -> FragmentMemory:
        """
        从对话中提取碎片记忆

        Args:
            user_id: 用户 ID
            session_id: 会话 ID
            message: 用户消息
            timestamp: 消息时间（默认当前时间）

        Returns:
            FragmentMemory 对象
        """
        timestamp = timestamp or datetime.now()
        time_slot = self._get_time_slot(timestamp)
        day_of_week = self._get_day_of_week(timestamp)

        # 构建 Prompt
        prompt = FRAGMENT_EXTRACTION_PROMPT.format(
            message=message,
            timestamp=timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            time_slot=self._time_slot_to_chinese(time_slot),
            day_of_week=self._day_to_chinese(day_of_week),
        )

        # 调用 LLM 进行提取
        try:
            response = await self._call_llm(prompt)
            extracted = self._parse_llm_response(response)
        except Exception as e:
            logger.error(f"[Extractor] LLM 提取失败: {e}")
            extracted = {}

        # 构建 FragmentMemory
        fragment = FragmentMemory(
            id=str(uuid.uuid4()),
            user_id=user_id,
            session_id=session_id,
            message=message,
            timestamp=timestamp,
            time_slot=time_slot,
            day_of_week=day_of_week,
            task_hint=self._build_task_hint(extracted.get("task_hint")),
            time_hint=self._build_time_hint(extracted.get("time_hint")),
            emotion_hint=self._build_emotion_hint(extracted.get("emotion_hint")),
            relation_hint=self._build_relation_hint(extracted.get("relation_hint")),
            todo_hint=self._build_todo_hint(extracted.get("todo_hint"), timestamp),
            preference_hint=self._build_preference_hint(extracted.get("preference_hint")),
            topic_hint=self._build_topic_hint(extracted.get("topic_hint")),
            constraint_hint=self._build_constraint_hint(extracted.get("constraint_hint")),
            tool_hint=self._build_tool_hint(extracted.get("tool_hint")),
            goal_hint=self._build_goal_hint(extracted.get("goal_hint")),
            confidence=self._calculate_overall_confidence(extracted),
            created_at=datetime.now(),
        )

        logger.info(
            f"[Extractor] 提取完成: user={user_id}, "
            f"task={fragment.task_hint.content if fragment.task_hint else 'None'}, "
            f"emotion={fragment.emotion_hint.signal if fragment.emotion_hint else 'neutral'}"
        )

        return fragment

    async def _call_llm(self, prompt: str) -> str:
        """
        调用 LLM 进行提取

        使用 llm_config 配置的模型，通过 core.llm 服务统一调用
        """
        messages = [Message(role="user", content=prompt)]

        # 使用统一的 LLM 服务接口
        llm_service = await self.get_llm_service()
        response = await llm_service.create_message_async(messages)

        # 提取响应文本（LLMResponse 对象有 text 属性）
        if hasattr(response, "text"):
            return response.text
        elif hasattr(response, "content"):
            return response.content
        else:
            return str(response)

    def _parse_llm_response(self, response: str) -> Dict[str, Any]:
        """解析 LLM 响应"""
        try:
            # 尝试提取 JSON
            json_start = response.find("{")
            json_end = response.rfind("}") + 1
            if json_start != -1 and json_end > json_start:
                json_str = response[json_start:json_end]
                return json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.warning(f"[Extractor] JSON 解析失败: {e}")
        return {}

    def _build_task_hint(self, data: Optional[Dict]) -> Optional[TaskHint]:
        """构建任务线索"""
        if not data or not data.get("content"):
            return None
        return TaskHint(
            content=data.get("content", ""),
            category=data.get("category", "general"),
            confidence=data.get("confidence", 0.5),
        )

    def _build_time_hint(self, data: Optional[Dict]) -> Optional[TimeHint]:
        """构建时间线索"""
        if not data or not data.get("pattern"):
            return None
        return TimeHint(
            pattern=data.get("pattern", ""),
            inferred_schedule=data.get("inferred_schedule"),
            confidence=data.get("confidence", 0.5),
        )

    def _build_emotion_hint(self, data: Optional[Dict]) -> Optional[EmotionHint]:
        """构建情绪线索"""
        if not data:
            return EmotionHint(signal="neutral", stress_level=0.0, keywords_detected=[])
        return EmotionHint(
            signal=data.get("signal", "neutral"),
            stress_level=data.get("stress_level", 0.0),
            keywords_detected=data.get("keywords_detected", []),
        )

    def _build_relation_hint(self, data: Optional[Dict]) -> Optional[RelationHint]:
        """构建关系线索"""
        if not data or not data.get("mentioned"):
            return None
        return RelationHint(
            mentioned=data.get("mentioned", []), relationship_type=data.get("relationship_type")
        )

    def _build_todo_hint(
        self, data: Optional[Dict], base_timestamp: datetime
    ) -> Optional[TodoHint]:
        """构建待办线索"""
        if not data or not data.get("content"):
            return None

        # 解析截止时间
        deadline = None
        deadline_text = data.get("deadline_text")
        if deadline_text:
            deadline = self._parse_deadline(deadline_text, base_timestamp)

        return TodoHint(
            content=data.get("content", ""),
            deadline=deadline,
            priority=data.get("priority", "medium"),
            confidence=data.get("confidence", 0.5),
        )

    def _parse_deadline(self, deadline_text: str, base_timestamp: datetime) -> Optional[datetime]:
        """
        解析截止时间文本

        使用简单的相对时间解析，复杂情况由 LLM 处理
        """
        from datetime import timedelta

        text = deadline_text.strip()
        base_date = base_timestamp.date()

        # 简单的相对时间解析
        if "明天" in text:
            return datetime.combine(
                base_date + timedelta(days=1), datetime.min.time().replace(hour=18)
            )
        elif "后天" in text:
            return datetime.combine(
                base_date + timedelta(days=2), datetime.min.time().replace(hour=18)
            )
        elif "今天" in text:
            return datetime.combine(base_date, datetime.min.time().replace(hour=18))
        elif "下周" in text:
            # 下周X
            weekday_map = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6}
            for char, wd in weekday_map.items():
                if f"下周{char}" in text:
                    days_ahead = wd - base_date.weekday() + 7
                    if days_ahead <= 0:
                        days_ahead += 7
                    return datetime.combine(
                        base_date + timedelta(days=days_ahead), datetime.min.time().replace(hour=18)
                    )
        elif "周" in text:
            # 本周X
            weekday_map = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6}
            for char, wd in weekday_map.items():
                if f"周{char}" in text:
                    days_ahead = wd - base_date.weekday()
                    if days_ahead < 0:
                        days_ahead += 7
                    return datetime.combine(
                        base_date + timedelta(days=days_ahead), datetime.min.time().replace(hour=18)
                    )

        return None

    def _calculate_overall_confidence(self, extracted: Dict) -> float:
        """计算整体置信度"""
        confidences = []
        hint_keys = [
            "task_hint",
            "time_hint",
            "emotion_hint",
            "todo_hint",
            "preference_hint",
            "topic_hint",
            "constraint_hint",
            "tool_hint",
            "goal_hint",
        ]
        for key in hint_keys:
            hint = extracted.get(key)
            if hint and isinstance(hint, dict) and "confidence" in hint:
                confidences.append(hint["confidence"])

        if not confidences:
            return 0.0
        return sum(confidences) / len(confidences)

    def _build_preference_hint(self, data: Optional[Dict]) -> Optional[PreferenceHint]:
        """构建偏好线索"""
        if not data:
            return None
        return PreferenceHint(
            response_format=data.get("response_format"),
            communication_style=data.get("communication_style"),
            preferred_tools=data.get("preferred_tools", []),
            work_preferences=data.get("work_preferences", {}),
            verbatim_preferences=data.get("verbatim_preferences", []),
            confidence=data.get("confidence", 0.5),
        )

    def _build_topic_hint(self, data: Optional[Dict]) -> Optional[TopicHint]:
        """构建主题线索"""
        if not data:
            return None
        return TopicHint(
            topics=data.get("topics", []),
            projects=data.get("projects", []),
            keywords=data.get("keywords", []),
            confidence=data.get("confidence", 0.5),
        )

    def _build_constraint_hint(self, data: Optional[Dict]) -> Optional[ConstraintHint]:
        """构建约束线索"""
        if not data:
            return None
        return ConstraintHint(
            constraints=data.get("constraints", []),
            taboos=data.get("taboos", []),
            limitations=data.get("limitations", []),
            confidence=data.get("confidence", 0.5),
        )

    def _build_tool_hint(self, data: Optional[Dict]) -> Optional[ToolHint]:
        """构建工具线索"""
        if not data:
            return None
        return ToolHint(
            tools_mentioned=data.get("tools_mentioned", []),
            platforms_mentioned=data.get("platforms_mentioned", []),
            preferred_workflow=data.get("preferred_workflow"),
            confidence=data.get("confidence", 0.5),
        )

    def _build_goal_hint(self, data: Optional[Dict]) -> Optional[GoalHint]:
        """构建目标线索"""
        if not data:
            return None
        return GoalHint(
            goals=data.get("goals", []),
            risks=data.get("risks", []),
            blockers=data.get("blockers", []),
            achievements=data.get("achievements", []),
            confidence=data.get("confidence", 0.5),
        )

    async def extract_batch(
        self, user_id: str, session_id: str, messages: List[Dict[str, Any]]
    ) -> List[FragmentMemory]:
        """
        批量提取碎片记忆

        Args:
            user_id: 用户 ID
            session_id: 会话 ID
            messages: 消息列表 [{"content": "...", "timestamp": ...}, ...]

        Returns:
            FragmentMemory 列表
        """
        fragments = []
        for msg in messages:
            content = msg.get("content", "")
            timestamp = msg.get("timestamp")
            if isinstance(timestamp, str):
                timestamp = datetime.fromisoformat(timestamp)

            fragment = await self.extract(
                user_id=user_id, session_id=session_id, message=content, timestamp=timestamp
            )
            fragments.append(fragment)

        return fragments


# ==================== 工厂函数 ====================

_extractor_instance: Optional[FragmentExtractor] = None


def get_fragment_extractor() -> FragmentExtractor:
    """获取碎片提取器单例"""
    global _extractor_instance
    if _extractor_instance is None:
        _extractor_instance = FragmentExtractor()
    return _extractor_instance


def reset_fragment_extractor() -> None:
    """重置碎片提取器（用于测试）"""
    global _extractor_instance
    _extractor_instance = None
