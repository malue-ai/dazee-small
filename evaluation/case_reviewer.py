"""
失败案例审核器（Case Reviewer）

提供人工审核和标注接口，用于：
1. 审核失败案例
2. 提供参考答案
3. 标记案例状态
4. 批量导出待转换案例
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from core.monitoring.failure_detector import FailureCase, FailureDetector, FailureType

logger = logging.getLogger(__name__)


class CaseReviewer:
    """
    失败案例审核器
    
    使用方式：
        reviewer = CaseReviewer(failure_detector)
        
        # 获取待审核案例
        pending = reviewer.get_pending_cases(limit=50)
        
        # 审核案例
        reviewer.review_case(
            case_id="case_123",
            reviewer="alice",
            reference_answer="这是推荐的答案...",
            notes="问题已修复"
        )
        
        # 批量导出待转换案例
        ready = reviewer.get_ready_for_conversion()
    """
    
    def __init__(self, failure_detector: FailureDetector):
        """
        初始化审核器
        
        Args:
            failure_detector: 失败检测器实例
        """
        self.failure_detector = failure_detector
    
    def get_pending_cases(
        self,
        limit: int = 50,
        failure_types: Optional[List[FailureType]] = None,
        min_severity: Optional[str] = None
    ) -> List[FailureCase]:
        """
        获取待审核案例
        
        Args:
            limit: 数量限制
            failure_types: 失败类型筛选（可选）
            min_severity: 最低严重程度（可选）
            
        Returns:
            List[FailureCase]: 待审核案例列表
        """
        # 获取所有未审核的案例
        all_cases = self.failure_detector.get_cases(status="new", limit=limit * 2)
        
        # 筛选
        filtered = []
        for case in all_cases:
            if failure_types and case.failure_type not in failure_types:
                continue
            if min_severity:
                severity_order = ["low", "medium", "high", "critical"]
                if severity_order.index(case.severity.value) < severity_order.index(min_severity):
                    continue
            filtered.append(case)
        
        return filtered[:limit]
    
    def review_case(
        self,
        case_id: str,
        reviewer: str,
        reference_answer: Optional[str] = None,
        notes: Optional[str] = None,
        should_convert: bool = True
    ) -> Optional[FailureCase]:
        """
        审核案例
        
        Args:
            case_id: 案例ID
            reviewer: 审核人
            reference_answer: 参考答案（可选）
            notes: 备注（可选）
            should_convert: 是否应该转换为评测任务
            
        Returns:
            FailureCase: 更新后的案例
        """
        case = self.failure_detector.mark_reviewed(case_id, reviewer)
        
        if not case:
            logger.warning(f"⚠️ 未找到案例: {case_id}")
            return None
        
        # 添加参考答案和备注到 context
        if reference_answer:
            case.context["reference_answer"] = reference_answer
        if notes:
            case.context["review_notes"] = notes
        if should_convert:
            case.context["should_convert"] = True
        
        # 更新状态
        if should_convert:
            case.status = "converted"
        else:
            case.status = "reviewed"
        
        logger.info(f"✅ 案例审核完成: {case_id} by {reviewer}")
        return case
    
    def get_ready_for_conversion(
        self,
        limit: int = 100
    ) -> List[FailureCase]:
        """
        获取已审核且可以转换为评测任务的案例
        
        Args:
            limit: 数量限制
            
        Returns:
            List[FailureCase]: 待转换案例列表
        """
        # 获取已审核的案例
        reviewed = self.failure_detector.get_cases(status="reviewed", limit=limit * 2)
        converted = self.failure_detector.get_cases(status="converted", limit=limit * 2)
        
        # 合并并筛选
        ready = []
        for case in reviewed + converted:
            # 检查是否有参考答案
            has_reference = (
                case.context.get("reference_answer") or
                case.agent_response
            )
            
            # 检查是否标记为应该转换
            should_convert = case.context.get("should_convert", True)
            
            if has_reference and should_convert:
                ready.append(case)
        
        return ready[:limit]
    
    def get_review_statistics(
        self,
        time_range_days: int = 7
    ) -> Dict[str, Any]:
        """
        获取审核统计信息
        
        Args:
            time_range_days: 时间范围（天）
            
        Returns:
            Dict: 统计信息
        """
        from datetime import timedelta
        
        cutoff = datetime.now() - timedelta(days=time_range_days)
        
        all_cases = self.failure_detector.get_cases(limit=1000)
        recent_cases = [c for c in all_cases if c.timestamp >= cutoff]
        
        by_status = {}
        by_type = {}
        by_reviewer = {}
        
        for case in recent_cases:
            # 按状态统计
            by_status[case.status] = by_status.get(case.status, 0) + 1
            
            # 按类型统计
            by_type[case.failure_type.value] = by_type.get(case.failure_type.value, 0) + 1
            
            # 按审核人统计
            if case.reviewed_by:
                by_reviewer[case.reviewed_by] = by_reviewer.get(case.reviewed_by, 0) + 1
        
        return {
            "total_cases": len(recent_cases),
            "by_status": by_status,
            "by_type": by_type,
            "by_reviewer": by_reviewer,
            "pending_review": by_status.get("new", 0),
            "ready_for_conversion": len(self.get_ready_for_conversion()),
        }
    
    def export_review_summary(
        self,
        output_path: Optional[str] = None
    ) -> str:
        """
        导出审核摘要报告
        
        Args:
            output_path: 输出路径（可选）
            
        Returns:
            str: Markdown 格式的报告
        """
        stats = self.get_review_statistics()
        ready_cases = self.get_ready_for_conversion(limit=50)
        
        lines = [
            "# 失败案例审核摘要",
            f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "## 统计信息",
            "",
            f"- 总案例数: {stats['total_cases']}",
            f"- 待审核: {stats['pending_review']}",
            f"- 待转换: {stats['ready_for_conversion']}",
            "",
            "### 按状态分布",
            "",
        ]
        
        for status, count in stats["by_status"].items():
            lines.append(f"- {status}: {count}")
        
        lines.extend([
            "",
            "### 按类型分布",
            "",
        ])
        
        for failure_type, count in stats["by_type"].items():
            lines.append(f"- {failure_type}: {count}")
        
        lines.extend([
            "",
            "### 按审核人分布",
            "",
        ])
        
        for reviewer, count in stats["by_reviewer"].items():
            lines.append(f"- {reviewer}: {count}")
        
        lines.extend([
            "",
            "## 待转换案例列表",
            "",
            "| 案例ID | 失败类型 | 严重程度 | 用户查询 | 状态 |",
            "|--------|----------|----------|----------|------|",
        ])
        
        for case in ready_cases[:20]:  # 只显示前20个
            lines.append(
                f"| {case.id} | {case.failure_type.value} | {case.severity.value} | "
                f"{case.user_query[:50]}... | {case.status} |"
            )
        
        report = "\n".join(lines)
        
        if output_path:
            from pathlib import Path
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(report)
        
        return report
