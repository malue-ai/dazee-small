"""
失败案例转换器（Case Converter）

将 FailureCase 自动转换为评测任务（Task YAML）。

转换流程：
1. 从 FailureDetector 获取失败案例
2. 人工审核并标注（status: reviewed）
3. 人工提供参考答案（reference_answer）
4. 自动生成 Task YAML（status: converted）
5. 加入回归测试套件
"""

import logging
import yaml
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.monitoring.failure_detector import FailureCase, FailureType
from evaluation.models import Task, TaskInput, ExpectedOutcome, GraderConfig, GraderType, Checkpoint

logger = logging.getLogger(__name__)


class CaseConverter:
    """
    失败案例转换器
    
    使用方式：
        converter = CaseConverter(output_dir="evaluation/suites/regression")
        
        # 转换单个案例
        task = converter.convert_case(failure_case, reference_answer="...")
        
        # 批量转换
        tasks = converter.convert_cases(failure_cases, reference_answers)
        
        # 导出为 YAML
        converter.export_to_yaml(tasks, suite_name="regression_from_failures")
    """
    
    def __init__(self, output_dir: str = "evaluation/suites/regression"):
        """
        初始化转换器
        
        Args:
            output_dir: 输出目录
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def convert_case(
        self,
        case: FailureCase,
        reference_answer: Optional[str] = None,
        custom_graders: Optional[List[GraderConfig]] = None
    ) -> Task:
        """
        将失败案例转换为评测任务
        
        Args:
            case: 失败案例
            reference_answer: 参考答案（可选，如果未提供则从 agent_response 提取）
            custom_graders: 自定义评分器（可选）
            
        Returns:
            Task: 评测任务
        """
        # 确定任务类别
        category = self._determine_category(case.failure_type)
        
        # 构建输入
        task_input = TaskInput(
            user_query=case.user_query,
            conversation_history=case.conversation_history,
            context=case.context,
        )
        
        # 构建预期结果
        expected_outcome = ExpectedOutcome(
            tool_calls=[
                tc.get("name") for tc in case.tool_calls
                if isinstance(tc, dict) and tc.get("name")
            ],
        )
        
        # 构建评分器
        graders = custom_graders or self._build_default_graders(case)
        
        # 构建检查点（如果有工具调用）
        checkpoints = []
        if case.tool_calls:
            checkpoints.append(Checkpoint(
                name="tool_calls_executed",
                check=f"tool_calls_count() >= {len(case.tool_calls)}",
                description="验证工具调用已执行"
            ))
        
        # 使用参考答案
        ref_answer = reference_answer or case.agent_response
        
        # 创建任务
        task = Task(
            id=f"regression_{case.id}",
            description=f"回归测试: {case.failure_type.value} - {case.error_message[:100]}",
            category=category,
            input=task_input,
            expected_outcome=expected_outcome,
            graders=graders,
            trials=3,
            timeout_seconds=60,
            tags=["regression", case.failure_type.value, "from_failure_case"],
            metadata={
                "source_case_id": case.id,
                "failure_type": case.failure_type.value,
                "severity": case.severity.value,
                "original_timestamp": case.timestamp.isoformat(),
            },
            checkpoints=checkpoints,
            reference_answer=ref_answer,
        )
        
        return task
    
    def _determine_category(self, failure_type: FailureType) -> str:
        """根据失败类型确定任务类别"""
        category_map = {
            FailureType.CONTEXT_OVERFLOW: "conversation",
            FailureType.TOOL_CALL_FAILURE: "coding",
            FailureType.CONSECUTIVE_TOOL_ERRORS: "coding",
            FailureType.USER_NEGATIVE_FEEDBACK: "conversation",
            FailureType.INTENT_MISMATCH: "conversation",
            FailureType.TIMEOUT: "general",
            FailureType.RESPONSE_QUALITY: "conversation",
            FailureType.OVER_ENGINEERING: "general",
            FailureType.LOGICAL_INCOHERENCE: "conversation",
            FailureType.USER_RETRY: "conversation",
            FailureType.SAFETY_VIOLATION: "safety",
            FailureType.UNKNOWN_ERROR: "general",
        }
        return category_map.get(failure_type, "general")
    
    def _build_default_graders(self, case: FailureCase) -> List[GraderConfig]:
        """根据失败类型构建默认评分器"""
        graders = []
        
        # 根据失败类型选择评分器
        if case.failure_type == FailureType.RESPONSE_QUALITY:
            graders.append(GraderConfig(
                type=GraderType.MODEL,
                name="grade_response_quality",
                rubric="grade_response_quality",
                min_score=4.0,
            ))
        
        elif case.failure_type == FailureType.OVER_ENGINEERING:
            graders.append(GraderConfig(
                type=GraderType.MODEL,
                name="grade_over_engineering",
                rubric="grade_over_engineering",
                min_score=4.0,
            ))
        
        elif case.failure_type == FailureType.INTENT_MISMATCH:
            graders.append(GraderConfig(
                type=GraderType.MODEL,
                name="grade_intent_understanding",
                rubric="grade_intent_understanding",
                min_score=4.0,
            ))
        
        elif case.failure_type == FailureType.TOOL_CALL_FAILURE:
            graders.append(GraderConfig(
                type=GraderType.CODE,
                name="check_no_tool_errors",
                check="check_no_tool_errors()",
            ))
        
        # 如果有参考答案，添加对比评分器
        if case.agent_response:
            graders.append(GraderConfig(
                type=GraderType.MODEL,
                name="grade_against_reference",
                rubric="grade_against_reference",
                min_score=4.0,
            ))
        
        # 默认添加工具调用验证（如果有工具调用）
        if case.tool_calls:
            expected_tools = [
                tc.get("name") for tc in case.tool_calls
                if isinstance(tc, dict) and tc.get("name")
            ]
            if expected_tools:
                graders.append(GraderConfig(
                    type=GraderType.CODE,
                    name="check_tool_calls",
                    check=f"tool_calls_contain({expected_tools[0]})",
                ))
        
        return graders
    
    def convert_cases(
        self,
        cases: List[FailureCase],
        reference_answers: Optional[Dict[str, str]] = None
    ) -> List[Task]:
        """
        批量转换失败案例
        
        Args:
            cases: 失败案例列表
            reference_answers: 参考答案字典（case_id -> answer）
            
        Returns:
            List[Task]: 评测任务列表
        """
        tasks = []
        reference_answers = reference_answers or {}
        
        for case in cases:
            # 只转换已审核的案例
            if case.status != "reviewed":
                logger.warning(f"⚠️ 跳过未审核案例: {case.id}")
                continue
            
            ref_answer = reference_answers.get(case.id)
            task = self.convert_case(case, reference_answer=ref_answer)
            tasks.append(task)
        
        logger.info(f"✅ 转换完成: {len(tasks)}/{len(cases)} 个案例")
        return tasks
    
    def export_to_yaml(
        self,
        tasks: List[Task],
        suite_name: str = "regression_from_failures",
        suite_id: Optional[str] = None
    ) -> str:
        """
        导出任务为 YAML 格式
        
        Args:
            tasks: 任务列表
            suite_name: 套件名称
            suite_id: 套件ID（可选）
            
        Returns:
            str: YAML 文件路径
        """
        suite_id = suite_id or f"{suite_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # 构建套件数据
        suite_data = {
            "id": suite_id,
            "name": suite_name,
            "description": f"从失败案例自动生成的回归测试套件（{len(tasks)} 个任务）",
            "category": "regression",
            "default_trials": 3,
            "metadata": {
                "version": "1.0.0",
                "generated_at": datetime.now().isoformat(),
                "source": "failure_cases",
            },
            "tasks": [self._task_to_dict(task) for task in tasks],
        }
        
        # 保存 YAML
        yaml_file = self.output_dir / f"{suite_id}.yaml"
        with open(yaml_file, "w", encoding="utf-8") as f:
            yaml.dump(suite_data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
        
        logger.info(f"✅ 导出完成: {yaml_file}")
        return str(yaml_file)
    
    def export_to_promptfoo(
        self,
        cases: List[FailureCase],
        suite_name: str = "promptfoo_regression",
        output_dir: Optional[Path] = None
    ) -> str:
        """
        将失败案例导出为 Promptfoo YAML 格式
        
        只导出适合 Promptfoo 的案例（单轮、无工具调用、无检查点）
        
        Args:
            cases: 失败案例列表
            suite_name: 套件名称
            output_dir: 输出目录（可选，默认使用 promptfoo/ 目录）
            
        Returns:
            str: YAML 文件路径
        """
        output_dir = output_dir or self.output_dir.parent / "promptfoo"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # 筛选适合 Promptfoo 的案例
        promptfoo_cases = []
        for case in cases:
            # 只处理单轮对话、无工具调用的案例
            if (case.status == "reviewed" and 
                not case.tool_calls and 
                len(case.conversation_history or []) <= 1):
                promptfoo_cases.append(case)
        
        if not promptfoo_cases:
            logger.warning("⚠️ 没有适合 Promptfoo 的案例（需要单轮、无工具调用）")
            return ""
        
        # 构建 Promptfoo 配置
        promptfoo_config = {
            "description": f"从失败案例生成的 Promptfoo 回归测试（{len(promptfoo_cases)} 个）",
            "prompts": [
                {
                    "prompt": "{{input}}",
                    "provider": "openai:chat:gpt-4",  # 默认，实际使用时需要配置
                    "config": {
                        "temperature": 0.7
                    }
                }
            ],
            "tests": []
        }
        
        # 为每个案例创建测试
        for case in promptfoo_cases:
            test = {
                "vars": {
                    "input": case.user_query
                },
                "assert": []
            }
            
            # 根据失败类型添加断言
            if case.failure_type == FailureType.USER_NEGATIVE_FEEDBACK:
                # 用户反馈不满意，使用 LLM-as-Judge 检查质量
                test["assert"].append({
                    "type": "llm-rubric",
                    "value": "响应应该满足用户需求，不应引起不满"
                })
            elif case.failure_type == FailureType.OVER_ENGINEERING:
                # 过度工程化，检查响应简洁性
                test["assert"].append({
                    "type": "llm-rubric",
                    "value": "响应应该简洁直接，不应过度复杂"
                })
            elif case.failure_type == FailureType.LOGICAL_INCOHERENCE:
                # 逻辑不一致
                test["assert"].append({
                    "type": "llm-rubric",
                    "value": "响应应该逻辑一致，不应自相矛盾"
                })
            else:
                # 默认：检查响应不为空
                test["assert"].append({
                    "type": "not-contains",
                    "value": ""
                })
            
            # 如果有参考答案，添加相似度检查
            if case.agent_response:
                test["assert"].append({
                    "type": "similar",
                    "threshold": 0.7
                })
            
            # 添加成本限制
            test["assert"].append({
                "type": "cost",
                "threshold": 5000  # 默认限制
            })
            
            promptfoo_config["tests"].append(test)
        
        # 保存 YAML
        yaml_file = output_dir / f"{suite_name}.yaml"
        with open(yaml_file, "w", encoding="utf-8") as f:
            yaml.dump(promptfoo_config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
        
        logger.info(f"✅ Promptfoo 配置导出完成: {yaml_file} ({len(promptfoo_cases)} 个测试)")
        return str(yaml_file)
    
    def _task_to_dict(self, task: Task) -> Dict[str, Any]:
        """将 Task 转换为字典（用于 YAML 导出）"""
        return {
            "id": task.id,
            "description": task.description,
            "category": task.category,
            "input": {
                "user_query": task.input.user_query,
                "conversation_history": task.input.conversation_history,
                "context": task.input.context,
                "files": task.input.files,
            },
            "expected_outcome": {
                "intent": task.expected_outcome.intent,
                "tool_calls": task.expected_outcome.tool_calls,
                "response_contains": task.expected_outcome.response_contains,
            },
            "graders": [
                {
                    "type": g.type.value,
                    "name": g.name,
                    "check": g.check,
                    "rubric": g.rubric,
                    "min_score": g.min_score,
                    "weight": g.weight,
                }
                for g in task.graders
            ],
            "trials": task.trials,
            "timeout_seconds": task.timeout_seconds,
            "tags": task.tags,
            "metadata": task.metadata,
            "checkpoints": [
                {
                    "name": cp.name,
                    "check": cp.check,
                    "description": cp.description,
                }
                for cp in task.checkpoints
            ],
            "reference_answer": task.reference_answer,
        }
