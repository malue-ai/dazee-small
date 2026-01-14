"""
ZenFlux Agent 生产监控模块

实现 Swiss Cheese Model 的多层防护：
1. 实时监控（响应延迟、Token消耗、工具调用成功率）
2. 失败检测（上下文溢出、工具调用失败、用户负面反馈）
3. 失败案例库（自动收集、分类、存储）
4. 闭环转化（失败案例 → 评估任务 → 回归测试）
5. Token 审计（消耗记录、统计分析、异常检测）

参考：https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents
"""

from core.monitoring.production_monitor import ProductionMonitor
from core.monitoring.failure_detector import FailureDetector
from core.monitoring.failure_case_db import FailureCaseDB
from core.monitoring.case_converter import CaseConverter
from core.monitoring.token_audit import (
    TokenAuditor,
    TokenAuditRecord,
    TokenAuditStats,
    AuditLevel,
    get_token_auditor,
    create_token_auditor,
)

__all__ = [
    "ProductionMonitor",
    "FailureDetector",
    "FailureCaseDB",
    "CaseConverter",
    # Token 审计
    "TokenAuditor",
    "TokenAuditRecord",
    "TokenAuditStats",
    "AuditLevel",
    "get_token_auditor",
    "create_token_auditor",
]
