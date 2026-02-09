"""
案例转换器（Case Converter）

实现闭环机制：
1. 失败案例 → 评估任务
2. 评估任务 → 回归测试套件
3. 自动添加到CI/CD
4. 定期报告生成

这是 Swiss Cheese Model 的关键环节，确保从真实失败中学习。
"""

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from utils.app_paths import get_user_data_dir

import aiofiles

from core.monitoring.failure_case_db import FailureCaseDB
from core.monitoring.failure_detector import FailureCase, FailureSeverity, FailureType
from logger import get_logger

logger = get_logger(__name__)


class CaseConverter:
    """
    案例转换器

    使用方式：
        converter = CaseConverter(failure_db=failure_case_db)

        # 转换单个案例
        task = converter.convert_to_eval_task(case)

        # 批量转换并生成回归测试套件
        suite_path = converter.generate_regression_suite()

        # 自动闭环（定期运行）
        await converter.auto_close_loop()
    """

    def __init__(
        self,
        failure_db: FailureCaseDB,
        eval_suites_dir: str = "",
        min_cases_for_suite: int = 5,
    ):
        """
        初始化案例转换器

        Args:
            failure_db: 失败案例数据库
            eval_suites_dir: 评估套件目录
            min_cases_for_suite: 生成套件的最小案例数
        """
        self.failure_db = failure_db
        self.eval_suites_dir = Path(eval_suites_dir) if eval_suites_dir else get_user_data_dir() / "evaluation" / "suites" / "regression"
        self.min_cases_for_suite = min_cases_for_suite

        # 确保目录存在
        self.eval_suites_dir.mkdir(parents=True, exist_ok=True)

    # ===================
    # 案例转换
    # ===================

    def convert_to_eval_task(
        self, case: FailureCase, custom_graders: Optional[List[Dict]] = None
    ) -> Dict[str, Any]:
        """
        将失败案例转换为评估任务

        Args:
            case: 失败案例
            custom_graders: 自定义评分器配置

        Returns:
            Dict: 评估任务配置
        """
        # 生成基础任务结构
        task = {
            "id": f"regression_{case.id}",
            "description": self._generate_task_description(case),
            "category": "regression",
            "source": {
                "type": "failure_case",
                "case_id": case.id,
                "failure_type": case.failure_type.value,
                "severity": case.severity.value,
                "original_timestamp": case.timestamp.isoformat(),
            },
            "input": {
                "user_query": case.user_query,
                "conversation_history": case.conversation_history,
                "context": case.context,
            },
            "expected_outcome": self._generate_expected_outcome(case),
            "graders": custom_graders or self._generate_graders(case),
            "trials": 3,
            "timeout_seconds": self._calculate_timeout(case),
            "tags": self._generate_tags(case),
            "metadata": {
                "converted_at": datetime.now().isoformat(),
                "original_error": case.error_message,
            },
        }

        return task

    def _generate_task_description(self, case: FailureCase) -> str:
        """生成任务描述"""
        type_descriptions = {
            FailureType.CONTEXT_OVERFLOW: "上下文溢出回归测试",
            FailureType.TOOL_CALL_FAILURE: "工具调用失败回归测试",
            FailureType.CONSECUTIVE_TOOL_ERRORS: "连续工具错误回归测试",
            FailureType.USER_NEGATIVE_FEEDBACK: "用户负面反馈改进测试",
            FailureType.INTENT_MISMATCH: "意图识别回归测试",
            FailureType.TIMEOUT: "超时问题回归测试",
            FailureType.RESPONSE_QUALITY: "响应质量改进测试",
            FailureType.SAFETY_VIOLATION: "安全合规回归测试",
            FailureType.UNKNOWN_ERROR: "未知错误回归测试",
        }

        base = type_descriptions.get(case.failure_type, "回归测试")
        query_preview = (
            case.user_query[:50] + "..." if len(case.user_query) > 50 else case.user_query
        )

        return f"{base}: {query_preview}"

    def _generate_expected_outcome(self, case: FailureCase) -> Dict[str, Any]:
        """生成预期结果"""
        outcome = {
            "should_succeed": True,  # 回归测试的核心目标
            "original_failure_type": case.failure_type.value,
        }

        # 根据失败类型添加特定预期
        if case.failure_type == FailureType.CONTEXT_OVERFLOW:
            max_tokens = case.token_usage.get("max", 200000)
            outcome["max_tokens"] = max_tokens
            outcome["token_efficiency"] = "high"

        elif case.failure_type == FailureType.TIMEOUT:
            timeout = case.context.get("timeout_seconds", 60)
            outcome["max_duration_seconds"] = timeout * 0.8  # 比原来更快

        elif case.failure_type == FailureType.INTENT_MISMATCH:
            outcome["expected_intent"] = case.context.get("expected_intent")

        return outcome

    def _generate_graders(self, case: FailureCase) -> List[Dict[str, Any]]:
        """生成评分器配置"""
        graders = []

        # 通用：检查无工具错误
        graders.append(
            {
                "type": "code",
                "name": "no_tool_errors",
                "check": "check_no_tool_errors()",
            }
        )

        # 根据失败类型添加特定评分器
        if case.failure_type == FailureType.CONTEXT_OVERFLOW:
            max_tokens = case.token_usage.get("max", 200000)
            graders.append(
                {
                    "type": "code",
                    "name": "token_limit",
                    "check": f"check_token_limit({int(max_tokens * 0.9)})",  # 90%阈值
                }
            )
            graders.append(
                {
                    "type": "code",
                    "name": "token_efficiency",
                    "check": "check_token_efficiency(5000)",  # 每次调用最多5000 tokens
                }
            )

        elif case.failure_type == FailureType.TIMEOUT:
            timeout_ms = case.context.get("timeout_seconds", 60) * 1000
            graders.append(
                {
                    "type": "code",
                    "name": "execution_time",
                    "check": f"check_execution_time({int(timeout_ms * 0.8)})",  # 80%阈值
                }
            )

        elif case.failure_type == FailureType.USER_NEGATIVE_FEEDBACK:
            graders.append(
                {
                    "type": "model",
                    "rubric": "grade_response_quality",
                    "min_score": 4,
                    "weight": 2.0,  # 质量评分权重加倍
                }
            )

        elif case.failure_type == FailureType.INTENT_MISMATCH:
            graders.append(
                {
                    "type": "model",
                    "rubric": "grade_intent_understanding",
                    "min_score": 4,
                }
            )

        elif case.failure_type == FailureType.SAFETY_VIOLATION:
            graders.append(
                {
                    "type": "model",
                    "rubric": "grade_safety_compliance",
                    "min_score": 5,  # 安全必须满分
                }
            )

        # 通用：过度工程化检测
        graders.append(
            {
                "type": "model",
                "rubric": "grade_over_engineering",
                "min_score": 4,
            }
        )

        return graders

    def _calculate_timeout(self, case: FailureCase) -> int:
        """计算超时时间"""
        if case.failure_type == FailureType.TIMEOUT:
            # 超时案例使用更长的超时时间
            return case.context.get("timeout_seconds", 60) * 2

        return 60  # 默认60秒

    def _generate_tags(self, case: FailureCase) -> List[str]:
        """生成标签"""
        tags = [
            "regression",
            case.failure_type.value,
            case.severity.value,
        ]

        # 添加用户相关标签
        if case.user_id:
            tags.append("user_specific")

        # 添加时间相关标签
        if case.timestamp.weekday() >= 5:
            tags.append("weekend")

        return tags

    # ===================
    # 批量转换
    # ===================

    async def generate_regression_suite(
        self,
        failure_types: Optional[List[FailureType]] = None,
        max_cases: int = 100,
        output_filename: Optional[str] = None,
    ) -> Optional[str]:
        """
        生成回归测试套件（异步）

        Args:
            failure_types: 失败类型筛选
            max_cases: 最大案例数
            output_filename: 输出文件名

        Returns:
            str: 生成的文件路径（如果案例数足够）
        """
        # 获取待转换的案例
        cases = self.failure_db.query(status="reviewed", limit=max_cases)

        if failure_types:
            cases = [c for c in cases if c.failure_type in failure_types]

        if len(cases) < self.min_cases_for_suite:
            logger.info(f"案例数 ({len(cases)}) 不足 {self.min_cases_for_suite}，跳过生成")
            return None

        # 转换为评估任务
        tasks = [self.convert_to_eval_task(case) for case in cases]

        # 生成套件
        suite = {
            "id": f"regression_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "name": f"回归测试套件 ({len(tasks)} 个任务)",
            "description": "从失败案例自动生成的回归测试套件",
            "category": "regression",
            "default_trials": 3,
            "metadata": {
                "generated_at": datetime.now().isoformat(),
                "source_cases": [c.id for c in cases],
                "failure_types": list(set(c.failure_type.value for c in cases)),
            },
            "tasks": tasks,
        }

        # 保存到文件（异步）
        if output_filename is None:
            output_filename = f"regression_{datetime.now().strftime('%Y%m%d')}.yaml"

        output_path = self.eval_suites_dir / output_filename

        import yaml

        content = yaml.dump(suite, allow_unicode=True, default_flow_style=False)
        async with aiofiles.open(output_path, "w", encoding="utf-8") as f:
            await f.write(content)

        # 更新案例状态（异步）
        for case in cases:
            case.status = "converted"
            await self.failure_db.update(case)

        logger.info(f"📋 生成回归测试套件: {output_path} ({len(tasks)} 个任务)")

        return str(output_path)

    # ===================
    # 自动闭环
    # ===================

    async def auto_close_loop(self) -> Dict[str, Any]:
        """
        自动闭环流程

        流程：
        1. 检查新增的失败案例
        2. 自动审查简单案例
        3. 生成回归测试套件
        4. 返回处理报告

        Returns:
            Dict: 处理报告
        """
        report = {
            "timestamp": datetime.now().isoformat(),
            "new_cases_found": 0,
            "auto_reviewed": 0,
            "suite_generated": False,
            "suite_path": None,
        }

        # 1. 获取新案例
        new_cases = self.failure_db.query(status="new", limit=100)
        report["new_cases_found"] = len(new_cases)

        # 2. 自动审查简单案例
        auto_reviewed_count = 0
        for case in new_cases:
            if self._can_auto_review(case):
                case.status = "reviewed"
                case.reviewed_by = "auto_reviewer"
                case.reviewed_at = datetime.now()
                self.failure_db.update(case)
                auto_reviewed_count += 1

        report["auto_reviewed"] = auto_reviewed_count

        # 3. 检查是否需要生成新套件
        reviewed_count = self.failure_db.count(status="reviewed")
        if reviewed_count >= self.min_cases_for_suite:
            suite_path = self.generate_regression_suite()
            if suite_path:
                report["suite_generated"] = True
                report["suite_path"] = suite_path

        logger.info(f"🔄 闭环处理完成: {report}")

        return report

    def _can_auto_review(self, case: FailureCase) -> bool:
        """
        判断案例是否可以自动审查

        自动审查条件：
        1. 高严重度案例（CRITICAL/HIGH）必须人工审查
        2. 安全违规必须人工审查
        3. 其他案例可以自动审查

        Args:
            case: 失败案例

        Returns:
            bool: 是否可以自动审查
        """
        # 高严重度需要人工审查
        if case.severity in [FailureSeverity.CRITICAL, FailureSeverity.HIGH]:
            return False

        # 安全违规需要人工审查
        if case.failure_type == FailureType.SAFETY_VIOLATION:
            return False

        # 用户负面反馈需要人工审查（可能需要分析原因）
        if case.failure_type == FailureType.USER_NEGATIVE_FEEDBACK:
            return False

        return True

    # ===================
    # 报告生成
    # ===================

    def generate_weekly_report(self) -> Dict[str, Any]:
        """
        生成每周闭环报告

        Returns:
            Dict: 周报数据
        """
        from datetime import timedelta

        # 本周时间范围
        now = datetime.now()
        week_start = now - timedelta(days=7)

        # 统计数据
        stats = self.failure_db.get_statistics()

        # 本周案例
        weekly_cases = self.failure_db.query(start_date=week_start, limit=1000)

        # 按类型统计
        by_type = {}
        for ft in FailureType:
            count = sum(1 for c in weekly_cases if c.failure_type == ft)
            if count > 0:
                by_type[ft.value] = count

        # 转化率
        converted = sum(1 for c in weekly_cases if c.status == "converted")
        conversion_rate = converted / len(weekly_cases) if weekly_cases else 0

        return {
            "report_type": "weekly_close_loop",
            "period": {
                "start": week_start.isoformat(),
                "end": now.isoformat(),
            },
            "summary": {
                "total_cases": len(weekly_cases),
                "converted_to_tests": converted,
                "conversion_rate": f"{conversion_rate:.1%}",
                "pending_review": stats["pending_review"],
            },
            "by_failure_type": by_type,
            "top_issues": self._identify_top_issues(weekly_cases),
            "recommendations": self._generate_recommendations(weekly_cases),
        }

    def _identify_top_issues(
        self, cases: List[FailureCase], top_n: int = 3
    ) -> List[Dict[str, Any]]:
        """识别最常见问题"""
        from collections import Counter

        # 按错误消息聚合
        error_counts = Counter(c.error_message[:100] for c in cases)

        top_issues = []
        for error, count in error_counts.most_common(top_n):
            # 找到代表性案例
            example = next(c for c in cases if c.error_message.startswith(error[:100]))

            top_issues.append(
                {
                    "error_pattern": error,
                    "count": count,
                    "failure_type": example.failure_type.value,
                    "severity": example.severity.value,
                    "example_case_id": example.id,
                }
            )

        return top_issues

    def _generate_recommendations(self, cases: List[FailureCase]) -> List[str]:
        """生成改进建议"""
        recommendations = []

        # 统计失败类型
        type_counts = {}
        for case in cases:
            type_counts[case.failure_type] = type_counts.get(case.failure_type, 0) + 1

        # 根据最常见问题生成建议
        if type_counts.get(FailureType.CONTEXT_OVERFLOW, 0) > 5:
            recommendations.append(
                "上下文溢出频繁发生，建议：\n"
                "1. 优化对话历史压缩策略\n"
                "2. 考虑使用更长上下文窗口的模型"
            )

        if type_counts.get(FailureType.TIMEOUT, 0) > 5:
            recommendations.append(
                "超时问题较多，建议：\n" "1. 分析超时案例的工具调用模式\n" "2. 优化工具执行效率"
            )

        if type_counts.get(FailureType.INTENT_MISMATCH, 0) > 5:
            recommendations.append(
                "意图识别错误较多，建议：\n" "1. 增加意图识别的训练样本\n" "2. 优化意图分析提示词"
            )

        if type_counts.get(FailureType.USER_NEGATIVE_FEEDBACK, 0) > 3:
            recommendations.append(
                "用户负面反馈较多，建议：\n"
                "1. 分析反馈内容，识别共性问题\n"
                "2. 改进响应质量和用户体验"
            )

        if not recommendations:
            recommendations.append("本周失败案例较少，系统运行稳定。")

        return recommendations
