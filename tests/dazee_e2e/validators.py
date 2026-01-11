"""
Dazee E2E 验证检查点

对测试结果进行高标准验证
"""

from typing import List, Dict, Any, Tuple
from datetime import datetime

from logger import get_logger
from core.memory.mem0 import FragmentMemory, BehaviorPattern, WorkPlan, ReminderItem

from test_data import (
    get_weekly_conversations,
    get_expected_behavior_pattern,
    get_expected_plans,
    get_expected_reminders,
)

logger = get_logger("dazee.e2e.validators")


class ValidationResult:
    """验证结果"""
    
    def __init__(self, checkpoint: str):
        self.checkpoint = checkpoint
        self.passed = True
        self.score = 0.0
        self.max_score = 0.0
        self.details: List[Dict[str, Any]] = []
        self.errors: List[str] = []
    
    def add_check(self, name: str, passed: bool, expected: Any, actual: Any, weight: float = 1.0):
        """添加检查项"""
        if passed:
            self.score += weight
        self.max_score += weight
        
        self.details.append({
            "name": name,
            "passed": passed,
            "expected": str(expected),
            "actual": str(actual),
            "weight": weight
        })
        
        if not passed:
            self.passed = False
            self.errors.append(f"{name}: 预期 {expected}, 实际 {actual}")
    
    def get_accuracy(self) -> float:
        """获取准确率"""
        return (self.score / self.max_score * 100) if self.max_score > 0 else 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "checkpoint": self.checkpoint,
            "passed": self.passed,
            "accuracy": f"{self.get_accuracy():.1f}%",
            "score": f"{self.score}/{self.max_score}",
            "details": self.details,
            "errors": self.errors
        }


class DazeeE2EValidator:
    """Dazee E2E 验证器"""
    
    def __init__(self):
        self.results: Dict[str, ValidationResult] = {}
        logger.info("[E2E Validator] 初始化")
    
    def validate_all(
        self,
        fragments: List[FragmentMemory],
        behavior_pattern: BehaviorPattern,
        plans: List[WorkPlan],
        reminders: List[ReminderItem]
    ) -> Dict[str, ValidationResult]:
        """
        执行所有验证检查点
        
        Returns:
            检查点结果字典
        """
        logger.info("\n" + "=" * 60)
        logger.info("[E2E Validator] 开始验证")
        logger.info("=" * 60)
        
        # 检查点 1: 碎片提取准确性
        self.results["checkpoint1"] = self.validate_fragments(fragments)
        
        # 检查点 2: 5W1H 行为分析合理性
        self.results["checkpoint2"] = self.validate_behavior_pattern(behavior_pattern)
        
        # 检查点 3: 计划识别与管理
        self.results["checkpoint3"] = self.validate_plans(plans)
        
        # 检查点 4: 提醒调度
        self.results["checkpoint4"] = self.validate_reminders(reminders, plans)
        
        # 检查点 5: 汇报生成价值（需要人工审查）
        self.results["checkpoint5"] = self.validate_reports_quality()
        
        self._print_summary()
        
        return self.results
    
    def validate_fragments(self, fragments: List[FragmentMemory]) -> ValidationResult:
        """检查点 1: 碎片提取准确性"""
        logger.info("\n[检查点 1/5] 碎片提取准确性")
        logger.info("-" * 60)
        
        result = ValidationResult("检查点1: 碎片提取准确性")
        conversations = get_weekly_conversations()
        
        if len(fragments) != len(conversations):
            result.add_check(
                "碎片数量",
                passed=False,
                expected=len(conversations),
                actual=len(fragments),
                weight=2.0
            )
            logger.warning(f"✗ 碎片数量不匹配: 预期 {len(conversations)}, 实际 {len(fragments)}")
        else:
            result.add_check(
                "碎片数量",
                passed=True,
                expected=len(conversations),
                actual=len(fragments),
                weight=2.0
            )
            logger.info(f"✓ 碎片数量正确: {len(fragments)}")
        
        # 任务识别准确率
        task_correct = 0
        task_total = 0
        for frag, conv in zip(fragments, conversations):
            if conv['expected']['task']:
                task_total += 1
                expected_task = conv['expected']['task'].lower()
                actual_task = (frag.task_hint.category if frag.task_hint else "none").lower()
                
                # 模糊匹配（包含关键词即可）
                if expected_task in actual_task or actual_task in expected_task or expected_task == "general":
                    task_correct += 1
        
        task_accuracy = task_correct / task_total if task_total > 0 else 0
        result.add_check(
            "任务识别准确率",
            passed=task_accuracy >= 0.80,
            expected=">= 80%",
            actual=f"{task_accuracy:.0%}",
            weight=3.0
        )
        logger.info(f"{'✓' if task_accuracy >= 0.80 else '✗'} 任务识别: {task_correct}/{task_total} ({task_accuracy:.0%})")
        
        # 情绪检测准确率
        emotion_correct = 0
        emotion_total = 0
        for frag, conv in zip(fragments, conversations):
            if conv['expected']['emotion']:
                emotion_total += 1
                expected_emotion = conv['expected']['emotion']
                actual_emotion = frag.emotion_hint.signal if frag.emotion_hint else "neutral"
                
                if expected_emotion == actual_emotion:
                    emotion_correct += 1
                elif expected_emotion == "neutral" and actual_emotion in ["neutral", "positive"]:
                    emotion_correct += 0.5  # 部分正确
        
        emotion_accuracy = emotion_correct / emotion_total if emotion_total > 0 else 0
        result.add_check(
            "情绪检测准确率",
            passed=emotion_accuracy >= 0.70,
            expected=">= 70%",
            actual=f"{emotion_accuracy:.0%}",
            weight=2.0
        )
        logger.info(f"{'✓' if emotion_accuracy >= 0.70 else '✗'} 情绪检测: {emotion_correct}/{emotion_total} ({emotion_accuracy:.0%})")
        
        # 关系提取准确率
        relation_correct = 0
        relation_total = 0
        for frag, conv in zip(fragments, conversations):
            if conv['expected']['relations']:
                relation_total += len(conv['expected']['relations'])
                actual_relations = frag.relation_hint.mentioned if frag.relation_hint else []
                
                for expected_person in conv['expected']['relations']:
                    # 模糊匹配（包含即可）
                    if any(expected_person in r or r in expected_person for r in actual_relations):
                        relation_correct += 1
        
        relation_accuracy = relation_correct / relation_total if relation_total > 0 else 0
        result.add_check(
            "关系提取准确率",
            passed=relation_accuracy >= 0.80,
            expected=">= 80%",
            actual=f"{relation_accuracy:.0%}",
            weight=2.0
        )
        logger.info(f"{'✓' if relation_accuracy >= 0.80 else '✗'} 关系提取: {relation_correct}/{relation_total} ({relation_accuracy:.0%})")
        
        # 待办识别准确率
        todo_correct = 0
        todo_total = 0
        for frag, conv in zip(fragments, conversations):
            if conv['expected']['todo']:
                todo_total += 1
                if frag.todo_hint and frag.todo_hint.content:
                    todo_correct += 1
        
        todo_accuracy = todo_correct / todo_total if todo_total > 0 else 0
        result.add_check(
            "待办识别准确率",
            passed=todo_accuracy >= 0.70,
            expected=">= 70%",
            actual=f"{todo_accuracy:.0%}",
            weight=1.0
        )
        logger.info(f"{'✓' if todo_accuracy >= 0.70 else '✗'} 待办识别: {todo_correct}/{todo_total} ({todo_accuracy:.0%})")
        
        logger.info(f"\n检查点 1 完成: {'通过' if result.passed else '失败'}, 得分 {result.score:.1f}/{result.max_score}")
        return result
    
    def validate_behavior_pattern(self, behavior_pattern: BehaviorPattern) -> ValidationResult:
        """检查点 2: 5W1H 行为分析合理性"""
        logger.info("\n[检查点 2/5] 5W1H 行为分析合理性")
        logger.info("-" * 60)
        
        result = ValidationResult("检查点2: 5W1H 行为分析")
        expected = get_expected_behavior_pattern()
        
        if not behavior_pattern:
            result.add_check("行为模式存在", passed=False, expected="存在", actual="不存在", weight=10.0)
            logger.error("✗ 行为模式为空")
            return result
        
        # 角色推断
        role_correct = behavior_pattern.inferred_role == expected["inferred_role"]
        result.add_check(
            "角色推断",
            passed=role_correct,
            expected=expected["inferred_role"],
            actual=behavior_pattern.inferred_role,
            weight=3.0
        )
        logger.info(f"{'✓' if role_correct else '✗'} 角色推断: {behavior_pattern.inferred_role} "
                   f"(置信度: {behavior_pattern.role_confidence:.0%})")
        
        role_confidence_ok = behavior_pattern.role_confidence >= expected["role_confidence_min"]
        result.add_check(
            "角色置信度",
            passed=role_confidence_ok,
            expected=f">= {expected['role_confidence_min']:.0%}",
            actual=f"{behavior_pattern.role_confidence:.0%}",
            weight=1.0
        )
        
        # What - 常规任务
        task_count = len(behavior_pattern.routine_tasks)
        task_count_ok = task_count >= expected["what"]["min_routine_tasks"]
        result.add_check(
            "常规任务数量",
            passed=task_count_ok,
            expected=f">= {expected['what']['min_routine_tasks']}",
            actual=task_count,
            weight=2.0
        )
        logger.info(f"{'✓' if task_count_ok else '✗'} 识别常规任务: {task_count} 个")
        
        if behavior_pattern.routine_tasks:
            for task in behavior_pattern.routine_tasks[:3]:
                logger.info(f"  - {task.name} ({task.frequency})")
        
        # When - 时间模式
        has_time_pattern = behavior_pattern.time_pattern is not None
        result.add_check(
            "时间模式存在",
            passed=has_time_pattern,
            expected="存在",
            actual="存在" if has_time_pattern else "不存在",
            weight=1.0
        )
        logger.info(f"{'✓' if has_time_pattern else '✗'} 时间模式识别")
        
        # Who - 协作者
        collab_count = len(behavior_pattern.collaborators)
        collab_count_ok = collab_count >= expected["who"]["min_collaborators"]
        result.add_check(
            "协作者数量",
            passed=collab_count_ok,
            expected=f">= {expected['who']['min_collaborators']}",
            actual=collab_count,
            weight=2.0
        )
        logger.info(f"{'✓' if collab_count_ok else '✗'} 识别协作者: {collab_count} 人")
        
        if behavior_pattern.collaborators:
            logger.info(f"  协作者: {[c.name for c in behavior_pattern.collaborators]}")
        
        # Why - 动机
        has_motivation = behavior_pattern.motivation is not None
        motivation_ok = has_motivation and (
            len(behavior_pattern.motivation.primary_goals) > 0 or
            len(behavior_pattern.motivation.motivations) > 0 or
            len(behavior_pattern.motivation.pain_points) > 0
        )
        result.add_check(
            "动机识别",
            passed=motivation_ok,
            expected="至少1个动机/目标/痛点",
            actual="存在" if motivation_ok else "缺失",
            weight=1.0
        )
        logger.info(f"{'✓' if motivation_ok else '✗'} 动机识别")
        
        # How - 工作风格
        has_work_style = behavior_pattern.work_style is not None
        result.add_check(
            "工作风格",
            passed=has_work_style,
            expected="存在",
            actual="存在" if has_work_style else "缺失",
            weight=1.0
        )
        
        if has_work_style:
            logger.info(f"✓ 工作风格: {behavior_pattern.work_style.work_style}")
        
        logger.info(f"\n检查点 2 完成: {'通过' if result.passed else '失败'}, 得分 {result.score:.1f}/{result.max_score}")
        return result
    
    def validate_plans(self, plans: List[WorkPlan]) -> ValidationResult:
        """检查点 3: 计划识别与管理"""
        logger.info("\n[检查点 3/5] 计划识别与管理")
        logger.info("-" * 60)
        
        result = ValidationResult("检查点3: 计划识别")
        expected_plans = get_expected_plans()
        
        # 计划数量
        plan_count_ok = len(plans) >= 1
        result.add_check(
            "计划数量",
            passed=plan_count_ok,
            expected=">= 1",
            actual=len(plans),
            weight=3.0
        )
        logger.info(f"{'✓' if plan_count_ok else '✗'} 识别计划: {len(plans)} 个")
        
        if not plans:
            logger.warning("✗ 未识别到任何计划")
            return result
        
        # 验证关键计划（永辉合同）
        key_plan = None
        for plan in plans:
            if any(keyword in plan.title for keyword in ["永辉", "合同", "签"]):
                key_plan = plan
                break
        
        if key_plan:
            logger.info(f"✓ 识别到关键计划: {key_plan.title}")
            result.add_check("关键计划识别", passed=True, expected="永辉合同", actual=key_plan.title, weight=2.0)
            
            # 优先级
            priority_ok = key_plan.priority in ["high", "urgent"]
            result.add_check(
                "优先级合理性",
                passed=priority_ok,
                expected="high/urgent",
                actual=key_plan.priority,
                weight=1.0
            )
            logger.info(f"{'✓' if priority_ok else '✗'} 优先级: {key_plan.priority}")
            
            # 截止时间
            has_deadline = key_plan.deadline is not None
            result.add_check(
                "截止时间存在",
                passed=has_deadline,
                expected="存在",
                actual="存在" if has_deadline else "缺失",
                weight=1.0
            )
            
            if has_deadline:
                days_until = (key_plan.deadline - datetime.now()).days
                logger.info(f"✓ 截止时间: {key_plan.deadline.strftime('%m-%d')} ({days_until}天后)")
            
            # 阻碍识别
            has_blockers = len(key_plan.blockers) > 0
            result.add_check(
                "阻碍识别",
                passed=has_blockers,
                expected=">= 1",
                actual=len(key_plan.blockers),
                weight=1.0
            )
            logger.info(f"{'✓' if has_blockers else '✗'} 阻碍: {key_plan.blockers if has_blockers else '无'}")
            
        else:
            result.add_check("关键计划识别", passed=False, expected="永辉合同", actual="未识别", weight=2.0)
            logger.warning("✗ 未识别到关键计划（永辉合同）")
        
        # 进度更新验证（检查是否有进度 > 0 的计划）
        plans_with_progress = [p for p in plans if p.progress > 0]
        result.add_check(
            "进度跟踪",
            passed=len(plans_with_progress) > 0,
            expected=">= 1个有进度",
            actual=f"{len(plans_with_progress)}个",
            weight=1.0
        )
        
        logger.info(f"\n检查点 3 完成: {'通过' if result.passed else '失败'}, 得分 {result.score:.1f}/{result.max_score}")
        return result
    
    def validate_reminders(self, reminders: List[ReminderItem], plans: List[WorkPlan]) -> ValidationResult:
        """检查点 4: 提醒调度"""
        logger.info("\n[检查点 4/5] 提醒调度")
        logger.info("-" * 60)
        
        result = ValidationResult("检查点4: 提醒调度")
        
        # 提醒数量
        reminder_count_ok = len(reminders) >= 1
        result.add_check(
            "提醒数量",
            passed=reminder_count_ok,
            expected=">= 1",
            actual=len(reminders),
            weight=2.0
        )
        logger.info(f"{'✓' if reminder_count_ok else '✗'} 创建提醒: {len(reminders)} 个")
        
        if not reminders:
            logger.warning("✗ 未创建任何提醒")
            return result
        
        # 截止日期提醒
        deadline_reminders = [r for r in reminders if r.reminder_type.value == "deadline"]
        has_deadline_reminder = len(deadline_reminders) > 0
        result.add_check(
            "截止日期提醒",
            passed=has_deadline_reminder,
            expected=">= 1",
            actual=len(deadline_reminders),
            weight=2.0
        )
        logger.info(f"{'✓' if has_deadline_reminder else '✗'} 截止日期提醒: {len(deadline_reminders)} 个")
        
        # 提醒时间合理性（应该在未来）
        future_reminders = [r for r in reminders if r.time > datetime.now()]
        time_ok = len(future_reminders) == len(reminders)
        result.add_check(
            "提醒时间合理性",
            passed=time_ok,
            expected="全部在未来",
            actual=f"{len(future_reminders)}/{len(reminders)}在未来",
            weight=1.0
        )
        logger.info(f"{'✓' if time_ok else '✗'} 提醒时间: {len(future_reminders)}/{len(reminders)} 在未来")
        
        # 提醒关联计划
        reminders_with_plan = [r for r in reminders if r.related_plan_id]
        link_ok = len(reminders_with_plan) > 0
        result.add_check(
            "提醒关联计划",
            passed=link_ok,
            expected=">= 1",
            actual=len(reminders_with_plan),
            weight=1.0
        )
        logger.info(f"{'✓' if link_ok else '✗'} 关联计划: {len(reminders_with_plan)} 个")
        
        logger.info(f"\n检查点 4 完成: {'通过' if result.passed else '失败'}, 得分 {result.score:.1f}/{result.max_score}")
        return result
    
    def validate_reports_quality(self) -> ValidationResult:
        """检查点 5: 汇报生成价值（需要人工审查）"""
        logger.info("\n[检查点 5/5] 汇报生成价值")
        logger.info("-" * 60)
        
        result = ValidationResult("检查点5: 汇报生成价值")
        
        # 这个检查点需要人工审查汇报内容
        logger.info("⚠️  此检查点需要人工审查汇报内容")
        logger.info("    请检查生成的日报和周报是否包含:")
        logger.info("    1. 工作摘要准确")
        logger.info("    2. 计划状态清晰")
        logger.info("    3. 建议有价值")
        logger.info("    4. 5W1H 洞察合理")
        logger.info("    5. 情绪摘要恰当")
        
        # 标记为通过，但提示需要人工确认
        result.add_check(
            "汇报内容质量",
            passed=True,
            expected="需人工审查",
            actual="待审查",
            weight=0.0  # 不计入自动评分
        )
        
        logger.info(f"\n检查点 5 完成: 需人工审查")
        return result
    
    def _print_summary(self):
        """打印验证摘要"""
        logger.info("\n" + "=" * 60)
        logger.info("验证摘要")
        logger.info("=" * 60)
        
        total_passed = sum(1 for r in self.results.values() if r.passed)
        total_checkpoints = len(self.results)
        
        for checkpoint_id, result in self.results.items():
            status = "✓ 通过" if result.passed else "✗ 失败"
            logger.info(f"{status} - {result.checkpoint} ({result.get_accuracy():.1f}%)")
            
            if result.errors:
                for error in result.errors[:3]:  # 只显示前3个错误
                    logger.warning(f"  ! {error}")
        
        logger.info("-" * 60)
        logger.info(f"总计: {total_passed}/{total_checkpoints} 个检查点通过")
        logger.info("=" * 60)


def validate_pipeline_results(results: Dict[str, Any]) -> Dict[str, ValidationResult]:
    """验证流程结果（便捷函数）"""
    validator = DazeeE2EValidator()
    return validator.validate_all(
        fragments=results["fragments"],
        behavior_pattern=results["behavior_pattern"],
        plans=results["plans"],
        reminders=results["reminders"]
    )


if __name__ == "__main__":
    # 测试验证器
    print("验证器模块已加载")
    print("请运行 run_e2e_test.py 执行完整测试")
