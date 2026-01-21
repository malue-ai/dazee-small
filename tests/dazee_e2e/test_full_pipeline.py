"""
Dazee E2E 完整流程测试

验证从碎片提取到汇报生成的完整流程
使用真实 LLM 调用（Claude Haiku）
"""

import asyncio
import os
from datetime import datetime
from typing import List, Dict, Any, Optional
from pathlib import Path

import pytest

RUN_DAZEE_E2E = os.getenv("RUN_DAZEE_E2E", "false").lower() == "true"
if not RUN_DAZEE_E2E:
    pytest.skip("未启用 RUN_DAZEE_E2E，跳过 Dazee E2E 测试", allow_module_level=True)

from logger import get_logger
from core.memory.mem0 import (
    get_fragment_extractor,
    get_behavior_analyzer,
    get_pdca_manager,
    get_reminder,
    get_reporter,
    FragmentMemory,
    BehaviorPattern,
    WorkPlan,
    ReminderItem,
)

try:
    # 作为包内测试执行
    from .test_data import (
        get_weekly_conversations,
        get_test_metadata,
        TEST_USER_ID,
        TEST_USER_NAME,
        TEST_SESSION_ID_PREFIX,
    )
except ImportError:
    # 作为脚本直接运行
    from test_data import (
        get_weekly_conversations,
        get_test_metadata,
        TEST_USER_ID,
        TEST_USER_NAME,
        TEST_SESSION_ID_PREFIX,
    )

logger = get_logger("dazee.e2e.pipeline")


class DazeeE2EPipeline:
    """
    Dazee 端到端测试流程
    
    执行完整的用户画像生成流程
    """
    
    def __init__(self):
        """初始化测试流程"""
        self.user_id = TEST_USER_ID
        self.user_name = TEST_USER_NAME
        self.metadata = get_test_metadata()
        
        # 结果存储
        self.fragments: List[FragmentMemory] = []
        self.behavior_pattern: Optional[BehaviorPattern] = None
        self.plans: List[WorkPlan] = []
        self.reminders: List[ReminderItem] = []
        self.daily_reports: Dict[str, str] = {}
        self.weekly_report: str = ""
        
        # 统计信息
        self.stats = {
            "llm_calls": {
                "extraction": 0,
                "analysis": 0,
                "planning": 0,
            },
            "execution_time": {},
            "errors": []
        }
        
        logger.info(f"[E2E Pipeline] 初始化: user={self.user_name}, 对话数={self.metadata['total_conversations']}")
    
    async def run_full_pipeline(self) -> Dict[str, Any]:
        """
        运行完整流程
        
        Returns:
            包含所有结果和统计信息的字典
        """
        logger.info("=" * 60)
        logger.info("[E2E Pipeline] 开始执行完整流程")
        logger.info("=" * 60)
        
        start_time = datetime.now()
        
        try:
            # 阶段 1: 碎片提取
            await self._stage1_fragment_extraction()
            
            # 阶段 2: 行为分析
            await self._stage2_behavior_analysis()
            
            # 阶段 3: 计划管理
            await self._stage3_plan_management()
            
            # 阶段 4: 提醒调度
            await self._stage4_reminder_scheduling()
            
            # 阶段 5: 汇报生成
            await self._stage5_report_generation()
            
            total_time = (datetime.now() - start_time).total_seconds()
            logger.info(f"[E2E Pipeline] 流程完成，总耗时: {total_time:.2f}秒")
            
            return self._build_results()
            
        except Exception as e:
            logger.error(f"[E2E Pipeline] 流程执行失败: {e}", exc_info=True)
            self.stats["errors"].append(str(e))
            raise
    
    async def _stage1_fragment_extraction(self):
        """阶段 1: 碎片记忆提取"""
        logger.info("\n[阶段 1/5] 碎片记忆提取")
        logger.info("-" * 60)
        
        start_time = datetime.now()
        extractor = get_fragment_extractor()
        conversations = get_weekly_conversations()
        
        for i, conv in enumerate(conversations, 1):
            session_id = f"{TEST_SESSION_ID_PREFIX}{conv['timestamp'].strftime('%Y%m%d')}"
            
            logger.info(f"[{i}/{len(conversations)}] 提取碎片: {conv['scenario']}")
            logger.debug(f"  消息: {conv['content']}")
            
            try:
                fragment = await extractor.extract(
                    user_id=self.user_id,
                    session_id=session_id,
                    message=conv['content'],
                    timestamp=conv['timestamp']
                )
                
                self.fragments.append(fragment)
                self.stats["llm_calls"]["extraction"] += 1
                
                # 输出提取结果
                logger.info(f"  ✓ 任务: {fragment.task_hint.content if fragment.task_hint else 'None'}")
                logger.info(f"  ✓ 情绪: {fragment.emotion_hint.signal if fragment.emotion_hint else 'neutral'}")
                if fragment.relation_hint:
                    logger.info(f"  ✓ 提及: {fragment.relation_hint.mentioned}")
                if fragment.todo_hint:
                    logger.info(f"  ✓ 待办: {fragment.todo_hint.content}")
                
            except Exception as e:
                logger.error(f"  ✗ 提取失败: {e}")
                self.stats["errors"].append(f"Fragment extraction failed at {i}: {e}")
        
        elapsed = (datetime.now() - start_time).total_seconds()
        self.stats["execution_time"]["stage1_extraction"] = elapsed
        logger.info(f"\n阶段 1 完成: 提取 {len(self.fragments)} 个碎片，耗时 {elapsed:.2f}秒")
    
    async def _stage2_behavior_analysis(self):
        """阶段 2: 5W1H 行为分析"""
        logger.info("\n[阶段 2/5] 5W1H 行为分析")
        logger.info("-" * 60)
        
        start_time = datetime.now()
        analyzer = get_behavior_analyzer()
        
        try:
            logger.info(f"分析 {len(self.fragments)} 个碎片记忆...")
            
            self.behavior_pattern = await analyzer.analyze(
                user_id=self.user_id,
                fragments=self.fragments,
                analysis_days=7
            )
            
            self.stats["llm_calls"]["analysis"] += 1
            
            # 输出分析结果
            logger.info(f"✓ 推断角色: {self.behavior_pattern.inferred_role} "
                       f"(置信度: {self.behavior_pattern.role_confidence:.0%})")
            
            if self.behavior_pattern.routine_tasks:
                logger.info(f"✓ 常规任务: {len(self.behavior_pattern.routine_tasks)} 个")
                for task in self.behavior_pattern.routine_tasks[:3]:
                    logger.info(f"  - {task.name} ({task.frequency})")
            
            if self.behavior_pattern.collaborators:
                logger.info(f"✓ 协作者: {[c.name for c in self.behavior_pattern.collaborators]}")
            
            if self.behavior_pattern.time_pattern:
                tp = self.behavior_pattern.time_pattern
                if tp.work_start:
                    logger.info(f"✓ 工作时间: {tp.work_start} - {tp.work_end}")
            
        except Exception as e:
            logger.error(f"✗ 行为分析失败: {e}")
            self.stats["errors"].append(f"Behavior analysis failed: {e}")
        
        elapsed = (datetime.now() - start_time).total_seconds()
        self.stats["execution_time"]["stage2_analysis"] = elapsed
        logger.info(f"\n阶段 2 完成，耗时 {elapsed:.2f}秒")
    
    async def _stage3_plan_management(self):
        """阶段 3: PDCA 计划管理"""
        logger.info("\n[阶段 3/5] PDCA 计划管理")
        logger.info("-" * 60)
        
        start_time = datetime.now()
        planner = get_pdca_manager()
        conversations = get_weekly_conversations()
        
        for i, conv in enumerate(conversations, 1):
            logger.info(f"[{i}/{len(conversations)}] 分析计划: {conv['scenario']}")
            
            try:
                plan = await planner.analyze_for_plan(
                    user_id=self.user_id,
                    message=conv['content']
                )
                
                self.stats["llm_calls"]["planning"] += 1
                
                if plan:
                    self.plans.append(plan)
                    logger.info(f"  ✓ 识别到计划: {plan.title}")
                    logger.info(f"    优先级: {plan.priority}, 进度: {plan.progress:.0%}")
                    if plan.deadline:
                        logger.info(f"    截止: {plan.deadline.strftime('%m-%d')}")
                    if plan.blockers:
                        logger.info(f"    阻碍: {plan.blockers}")
                else:
                    logger.debug(f"  - 未识别到计划")
                
            except Exception as e:
                logger.error(f"  ✗ 计划分析失败: {e}")
                self.stats["errors"].append(f"Plan analysis failed at {i}: {e}")
        
        elapsed = (datetime.now() - start_time).total_seconds()
        self.stats["execution_time"]["stage3_planning"] = elapsed
        logger.info(f"\n阶段 3 完成: 识别 {len(self.plans)} 个计划，耗时 {elapsed:.2f}秒")
    
    async def _stage4_reminder_scheduling(self):
        """阶段 4: 智能提醒调度"""
        logger.info("\n[阶段 4/5] 智能提醒调度")
        logger.info("-" * 60)
        
        start_time = datetime.now()
        reminder_manager = get_reminder()
        
        # 为计划创建提醒
        for plan in self.plans:
            try:
                # 截止日期提醒
                if plan.deadline:
                    reminder = reminder_manager.create_deadline_reminder(
                        user_id=self.user_id,
                        plan=plan,
                        advance_hours=24
                    )
                    if reminder:
                        self.reminders.append(reminder)
                        logger.info(f"✓ 创建截止提醒: {plan.title} @ {reminder.time.strftime('%m-%d %H:%M')}")
                
                # 进度检查提醒（仅活跃计划）
                if plan.status == "active" and plan.progress < 0.5:
                    reminder = reminder_manager.create_progress_reminder(
                        user_id=self.user_id,
                        plan=plan,
                        check_interval_hours=48
                    )
                    self.reminders.append(reminder)
                    logger.info(f"✓ 创建进度检查提醒: {plan.title} @ {reminder.time.strftime('%m-%d %H:%M')}")
                
            except Exception as e:
                logger.error(f"✗ 提醒创建失败: {e}")
                self.stats["errors"].append(f"Reminder creation failed for {plan.title}: {e}")
        
        elapsed = (datetime.now() - start_time).total_seconds()
        self.stats["execution_time"]["stage4_reminder"] = elapsed
        logger.info(f"\n阶段 4 完成: 创建 {len(self.reminders)} 个提醒，耗时 {elapsed:.2f}秒")
    
    async def _stage5_report_generation(self):
        """阶段 5: 智能汇报生成"""
        logger.info("\n[阶段 5/5] 智能汇报生成")
        logger.info("-" * 60)
        
        start_time = datetime.now()
        reporter = get_reporter()
        
        try:
            # 生成每日洞察（取最后一天）
            last_day_fragments = [f for f in self.fragments if f.timestamp.date() == self.fragments[-1].timestamp.date()]
            
            logger.info(f"生成每日洞察（{len(last_day_fragments)} 个碎片）...")
            self.daily_reports["last_day"] = reporter.generate_daily_report(
                user_id=self.user_id,
                user_name=self.user_name,
                fragments=last_day_fragments,
                plans=self.plans,
                reminders=self.reminders,
                date=self.fragments[-1].timestamp
            )
            logger.info("✓ 每日洞察生成完成")
            
            # 生成每周洞察
            logger.info(f"生成每周洞察（{len(self.fragments)} 个碎片）...")
            self.weekly_report = reporter.generate_weekly_report(
                user_id=self.user_id,
                user_name=self.user_name,
                fragments=self.fragments,
                plans=self.plans,
                behavior=self.behavior_pattern,
                emotion=None,  # 暂不支持独立 EmotionState
                start_date=self.metadata['test_period']['start']
            )
            logger.info("✓ 每周洞察生成完成")
            
        except Exception as e:
            logger.error(f"✗ 汇报生成失败: {e}")
            self.stats["errors"].append(f"Report generation failed: {e}")
        
        elapsed = (datetime.now() - start_time).total_seconds()
        self.stats["execution_time"]["stage5_reporting"] = elapsed
        logger.info(f"\n阶段 5 完成，耗时 {elapsed:.2f}秒")
    
    def _build_results(self) -> Dict[str, Any]:
        """构建测试结果"""
        return {
            "metadata": self.metadata,
            "fragments": self.fragments,
            "behavior_pattern": self.behavior_pattern,
            "plans": self.plans,
            "reminders": self.reminders,
            "reports": {
                "daily": self.daily_reports,
                "weekly": self.weekly_report
            },
            "stats": self.stats
        }


async def run_pipeline() -> Dict[str, Any]:
    """运行完整流程（便捷函数）"""
    pipeline = DazeeE2EPipeline()
    return await pipeline.run_full_pipeline()


if __name__ == "__main__":
    # 直接运行测试
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    
    results = asyncio.run(run_pipeline())
    
    print("\n" + "=" * 60)
    print("测试完成！")
    print("=" * 60)
    print(f"碎片提取: {len(results['fragments'])} 个")
    print(f"计划识别: {len(results['plans'])} 个")
    print(f"提醒创建: {len(results['reminders'])} 个")
    print(f"LLM 调用: {sum(results['stats']['llm_calls'].values())} 次")
    print(f"错误数量: {len(results['stats']['errors'])}")
