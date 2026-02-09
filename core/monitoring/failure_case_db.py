"""
失败案例库（Failure Case DB）

存储和管理失败案例，支持：
1. 持久化存储（文件/数据库）
2. 查询和检索
3. 导出为评估任务
4. 统计分析
"""

import asyncio
import json
import os
from dataclasses import asdict
from datetime import datetime, timedelta

from utils.app_paths import get_user_data_dir
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiofiles

from core.monitoring.failure_detector import FailureCase, FailureSeverity, FailureType
from logger import get_logger

logger = get_logger(__name__)


class FailureCaseDB:
    """
    失败案例数据库

    使用方式：
        db = FailureCaseDB(storage_path="data/failure_cases")

        # 保存案例
        db.save(failure_case)

        # 查询案例
        cases = db.query(failure_type=FailureType.CONTEXT_OVERFLOW)

        # 导出为评估任务
        tasks = db.export_as_eval_tasks(case_ids=["case_001", "case_002"])
    """

    def __init__(self, storage_path: str = "", retention_days: int = 30):
        """
        初始化失败案例数据库

        Args:
            storage_path: 存储路径
            retention_days: 保留天数

        注意：需要调用 await initialize() 完成异步初始化
        """
        self.storage_path = Path(storage_path) if storage_path else get_user_data_dir() / "data" / "failure_cases"
        self.retention_days = retention_days

        # 确保存储目录存在
        self.storage_path.mkdir(parents=True, exist_ok=True)

        # 内存缓存
        self._cache: Dict[str, FailureCase] = {}

        # 初始化标记
        self._initialized: bool = False

    async def initialize(self) -> None:
        """
        异步初始化：加载现有案例

        使用方式：
            db = FailureCaseDB()
            await db.initialize()
        """
        if self._initialized:
            return

        await self._load_all_async()
        self._initialized = True

    # ===================
    # 存储操作
    # ===================

    async def save(self, case: FailureCase) -> None:
        """
        保存失败案例（异步）

        Args:
            case: 失败案例
        """
        # 保存到内存缓存
        self._cache[case.id] = case

        # 持久化到文件（异步）
        file_path = self._get_file_path(case.id)
        content = json.dumps(case.to_dict(), ensure_ascii=False, indent=2)

        async with aiofiles.open(file_path, "w", encoding="utf-8") as f:
            await f.write(content)

        logger.debug(f"💾 保存失败案例: {case.id}")

    def delete(self, case_id: str) -> bool:
        """
        删除失败案例

        Args:
            case_id: 案例ID

        Returns:
            bool: 是否删除成功
        """
        # 从缓存删除
        if case_id in self._cache:
            del self._cache[case_id]

        # 从文件删除
        file_path = self._get_file_path(case_id)
        if file_path.exists():
            file_path.unlink()
            logger.debug(f"🗑️ 删除失败案例: {case_id}")
            return True

        return False

    def get(self, case_id: str) -> Optional[FailureCase]:
        """
        获取失败案例

        Args:
            case_id: 案例ID

        Returns:
            FailureCase: 失败案例
        """
        return self._cache.get(case_id)

    async def update(self, case: FailureCase) -> None:
        """
        更新失败案例（异步）

        Args:
            case: 失败案例
        """
        await self.save(case)

    # ===================
    # 查询操作
    # ===================

    def query(
        self,
        failure_type: Optional[FailureType] = None,
        severity: Optional[FailureSeverity] = None,
        status: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        user_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[FailureCase]:
        """
        查询失败案例

        Args:
            failure_type: 失败类型
            severity: 严重程度
            status: 状态
            start_date: 开始日期
            end_date: 结束日期
            user_id: 用户ID
            limit: 返回数量限制
            offset: 偏移量

        Returns:
            List[FailureCase]: 失败案例列表
        """
        cases = list(self._cache.values())

        # 应用筛选条件
        if failure_type:
            cases = [c for c in cases if c.failure_type == failure_type]

        if severity:
            cases = [c for c in cases if c.severity == severity]

        if status:
            cases = [c for c in cases if c.status == status]

        if start_date:
            cases = [c for c in cases if c.timestamp >= start_date]

        if end_date:
            cases = [c for c in cases if c.timestamp <= end_date]

        if user_id:
            cases = [c for c in cases if c.user_id == user_id]

        # 按时间倒序排序
        cases.sort(key=lambda c: c.timestamp, reverse=True)

        # 分页
        return cases[offset : offset + limit]

    def count(
        self,
        failure_type: Optional[FailureType] = None,
        severity: Optional[FailureSeverity] = None,
        status: Optional[str] = None,
    ) -> int:
        """
        统计失败案例数量

        Args:
            failure_type: 失败类型
            severity: 严重程度
            status: 状态

        Returns:
            int: 数量
        """
        cases = self.query(
            failure_type=failure_type,
            severity=severity,
            status=status,
            limit=100000,  # 大数值获取全部
        )
        return len(cases)

    def get_pending_review(self, limit: int = 100) -> List[FailureCase]:
        """
        获取待审查的案例

        Args:
            limit: 返回数量限制

        Returns:
            List[FailureCase]: 待审查案例列表
        """
        return self.query(status="new", limit=limit)

    # ===================
    # 导出操作
    # ===================

    def export_as_eval_tasks(
        self,
        case_ids: Optional[List[str]] = None,
        failure_types: Optional[List[FailureType]] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        导出为评估任务（YAML格式的字典）

        Args:
            case_ids: 指定案例ID列表
            failure_types: 失败类型列表
            limit: 数量限制

        Returns:
            List[Dict]: 评估任务列表（可序列化为YAML）
        """
        if case_ids:
            cases = [self.get(cid) for cid in case_ids if self.get(cid)]
        elif failure_types:
            cases = []
            for ft in failure_types:
                cases.extend(self.query(failure_type=ft, limit=limit))
            cases = cases[:limit]
        else:
            cases = self.query(limit=limit)

        tasks = []
        for case in cases:
            task = {
                "id": f"regression_{case.id}",
                "description": f"回归测试: {case.error_message[:100]}",
                "category": "regression",
                "source_case_id": case.id,
                "input": {
                    "user_query": case.user_query,
                    "conversation_history": case.conversation_history,
                    "context": case.context,
                },
                "expected_outcome": {
                    # 根据失败类型生成预期结果
                    "should_not_fail": True,
                    "original_failure_type": case.failure_type.value,
                },
                "graders": self._generate_graders_for_case(case),
                "trials": 3,
                "timeout_seconds": 60,
                "tags": ["regression", case.failure_type.value],
                "metadata": {
                    "source_case": case.id,
                    "original_timestamp": case.timestamp.isoformat(),
                    "severity": case.severity.value,
                },
            }
            tasks.append(task)

        return tasks

    def _generate_graders_for_case(self, case: FailureCase) -> List[Dict[str, Any]]:
        """
        根据失败类型生成评分器配置

        Args:
            case: 失败案例

        Returns:
            List[Dict]: 评分器配置列表
        """
        graders = []

        # 通用评分器：检查是否有工具调用错误
        graders.append(
            {
                "type": "code",
                "name": "check_no_tool_errors",
                "check": "check_no_tool_errors()",
            }
        )

        # 根据失败类型添加特定评分器
        if case.failure_type == FailureType.CONTEXT_OVERFLOW:
            max_tokens = case.token_usage.get("max", 200000)
            graders.append(
                {
                    "type": "code",
                    "name": "check_token_limit",
                    "check": f"check_token_limit({max_tokens})",
                }
            )

        elif case.failure_type == FailureType.TIMEOUT:
            timeout = case.context.get("timeout_seconds", 60) * 1000  # 转换为毫秒
            graders.append(
                {
                    "type": "code",
                    "name": "check_execution_time",
                    "check": f"check_execution_time({timeout})",
                }
            )

        elif case.failure_type == FailureType.USER_NEGATIVE_FEEDBACK:
            graders.append(
                {
                    "type": "model",
                    "rubric": "grade_response_quality",
                    "min_score": 4,
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

        return graders

    async def export_to_yaml_file(
        self,
        output_path: str,
        case_ids: Optional[List[str]] = None,
        failure_types: Optional[List[FailureType]] = None,
    ) -> str:
        """
        导出为YAML文件（异步）

        Args:
            output_path: 输出文件路径
            case_ids: 指定案例ID列表
            failure_types: 失败类型列表

        Returns:
            str: 输出文件路径
        """
        import yaml

        tasks = self.export_as_eval_tasks(case_ids=case_ids, failure_types=failure_types)

        suite = {
            "id": f"regression_suite_{datetime.now().strftime('%Y%m%d')}",
            "name": "回归测试套件（自动生成）",
            "description": "从失败案例自动生成的回归测试",
            "category": "regression",
            "default_trials": 3,
            "metadata": {
                "generated_at": datetime.now().isoformat(),
                "source": "failure_case_db",
                "case_count": len(tasks),
            },
            "tasks": tasks,
        }

        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        content = yaml.dump(suite, allow_unicode=True, default_flow_style=False)
        async with aiofiles.open(output_file, "w", encoding="utf-8") as f:
            await f.write(content)

        logger.info(f"📄 导出回归测试套件: {output_path} ({len(tasks)} 个任务)")

        return str(output_file)

    # ===================
    # 统计分析
    # ===================

    def get_statistics(self) -> Dict[str, Any]:
        """
        获取统计信息

        Returns:
            Dict: 统计信息
        """
        cases = list(self._cache.values())

        # 按类型统计
        by_type = {}
        for ft in FailureType:
            by_type[ft.value] = sum(1 for c in cases if c.failure_type == ft)

        # 按严重程度统计
        by_severity = {}
        for s in FailureSeverity:
            by_severity[s.value] = sum(1 for c in cases if c.severity == s)

        # 按状态统计
        statuses = set(c.status for c in cases)
        by_status = {s: sum(1 for c in cases if c.status == s) for s in statuses}

        # 时间分布（最近7天）
        daily_counts = {}
        for i in range(7):
            date = datetime.now() - timedelta(days=i)
            date_str = date.strftime("%Y-%m-%d")
            daily_counts[date_str] = sum(
                1 for c in cases if c.timestamp.strftime("%Y-%m-%d") == date_str
            )

        return {
            "total_cases": len(cases),
            "by_type": by_type,
            "by_severity": by_severity,
            "by_status": by_status,
            "daily_counts": daily_counts,
            "pending_review": by_status.get("new", 0),
            "converted_to_tasks": by_status.get("converted", 0),
        }

    # ===================
    # 清理操作
    # ===================

    def cleanup_old_cases(self) -> int:
        """
        清理过期案例

        Returns:
            int: 清理的案例数量
        """
        cutoff = datetime.now() - timedelta(days=self.retention_days)

        deleted_count = 0
        for case_id, case in list(self._cache.items()):
            if case.timestamp < cutoff and case.status in ["resolved", "converted"]:
                self.delete(case_id)
                deleted_count += 1

        if deleted_count > 0:
            logger.info(f"🧹 清理了 {deleted_count} 个过期案例")

        return deleted_count

    # ===================
    # 内部方法
    # ===================

    def _get_file_path(self, case_id: str) -> Path:
        """获取案例文件路径"""
        return self.storage_path / f"{case_id}.json"

    async def _load_all_async(self) -> None:
        """异步加载所有案例到内存"""
        # 使用 asyncio.to_thread 包装同步的 glob 操作
        file_paths = await asyncio.to_thread(list, self.storage_path.glob("*.json"))
        for file_path in file_paths:
            try:
                async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
                    content = await f.read()
                    data = json.loads(content)

                case = self._dict_to_case(data)
                self._cache[case.id] = case

            except Exception as e:
                logger.error(f"加载案例失败 {file_path}: {e}")

        logger.info(f"📂 加载了 {len(self._cache)} 个失败案例")

    def _dict_to_case(self, data: Dict[str, Any]) -> FailureCase:
        """字典转换为FailureCase"""
        return FailureCase(
            id=data["id"],
            failure_type=FailureType(data["failure_type"]),
            severity=FailureSeverity(data["severity"]),
            conversation_id=data["conversation_id"],
            user_id=data.get("user_id"),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            user_query=data.get("user_query", ""),
            conversation_history=data.get("conversation_history", []),
            error_message=data.get("error_message", ""),
            stack_trace=data.get("stack_trace"),
            tool_calls=data.get("tool_calls", []),
            agent_response=data.get("agent_response", ""),
            token_usage=data.get("token_usage", {}),
            context=data.get("context", {}),
            status=data.get("status", "new"),
            reviewed_by=data.get("reviewed_by"),
            reviewed_at=(
                datetime.fromisoformat(data["reviewed_at"]) if data.get("reviewed_at") else None
            ),
        )
