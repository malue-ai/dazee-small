"""
Dazee PDCA 计划管理器

基于 LLM 语义理解，管理用户的工作计划和待办事项
支持 PDCA 循环：Plan -> Do -> Check -> Act

使用 llm_config 配置系统管理模型参数
"""

# 1. 标准库
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

# 3. 本地模块
from core.llm import Message
from logger import get_logger

from ..schemas import (
    ActionItem,
    CheckResult,
    PDCAPhase,
    WorkPlan,
)

# 2. 第三方库（无）


logger = get_logger("dazee.planner")


# ==================== LLM Profile 名称 ====================

PLANNER_PROFILE_NAME = "plan_manager"


# ==================== LLM Prompts ====================

PLAN_ANALYSIS_PROMPT = """你是 Dazee 智能助理的计划分析系统。请分析用户消息，识别是否包含计划或待办事项。

## 用户消息
"{message}"

## 当前时间
{current_time}

## 请分析并输出 JSON：

```json
{{
  "has_plan": true/false,
  "plan": {{
    "title": "计划标题（简洁概括）",
    "description": "计划详细描述",
    "category": "分类（project/daily_task/meeting/report/learning/other）",
    "priority": "优先级（low/medium/high/urgent）",
    "deadline_text": "截止时间原文（如：下周三、月底前）",
    "estimated_hours": 预估工时（数字，如 2.5）,
    "sub_tasks": ["子任务1", "子任务2"],
    "blockers": ["潜在阻碍1"],
    "confidence": 0.0-1.0
  }}
}}
```

## 分析原则：
1. 只有明确的行动意图才算计划（如"要做XX"、"需要完成XX"）
2. 如果没有明确计划，has_plan 设为 false，plan 设为 null
3. 从上下文推断优先级和截止时间
4. 只输出 JSON

请分析："""


PLAN_UPDATE_PROMPT = """你是 Dazee 智能助理的计划跟踪系统。请根据用户消息更新计划状态。

## 现有计划
标题: {plan_title}
描述: {plan_description}
当前进度: {progress}%
当前阶段: {phase}
子任务: {sub_tasks}

## 用户最新消息
"{message}"

## 请分析并输出 JSON：

```json
{{
  "progress_delta": 进度变化（0-100，如 +20 表示增加 20%）,
  "completed_tasks": ["已完成的子任务"],
  "new_blockers": ["新发现的阻碍"],
  "resolved_blockers": ["已解决的阻碍"],
  "status_change": "状态变化（null/completed/blocked/at_risk）",
  "notes": "进展备注"
}}
```

请分析："""


class PDCAManager:
    """
    PDCA 计划管理器

    基于 LLM 语义理解，管理用户的工作计划
    支持 PDCA 循环：Plan -> Do -> Check -> Act
    """

    def __init__(self, profile_name: Optional[str] = None, **profile_overrides):
        """
        初始化计划管理器

        Args:
            profile_name: LLM Profile 名称，默认使用 "plan_manager"
            **profile_overrides: 覆盖 Profile 中的参数
        """
        self.profile_name = profile_name or PLANNER_PROFILE_NAME
        self._profile_overrides = profile_overrides
        self._profile: Optional[Dict[str, Any]] = None
        self._llm_service = None

        # 用户计划存储（user_id -> List[WorkPlan]）
        self._user_plans: Dict[str, List[WorkPlan]] = {}

        logger.info(f"[PDCAManager] 初始化: profile={self.profile_name}")

    async def get_profile(self) -> Dict[str, Any]:
        """懒加载 LLM Profile 配置"""
        if self._profile is None:
            from config.llm_config import get_llm_profile

            self._profile = await get_llm_profile(self.profile_name, **self._profile_overrides)
            logger.info(f"[PDCAManager] 加载配置: model={self._profile.get('model')}")
        return self._profile

    async def get_llm_service(self) -> Any:
        """懒加载 LLM 服务"""
        if self._llm_service is None:
            from core.llm import create_llm_service

            profile = await self.get_profile()
            self._llm_service = create_llm_service(**profile)
        return self._llm_service

    # ==================== Plan 阶段 ====================

    async def analyze_for_plan(self, user_id: str, message: str) -> Optional[WorkPlan]:
        """
        分析用户消息，识别并创建计划

        Args:
            user_id: 用户 ID
            message: 用户消息

        Returns:
            如果识别到计划，返回 WorkPlan；否则返回 None
        """
        prompt = PLAN_ANALYSIS_PROMPT.format(
            message=message, current_time=datetime.now().strftime("%Y-%m-%d %H:%M %A")
        )

        try:
            response = await self._call_llm(prompt)
            result = self._parse_json_response(response)

            if not result.get("has_plan"):
                return None

            plan_data = result.get("plan", {})

            # 创建 WorkPlan
            plan = WorkPlan(
                id=str(uuid.uuid4()),
                user_id=user_id,
                title=plan_data.get("title", "未命名计划"),
                description=plan_data.get("description", ""),
                category=plan_data.get("category", "other"),
                priority=plan_data.get("priority", "medium"),
                deadline=self._parse_deadline(plan_data.get("deadline_text")),
                estimated_hours=plan_data.get("estimated_hours"),
                sub_tasks=plan_data.get("sub_tasks", []),
                completed_tasks=[],
                blockers=plan_data.get("blockers", []),
                progress=0.0,
                phase=PDCAPhase.PLAN,
                status="active",
                created_at=datetime.now(),
                updated_at=datetime.now(),
            )

            # 存储计划
            self._add_plan(user_id, plan)

            logger.info(f"[PDCAManager] 创建计划: user={user_id}, title={plan.title}")
            return plan

        except Exception as e:
            logger.error(f"[PDCAManager] 计划分析失败: {e}")
            return None

    # ==================== Do 阶段 ====================

    async def start_plan(self, user_id: str, plan_id: str) -> Optional[WorkPlan]:
        """
        开始执行计划，进入 Do 阶段

        Args:
            user_id: 用户 ID
            plan_id: 计划 ID

        Returns:
            更新后的 WorkPlan
        """
        plan = self._get_plan(user_id, plan_id)
        if not plan:
            return None

        plan.phase = PDCAPhase.DO
        plan.started_at = datetime.now()
        plan.updated_at = datetime.now()

        logger.info(f"[PDCAManager] 开始执行: plan={plan.title}")
        return plan

    async def update_progress(self, user_id: str, plan_id: str, message: str) -> Optional[WorkPlan]:
        """
        根据用户消息更新计划进度

        Args:
            user_id: 用户 ID
            plan_id: 计划 ID
            message: 用户消息

        Returns:
            更新后的 WorkPlan
        """
        plan = self._get_plan(user_id, plan_id)
        if not plan:
            return None

        prompt = PLAN_UPDATE_PROMPT.format(
            plan_title=plan.title,
            plan_description=plan.description,
            progress=int(plan.progress * 100),
            phase=plan.phase.value,
            sub_tasks=", ".join(plan.sub_tasks) if plan.sub_tasks else "无",
            message=message,
        )

        try:
            response = await self._call_llm(prompt)
            result = self._parse_json_response(response)

            # 更新进度
            progress_delta = result.get("progress_delta", 0)
            plan.progress = min(1.0, max(0.0, plan.progress + progress_delta / 100))

            # 更新已完成任务
            completed = result.get("completed_tasks", [])
            for task in completed:
                if task in plan.sub_tasks and task not in plan.completed_tasks:
                    plan.completed_tasks.append(task)

            # 更新阻碍
            new_blockers = result.get("new_blockers", [])
            plan.blockers.extend(new_blockers)

            resolved = result.get("resolved_blockers", [])
            plan.blockers = [b for b in plan.blockers if b not in resolved]

            # 状态变化
            status_change = result.get("status_change")
            if status_change:
                plan.status = status_change
                if status_change == "completed":
                    plan.phase = PDCAPhase.CHECK
                    plan.progress = 1.0

            plan.updated_at = datetime.now()

            logger.info(f"[PDCAManager] 更新进度: plan={plan.title}, progress={plan.progress:.0%}")
            return plan

        except Exception as e:
            logger.error(f"[PDCAManager] 进度更新失败: {e}")
            return plan

    # ==================== Check 阶段 ====================

    async def check_plan(
        self, user_id: str, plan_id: str, actual_result: str
    ) -> Optional[CheckResult]:
        """
        检查计划执行结果

        Args:
            user_id: 用户 ID
            plan_id: 计划 ID
            actual_result: 实际结果描述

        Returns:
            CheckResult 检查结果
        """
        plan = self._get_plan(user_id, plan_id)
        if not plan:
            return None

        plan.phase = PDCAPhase.CHECK
        plan.updated_at = datetime.now()

        # 计算完成率
        completion_rate = (
            len(plan.completed_tasks) / len(plan.sub_tasks) if plan.sub_tasks else plan.progress
        )

        # 创建检查结果
        check_result = CheckResult(
            plan_id=plan_id,
            checked_at=datetime.now(),
            completion_rate=completion_rate,
            actual_result=actual_result,
            gaps=[],  # 可由 LLM 分析差距
            lessons_learned=[],
        )

        plan.check_results.append(check_result)

        logger.info(f"[PDCAManager] 检查完成: plan={plan.title}, rate={completion_rate:.0%}")
        return check_result

    # ==================== Act 阶段 ====================

    async def act_on_plan(self, user_id: str, plan_id: str, decision: str) -> Optional[ActionItem]:
        """
        根据检查结果采取行动

        Args:
            user_id: 用户 ID
            plan_id: 计划 ID
            decision: 决策（continue/adjust/close/restart）

        Returns:
            ActionItem 行动项
        """
        plan = self._get_plan(user_id, plan_id)
        if not plan:
            return None

        plan.phase = PDCAPhase.ACT
        plan.updated_at = datetime.now()

        # 创建行动项
        action = ActionItem(
            plan_id=plan_id,
            decision=decision,
            action_taken=f"决策: {decision}",
            created_at=datetime.now(),
        )

        # 根据决策更新状态
        if decision == "close":
            plan.status = "completed"
            plan.completed_at = datetime.now()
        elif decision == "restart":
            plan.phase = PDCAPhase.PLAN
            plan.progress = 0.0

        plan.action_history.append(action)

        logger.info(f"[PDCAManager] 行动决策: plan={plan.title}, decision={decision}")
        return action

    # ==================== 查询接口 ====================

    def get_user_plans(
        self, user_id: str, status: Optional[str] = None, limit: int = 10
    ) -> List[WorkPlan]:
        """
        获取用户的计划列表

        Args:
            user_id: 用户 ID
            status: 过滤状态（active/completed/blocked/at_risk）
            limit: 最大数量

        Returns:
            WorkPlan 列表
        """
        plans = self._user_plans.get(user_id, [])

        if status:
            plans = [p for p in plans if p.status == status]

        # 按优先级和截止时间排序
        priority_order = {"urgent": 0, "high": 1, "medium": 2, "low": 3}
        plans.sort(key=lambda p: (priority_order.get(p.priority, 2), p.deadline or datetime.max))

        return plans[:limit]

    def get_active_plans(self, user_id: str) -> List[WorkPlan]:
        """获取用户的活跃计划"""
        return self.get_user_plans(user_id, status="active")

    def get_at_risk_plans(self, user_id: str) -> List[WorkPlan]:
        """获取有风险的计划（即将到期或有阻碍）"""
        plans = self._user_plans.get(user_id, [])
        at_risk = []

        now = datetime.now()
        for plan in plans:
            if plan.status != "active":
                continue

            # 有阻碍
            if plan.blockers:
                at_risk.append(plan)
                continue

            # 即将到期（3天内）
            if plan.deadline and (plan.deadline - now).days <= 3:
                at_risk.append(plan)

        return at_risk

    def get_upcoming_deadlines(self, user_id: str, days: int = 7) -> List[WorkPlan]:
        """获取即将到期的计划"""
        plans = self._user_plans.get(user_id, [])
        cutoff = datetime.now() + timedelta(days=days)

        upcoming = [
            p for p in plans if p.status == "active" and p.deadline and p.deadline <= cutoff
        ]

        upcoming.sort(key=lambda p: p.deadline)
        return upcoming

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
            logger.warning(f"[PDCAManager] JSON 解析失败: {e}")
        return {}

    def _parse_deadline(self, deadline_text: Optional[str]) -> Optional[datetime]:
        """解析截止时间文本"""
        if not deadline_text:
            return None

        now = datetime.now()
        text = deadline_text.strip()

        if "明天" in text:
            return datetime.combine(
                now.date() + timedelta(days=1), datetime.min.time().replace(hour=18)
            )
        elif "后天" in text:
            return datetime.combine(
                now.date() + timedelta(days=2), datetime.min.time().replace(hour=18)
            )
        elif "本周" in text or "这周" in text:
            days_to_friday = 4 - now.weekday()
            if days_to_friday < 0:
                days_to_friday += 7
            return datetime.combine(
                now.date() + timedelta(days=days_to_friday), datetime.min.time().replace(hour=18)
            )
        elif "下周" in text:
            days_to_next_friday = 4 - now.weekday() + 7
            return datetime.combine(
                now.date() + timedelta(days=days_to_next_friday),
                datetime.min.time().replace(hour=18),
            )
        elif "月底" in text:
            next_month = now.replace(day=28) + timedelta(days=4)
            last_day = next_month - timedelta(days=next_month.day)
            return datetime.combine(last_day.date(), datetime.min.time().replace(hour=18))

        return None

    def _add_plan(self, user_id: str, plan: WorkPlan) -> None:
        """添加计划到存储"""
        if user_id not in self._user_plans:
            self._user_plans[user_id] = []
        self._user_plans[user_id].append(plan)

    def _get_plan(self, user_id: str, plan_id: str) -> Optional[WorkPlan]:
        """获取指定计划"""
        plans = self._user_plans.get(user_id, [])
        for plan in plans:
            if plan.id == plan_id:
                return plan
        return None


# ==================== 工厂函数 ====================

_manager_instance: Optional[PDCAManager] = None


def get_pdca_manager() -> PDCAManager:
    """获取 PDCA 管理器单例"""
    global _manager_instance
    if _manager_instance is None:
        _manager_instance = PDCAManager()
    return _manager_instance


def reset_pdca_manager() -> None:
    """重置 PDCA 管理器（用于测试）"""
    global _manager_instance
    _manager_instance = None
