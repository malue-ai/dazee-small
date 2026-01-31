"""
Dazee 智能汇报和个性化响应生成器

基于用户画像、行为模式和计划，生成：
1. 智能日报/周报
2. 个性化响应建议
3. 主动关怀提示
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

from logger import get_logger
from ..schemas import (
    UserPersona,
    BehaviorPattern,
    WorkPlan,
    EmotionState,
    FragmentMemory,
)

logger = get_logger("dazee.reporter")


# ==================== 汇报模板 ====================

DAILY_REPORT_TEMPLATE = """# 📊 Dazee 每日工作洞察
**日期**: {date}
**用户**: {user_name}

## 📝 今日工作摘要
{work_summary}

## ⏰ 活跃计划状态
{plan_status}

## 💡 建议关注
{suggestions}

## 🎯 明日提醒
{tomorrow_reminders}

---
*由 Dazee 智能助理自动生成*
"""


WEEKLY_REPORT_TEMPLATE = """# 📈 Dazee 每周工作洞察
**周期**: {date_range}
**用户**: {user_name}

## 🔄 本周工作概览
{weekly_overview}

## 📊 5W1H 行为分析
{behavior_insights}

## ✅ 计划完成情况
{plan_completion}

## 😊 情绪与状态
{emotion_summary}

## 🎯 下周建议
{next_week_suggestions}

---
*由 Dazee 智能助理自动生成*
"""


class Reporter:
    """
    智能汇报和个性化响应生成器
    """
    
    def __init__(self):
        """初始化汇报器"""
        logger.info("[Reporter] 初始化完成")
    
    # ==================== 日报/周报生成 ====================
    
    def generate_daily_report(
        self,
        user_id: str,
        user_name: str,
        fragments: List[FragmentMemory],
        plans: List[WorkPlan],
        reminders: List[Any] = None,
        date: Optional[datetime] = None
    ) -> str:
        """
        生成每日工作洞察报告
        
        Args:
            user_id: 用户 ID
            user_name: 用户名称
            fragments: 当日碎片记忆
            plans: 活跃计划列表
            reminders: 明日提醒
            date: 报告日期
            
        Returns:
            Markdown 格式的日报
        """
        date = date or datetime.now()
        
        # 工作摘要
        work_summary = self._summarize_daily_work(fragments)
        
        # 计划状态
        plan_status = self._format_plan_status(plans)
        
        # 建议关注
        suggestions = self._generate_daily_suggestions(fragments, plans)
        
        # 明日提醒
        tomorrow_reminders = self._format_tomorrow_reminders(reminders)
        
        report = DAILY_REPORT_TEMPLATE.format(
            date=date.strftime("%Y年%m月%d日"),
            user_name=user_name,
            work_summary=work_summary,
            plan_status=plan_status,
            suggestions=suggestions,
            tomorrow_reminders=tomorrow_reminders
        )
        
        logger.info(f"[Reporter] 生成日报: user={user_id}, date={date.date()}")
        return report
    
    def generate_weekly_report(
        self,
        user_id: str,
        user_name: str,
        fragments: List[FragmentMemory],
        plans: List[WorkPlan],
        behavior: Optional[BehaviorPattern] = None,
        emotion: Optional[EmotionState] = None,
        start_date: Optional[datetime] = None
    ) -> str:
        """
        生成每周工作洞察报告
        
        Args:
            user_id: 用户 ID
            user_name: 用户名称
            fragments: 本周碎片记忆
            plans: 计划列表
            behavior: 行为模式分析
            emotion: 情绪状态
            start_date: 周起始日期
            
        Returns:
            Markdown 格式的周报
        """
        start_date = start_date or (datetime.now() - timedelta(days=7))
        end_date = start_date + timedelta(days=7)
        
        # 周概览
        weekly_overview = self._summarize_weekly_work(fragments)
        
        # 行为洞察
        behavior_insights = self._format_behavior_insights(behavior)
        
        # 计划完成情况
        plan_completion = self._format_plan_completion(plans)
        
        # 情绪摘要
        emotion_summary = self._format_emotion_summary(emotion, fragments)
        
        # 下周建议
        next_week_suggestions = self._generate_weekly_suggestions(plans, behavior, emotion)
        
        report = WEEKLY_REPORT_TEMPLATE.format(
            date_range=f"{start_date.strftime('%m月%d日')} - {end_date.strftime('%m月%d日')}",
            user_name=user_name,
            weekly_overview=weekly_overview,
            behavior_insights=behavior_insights,
            plan_completion=plan_completion,
            emotion_summary=emotion_summary,
            next_week_suggestions=next_week_suggestions
        )
        
        logger.info(f"[Reporter] 生成周报: user={user_id}")
        return report
    
    # ==================== 个性化响应建议 ====================
    
    def suggest_response_style(
        self,
        persona: UserPersona,
        context: str = ""
    ) -> Dict[str, Any]:
        """
        根据用户画像建议响应风格
        
        Args:
            persona: 用户画像
            context: 当前上下文
            
        Returns:
            响应风格建议
        """
        suggestions = {
            "format": "concise",
            "tone": "professional",
            "include_emoji": False,
            "proactive_care": False,
            "additional_tips": []
        }
        
        # 根据响应格式偏好
        if persona.response_format == "detailed":
            suggestions["format"] = "detailed"
            suggestions["additional_tips"].append("提供更详细的解释和步骤")
        elif persona.response_format == "structured":
            suggestions["format"] = "structured"
            suggestions["additional_tips"].append("使用列表和标题组织内容")
        
        # 根据情绪状态
        if persona.mood in ["stressed", "frustrated"]:
            suggestions["tone"] = "supportive"
            suggestions["proactive_care"] = True
            suggestions["additional_tips"].append("语气温和，表达理解")
        
        # 根据支持标志
        if persona.emotional_support and persona.support_flag:
            suggestions["proactive_care"] = True
            suggestions["additional_tips"].append("适时关怀，询问是否需要帮助")
        
        return suggestions
    
    def generate_proactive_message(
        self,
        persona: UserPersona,
        trigger: str
    ) -> Optional[str]:
        """
        生成主动关怀消息
        
        Args:
            persona: 用户画像
            trigger: 触发原因
            
        Returns:
            主动关怀消息，或 None
        """
        if not persona.emotional_support:
            return None
        
        messages = {
            "high_stress": "我注意到你最近工作比较忙，有什么我可以帮忙的吗？💙",
            "deadline_approaching": f"「{persona.active_plans[0].title if persona.active_plans else '项目'}」快到截止时间了，进展如何？需要我帮你整理下思路吗？",
            "long_silence": "好久没见你了，一切都还顺利吗？有什么新的工作需要帮忙安排吗？",
            "repeated_blocker": "你之前提到的问题解决了吗？如果还有困难，我们可以一起想想办法。"
        }
        
        return messages.get(trigger)
    
    # ==================== 内部方法 ====================
    
    def _summarize_daily_work(self, fragments: List[FragmentMemory]) -> str:
        """汇总每日工作"""
        if not fragments:
            return "今日暂无工作记录"
        
        lines = []
        
        # 按任务类别分组
        task_counts: Dict[str, int] = {}
        for f in fragments:
            if f.task_hint:
                category = f.task_hint.category
                task_counts[category] = task_counts.get(category, 0) + 1
        
        if task_counts:
            lines.append("**工作分布**:")
            for category, count in sorted(task_counts.items(), key=lambda x: -x[1]):
                lines.append(f"- {self._translate_category(category)}: {count}次对话")
        
        # 提取待办
        todos = [f.todo_hint for f in fragments if f.todo_hint]
        if todos:
            lines.append("\n**识别到的待办**:")
            for todo in todos[:3]:
                lines.append(f"- {todo.content}")
        
        return "\n".join(lines) if lines else "今日工作记录较少"
    
    def _summarize_weekly_work(self, fragments: List[FragmentMemory]) -> str:
        """汇总每周工作"""
        if not fragments:
            return "本周暂无工作记录"
        
        lines = [f"本周共 **{len(fragments)}** 次交互\n"]
        
        # 按星期分布
        day_counts: Dict[str, int] = {}
        for f in fragments:
            day = f.day_of_week.value
            day_counts[day] = day_counts.get(day, 0) + 1
        
        lines.append("**每日活跃度**:")
        day_names = {"monday": "周一", "tuesday": "周二", "wednesday": "周三",
                     "thursday": "周四", "friday": "周五", "saturday": "周六", "sunday": "周日"}
        for day in ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]:
            count = day_counts.get(day, 0)
            bar = "█" * min(count, 10)
            lines.append(f"- {day_names[day]}: {bar} ({count})")
        
        return "\n".join(lines)
    
    def _format_plan_status(self, plans: List[WorkPlan]) -> str:
        """格式化计划状态"""
        if not plans:
            return "暂无活跃计划"
        
        lines = []
        for plan in plans[:5]:
            # 状态图标
            if plan.status == "at_risk":
                icon = "⚠️"
            elif plan.status == "blocked":
                icon = "🚧"
            elif plan.progress >= 0.8:
                icon = "✅"
            else:
                icon = "🔄"
            
            progress_pct = int(plan.progress * 100)
            deadline_str = plan.deadline.strftime("%m/%d") if plan.deadline else "无截止"
            
            lines.append(f"{icon} **{plan.title}** - 进度 {progress_pct}% | 截止 {deadline_str}")
            
            if plan.blockers:
                lines.append(f"   └ 阻碍: {plan.blockers[0]}")
        
        return "\n".join(lines)
    
    def _format_plan_completion(self, plans: List[WorkPlan]) -> str:
        """格式化计划完成情况"""
        if not plans:
            return "暂无计划记录"
        
        completed = [p for p in plans if p.status == "completed"]
        active = [p for p in plans if p.status == "active"]
        at_risk = [p for p in plans if p.status in ["at_risk", "blocked"]]
        
        lines = [
            f"- ✅ 已完成: {len(completed)} 个",
            f"- 🔄 进行中: {len(active)} 个",
            f"- ⚠️ 有风险: {len(at_risk)} 个"
        ]
        
        return "\n".join(lines)
    
    def _format_behavior_insights(self, behavior: Optional[BehaviorPattern]) -> str:
        """格式化行为洞察"""
        if not behavior:
            return "数据不足，无法生成行为分析"
        
        lines = []
        
        # 推断角色
        if behavior.inferred_role != "unknown":
            role_names = {
                "product_manager": "产品经理",
                "developer": "开发工程师",
                "sales": "销售",
                "operations": "运营",
                "designer": "设计师",
                "analyst": "分析师"
            }
            role = role_names.get(behavior.inferred_role, behavior.inferred_role)
            confidence = int(behavior.role_confidence * 100)
            lines.append(f"**推断角色**: {role}（置信度 {confidence}%）")
        
        # 常规任务
        if behavior.routine_tasks:
            lines.append("\n**常规工作**:")
            for task in behavior.routine_tasks[:3]:
                lines.append(f"- {task.name}（{task.frequency}）")
        
        # 工作时间
        if behavior.time_pattern:
            tp = behavior.time_pattern
            if tp.work_start and tp.work_end:
                lines.append(f"\n**工作时间**: {tp.work_start} - {tp.work_end}")
            if tp.peak_hours:
                lines.append(f"**高效时段**: {', '.join(tp.peak_hours)}")
        
        return "\n".join(lines) if lines else "行为模式分析中..."
    
    def _format_emotion_summary(
        self,
        emotion: Optional[EmotionState],
        fragments: List[FragmentMemory]
    ) -> str:
        """格式化情绪摘要"""
        lines = []
        
        if emotion:
            mood_names = {
                "neutral": "😐 平和",
                "positive": "😊 积极",
                "stressed": "😰 压力较大",
                "frustrated": "😤 有些沮丧",
                "fatigue": "😩 疲惫"
            }
            mood = mood_names.get(emotion.current_mood, emotion.current_mood)
            stress_pct = int(emotion.stress_level * 100)
            lines.append(f"**当前状态**: {mood}")
            lines.append(f"**压力指数**: {stress_pct}%")
        
        # 从碎片中统计情绪
        if fragments:
            signals = {}
            for f in fragments:
                if f.emotion_hint:
                    sig = f.emotion_hint.signal
                    signals[sig] = signals.get(sig, 0) + 1
            
            if signals:
                lines.append("\n**本周情绪分布**:")
                for sig, count in sorted(signals.items(), key=lambda x: -x[1]):
                    lines.append(f"- {sig}: {count}次")
        
        return "\n".join(lines) if lines else "情绪状态良好 😊"
    
    def _generate_daily_suggestions(
        self,
        fragments: List[FragmentMemory],
        plans: List[WorkPlan]
    ) -> str:
        """生成每日建议"""
        suggestions = []
        
        # 检查即将到期的计划
        at_risk_plans = [p for p in plans if p.status == "at_risk" or 
                        (p.deadline and (p.deadline - datetime.now()).days <= 2)]
        if at_risk_plans:
            suggestions.append(f"⚠️ {len(at_risk_plans)} 个计划即将到期或有风险，建议优先处理")
        
        # 检查情绪状态
        stressed = sum(1 for f in fragments if f.emotion_hint and f.emotion_hint.stress_level > 0.6)
        if stressed > len(fragments) * 0.3:
            suggestions.append("💙 今日压力较大，建议适当休息")
        
        # 检查阻碍
        blocked_plans = [p for p in plans if p.blockers]
        if blocked_plans:
            suggestions.append(f"🚧 {len(blocked_plans)} 个计划有阻碍，需要协调解决")
        
        return "\n".join(suggestions) if suggestions else "✅ 一切顺利，继续保持！"
    
    def _generate_weekly_suggestions(
        self,
        plans: List[WorkPlan],
        behavior: Optional[BehaviorPattern],
        emotion: Optional[EmotionState]
    ) -> str:
        """生成每周建议"""
        suggestions = []
        
        # 基于计划
        incomplete = [p for p in plans if p.status == "active" and p.progress < 0.5]
        if incomplete:
            suggestions.append(f"📋 有 {len(incomplete)} 个计划进度不足 50%，建议重新评估优先级")
        
        # 基于行为模式
        if behavior and behavior.motivation:
            if behavior.motivation.pain_points:
                suggestions.append(f"💡 关注痛点: {behavior.motivation.pain_points[0]}")
        
        # 基于情绪
        if emotion and emotion.stress_level > 0.7:
            suggestions.append("🌟 压力较高，建议下周安排一些轻松的任务")
        
        return "\n".join(f"- {s}" for s in suggestions) if suggestions else "- 保持当前节奏，继续加油！"
    
    def _format_tomorrow_reminders(self, reminders: List[Any]) -> str:
        """格式化明日提醒"""
        if not reminders:
            return "暂无提醒"
        
        lines = []
        for r in reminders[:5]:
            time_str = r.time.strftime("%H:%M") if hasattr(r, 'time') else ""
            content = r.content if hasattr(r, 'content') else str(r)
            lines.append(f"- [{time_str}] {content}")
        
        return "\n".join(lines)
    
    def _translate_category(self, category: str) -> str:
        """翻译任务类别"""
        translations = {
            "customer_support": "客户支持",
            "report": "报告/汇报",
            "meeting": "会议",
            "development": "开发",
            "document": "文档",
            "analysis": "分析",
            "coordination": "协调",
            "general": "一般任务"
        }
        return translations.get(category, category)


# ==================== 工厂函数 ====================

_reporter_instance: Optional[Reporter] = None


def get_reporter() -> Reporter:
    """获取汇报器单例"""
    global _reporter_instance
    if _reporter_instance is None:
        _reporter_instance = Reporter()
    return _reporter_instance


def reset_reporter() -> None:
    """重置汇报器（用于测试）"""
    global _reporter_instance
    _reporter_instance = None
